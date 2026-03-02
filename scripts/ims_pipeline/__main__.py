"""
IMS Issue → Neo4j RAG Pipeline CLI

Usage:
    python -m scripts.ims_pipeline full --csv SearchIssue_template.csv --credentials scripts/ims_login.json
    python -m scripts.ims_pipeline parse-csv --csv SearchIssue_template.csv
    python -m scripts.ims_pipeline crawl --credentials scripts/ims_login.json [--concurrency 5] [--force]
    python -m scripts.ims_pipeline embed [--batch-size 10] [--force]
    python -m scripts.ims_pipeline stats
    python -m scripts.ims_pipeline search "에러 -5212"
"""

import argparse
import json
import logging
import sys

from . import csv_parser, issue_crawler, neo4j_embedder
from .config import DEFAULT_CREDENTIALS, DEFAULT_CSV, OUTPUT_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ims_pipeline")


def cmd_parse_csv(args: argparse.Namespace) -> None:
    """Phase 1: CSV 파싱 → index.json"""
    path = csv_parser.run(csv_path=args.csv, output_dir=args.output_dir)
    print(f"\nindex.json saved: {path}")

    # 간단 통계
    data = json.loads(path.read_text(encoding="utf-8"))
    products: dict[str, int] = {}
    for item in data:
        p = item.get("product", "Unknown")
        products[p] = products.get(p, 0) + 1

    print(f"Total issues: {len(data)}")
    print("Products:")
    for product, count in sorted(products.items(), key=lambda x: -x[1]):
        print(f"  {product}: {count}")


def cmd_crawl(args: argparse.Namespace) -> None:
    """Phase 2: IMS 이슈 상세 크롤"""
    stats = issue_crawler.run(
        credentials=args.credentials,
        concurrency=args.concurrency,
        force=args.force,
        limit=args.limit,
    )
    print(f"\nCrawl results: {json.dumps(stats, indent=2)}")


def cmd_embed(args: argparse.Namespace) -> None:
    """Phase 3: 청킹 + 임베딩 + Neo4j 저장"""
    dry_run = getattr(args, "dry_run", False)
    if dry_run:
        print("[DRY-RUN MODE] Using zero vectors - no BGE-M3 calls")
    stats = neo4j_embedder.embed_and_store(
        batch_size=args.batch_size,
        force=args.force,
        dry_run=dry_run,
        limit=getattr(args, "limit", None),
    )
    print(f"\nEmbed results: {json.dumps(stats, indent=2)}")


def cmd_full(args: argparse.Namespace) -> None:
    """전체 파이프라인 실행"""
    print("=" * 60)
    print("Phase 1: CSV → index.json")
    print("=" * 60)
    csv_parser.run(csv_path=args.csv, output_dir=args.output_dir)

    print("\n" + "=" * 60)
    print("Phase 2: Crawl IMS Issues")
    print("=" * 60)
    issue_crawler.run(
        credentials=args.credentials,
        concurrency=args.concurrency,
        force=args.force,
        limit=args.limit,
    )

    print("\n" + "=" * 60)
    print("Phase 3: Embed + Neo4j Store")
    print("=" * 60)
    stats = neo4j_embedder.embed_and_store(
        batch_size=args.batch_size,
        force=args.force,
    )
    print(f"\nPipeline complete: {json.dumps(stats, indent=2)}")


def cmd_stats(args: argparse.Namespace) -> None:
    """Neo4j 내 IMS 이슈 통계 출력"""
    # 로컬 파일 통계
    index_path = OUTPUT_DIR / "index.json"
    if index_path.exists():
        data = json.loads(index_path.read_text(encoding="utf-8"))
        print(f"Local index: {len(data)} issues")
        txt_count = len(list(OUTPUT_DIR.glob("*.txt")))
        print(f"Crawled .txt files: {txt_count}")
    else:
        print("Local index: not found")

    # Neo4j 통계
    try:
        stats = neo4j_embedder.get_stats()
        print(f"\nNeo4j:")
        print(f"  Documents (ims_issue): {stats['documents']}")
        print(f"  Chunks: {stats['chunks']}")
        print(f"  Entities: {stats['entities']}")
        if stats['products']:
            print("  Products:")
            for product, count in stats['products'].items():
                print(f"    {product}: {count}")
    except Exception as e:
        print(f"\nNeo4j connection failed: {e}")


def cmd_search(args: argparse.Namespace) -> None:
    """벡터 검색 테스트"""
    results = neo4j_embedder.test_search(args.query, top_k=args.top_k)
    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results, 1):
        print(f"\n--- Result {i} (score: {r['score']}) ---")
        print(f"IMS ID: {r['ims_id']} | Product: {r['product']}")
        print(f"Title: {r['title']}")
        print(f"Type: {r['chunk_type']}")
        print(f"Content: {r['content']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ims_pipeline",
        description="IMS Issue → Neo4j RAG Pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # parse-csv
    p_csv = sub.add_parser("parse-csv", help="Phase 1: CSV → index.json")
    p_csv.add_argument("--csv", default=str(DEFAULT_CSV), help="CSV file path")
    p_csv.add_argument("--output-dir", default=None, help="Output directory")

    # crawl
    p_crawl = sub.add_parser("crawl", help="Phase 2: Crawl IMS issue pages")
    p_crawl.add_argument("--credentials", default=str(DEFAULT_CREDENTIALS), help="Credentials JSON path")
    p_crawl.add_argument("--concurrency", type=int, default=5, help="Max concurrent requests")
    p_crawl.add_argument("--force", action="store_true", help="Re-crawl existing files")
    p_crawl.add_argument("--limit", type=int, default=None, help="Limit number of issues to crawl")

    # embed
    p_embed = sub.add_parser("embed", help="Phase 3: Chunk + Embed + Neo4j store")
    p_embed.add_argument("--batch-size", type=int, default=10, help="Batch size for embedding")
    p_embed.add_argument("--force", action="store_true", help="Re-embed existing documents")
    p_embed.add_argument("--dry-run", action="store_true", help="Skip BGE-M3, use zero vectors (for pipeline testing)")
    p_embed.add_argument("--limit", type=int, default=None, help="Limit number of files to process")

    # full
    p_full = sub.add_parser("full", help="Run full pipeline (parse → crawl → embed)")
    p_full.add_argument("--csv", default=str(DEFAULT_CSV), help="CSV file path")
    p_full.add_argument("--output-dir", default=None, help="Output directory")
    p_full.add_argument("--credentials", default=str(DEFAULT_CREDENTIALS), help="Credentials JSON path")
    p_full.add_argument("--concurrency", type=int, default=5, help="Max concurrent requests")
    p_full.add_argument("--batch-size", type=int, default=10, help="Embedding batch size")
    p_full.add_argument("--force", action="store_true", help="Force re-process")
    p_full.add_argument("--limit", type=int, default=None, help="Limit issues to crawl")

    # stats
    sub.add_parser("stats", help="Show IMS issue statistics")

    # search
    p_search = sub.add_parser("search", help="Test vector search on IMS issues")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--top-k", type=int, default=5, help="Number of results")

    args = parser.parse_args()

    try:
        {
            "parse-csv": cmd_parse_csv,
            "crawl": cmd_crawl,
            "embed": cmd_embed,
            "full": cmd_full,
            "stats": cmd_stats,
            "search": cmd_search,
        }[args.command](args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
