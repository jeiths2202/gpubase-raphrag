"""
Agent Executor
Implements the ReAct (Reasoning + Acting) loop for agent execution.
"""
from typing import Dict, List, Any, Optional, AsyncGenerator
import asyncio
import logging
import os
import time
import json
import base64

from .types import (
    AgentContext, AgentResult, AgentMessage, ToolCall,
    ToolResult, MessageRole, ToolStatus, AgentStreamChunk,
    ToolDefinition, ResponseMode
)
from .base import BaseAgent
from .registry import ToolRegistry, get_tool_registry
from .permissions import PermissionManager, get_permission_manager
from .master_system_constraint import (
    build_constrained_system_prompt,
    get_constraint_enforcer,
    log_compliance_violation,
    ComplianceViolationType,
    get_insufficient_info_response
)
from .formatters import DirectReturnFormatter, HybridModeDecision
from .types import BlockType, AnswerBlock, StructuredAnswer
from ..core.app_mode import is_develop_mode
from ..services.reliability_service import calculate_reliability
import re

logger = logging.getLogger(__name__)


# ============================================================================
# STRIP THINKING TAGS: Remove internal LLM reasoning from responses
# ============================================================================

def strip_thinking_tags(text: str) -> str:
    """
    LLM 응답에서 thinking 관련 콘텐츠 제거.

    Strategy:
    1. Remove <think>...</think> tags
    2. Find actual content by looking for answer markers (###, bullets, CJK text blocks)
    3. Remove English internal reasoning sentences before actual content
    4. Preserve actual answer content
    """
    if not text:
        return text

    # Step 1: <think>...</think> 태그와 그 내용 제거
    cleaned = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)

    # Step 2: Find the start of actual content
    # Look for markers that indicate actual answer content:
    # - Markdown headers (###, ##, #)
    # - Japanese/Korean/Chinese content blocks
    # - Numbered lists (1., 2.)
    # - Bullet points (-, *, •)

    # Pattern to find actual content start
    actual_content_markers = [
        r'#{1,3}\s+',                           # Markdown headers
        r'(?:^|\n)(?:\d+\.|\-|\*|•)\s+',        # Lists
        r'(?:^|\n)[^\x00-\x7F]{5,}',            # CJK text (5+ non-ASCII chars at line start)
        r'(?:^|\n)(?:原因|解決|関連|出典|エラー|概要|説明|参考|注意|결과|원인|해결|관련|오류|개요|설명)',  # JP/KR section headers
    ]

    # Find earliest match of actual content
    earliest_pos = len(cleaned)
    for marker in actual_content_markers:
        match = re.search(marker, cleaned)
        if match:
            earliest_pos = min(earliest_pos, match.start())

    # If we found actual content marker, check if there's thinking before it
    if earliest_pos > 0 and earliest_pos < len(cleaned):
        before_content = cleaned[:earliest_pos]
        after_content = cleaned[earliest_pos:]

        # Check if the part before actual content is mostly English thinking
        english_thinking_patterns = [
            r'(?:let\'?s|I\'?ll|I\'?m going to) (?:tackle|check|look|analyze|extract|provide|explain)',
            r'I (?:see|need|should|must|will|can) (?:that|to|)',
            r'(?:The|This) (?:user|query|question|content|tool|search|response)',
            r'(?:From|Based on|Looking at|According to) (?:the|this|my)',
            r'(?:keyword|information|document|chunk|result)s? (?:is|are|found|present)',
            r'(?:present|structure|mention|cite|format|extract)',
            r'(?:clearly|properly|carefully|correctly|concise)',
        ]

        is_thinking_section = any(
            re.search(p, before_content, re.IGNORECASE)
            for p in english_thinking_patterns
        )

        if is_thinking_section:
            cleaned = after_content.lstrip()

    # Step 3: Remove any remaining English thinking sentences at the beginning
    thinking_sentence_patterns = [
        r'^(?:Okay|Ok|Alright|Well|So|Now|Let\'?s)[,.]?\s*[^#\n]*?(?:query|user|question|search|tool|response|document|content)[^#\n]*?\.\s*',
        r'^(?:I (?:see|need|should|must|will|can|\'ll|\'m)[^#\n]*?\.\s*)+',
        r'^(?:The (?:user|query|question|content|keyword)[^#\n]*?\.\s*)+',
        r'^(?:From|Based on|Looking at|According to)[^#\n]*?\.\s*',
        r'^(?:Since|Because|As)[^#\n]*?(?:Japanese|Korean|language|respond)[^#\n]*?\.\s*',
    ]

    for pattern in thinking_sentence_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)

    # Step 4: Remove JSON tool outputs
    cleaned = re.sub(r'{\s*"query"[^}]+}\s*', '', cleaned)
    cleaned = re.sub(r'{\s*"results[^}]+}\s*', '', cleaned)

    # Step 5: Clean up multiple newlines and whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()

    return cleaned


# ============================================================================
# DEVELOP MODE: All-Tools Execution for debugging and analysis
# ============================================================================

# Tools that can be executed with just a query (no required doc_id etc.)
DEVELOP_MODE_SEARCHABLE_TOOLS = ["adaptive_search", "vector_search", "graph_query"]


def _format_develop_mode_summary(
    query: str,
    tool_results: Dict[str, Dict[str, Any]]
) -> str:
    """
    Format develop mode results summary.

    Args:
        query: Original search query
        tool_results: Dict of tool_name -> {count, results, error}

    Returns:
        Formatted markdown summary
    """
    total_count = sum(r.get("count", 0) for r in tool_results.values())

    lines = [
        f"## 🔍 개발 모드 검색 결과",
        f"",
        f"검색키워드 **'{query}'**에 대해 총 **{total_count}건**을 찾았습니다.",
        f"",
    ]

    for tool_name, result in tool_results.items():
        count = result.get("count", 0)
        error = result.get("error")

        if error:
            lines.append(f"- **{tool_name}**: ❌ 오류 - {error}")
        elif count == 0:
            lines.append(f"- **{tool_name}**: 0건")
        else:
            # Format similarity scores
            scores = result.get("scores", [])
            if scores:
                score_str = ", ".join([f"{s*100:.1f}%" for s in scores[:5]])
                if len(scores) > 5:
                    score_str += f" ... 외 {len(scores)-5}건"
                lines.append(f"- **{tool_name}**: {count}건 (유사도: {score_str})")
            else:
                lines.append(f"- **{tool_name}**: {count}건")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### 📋 각 Tool별 상세 검색 결과")
    lines.append("")

    for tool_name, result in tool_results.items():
        lines.append(f"#### {tool_name}")

        if result.get("error"):
            lines.append(f"오류: {result['error']}")
        elif result.get("count", 0) == 0:
            lines.append("결과 없음")
        else:
            results_data = result.get("results", [])
            for i, item in enumerate(results_data[:5], 1):
                score = item.get("score") or item.get("similarity", 0)
                content_preview = item.get("content", "")[:200]
                source = item.get("source", "Unknown")

                lines.append(f"**{i}. [{source}]** (유사도: {score*100:.1f}%)")
                lines.append(f"> {content_preview}...")
                lines.append("")

        lines.append("")

    return "\n".join(lines)


async def _execute_all_tools_develop_mode(
    tools: List[Any],
    query: str,
    context: "AgentContext"
) -> Dict[str, Dict[str, Any]]:
    """
    Execute all searchable tools in parallel for develop mode.

    Args:
        tools: List of available tools
        query: Search query
        context: Agent context

    Returns:
        Dict of tool_name -> {count, scores, results, error}
    """
    results = {}

    async def execute_tool(tool):
        tool_name = tool.name
        try:
            if tool_name == "adaptive_search":
                result = await tool.execute(context, query=query, top_k=10, include_images=True)
            elif tool_name == "vector_search":
                result = await tool.execute(context, query=query, top_k=10)
            elif tool_name == "graph_query":
                result = await tool.execute(context, query=query, query_type="entity", top_k=10)
            else:
                return tool_name, {"count": 0, "scores": [], "results": [], "error": "Not a searchable tool"}

            if not result.get("success"):
                return tool_name, {"count": 0, "scores": [], "results": [], "error": result.get("error", "Unknown error")}

            # Extract data from metadata (preferred) or output
            metadata = result.get("metadata", {})
            output = result.get("output", "")

            # Try to get structured data from metadata.sources first
            sources = metadata.get("sources", [])
            count = metadata.get("results_count", 0)

            if sources:
                # Use sources from metadata (adaptive_search, vector_search)
                scores = [float(s.get("score", 0) or s.get("similarity", 0) or 0) for s in sources]
                items = sources
            else:
                # Try to parse output JSON (for tools that return JSON output)
                try:
                    if isinstance(output, str):
                        data = json.loads(output)
                    else:
                        data = output if isinstance(output, dict) else {}
                except (json.JSONDecodeError, TypeError):
                    data = {}

                items = data.get("results", [])
                count = data.get("results_count", len(items)) if not count else count

                # Extract similarity scores from different formats
                scores = []
                for item in items:
                    score = item.get("score") or item.get("similarity") or 0
                    scores.append(float(score) if score else 0)

            return tool_name, {
                "count": count or len(items),
                "scores": scores,
                "results": items,
                "error": None
            }

        except Exception as e:
            logger.error(f"[DevelopMode] Error executing {tool_name}: {e}")
            return tool_name, {"count": 0, "scores": [], "results": [], "error": str(e)}

    # Filter to only searchable tools
    searchable_tools = [t for t in tools if t.name in DEVELOP_MODE_SEARCHABLE_TOOLS]

    # Execute in parallel
    tasks = [execute_tool(tool) for tool in searchable_tools]
    task_results = await asyncio.gather(*tasks, return_exceptions=True)

    for item in task_results:
        if isinstance(item, Exception):
            logger.error(f"[DevelopMode] Task exception: {item}")
            continue
        tool_name, result_data = item
        results[tool_name] = result_data

    return results


# ============================================================================
# RAG Analysis: Extract and format detailed RAG processing information
# ============================================================================

def _analyze_query_keywords(query: str, language: str = "ko") -> Dict[str, Any]:
    """
    분석 프롬프트에서 키워드와 의도를 추출합니다.
    Extracts keywords and intent from the query prompt.

    Args:
        query: User query string
        language: User's configured language (ko, en, ja)

    Returns:
        Dict with keywords, intent, search_strategy (localized)
    """
    import re

    # Localized labels for intent and search strategy
    INTENT_LABELS = {
        "info_search": {"ko": "정보 검색", "en": "Information Search", "ja": "情報検索"},
        "error_fix": {"ko": "오류 해결", "en": "Error Resolution", "ja": "エラー解決"},
        "howto": {"ko": "방법/절차 안내", "en": "How-to Guide", "ja": "手順ガイド"},
        "compare": {"ko": "비교 분석", "en": "Comparison Analysis", "ja": "比較分析"},
        "concept": {"ko": "개념 설명", "en": "Concept Explanation", "ja": "概念説明"},
    }
    STRATEGY_LABELS = {
        "simple_vector": {"ko": "단순 벡터 검색", "en": "Simple Vector Search", "ja": "単純ベクター検索"},
        "complex_query": {"ko": "복합 쿼리 검색", "en": "Complex Query Search", "ja": "複合クエリ検索"},
        "include_image": {"ko": "이미지/테이블 포함", "en": "Include Images/Tables", "ja": "画像/テーブル含む"},
    }

    def get_label(labels: Dict, key: str) -> str:
        """Get localized label, fallback to English then Korean"""
        lang_labels = labels.get(key, {})
        return lang_labels.get(language, lang_labels.get("en", lang_labels.get("ko", key)))

    # 간단한 키워드 추출 (stopwords 제외)
    stopwords_ko = {'이', '가', '은', '는', '을', '를', '의', '에', '에서', '로', '으로', '와', '과', '도', '만', '까지', '부터', '처럼', '같이', '대해', '대한', '관한', '있는', '있다', '없다', '하는', '하다', '되는', '되다', '한', '할', '된', '될', '합니다', '입니다', '습니다', '있습니다', '어떻게', '무엇', '언제', '어디', '왜', '누가'}
    stopwords_en = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because', 'until', 'while', 'about', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves', 'you', 'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'we', 'us', 'our', 'ours', 'ourselves', 'i', 'me', 'my', 'mine', 'myself'}
    stopwords_ja = {'の', 'に', 'は', 'を', 'た', 'が', 'で', 'て', 'と', 'し', 'れ', 'さ', 'ある', 'いる', 'も', 'する', 'から', 'な', 'こと', 'として', 'い', 'や', 'など', 'なっ', 'ない', 'この', 'ため', 'その', 'あっ', 'よう', 'また', 'もの', 'という', 'あり', 'まで', 'られ', 'なる', 'へ', 'か', 'だ', 'これ', 'によって', 'により', 'おり', 'より', 'による', 'ず', 'なり', 'られる', 'において', 'ば', 'なかっ', 'なく', 'しかし', 'について', 'せ', 'だっ', 'でき', 'それ', 'お', 'ほど', 'ものの', 'に対して', 'ほとんど', 'と共に', 'といった', 'です', 'ます', 'でした'}

    # 토큰화 (알파벳, 숫자, 한글, 일본어 히라가나/카타카나/한자)
    tokens = re.findall(r'[a-zA-Z0-9가-힣ぁ-んァ-ン一-龥]+', query.lower())

    # 키워드 추출 (stopwords 제외, 2글자 이상)
    all_stopwords = stopwords_ko | stopwords_en | stopwords_ja
    keywords = [t for t in tokens if t not in all_stopwords and len(t) >= 2]

    # 의도 분류 (간단한 규칙 기반) - multilingual keywords
    intent_key = "info_search"
    if any(kw in query.lower() for kw in ['오류', 'error', '에러', '버그', 'bug', '문제', 'problem', 'issue', 'エラー', 'バグ', '問題']):
        intent_key = "error_fix"
    elif any(kw in query.lower() for kw in ['방법', 'how', '어떻게', '설정', 'config', 'setup', 'install', '方法', 'やり方', '設定', 'インストール']):
        intent_key = "howto"
    elif any(kw in query.lower() for kw in ['비교', 'compare', '차이', 'difference', 'vs', '比較', '違い']):
        intent_key = "compare"
    elif any(kw in query.lower() for kw in ['정의', 'what', '무엇', 'definition', '개념', '何', '定義', '概念', 'とは']):
        intent_key = "concept"

    # 검색 전략 결정
    strategy_keys = []
    if len(keywords) <= 2:
        strategy_keys.append("simple_vector")
    else:
        strategy_keys.append("complex_query")

    if any(kw in query.lower() for kw in ['표', 'table', '그림', 'figure', '이미지', 'image', '차트', 'chart', '図', '画像', 'テーブル', 'チャート']):
        strategy_keys.append("include_image")

    return {
        "original_query": query,
        "keywords": keywords[:10],  # 상위 10개 키워드
        "intent": get_label(INTENT_LABELS, intent_key),
        "search_strategy": [get_label(STRATEGY_LABELS, sk) for sk in strategy_keys],
        "token_count": len(tokens)
    }


def _extract_chunk_structure(tool_result: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    """
    도구 결과에서 청킹 구조 정보를 추출합니다.
    """
    structure = {
        "tool_name": tool_name,
        "total_chunks": 0,
        "chunk_types": {},
        "page_distribution": {},
        "avg_chunk_size": 0,
        "chunks_preview": []
    }

    metadata = tool_result.get("metadata", {})
    sources = metadata.get("sources", [])

    if not sources:
        # Try parsing output
        try:
            output = tool_result.get("output", "")
            if isinstance(output, str):
                data = json.loads(output)
                sources = data.get("results", [])
        except:
            pass

    if sources:
        structure["total_chunks"] = len(sources)

        chunk_types = {}
        pages = {}
        total_size = 0

        for i, src in enumerate(sources[:20]):  # 상위 20개만 분석
            # 청크 타입
            chunk_type = src.get("chunk_type", src.get("type", "TEXT"))
            chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1

            # 페이지 분포
            page = src.get("page_number", src.get("page", 0))
            if page:
                pages[page] = pages.get(page, 0) + 1

            # 청크 크기
            content = src.get("content", src.get("text", ""))
            total_size += len(content)

            # 미리보기
            if i < 5:
                structure["chunks_preview"].append({
                    "index": i + 1,
                    "type": chunk_type,
                    "page": page,
                    "size": len(content),
                    "preview": content[:100] + "..." if len(content) > 100 else content,
                    "similarity": src.get("score", src.get("similarity", 0))
                })

        structure["chunk_types"] = chunk_types
        structure["page_distribution"] = dict(sorted(pages.items())[:10])  # 상위 10페이지
        structure["avg_chunk_size"] = total_size // len(sources) if sources else 0

    return structure


def _extract_embedding_info(tool_result: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    """
    도구 결과에서 임베딩 정보를 추출합니다.
    """
    info = {
        "tool_name": tool_name,
        "model": "NV-EmbedQA-Mistral-7B-v2",  # 기본 임베딩 모델
        "dimension": 4096,
        "similarity_scores": [],
        "score_distribution": {
            "excellent": 0,  # >= 0.8
            "good": 0,       # >= 0.6
            "fair": 0,       # >= 0.4
            "low": 0         # < 0.4
        },
        "top_matches": []
    }

    metadata = tool_result.get("metadata", {})
    sources = metadata.get("sources", [])

    if not sources:
        try:
            output = tool_result.get("output", "")
            if isinstance(output, str):
                data = json.loads(output)
                sources = data.get("results", [])
        except:
            pass

    if sources:
        for src in sources[:20]:
            score = float(src.get("score", src.get("similarity", 0)) or 0)
            info["similarity_scores"].append(score)

            # 점수 분포
            if score >= 0.8:
                info["score_distribution"]["excellent"] += 1
            elif score >= 0.6:
                info["score_distribution"]["good"] += 1
            elif score >= 0.4:
                info["score_distribution"]["fair"] += 1
            else:
                info["score_distribution"]["low"] += 1

        # 상위 매치
        for i, src in enumerate(sources[:5]):
            score = float(src.get("score", src.get("similarity", 0)) or 0)
            info["top_matches"].append({
                "rank": i + 1,
                "source": src.get("source", src.get("document_name", "Unknown")),
                "score": score,
                "score_pct": f"{score * 100:.1f}%"
            })

    return info


# Max characters per tool result to prevent context overflow
def _get_max_tool_result_chars() -> int:
    """
    Get maximum tool result characters based on LLM context mode.

    When RAG_LLM_USE_LARGE_CONTEXT=true, uses Mistral NeMo 12B (128K context),
    allowing much larger tool results for better RAG accuracy.

    Values are configured in api_settings:
    - RAG_TOOL_RESULT_CHARS: Standard mode (default: 6000)
    - RAG_TOOL_RESULT_CHARS_LARGE: Large context mode (default: 15000)
    """
    from ..core.config import api_settings

    use_large_context = os.getenv("RAG_LLM_USE_LARGE_CONTEXT", "false").lower() == "true"
    if use_large_context:
        return api_settings.RAG_TOOL_RESULT_CHARS_LARGE
    return api_settings.RAG_TOOL_RESULT_CHARS


def _truncate_tool_result(content: str, max_chars: int = None) -> str:
    """
    Truncate tool result content to prevent LLM context overflow.
    Keeps the beginning and notes truncation.

    Args:
        content: The content to truncate
        max_chars: Maximum characters. If None, determined by RAG_LLM_USE_LARGE_CONTEXT setting.
    """
    if max_chars is None:
        max_chars = _get_max_tool_result_chars()

    if not content or len(content) <= max_chars:
        return content

    truncated = content[:max_chars]
    # Try to cut at a natural boundary (newline or period)
    last_newline = truncated.rfind('\n', max_chars - 500, max_chars)
    last_period = truncated.rfind('. ', max_chars - 500, max_chars)
    cut_point = max(last_newline, last_period)

    if cut_point > max_chars - 500:
        truncated = truncated[:cut_point + 1]

    return truncated + f"\n\n[... truncated {len(content) - len(truncated)} characters]"


def _get_max_file_context_chars() -> int:
    """
    Get maximum file context characters based on LLM context mode.

    File context is more critical than tool results, so we allow slightly more
    but still need to leave room for system prompt, user query, and response.

    Default: 5000 chars (standard mode), 12000 chars (large context mode)
    """
    from ..core.config import api_settings

    use_large_context = os.getenv("RAG_LLM_USE_LARGE_CONTEXT", "false").lower() == "true"
    if use_large_context:
        # Large context mode: use about 80% of tool result limit
        return int(api_settings.RAG_TOOL_RESULT_CHARS_LARGE * 0.8)
    # Standard mode: 5000 chars to leave room for prompt overhead
    # 8192 tokens ≈ 32K chars, but with Korean text ~16K chars
    # System prompt ~2K chars, user query ~500 chars, response reserve ~3K chars
    return 5000


def _truncate_file_context(content: str, max_chars: int = None) -> str:
    """
    Truncate file context content to prevent LLM context overflow.

    Keeps the beginning and notes truncation. For file context, we also
    try to preserve section boundaries where possible.

    Args:
        content: The file context content to truncate
        max_chars: Maximum characters. If None, determined by _get_max_file_context_chars().

    Returns:
        Truncated content with truncation note if applicable
    """
    if max_chars is None:
        max_chars = _get_max_file_context_chars()

    if not content or len(content) <= max_chars:
        return content

    truncated = content[:max_chars]

    # Try to cut at a natural boundary (section header, paragraph, or sentence)
    # Look for markdown headers first (##, ###)
    last_header = truncated.rfind('\n##', max_chars - 1000, max_chars)
    last_double_newline = truncated.rfind('\n\n', max_chars - 800, max_chars)
    last_newline = truncated.rfind('\n', max_chars - 500, max_chars)
    last_period = truncated.rfind('. ', max_chars - 300, max_chars)

    # Prefer section boundaries over sentence boundaries
    cut_point = max_chars
    if last_header > max_chars - 1000:
        cut_point = last_header
    elif last_double_newline > max_chars - 800:
        cut_point = last_double_newline
    elif last_newline > max_chars - 500:
        cut_point = last_newline + 1
    elif last_period > max_chars - 300:
        cut_point = last_period + 1

    truncated = truncated[:cut_point]
    original_len = len(content)
    truncated_len = len(truncated)
    remaining = original_len - truncated_len

    logger.warning(
        f"[Executor] File context truncated: {original_len} -> {truncated_len} chars "
        f"(removed {remaining} chars, {remaining * 100 // original_len}%)"
    )

    return truncated + f"\n\n[... 문서가 너무 길어 {remaining:,} 문자가 생략되었습니다. 전체 내용은 원본 문서를 참조하세요.]"


# ============================================================================
# HYBRID MODE: Direct Return vs LLM Synthesis
# ============================================================================

# Formatter instance for hybrid mode (singleton)
_direct_formatter: Optional[DirectReturnFormatter] = None


def _get_direct_formatter() -> DirectReturnFormatter:
    """Get or create DirectReturnFormatter instance."""
    global _direct_formatter
    if _direct_formatter is None:
        _direct_formatter = DirectReturnFormatter()
    return _direct_formatter


def _extract_search_results_from_tool_results(
    tool_results: List[ToolResult]
) -> Optional[List[Dict[str, Any]]]:
    """
    도구 결과에서 검색 결과(enriched_results) 추출.

    Args:
        tool_results: 실행된 도구 결과 리스트

    Returns:
        enriched_results 리스트 또는 None
    """
    for result in tool_results:
        if not result.get("success"):
            continue

        metadata = result.get("metadata", {})
        if not metadata:
            continue

        # unified_search 또는 vector_search 결과에서 individual_results 추출
        individual_results = metadata.get("individual_results")
        if individual_results:
            return individual_results

    return None


def _should_use_direct_mode(
    tool_results: List[ToolResult],
    task: str,
    context: AgentContext,
    response_mode: ResponseMode = ResponseMode.HYBRID
) -> tuple[bool, Optional[List[Dict[str, Any]]], Optional[HybridModeDecision]]:
    """
    Direct 모드 사용 여부 결정.

    Args:
        tool_results: 도구 실행 결과
        task: 사용자 쿼리
        context: 에이전트 컨텍스트
        response_mode: 응답 모드 설정

    Returns:
        (use_direct, search_results, decision)
        - use_direct: Direct 모드 사용 여부
        - search_results: 검색 결과 (Direct 모드일 때)
        - decision: 하이브리드 모드 결정 정보
    """
    # 명시적 LLM 모드면 스킵
    if response_mode == ResponseMode.LLM:
        return False, None, None

    # 검색 결과 추출
    search_results = _extract_search_results_from_tool_results(tool_results)

    # ================================================================
    # 검색 결과 없음 → Direct 모드로 "정보 없음" 반환 (할루시네이션 방지)
    # LLM에게 맡기면 일반 지식으로 답변할 수 있으므로 강제로 Direct 모드 사용
    # ================================================================
    if not search_results:
        logger.info("[HybridMode] No search results - forcing Direct mode to prevent hallucination")
        decision = HybridModeDecision(
            use_direct=True,
            reason="no_results",
            confidence=0.0,
            top_score=0.0,
            result_count=0
        )
        return True, [], decision  # 빈 리스트 반환 (None 대신)

    # 명시적 Direct 모드
    if response_mode == ResponseMode.DIRECT:
        decision = HybridModeDecision(
            use_direct=True,
            reason="explicit_direct_mode",
            confidence=1.0,
            top_score=search_results[0].get("rrf_score", 0) if search_results else 0,
            result_count=len(search_results)
        )
        return True, search_results, decision

    # 하이브리드 모드: 자동 결정
    formatter = _get_direct_formatter()
    decision = formatter.decide_mode(search_results, task)

    logger.info(
        f"[HybridMode] Decision: use_direct={decision.use_direct}, "
        f"reason={decision.reason}, confidence={decision.confidence:.2f}, "
        f"top_score={decision.top_score:.4f}, results={decision.result_count}"
    )

    return decision.use_direct, search_results, decision


def _format_direct_response(
    search_results: List[Dict[str, Any]],
    task: str,
    context: AgentContext,
    decision: Optional[HybridModeDecision] = None
) -> str:
    """
    Direct 모드로 검색 결과 포맷팅.

    Args:
        search_results: 검색 결과
        task: 사용자 쿼리
        context: 에이전트 컨텍스트
        decision: 하이브리드 모드 결정 정보

    Returns:
        포맷팅된 응답 문자열
    """
    formatter = _get_direct_formatter()
    language = context.language or "ko"

    # ================================================================
    # Special Case: 결과 없음 또는 매우 낮은 점수 → "정보 없음" 메시지
    # 할루시네이션을 방지하기 위해 명확하게 "없음"으로 응답
    # ================================================================
    if decision and decision.reason in ("no_results", "very_low_score"):
        not_found_messages = {
            "ko": f"죄송합니다. **\"{task}\"**에 대한 정보를 지식 베이스에서 찾을 수 없습니다.\n\n다른 키워드로 다시 검색해 주세요.",
            "en": f"Sorry, I couldn't find information about **\"{task}\"** in the knowledge base.\n\nPlease try searching with different keywords.",
            "ja": f"申し訳ございませんが、**「{task}」**に関する情報はナレッジベースに見つかりませんでした。\n\n別のキーワードで再検索してください。"
        }
        return not_found_messages.get(language, not_found_messages["en"])

    # 높은 신뢰도 또는 단일 결과면 컴팩트 포맷
    if decision and (decision.reason in ("single_high_match", "error_code_match") or
                     (decision.result_count == 1 and decision.confidence > 0.7)):
        return formatter.format_compact(
            search_results,
            language=language,
            query=task,
            max_results=2
        )

    # 일반 포맷
    return formatter.format(
        search_results,
        language=language,
        query=task,
        include_score=False,  # 사용자에게는 점수 숨김
        highlight_keywords=True
    )


# ============================================================================
# Language Adaptation Prompt for Direct Mode
# 검색 결과를 사용자 언어로 적응 (정보 추가 금지)
# ============================================================================
LANGUAGE_ADAPTATION_PROMPT = """You are a STRICT TRANSLATOR. Your ONLY job is to translate the search results to {language}.

## 🚨🚨🚨 ABSOLUTE PROHIBITION - READ CAREFULLY 🚨🚨🚨

**YOU MUST NOT:**
- ❌ Add ANY information not explicitly written in the search results
- ❌ Explain, elaborate, or expand on the content
- ❌ Add examples that are not in the search results
- ❌ Infer or deduce information
- ❌ Add options, parameters, or details not mentioned
- ❌ Complete truncated sentences with guessed content

**YOU MUST:**
- ✅ Translate ONLY what is written in the search results
- ✅ If content is truncated (ends with ...), keep it truncated
- ✅ Preserve technical terms (dsmigin, EBCDIC, ASCII, SOSI, etc.)
- ✅ If unsure about translation, keep the original term

## VERIFICATION BEFORE OUTPUT
Ask yourself: "Is EVERY word in my output directly from the search results?"
If NO → DELETE that content immediately.

## Language: {language}
- ko = Korean (한국어)
- en = English
- ja = Japanese (日本語)

## User Question:
{query}

## Search Results (TRANSLATE ONLY THIS - ADD NOTHING):
{search_results}

## Output Format:
Translate the above content to {language}. Do NOT add source citations - they will be added automatically by the system.

REMEMBER: You are a TRANSLATOR, not an expert. DO NOT add your knowledge. DO NOT generate document IDs or source references."""


async def _adapt_language_with_llm_stream(
    search_results: List[Dict[str, Any]],
    query: str,
    language: str,
    llm_adapter,
    decision: Optional[HybridModeDecision] = None
) -> AsyncGenerator[str, None]:
    """
    검색 결과를 LLM을 통해 사용자 언어로 적응하여 스트리밍.

    할루시네이션 방지:
    - 검색 결과만 사용하도록 엄격한 프롬프트 적용
    - 정보 추가 금지

    Args:
        search_results: 검색 결과 리스트
        query: 사용자 쿼리
        language: 대상 언어 (ko, en, ja)
        llm_adapter: LLM 어댑터
        decision: 하이브리드 모드 결정 정보

    Yields:
        적응된 응답 텍스트 청크
    """
    # 검색 결과가 없으면 "정보 없음" 메시지 반환
    if not search_results or (decision and decision.reason in ("no_results", "very_low_score")):
        not_found = {
            "ko": f"죄송합니다. **\"{query}\"**에 대한 정보를 지식 베이스에서 찾을 수 없습니다.",
            "en": f"Sorry, I couldn't find information about **\"{query}\"** in the knowledge base.",
            "ja": f"申し訳ございませんが、**「{query}」**に関する情報はナレッジベースに見つかりませんでした。"
        }
        yield not_found.get(language, not_found["en"])
        return

    # 검색 결과를 텍스트로 포맷
    results_text = []
    for i, result in enumerate(search_results, 1):
        source = result.get("source", {})
        content = result.get("content", "")
        doc_name = source.get("document_name", "Unknown")
        page = source.get("page_start", "")
        section = source.get("section_title", "")

        result_entry = f"### Result {i}\n"
        result_entry += f"- Document: {doc_name}\n"
        if page:
            result_entry += f"- Page: {page}\n"
        if section:
            result_entry += f"- Section: {section}\n"
        result_entry += f"- Content:\n{content}\n"
        results_text.append(result_entry)

    formatted_results = "\n".join(results_text)

    # 언어 이름 매핑
    lang_names = {"ko": "Korean", "en": "English", "ja": "Japanese"}
    lang_name = lang_names.get(language, "English")

    # 프롬프트 생성
    prompt = LANGUAGE_ADAPTATION_PROMPT.format(
        language=lang_name,
        query=query,
        search_results=formatted_results
    )

    # LLM 호출 (스트리밍)
    try:
        messages = [{"role": "user", "content": prompt}]

        # 스트리밍 지원 여부 확인
        if hasattr(llm_adapter, 'generate_stream'):
            async for chunk in llm_adapter.generate_stream(messages=messages, tools=None):
                if isinstance(chunk, dict) and "content" in chunk:
                    yield chunk["content"]
                elif isinstance(chunk, str):
                    yield chunk
        else:
            # 스트리밍 미지원 시 일반 호출
            response = await llm_adapter.generate(messages=messages, tools=None)
            content = response.get("content", "")
            # 청크 단위로 분할하여 yield
            chunk_size = 50
            for i in range(0, len(content), chunk_size):
                yield content[i:i + chunk_size]

        # ================================================================
        # PROGRAMMATIC CITATIONS: Append actual source citations
        # This prevents LLM hallucination of document IDs
        # ================================================================
        citation_labels = {"ko": "\n\n📚 출처:", "en": "\n\n📚 Sources:", "ja": "\n\n📚 出典:"}
        citation_header = citation_labels.get(language, citation_labels["en"])
        yield citation_header

        for i, result in enumerate(search_results[:3], 1):
            source = result.get("source", {})
            doc_name = source.get("document_name") or result.get("doc_name") or source.get("doc_id", "Unknown")
            page = source.get("page_start") or result.get("page_number", "")
            doc_id = source.get("doc_id") or result.get("doc_id", "")

            # Build citation line with actual data
            citation_line = f"\n- {doc_name}"
            if page:
                citation_line += f" (p.{page})"
            if doc_id:
                citation_line += f" [{doc_id}]"
            yield citation_line

    except Exception as e:
        logger.error(f"[LanguageAdapt] LLM call failed: {e}")
        # 폴백: 원본 검색 결과 반환
        formatter = _get_direct_formatter()
        fallback = formatter.format(search_results, language=language, query=query)
        yield fallback


async def _adapt_language_with_llm(
    search_results: List[Dict[str, Any]],
    query: str,
    language: str,
    llm_adapter,
    decision: Optional[HybridModeDecision] = None
) -> str:
    """
    검색 결과를 LLM을 통해 사용자 언어로 적응 (non-streaming 버전).

    Args:
        search_results: 검색 결과 리스트
        query: 사용자 쿼리
        language: 대상 언어 (ko, en, ja)
        llm_adapter: LLM 어댑터
        decision: 하이브리드 모드 결정 정보

    Returns:
        적응된 응답 텍스트
    """
    # 스트리밍 버전을 사용하여 전체 응답 수집
    chunks = []
    async for chunk in _adapt_language_with_llm_stream(
        search_results, query, language, llm_adapter, decision
    ):
        chunks.append(chunk)
    return "".join(chunks)


async def _stream_images_from_metadata(
    metadata: Dict[str, Any],
    max_images: int = 5
) -> AsyncGenerator[AgentStreamChunk, None]:
    """
    Yield image chunks from tool result metadata.

    Checks for image_urls in metadata and fetches binary data from the repository.
    Used by adaptive_search tool to stream related document images.
    """
    if not metadata:
        return

    image_urls = metadata.get("image_urls", [])
    if not image_urls:
        return

    try:
        from ..core.deps import get_postgres_pool
        from ..infrastructure.postgres.image_repository import PostgresImageRepository

        pool = await get_postgres_pool()
        image_repo = PostgresImageRepository(pool)

        for url in image_urls[:max_images]:
            # Extract image_id from URL: /api/v1/documents/adaptive/images/{image_id}/raw
            parts = url.strip('/').split('/')
            if len(parts) >= 2 and parts[-1] == 'raw':
                image_id = parts[-2]
            else:
                continue

            try:
                # Fetch image data
                image_data = await image_repo.get_image(image_id)
                if not image_data or not image_data.get("image_data"):
                    continue

                # Encode binary to base64
                binary_data = image_data["image_data"]
                if isinstance(binary_data, memoryview):
                    binary_data = bytes(binary_data)
                b64_data = base64.b64encode(binary_data).decode('utf-8')

                mime_type = image_data.get("mime_type", "image/png")
                data_url = f"data:{mime_type};base64,{b64_data}"

                yield AgentStreamChunk(
                    chunk_type="image",
                    metadata={
                        "image_id": image_id,
                        "document_id": image_data.get("document_id", ""),
                        "page_number": image_data.get("page_number"),
                        "description": image_data.get("description", ""),
                        "figure_caption": image_data.get("figure_caption", ""),
                        "alt_text": image_data.get("alt_text", ""),
                        "width": image_data.get("width"),
                        "height": image_data.get("height"),
                        "mime_type": mime_type,
                        "data": data_url,
                    }
                )
                logger.debug(f"[Executor] Streamed image: {image_id}")

            except Exception as img_err:
                logger.warning(f"[Executor] Failed to stream image {image_id}: {img_err}")
                continue

    except Exception as e:
        logger.warning(f"[Executor] Failed to stream images: {e}")


def _check_for_general_knowledge_violation(
    answer: str,
    tool_results: List[ToolResult],
    language: str = "en"
) -> tuple[bool, str]:
    """
    Check if the answer contains general knowledge that wasn't in tool results.

    This is a post-execution guardrail to catch cases where the LLM ignores
    the system constraints and answers from training data.

    Args:
        answer: The generated answer
        tool_results: Results from tool executions
        language: User's language preference

    Returns:
        Tuple of (is_violation, corrected_answer)
    """
    if not answer:
        return False, answer

    answer_lower = answer.lower()

    # Common violation patterns - direct factual answers to general knowledge
    general_knowledge_patterns = [
        # Geography - capital cities (direct answers)
        ("capital of france", "paris"),
        ("capital of japan", "tokyo"),
        ("capital of germany", "berlin"),
        ("capital of italy", "rome"),
        ("capital of spain", "madrid"),
        ("capital of china", "beijing"),
        ("capital of korea", "seoul"),
        ("수도", "파리"),  # Korean capital questions
        ("수도", "도쿄"),
        ("首都", "パリ"),  # Japanese capital questions
        ("首都", "東京"),
        # Famous people
        ("who is", "was born"),
        ("who invented", "invented by"),
        # Historical facts
        ("when did", "in "),
        ("year of", "in "),
    ]

    # Check if any tool returned useful content (not just errors/not found)
    has_useful_tool_results = False
    for result in tool_results:
        if result.get("success") and result.get("output"):
            output = str(result["output"]).lower()
            # Check if it's a real result, not a "not found" message
            if (len(output) > 100 and
                "not found" not in output and
                "no results" not in output and
                "no relevant" not in output and
                "찾을 수 없" not in output):
                has_useful_tool_results = True
                break

    # Check for violation indicators in the answer
    violation_indicators = [
        "well-known fact",
        "as everyone knows",
        "common knowledge",
        "generally known",
        "widely known",
        "it's a fact that",
        "i can tell you that",
        "i know that",
        "without further searching",
        "from general knowledge",
        "general knowledge",
        "provide you with the answer directly",
        "provide the answer directly",
        "answer directly",
        "i'll provide",
        "i will provide",
        "i can provide",
        "잘 알려진",  # well-known in Korean
        "일반적으로",  # generally in Korean
        "一般的に",  # generally in Japanese
        "issue connecting to",  # database connection issue excuse
        "connection problem",
        "however, i can",  # transitional excuse to use general knowledge
        "however i can",
    ]

    has_violation_indicator = any(ind in answer_lower for ind in violation_indicators)

    # If no useful tool results AND answer has violation indicators, it's a violation
    if not has_useful_tool_results and has_violation_indicator:
        logger.warning("[ResponseValidator] Detected general knowledge violation - replacing response")
        return True, get_insufficient_info_response(language)

    # Check specific patterns (e.g., answering "Paris" when asked about capital)
    for pattern_question, pattern_answer in general_knowledge_patterns:
        if pattern_question in answer_lower and pattern_answer in answer_lower:
            # Double check - was this info in the tool results?
            found_in_results = False
            for result in tool_results:
                if result.get("success") and result.get("output"):
                    if pattern_answer in str(result["output"]).lower():
                        found_in_results = True
                        break

            if not found_in_results and not has_useful_tool_results:
                logger.warning(f"[ResponseValidator] Detected unsourced fact ({pattern_answer}) - replacing response")
                return True, get_insufficient_info_response(language)

    # Final check: ALWAYS check for capital city answers - these are clear general knowledge
    # This runs regardless of tool results since capital cities are common violations
    capital_cities = [
        ("france", "paris"), ("japan", "tokyo"), ("germany", "berlin"),
        ("italy", "rome"), ("spain", "madrid"), ("china", "beijing"),
        ("korea", "seoul"), ("uk", "london"), ("usa", "washington"),
        ("canada", "ottawa"), ("australia", "canberra"), ("brazil", "brasilia"),
        ("프랑스", "파리"), ("일본", "도쿄"), ("독일", "베를린"),
        ("フランス", "パリ"), ("日本", "東京"), ("ドイツ", "ベルリン"),
        ("russia", "moscow"), ("india", "new delhi"), ("netherlands", "amsterdam"),
    ]
    for country, capital in capital_cities:
        if country in answer_lower and capital in answer_lower:
            # Check if the capital was actually found in tool results
            capital_in_results = False
            for result in tool_results:
                if result.get("success") and result.get("output"):
                    output_lower = str(result["output"]).lower()
                    # Must be a substantial match - capital should be in actual content
                    if capital in output_lower and len(output_lower) > 200:
                        capital_in_results = True
                        break
            if not capital_in_results:
                logger.warning(f"[ResponseValidator] Detected capital city answer ({capital}) - blocking")
                return True, get_insufficient_info_response(language)

    return False, answer


class MaxStepsExceeded(Exception):
    """Raised when agent exceeds maximum steps"""
    pass


class DoomLoopDetected(Exception):
    """Raised when agent is stuck in a doom loop"""
    pass


# ============================================================================
# STRUCTURED ANSWER STREAMING: ChatGPT-style block-based output
# ============================================================================

async def _stream_structured_answer(
    answer: StructuredAnswer,
    delay: float = 0.05
) -> AsyncGenerator[AgentStreamChunk, None]:
    """
    Stream a structured answer as individual blocks.

    Args:
        answer: StructuredAnswer with blocks to stream
        delay: Delay between blocks for UX

    Yields:
        AgentStreamChunk for each block
    """
    total_blocks = len(answer.blocks)

    # Start notification
    yield AgentStreamChunk(
        chunk_type="answer_start",
        metadata={
            "total_blocks": total_blocks,
            "confidence": answer.confidence,
            "language": answer.language,
            "intent": answer.metadata.get("intent") if answer.metadata else None
        }
    )

    # Stream each block
    for i, block in enumerate(answer.blocks):
        yield AgentStreamChunk(
            chunk_type="answer_block",
            answer_block=block,
            block_index=i,
            total_blocks=total_blocks
        )
        await asyncio.sleep(delay)

    # Completion notification
    yield AgentStreamChunk(
        chunk_type="answer_complete",
        metadata={
            "total_blocks": total_blocks,
            "confidence": answer.confidence
        }
    )


async def _build_and_stream_structured_answer(
    search_results: List[Dict[str, Any]],
    query: str,
    language: str,
    sources: List[Dict[str, Any]]
) -> AsyncGenerator[AgentStreamChunk, None]:
    """
    Build structured answer from search results and stream it.

    Args:
        search_results: List of search result dictionaries
        query: User's original query
        language: Response language
        sources: Source list for citation

    Yields:
        AgentStreamChunk for structured answer
    """
    try:
        from ..services.answer_builder_service import get_answer_builder_service

        builder = get_answer_builder_service()

        # Build structured answer
        answer = await builder.build_answer(
            query=query,
            search_results=search_results,
            language=language
        )

        logger.info(
            f"[StructuredAnswer] Built answer with {len(answer.blocks)} blocks, "
            f"confidence={answer.confidence:.2f}"
        )

        # Stream the structured answer
        async for chunk in _stream_structured_answer(answer):
            yield chunk

        # Also yield the markdown version for backward compatibility
        markdown_content = answer.to_markdown()
        yield AgentStreamChunk(
            chunk_type="text",
            content=markdown_content,
            metadata={"structured_fallback": True}
        )

    except Exception as e:
        logger.error(f"[StructuredAnswer] Failed to build structured answer: {e}")
        # Fall back to sources-based response
        yield AgentStreamChunk(
            chunk_type="error",
            content=f"Structured answer generation failed: {str(e)}"
        )


class AgentExecutor:
    """
    Executes agent tasks using the ReAct loop.

    The ReAct loop:
    1. Think: Agent reasons about the task and decides what to do
    2. Act: Execute tool calls if any
    3. Observe: Process tool results
    4. Repeat until task is complete or max steps reached
    """

    DOOM_LOOP_THRESHOLD = 3  # Consecutive identical tool calls

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        permission_manager: Optional[PermissionManager] = None,
        llm_adapter = None
    ):
        self.tool_registry = tool_registry or get_tool_registry()
        self.permission_manager = permission_manager or get_permission_manager()
        self._llm_adapter = llm_adapter

    @property
    def llm_adapter(self):
        """Lazy load LLM adapter (NIM primary, Ollama fallback)"""
        if self._llm_adapter is None:
            # Try LLM adapter first (NIM primary, Ollama fallback)
            try:
                from .adapters.ollama_adapter import get_llm_adapter
                self._llm_adapter = get_llm_adapter()
                backend_info = self._llm_adapter.get_backend_info()
                logger.info(f"Using LLM adapter: backend={backend_info['backend']}, model={backend_info['model']}")
            except ImportError as e:
                logger.warning(f"LLM adapter import failed: {e}")
                # Fallback to LangChain adapter
                try:
                    from ..adapters.langchain.llm_adapter import get_langchain_llm
                    self._llm_adapter = get_langchain_llm()
                    logger.info("Using LangChain LLM adapter")
                except ImportError as e2:
                    logger.warning(f"LangChain adapter import failed: {e2}")
                    logger.warning("No LLM adapter available")
            except Exception as e:
                logger.error(f"Unexpected error loading LLM adapter: {e}")
        return self._llm_adapter

    async def run(
        self,
        agent: BaseAgent,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """
        Execute a task using the ReAct loop.

        Args:
            agent: The agent to execute with
            task: The user's task or question
            context: Execution context

        Returns:
            AgentResult with answer and metadata
        """
        start_time = time.time()

        # Store original task in context for query validation in tools
        # This prevents LLM from corrupting/expanding queries in tool calls
        if context.metadata is None:
            context.metadata = {}
        context.metadata['original_query'] = task
        logger.info(f"[Executor.run] Stored original_query: {task[:50]}...")

        # ========================================================================
        # MASTER SYSTEM CONSTRAINT INJECTION (HIGHEST PRIORITY)
        # This constraint MUST be prepended to ALL agent prompts
        # ========================================================================
        base_agent_prompt = agent.system_prompt
        system_prompt = build_constrained_system_prompt(base_agent_prompt)
        logger.info(f"[Executor] Master system constraint injected for {agent.agent_type.value} agent")

        # Validate constraint is properly applied
        enforcer = get_constraint_enforcer()
        try:
            enforcer.validate_before_execution(
                agent_type=agent.agent_type.value,
                system_prompt=system_prompt,
                context={
                    "user_id": context.user_id,
                    "session_id": context.session_id
                }
            )
        except Exception as e:
            logger.critical(f"[Executor] Constraint validation failed: {e}")
            # Still proceed but log the violation
            log_compliance_violation(
                ComplianceViolationType.CONSTRAINT_MISSING,
                agent.agent_type.value,
                user_id=context.user_id,
                session_id=context.session_id,
                details={"error": str(e)}
            )

        # Build system prompt with language preference - INJECT AT BEGINNING for stronger effect
        if context.language and context.language != "auto":
            language_names = {"en": "English", "ko": "Korean", "ja": "Japanese"}
            lang_name = language_names.get(context.language, context.language)
            # Language names in their own language for stronger emphasis
            lang_native = {"en": "English", "ko": "한국어", "ja": "日本語"}
            native_name = lang_native.get(context.language, lang_name)

            # PREPEND language instruction at the BEGINNING of system prompt for maximum effect
            language_instruction = f"""🔴 MANDATORY RESPONSE LANGUAGE: {lang_name} ({native_name})

You MUST respond ONLY in {lang_name} ({native_name}).
This is the user's configured UI language setting - NOT negotiable.
The query language does NOT determine your response language.
IGNORE the language of the user's question. ALWAYS respond in {lang_name}.

Exception: ONLY switch language if user EXPLICITLY writes:
- "Answer in English" / "영어로 답변해줘" / "英語で答えて"
- "한국어로 답변해줘" / "Answer in Korean" / "韓国語で答えて"
- "日本語で答えて" / "일본어로 답변해줘" / "Answer in Japanese"

═══════════════════════════════════════════════════════════════

"""
            system_prompt = language_instruction + system_prompt
            logger.info(f"[Executor.run] Language instruction PREPENDED: {lang_name}")

        # Add UI context if available (context-aware AI)
        if context.metadata.get('ui_context_prompt'):
            ui_context_prompt = context.metadata['ui_context_prompt']
            system_prompt += f"""

CURRENT UI CONTEXT:
{ui_context_prompt}

Use this context to provide more relevant and context-aware responses. If the user is viewing specific content, consider that context when answering."""

        # Build user message with optional file context
        user_message = task
        if context.file_context:
            # Truncate file context to prevent LLM context overflow
            truncated_file_context = _truncate_file_context(context.file_context)

            # Add strong instruction to system prompt for file context priority
            system_prompt += """

CRITICAL INSTRUCTION - ATTACHED FILE CONTEXT:
The user has attached file(s) for reference. You MUST:
1. FIRST search the attached file context for the answer
2. If the answer is found in the attached context, respond directly WITHOUT using any tools
3. ONLY use tools (vector_search, document_read, etc.) if the information is NOT in the attached context
4. When answering from attached context, mention "첨부된 문서에 따르면" or "According to the attached document"
"""
            user_message = f"""[ATTACHED FILE CONTEXT - PRIMARY REFERENCE]
{truncated_file_context}
[END ATTACHED FILE CONTEXT]

IMPORTANT: Answer from the attached file context above if possible. Only use tools if the answer is not in the attached context.

User Query: {task}"""
            logger.info(f"[Executor] File context attached (original: {len(context.file_context)} chars, truncated: {len(truncated_file_context)} chars)")

        # Handle URL context (fetched web content)
        if context.url_context:
            system_prompt += """

CRITICAL INSTRUCTION - URL CONTENT CONTEXT:
The user has provided a URL and its content has been fetched for reference. You MUST:
1. FIRST search the URL content for the answer
2. If the answer is found in the URL content, respond directly WITHOUT using any tools
3. ONLY use tools (vector_search, document_read, etc.) if the information is NOT in the URL content
4. When answering from URL content, mention the source URL
"""
            url_source = context.url_source or "provided URL"
            # Truncate URL context to prevent LLM context overflow
            truncated_url_context = _truncate_file_context(context.url_context)

            if context.file_context:
                # Both file and URL context
                user_message = user_message.replace(
                    "[END ATTACHED FILE CONTEXT]",
                    f"""[END ATTACHED FILE CONTEXT]

[URL CONTENT FROM: {url_source}]
{truncated_url_context}
[END URL CONTENT]"""
                )
            else:
                # Only URL context
                user_message = f"""[URL CONTENT FROM: {url_source}]
{truncated_url_context}
[END URL CONTENT]

IMPORTANT: Answer from the URL content above if possible. Only use tools if the answer is not in the URL content.

User Query: {task}"""
            logger.info(f"[Executor] URL context attached (original: {len(context.url_context)} chars, truncated: {len(truncated_url_context)} chars) from {url_source}")

        # Handle Summary Context (Two-Stage Retrieval - error codes, glossary terms, commands, APIs, products)
        summary_error = context.metadata.get('summary_error_context')
        summary_term = context.metadata.get('summary_term_context')
        summary_cmd = context.metadata.get('summary_command_context')
        summary_api = context.metadata.get('summary_api_context')
        summary_product = context.metadata.get('summary_product_context')
        if summary_error or summary_term or summary_cmd or summary_api or summary_product:
            summary_parts = []
            if summary_product:
                summary_parts.append(summary_product)
            if summary_error:
                summary_parts.append(summary_error)
            if summary_term:
                summary_parts.append(summary_term)
            if summary_cmd:
                summary_parts.append(summary_cmd)
            if summary_api:
                summary_parts.append(summary_api)
            summary_context = "\n\n".join(summary_parts)

            system_prompt += """

SUMMARY CONTEXT (Two-Stage Retrieval):
Pre-searched context from manual summaries is provided below. Use this to:
1. Understand product overviews and available components
2. Understand error codes and their meanings
3. Understand technical terms and abbreviations
4. Understand commands/utilities and their usage
5. Understand API functions and their prototypes
6. Enrich your vector_search queries with this context
"""
            # Append summary context to user message
            if "[END ATTACHED FILE CONTEXT]" in user_message:
                user_message = user_message.replace(
                    "User Query:",
                    f"""[SUMMARY CONTEXT]
{summary_context}
[/SUMMARY CONTEXT]

User Query:"""
                )
            elif "[END URL CONTENT]" in user_message:
                user_message = user_message.replace(
                    "User Query:",
                    f"""[SUMMARY CONTEXT]
{summary_context}
[/SUMMARY CONTEXT]

User Query:"""
                )
            else:
                user_message = f"""[SUMMARY CONTEXT]
{summary_context}
[/SUMMARY CONTEXT]

{task}"""
            logger.info(f"[Executor] Summary context attached ({len(summary_context)} chars)")

        # Initialize messages with system prompt and user task
        messages: List[AgentMessage] = [
            AgentMessage(role=MessageRole.SYSTEM, content=system_prompt),
            AgentMessage(role=MessageRole.USER, content=user_message)
        ]

        # Add conversation history
        for hist in context.conversation_history[-5:]:
            if "question" in hist:
                messages.insert(-1, AgentMessage(
                    role=MessageRole.USER,
                    content=hist["question"]
                ))
            if "answer" in hist:
                messages.insert(-1, AgentMessage(
                    role=MessageRole.ASSISTANT,
                    content=hist["answer"]
                ))

        # Get available tools for this agent
        available_tools = self.tool_registry.get_tools_for_agent(agent.agent_type)
        tool_definitions = [tool.get_definition() for tool in available_tools]

        tool_calls_made: List[ToolCall] = []
        tool_results: List[ToolResult] = []
        recent_tool_calls: List[Dict] = []  # For doom loop detection

        step = 0
        final_answer = ""

        while step < context.max_steps:
            step += 1
            logger.debug(f"Step {step}/{context.max_steps}")

            # Think: Get LLM response
            # For RAG agents on step 1, force unified_search tool call
            current_tool_choice = "auto"
            if step == 1 and agent.agent_type.value == "rag":
                # Force specific tool call to prevent hallucination
                current_tool_choice = {"type": "function", "function": {"name": "unified_search"}}
                logger.info(f"[Executor] RAG agent step 1: forcing unified_search")

            response = await self._call_llm(messages, tool_definitions, tool_choice=current_tool_choice)

            if response is None:
                final_answer = "I encountered an error while processing your request."
                break

            # Add assistant message
            messages.append(response)

            # Check if we have tool calls
            if response.tool_calls:
                # Doom loop detection
                for tool_call in response.tool_calls:
                    call_signature = {
                        "tool": tool_call.tool_name,
                        "args": json.dumps(tool_call.arguments, sort_keys=True)
                    }
                    recent_tool_calls.append(call_signature)

                    # Check for repeated calls
                    if len(recent_tool_calls) >= self.DOOM_LOOP_THRESHOLD:
                        last_n = recent_tool_calls[-self.DOOM_LOOP_THRESHOLD:]
                        if all(c == last_n[0] for c in last_n):
                            logger.warning(f"Doom loop detected: {tool_call.tool_name}")
                            # Break the loop
                            final_answer = (
                                f"I noticed I was repeating the same action. "
                                f"Based on the information gathered: {response.content or 'Unable to provide answer.'}"
                            )
                            break

                # Skip tool execution if doom loop was detected
                if final_answer:
                    break

                # Act: Execute tool calls
                for tool_call in response.tool_calls:
                    tool_calls_made.append(tool_call)

                    # Check permissions
                    if not self.permission_manager.check_permission(
                        tool_call.tool_name,
                        agent.agent_type,
                        context.user_id
                    ):
                        logger.warning(f"[Executor] Permission denied for tool: {tool_call.tool_name}")
                        result = ToolResult(
                            success=False,
                            output="",
                            error=f"Permission denied for tool: {tool_call.tool_name}",
                            metadata=None
                        )
                    else:
                        # Execute tool
                        result = await self._execute_tool(tool_call, context)

                    tool_results.append(result)

                    # Add tool result message (truncate to prevent context overflow)
                    tool_content = result["output"] if result["success"] else f"Error: {result['error']}"
                    messages.append(AgentMessage(
                        role=MessageRole.TOOL,
                        content=_truncate_tool_result(tool_content),
                        tool_call_id=tool_call.call_id,
                        name=tool_call.tool_name
                    ))

                # Check if we broke out due to doom loop
                if final_answer:
                    break

                # ================================================================
                # HYBRID MODE: Check if we should use Direct Return
                # For RAG agents, skip LLM synthesis if search results are good
                # ================================================================
                if agent.agent_type.value == "rag" and step == 1:
                    response_mode = ResponseMode(
                        context.metadata.get("response_mode", "hybrid")
                    )
                    use_direct, search_results, decision = _should_use_direct_mode(
                        tool_results, task, context, response_mode
                    )

                    # Changed: search_results는 빈 리스트일 수 있음 (no_results 케이스)
                    if use_direct and decision is not None:
                        logger.info(
                            f"[Executor] Using DIRECT mode with LLM language adaptation "
                            f"(reason={decision.reason}, confidence={decision.confidence:.2f}, lang={context.language})"
                        )
                        # LLM을 통한 언어 적응 (검색 결과만 사용)
                        final_answer = await _adapt_language_with_llm(
                            search_results=search_results or [],
                            query=task,
                            language=context.language or "ko",
                            llm_adapter=self.llm_adapter,
                            decision=decision
                        )
                        # Store decision info in metadata
                        context.metadata["hybrid_mode_decision"] = {
                            "mode": "direct_with_llm",
                            "reason": decision.reason,
                            "confidence": decision.confidence,
                            "top_score": decision.top_score
                        }
                        break
            else:
                # No tool calls - agent has finished reasoning
                # ================================================================
                # ANTI-HALLUCINATION: RAG agents MUST use search tools
                # If step 1 has no tool calls, the LLM is hallucinating
                # ================================================================
                if step == 1 and agent.agent_type.value == "rag" and len(tool_calls_made) == 0:
                    logger.warning(f"[Executor] HALLUCINATION DETECTED: RAG agent responded without using search tools")
                    # Force "not found" response based on language
                    lang = context.language or "en"
                    if lang == "ja":
                        final_answer = f"申し訳ございませんが、「{task}」に関する情報はナレッジベースに見つかりませんでした。"
                    elif lang == "ko":
                        final_answer = f"죄송합니다. 「{task}」에 대한 정보를 지식 베이스에서 찾을 수 없습니다."
                    else:
                        final_answer = f"I'm sorry, but I couldn't find information about \"{task}\" in the knowledge base."
                else:
                    final_answer = response.content or "I couldn't generate a response."
                break

        execution_time = time.time() - start_time

        # Extract sources from tool results
        sources = self._extract_sources(tool_results)

        # ========================================================================
        # POST-EXECUTION VALIDATION: Check for general knowledge violations
        # ========================================================================
        is_violation, validated_answer = _check_for_general_knowledge_violation(
            final_answer,
            tool_results,
            language=context.language or "en"
        )
        if is_violation:
            logger.warning(f"[Executor] General knowledge violation detected and corrected for {agent.agent_type.value} agent")
            log_compliance_violation(
                ComplianceViolationType.GENERAL_KNOWLEDGE_DETECTED,
                agent.agent_type.value,
                user_id=context.user_id,
                session_id=context.session_id,
                details={"original_answer_preview": final_answer[:200]}
            )
            final_answer = validated_answer

        return AgentResult(
            answer=final_answer,
            agent_type=agent.agent_type,
            steps=step,
            tool_calls=tool_calls_made,
            tool_results=tool_results,
            sources=sources,
            execution_time=execution_time,
            success=True,
            metadata={
                "max_steps": context.max_steps,
                "tools_used": list(set(tc.tool_name for tc in tool_calls_made))
            }
        )

    async def stream(
        self,
        agent: BaseAgent,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        Stream execution of a task.

        Yields events as the agent thinks and acts.
        """
        start_time = time.time()

        # ========================================================================
        # MASTER SYSTEM CONSTRAINT INJECTION (HIGHEST PRIORITY)
        # This constraint MUST be prepended to ALL agent prompts
        # ========================================================================
        base_agent_prompt = agent.system_prompt
        system_prompt = build_constrained_system_prompt(base_agent_prompt)
        logger.info(f"[Executor.stream] Master system constraint injected for {agent.agent_type.value} agent")

        # Validate constraint is properly applied
        enforcer = get_constraint_enforcer()
        try:
            enforcer.validate_before_execution(
                agent_type=agent.agent_type.value,
                system_prompt=system_prompt,
                context={
                    "user_id": context.user_id,
                    "session_id": context.session_id
                }
            )
        except Exception as e:
            logger.critical(f"[Executor.stream] Constraint validation failed: {e}")
            log_compliance_violation(
                ComplianceViolationType.CONSTRAINT_MISSING,
                agent.agent_type.value,
                user_id=context.user_id,
                session_id=context.session_id,
                details={"error": str(e)}
            )

        # Build system prompt with language preference - INJECT AT BEGINNING for stronger effect
        logger.debug(f"[Executor.stream] context.language = '{context.language}'")
        if context.language and context.language != "auto":
            language_names = {"en": "English", "ko": "Korean", "ja": "Japanese"}
            lang_name = language_names.get(context.language, context.language)
            # Language names in their own language for stronger emphasis
            lang_native = {"en": "English", "ko": "한국어", "ja": "日本語"}
            native_name = lang_native.get(context.language, lang_name)

            # PREPEND language instruction at the BEGINNING of system prompt for maximum effect
            language_instruction = f"""🔴 MANDATORY RESPONSE LANGUAGE: {lang_name} ({native_name})

You MUST respond ONLY in {lang_name} ({native_name}).
This is the user's configured UI language setting - NOT negotiable.
The query language does NOT determine your response language.
IGNORE the language of the user's question. ALWAYS respond in {lang_name}.

Exception: ONLY switch language if user EXPLICITLY writes:
- "Answer in English" / "영어로 답변해줘" / "英語で答えて"
- "한국어로 답변해줘" / "Answer in Korean" / "韓国語で答えて"
- "日本語で答えて" / "일본어로 답변해줘" / "Answer in Japanese"

═══════════════════════════════════════════════════════════════

"""
            system_prompt = language_instruction + system_prompt
            logger.info(f"[Executor.stream] Language instruction PREPENDED: {lang_name}")

        # Add UI context if available (context-aware AI)
        if context.metadata.get('ui_context_prompt'):
            ui_context_prompt = context.metadata['ui_context_prompt']
            system_prompt += f"""

CURRENT UI CONTEXT:
{ui_context_prompt}

Use this context to provide more relevant and context-aware responses. If the user is viewing specific content, consider that context when answering."""
            logger.debug("[Executor.stream] Added UI context to system prompt")

        # Build user message with optional file context
        user_message = task
        if context.file_context:
            # Truncate file context to prevent LLM context overflow
            truncated_file_context = _truncate_file_context(context.file_context)

            # Add strong instruction to system prompt for file context priority
            system_prompt += """

CRITICAL INSTRUCTION - ATTACHED FILE CONTEXT:
The user has attached file(s) for reference. You MUST:
1. FIRST search the attached file context for the answer
2. If the answer is found in the attached context, respond directly WITHOUT using any tools
3. ONLY use tools (vector_search, document_read, etc.) if the information is NOT in the attached context
4. When answering from attached context, mention "첨부된 문서에 따르면" or "According to the attached document"
"""
            user_message = f"""[ATTACHED FILE CONTEXT - PRIMARY REFERENCE]
{truncated_file_context}
[END ATTACHED FILE CONTEXT]

IMPORTANT: Answer from the attached file context above if possible. Only use tools if the answer is not in the attached context.

User Query: {task}"""
            logger.info(f"[Executor.stream] File context attached (original: {len(context.file_context)} chars, truncated: {len(truncated_file_context)} chars)")

        # Handle URL context (fetched web content)
        if context.url_context:
            system_prompt += """

CRITICAL INSTRUCTION - URL CONTENT CONTEXT:
The user has provided a URL and its content has been fetched for reference. You MUST:
1. FIRST search the URL content for the answer
2. If the answer is found in the URL content, respond directly WITHOUT using any tools
3. ONLY use tools (vector_search, document_read, etc.) if the information is NOT in the URL content
4. When answering from URL content, mention the source URL
"""
            url_source = context.url_source or "provided URL"
            # Truncate URL context to prevent LLM context overflow
            truncated_url_context = _truncate_file_context(context.url_context)

            if context.file_context:
                # Both file and URL context
                user_message = user_message.replace(
                    "[END ATTACHED FILE CONTEXT]",
                    f"""[END ATTACHED FILE CONTEXT]

[URL CONTENT FROM: {url_source}]
{truncated_url_context}
[END URL CONTENT]"""
                )
            else:
                # Only URL context
                user_message = f"""[URL CONTENT FROM: {url_source}]
{truncated_url_context}
[END URL CONTENT]

IMPORTANT: Answer from the URL content above if possible. Only use tools if the answer is not in the URL content.

User Query: {task}"""
            logger.info(f"[Executor.stream] URL context attached (original: {len(context.url_context)} chars, truncated: {len(truncated_url_context)} chars) from {url_source}")

        # Handle Summary Context (Two-Stage Retrieval - error codes, glossary terms, commands, APIs, products)
        summary_error = context.metadata.get('summary_error_context')
        summary_term = context.metadata.get('summary_term_context')
        summary_cmd = context.metadata.get('summary_command_context')
        summary_api = context.metadata.get('summary_api_context')
        summary_product = context.metadata.get('summary_product_context')
        if summary_error or summary_term or summary_cmd or summary_api or summary_product:
            summary_parts = []
            if summary_product:
                summary_parts.append(summary_product)
            if summary_error:
                summary_parts.append(summary_error)
            if summary_term:
                summary_parts.append(summary_term)
            if summary_cmd:
                summary_parts.append(summary_cmd)
            if summary_api:
                summary_parts.append(summary_api)
            summary_context = "\n\n".join(summary_parts)

            system_prompt += """

SUMMARY CONTEXT (Two-Stage Retrieval):
Pre-searched context from manual summaries is provided below. Use this to:
1. Understand product overviews and available components
2. Understand error codes and their meanings
3. Understand technical terms and abbreviations
4. Understand commands/utilities and their usage
5. Understand API functions and their prototypes
6. Enrich your vector_search queries with this context
"""
            # Append summary context to user message
            if "[END ATTACHED FILE CONTEXT]" in user_message:
                user_message = user_message.replace(
                    "User Query:",
                    f"""[SUMMARY CONTEXT]
{summary_context}
[/SUMMARY CONTEXT]

User Query:"""
                )
            elif "[END URL CONTENT]" in user_message:
                user_message = user_message.replace(
                    "User Query:",
                    f"""[SUMMARY CONTEXT]
{summary_context}
[/SUMMARY CONTEXT]

User Query:"""
                )
            else:
                user_message = f"""[SUMMARY CONTEXT]
{summary_context}
[/SUMMARY CONTEXT]

{task}"""
            logger.info(f"[Executor.stream] Summary context attached ({len(summary_context)} chars)")

        # Initialize messages
        messages: List[AgentMessage] = [
            AgentMessage(role=MessageRole.SYSTEM, content=system_prompt),
            AgentMessage(role=MessageRole.USER, content=user_message)
        ]

        available_tools = self.tool_registry.get_tools_for_agent(agent.agent_type)
        tool_definitions = [tool.get_definition() for tool in available_tools]

        sources = []
        tool_results: List[ToolResult] = []  # Collect for post-execution validation
        step = 0

        # Queue for status messages from tools
        status_queue: asyncio.Queue[str] = asyncio.Queue()

        # Create status callback
        async def status_callback(message: str):
            await status_queue.put(message)

        # Set up status callbacks for tools that support them
        for tool in available_tools:
            if hasattr(tool, 'set_status_callback'):
                tool.set_status_callback(status_callback)

        yield AgentStreamChunk(chunk_type="thinking", content="Analyzing your request...")

        # ========================================================================
        # RAG Analysis: Send query analysis info for UI progress modal
        # ========================================================================
        user_language = context.language if context.language and context.language != "auto" else "ko"
        query_analysis = _analyze_query_keywords(task, language=user_language)
        yield AgentStreamChunk(
            chunk_type="rag_analysis",
            content=json.dumps(query_analysis, ensure_ascii=False),
            metadata=query_analysis
        )

        # Store original task in context for query validation in tools
        # This prevents LLM from corrupting Japanese/Korean queries in tool calls
        context.metadata['original_query'] = task

        logger.info(f"Starting stream for task: {task[:50]}...")
        logger.info(f"Agent: {agent.name}, Tools: {[t.name for t in available_tools]}")
        logger.debug(f"[Executor] LLM adapter: {self.llm_adapter}")

        # ========================================================================
        # DEVELOP MODE: Execute all tools and show aggregated results
        # ========================================================================
        if is_develop_mode():
            logger.info("DEVELOP MODE: Executing all tools for analysis")

            yield AgentStreamChunk(chunk_type="status", content="[개발모드] 모든 검색 도구 실행 중...")

            # Execute all searchable tools in parallel
            develop_results = await _execute_all_tools_develop_mode(
                available_tools, task, context
            )

            # Yield individual tool results for UI
            for tool_name, result in develop_results.items():
                yield AgentStreamChunk(
                    chunk_type="tool_call",
                    tool_name=tool_name,
                    tool_input={"query": task, "top_k": 10}
                )
                count = result.get("count", 0)
                scores = result.get("scores", [])
                error = result.get("error")

                if error:
                    output_summary = f"오류: {error}"
                else:
                    score_preview = ", ".join([f"{s*100:.1f}%" for s in scores[:3]]) if scores else "N/A"
                    output_summary = f"{count}건 발견 (유사도: {score_preview})"

                yield AgentStreamChunk(
                    chunk_type="tool_result",
                    tool_name=tool_name,
                    tool_output=output_summary
                )

            # Format and stream the summary
            summary = _format_develop_mode_summary(task, develop_results)

            # Stream the summary in chunks
            chunk_size = 50
            for i in range(0, len(summary), chunk_size):
                chunk = summary[i:i + chunk_size]
                yield AgentStreamChunk(chunk_type="text", content=chunk)
                await asyncio.sleep(0.02)

            # Cleanup and finish
            for tool in available_tools:
                if hasattr(tool, 'set_status_callback'):
                    tool.set_status_callback(None)

            yield AgentStreamChunk(
                chunk_type="done",
                metadata={
                    "steps": 1,
                    "execution_time": time.time() - start_time,
                    "develop_mode": True,
                    "tools_executed": list(develop_results.keys())
                }
            )
            return

        while step < context.max_steps:
            step += 1

            # Think
            # For RAG agents on step 1, force unified_search tool call
            # Note: "required" causes 400 error on NIM/vLLM, use specific tool format instead
            current_tool_choice = "auto"
            if step == 1 and agent.agent_type.value == "rag":
                # Force specific tool call to prevent hallucination
                current_tool_choice = {"type": "function", "function": {"name": "unified_search"}}
                logger.info(f"[Executor.stream] RAG agent step 1: forcing unified_search")

            response = await self._call_llm(messages, tool_definitions, tool_choice=current_tool_choice)

            if response is None:
                # LLM connection failed - return user-friendly error message
                lang = context.language or "en"
                if lang == "ja":
                    error_msg = "申し訳ございません。AI サービスに一時的に接続できません。しばらくしてからもう一度お試しください。"
                elif lang == "ko":
                    error_msg = "죄송합니다. AI 서비스에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
                else:
                    error_msg = "Sorry, the AI service is temporarily unavailable. Please try again shortly."
                logger.error(f"[Executor.stream] LLM call failed at step {step}")
                yield AgentStreamChunk(chunk_type="text", content=error_msg)
                yield AgentStreamChunk(chunk_type="done", metadata={"llm_connection_failed": True})
                return

            messages.append(response)

            if response.tool_calls:
                # Stream tool execution
                for tool_call in response.tool_calls:
                    yield AgentStreamChunk(
                        chunk_type="tool_call",
                        tool_name=tool_call.tool_name,
                        tool_input=tool_call.arguments
                    )

                    # Execute tool (may emit status messages)
                    logger.debug(f"Calling tool: {tool_call.tool_name}")
                    result = await self._execute_tool(tool_call, context)
                    tool_results.append(result)  # Collect for validation

                    # Drain status queue and yield status messages
                    while not status_queue.empty():
                        try:
                            status_msg = status_queue.get_nowait()
                            yield AgentStreamChunk(
                                chunk_type="status",
                                content=status_msg
                            )
                        except asyncio.QueueEmpty:
                            break

                    # Extract query correction info for UI display
                    tool_result_metadata = None
                    if result.get("success") and result.get("metadata"):
                        meta = result["metadata"]
                        if meta.get("query_corrected"):
                            tool_result_metadata = {
                                "query_corrected": True,
                                "original_llm_query": meta.get("original_llm_query"),
                                "corrected_query": meta.get("corrected_query"),
                            }

                    yield AgentStreamChunk(
                        chunk_type="tool_result",
                        tool_name=tool_call.tool_name,
                        tool_output=result["output"][:500] if result["success"] else result["error"],
                        metadata=tool_result_metadata
                    )

                    # ========================================================================
                    # RAG Analysis: Send chunk structure and embedding info for search tools
                    # ========================================================================
                    if result.get("success") and tool_call.tool_name in ["adaptive_search", "vector_search", "graph_query"]:
                        # Chunk structure info
                        chunk_structure = _extract_chunk_structure(result, tool_call.tool_name)
                        yield AgentStreamChunk(
                            chunk_type="chunk_structure",
                            tool_name=tool_call.tool_name,
                            content=json.dumps(chunk_structure, ensure_ascii=False),
                            metadata=chunk_structure
                        )

                        # Embedding info
                        embedding_info = _extract_embedding_info(result, tool_call.tool_name)
                        yield AgentStreamChunk(
                            chunk_type="embedding_info",
                            tool_name=tool_call.tool_name,
                            content=json.dumps(embedding_info, ensure_ascii=False),
                            metadata=embedding_info
                        )

                    # Stream images if tool result contains image_urls (e.g., from adaptive_search)
                    if result.get("success") and result.get("metadata"):
                        async for image_chunk in _stream_images_from_metadata(result["metadata"]):
                            yield image_chunk

                    # ========================================================================
                    # Stream individual search results for expandable card display
                    # Each result is sent as a separate search_result chunk
                    # ========================================================================
                    if result.get("success") and result.get("metadata"):
                        individual_results = result["metadata"].get("individual_results", [])
                        if individual_results:
                            total = len(individual_results)
                            logger.debug(f"Streaming {total} individual search results")
                            for idx, ind_result in enumerate(individual_results):
                                yield AgentStreamChunk(
                                    chunk_type="search_result",
                                    result_index=idx + 1,
                                    result_total=total,
                                    result_title=ind_result.get("title", ""),
                                    result_content=ind_result.get("content", ""),
                                    result_images=ind_result.get("images", []),
                                    result_tables=ind_result.get("tables", []),
                                    result_source=ind_result.get("source", {}),
                                    result_score=ind_result.get("similarity", 0),
                                    metadata={
                                        "chunk_id": ind_result.get("chunk_id"),
                                        "chunk_type": ind_result.get("chunk_type"),
                                        "relations": ind_result.get("relations", {})
                                    }
                                )

                    # Check if tool result contains markdown_table - bypass LLM and output directly
                    if result["success"] and result.get("output"):
                        try:
                            tool_output_data = json.loads(result["output"])
                            if isinstance(tool_output_data, dict) and tool_output_data.get("markdown_table"):
                                markdown_table = tool_output_data["markdown_table"]
                                logger.debug("[Executor] Found markdown_table, bypassing LLM")

                                # Stream the markdown table directly
                                chunk_size = 50
                                for i in range(0, len(markdown_table), chunk_size):
                                    chunk = markdown_table[i:i + chunk_size]
                                    yield AgentStreamChunk(chunk_type="text", content=chunk)
                                    await asyncio.sleep(0.02)

                                # Clean up and finish
                                for tool in available_tools:
                                    if hasattr(tool, 'set_status_callback'):
                                        tool.set_status_callback(None)

                                yield AgentStreamChunk(
                                    chunk_type="done",
                                    metadata={
                                        "steps": step,
                                        "execution_time": time.time() - start_time,
                                        "direct_output": True
                                    }
                                )
                                return
                        except (json.JSONDecodeError, TypeError):
                            pass  # Not JSON or no markdown_table, continue normal flow

                    # Add tool result message (truncate to prevent context overflow)
                    tool_content = result["output"] if result["success"] else f"Error: {result['error']}"
                    messages.append(AgentMessage(
                        role=MessageRole.TOOL,
                        content=_truncate_tool_result(tool_content),
                        tool_call_id=tool_call.call_id,
                        name=tool_call.tool_name
                    ))

                    # Collect sources
                    if result.get("metadata") and "sources" in result["metadata"]:
                        result_sources = result["metadata"]["sources"]
                        logger.info(f"Collected {len(result_sources)} sources from {tool_call.tool_name}")
                        sources.extend(result_sources)

                # ================================================================
                # HYBRID MODE: Check if we should use Direct Return
                # For RAG agents, skip LLM synthesis if search results are good
                # ================================================================
                if agent.agent_type.value == "rag" and step == 1:
                    response_mode = ResponseMode(
                        context.metadata.get("response_mode", "hybrid")
                    )
                    use_direct, search_results, decision = _should_use_direct_mode(
                        tool_results, task, context, response_mode
                    )

                    # Changed: search_results는 빈 리스트일 수 있음 (no_results 케이스)
                    if use_direct and decision is not None:
                        # ================================================================
                        # STRUCTURED OUTPUT: ChatGPT-style block-based answer
                        # Check if structured output is requested and enabled
                        # ================================================================
                        from ..core.config import api_settings
                        use_structured = (
                            context.metadata.get("structured_output", False) and
                            getattr(api_settings, 'ENABLE_STRUCTURED_ANSWER', False)
                        )

                        if use_structured and search_results:
                            logger.info(
                                f"Using STRUCTURED OUTPUT mode (reason={decision.reason})"
                            )

                            # Stream structured answer blocks
                            async for chunk in _build_and_stream_structured_answer(
                                search_results=search_results,
                                query=task,
                                language=context.language or "ko",
                                sources=sources
                            ):
                                yield chunk

                            # Send sources
                            if sources:
                                yield AgentStreamChunk(chunk_type="sources", sources=sources)

                            # Clean up and finish
                            for tool in available_tools:
                                if hasattr(tool, 'set_status_callback'):
                                    tool.set_status_callback(None)

                            yield AgentStreamChunk(
                                chunk_type="done",
                                metadata={
                                    "steps": step,
                                    "execution_time": time.time() - start_time,
                                    "structured_output": True,
                                    "decision_reason": decision.reason,
                                    "decision_confidence": decision.confidence
                                }
                            )
                            return

                        # ================================================================
                        # FALLBACK: LLM language adaptation (existing behavior)
                        # ================================================================
                        logger.info(
                            f"Using DIRECT mode with LLM language adaptation "
                            f"(reason={decision.reason}, confidence={decision.confidence:.2f})"
                        )

                        # Start generation
                        yield AgentStreamChunk(
                            chunk_type="generation_start",
                            content="검색 결과를 분석하고 있습니다...",
                            metadata={
                                "total_sources": len(sources),
                                "mode": "direct_with_llm",
                                "decision_reason": decision.reason,
                                "target_language": context.language
                            }
                        )

                        # ================================================================
                        # LLM을 통한 언어 적응 스트리밍
                        # 검색 결과만 사용하여 사용자 언어로 답변 생성
                        # ================================================================
                        chunk_count = 0
                        async for text_chunk in _adapt_language_with_llm_stream(
                            search_results=search_results or [],
                            query=task,
                            language=context.language or "ko",
                            llm_adapter=self.llm_adapter,
                            decision=decision
                        ):
                            chunk_count += 1
                            # 진행 상태 업데이트 (매 10청크마다)
                            if chunk_count % 10 == 1:
                                yield AgentStreamChunk(
                                    chunk_type="generation_progress",
                                    content=f"답변 생성 중...",
                                    metadata={"chunks_generated": chunk_count}
                                )
                            yield AgentStreamChunk(chunk_type="text", content=text_chunk)

                        # Send sources
                        if sources:
                            yield AgentStreamChunk(chunk_type="sources", sources=sources)

                        # Clean up and finish
                        for tool in available_tools:
                            if hasattr(tool, 'set_status_callback'):
                                tool.set_status_callback(None)

                        yield AgentStreamChunk(
                            chunk_type="done",
                            metadata={
                                "steps": step,
                                "execution_time": time.time() - start_time,
                                "hybrid_mode": "direct_with_llm",
                                "decision_reason": decision.reason,
                                "decision_confidence": decision.confidence
                            }
                        )
                        return

            else:
                # Stream final answer
                answer = response.content or ""

                # ========================================================================
                # ANTI-HALLUCINATION: RAG agents MUST use search tools
                # If step 1 has no tool calls, the LLM is hallucinating
                # ========================================================================
                if step == 1 and agent.agent_type.value == "rag" and len(tool_results) == 0:
                    logger.warning(f"[Executor.stream] HALLUCINATION DETECTED: RAG agent responded without using search tools")
                    lang = context.language or "en"
                    if lang == "ja":
                        answer = f"申し訳ございませんが、「{task}」に関する情報はナレッジベースに見つかりませんでした。"
                    elif lang == "ko":
                        answer = f"죄송합니다. 「{task}」에 대한 정보를 지식 베이스에서 찾을 수 없습니다."
                    else:
                        answer = f"I'm sorry, but I couldn't find information about \"{task}\" in the knowledge base."
                    # Skip strip_thinking_tags and validation for hallucination response
                    yield AgentStreamChunk(chunk_type="text", content=answer)
                    yield AgentStreamChunk(chunk_type="done", metadata={"hallucination_blocked": True})
                    return

                # ========================================================================
                # STRIP THINKING TAGS: Remove internal reasoning from response
                # ========================================================================
                original_answer = answer
                logger.debug(f"Original LLM response ({len(original_answer)} chars): {original_answer[:200]}...")

                answer = strip_thinking_tags(answer)
                if answer != original_answer:
                    logger.info(f"Stripped thinking tags from answer. Original: {len(original_answer)} chars, Cleaned: {len(answer)} chars")
                    logger.debug(f"Cleaned answer: {answer[:200] if answer else '(empty)'}")
                    if not answer:
                        # If all content was thinking, request a new response
                        logger.warning("All content was internal reasoning - returning generic message")
                        answer = get_insufficient_info_response(context.language or "en")

                # ========================================================================
                # RAG Analysis: Send generation start for UI progress modal
                # ========================================================================
                yield AgentStreamChunk(
                    chunk_type="generation_start",
                    content="답변 생성을 시작합니다...",
                    metadata={
                        "total_sources": len(sources),
                        "tools_used": [tr.get("tool_name", "unknown") for tr in tool_results if tr.get("success")],
                        "answer_length": len(answer)
                    }
                )

                # ========================================================================
                # POST-EXECUTION VALIDATION: Check for general knowledge violations
                # ========================================================================
                is_violation, validated_answer = _check_for_general_knowledge_violation(
                    answer,
                    tool_results,
                    language=context.language or "en"
                )
                if is_violation:
                    logger.warning(f"[Executor.stream] General knowledge violation detected for {agent.agent_type.value} agent")
                    log_compliance_violation(
                        ComplianceViolationType.GENERAL_KNOWLEDGE_DETECTED,
                        agent.agent_type.value,
                        user_id=context.user_id,
                        session_id=context.session_id,
                        details={"original_answer_preview": answer[:200]}
                    )
                    answer = validated_answer

                # Detect artifacts in the response
                from .artifact_detector import detect_artifacts
                detected_artifacts = detect_artifacts(answer)

                # Yield artifact chunks first (before text)
                for artifact in detected_artifacts:
                    yield AgentStreamChunk(
                        chunk_type="artifact",
                        content=artifact.content,
                        artifact_id=artifact.id,
                        artifact_type=artifact.type,
                        artifact_title=artifact.title,
                        artifact_language=artifact.language,
                        metadata={
                            "line_count": artifact.line_count,
                            "char_count": artifact.char_count,
                        }
                    )

                # Stream text content with progress tracking
                chunk_size = 50
                total_chunks = (len(answer) + chunk_size - 1) // chunk_size
                for i in range(0, len(answer), chunk_size):
                    chunk = answer[i:i + chunk_size]
                    current_chunk = (i // chunk_size) + 1

                    # Send generation progress every 10 chunks
                    if current_chunk % 10 == 1 or current_chunk == total_chunks:
                        yield AgentStreamChunk(
                            chunk_type="generation_progress",
                            content=f"답변 생성 중... ({current_chunk}/{total_chunks})",
                            metadata={
                                "current_chunk": current_chunk,
                                "total_chunks": total_chunks,
                                "progress_pct": round((current_chunk / total_chunks) * 100, 1)
                            }
                        )

                    yield AgentStreamChunk(chunk_type="text", content=chunk)
                    await asyncio.sleep(0.02)

                break

        # Clean up status callbacks
        for tool in available_tools:
            if hasattr(tool, 'set_status_callback'):
                tool.set_status_callback(None)

        # Yield sources and done
        if sources:
            logger.info(f"Yielding {len(sources)} sources to client: {[s.get('source', 'unknown') for s in sources[:5]]}")
            yield AgentStreamChunk(chunk_type="sources", sources=sources[:10])

            # Calculate and yield source reliability
            language = context.language if context.language != "auto" else "ko"
            reliability = calculate_reliability(sources, language)
            yield AgentStreamChunk(
                chunk_type="source_reliability",
                metadata={
                    "score": reliability.score,
                    "level": reliability.level.value,
                    "factors": reliability.factors,
                    "explanation": reliability.explanation
                }
            )
            logger.info(f"[Executor] Yielded reliability: score={reliability.score}, level={reliability.level.value}")

            # RAG Evaluation: 자동 평가 (설정 활성화 시)
            from ..core.config import api_settings
            if getattr(api_settings, 'RAG_EVALUATION_AUTO_EVALUATE', False):
                try:
                    from ..services.rag_evaluation_service import get_rag_evaluation_service
                    from ..models.rag_evaluation import SourceInput

                    eval_service = get_rag_evaluation_service()
                    if eval_service and answer and sources:
                        # 소스 변환
                        source_inputs = [
                            SourceInput(
                                content=s.get("content", "")[:2000],  # 2000자 제한
                                score=s.get("score") or s.get("similarity"),
                                source=s.get("source"),
                                doc_id=s.get("doc_id"),
                            )
                            for s in sources[:5]  # 상위 5개만 평가
                            if s.get("content")
                        ]

                        if source_inputs:
                            # 진행 상태 알림
                            yield AgentStreamChunk(
                                chunk_type="rag_evaluation_progress",
                                content="RAG 응답 품질 평가 중...",
                                metadata={"status": "evaluating"}
                            )

                            # 평가 수행
                            evaluation = await eval_service.evaluate(
                                query=task,
                                answer=answer[:3000],  # 3000자 제한
                                sources=source_inputs,
                                language=language,
                                user_id=context.user_id or "anonymous",
                            )

                            # 평가 결과 전송
                            yield AgentStreamChunk(
                                chunk_type="rag_evaluation",
                                metadata={
                                    "evaluation_id": evaluation.evaluation_id,
                                    "overall_score": evaluation.overall_score,
                                    "overall_level": evaluation.overall_level.value,
                                    "metrics": {
                                        k.value: {
                                            "score": v.score,
                                            "explanation": v.explanation
                                        }
                                        for k, v in evaluation.metrics.items()
                                    },
                                    "issues": evaluation.issues[:3],  # 상위 3개 이슈
                                    "evaluation_time_ms": evaluation.evaluation_time_ms,
                                }
                            )
                            logger.info(
                                f"[Executor] RAG evaluation: score={evaluation.overall_score}, "
                                f"level={evaluation.overall_level.value}"
                            )
                except Exception as eval_error:
                    logger.warning(f"RAG evaluation failed (non-fatal): {eval_error}")
        else:
            logger.debug("No sources to yield")

        # User Feedback Prompt: message_id와 함께 피드백 UI 표시 요청
        # 프론트엔드에서 이 chunk를 받으면 👍/👎 버튼을 표시
        if answer:
            import uuid
            response_message_id = str(uuid.uuid4())  # 메시지 고유 ID 생성
            yield AgentStreamChunk(
                chunk_type="feedback_prompt",
                metadata={
                    "message_id": response_message_id,
                    "query": task[:500] if task else "",
                    "answer_preview": answer[:200] if answer else "",
                    "sources_count": len(sources) if sources else 0,
                    "enable_quick_feedback": True,  # 👍/👎 버튼 활성화
                    "enable_detailed_feedback": True,  # 상세 피드백 옵션 활성화
                    "enable_citation_feedback": bool(sources),  # 출처 피드백 활성화
                }
            )
            logger.info(f"[Executor] Yielded feedback prompt: message_id={response_message_id}")

        # Enhanced Citations: 출처 정보에 표시 포맷 추가
        if sources:
            try:
                from ..services.user_feedback_service import get_user_feedback_service
                feedback_service = get_user_feedback_service()
                if feedback_service:
                    enhanced = feedback_service.enhance_citations(sources[:10])
                    yield AgentStreamChunk(
                        chunk_type="enhanced_citations",
                        metadata={
                            "citations": [c.model_dump() for c in enhanced],
                            "total_sources": len(sources),
                        }
                    )
                    logger.info(f"[Executor] Yielded {len(enhanced)} enhanced citations")
            except Exception as cite_err:
                logger.warning(f"[Executor] Enhanced citations failed (non-fatal): {cite_err}")

        yield AgentStreamChunk(
            chunk_type="done",
            metadata={
                "steps": step,
                "execution_time": time.time() - start_time
            }
        )

    async def _call_llm(
        self,
        messages: List[AgentMessage],
        tools: List[ToolDefinition],
        tool_choice: str = "auto"
    ) -> Optional[AgentMessage]:
        """Call the LLM with messages and tools

        Args:
            tool_choice: "auto" (default), "required" (force tool use), or "none"
        """
        try:
            logger.debug(f"[Executor] _call_llm called, adapter={self.llm_adapter}, tools={len(tools)}")

            if self.llm_adapter is None:
                # Mock response for testing
                logger.warning("[Executor] No LLM adapter - returning mock response")
                return AgentMessage(
                    role=MessageRole.ASSISTANT,
                    content="LLM adapter not configured. This is a mock response."
                )

            # Format messages for LLM with size limiting
            # NIM/vLLM can fail with 400 error if request is too large
            # Must count TOTAL payload size including tool_calls, not just content
            MAX_TOTAL_CHARS = 25000  # ~6250 tokens (reduced for safety margin)

            def _estimate_message_size(msg: AgentMessage) -> int:
                """Estimate total serialized size of a message including tool_calls."""
                size = len(msg.content or "")
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        size += len(tc.call_id or "")
                        size += len(tc.tool_name or "")
                        # Arguments can be very large (e.g., search results)
                        args_str = json.dumps(tc.arguments) if tc.arguments else "{}"
                        size += len(args_str)
                if msg.tool_call_id:
                    size += len(msg.tool_call_id)
                if msg.name:
                    size += len(msg.name)
                return size

            total_chars = sum(_estimate_message_size(msg) for msg in messages)
            logger.debug(f"Total message payload size: {total_chars} chars, {len(messages)} messages")

            if total_chars > MAX_TOTAL_CHARS:
                logger.warning(f"[Executor] Message payload too large ({total_chars} chars), truncating")
                # Keep system prompt (first) and latest user query (last), truncate middle
                # For RAG agents, the middle messages are typically:
                # - Assistant with tool_calls
                # - Tool results (can be VERY large)
                # We prioritize keeping the system prompt and user query

                truncated_messages = []
                # Always keep system prompt (index 0)
                if messages:
                    truncated_messages.append(messages[0])
                # Always keep latest user message (last index)
                if len(messages) > 1:
                    truncated_messages.append(messages[-1])

                current_size = sum(_estimate_message_size(m) for m in truncated_messages)

                # Try to add some middle messages if space allows (from most recent backward)
                middle_messages = messages[1:-1] if len(messages) > 2 else []
                for msg in reversed(middle_messages):
                    msg_size = _estimate_message_size(msg)
                    if current_size + msg_size < MAX_TOTAL_CHARS - 2000:  # Leave 2000 char buffer
                        truncated_messages.insert(-1, msg)  # Insert before last
                        current_size += msg_size
                    else:
                        logger.debug(f"[Executor] Skipping message (size={msg_size}) to stay under limit")

                messages = truncated_messages
                final_size = sum(_estimate_message_size(m) for m in messages)
                logger.info(f"Truncated to {len(messages)} messages, {final_size} chars (from {total_chars})")

            formatted_messages = []
            for msg in messages:
                formatted = {"role": msg.role.value, "content": msg.content}
                if msg.tool_calls:
                    formatted["tool_calls"] = [
                        {
                            "id": tc.call_id,
                            "type": "function",
                            "function": {
                                "name": tc.tool_name,
                                "arguments": json.dumps(tc.arguments)
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                if msg.tool_call_id:
                    formatted["tool_call_id"] = msg.tool_call_id
                if msg.name:
                    formatted["name"] = msg.name
                formatted_messages.append(formatted)

            # Format tools for LLM
            formatted_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters
                    }
                }
                for tool in tools
            ]

            # Call LLM
            # Log actual payload size for debugging
            payload_size = len(json.dumps(formatted_messages, ensure_ascii=False))
            tools_size = len(json.dumps(formatted_tools, ensure_ascii=False)) if formatted_tools else 0
            total_payload = payload_size + tools_size
            logger.info(f"Calling LLM: {len(formatted_messages)} messages ({payload_size} chars), {len(formatted_tools)} tools ({tools_size} chars), total={total_payload} chars, tool_choice={tool_choice}")
            if total_payload > 30000:
                logger.warning(f"Large payload detected: {total_payload} chars may cause NIM 400 error")
            response = await self.llm_adapter.generate(
                messages=formatted_messages,
                tools=formatted_tools if formatted_tools else None,
                tool_choice=tool_choice
            )
            logger.info(f"[Executor] LLM response: content_len={len(response.get('content', ''))}, tool_calls={len(response.get('tool_calls', []))}")

            # Parse response
            content = response.get("content", "")

            # Check for LLM errors (adapter returns error in content)
            if (content.startswith("Connection error:") or
                content.startswith("Timeout error:") or
                content.startswith("LLM error:") or
                content.startswith("Error:")):
                logger.error(f"[Executor] LLM request failed: {content}")
                return None  # Signal LLM failure to caller
            tool_calls = []

            if "tool_calls" in response:
                for tc in response["tool_calls"]:
                    func = tc.get("function", {})
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        args = json.loads(args)

                    logger.debug(f"LLM tool_call: {func.get('name')} args={args}")
                    tool_calls.append(ToolCall(
                        tool_name=func.get("name", ""),
                        arguments=args,
                        call_id=tc.get("id", "")
                    ))

            return AgentMessage(
                role=MessageRole.ASSISTANT,
                content=content,
                tool_calls=tool_calls if tool_calls else None
            )

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    async def _execute_tool(
        self,
        tool_call: ToolCall,
        context: AgentContext
    ) -> ToolResult:
        """Execute a tool call"""
        tool = self.tool_registry.get(tool_call.tool_name)

        if tool is None:
            logger.warning(f"[Executor] Tool not found in registry: {tool_call.tool_name}")
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {tool_call.tool_name}",
                metadata=None
            )

        # Validate parameters
        is_valid, error = tool.validate_params(tool_call.arguments)
        if not is_valid:
            logger.warning(f"[Executor] Parameter validation failed: {error}")
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid parameters: {error}",
                metadata=None
            )

        try:
            result = await tool.execute(context, **tool_call.arguments)
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Tool execution failed: {str(e)}",
                metadata=None
            )

    def _extract_sources(self, tool_results: List[ToolResult]) -> List[Dict[str, Any]]:
        """Extract sources from tool results"""
        sources = []
        for result in tool_results:
            if result["success"] and result.get("metadata"):
                if "sources" in result["metadata"]:
                    sources.extend(result["metadata"]["sources"])

            # Also try to parse output for sources
            try:
                output = result.get("output", "")
                if isinstance(output, str) and output.startswith("{"):
                    data = json.loads(output)
                    if "results" in data:
                        for r in data["results"]:
                            if "source" in r:
                                sources.append({
                                    "content": r.get("content", "")[:200],
                                    "source": r["source"],
                                    "score": r.get("score", 0)
                                })
            except (json.JSONDecodeError, TypeError):
                pass

        # Deduplicate sources
        seen = set()
        unique_sources = []
        for s in sources:
            key = s.get("source", "")
            if key and key not in seen:
                seen.add(key)
                unique_sources.append(s)

        return unique_sources[:10]  # Limit to 10 sources


# Convenience function
def get_executor() -> AgentExecutor:
    """Get a configured executor instance"""
    return AgentExecutor()
