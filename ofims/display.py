"""Terminal display formatting for IMS CLI."""
import itertools
import re
import sys
import threading
import time

# 고객사명 필터 목록
_CUSTOMER_NAMES = [
    "이나게야", "노무라", "노무라증권", "야마기와", "라이온", "LION",
    "이토요카도", "이토요카드", "LG화재", "삼성생명", "해경",
    "손보", "손보재팬", "Sonpo", "Sompo", "동경해상",
    "토야마", "Toyama", "Daiken", "다이켄",
    "Fukuyama", "후쿠야마", "PGF", "라이프카드", "Lifrecard",
    "스미노애", "SUMINOE", "suminoe", "스즈키", "suzuki",
    "일본예금보험기구", "GE Capital", "혼다", "HONDA", "Honda",
    "Itoyocado", "우오이치", "uoichi", "미스미", "MISUMI",
]
_CUSTOMER_PATTERN = re.compile(
    '|'.join(re.escape(name) for name in _CUSTOMER_NAMES),
    re.IGNORECASE,
)


class _ThinkingSpinner:
    """thinking 중 애니메이션 스피너"""
    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self):
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        # 스피너 라인 지우기
        sys.stdout.write("\r" + " " * 30 + "\r")
        sys.stdout.flush()

    def _spin(self):
        frames = itertools.cycle(self._FRAMES)
        elapsed = 0.0
        while self._running:
            frame = next(frames)
            sys.stdout.write(f"\r  {frame} thinking... ({elapsed:.0f}s)")
            sys.stdout.flush()
            time.sleep(0.1)
            elapsed += 0.1


def _strip_customer_info(text: str) -> str:
    """[고객사/프로젝트명] 접두사 제거 + 고객사명 마스킹"""
    text = re.sub(r'^\[.*?\]\s*', '', text)
    return _CUSTOMER_PATTERN.sub('***', text)


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
    """SSE 이벤트 스트림을 실시간 출력 (<think> 태그는 spinner로 대체)"""
    in_think = False
    spinner = _ThinkingSpinner()
    token_buf = ""  # <think> 태그 파편 감지용 버퍼

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
            content = data.get("content", "")
            token_buf += content

            # <think> 열림 태그 감지
            if not in_think and "<think>" in token_buf:
                # <think> 앞 텍스트 출력
                before = token_buf[:token_buf.index("<think>")]
                if before:
                    sys.stdout.write(_CUSTOMER_PATTERN.sub('***', before))
                    sys.stdout.flush()
                in_think = True
                token_buf = token_buf[token_buf.index("<think>") + 7:]
                spinner.start()
                continue

            # </think> 닫힘 태그 감지
            if in_think and "</think>" in token_buf:
                spinner.stop()
                in_think = False
                token_buf = token_buf[token_buf.index("</think>") + 8:]
                # </think> 뒤 남은 텍스트 출력
                if token_buf:
                    sys.stdout.write(_CUSTOMER_PATTERN.sub('***', token_buf))
                    sys.stdout.flush()
                token_buf = ""
                continue

            # thinking 중이면 버퍼만 누적 (출력 안 함)
            if in_think:
                # 버퍼가 너무 커지면 앞부분 버림 (</think> 태그만 감지하면 됨)
                if len(token_buf) > 200:
                    token_buf = token_buf[-50:]
                continue

            # 일반 토큰: 태그 파편 가능성 체크 후 출력
            # "<" 로 끝나면 다음 토큰까지 대기
            if token_buf.endswith("<"):
                continue
            if token_buf.endswith("<t") or token_buf.endswith("<th") or \
               token_buf.endswith("<thi") or token_buf.endswith("<thin") or \
               token_buf.endswith("<think"):
                continue

            sys.stdout.write(_CUSTOMER_PATTERN.sub('***', token_buf))
            sys.stdout.flush()
            token_buf = ""

        elif evt == "sources":
            # thinking이 끝나지 않았으면 정리
            if in_think:
                spinner.stop()
                in_think = False
            print("\n\n  " + "─" * 60)
            print("  Sources:")
            for s in data.get("sources", []):
                print(f"    IMS#{s['ims_id']} ({s.get('score', 0):.4f}) {_strip_customer_info(s.get('subject', ''))[:50]}")

        elif evt == "done":
            if in_think:
                spinner.stop()
            conv_id = data.get("conversation_id", "")
            print(f"\n  [conversation: {conv_id[:8]}...]\n")

        elif evt == "error":
            if in_think:
                spinner.stop()
            print(f"\n  ERROR: {data.get('message', 'Unknown error')}\n")


def print_knowledge(data: dict) -> None:
    """생성된 지식 문서 출력"""
    print(f"\n{'='*70}")
    print(f"  Knowledge Article: {data.get('title', '')}")
    print(f"  Sources: {', '.join('IMS#' + s for s in data.get('source_issues', []))}")
    print(f"{'='*70}\n")
    print(data.get("content", ""))
    print()
