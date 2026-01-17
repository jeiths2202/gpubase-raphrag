"""
Agent Executor
Implements the ReAct (Reasoning + Acting) loop for agent execution.
"""
from typing import Dict, List, Any, Optional, AsyncGenerator
import asyncio
import logging
import time
import json
import base64

from .types import (
    AgentContext, AgentResult, AgentMessage, ToolCall,
    ToolResult, MessageRole, ToolStatus, AgentStreamChunk,
    ToolDefinition
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
from ..core.app_mode import is_develop_mode

logger = logging.getLogger(__name__)


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

# Max characters per tool result to prevent context overflow (NIM limit: 8192 tokens ~ 24000 chars)
# Conservative limit: 3000 chars (~1000 tokens) to leave room for system prompt + messages
MAX_TOOL_RESULT_CHARS = 3000


def _truncate_tool_result(content: str, max_chars: int = MAX_TOOL_RESULT_CHARS) -> str:
    """
    Truncate tool result content to prevent LLM context overflow.
    Keeps the beginning and notes truncation.
    """
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

        # Build system prompt with language preference
        if context.language and context.language != "auto":
            language_names = {"en": "English", "ko": "Korean", "ja": "Japanese"}
            lang_name = language_names.get(context.language, context.language)
            system_prompt += f"""

LANGUAGE REQUIREMENT:
- You MUST respond in {lang_name} by default
- This is the user's configured language preference
- ONLY switch to a different language if the user EXPLICITLY requests it in their message (e.g., "Answer in English", "日本語で答えて", "영어로 대답해줘")
- If the user's message is in a different language but they don't explicitly request a response in that language, still respond in {lang_name}"""

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
{context.file_context}
[END ATTACHED FILE CONTEXT]

IMPORTANT: Answer from the attached file context above if possible. Only use tools if the answer is not in the attached context.

User Query: {task}"""
            logger.info(f"[Executor] File context attached ({len(context.file_context)} chars)")

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
            if context.file_context:
                # Both file and URL context
                user_message = user_message.replace(
                    "[END ATTACHED FILE CONTEXT]",
                    f"""[END ATTACHED FILE CONTEXT]

[URL CONTENT FROM: {url_source}]
{context.url_context}
[END URL CONTENT]"""
                )
            else:
                # Only URL context
                user_message = f"""[URL CONTENT FROM: {url_source}]
{context.url_context}
[END URL CONTENT]

IMPORTANT: Answer from the URL content above if possible. Only use tools if the answer is not in the URL content.

User Query: {task}"""
            logger.info(f"[Executor] URL context attached ({len(context.url_context)} chars) from {url_source}")

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
            response = await self._call_llm(messages, tool_definitions)

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
            else:
                # No tool calls - agent has finished reasoning
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

        # Build system prompt with language preference
        logger.debug(f"[Executor.stream] context.language = '{context.language}'")
        if context.language and context.language != "auto":
            language_names = {"en": "English", "ko": "Korean", "ja": "Japanese"}
            lang_name = language_names.get(context.language, context.language)
            system_prompt += f"""

LANGUAGE REQUIREMENT:
- You MUST respond in {lang_name} by default
- This is the user's configured language preference
- ONLY switch to a different language if the user EXPLICITLY requests it in their message (e.g., "Answer in English", "日本語で答えて", "영어로 대답해줘")
- If the user's message is in a different language but they don't explicitly request a response in that language, still respond in {lang_name}"""
            logger.debug(f"[Executor.stream] Added language instruction for {lang_name}")

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
{context.file_context}
[END ATTACHED FILE CONTEXT]

IMPORTANT: Answer from the attached file context above if possible. Only use tools if the answer is not in the attached context.

User Query: {task}"""
            logger.info(f"[Executor.stream] File context attached ({len(context.file_context)} chars)")

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
            if context.file_context:
                # Both file and URL context
                user_message = user_message.replace(
                    "[END ATTACHED FILE CONTEXT]",
                    f"""[END ATTACHED FILE CONTEXT]

[URL CONTENT FROM: {url_source}]
{context.url_context}
[END URL CONTENT]"""
                )
            else:
                # Only URL context
                user_message = f"""[URL CONTENT FROM: {url_source}]
{context.url_context}
[END URL CONTENT]

IMPORTANT: Answer from the URL content above if possible. Only use tools if the answer is not in the URL content.

User Query: {task}"""
            logger.info(f"[Executor.stream] URL context attached ({len(context.url_context)} chars) from {url_source}")

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

        # Store original task in context for query validation in tools
        # This prevents LLM from corrupting Japanese/Korean queries in tool calls
        context.metadata['original_query'] = task

        print(f"[Executor] Starting stream for task: {task}", flush=True)
        print(f"[Executor] Agent: {agent.name}, Tools: {[t.name for t in available_tools]}", flush=True)
        logger.info(f"[Executor] Starting stream for task: {task[:50]}...")
        logger.info(f"[Executor] Agent: {agent.name}, Tools: {[t.name for t in available_tools]}")
        logger.debug(f"[Executor] LLM adapter: {self.llm_adapter}")

        # ========================================================================
        # DEVELOP MODE: Execute all tools and show aggregated results
        # ========================================================================
        if is_develop_mode():
            print(f"[Executor] DEVELOP MODE: Executing all tools for analysis", flush=True)
            logger.info("[Executor] DEVELOP MODE: Executing all tools for analysis")

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
            response = await self._call_llm(messages, tool_definitions)

            if response is None:
                yield AgentStreamChunk(chunk_type="error", content="LLM call failed")
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
                    print(f"[Executor] Calling tool: {tool_call.tool_name}", flush=True)
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

                    # Stream images if tool result contains image_urls (e.g., from adaptive_search)
                    if result.get("success") and result.get("metadata"):
                        async for image_chunk in _stream_images_from_metadata(result["metadata"]):
                            yield image_chunk

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
                        sources.extend(result["metadata"]["sources"])
            else:
                # Stream final answer
                answer = response.content or ""

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

                # Stream text content
                chunk_size = 50
                for i in range(0, len(answer), chunk_size):
                    chunk = answer[i:i + chunk_size]
                    yield AgentStreamChunk(chunk_type="text", content=chunk)
                    await asyncio.sleep(0.02)

                break

        # Clean up status callbacks
        for tool in available_tools:
            if hasattr(tool, 'set_status_callback'):
                tool.set_status_callback(None)

        # Yield sources and done
        if sources:
            yield AgentStreamChunk(chunk_type="sources", sources=sources[:10])

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
        tools: List[ToolDefinition]
    ) -> Optional[AgentMessage]:
        """Call the LLM with messages and tools"""
        try:
            logger.debug(f"[Executor] _call_llm called, adapter={self.llm_adapter}, tools={len(tools)}")

            if self.llm_adapter is None:
                # Mock response for testing
                logger.warning("[Executor] No LLM adapter - returning mock response")
                return AgentMessage(
                    role=MessageRole.ASSISTANT,
                    content="LLM adapter not configured. This is a mock response."
                )

            # Format messages for LLM
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
            logger.info(f"[Executor] Calling LLM with {len(formatted_messages)} messages, {len(formatted_tools)} tools")
            response = await self.llm_adapter.generate(
                messages=formatted_messages,
                tools=formatted_tools if formatted_tools else None
            )
            logger.info(f"[Executor] LLM response: content_len={len(response.get('content', ''))}, tool_calls={len(response.get('tool_calls', []))}")

            # Parse response
            content = response.get("content", "")
            tool_calls = []

            if "tool_calls" in response:
                for tc in response["tool_calls"]:
                    func = tc.get("function", {})
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        args = json.loads(args)

                    print(f"[Executor] LLM tool_call: {func.get('name')} args={args}", flush=True)
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
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {tool_call.tool_name}",
                metadata=None
            )

        # Validate parameters
        is_valid, error = tool.validate_params(tool_call.arguments)
        if not is_valid:
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
            logger.error(f"Tool execution failed: {e}")
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
