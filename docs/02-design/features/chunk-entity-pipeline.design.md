# Design: Chunk-Entity Pipeline (孤立Chunk Entity自動抽出・接続)

> **Plan参照**: `docs/01-plan/features/chunk-entity-pipeline.plan.md`
> **Design Version**: 1.0
> **Date**: 2026-02-27

---

## 1. アーキテクチャ概要

```
┌─────────────────────────────────────────────────────────────┐
│                   batch_extract.py (CLI)                     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Summary      │  │ Pattern      │  │ Neo4j             │  │
│  │ Extractor    │  │ Extractor    │  │ Writer            │  │
│  │              │  │              │  │                   │  │
│  │ commands/    │  │ JA_PATTERNS  │  │ MERGE Entity      │  │
│  │ error-codes/ │  │ EN_PATTERNS  │  │ MERGE MENTIONS    │  │
│  │ configs/     │  │ KO_PATTERNS  │  │ Batch UNWIND      │  │
│  │ glossary/    │  │ OF_PATTERNS  │  │                   │  │
│  │ concepts/    │  │              │  │                   │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘  │
│         │                 │                    │             │
│         └────────┬────────┘                    │             │
│                  ▼                             │             │
│         ┌──────────────┐                       │             │
│         │ Normalizer   │───────────────────────┘             │
│         │ dedup+lower  │                                     │
│         └──────────────┘                                     │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   Neo4j Database      │
              │                       │
              │  (Chunk)──MENTIONS──▶(Entity)  │
              └───────────────────────┘
```

---

## 2. データモデル

### 2.1 既存EntityType enum (変更なし)

`app/api/models/knowledge_graph.py` の `EntityType` をそのまま使用:

| EntityType | 用途 | 既存Entity数 |
|-----------|------|------------|
| COMMAND | コマンド・ツール名 | 336 |
| ERROR_CODE | エラーコード | 2,326 |
| CONFIG | 設定パラメータ | 0 (新規) |
| CONCEPT | 概念・用語 | 168 |
| PRODUCT | 製品名 | 0 (新規) |
| TECHNOLOGY | 技術名 | 0 (新規) |
| TERM | 用語定義 | 0 (新規) |
| ACRONYM | 略語 | 277 (追加見込み) |

### 2.2 ExtractedEntity (パイプライン内部モデル)

```python
@dataclass
class ExtractedEntity:
    name: str           # 正規化済みEntity名 (小文字 or 原形保持)
    entity_type: str    # EntityType enum value
    confidence: float   # 0.0 - 1.0
    source: str         # "pattern" | "summary" | "tfidf"
    chunk_id: str       # 対象Chunk ID
```

### 2.3 Neo4j Entity ノードプロパティ

```
(:Entity {
    name: String,          -- 正規化名 (MERGEキー)
    type: String,          -- EntityType enum value
    confidence: Float,     -- 最大値保持 (ON MATCH更新)
    source: String,        -- 'pipeline_v1'
    created_at: DateTime   -- 作成日時
})
```

### 2.4 MENTIONS 関係

```
(:Chunk {id: $chunk_id})-[:MENTIONS]->(:Entity {name: $name})
```
- MERGE で冪等性担保
- 追加プロパティなし (シンプルに接続のみ)

---

## 3. モジュール設計

### 3.1 `scripts/entity_pipeline/__init__.py`

パッケージ初期化のみ。

### 3.2 `scripts/entity_pipeline/summary_extractor.py`

**責務**: `uploads/summaries/` からEntity辞書を構築

```python
class SummaryExtractor:
    """Summary Markdown → Entity辞書変換"""

    def __init__(self, summaries_dir: str = "uploads/summaries"):
        self.summaries_dir = Path(summaries_dir)
        self.entity_dict: Dict[str, EntityInfo] = {}

    def load_all(self) -> Dict[str, EntityInfo]:
        """全Summaryカテゴリをロード"""
        self._load_commands()     # commands/*.md → COMMAND
        self._load_error_codes()  # error-codes/*.md → ERROR_CODE
        self._load_configs()      # configs/*.md → CONFIG
        self._load_glossary()     # glossary/*.md → ACRONYM/CONCEPT
        self._load_concepts()     # concepts/*.md → CONCEPT
        return self.entity_dict
```

**カテゴリ別パース仕様**:

#### commands/*.md
```
フォーマット:
  ## <command_name>
  - **지원 제품**: ...
  - **설명**: ...
  - **구문**: `command [options]`

パースルール:
  - `## ` 直後の単語 → Entity名 (type=COMMAND, confidence=0.95)
  - `구문` フィールドのバッククォート内テキスト → サブコマンド抽出
```

#### error-codes/*.md
```
フォーマット:
  ### ERROR_NAME (-XXXX)
  - **설명**: ...
  - **대처방법**: ...

パースルール:
  - `### ` 直後の `NAME (-NUMBER)` → Entity名=NAME, alias=-NUMBER
  - (type=ERROR_CODE, confidence=0.95)
```

#### configs/*.md
```
フォーマット:
  | `param_name` | 설명 | 소스 |

パースルール:
  - テーブル行のバッククォート内パラメータ名 → Entity名
  - (type=CONFIG, confidence=0.90)
```

#### glossary/*.md
```
フォーマット:
  ## TERM_NAME
  - **정식명칭**: Full Name
  - **설명**: ...

パースルール:
  - `## ` 直後の語 → Entity名 (type=ACRONYM, confidence=0.95)
  - `정식명칭` フィールド → alias
```

#### concepts/*.md
```
フォーマット:
  ## concept_name
  - **제품**: ...
  - **설명**: ...

パースルール:
  - `## ` 直後の語 → Entity名 (type=CONCEPT, confidence=0.90)
```

**EntityInfo構造**:
```python
@dataclass
class EntityInfo:
    name: str
    entity_type: str
    confidence: float
    aliases: List[str]     # 別名リスト (略語展開、エラー番号等)
    source_file: str       # 元ファイルパス
```

### 3.3 `scripts/entity_pipeline/pattern_extractor.py`

**責務**: ChunkテキストからパターンベースでEntity抽出

```python
class PatternExtractor:
    """拡張正規表現パターンによるEntity抽出"""

    def __init__(self, summary_dict: Dict[str, EntityInfo]):
        self.summary_dict = summary_dict
        self._compile_patterns()

    def extract(self, chunk_id: str, text: str) -> List[ExtractedEntity]:
        """1つのChunkからEntity抽出"""
        entities = []
        seen = set()

        # Phase A: Summary辞書マッチ (最高精度)
        entities.extend(self._match_summary_dict(chunk_id, text, seen))

        # Phase B: 正規表現パターン (高精度)
        entities.extend(self._match_patterns(chunk_id, text, seen))

        # Phase C: 頻出カタカナ語 (中精度、Phase A/Bでゼロの場合のみ)
        if not entities:
            entities.extend(self._extract_katakana_terms(chunk_id, text, seen))

        return entities
```

#### パターン定義

**OPENFRAME_PATTERNS** (新規追加):
```python
OPENFRAME_PATTERNS = {
    # OpenFrame tools/commands - 包括的パターン
    "COMMAND": [
        # *mgr commands (any pattern: xxxmgr)
        r'\b[a-z]{2,10}mgr\b',
        # OpenFrame specific tools
        r'\b(?:osctdl(?:init|rm|update)|oscmcsvr|oscscview|oscsddump|'
        r'oscsdgen|oscfdump|oscfgen|oscmgr|oscrsasvr)\b',
        # OF tools: ds*, of*, tjes*
        r'\b(?:dsmigin|dsmigout|dsview|dscreate|dsdelete|dscopy|'
        r'dsrename|dslist|dsentool)\b',
        r'\b(?:ofcbppf|ofconfig|oferror|ofjclpp|offile|'
        r'ofsautil|ofudtool|ofrpmsvr)\b',
        r'\b(?:tjesinit|tjesdown|tjesclean|tjclrun|tjesmgr)\b',
        # Mainframe utilities
        r'\b(?:IDCAMS|IEBGENER|IEBCOPY|IEFBR14|SORT|DFSORT|'
        r'IKJEFT01|ADRDSSU|AMASPZAP)\b',
        # JCL keywords (大文字のみ — 小文字除外でノイズ防止)
        r'\b(?:JOB|EXEC|DD|PROC|PEND|IF|THEN|ELSE|ENDIF)\b',
        # System boot/shutdown
        r'\b(?:tmboot|tmdown|ofboot|ofdown|jesinit|jesdown|'
        r'tmadmin|oscboot|oscdown)\b',
    ],

    # Error codes
    "ERROR_CODE": [
        r'(?<![A-Za-z])-\d{4,5}(?!\d)',
        r'\b[A-Z]{2,10}_ERR_[A-Z_]+\b',
        r'\b(?:ABEND|ABEND)\s*S[0-9A-F]{3,4}\b',
        r'\bS[0-9][0-9A-F]{2}\b',
    ],

    # Configuration
    "CONFIG": [
        r'\b(?:oframe|tjes|hidb|osc|tacf|ds|batch|ofgw|ofmanager)\.conf\b',
        r'\b[A-Z][A-Z0-9_]{2,}(?:_DIR|_HOME|_BASE|_PATH|_URL|_PORT|_SID)\b',
        r'\b(?:OPENFRAME_HOME|TMAX_HOST_ADDR|TB_SID|COBDIR|'
        r'TMAXDIR|TMAX_DIR|OFGW_HOME|OFMANAGER_HOME)\b',
    ],

    # Products
    "PRODUCT": [
        r'\bOpenFrame[/ ]?(?:Base|TJES|OSC|TACF|HIDB|ASM|COBOL|Manager|Gateway|Studio)\b',
        r'\b(?:Tmax|Tibero|JEUS|ProObject|WebtoB)\s*\d*\b',
        r'\b(?:OFMiner|OFStudio|OFManager|OFGW)\b',
    ],

    # Technology/Architecture terms (English)
    "TECHNOLOGY": [
        r'\b(?:VSAM|KSDS|ESDS|RRDS|LDS|PDS|GDG|SMS)\b',
        r'\b(?:CICS|IMS|DB2|JES2|JES3|TSO|ISPF|VTAM)\b',
        r'\b(?:COBOL|JCL|REXX|PL/I|Assembler)\b',
        r'\b(?:TCP/IP|FTP|HTTP|SSL|TLS)\b',
    ],
}

# 日本語パターン
JAPANESE_PATTERNS = {
    "CONCEPT": [
        # カタカナ技術用語 (3文字以上)
        r'[ァ-ヶー]{3,}(?:・[ァ-ヶー]{2,})*',
        # 日本語複合技術用語
        r'(?:共有メモリ|バッチ処理|トランザクション処理|データセット|'
        r'リージョン|オンライン|オフライン|カタログ|ボリューム|'
        r'コンパイラ|プリプロセッサ|エンコーディング|デバッグ)',
    ],
    "CONFIG": [
        # 日本語設定用語
        r'(?:環境変数|設定ファイル|構成ファイル|パラメータ|'
        r'プロパティ|セクション)',
    ],
}
```

#### Summary辞書マッチング
```python
def _match_summary_dict(self, chunk_id, text, seen) -> List[ExtractedEntity]:
    """Summary辞書の全エントリをチャンクテキストに対してマッチ"""
    results = []
    text_lower = text.lower()

    for name, info in self.summary_dict.items():
        # 完全一致 (大文字小文字無視)
        if name.lower() in text_lower:
            if name.lower() not in seen:
                seen.add(name.lower())
                results.append(ExtractedEntity(
                    name=name,
                    entity_type=info.entity_type,
                    confidence=0.95,
                    source="summary",
                    chunk_id=chunk_id,
                ))

        # alias マッチ
        for alias in info.aliases:
            if alias.lower() in text_lower and alias.lower() not in seen:
                seen.add(alias.lower())
                results.append(ExtractedEntity(
                    name=name,  # 正規名に統一
                    entity_type=info.entity_type,
                    confidence=0.90,
                    source="summary_alias",
                    chunk_id=chunk_id,
                ))

    return results
```

#### カタカナ語抽出 (フォールバック)
```python
# 最小3文字のカタカナ連続 (ー含む)
# 不要語リストで汎用語を除外
KATAKANA_STOPWORDS = {
    'システム', 'サーバー', 'クライアント', 'ファイル', 'メッセージ',
    'エラー', 'パラメータ', 'プログラム', 'モジュール', 'ライブラリ',
    'リクエスト', 'レスポンス', 'ディレクトリ', 'インストール',
    'アプリケーション', 'ユーザー', 'コマンド', 'オプション',
    'ガイド', 'マニュアル', 'ドキュメント', 'セクション',
}
```

### 3.4 `scripts/entity_pipeline/neo4j_writer.py`

**責務**: 抽出済みEntityをNeo4jにバッチ書き込み

```python
class Neo4jBatchWriter:
    """Neo4jバッチ書き込み (MERGE保証)"""

    BATCH_SIZE = 100  # 1クエリあたりのEntity数
    INTER_BATCH_DELAY = 0.1  # バッチ間の待機秒

    def __init__(self, neo4j_uri, neo4j_user, neo4j_password):
        self.driver = GraphDatabase.driver(
            neo4j_uri, auth=(neo4j_user, neo4j_password)
        )

    async def write_batch(self, entities: List[ExtractedEntity]) -> WriteResult:
        """Entityバッチ書き込み"""
        # Entity名で重複排除 (chunk_id別にグループ化)
        unique = self._deduplicate(entities)

        created_entities = 0
        created_mentions = 0

        for i in range(0, len(unique), self.BATCH_SIZE):
            batch = unique[i:i + self.BATCH_SIZE]
            result = self._execute_merge(batch)
            created_entities += result.entities
            created_mentions += result.mentions

            if i + self.BATCH_SIZE < len(unique):
                await asyncio.sleep(self.INTER_BATCH_DELAY)

        return WriteResult(
            entities_created=created_entities,
            mentions_created=created_mentions,
        )
```

**Cypherクエリ**:
```cypher
UNWIND $batch AS item
MERGE (e:Entity {name: item.name})
  ON CREATE SET
    e.type = item.type,
    e.confidence = item.confidence,
    e.source = 'pipeline_v1',
    e.created_at = datetime()
  ON MATCH SET
    e.confidence = CASE
      WHEN item.confidence > e.confidence THEN item.confidence
      ELSE e.confidence END,
    e.source = CASE
      WHEN e.source IS NULL THEN 'pipeline_v1'
      ELSE e.source END
WITH e, item
MATCH (c:Chunk {id: item.chunk_id})
MERGE (c)-[:MENTIONS]->(e)
RETURN
  sum(CASE WHEN e.created_at = datetime() THEN 1 ELSE 0 END) AS new_entities,
  count(*) AS total_mentions
```

### 3.5 `scripts/entity_pipeline/batch_extract.py`

**責務**: パイプライン全体オーケストレーション

```python
"""
Chunk-Entity Pipeline: 孤立ChunkへのEntity自動抽出・接続

Usage:
    python -m scripts.entity_pipeline.batch_extract [options]

Options:
    --dry-run        実行せずに抽出結果のみ表示
    --batch-size N   Chunkフェッチバッチサイズ (default: 500)
    --limit N        処理Chunk数上限 (default: 全件)
    --report         最終レポートをJSON出力
    --skip-summary   Summary辞書マッチをスキップ
"""

async def main():
    # 1. 設定ロード (.envからNeo4j接続情報)
    config = load_config()

    # 2. Summary辞書構築
    summary_ext = SummaryExtractor(config.summaries_dir)
    entity_dict = summary_ext.load_all()
    print(f"Summary辞書: {len(entity_dict)} エントリ")

    # 3. パターン抽出器初期化
    pattern_ext = PatternExtractor(entity_dict)

    # 4. Neo4jライター初期化
    writer = Neo4jBatchWriter(config.neo4j_uri, config.neo4j_user, config.neo4j_password)

    # 5. 処理前統計
    before_stats = await writer.get_stats()
    print(f"処理前: {before_stats}")

    # 6. 孤立Chunkバッチ処理
    total_processed = 0
    total_entities_extracted = 0
    total_entities_written = 0
    total_mentions_written = 0

    skip = 0
    while True:
        # 孤立Chunkフェッチ
        chunks = await writer.fetch_orphan_chunks(skip, config.batch_size)
        if not chunks:
            break

        # バッチ内全Chunkからentity抽出
        all_extracted = []
        for chunk in chunks:
            extracted = pattern_ext.extract(chunk['id'], chunk['content'])
            all_extracted.extend(extracted)

        # Neo4j書き込み
        if all_extracted and not config.dry_run:
            result = await writer.write_batch(all_extracted)
            total_entities_written += result.entities_created
            total_mentions_written += result.mentions_created

        total_processed += len(chunks)
        total_entities_extracted += len(all_extracted)
        skip += config.batch_size

        # 進捗表示 (10%ごと)
        progress = total_processed / before_stats.orphan_chunks * 100
        if int(progress) % 10 == 0:
            print(f"  {progress:.0f}% ({total_processed}/{before_stats.orphan_chunks})")

    # 7. 処理後統計
    after_stats = await writer.get_stats()

    # 8. レポート出力
    report = {
        "timestamp": datetime.now().isoformat(),
        "before": asdict(before_stats),
        "after": asdict(after_stats),
        "processing": {
            "chunks_processed": total_processed,
            "entities_extracted": total_entities_extracted,
            "entities_written": total_entities_written,
            "mentions_written": total_mentions_written,
            "summary_dict_size": len(entity_dict),
        },
        "improvement": {
            "orphan_reduction": f"{before_stats.orphan_chunks} → {after_stats.orphan_chunks}",
            "orphan_pct_before": f"{before_stats.orphan_pct:.1f}%",
            "orphan_pct_after": f"{after_stats.orphan_pct:.1f}%",
            "new_entities": after_stats.total_entities - before_stats.total_entities,
            "new_mentions": after_stats.total_mentions - before_stats.total_mentions,
        }
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))

    writer.close()
```

---

## 4. knowledge_graph_service.py 変更設計

### 4.1 ENTITY_PATTERNS拡張

既存パターン (line 42-99) に以下を**追加**:

```python
# 追加: OpenFrame tool/command patterns (broader coverage)
EntityType.COMMAND: [
    # --- 既存 ---
    r'\b(?:tjes|hidb|of|tac|tso|vtam|cics|batch|online)mgr\b',
    r'\b(?:tjesmgr|hidbmgr|ofmgr|tacfmgr|tsomgr|vtammgr|cicsmgr)\s+[A-Z]+\b',
    r'\b(?:IDCAMS|IEBGENER|IEBCOPY|IEFBR14|SORT|DFSORT)\b',
    r'\b(?:DD|DSN|DISP|SPACE|DCB|VOL|UNIT|SYSOUT|COND)\b',
    # --- 新規 ---
    r'\b[a-z]{2,10}mgr\b',                    # 汎用*mgrパターン
    r'\b(?:osctdl(?:init|rm|update))\b',       # OSC TDLツール群
    r'\b(?:dsmigin|dsmigout|dsview|dscreate|dsdelete)\b',  # DSツール
    r'\b(?:ofcbppf|ofconfig|oferror|ofjclpp)\b',  # OFツール
    r'\b(?:tmboot|tmdown|ofboot|ofdown)\b',    # システム起動/停止
],

# 追加: Product type (新規)
EntityType.PRODUCT: [
    r'\bOpenFrame[/ ]?(?:Base|TJES|OSC|TACF|HIDB|ASM|COBOL|Manager|Gateway|Studio)\b',
    r'\b(?:Tmax|Tibero|JEUS|ProObject|WebtoB|OFMiner|OFStudio)\b',
],
```

### 4.2 JAPANESE_PATTERNS (新規追加)

```python
JAPANESE_PATTERNS = {
    EntityType.CONCEPT: [
        r'[ァ-ヶー]{3,}(?:・[ァ-ヶー]{2,})*',
        r'(?:共有メモリ|バッチ処理|トランザクション|データセット|'
        r'リージョン|カタログ|ボリューム)',
    ],
}
```

### 4.3 `_detect_language` 拡張

```python
def _detect_language(self, text: str) -> str:
    korean_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7a3')
    japanese_chars = sum(1 for c in text if
        '\u3040' <= c <= '\u309f' or  # ひらがな
        '\u30a0' <= c <= '\u30ff' or  # カタカナ
        '\u4e00' <= c <= '\u9fff')    # 漢字
    total_chars = len(text.replace(' ', ''))
    if total_chars > 0:
        if korean_chars / total_chars > 0.3:
            return "ko"
        if japanese_chars / total_chars > 0.1:
            return "ja"
    return "en"
```

### 4.4 `extract_entities` 拡張

```python
for entity_type in types_to_extract:
    patterns = self.ENTITY_PATTERNS.get(entity_type, [])
    if language == "ko":
        patterns.extend(self.KOREAN_PATTERNS.get(entity_type, []))
    if language == "ja":                                          # 新規
        patterns.extend(self.JAPANESE_PATTERNS.get(entity_type, []))  # 新規
```

---

## 5. Cypherクエリ仕様

### 5.1 孤立Chunkフェッチ

```cypher
MATCH (c:Chunk)
WHERE NOT (c)-[:MENTIONS]->(:Entity)
  AND c.content IS NOT NULL
  AND size(c.content) >= 30
RETURN c.id AS id, c.content AS content
ORDER BY c.id
SKIP $skip LIMIT $batch_size
```

### 5.2 バッチEntity MERGE + MENTIONS接続

```cypher
UNWIND $batch AS item
MERGE (e:Entity {name: item.name})
  ON CREATE SET
    e.type = item.type,
    e.confidence = item.confidence,
    e.source = 'pipeline_v1',
    e.created_at = datetime()
  ON MATCH SET
    e.confidence = CASE
      WHEN item.confidence > e.confidence
      THEN item.confidence
      ELSE e.confidence END
WITH e, item
MATCH (c:Chunk {id: item.chunk_id})
MERGE (c)-[:MENTIONS]->(e)
```

### 5.3 統計クエリ

```cypher
-- 全体統計
MATCH (c:Chunk)
OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
WITH c, count(e) AS entity_count
RETURN
  count(c) AS total_chunks,
  sum(CASE WHEN entity_count > 0 THEN 1 ELSE 0 END) AS connected_chunks,
  sum(CASE WHEN entity_count = 0 THEN 1 ELSE 0 END) AS orphan_chunks,
  avg(entity_count) AS avg_entities_per_chunk

-- Entity種別分布
MATCH (e:Entity)
WHERE e.source = 'pipeline_v1'
RETURN e.type AS type, count(e) AS cnt
ORDER BY cnt DESC

-- 特定キーワード検証 (osctdlrm)
MATCH (c:Chunk)-[:MENTIONS]->(e:Entity {name: 'osctdlrm'})
RETURN c.id, substring(c.content, 0, 100) AS preview
```

---

## 6. Entity正規化ルール

### 6.1 大文字/小文字統一

| カテゴリ | ルール | 例 |
|---------|--------|-----|
| COMMAND | 小文字保持 (原形) | `tjesmgr`, `osctdlrm`, `dsmigin` |
| ERROR_CODE | 大文字保持 | `DSALC_ERR_NOT_FOUND`, `S0C7` |
| CONFIG | 原形保持 | `oframe.conf`, `OPENFRAME_HOME` |
| PRODUCT | 原形保持 | `OpenFrame Base`, `Tibero` |
| CONCEPT | 原形保持 | `バッチ処理`, `VSAM` |
| ACRONYM | 大文字 | `TJES`, `TACF`, `HIDB` |

### 6.2 最小長フィルタ

| カテゴリ | 最小文字数 | 理由 |
|---------|-----------|------|
| COMMAND | 3 | `DD`, `JOB` は2文字だが許可 (JCLキーワード) |
| ERROR_CODE | 4 | `-5001` (ダッシュ含む) |
| CONFIG | 3 | `ds` 等短い設定名 |
| PRODUCT | 4 | `JEUS` 等 |
| CONCEPT (カタカナ) | 3 | 2文字カタカナはノイズ多い |
| ACRONYM | 2 | `DB`, `AI` 等2文字略語あり |

### 6.3 不要語 (Stopwords)

```python
ENTITY_STOPWORDS = {
    # 汎用すぎる英語
    'the', 'this', 'that', 'with', 'from', 'for', 'and', 'not',
    'null', 'true', 'false', 'none', 'void',
    # 汎用すぎるカタカナ
    'システム', 'サーバー', 'クライアント', 'ファイル', 'メッセージ',
    'エラー', 'パラメータ', 'プログラム', 'モジュール', 'ライブラリ',
    'アプリケーション', 'ユーザー', 'コマンド', 'オプション',
    'インストール', 'ディレクトリ', 'ガイド', 'マニュアル',
    'ドキュメント', 'セクション', 'バージョン', 'データ',
    # 数字のみ
    # (regex: ^\d+$ → skip)
}
```

---

## 7. エラーハンドリング

| シナリオ | 対応 |
|---------|------|
| Chunkコンテンツが文字化け (UTF-8デコード不可) | スキップ + `skipped_chunks` カウンタ増加 |
| Neo4j接続タイムアウト | 3回リトライ (exponential backoff) |
| Entity名が空 or stopword | スキップ |
| MERGE中のデッドロック | リトライ1回 |
| Summary MDファイル読み込みエラー | 警告ログ + 続行 |

---

## 8. CLI引数設計

```
python -m scripts.entity_pipeline.batch_extract [OPTIONS]

OPTIONS:
  --dry-run           抽出のみ実行 (Neo4j書き込みなし)
  --batch-size N      Chunkフェッチバッチサイズ [default: 500]
  --limit N           処理Chunk数上限 [default: 0 = 全件]
  --report FILE       レポートJSON出力先 [default: stdout]
  --skip-summary      Summary辞書マッチをスキップ
  --skip-patterns     正規表現パターンマッチをスキップ
  --verbose           詳細ログ出力
  --neo4j-uri URI     Neo4j URI [default: .envから]
  --neo4j-user USER   Neo4j user [default: .envから]
  --neo4j-pass PASS   Neo4j password [default: .envから]
```

---

## 9. 実装順序 (5ステップ)

| Step | ファイル | 内容 | 依存 |
|------|---------|------|------|
| **1** | `app/api/services/knowledge_graph_service.py` | ENTITY_PATTERNS拡張 + JAPANESE_PATTERNS + _detect_language日本語対応 | なし |
| **2** | `scripts/entity_pipeline/summary_extractor.py` | Summary辞書ローダー (5カテゴリ) | なし |
| **3** | `scripts/entity_pipeline/pattern_extractor.py` | パターンマッチャー + Summary辞書マッチ + カタカナフォールバック | Step 2 |
| **4** | `scripts/entity_pipeline/neo4j_writer.py` | バッチMERGE + 統計クエリ + 孤立Chunkフェッチ | なし |
| **5** | `scripts/entity_pipeline/batch_extract.py` | メインパイプライン + CLI + レポート | Step 2-4 |

---

## 10. 検証シナリオ

### V-1: 孤立Chunk削減率
```bash
# 実行前
python -m scripts.entity_pipeline.batch_extract --dry-run --limit 100
# 確認: 100 chunks中のentity抽出数

# 本番実行
python -m scripts.entity_pipeline.batch_extract --report report.json
# 確認: report.json の orphan_pct_after < 20%
```

### V-2: osctdlrmの具体的検証
```cypher
-- Entity存在確認
MATCH (e:Entity) WHERE e.name =~ '(?i)osctdlrm.*' RETURN e

-- MENTIONS接続確認
MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
WHERE e.name =~ '(?i)osctdlrm.*'
RETURN c.id, substring(c.content, 0, 100)
```

### V-3: 冪等性検証
```bash
# 1回目
python -m scripts.entity_pipeline.batch_extract --report r1.json
# 2回目
python -m scripts.entity_pipeline.batch_extract --report r2.json
# 比較: r2のnew_entities == 0, new_mentions == 0
```

### V-4: 既存データ保全
```cypher
-- 実行前にスナップショット
MATCH (c:Chunk)-[r:MENTIONS]->(e:Entity)
WHERE e.source <> 'pipeline_v1' OR e.source IS NULL
RETURN count(r) AS existing_mentions
-- 実行後に同クエリ → 数値が同一であること
```
