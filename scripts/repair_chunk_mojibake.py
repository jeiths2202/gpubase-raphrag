#!/usr/bin/env python3
"""
Neo4j Chunk 文字化け (Mojibake) 修復 + 再エンベディング

PDF から抽出された日本語テキストが latin-1 → cp932 エンコーディング不整合で
文字化けした Chunk ノードを検出・修復し、BGE-M3 で再エンベディングして Neo4j を更新する。

修復方法: U+0080〜U+00FF 範囲の連続文字を latin-1 bytes → cp932 デコード

Usage:
    python scripts/repair_chunk_mojibake.py --dry-run          # 検出のみ
    python scripts/repair_chunk_mojibake.py --execute           # 修復実行
    python scripts/repair_chunk_mojibake.py --verify osctdlrm   # 特定 Entity 確認
"""

import argparse
import io
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Windows コンソール文字化け対策: UTF-8 強制
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import httpx
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── 既知の文字化けシグネチャ (latin-1 bytes → cp932 日本語) ───
# 例: ‚Í = は, ‚Ì = の, ‚ð = を, ‚É = に, ‚ª = が
MOJIBAKE_SIGNATURES = [
    "\u201a\u00cd",  # ‚Í → は
    "\u201a\u00cc",  # ‚Ì → の
    "\u201a\u00f0",  # ‚ð → を
    "\u201a\u00c9",  # ‚É → に
    "\u201a\u00aa",  # ‚ª → が
    "\u201a\u00c5",  # ‚Å → で
    "\u201a\u00b7",  # ‚· → し
    "\u201a\u00c8",  # ‚È → な
    "\u201a\u00e8",  # ‚è → り
    "\u201a\u00c6",  # ‚Æ → と
    "\u201a\u00a9",  # ‚© → か
    "\u201a\u00e9",  # ‚é → る
    "\u201a\u00dc",  # ‚Ü → ま
    "\u201a\u00b3",  # ‚³ → さ
    "\u201a\u00bd",  # ‚½ → た
    "\u201a\u00c4",  # ‚Ä → て
    "\u0192\u0081",  # ƒ → メ (start of katakana)
]

# CP932 文字化けで出現する典型的な Unicode ブロック:
# - U+0080-00FF (Latin-1 Supplement)
# - U+0152-0153, U+0160-0161, U+0178, U+017D-017E (Latin Extended)
# - U+0192 (ƒ), U+02C6 (ˆ), U+02DC (~)
# - U+2013-2014 (–—), U+2018-201A ('‚), U+201C-201E (""), U+2020-2021 (†‡)
# - U+2026 (…), U+2030 (‰), U+2039-203A (‹›)
# - U+20AC (€), U+2122 (™)
_MOJIBAKE_CODEPOINTS = set()
# Windows-1252 / CP1252 上位バイトがマッピングされる Unicode
for cp in range(0x80, 0x100):
    _MOJIBAKE_CODEPOINTS.add(cp)
# CP1252 の 0x80-0x9F が割り当てられる Unicode コードポイント
_CP1252_EXTRAS = [
    0x20AC, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021, 0x02C6,
    0x2030, 0x0160, 0x2039, 0x0152, 0x017D, 0x2018, 0x2019, 0x201C,
    0x201D, 0x2013, 0x2014, 0x02DC, 0x2122, 0x0161, 0x203A, 0x0153,
    0x017E, 0x0178,
]
for cp in _CP1252_EXTRAS:
    _MOJIBAKE_CODEPOINTS.add(cp)

# CP1252 byte → Unicode codepoint mapping (0x80-0x9F range)
_CP1252_MAP = {
    0x80: 0x20AC, 0x82: 0x201A, 0x83: 0x0192, 0x84: 0x201E, 0x85: 0x2026,
    0x86: 0x2020, 0x87: 0x2021, 0x88: 0x02C6, 0x89: 0x2030, 0x8A: 0x0160,
    0x8B: 0x2039, 0x8C: 0x0152, 0x8E: 0x017D, 0x91: 0x2018, 0x92: 0x2019,
    0x93: 0x201C, 0x94: 0x201D, 0x95: 0x2022, 0x96: 0x2013, 0x97: 0x2014,
    0x98: 0x02DC, 0x99: 0x2122, 0x9A: 0x0161, 0x9B: 0x203A, 0x9C: 0x0153,
    0x9E: 0x017E, 0x9F: 0x0178,
}
# Reverse: Unicode codepoint → CP1252 byte
_UNICODE_TO_CP1252 = {v: k for k, v in _CP1252_MAP.items()}


def _is_mojibake_char(ch: str) -> bool:
    """文字化け由来の可能性がある文字か判定"""
    return ord(ch) in _MOJIBAKE_CODEPOINTS


def _char_to_byte(ch: str) -> int:
    """Unicode 文字を元の CP1252/Latin-1 バイト値に復元"""
    cp = ord(ch)
    if cp in _UNICODE_TO_CP1252:
        return _UNICODE_TO_CP1252[cp]
    if 0x80 <= cp <= 0xFF:
        return cp
    return cp


def repair_mojibake(text: str) -> str:
    """文字化けテキストを修復。

    CP1252/Latin-1 として誤解釈された CP932 バイト列を検出し、
    元の日本語テキストに復元する。
    """
    result = []
    buf = []

    for ch in text:
        if _is_mojibake_char(ch):
            buf.append(ch)
        else:
            if buf:
                result.append(_decode_buffer(buf))
                buf = []
            result.append(ch)

    if buf:
        result.append(_decode_buffer(buf))

    return ''.join(result)


def _decode_buffer(buf: List[str]) -> str:
    """文字化けバッファを CP932 デコード"""
    try:
        raw_bytes = bytes(_char_to_byte(ch) for ch in buf)
        return raw_bytes.decode('cp932')
    except (UnicodeDecodeError, ValueError, OverflowError):
        # フォールバック: デコード不可ならそのまま返す
        return ''.join(buf)


def _count_fullwidth_japanese(text: str) -> int:
    """全角日本語文字 (ひらがな / カタカナ / 漢字) をカウント。半角カタカナは除外"""
    count = 0
    for ch in text:
        cp = ord(ch)
        if (0x3040 <= cp <= 0x309F        # ひらがな
            or 0x30A0 <= cp <= 0x30FF      # カタカナ (全角)
            or 0x4E00 <= cp <= 0x9FFF):    # CJK 統合漢字
            count += 1
    return count


def has_mojibake(text: str) -> bool:
    """テキストに文字化けが含まれるか判定

    既知のシグネチャ (‚Í, ƒƒ 等) を検出し、修復後に日本語文字が増加する場合のみ True。
    """
    if not text:
        return False

    # 既知シグネチャチェック (高速パス)
    for sig in MOJIBAKE_SIGNATURES:
        if sig in text:
            return True

    # 連続した mojibake 文字が 3 文字以上あれば候補
    max_run = 0
    run = 0
    for ch in text:
        if _is_mojibake_char(ch):
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0

    if max_run < 3:
        return False

    # 修復して全角日本語文字が実際に増えるか検証 (false positive 排除)
    # 半角カタカナ (FF60-FF9F) への変換は binary dump の誤検出なので除外
    repaired = repair_mojibake(text)
    new_japanese = _count_fullwidth_japanese(repaired) - _count_fullwidth_japanese(text)
    return new_japanese >= 3


class MojibakeRepairTool:
    """Neo4j Chunk の文字化け修復 + 再エンベディング"""

    SCAN_BATCH_SIZE = 1000
    EMBED_BATCH_SIZE = 50
    UPDATE_BATCH_SIZE = 100
    INTER_BATCH_DELAY = 0.01  # 10ms

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        embedding_url: str,
        embedding_model: str = "bge-m3",
    ):
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.embedding_url = embedding_url.rstrip("/")
        self.embedding_model = embedding_model

    def close(self):
        self.driver.close()

    # ─── Phase 1: 検出 ───

    def scan_mojibake_chunks(self) -> List[Dict]:
        """全 Chunk をスキャンし文字化け候補を返す"""
        print("\n[Phase 1] 文字化け Chunk スキャン...")

        candidates = []
        skip = 0

        while True:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (c:Chunk)
                    WHERE c.content IS NOT NULL
                    RETURN c.id AS id, c.content AS content
                    ORDER BY c.id
                    SKIP $skip LIMIT $limit
                """, skip=skip, limit=self.SCAN_BATCH_SIZE)
                batch = [{"id": r["id"], "content": r["content"]} for r in result]

            if not batch:
                break

            for chunk in batch:
                if has_mojibake(chunk["content"]):
                    repaired = repair_mojibake(chunk["content"])
                    if repaired != chunk["content"]:
                        candidates.append({
                            "id": chunk["id"],
                            "original": chunk["content"],
                            "repaired": repaired,
                        })

            skip += self.SCAN_BATCH_SIZE
            total_scanned = skip
            print(f"  スキャン済: {total_scanned} chunks, 検出: {len(candidates)} 件", end="\r")

        print(f"\n  完了: {skip} chunks スキャン → {len(candidates)} 件の文字化け検出")
        return candidates

    # ─── Phase 2: 再エンベディング ───

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """BGE-M3 API で dense embedding を取得 (同期 httpx)"""
        all_embeddings = []

        for i in range(0, len(texts), self.EMBED_BATCH_SIZE):
            batch = texts[i:i + self.EMBED_BATCH_SIZE]
            resp = httpx.post(
                f"{self.embedding_url}/v1/embeddings",
                json={"input": batch, "model": self.embedding_model},
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = [item["embedding"] for item in data["data"]]
            all_embeddings.extend(embeddings)

            done = min(i + self.EMBED_BATCH_SIZE, len(texts))
            print(f"  エンベディング: {done}/{len(texts)}", end="\r")

        print(f"\n  完了: {len(all_embeddings)} 件のエンベディング取得")
        return all_embeddings

    # ─── Phase 3: Neo4j 更新 ───

    def update_chunks(self, updates: List[Dict]) -> int:
        """content + embedding を一括更新"""
        print(f"\n[Phase 3] Neo4j 更新 ({len(updates)} 件)...")
        total_updated = 0

        for i in range(0, len(updates), self.UPDATE_BATCH_SIZE):
            batch = updates[i:i + self.UPDATE_BATCH_SIZE]
            with self.driver.session() as session:
                result = session.run("""
                    UNWIND $batch AS item
                    MATCH (c:Chunk {id: item.id})
                    SET c.content = item.content, c.embedding = item.embedding
                    RETURN count(*) AS cnt
                """, batch=batch)
                cnt = result.single()["cnt"]
                total_updated += cnt

            done = min(i + self.UPDATE_BATCH_SIZE, len(updates))
            print(f"  更新: {done}/{len(updates)}", end="\r")

            if i + self.UPDATE_BATCH_SIZE < len(updates):
                time.sleep(self.INTER_BATCH_DELAY)

        print(f"\n  完了: {total_updated} Chunk 更新")
        return total_updated

    # ─── Verify ───

    def verify_entity(self, entity_name: str) -> Dict:
        """特定 Entity に接続された Chunk の content を表示"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
                WHERE toLower(e.name) = toLower($name)
                RETURN c.id AS id,
                       substring(c.content, 0, 200) AS content_preview,
                       c.embedding IS NOT NULL AS has_embedding
                LIMIT 10
            """, name=entity_name)
            chunks = [
                {
                    "id": r["id"],
                    "content_preview": r["content_preview"],
                    "has_embedding": r["has_embedding"],
                }
                for r in result
            ]

        # Entity ノード自体の情報
        with self.driver.session() as session:
            result = session.run("""
                MATCH (e:Entity)
                WHERE toLower(e.name) = toLower($name)
                RETURN e.name AS name, e.type AS type, e.confidence AS confidence
            """, name=entity_name)
            entity = result.single()

        return {
            "entity": dict(entity) if entity else None,
            "chunks": chunks,
            "chunk_count": len(chunks),
        }

    # ─── Main flows ───

    def dry_run(self) -> Dict:
        """検出のみ。修復プレビューを表示"""
        candidates = self.scan_mojibake_chunks()

        if not candidates:
            print("\n文字化け Chunk は検出されませんでした。")
            return {"detected": 0, "samples": []}

        print(f"\n{'='*60}")
        print(f"検出結果: {len(candidates)} 件の文字化け Chunk")
        print(f"{'='*60}")

        # サンプル表示 (最大 10 件)
        samples = []
        for c in candidates[:10]:
            orig_preview = c["original"][:120].replace("\n", " ")
            fixed_preview = c["repaired"][:120].replace("\n", " ")
            print(f"\n  Chunk ID: {c['id']}")
            print(f"  Before: {orig_preview}")
            print(f"  After:  {fixed_preview}")
            samples.append({
                "id": c["id"],
                "before": orig_preview,
                "after": fixed_preview,
            })

        if len(candidates) > 10:
            print(f"\n  ... +{len(candidates) - 10} more")

        return {"detected": len(candidates), "samples": samples}

    def execute(self) -> Dict:
        """修復 + 再エンベディング + Neo4j 更新"""
        # Phase 1: 検出
        candidates = self.scan_mojibake_chunks()

        if not candidates:
            print("\n文字化け Chunk は検出されませんでした。")
            return {"detected": 0, "repaired": 0, "embedded": 0, "updated": 0}

        print(f"\n検出: {len(candidates)} 件 → 修復 + 再エンベディング開始")

        # Phase 2: 再エンベディング
        print(f"\n[Phase 2] BGE-M3 再エンベディング ({len(candidates)} 件)...")
        repaired_texts = [c["repaired"] for c in candidates]
        embeddings = self.embed_texts(repaired_texts)

        # Phase 3: Neo4j 更新
        updates = []
        for c, emb in zip(candidates, embeddings):
            updates.append({
                "id": c["id"],
                "content": c["repaired"],
                "embedding": emb,
            })

        updated = self.update_chunks(updates)

        # レポート
        report = {
            "timestamp": datetime.now().isoformat(),
            "detected": len(candidates),
            "repaired": len(repaired_texts),
            "embedded": len(embeddings),
            "updated": updated,
            "samples": [
                {
                    "id": c["id"],
                    "before": c["original"][:200],
                    "after": c["repaired"][:200],
                }
                for c in candidates[:20]
            ],
        }

        # JSON レポート出力
        report_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "mojibake_repair_report.json",
        )
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nレポート保存: {report_path}")

        print(f"\n{'='*60}")
        print("修復結果サマリー")
        print(f"{'='*60}")
        print(f"  検出:           {report['detected']} 件")
        print(f"  修復:           {report['repaired']} 件")
        print(f"  エンベディング: {report['embedded']} 件")
        print(f"  Neo4j 更新:     {report['updated']} 件")

        return report


def main():
    parser = argparse.ArgumentParser(
        description="Neo4j Chunk 文字化け (Mojibake) 修復 + 再エンベディング"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="検出のみ、変更なし")
    mode.add_argument("--execute", action="store_true", help="修復 + 再エンベディング + Neo4j 更新")
    mode.add_argument("--verify", type=str, metavar="ENTITY", help="特定 Entity の Chunk を表示")

    parser.add_argument("--neo4j-uri", type=str, help="Neo4j URI (default: from .env)")
    parser.add_argument("--neo4j-password", type=str, help="Neo4j password (default: from .env)")
    parser.add_argument("--embedding-url", type=str, help="Embedding API base URL (default: from .env)")

    args = parser.parse_args()

    # Load environment
    load_dotenv()

    neo4j_uri = args.neo4j_uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = args.neo4j_password or os.getenv("NEO4J_PASSWORD", "")
    embedding_url = args.embedding_url or os.getenv("EMBEDDING_API_URL", "http://192.168.8.11:12801/v1").rstrip("/v1").rstrip("/")
    embedding_model = os.getenv("EMBEDDING_MODEL", "bge-m3")

    if not neo4j_password:
        print("Error: NEO4J_PASSWORD not set. Use --neo4j-password or .env")
        sys.exit(1)

    tool = MojibakeRepairTool(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        embedding_url=embedding_url,
        embedding_model=embedding_model,
    )

    try:
        if args.dry_run:
            tool.dry_run()
        elif args.execute:
            tool.execute()
        elif args.verify:
            info = tool.verify_entity(args.verify)
            if not info["entity"]:
                print(f"\nEntity '{args.verify}' が見つかりません。")
            else:
                e = info["entity"]
                print(f"\nEntity: {e['name']} (type={e['type']}, confidence={e['confidence']})")
                print(f"接続 Chunk 数: {info['chunk_count']}")
                for c in info["chunks"]:
                    has_emb = "✓" if c["has_embedding"] else "✗"
                    print(f"\n  [{has_emb}] {c['id']}")
                    print(f"      {c['content_preview']}")
    finally:
        tool.close()


if __name__ == "__main__":
    main()
