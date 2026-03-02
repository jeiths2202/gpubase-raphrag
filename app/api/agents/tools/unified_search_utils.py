"""Unified Search Utility Functions

Intent detection, query validation, result formatting utilities.
Extracted from unified_search.py for code organization.
"""
import re
import logging
from typing import Dict, Any, List, Set, Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================
# INTENT DETECTION PATTERNS
# =============================================================

_ERROR_INTENT_PATTERNS = re.compile(
    r'에러|error|오류|エラー|실패|fail|exception|장애|障害|원인|cause|이유|reason|해결|solution|fix|대처|対処',
    re.IGNORECASE
)
_COMMAND_INTENT_PATTERNS = re.compile(
    r'명령|command|cmd|사용법|usage|how\s*to|방법|옵션|option|파라미터|parameter|argument|구문|syntax|실행|execute|run',
    re.IGNORECASE
)
_GLOSSARY_INTENT_PATTERNS = re.compile(
    r'뭐|what\s*is|무엇|정의|definition|의미|mean|약어|abbreviation|용어|term|설명|explain|概要',
    re.IGNORECASE
)

SPECIFIC_SECTION_PATTERNS = [
    '基本構造', '基本設定', '構造', '構成', '設定', '使用方法', '使い方',
    '概要', '詳細', 'について', '説明', 'chapter', 'section', 'guide',
    '설정', '구성', '구조', '방법', '상세', '개요',
]

DEFINITION_KEYWORDS = ['とは', '是什么', '是什麼', '란', '이란', 'what is', 'define ', 'meaning of']


def detect_query_intent(query: str) -> Set[str]:
    """Detect query intent based on keyword patterns."""
    intents = set()
    if _ERROR_INTENT_PATTERNS.search(query):
        intents.add('error')
    if _COMMAND_INTENT_PATTERNS.search(query):
        intents.add('command')
    if _GLOSSARY_INTENT_PATTERNS.search(query):
        intents.add('glossary')
    return intents or {'general'}


def check_intent_result_match(query_intents: Set[str], summary_results: List[Dict], query: str = "") -> bool:
    """Check if summary results match detected query intent."""
    if not summary_results:
        return False

    # Get result types
    result_types = set()
    for result in summary_results:
        result_type = result.get("type", "").lower()
        if "error" in result_type:
            result_types.add('error')
        elif "command" in result_type:
            result_types.add('command')
        elif "glossary" in result_type or "term" in result_type:
            result_types.add('glossary')
        else:
            result_types.add('general')

    # Encoding issue workaround
    if query and '?' in query and result_types == {'command'}:
        return False

    # Specific section check
    if query and any(p in query.lower() for p in SPECIFIC_SECTION_PATTERNS):
        if result_types <= {'glossary', 'term'}:
            return False

    # Definition query check
    query_lower = query.lower() if query else ""
    is_definition_query = any(kw in query_lower for kw in DEFINITION_KEYWORDS)
    is_only_glossary = result_types <= {'glossary', 'term'}

    if 'general' in query_intents:
        if is_only_glossary and not is_definition_query:
            return False
        return True

    if 'error' in query_intents and 'error' not in result_types:
        return False
    if 'error' in query_intents and 'command' in query_intents and 'error' not in result_types:
        return False

    return True


# =============================================================
# MARKDOWN TABLE UTILITIES
# =============================================================

def fix_markdown_table_separators(content: str) -> str:
    """Fix markdown tables missing separator line."""
    lines = content.split('\n')
    result_lines = []
    table_rows = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        is_table_row = stripped.startswith('|') and stripped.endswith('|') and stripped.count('|') >= 2
        is_separator = bool(re.match(r'^\|[\s\-:|]+\|$', stripped)) if stripped else False

        if is_table_row or is_separator:
            if not in_table:
                in_table = True
            table_rows.append(stripped)
        elif stripped == '' and in_table:
            continue
        else:
            if table_rows:
                result_lines.extend(_finalize_table(table_rows))
                table_rows = []
                in_table = False
            result_lines.append(line)

    if table_rows:
        result_lines.extend(_finalize_table(table_rows))

    return '\n'.join(result_lines)


def _finalize_table(rows: List[str]) -> List[str]:
    """Add separator after first row if missing."""
    if not rows:
        return rows

    result = [rows[0]]
    if len(rows) > 1:
        is_separator = bool(re.match(r'^\|[\s\-:|]+\|$', rows[1]))
        if not is_separator:
            cols = len([c for c in rows[0].split('|') if c.strip()])
            separator = '|' + '|'.join([' --- ' for _ in range(cols)]) + '|'
            result.append(separator)

    result.extend(rows[1:])
    return result


# =============================================================
# RESULT FORMATTING
# =============================================================

def format_summary_result(result: Dict, index: int) -> str:
    """Format a single summary result for output."""
    result_type = result.get("type", "unknown")
    name = result.get("name", "Unknown")
    description = result.get("description", "")
    content = result.get("content", "")
    source_file = result.get("source_file", "")
    page_numbers = result.get("page_numbers", [])
    score = result.get("score", 0)

    type_label = result_type.upper()
    if result_type == "error-codes":
        type_label = "ERROR CODE"
    elif result_type == "commands":
        type_label = "COMMAND"
    elif result_type == "glossary":
        type_label = "TERM"
    elif result_type == "apis":
        type_label = "API"

    chunk_info = f"\n{index}. [{type_label}] {name}\n   Score: {score:.2f}\n"

    if result_type == "error-codes":
        if description:
            chunk_info += f"   설명: {description}\n"
        solution = result.get("solution") or ""
        if solution:
            chunk_info += f"   대처방법: {solution}\n"
    elif result_type == "commands":
        if description:
            chunk_info += f"   설명: {description[:200]}\n"
        syntax = result.get("syntax") or ""
        if syntax:
            chunk_info += f"   구문: {syntax}\n"
        products = result.get("products") or result.get("product") or ""
        if products:
            if isinstance(products, list):
                products = ", ".join(products)
            chunk_info += f"   제품: {products}\n"
    elif result_type == "glossary":
        full_name = result.get("full_name") or ""
        if full_name:
            chunk_info += f"   정식명칭: {full_name}\n"
        if description:
            chunk_info += f"   설명: {description}\n"
    elif result_type == "apis":
        if description:
            chunk_info += f"   설명: {description[:200]}\n"
        syntax = result.get("syntax") or ""
        if syntax:
            chunk_info += f"   프로토타입: {syntax}\n"
    else:
        if content:
            chunk_info += f"   Content: {content[:300]}...\n"

    if source_file:
        chunk_info += f"   Source: {source_file}"
        if page_numbers:
            pages_str = ", ".join(str(p) for p in page_numbers[:3])
            chunk_info += f" (p.{pages_str})"
        chunk_info += "\n"

    return chunk_info


def format_search_result(result: Dict) -> str:
    """Format a single search result for output."""
    chunk_type = result.get("chunk_type", "TEXT")
    rrf_score = result.get("rrf_score", 0)
    source = result.get("source", {})
    doc_name = source.get("document_name", "Unknown")
    page_start = source.get("page_start", "?")
    page_end = source.get("page_end", "?")
    section_title = source.get("section_title", "")
    section_path = source.get("section_path", "")
    content = result.get("content", "")

    # Page display
    page_display = f"p.{page_start}" if page_start == page_end or not page_end else f"p.{page_start}-{page_end}"
    source_display = f"{doc_name} ({page_display})"

    chunk_info = (
        f"\n{result['index']}. [{chunk_type}] RRF Score: {rrf_score:.4f}\n"
        f"   Source: {source_display}\n"
    )

    # Web source URL
    if source.get("source_type") == "web" and source.get("source_url"):
        chunk_info += f"   🌐 Web Source: {source['source_url']}\n"

    if result.get("error_boosted"):
        chunk_info += "   ⚠️ KEYWORD MATCH - ANSWER IS IN CONTENT BELOW:\n"
    if result.get("exact_phrase_match"):
        chunk_info += "   🎯 EXACT PHRASE MATCH - HIGH PRIORITY RESULT\n"
    elif result.get("exact_phrase_partial"):
        chunk_info += "   ✓ Partial phrase match\n"

    if section_title:
        chunk_info += f"   Section: {section_title}\n"
    if section_path:
        chunk_info += f"   Path: {section_path}\n"

    # Truncate content
    if len(content) > 800:
        content = content[:800] + "..."
    chunk_info += f"   Content:\n   {content}\n"

    return chunk_info


def build_enriched_result(result: Dict, index: int) -> Dict:
    """Build enriched result dict for metadata."""
    source = result.get("source", {})
    page_numbers = result.get("page_numbers", [])

    return {
        "index": index,
        "chunk_type": result.get("type", "unknown").upper(),
        "title": result.get("name", ""),
        "content": result.get("content") or result.get("description") or "",
        "rrf_score": result.get("score", 0),
        "source": {
            "document_name": result.get("source_pdf") or result.get("source_file", ""),
            "source_file": result.get("source_file", ""),
            "page_start": page_numbers[0] if page_numbers else None,
            "page_end": page_numbers[-1] if page_numbers else None,
            "source_type": "summary",
        },
        "summary_match": True,
        "tables": [],
        "images": [],
    }
