"""
Web docs crawl CLI.

docs.tmaxsoft.com 전체 크롤링 및 인덱스 관리.

Usage:
    python -m scripts.crawl_web_docs                 # 풀 크롤 (ja)
    python -m scripts.crawl_web_docs --lang ja ko en # 다국어
    python -m scripts.crawl_web_docs --stats          # 인덱스 통계
    python -m scripts.crawl_web_docs --search "tjesmgr BOOT"  # 검색 테스트
"""
import asyncio
import argparse
import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def do_crawl(args):
    """전체 크롤링 실행"""
    from app.api.services.web_doc_crawler_service import get_web_doc_crawler_service

    crawler = get_web_doc_crawler_service()
    print(f"Starting crawl: languages={args.lang}, concurrency={args.concurrency}")
    print(f"Target: https://docs.tmaxsoft.com")
    print()

    index = await crawler.crawl_all(
        languages=args.lang,
        concurrency=args.concurrency,
    )
    await crawler.close()

    print(f"\nCrawl complete!")
    print(f"  Total pages: {index.total_pages}")
    print(f"  Components:  {len(index.components)}")
    print(f"  Crawled at:  {index.crawled_at}")
    _print_component_stats(index)


def do_stats(args):
    """인덱스 통계 표시"""
    from app.api.services.web_doc_crawler_service import get_web_doc_crawler_service

    crawler = get_web_doc_crawler_service()
    index = crawler.load_index()
    if not index:
        print("No index found. Run: python -m scripts.crawl_web_docs")
        return

    print(f"Web Doc Index Statistics")
    print(f"  Total pages: {index.total_pages}")
    print(f"  Components:  {len(index.components)}")
    print(f"  Crawled at:  {index.crawled_at}")
    _print_component_stats(index)

    # 언어별 통계
    lang_counts = {}
    for p in index.pages:
        lang_counts[p.language] = lang_counts.get(p.language, 0) + 1
    print(f"\nBy language:")
    for lang, count in sorted(lang_counts.items()):
        print(f"  {lang}: {count} pages")

    # product_id별 통계
    pid_counts = {}
    for p in index.pages:
        pid = p.product_id or "(unmapped)"
        pid_counts[pid] = pid_counts.get(pid, 0) + 1
    print(f"\nBy product_id:")
    for pid, count in sorted(pid_counts.items()):
        print(f"  {pid}: {count} pages")


def do_search(args):
    """검색 테스트"""
    from app.api.services.web_doc_crawler_service import get_web_doc_crawler_service
    from app.api.services.web_doc_search_service import get_web_doc_search_service, WEB_DOC_THRESHOLD

    # 인덱스 로드
    crawler = get_web_doc_crawler_service()
    crawler.load_index()

    search = get_web_doc_search_service()
    query = args.search
    lang = args.lang[0] if args.lang else "ja"

    print(f"Query: {query}")
    print(f"Language: {lang}")
    print(f"Threshold: {WEB_DOC_THRESHOLD}")
    print()

    results = search.search(query=query, language=lang, top_k=5)

    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results, 1):
        marker = " *** WEB DOC MATCH ***" if r.normalized_score >= WEB_DOC_THRESHOLD else ""
        print(f"#{i} [score={r.normalized_score:.4f}]{marker}")
        print(f"   Title: {r.title}")
        print(f"   URL: {r.url}")
        print(f"   Component: {r.component} | Product: {r.product_id}")
        if r.headings:
            print(f"   Headings: {', '.join(r.headings[:3])}")
        print()


def _print_component_stats(index):
    """컴포넌트별 페이지 수 표시"""
    comp_counts = {}
    for p in index.pages:
        comp_counts[p.component] = comp_counts.get(p.component, 0) + 1
    print(f"\nBy component:")
    for comp, count in sorted(comp_counts.items()):
        print(f"  {comp}: {count} pages")


async def main():
    parser = argparse.ArgumentParser(description="Crawl docs.tmaxsoft.com for Web Doc RAG")
    parser.add_argument("--lang", nargs="+", default=["ja"], help="Languages to crawl (default: ja)")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent HTTP requests")
    parser.add_argument("--stats", action="store_true", help="Show index statistics")
    parser.add_argument("--search", type=str, help="Test search query")
    args = parser.parse_args()

    if args.stats:
        do_stats(args)
    elif args.search:
        do_search(args)
    else:
        await do_crawl(args)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
