"""
PDF Chunk Visualizer

StructuredKnowledgeStore의 청킹 로직을 그대로 사용하여
PDF를 청킹하고 결과를 HTML로 시각화하는 CLI 도구.

Usage:
    python -m scripts.pdf_chunk_visualizer <pdf_path> [--output <html_path>] [--search <query>]
    python -m scripts.pdf_chunk_visualizer uploads/manuals/mvs_openframe_7.1/*.pdf
    python -m scripts.pdf_chunk_visualizer sample.pdf --search "BOOT 명령어"
"""

import argparse
import glob
import html
import json
import os
import sys
import time
from typing import Dict, List, Optional

# 프로젝트 루트를 path에 추가
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.api.services.structured_knowledge_store import StructuredKnowledgeStore


def chunk_pdf(pdf_path: str) -> tuple:
    """PDF를 StructuredKnowledgeStore 로직으로 청킹하여 섹션 리스트 반환.

    Returns:
        (sections, elapsed_ms, toc_info)
    """
    store = StructuredKnowledgeStore(product_id="visualizer", summary_paths={})
    start = time.perf_counter()
    sections = store._parse_pdf(pdf_path, "pdf_manuals")
    elapsed_ms = (time.perf_counter() - start) * 1000

    # TOC 정보 추출
    toc_info = []
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        toc = doc.get_toc()
        toc_info = [(level, title, page) for level, title, page in toc]
        doc.close()
    except Exception:
        pass

    return sections, elapsed_ms, toc_info


def search_chunks(sections: List[Dict], query: str) -> List[Dict]:
    """청킹된 섹션에서 검색 수행 (StructuredKnowledgeStore.search 로직 재현)."""
    store = StructuredKnowledgeStore(product_id="visualizer", summary_paths={})
    # 수동으로 캐시에 섹션 적재
    store._cache["pdf_manuals"] = sections
    store._loaded = True

    import asyncio
    loop = asyncio.new_event_loop()
    results = loop.run_until_complete(store.search(query, top_k=10))
    loop.close()

    return [
        {
            "title": r.title,
            "content": r.content,
            "source_page": r.source_page,
            "relevance_score": r.relevance_score,
        }
        for r in results
    ]


def _size_class(length: int) -> str:
    """섹션 크기에 따른 CSS 클래스."""
    if length < 500:
        return "size-small"
    elif length < 2000:
        return "size-medium"
    elif length < 5000:
        return "size-large"
    return "size-xlarge"


def _size_color(length: int) -> str:
    """섹션 크기에 따른 바 색상."""
    if length < 500:
        return "#4ade80"  # green
    elif length < 2000:
        return "#60a5fa"  # blue
    elif length < 5000:
        return "#fbbf24"  # amber
    return "#f87171"  # red


def _escape(text: str) -> str:
    return html.escape(text)


def generate_html(
    pdf_path: str,
    sections: List[Dict],
    elapsed_ms: float,
    toc_info: list,
    search_query: Optional[str] = None,
    search_results: Optional[List[Dict]] = None,
) -> str:
    """청킹 결과를 인터랙티브 HTML로 생성."""
    filename = os.path.basename(pdf_path)
    total_sections = len(sections)
    total_chars = sum(len(s.get("content", "")) for s in sections)
    avg_chars = total_chars // total_sections if total_sections > 0 else 0
    max_chars = max((len(s.get("content", "")) for s in sections), default=0)
    min_chars = min((len(s.get("content", "")) for s in sections), default=0)

    # 크기 분포
    size_dist = {"small (<500)": 0, "medium (500-2K)": 0, "large (2K-5K)": 0, "xlarge (5K+)": 0}
    for s in sections:
        l = len(s.get("content", ""))
        if l < 500:
            size_dist["small (<500)"] += 1
        elif l < 2000:
            size_dist["medium (500-2K)"] += 1
        elif l < 5000:
            size_dist["large (2K-5K)"] += 1
        else:
            size_dist["xlarge (5K+)"] += 1

    # 코드블록 포함 섹션 수
    code_sections = sum(1 for s in sections if "```" in s.get("content", ""))
    # 테이블 포함 섹션 수
    table_sections = sum(1 for s in sections if "| " in s.get("content", "") and "---" in s.get("content", ""))

    # TOC 트리 HTML
    toc_html = ""
    if toc_info:
        toc_html = '<div class="toc-tree"><h3>PDF TOC Structure</h3><ul class="toc-list">'
        for level, title, page in toc_info:
            if level > 3:
                continue
            indent = (level - 1) * 20
            toc_html += f'<li style="padding-left:{indent}px" class="toc-l{level}"><span class="toc-level">L{level}</span> {_escape(title)} <span class="toc-page">p.{page}</span></li>'
        toc_html += "</ul></div>"

    # 섹션 카드 HTML
    section_cards = ""
    for idx, section in enumerate(sections):
        title = section.get("title", "Untitled")
        content = section.get("content", "")
        source_page = section.get("source_page", "")
        char_count = len(content)
        sc = _size_class(char_count)
        bar_color = _size_color(char_count)
        bar_width = min(100, char_count / max_chars * 100) if max_chars > 0 else 0

        has_code = "```" in content
        has_table = "| " in content and "---" in content
        badges = ""
        if has_code:
            badges += '<span class="badge badge-code">CODE</span>'
        if has_table:
            badges += '<span class="badge badge-table">TABLE</span>'

        # content 미리보기 (처음 300자)
        preview = content[:300].replace("\n", " ")
        if len(content) > 300:
            preview += "..."

        section_cards += f"""
        <div class="section-card {sc}" id="section-{idx}">
            <div class="section-header" onclick="toggleSection({idx})">
                <div class="section-title-row">
                    <span class="section-idx">#{idx + 1}</span>
                    <span class="section-title">{_escape(title)}</span>
                    {badges}
                </div>
                <div class="section-meta">
                    <span class="section-page">{_escape(source_page)}</span>
                    <span class="section-chars">{char_count:,}chars</span>
                    <span class="section-toggle" id="toggle-{idx}">+</span>
                </div>
            </div>
            <div class="section-bar">
                <div class="section-bar-fill" style="width:{bar_width:.1f}%;background:{bar_color}"></div>
            </div>
            <div class="section-body" id="body-{idx}" style="display:none">
                <pre class="section-content">{_escape(content)}</pre>
            </div>
        </div>
        """

    # 검색 결과 HTML
    search_html = ""
    if search_query and search_results is not None:
        search_html = f"""
        <div class="search-results">
            <h3>Search Results for: "{_escape(search_query)}"</h3>
            <p class="search-count">{len(search_results)} results found</p>
        """
        for i, r in enumerate(search_results):
            preview = r["content"][:500].replace("\n", " ")
            search_html += f"""
            <div class="search-result-card">
                <div class="search-result-header">
                    <span class="search-rank">#{i + 1}</span>
                    <span class="search-result-title">{_escape(r['title'])}</span>
                    <span class="search-score">score: {r['relevance_score']:.2f}</span>
                    <span class="section-page">{_escape(r.get('source_page', ''))}</span>
                </div>
                <div class="search-result-preview">{_escape(preview)}</div>
            </div>
            """
        search_html += "</div>"

    # 크기 분포 차트 (CSS bar chart)
    dist_bars = ""
    max_count = max(size_dist.values()) if size_dist else 1
    colors = {"small (<500)": "#4ade80", "medium (500-2K)": "#60a5fa", "large (2K-5K)": "#fbbf24", "xlarge (5K+)": "#f87171"}
    for label, count in size_dist.items():
        pct = (count / max_count * 100) if max_count > 0 else 0
        color = colors[label]
        dist_bars += f"""
        <div class="dist-row">
            <span class="dist-label">{label}</span>
            <div class="dist-bar-bg"><div class="dist-bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>
            <span class="dist-count">{count}</span>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDF Chunk Visualizer - {_escape(filename)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
h1 {{ font-size: 1.5rem; color: #f8fafc; margin-bottom: 4px; }}
h2 {{ font-size: 1.2rem; color: #94a3b8; margin: 24px 0 12px; }}
h3 {{ font-size: 1rem; color: #cbd5e1; margin-bottom: 8px; }}
.subtitle {{ color: #64748b; font-size: 0.9rem; margin-bottom: 20px; }}

/* Stats */
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.stat-card {{ background: #1e293b; border-radius: 8px; padding: 16px; border: 1px solid #334155; }}
.stat-value {{ font-size: 1.6rem; font-weight: 700; color: #f8fafc; }}
.stat-label {{ font-size: 0.8rem; color: #64748b; margin-top: 4px; }}

/* Distribution */
.dist-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.dist-label {{ width: 120px; font-size: 0.8rem; color: #94a3b8; text-align: right; }}
.dist-bar-bg {{ flex: 1; height: 20px; background: #1e293b; border-radius: 4px; overflow: hidden; }}
.dist-bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}
.dist-count {{ width: 30px; font-size: 0.85rem; color: #cbd5e1; text-align: right; font-weight: 600; }}

/* TOC */
.toc-tree {{ background: #1e293b; border-radius: 8px; padding: 16px; margin-bottom: 24px; border: 1px solid #334155; max-height: 400px; overflow-y: auto; }}
.toc-list {{ list-style: none; }}
.toc-list li {{ padding: 3px 8px; font-size: 0.85rem; border-radius: 4px; }}
.toc-list li:hover {{ background: #334155; }}
.toc-l1 {{ font-weight: 600; color: #f8fafc; }}
.toc-l2 {{ color: #cbd5e1; }}
.toc-l3 {{ color: #94a3b8; font-size: 0.8rem; }}
.toc-level {{ display: inline-block; width: 24px; text-align: center; font-size: 0.7rem; background: #334155; border-radius: 3px; margin-right: 6px; color: #94a3b8; }}
.toc-page {{ float: right; font-size: 0.75rem; color: #64748b; }}

/* Sections */
.section-card {{ background: #1e293b; border-radius: 8px; margin-bottom: 8px; border: 1px solid #334155; overflow: hidden; transition: border-color 0.2s; }}
.section-card:hover {{ border-color: #475569; }}
.section-card.size-small {{ border-left: 3px solid #4ade80; }}
.section-card.size-medium {{ border-left: 3px solid #60a5fa; }}
.section-card.size-large {{ border-left: 3px solid #fbbf24; }}
.section-card.size-xlarge {{ border-left: 3px solid #f87171; }}
.section-header {{ padding: 12px 16px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }}
.section-header:hover {{ background: #253348; }}
.section-title-row {{ display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }}
.section-idx {{ font-size: 0.75rem; color: #64748b; min-width: 30px; }}
.section-title {{ font-size: 0.9rem; color: #e2e8f0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.section-meta {{ display: flex; align-items: center; gap: 12px; flex-shrink: 0; }}
.section-page {{ font-size: 0.75rem; color: #64748b; }}
.section-chars {{ font-size: 0.75rem; color: #94a3b8; font-variant-numeric: tabular-nums; }}
.section-toggle {{ font-size: 1.1rem; color: #64748b; width: 20px; text-align: center; }}
.section-bar {{ height: 3px; background: #0f172a; }}
.section-bar-fill {{ height: 100%; transition: width 0.3s; }}
.section-body {{ padding: 0 16px 16px; }}
.section-content {{ font-size: 0.8rem; color: #cbd5e1; white-space: pre-wrap; word-wrap: break-word; background: #0f172a; border-radius: 6px; padding: 12px; max-height: 500px; overflow-y: auto; line-height: 1.5; font-family: 'Consolas', 'Monaco', monospace; }}

/* Badges */
.badge {{ font-size: 0.65rem; padding: 2px 6px; border-radius: 3px; font-weight: 600; }}
.badge-code {{ background: #1e3a5f; color: #60a5fa; }}
.badge-table {{ background: #3b2f1e; color: #fbbf24; }}

/* Search */
.search-results {{ margin-bottom: 24px; }}
.search-count {{ color: #64748b; font-size: 0.85rem; margin-bottom: 12px; }}
.search-result-card {{ background: #1e293b; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; border: 1px solid #334155; border-left: 3px solid #a78bfa; }}
.search-result-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
.search-rank {{ font-size: 0.75rem; color: #a78bfa; font-weight: 700; }}
.search-result-title {{ font-size: 0.9rem; color: #e2e8f0; flex: 1; }}
.search-score {{ font-size: 0.75rem; color: #a78bfa; background: #2e1065; padding: 2px 8px; border-radius: 4px; }}
.search-result-preview {{ font-size: 0.8rem; color: #94a3b8; }}

/* Filter */
.filter-bar {{ display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }}
.filter-input {{ background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px 12px; color: #e2e8f0; font-size: 0.85rem; width: 300px; outline: none; }}
.filter-input:focus {{ border-color: #60a5fa; }}
.filter-btn {{ background: #334155; border: none; border-radius: 6px; padding: 8px 14px; color: #e2e8f0; font-size: 0.8rem; cursor: pointer; }}
.filter-btn:hover {{ background: #475569; }}
.filter-btn.active {{ background: #1d4ed8; }}

/* Expand All */
.toolbar {{ display: flex; gap: 8px; margin-bottom: 8px; }}

/* two-column layout */
.two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
@media (max-width: 800px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
    <h1>PDF Chunk Visualizer</h1>
    <div class="subtitle">{_escape(filename)} | Parsed in {elapsed_ms:.0f}ms | StructuredKnowledgeStore logic</div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value">{total_sections}</div>
            <div class="stat-label">Total Sections</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{total_chars:,}</div>
            <div class="stat-label">Total Characters</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{avg_chars:,}</div>
            <div class="stat-label">Avg Section Size</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{min_chars:,} ~ {max_chars:,}</div>
            <div class="stat-label">Min ~ Max Size</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{code_sections}</div>
            <div class="stat-label">Code Block Sections</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{table_sections}</div>
            <div class="stat-label">Table Sections</div>
        </div>
    </div>

    <div class="two-col">
        <div>
            <h2>Size Distribution</h2>
            {dist_bars}
        </div>
        <div>
            <h2>Legend</h2>
            <div class="dist-row"><span class="dist-label" style="color:#4ade80">green</span><span class="dist-count" style="color:#94a3b8">&lt;500 chars</span></div>
            <div class="dist-row"><span class="dist-label" style="color:#60a5fa">blue</span><span class="dist-count" style="color:#94a3b8">500-2K</span></div>
            <div class="dist-row"><span class="dist-label" style="color:#fbbf24">amber</span><span class="dist-count" style="color:#94a3b8">2K-5K</span></div>
            <div class="dist-row"><span class="dist-label" style="color:#f87171">red</span><span class="dist-count" style="color:#94a3b8">5K+ (may need splitting)</span></div>
        </div>
    </div>

    {toc_html}

    {search_html}

    <h2>Chunked Sections ({total_sections})</h2>

    <div class="filter-bar">
        <input type="text" class="filter-input" id="filterInput" placeholder="Filter sections by title or content..." oninput="filterSections()">
        <button class="filter-btn" onclick="filterBySize('all')" id="btn-all">All</button>
        <button class="filter-btn" onclick="filterBySize('size-small')" id="btn-size-small">Small</button>
        <button class="filter-btn" onclick="filterBySize('size-medium')" id="btn-size-medium">Medium</button>
        <button class="filter-btn" onclick="filterBySize('size-large')" id="btn-size-large">Large</button>
        <button class="filter-btn" onclick="filterBySize('size-xlarge')" id="btn-size-xlarge">XLarge</button>
    </div>

    <div class="toolbar">
        <button class="filter-btn" onclick="expandAll()">Expand All</button>
        <button class="filter-btn" onclick="collapseAll()">Collapse All</button>
    </div>

    <div id="sections-container">
        {section_cards}
    </div>
</div>

<script>
function toggleSection(idx) {{
    const body = document.getElementById('body-' + idx);
    const toggle = document.getElementById('toggle-' + idx);
    if (body.style.display === 'none') {{
        body.style.display = 'block';
        toggle.textContent = '−';
    }} else {{
        body.style.display = 'none';
        toggle.textContent = '+';
    }}
}}

function expandAll() {{
    document.querySelectorAll('.section-body').forEach(el => el.style.display = 'block');
    document.querySelectorAll('.section-toggle').forEach(el => el.textContent = '−');
}}

function collapseAll() {{
    document.querySelectorAll('.section-body').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.section-toggle').forEach(el => el.textContent = '+');
}}

function filterSections() {{
    const q = document.getElementById('filterInput').value.toLowerCase();
    document.querySelectorAll('.section-card').forEach(card => {{
        const title = card.querySelector('.section-title').textContent.toLowerCase();
        const content = card.querySelector('.section-content')?.textContent?.toLowerCase() || '';
        card.style.display = (title.includes(q) || content.includes(q)) ? '' : 'none';
    }});
}}

let activeSize = 'all';
function filterBySize(size) {{
    activeSize = size;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('btn-' + size).classList.add('active');
    document.querySelectorAll('.section-card').forEach(card => {{
        if (size === 'all') {{
            card.style.display = '';
        }} else {{
            card.style.display = card.classList.contains(size) ? '' : 'none';
        }}
    }});
}}
</script>
</body>
</html>"""


def generate_multi_pdf_html(
    pdf_results: List[dict],
    output_dir: str,
) -> str:
    """여러 PDF 결과를 하나의 요약 HTML로 생성."""
    total_pdfs = len(pdf_results)
    total_sections = sum(r["total_sections"] for r in pdf_results)
    total_chars = sum(r["total_chars"] for r in pdf_results)
    total_time = sum(r["elapsed_ms"] for r in pdf_results)

    rows = ""
    for r in sorted(pdf_results, key=lambda x: x["total_sections"], reverse=True):
        sc_color = _size_color(r["avg_chars"])
        rows += f"""
        <tr>
            <td><a href="{_escape(r['html_file'])}" style="color:#60a5fa;text-decoration:none">{_escape(r['filename'])}</a></td>
            <td style="text-align:right">{r['total_sections']}</td>
            <td style="text-align:right">{r['total_chars']:,}</td>
            <td style="text-align:right">{r['avg_chars']:,}</td>
            <td style="text-align:right">{r['max_chars']:,}</td>
            <td style="text-align:right">{r['code_sections']}</td>
            <td style="text-align:right">{r['table_sections']}</td>
            <td style="text-align:right">{r['elapsed_ms']:.0f}ms</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>PDF Chunk Visualizer - Summary</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #f8fafc; margin-bottom: 4px; }}
.subtitle {{ color: #64748b; margin-bottom: 20px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
.stat-card {{ background: #1e293b; border-radius: 8px; padding: 16px; border: 1px solid #334155; }}
.stat-value {{ font-size: 1.6rem; font-weight: 700; color: #f8fafc; }}
.stat-label {{ font-size: 0.8rem; color: #64748b; }}
table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }}
th {{ background: #334155; padding: 10px 12px; text-align: left; font-size: 0.8rem; color: #94a3b8; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #1e293b; font-size: 0.85rem; }}
tr:hover {{ background: #253348; }}
</style>
</head>
<body>
<div class="container">
    <h1>PDF Chunk Visualizer - Multi-PDF Summary</h1>
    <div class="subtitle">{total_pdfs} PDFs | {total_time:.0f}ms total</div>
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">{total_pdfs}</div><div class="stat-label">PDFs Processed</div></div>
        <div class="stat-card"><div class="stat-value">{total_sections}</div><div class="stat-label">Total Sections</div></div>
        <div class="stat-card"><div class="stat-value">{total_chars:,}</div><div class="stat-label">Total Characters</div></div>
        <div class="stat-card"><div class="stat-value">{total_time:.0f}ms</div><div class="stat-label">Total Parse Time</div></div>
    </div>
    <table>
        <thead><tr>
            <th>File</th><th>Sections</th><th>Total Chars</th><th>Avg Size</th><th>Max Size</th><th>Code</th><th>Tables</th><th>Time</th>
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>
</div>
</body>
</html>"""


def main():
    # Windows cp932 인코딩 문제 방지
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="PDF Chunk Visualizer - StructuredKnowledgeStore 로직으로 PDF 청킹 후 HTML 시각화",
    )
    parser.add_argument(
        "pdf_paths",
        nargs="+",
        help="PDF 파일 경로 (glob 패턴 가능, 예: uploads/manuals/mvs_openframe_7.1/*.pdf)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="출력 HTML 파일 경로 (기본: <pdf_name>_chunks.html)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="출력 디렉토리 (여러 PDF 처리 시, 기본: temp/chunk_viz/)",
    )
    parser.add_argument(
        "--search", "-s",
        default=None,
        help="청킹 후 검색 쿼리 실행 (검색 결과도 HTML에 포함)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 형식으로 청킹 결과 출력 (HTML 대신)",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="통계만 출력 (HTML 생성 없음)",
    )

    args = parser.parse_args()

    # glob 패턴 확장
    all_pdfs = []
    for pattern in args.pdf_paths:
        expanded = glob.glob(pattern)
        if expanded:
            all_pdfs.extend(expanded)
        elif os.path.isfile(pattern):
            all_pdfs.append(pattern)
        else:
            print(f"Warning: {pattern} - no matching files found")

    all_pdfs = [p for p in all_pdfs if p.lower().endswith(".pdf")]
    if not all_pdfs:
        print("Error: No PDF files found")
        sys.exit(1)

    print(f"Processing {len(all_pdfs)} PDF file(s)...")

    # 단일 PDF
    if len(all_pdfs) == 1:
        pdf_path = all_pdfs[0]
        print(f"  Chunking: {os.path.basename(pdf_path)}")
        sections, elapsed_ms, toc_info = chunk_pdf(pdf_path)
        total_chars = sum(len(s.get("content", "")) for s in sections)
        print(f"  -> {len(sections)} sections, {total_chars:,} chars, {elapsed_ms:.0f}ms")

        if args.stats_only:
            print(f"\n--- Stats ---")
            print(f"  Sections: {len(sections)}")
            print(f"  Total chars: {total_chars:,}")
            print(f"  Avg size: {total_chars // len(sections) if sections else 0:,}")
            print(f"  Code blocks: {sum(1 for s in sections if '```' in s.get('content', ''))}")
            print(f"  Tables: {sum(1 for s in sections if '| ' in s.get('content', '') and '---' in s.get('content', ''))}")
            for s in sections:
                depth = s["title"].count(" > ") + 1
                prefix = "  " * depth
                chars = len(s.get("content", ""))
                print(f"  {prefix}{s['title']} ({chars:,} chars) [{s.get('source_page', '')}]")
            return

        if args.json:
            output = args.output or os.path.splitext(os.path.basename(pdf_path))[0] + "_chunks.json"
            with open(output, "w", encoding="utf-8") as f:
                json.dump(sections, f, ensure_ascii=False, indent=2)
            print(f"  JSON output: {output}")
            return

        search_results = None
        if args.search:
            print(f"  Searching: \"{args.search}\"")
            search_results = search_chunks(sections, args.search)
            print(f"  -> {len(search_results)} results")

        html_content = generate_html(
            pdf_path, sections, elapsed_ms, toc_info,
            search_query=args.search, search_results=search_results,
        )

        output_path = args.output or os.path.splitext(os.path.basename(pdf_path))[0] + "_chunks.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"  HTML output: {output_path}")

    # 여러 PDF
    else:
        output_dir = args.output_dir or os.path.join("temp", "chunk_viz")
        os.makedirs(output_dir, exist_ok=True)

        pdf_results = []
        for pdf_path in all_pdfs:
            filename = os.path.basename(pdf_path)
            print(f"  Chunking: {filename}")
            sections, elapsed_ms, toc_info = chunk_pdf(pdf_path)
            total_chars = sum(len(s.get("content", "")) for s in sections)
            avg_chars = total_chars // len(sections) if sections else 0
            max_chars = max((len(s.get("content", "")) for s in sections), default=0)
            code_sections = sum(1 for s in sections if "```" in s.get("content", ""))
            table_sections = sum(1 for s in sections if "| " in s.get("content", "") and "---" in s.get("content", ""))
            print(f"    -> {len(sections)} sections, {total_chars:,} chars, {elapsed_ms:.0f}ms")

            # 개별 HTML 생성
            html_file = os.path.splitext(filename)[0] + "_chunks.html"
            html_path = os.path.join(output_dir, html_file)

            search_results = None
            if args.search:
                search_results = search_chunks(sections, args.search)

            html_content = generate_html(
                pdf_path, sections, elapsed_ms, toc_info,
                search_query=args.search, search_results=search_results,
            )
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            pdf_results.append({
                "filename": filename,
                "html_file": html_file,
                "total_sections": len(sections),
                "total_chars": total_chars,
                "avg_chars": avg_chars,
                "max_chars": max_chars,
                "code_sections": code_sections,
                "table_sections": table_sections,
                "elapsed_ms": elapsed_ms,
            })

        # 요약 HTML
        summary_html = generate_multi_pdf_html(pdf_results, output_dir)
        summary_path = os.path.join(output_dir, "index.html")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_html)

        total_sections = sum(r["total_sections"] for r in pdf_results)
        total_time = sum(r["elapsed_ms"] for r in pdf_results)
        print(f"\nDone: {len(all_pdfs)} PDFs, {total_sections} sections, {total_time:.0f}ms")
        print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
