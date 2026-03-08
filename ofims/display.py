"""Terminal display formatting for IMS CLI."""
import re
import sys


def _strip_customer_info(subject: str) -> str:
    """Subject에서 [고객사/프로젝트명] 접두사 제거"""
    return re.sub(r'^\[.*?\]\s*', '', subject)


def print_search_results(data: dict) -> None:
    """검색 결과를 테이블 형태로 출력"""
    results = data.get("results", [])
    query = data.get("query", "")
    total = data.get("total", 0)
    elapsed = data.get("search_time_ms", 0)

    print(f"\n  Search: \"{query}\"")
    print(f"  Results: {total} issues ({elapsed:.0f}ms)\n")

    if not results:
        print("  No matching issues found.\n")
        return

    # Header
    print(f"  {'IMS ID':<10} {'Score':>6}  {'Product':<25} {'Status':<12} {'Subject'}")
    print(f"  {'─'*10} {'─'*6}  {'─'*25} {'─'*12} {'─'*40}")

    for r in results:
        subject = _strip_customer_info(r.get("subject", ""))[:50]
        print(
            f"  {r['ims_id']:<10} {r['score']:>6.4f}  "
            f"{r.get('product', ''):<25} {r.get('status', ''):<12} {subject}"
        )

    print()


def print_issue_detail(data: dict) -> None:
    """이슈 상세를 포맷팅하여 출력"""
    meta = data.get("metadata", {})
    print(f"\n{'='*70}")
    print(f"  IMS Issue #{meta.get('ims_id', 'N/A')}")
    print(f"{'='*70}")
    print(f"  Product:  {meta.get('product', '')}")
    print(f"  Version:  {meta.get('version', '')}")
    print(f"  Subject:  {_strip_customer_info(meta.get('subject', ''))}")
    print(f"  Status:   {meta.get('status', '')}  |  Date: {meta.get('date', '')}")
    print(f"{'─'*70}")

    desc = data.get("description", "")
    if desc:
        print(f"\n  [Description]\n")
        for line in desc.split("\n")[:30]:
            print(f"  {line}")

    action_log = data.get("action_log", [])
    if action_log:
        print(f"\n  [Action Log] ({len(action_log)} entries)")
        for entry in action_log[:5]:
            print(f"\n  --- #{entry['index']} ---")
            content = entry["content"][:300]
            for line in content.split("\n"):
                print(f"  {line}")
        if len(action_log) > 5:
            print(f"\n  ... and {len(action_log) - 5} more entries")

    refs = data.get("referenced_ims_ids", [])
    if refs:
        print(f"\n  [Referenced Issues]")
        print(f"  {', '.join('IMS#' + r for r in refs)}")

    urls = data.get("referenced_urls", [])
    if urls:
        print(f"\n  [URLs]")
        for url in urls[:5]:
            print(f"  {url}")

    print()


def print_related_issues(data: dict) -> None:
    """관련 이슈 목록 출력"""
    ims_id = data.get("ims_id", "")
    related = data.get("related_issues", [])

    print(f"\n  Related Issues for IMS#{ims_id}  ({data.get('total', 0)} found)\n")

    if not related:
        print("  No related issues found.\n")
        return

    for r in related:
        print(f"  IMS#{r['ims_id']}  [{r['relation_type']}]")
        if r.get("subject"):
            print(f"    Subject: {_strip_customer_info(r['subject'])[:60]}")
        if r.get("product"):
            print(f"    Product: {r['product']}  Status: {r.get('status', '')}")
        if r.get("context"):
            print(f"    Context: {r['context'][:80]}")
        print()


def print_summary(data: dict) -> None:
    """이슈 요약 출력"""
    print(f"\n{'='*70}")
    print(f"  Summary: IMS#{data.get('ims_id', '')}")
    print(f"  Subject: {_strip_customer_info(data.get('subject', ''))}")
    print(f"{'='*70}\n")
    print(f"  {data.get('summary', '')}\n")

    key_points = data.get("key_points", [])
    if key_points:
        print("  Key Points:")
        for kp in key_points:
            print(f"    - {kp}")

    resolution = data.get("resolution")
    if resolution:
        print(f"\n  Resolution:\n    {resolution}")

    refs = data.get("related_ims_ids", [])
    if refs:
        print(f"\n  Related: {', '.join('IMS#' + r for r in refs)}")

    print()


def print_chat_stream(events_iter) -> None:
    """SSE 이벤트 스트림을 실시간 출력"""
    for event in events_iter:
        evt = event["event"]
        data = event["data"]

        if evt == "search_start":
            print(f"\n  Searching: \"{data.get('query', '')}\" (limit={data.get('limit', 5)})")

        elif evt == "search_results":
            total = data.get("total", 0)
            elapsed = data.get("search_time_ms", 0)
            print(f"  Found {total} issues ({elapsed:.0f}ms)")
            for r in data.get("results", [])[:5]:
                print(f"    IMS#{r['ims_id']} ({r['score']:.4f}) {_strip_customer_info(r.get('subject', ''))[:50]}")

        elif evt == "context_loaded":
            print(f"  Context: {data.get('issues_loaded', 0)} issues + {data.get('related_loaded', 0)} related\n")
            print("  " + "─" * 60)
            print()

        elif evt == "token":
            sys.stdout.write(data.get("content", ""))
            sys.stdout.flush()

        elif evt == "sources":
            print("\n\n  " + "─" * 60)
            print("  Sources:")
            for s in data.get("sources", []):
                print(f"    IMS#{s['ims_id']} ({s.get('score', 0):.4f}) {_strip_customer_info(s.get('subject', ''))[:50]}")

        elif evt == "done":
            conv_id = data.get("conversation_id", "")
            print(f"\n  [conversation: {conv_id[:8]}...]\n")

        elif evt == "error":
            print(f"\n  ERROR: {data.get('message', 'Unknown error')}\n")


def print_knowledge(data: dict) -> None:
    """생성된 지식 문서 출력"""
    print(f"\n{'='*70}")
    print(f"  Knowledge Article: {data.get('title', '')}")
    print(f"  Sources: {', '.join('IMS#' + s for s in data.get('source_issues', []))}")
    print(f"{'='*70}\n")
    print(data.get("content", ""))
    print()
