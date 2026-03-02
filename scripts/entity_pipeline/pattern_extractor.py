"""
Pattern Extractor - ChunkテキストからEntity抽出

3段階抽出:
  Phase A: Summary辞書マッチ (最高精度 conf=0.95)
  Phase B: 正規表現パターン (高精度 conf=0.80)
  Phase C: カタカナ語フォールバック (中精度 conf=0.70、A/Bゼロの場合のみ)
"""
import re
from dataclasses import dataclass
from typing import Dict, List, Set

from .summary_extractor import EntityInfo


@dataclass
class ExtractedEntity:
    """抽出されたEntity"""
    name: str
    entity_type: str
    confidence: float
    source: str       # "summary" | "summary_alias" | "pattern" | "katakana"
    chunk_id: str


# OpenFrame/Mainframe 正規表現パターン
OPENFRAME_PATTERNS: Dict[str, List[str]] = {
    "command": [
        # *mgr commands
        r'\b[a-z]{2,10}mgr\b',
        # OSC tools
        r'\b(?:osctdl(?:init|rm|update)|oscmcsvr|oscscview|oscsddump|'
        r'oscsdgen|oscfdump|oscfgen|oscrsasvr)\b',
        # DS tools
        r'\b(?:dsmigin|dsmigout|dsview|dscreate|dsdelete|dscopy|dsrename|dslist|dsentool)\b',
        # OF tools
        r'\b(?:ofcbppf|ofconfig|oferror|ofjclpp|offile|ofsautil|ofudtool|ofrpmsvr)\b',
        # TJES tools
        r'\b(?:tjesinit|tjesdown|tjesclean|tjclrun)\b',
        # Mainframe utilities
        r'\b(?:IDCAMS|IEBGENER|IEBCOPY|IEFBR14|SORT|DFSORT|IKJEFT01|ADRDSSU|AMASPZAP)\b',
        # System boot/shutdown
        r'\b(?:tmboot|tmdown|ofboot|ofdown|jesinit|jesdown|tmadmin|oscboot|oscdown)\b',
    ],
    "error_code": [
        r'(?<![A-Za-z])-\d{4,5}(?!\d)',
        r'\b[A-Z]{2,10}_ERR_[A-Z_]+\b',
        r'\bS[0-9][0-9A-F]{2}\b',
    ],
    "config": [
        r'\b(?:oframe|tjes|hidb|osc|tacf|ds|batch|ofgw|ofmanager)\.conf\b',
        r'\b[A-Z][A-Z0-9_]{2,}(?:_DIR|_HOME|_BASE|_PATH|_URL|_PORT|_SID)\b',
        r'\b(?:OPENFRAME_HOME|TMAX_HOST_ADDR|TB_SID|COBDIR|TMAXDIR|TMAX_DIR)\b',
    ],
    "product": [
        r'\bOpenFrame[/ ]?(?:Base|TJES|OSC|TACF|HIDB|ASM|COBOL|Manager|Gateway|Studio)\b',
        r'\b(?:OFMiner|OFStudio|OFManager|OFGW)\b',
    ],
    "technology": [
        r'\b(?:VSAM|KSDS|ESDS|RRDS|LDS|PDS|GDG|SMS)\b',
        r'\b(?:CICS|IMS|DB2|JES2|JES3|TSO|ISPF|VTAM)\b',
        r'\b(?:COBOL|JCL|REXX|Assembler)\b',
    ],
}

# Entity不要語 (汎用すぎるためノイズとなる語)
ENTITY_STOPWORDS: Set[str] = {
    # 英語汎用語
    'the', 'this', 'that', 'with', 'from', 'for', 'and', 'not', 'are', 'was',
    'null', 'true', 'false', 'none', 'void', 'data', 'type', 'name', 'value',
    'file', 'list', 'info', 'item', 'test', 'user', 'path', 'home', 'base',
    'log', 'err', 'error', 'msg', 'cmd', 'dir', 'src', 'tmp', 'var',
    # カタカナ汎用語 (技術文書で頻出しすぎる)
    'システム', 'サーバー', 'クライアント', 'ファイル', 'メッセージ',
    'エラー', 'パラメータ', 'プログラム', 'モジュール', 'ライブラリ',
    'アプリケーション', 'ユーザー', 'コマンド', 'オプション',
    'インストール', 'ディレクトリ', 'ガイド', 'マニュアル',
    'ドキュメント', 'セクション', 'バージョン', 'データ',
    'リスト', 'テーブル', 'レコード', 'フィールド', 'バッファー',
    'ステータス', 'メソッド', 'プロセス', 'スレッド',
    'ログ', 'タイプ', 'モード', 'ノード', 'キー',
    'サービス', 'リソース',
}

# カタカナ語抽出正規表現
KATAKANA_RE = re.compile(r'[ァ-ヶー]{3,}(?:・[ァ-ヶー]{2,})*')


class PatternExtractor:
    """拡張正規表現パターンによるEntity抽出"""

    def __init__(self, summary_dict: Dict[str, EntityInfo]):
        self.summary_dict = summary_dict

        # Summary辞書を長さ別に事前分割 (高速マッチ用)
        self._long_keys: Dict[str, EntityInfo] = {}   # 5文字以上 (ASCII)
        self._short_keys: Dict[str, EntityInfo] = {}   # 3-4文字
        self._alias_map: Dict[str, EntityInfo] = {}    # alias (5文字以上)
        self._non_ascii_keys: Dict[str, EntityInfo] = {}  # 非ASCII (日本語等)

        for key, info in summary_dict.items():
            if len(key) < 3:
                continue
            if key.lstrip('-').isdigit() and len(key) < 4:
                continue
            # 非ASCIIキーは別管理 (トークン化不可)
            if not key.isascii():
                if len(key) >= 3:
                    self._non_ascii_keys[key] = info
            elif len(key) >= 5:
                self._long_keys[key] = info
            else:
                self._short_keys[key] = info
            # alias展開
            for alias in info.aliases:
                al = alias.lower()
                if len(al) >= 5 and al not in self._alias_map:
                    self._alias_map[al] = info

        # set化 (O(1)ルックアップ用)
        self._long_key_set: Set[str] = set(self._long_keys.keys())
        self._short_key_set: Set[str] = set(self._short_keys.keys())
        self._alias_set: Set[str] = set(self._alias_map.keys())

        # ASCII トークン抽出パターン (プリコンパイル)
        self._ascii_token_re = re.compile(r'[a-z0-9][a-z0-9_\-./]*[a-z0-9]|[a-z0-9]')
        self._split_re = re.compile(r'[_\-./]')

        # パターンをプリコンパイル
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}
        for entity_type, patterns in OPENFRAME_PATTERNS.items():
            self._compiled_patterns[entity_type] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def extract(self, chunk_id: str, text: str) -> List[ExtractedEntity]:
        """1つのChunkからEntity抽出 (3段階)"""
        entities: List[ExtractedEntity] = []
        seen: Set[str] = set()

        # Phase A: Summary辞書マッチ (最高精度)
        entities.extend(self._match_summary_dict(chunk_id, text, seen))

        # Phase B: 正規表現パターン (高精度)
        entities.extend(self._match_patterns(chunk_id, text, seen))

        # Phase C: カタカナ語フォールバック (Phase A/Bでゼロの場合のみ)
        if not entities:
            entities.extend(self._extract_katakana_terms(chunk_id, text, seen))

        return entities

    def _tokenize(self, text_lower: str, text_orig: str) -> Set[str]:
        """テキストからトークンセットを抽出 (O(n)、辞書ルックアップ用)"""
        # ASCII トークン (コマンド、設定、エラーコード等)
        tokens = set(self._ascii_token_re.findall(text_lower))
        # 複合トークンを分割して部分語も追加 (例: openframe_home → openframe, home)
        extra: Set[str] = set()
        for t in tokens:
            for part in self._split_re.split(t):
                if len(part) >= 3:
                    extra.add(part)
        tokens.update(extra)
        # カタカナトークン
        for m in KATAKANA_RE.finditer(text_orig):
            tokens.add(m.group(0))
        return tokens

    def _match_summary_dict(
        self, chunk_id: str, text: str, seen: Set[str]
    ) -> List[ExtractedEntity]:
        """Summary辞書マッチ (トークンベースO(1)ルックアップ版)

        旧実装: 17Kキー × テキスト内検索 = O(17K) per chunk
        新実装: テキスト→~200トークン → set intersection = O(200) per chunk
        """
        results: List[ExtractedEntity] = []
        text_lower = text.lower()

        # === 高速パス: トークンセット → 辞書set intersection ===
        tokens = self._tokenize(text_lower, text)

        # 長いキー (5+文字): トークンとの交差でO(1)マッチ
        for key in tokens & self._long_key_set:
            info = self._long_keys[key]
            norm = info.name.lower()
            if norm not in seen and norm not in ENTITY_STOPWORDS:
                seen.add(norm)
                results.append(ExtractedEntity(
                    name=info.name,
                    entity_type=info.entity_type,
                    confidence=0.95,
                    source="summary",
                    chunk_id=chunk_id,
                ))

        # 短いキー (3-4文字): トークンマッチ (境界は分割で保証)
        for key in tokens & self._short_key_set:
            info = self._short_keys[key]
            norm = info.name.lower()
            if norm not in seen and norm not in ENTITY_STOPWORDS:
                seen.add(norm)
                results.append(ExtractedEntity(
                    name=info.name,
                    entity_type=info.entity_type,
                    confidence=0.95,
                    source="summary",
                    chunk_id=chunk_id,
                ))

        # alias マッチ
        for key in tokens & self._alias_set:
            info = self._alias_map[key]
            norm = info.name.lower()
            if norm not in seen and norm not in ENTITY_STOPWORDS:
                seen.add(norm)
                results.append(ExtractedEntity(
                    name=info.name,
                    entity_type=info.entity_type,
                    confidence=0.90,
                    source="summary_alias",
                    chunk_id=chunk_id,
                ))

        # === 低速パス: 非ASCIIキー (日本語等、トークン化困難) ===
        # 数が少ないため(~数百件) 従来の in 演算子チェック
        for key, info in self._non_ascii_keys.items():
            if key in text_lower or key in text:
                norm = info.name.lower()
                if norm not in seen and norm not in ENTITY_STOPWORDS:
                    seen.add(norm)
                    results.append(ExtractedEntity(
                        name=info.name,
                        entity_type=info.entity_type,
                        confidence=0.95,
                        source="summary",
                        chunk_id=chunk_id,
                    ))

        return results

    def _match_patterns(
        self, chunk_id: str, text: str, seen: Set[str]
    ) -> List[ExtractedEntity]:
        """正規表現パターンマッチ"""
        results: List[ExtractedEntity] = []

        for entity_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    name = match.group(0).strip()
                    norm = name.lower()
                    if (
                        norm not in seen
                        and norm not in ENTITY_STOPWORDS
                        and len(name) >= 2
                        and not name.isdigit()
                    ):
                        seen.add(norm)
                        results.append(ExtractedEntity(
                            name=name,
                            entity_type=entity_type,
                            confidence=0.80,
                            source="pattern",
                            chunk_id=chunk_id,
                        ))

        return results

    def _extract_katakana_terms(
        self, chunk_id: str, text: str, seen: Set[str]
    ) -> List[ExtractedEntity]:
        """カタカナ技術用語フォールバック (3文字以上)"""
        results: List[ExtractedEntity] = []

        for match in KATAKANA_RE.finditer(text):
            term = match.group(0)
            norm = term
            if (
                norm not in seen
                and norm not in ENTITY_STOPWORDS
                and len(term) >= 3
            ):
                seen.add(norm)
                results.append(ExtractedEntity(
                    name=term,
                    entity_type="concept",
                    confidence=0.70,
                    source="katakana",
                    chunk_id=chunk_id,
                ))

        return results
