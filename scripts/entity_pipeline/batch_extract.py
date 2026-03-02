"""
Chunk-Entity Pipeline: 孤立ChunkへのEntity自動抽出・接続

Usage:
    python -m scripts.entity_pipeline.batch_extract [options]

Options:
    --dry-run           抽出のみ実行 (Neo4j書き込みなし)
    --batch-size N      Chunkフェッチバッチサイズ (default: 500)
    --limit N           処理Chunk数上限 (default: 0 = 全件)
    --report FILE       レポートJSON出力先 (default: stdout)
    --verbose           詳細ログ出力
"""
import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

# 出力バッファリング無効化
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import dotenv
    dotenv.load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from scripts.entity_pipeline.summary_extractor import SummaryExtractor
from scripts.entity_pipeline.pattern_extractor import PatternExtractor
from scripts.entity_pipeline.neo4j_writer import Neo4jBatchWriter


def parse_args():
    parser = argparse.ArgumentParser(
        description="Chunk-Entity Pipeline: 孤立ChunkへのEntity自動抽出・接続"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="抽出のみ実行 (Neo4j書き込みなし)")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="Chunkフェッチバッチサイズ (default: 500)")
    parser.add_argument("--limit", type=int, default=0,
                        help="処理Chunk数上限 (default: 0 = 全件)")
    parser.add_argument("--report", type=str, default=None,
                        help="レポートJSON出力先ファイル")
    parser.add_argument("--verbose", action="store_true",
                        help="詳細ログ出力")
    parser.add_argument("--verify", type=str, default=None,
                        help="特定EntityのNeo4j接続状態を検証")
    return parser.parse_args()


def main():
    args = parse_args()
    start_time = time.time()

    # --- Neo4j接続設定 ---
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://192.168.8.11:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")
    summaries_dir = os.getenv("SUMMARIES_DIR", str(PROJECT_ROOT / "uploads" / "summaries"))

    writer = Neo4jBatchWriter(neo4j_uri, neo4j_user, neo4j_password)

    # --- 検証モード ---
    if args.verify:
        result = writer.verify_entity(args.verify)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        writer.close()
        return

    # === Step 1: Summary辞書構築 ===
    print("=" * 60)
    print("Chunk-Entity Pipeline v1.0")
    print("=" * 60)
    print(f"\n[Step 1] Summary辞書構築中...")

    summary_ext = SummaryExtractor(summaries_dir)
    entity_dict = summary_ext.load_all()
    stats = summary_ext.get_stats()
    print(f"  辞書エントリ: {stats['total']}")
    for t, c in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    # === Step 2: パターン抽出器初期化 ===
    print(f"\n[Step 2] パターン抽出器初期化...")
    pattern_ext = PatternExtractor(entity_dict)
    print("  OK")

    # === Step 3: 処理前統計 ===
    print(f"\n[Step 3] 処理前統計取得...")
    before_stats = writer.get_stats()
    print(f"  全Chunk: {before_stats.total_chunks}")
    print(f"  接続済み: {before_stats.connected_chunks} ({before_stats.connected_pct:.1f}%)")
    print(f"  孤立: {before_stats.orphan_chunks} ({before_stats.orphan_pct:.1f}%)")
    print(f"  全Entity: {before_stats.total_entities}")
    print(f"  全MENTIONS: {before_stats.total_mentions}")

    if args.dry_run:
        print("\n  [DRY-RUN] Neo4j書き込みはスキップします")

    # === Step 4: 孤立Chunkバッチ処理 ===
    total_target = args.limit if args.limit > 0 else before_stats.orphan_chunks
    print(f"\n[Step 4] 孤立Chunkバッチ処理 (対象: {total_target}件)...")

    total_processed = 0
    total_entities_extracted = 0
    total_entities_written = 0
    total_mentions_written = 0
    total_skipped = 0
    total_no_match = 0   # Entity抽出ゼロのChunk数
    last_progress = -1

    skip = 0
    while True:
        # 上限チェック
        remaining = total_target - total_processed if args.limit > 0 else args.batch_size
        fetch_size = min(args.batch_size, remaining) if args.limit > 0 else args.batch_size
        if fetch_size <= 0:
            break

        # 孤立Chunkフェッチ
        chunks = writer.fetch_orphan_chunks(skip, fetch_size)
        if not chunks:
            break

        # バッチ内全ChunkからEntity抽出
        batch_entities = []
        batch_no_match = 0
        for chunk in chunks:
            content = chunk.get("content", "")
            if not content or len(content) < 30:
                total_skipped += 1
                batch_no_match += 1
                continue
            try:
                extracted = pattern_ext.extract(chunk["id"], content)
                if extracted:
                    batch_entities.extend(extracted)
                else:
                    batch_no_match += 1
            except Exception as e:
                total_skipped += 1
                batch_no_match += 1
                if args.verbose:
                    print(f"    SKIP {chunk['id']}: {e}")

        total_entities_extracted += len(batch_entities)
        total_no_match += batch_no_match

        # Neo4j書き込み
        if batch_entities and not args.dry_run:
            try:
                result = writer.write_batch(batch_entities)
                total_entities_written += result.entities_processed
                total_mentions_written += result.mentions_processed
            except Exception as e:
                print(f"    WRITE ERROR: {e}")

        total_processed += len(chunks)

        # skipポインタ管理:
        # - dry-run: 常にskipを進める
        # - 書き込み成功: 接続済みChunkはorphanから外れるためskip=0
        # - Entity抽出ゼロ: Chunkはorphanのまま残るためskipを進める
        if args.dry_run:
            skip += len(chunks)
        elif batch_no_match == len(chunks):
            # 全Chunkでentity抽出ゼロ → orphanのまま残るためskip前進
            skip += len(chunks)
        elif batch_no_match > 0 and batch_entities:
            # 一部成功、一部ゼロ → 成功分はorphanから外れるが
            # ゼロ分はorphanのまま → skip前進 (ゼロ分だけ)
            skip += batch_no_match
        else:
            # 全Chunk成功 → orphanから外れるためskip=0
            skip = 0

        # 終了判定: 全バッチでentity抽出ゼロなら終了
        if batch_no_match == len(chunks) and not batch_entities:
            print(f"  全ChunkでEntity抽出ゼロ (skip={skip}) - 終了")
            break

        # 進捗表示 (5%ごと)
        if total_target > 0:
            progress = int(total_processed / total_target * 100)
            if progress >= last_progress + 5:
                elapsed = time.time() - start_time
                rate = total_processed / elapsed if elapsed > 0 else 0
                remaining_est = max(0, total_target - total_processed)
                eta = remaining_est / rate if rate > 0 else 0
                print(f"  {progress:3d}% | {total_processed}/{total_target} | "
                      f"extracted={total_entities_extracted} | "
                      f"no_match={total_no_match} | ETA={eta:.0f}s")
                last_progress = progress

        # Limit check
        if args.limit > 0 and total_processed >= args.limit:
            break

    elapsed = time.time() - start_time
    print(f"\n  処理完了: {elapsed:.1f}秒")

    # === Step 5: 処理後統計 ===
    print(f"\n[Step 5] 処理後統計取得...")
    after_stats = writer.get_stats()
    print(f"  全Chunk: {after_stats.total_chunks}")
    print(f"  接続済み: {after_stats.connected_chunks} ({after_stats.connected_pct:.1f}%)")
    print(f"  孤立: {after_stats.orphan_chunks} ({after_stats.orphan_pct:.1f}%)")
    print(f"  全Entity: {after_stats.total_entities}")
    print(f"  全MENTIONS: {after_stats.total_mentions}")

    # Entity種別分布 (pipeline_v1)
    if not args.dry_run:
        type_dist = writer.get_entity_type_distribution(source="pipeline_v1")
        if type_dist:
            print(f"\n  新規Entity種別分布 (pipeline_v1):")
            for t, c in sorted(type_dist.items(), key=lambda x: -x[1]):
                print(f"    {t}: {c}")

    # === Step 6: レポート ===
    report = {
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "dry_run": args.dry_run,
        "before": {
            "total_chunks": before_stats.total_chunks,
            "connected_chunks": before_stats.connected_chunks,
            "orphan_chunks": before_stats.orphan_chunks,
            "orphan_pct": round(before_stats.orphan_pct, 1),
            "total_entities": before_stats.total_entities,
            "total_mentions": before_stats.total_mentions,
        },
        "after": {
            "total_chunks": after_stats.total_chunks,
            "connected_chunks": after_stats.connected_chunks,
            "orphan_chunks": after_stats.orphan_chunks,
            "orphan_pct": round(after_stats.orphan_pct, 1),
            "total_entities": after_stats.total_entities,
            "total_mentions": after_stats.total_mentions,
        },
        "processing": {
            "chunks_processed": total_processed,
            "chunks_skipped": total_skipped,
            "chunks_no_match": total_no_match,
            "entities_extracted": total_entities_extracted,
            "entities_written": total_entities_written,
            "mentions_written": total_mentions_written,
            "summary_dict_size": stats["total"],
        },
        "improvement": {
            "orphan_before": before_stats.orphan_chunks,
            "orphan_after": after_stats.orphan_chunks,
            "orphan_reduction": before_stats.orphan_chunks - after_stats.orphan_chunks,
            "new_entities": after_stats.total_entities - before_stats.total_entities,
            "new_mentions": after_stats.total_mentions - before_stats.total_mentions,
        },
    }

    print("\n" + "=" * 60)
    print("RESULT SUMMARY")
    print("=" * 60)
    print(f"  孤立Chunk: {before_stats.orphan_chunks} → {after_stats.orphan_chunks} "
          f"({before_stats.orphan_pct:.1f}% → {after_stats.orphan_pct:.1f}%)")
    print(f"  新規Entity: +{report['improvement']['new_entities']}")
    print(f"  新規MENTIONS: +{report['improvement']['new_mentions']}")
    print(f"  処理時間: {elapsed:.1f}秒")

    if args.report:
        report_path = Path(args.report)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n  レポート出力: {report_path}")
    else:
        print(f"\n{json.dumps(report, indent=2, ensure_ascii=False)}")

    writer.close()


if __name__ == "__main__":
    main()
