"""
Long Context Management Service (32K+ Token Support)

Provides intelligent context window management for long conversations:
- Token counting and budget management
- Semantic chunking and importance scoring
- Adaptive compression and summarization
- Multi-turn context optimization
- Model-aware context sizing
"""
import hashlib
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4

from app.api.models.long_context import (
    ContextPriority, ChunkType, CompressionMethod, LLMModelFamily,
    LLMContextConfig, ContextChunk, ContextWindow,
    CompressionRequest, CompressionResult,
    SummarizationRequest, SummarizationResult,
    ContextBuildRequest, ContextBuildResult,
    TokenBudget, TokenUsageReport,
    ContextWindowStatus, OptimizeContextRequest, OptimizeContextResult,
    get_model_context_limit
)

logger = logging.getLogger(__name__)

# Try to import tiktoken for accurate token counting
try:
    import tiktoken
    _ENCODING = tiktoken.get_encoding("cl100k_base")
    _HAS_TIKTOKEN = True
except ImportError:
    _ENCODING = None
    _HAS_TIKTOKEN = False
    logger.warning("tiktoken not available, using approximate token counting")


class LongContextService:
    """
    Service for managing long context windows (32K+ tokens).

    Features:
    - Model-aware context window sizing
    - Intelligent compression with priority preservation
    - Rolling summarization for very long conversations
    - Semantic importance scoring
    - Efficient token budget management
    """

    # Default configuration
    DEFAULT_MAX_TOKENS = 32000
    DEFAULT_COMPRESSION_THRESHOLD = 0.75
    DEFAULT_SUMMARY_TARGET_TOKENS = 500
    IMPORTANCE_DECAY_FACTOR = 0.95  # Per-turn decay for importance

    def __init__(
        self,
        conversation_repository=None,
        llm_service=None,
        default_config: Optional[LLMContextConfig] = None
    ):
        """
        Initialize long context service.

        Args:
            conversation_repository: Repository for conversation data
            llm_service: LLM service for summarization
            default_config: Default context configuration
        """
        self._repository = conversation_repository
        self._llm_service = llm_service
        self._default_config = default_config or LLMContextConfig()
        self._summary_cache: Dict[str, Tuple[str, datetime]] = {}

    # ============================================
    # Token Counting
    # ============================================

    @staticmethod
    def count_tokens(text: str) -> int:
        """
        Count tokens in text using tiktoken or approximation.

        Args:
            text: Text to count tokens for

        Returns:
            Token count
        """
        if not text:
            return 0

        if _HAS_TIKTOKEN and _ENCODING:
            return len(_ENCODING.encode(text))
        else:
            # Approximation: ~4 characters per token for English
            # Adjust for CJK characters (1-2 chars per token)
            cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff'
                          or '\u3040' <= c <= '\u30ff'
                          or '\uac00' <= c <= '\ud7af')
            other_count = len(text) - cjk_count
            return max(1, (cjk_count // 2) + (other_count // 4))

    def count_message_tokens(self, role: str, content: str) -> int:
        """Count tokens for a message including overhead."""
        content_tokens = self.count_tokens(content)
        # Add overhead for role, formatting (~4 tokens per message)
        return content_tokens + 4

    # ============================================
    # Context Building
    # ============================================

    async def build_context(
        self,
        request: ContextBuildRequest
    ) -> ContextBuildResult:
        """
        Build optimized context window for LLM input.

        This is the main entry point for context management.

        Args:
            request: Context build request

        Returns:
            ContextBuildResult with optimized context
        """
        config = request.config or self._default_config
        warnings = []

        # Initialize token budget
        budget = TokenBudget(
            total_budget=config.available_context_tokens,
            reserved={
                "response": config.reserved_for_response,
                "system": config.reserved_for_system,
                "rag": config.reserved_for_rag,
                "tools": config.reserved_for_tools
            }
        )

        chunks: List[ContextChunk] = []

        # 1. Add system prompt (CRITICAL priority)
        system_prompt = request.system_prompt or self._default_system_prompt()
        system_tokens = self.count_tokens(system_prompt)
        chunks.append(ContextChunk(
            chunk_id=str(uuid4()),
            chunk_type=ChunkType.SYSTEM_PROMPT,
            content=system_prompt,
            token_count=system_tokens,
            priority=ContextPriority.CRITICAL
        ))
        budget.allocated["system"] = system_tokens

        # 2. Add current query (CRITICAL priority)
        query_tokens = self.count_tokens(request.current_query)
        chunks.append(ContextChunk(
            chunk_id=str(uuid4()),
            chunk_type=ChunkType.USER_MESSAGE,
            content=request.current_query,
            token_count=query_tokens,
            priority=ContextPriority.CRITICAL,
            recency_score=1.0
        ))
        budget.allocated["query"] = query_tokens

        # 3. Get conversation history
        messages_added = 0
        messages_tokens = 0
        summary_tokens = 0
        summary_used = False

        if self._repository:
            history_data = await self._get_conversation_history(
                request.conversation_id,
                config
            )

            # Add summary if available
            if history_data.get("summary"):
                summary = history_data["summary"]
                summary_tokens = self.count_tokens(summary)
                chunks.append(ContextChunk(
                    chunk_id=str(uuid4()),
                    chunk_type=ChunkType.SUMMARY,
                    content=summary,
                    token_count=summary_tokens,
                    priority=ContextPriority.HIGH,
                    is_compressed=True
                ))
                budget.allocated["summary"] = summary_tokens
                summary_used = True

            # Add recent messages with importance scoring
            messages = history_data.get("messages", [])
            total_messages = len(messages)

            for idx, msg in enumerate(reversed(messages)):
                # Calculate recency score (newer = higher)
                recency = (idx + 1) / max(total_messages, 1)

                msg_tokens = self.count_message_tokens(
                    msg.get("role", "user"),
                    msg.get("content", "")
                )

                # Determine priority based on position
                if idx < 4:  # Last 2 turns
                    priority = ContextPriority.HIGH
                elif idx < 10:  # Last 5 turns
                    priority = ContextPriority.MEDIUM
                else:
                    priority = ContextPriority.LOW

                chunk = ContextChunk(
                    chunk_id=str(uuid4()),
                    chunk_type=ChunkType.USER_MESSAGE if msg.get("role") == "user"
                              else ChunkType.ASSISTANT_MESSAGE,
                    content=msg.get("content", ""),
                    token_count=msg_tokens,
                    priority=priority,
                    source_id=msg.get("id"),
                    recency_score=recency,
                    importance_score=self._calculate_importance(msg.get("content", ""))
                )
                chunks.append(chunk)
                messages_added += 1
                messages_tokens += msg_tokens

            budget.allocated["messages"] = messages_tokens

        # 4. Add RAG context
        rag_tokens = 0
        rag_chunks_added = 0

        if request.rag_context:
            for idx, rag_chunk in enumerate(request.rag_context[:request.max_rag_chunks]):
                content = rag_chunk.get("content", "")
                chunk_tokens = self.count_tokens(content)

                # Priority based on relevance score
                score = rag_chunk.get("score", 0.5)
                if score >= 0.8:
                    priority = ContextPriority.HIGH
                elif score >= 0.6:
                    priority = ContextPriority.MEDIUM
                else:
                    priority = ContextPriority.LOW

                chunks.append(ContextChunk(
                    chunk_id=str(uuid4()),
                    chunk_type=ChunkType.RAG_CONTEXT,
                    content=content,
                    token_count=chunk_tokens,
                    priority=priority,
                    source_id=rag_chunk.get("doc_id"),
                    source_type=rag_chunk.get("source_type", "vector"),
                    relevance_score=score
                ))
                rag_tokens += chunk_tokens
                rag_chunks_added += 1

            budget.allocated["rag"] = rag_tokens

        # 5. Add file context if provided
        file_tokens = 0

        if request.file_context:
            for file_ctx in request.file_context:
                content = file_ctx.get("content", "")
                chunk_tokens = self.count_tokens(content)

                chunks.append(ContextChunk(
                    chunk_id=str(uuid4()),
                    chunk_type=ChunkType.FILE_CONTEXT,
                    content=content,
                    token_count=chunk_tokens,
                    priority=ContextPriority.HIGH,  # User-provided files are important
                    source_id=file_ctx.get("file_id"),
                    source_type=file_ctx.get("file_type")
                ))
                file_tokens += chunk_tokens

            budget.allocated["files"] = file_tokens

        # 6. Calculate total and check if compression needed
        total_tokens = sum(c.token_count for c in chunks)
        compression_applied = False
        messages_dropped = 0
        rag_dropped = 0

        if total_tokens > config.available_context_tokens:
            # Apply compression
            compress_result = await self._compress_context(
                chunks=chunks,
                target_tokens=config.available_context_tokens,
                config=config
            )
            chunks = compress_result.compressed_chunks
            compression_applied = True
            messages_dropped = compress_result.chunks_removed
            total_tokens = sum(c.token_count for c in chunks)
            warnings.append(
                f"Context compressed: {compress_result.original_tokens} → "
                f"{compress_result.compressed_tokens} tokens "
                f"({compress_result.compression_ratio:.1%} reduction)"
            )

        # 7. Build formatted messages for LLM
        formatted_messages = self._format_chunks_for_llm(chunks)

        # 8. Build context window model
        context_window = ContextWindow(
            conversation_id=request.conversation_id,
            chunks=chunks,
            total_tokens=total_tokens,
            max_tokens=config.available_context_tokens,
            has_summary=summary_used,
            compression_applied=compression_applied,
            messages_included=messages_added - messages_dropped,
            rag_chunks_included=rag_chunks_added - rag_dropped
        )

        return ContextBuildResult(
            context_window=context_window,
            formatted_messages=formatted_messages,
            system_tokens=system_tokens,
            summary_tokens=summary_tokens,
            message_tokens=messages_tokens,
            rag_tokens=rag_tokens,
            query_tokens=query_tokens,
            total_tokens=total_tokens,
            compression_applied=compression_applied,
            summarization_applied=summary_used,
            messages_dropped=messages_dropped,
            rag_chunks_dropped=rag_dropped,
            warnings=warnings
        )

    async def _get_conversation_history(
        self,
        conversation_id: UUID,
        config: LLMContextConfig
    ) -> Dict[str, Any]:
        """Get conversation history from repository."""
        try:
            # Get messages with limit
            max_messages = config.max_recent_turns * 2
            context_data = await self._repository.get_context_window(
                conversation_id=str(conversation_id),
                max_tokens=config.available_context_tokens,
                include_summary=True
            )

            messages = []
            for msg in context_data.get("messages", [])[-max_messages:]:
                messages.append({
                    "id": msg.id if hasattr(msg, 'id') else None,
                    "role": msg.role if hasattr(msg, 'role') else msg.get("role"),
                    "content": msg.content if hasattr(msg, 'content') else msg.get("content")
                })

            return {
                "messages": messages,
                "summary": context_data.get("summary"),
                "total_tokens": context_data.get("total_tokens", 0),
                "messages_summarized": context_data.get("messages_summarized", 0)
            }

        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return {"messages": [], "summary": None}

    # ============================================
    # Context Compression
    # ============================================

    async def _compress_context(
        self,
        chunks: List[ContextChunk],
        target_tokens: int,
        config: LLMContextConfig
    ) -> CompressionResult:
        """
        Compress context to fit within token budget.

        Strategy:
        1. Remove low-priority chunks first
        2. Truncate medium-priority chunks
        3. Summarize if still over budget
        """
        original_tokens = sum(c.token_count for c in chunks)

        if original_tokens <= target_tokens:
            return CompressionResult(
                compressed_chunks=chunks,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                method_used=CompressionMethod.NONE
            )

        # Sort chunks by combined score (higher = more important)
        sorted_chunks = sorted(chunks, key=lambda c: c.combined_score, reverse=True)

        # Phase 1: Remove low-priority chunks
        kept_chunks = []
        current_tokens = 0
        removed_count = 0

        for chunk in sorted_chunks:
            if chunk.priority == ContextPriority.CRITICAL:
                # Always keep critical chunks
                kept_chunks.append(chunk)
                current_tokens += chunk.token_count
            elif current_tokens + chunk.token_count <= target_tokens:
                kept_chunks.append(chunk)
                current_tokens += chunk.token_count
            else:
                removed_count += 1

        # Phase 2: Truncate if still over budget
        truncated_count = 0
        if current_tokens > target_tokens:
            # Truncate lower priority chunks
            for i, chunk in enumerate(kept_chunks):
                if chunk.priority in [ContextPriority.LOW, ContextPriority.OPTIONAL]:
                    excess = current_tokens - target_tokens
                    if chunk.token_count > 100:  # Only truncate if meaningful
                        new_length = max(50, chunk.token_count - excess - 50)
                        truncated_content = self._truncate_text(
                            chunk.content,
                            new_length
                        )
                        old_tokens = chunk.token_count
                        new_tokens = self.count_tokens(truncated_content)

                        kept_chunks[i] = ContextChunk(
                            chunk_id=chunk.chunk_id,
                            chunk_type=chunk.chunk_type,
                            content=truncated_content,
                            token_count=new_tokens,
                            priority=chunk.priority,
                            source_id=chunk.source_id,
                            is_compressed=True,
                            original_token_count=old_tokens,
                            compression_method=CompressionMethod.TRUNCATION
                        )
                        current_tokens = current_tokens - old_tokens + new_tokens
                        truncated_count += 1

                        if current_tokens <= target_tokens:
                            break

        # Phase 3: Summarize message history if still over
        summarized_count = 0
        if current_tokens > target_tokens and self._llm_service:
            message_chunks = [c for c in kept_chunks
                           if c.chunk_type in [ChunkType.USER_MESSAGE, ChunkType.ASSISTANT_MESSAGE]
                           and c.priority not in [ContextPriority.CRITICAL, ContextPriority.HIGH]]

            if len(message_chunks) > 4:
                # Summarize older messages
                to_summarize = message_chunks[:-4]  # Keep last 2 turns
                messages_content = [{"role": "user" if c.chunk_type == ChunkType.USER_MESSAGE else "assistant",
                                   "content": c.content} for c in to_summarize]

                summary_result = await self.summarize_messages(
                    SummarizationRequest(
                        messages=messages_content,
                        target_tokens=min(500, sum(c.token_count for c in to_summarize) // 4)
                    )
                )

                # Replace summarized chunks with summary
                for c in to_summarize:
                    kept_chunks.remove(c)
                    current_tokens -= c.token_count

                summary_chunk = ContextChunk(
                    chunk_id=str(uuid4()),
                    chunk_type=ChunkType.SUMMARY,
                    content=summary_result.summary,
                    token_count=summary_result.summary_tokens,
                    priority=ContextPriority.MEDIUM,
                    is_compressed=True,
                    compression_method=CompressionMethod.SUMMARIZATION
                )
                kept_chunks.insert(1, summary_chunk)  # After system prompt
                current_tokens += summary_result.summary_tokens
                summarized_count = len(to_summarize)

        compressed_tokens = sum(c.token_count for c in kept_chunks)

        return CompressionResult(
            compressed_chunks=kept_chunks,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compressed_tokens / original_tokens if original_tokens > 0 else 1.0,
            method_used=CompressionMethod.HYBRID,
            chunks_removed=removed_count,
            chunks_truncated=truncated_count,
            chunks_summarized=summarized_count
        )

    def _truncate_text(self, text: str, target_tokens: int) -> str:
        """Truncate text to approximate token count."""
        if not text:
            return ""

        current_tokens = self.count_tokens(text)
        if current_tokens <= target_tokens:
            return text

        # Binary search for optimal truncation point
        ratio = target_tokens / current_tokens
        approx_chars = int(len(text) * ratio)

        # Find sentence boundary
        truncated = text[:approx_chars]
        last_period = truncated.rfind('.')
        last_newline = truncated.rfind('\n')
        cut_point = max(last_period, last_newline)

        if cut_point > approx_chars * 0.7:
            truncated = text[:cut_point + 1]
        else:
            truncated = text[:approx_chars] + "..."

        return truncated.strip()

    # ============================================
    # Summarization
    # ============================================

    async def summarize_messages(
        self,
        request: SummarizationRequest
    ) -> SummarizationResult:
        """
        Summarize conversation messages.

        Args:
            request: Summarization request

        Returns:
            SummarizationResult with summary
        """
        messages = request.messages
        original_tokens = sum(self.count_message_tokens(m["role"], m["content"])
                            for m in messages)

        if not messages:
            return SummarizationResult(
                summary="",
                original_tokens=0,
                summary_tokens=0,
                compression_ratio=1.0,
                messages_summarized=0
            )

        # Try LLM summarization first
        if self._llm_service:
            try:
                summary = await self._llm_summarize(messages, request)
                summary_tokens = self.count_tokens(summary)

                return SummarizationResult(
                    summary=summary,
                    original_tokens=original_tokens,
                    summary_tokens=summary_tokens,
                    compression_ratio=summary_tokens / original_tokens if original_tokens > 0 else 1.0,
                    messages_summarized=len(messages),
                    key_topics=self._extract_topics_from_messages(messages)
                )
            except Exception as e:
                logger.error(f"LLM summarization failed: {e}")

        # Fallback to extractive summary
        summary = self._extractive_summarize(messages, request.target_tokens)
        summary_tokens = self.count_tokens(summary)

        return SummarizationResult(
            summary=summary,
            original_tokens=original_tokens,
            summary_tokens=summary_tokens,
            compression_ratio=summary_tokens / original_tokens if original_tokens > 0 else 1.0,
            messages_summarized=len(messages),
            key_topics=self._extract_topics_from_messages(messages)
        )

    async def _llm_summarize(
        self,
        messages: List[Dict[str, str]],
        request: SummarizationRequest
    ) -> str:
        """Generate LLM-based summary."""
        conversation_text = "\n\n".join([
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in messages
        ])

        prompt = f"""Summarize the following conversation concisely, preserving:
- Key questions and answers
- Important decisions made
- Relevant context for future discussion

{f"Previous context: {request.existing_summary}" if request.existing_summary else ""}

Conversation:
{conversation_text}

Concise summary:"""

        response = await self._llm_service.generate(
            prompt=prompt,
            max_tokens=request.target_tokens
        )

        return response.get("text", "").strip()

    def _extractive_summarize(
        self,
        messages: List[Dict[str, str]],
        target_tokens: int
    ) -> str:
        """Create extractive summary from messages."""
        parts = []

        for msg in messages:
            role = "Q" if msg["role"] == "user" else "A"
            content = msg["content"]

            # Take first portion of each message
            if msg["role"] == "user":
                excerpt = content[:150]
            else:
                excerpt = content[:300]

            if len(content) > len(excerpt):
                excerpt += "..."

            parts.append(f"{role}: {excerpt}")

        summary = "\n".join(parts)

        # Trim to target tokens
        while self.count_tokens(summary) > target_tokens and parts:
            parts.pop(0)  # Remove oldest first
            summary = "\n".join(parts)

        return summary

    # ============================================
    # Context Window Status
    # ============================================

    async def get_context_status(
        self,
        conversation_id: UUID,
        config: Optional[LLMContextConfig] = None
    ) -> ContextWindowStatus:
        """
        Get current context window status.

        Args:
            conversation_id: Conversation ID
            config: Optional context configuration

        Returns:
            ContextWindowStatus with current state
        """
        config = config or self._default_config

        total_tokens = 0
        total_messages = 0
        summary_tokens = 0
        has_summary = False
        messages_summarized = 0

        if self._repository:
            try:
                # Get conversation data
                context_data = await self._repository.get_context_window(
                    conversation_id=str(conversation_id),
                    max_tokens=config.max_context_tokens,
                    include_summary=True
                )

                total_tokens = context_data.get("total_tokens", 0)
                total_messages = len(context_data.get("messages", []))
                messages_summarized = context_data.get("messages_summarized", 0)

                if context_data.get("summary"):
                    has_summary = True
                    summary_tokens = self.count_tokens(context_data["summary"])

            except Exception as e:
                logger.error(f"Error getting context status: {e}")

        usage_ratio = total_tokens / config.max_context_tokens if config.max_context_tokens > 0 else 0
        available_tokens = config.max_context_tokens - total_tokens

        # Determine compression level
        if usage_ratio < 0.5:
            compression_level = "none"
        elif usage_ratio < 0.75:
            compression_level = "light"
        elif usage_ratio < 0.9:
            compression_level = "moderate"
        else:
            compression_level = "aggressive"

        # Check if optimization needed
        needs_optimization = usage_ratio > config.compression_threshold
        optimization_reason = None
        if needs_optimization:
            optimization_reason = f"Token usage at {usage_ratio:.1%}, exceeds threshold of {config.compression_threshold:.1%}"

        return ContextWindowStatus(
            conversation_id=conversation_id,
            total_messages=total_messages,
            total_tokens=total_tokens,
            max_tokens=config.max_context_tokens,
            usage_ratio=usage_ratio,
            available_tokens=available_tokens,
            has_active_summary=has_summary,
            messages_summarized=messages_summarized,
            summary_token_count=summary_tokens,
            compression_level=compression_level,
            needs_optimization=needs_optimization,
            optimization_reason=optimization_reason
        )

    async def optimize_context(
        self,
        request: OptimizeContextRequest
    ) -> OptimizeContextResult:
        """
        Optimize context window to reduce token usage.

        Args:
            request: Optimization request

        Returns:
            OptimizeContextResult with optimization details
        """
        config = self._default_config

        # Get current status
        current_status = await self.get_context_status(request.conversation_id, config)

        if current_status.usage_ratio <= request.target_usage_ratio:
            return OptimizeContextResult(
                success=True,
                original_tokens=current_status.total_tokens,
                optimized_tokens=current_status.total_tokens,
                tokens_saved=0,
                method_used=CompressionMethod.NONE,
                new_status=current_status
            )

        # Calculate target tokens
        target_tokens = int(config.max_context_tokens * request.target_usage_ratio)

        # Get messages to potentially summarize
        if self._repository:
            context_data = await self._repository.get_context_window(
                conversation_id=str(request.conversation_id),
                max_tokens=config.max_context_tokens,
                include_summary=True
            )

            messages = context_data.get("messages", [])
            keep_count = request.preserve_recent_turns * 2

            if len(messages) > keep_count:
                to_summarize = messages[:-keep_count]

                # Perform summarization
                summary_result = await self.summarize_messages(
                    SummarizationRequest(
                        messages=[{"role": m.role, "content": m.content} for m in to_summarize],
                        existing_summary=context_data.get("summary"),
                        target_tokens=self.DEFAULT_SUMMARY_TARGET_TOKENS
                    )
                )

                # Store new summary (would need repository method)
                # For now, return the result
                new_status = await self.get_context_status(request.conversation_id, config)

                return OptimizeContextResult(
                    success=True,
                    original_tokens=current_status.total_tokens,
                    optimized_tokens=current_status.total_tokens - summary_result.tokens_saved,
                    tokens_saved=summary_result.tokens_saved,
                    method_used=request.method,
                    messages_summarized=len(to_summarize),
                    new_status=new_status
                )

        return OptimizeContextResult(
            success=False,
            original_tokens=current_status.total_tokens,
            optimized_tokens=current_status.total_tokens,
            tokens_saved=0,
            method_used=CompressionMethod.NONE,
            new_status=current_status
        )

    # ============================================
    # Utility Methods
    # ============================================

    def _calculate_importance(self, content: str) -> float:
        """Calculate importance score for content."""
        if not content:
            return 0.5

        score = 0.5

        # Boost for questions
        if "?" in content:
            score += 0.1

        # Boost for longer content (likely more detailed)
        word_count = len(content.split())
        if word_count > 50:
            score += 0.1
        if word_count > 200:
            score += 0.1

        # Boost for technical content (code, numbers)
        if any(c in content for c in ['```', 'def ', 'class ', 'function']):
            score += 0.15

        # Boost for action items
        action_words = ['should', 'must', 'need to', 'will', 'please', 'important']
        if any(word in content.lower() for word in action_words):
            score += 0.05

        return min(1.0, score)

    def _extract_topics_from_messages(self, messages: List[Dict[str, str]]) -> List[str]:
        """Extract key topics from messages."""
        topics = set()

        for msg in messages:
            content = msg.get("content", "")
            words = content.split()

            # Extract capitalized words as potential topics
            for word in words:
                clean = word.strip('.,!?:;()[]{}')
                if len(clean) > 3 and clean[0].isupper() and clean.isalpha():
                    topics.add(clean)

        return list(topics)[:10]

    def _format_chunks_for_llm(self, chunks: List[ContextChunk]) -> List[Dict[str, str]]:
        """Format chunks as LLM message array."""
        messages = []

        for chunk in chunks:
            if chunk.chunk_type == ChunkType.SYSTEM_PROMPT:
                messages.append({"role": "system", "content": chunk.content})
            elif chunk.chunk_type == ChunkType.SUMMARY:
                messages.append({
                    "role": "system",
                    "content": f"[Previous conversation summary]\n{chunk.content}"
                })
            elif chunk.chunk_type == ChunkType.USER_MESSAGE:
                messages.append({"role": "user", "content": chunk.content})
            elif chunk.chunk_type == ChunkType.ASSISTANT_MESSAGE:
                messages.append({"role": "assistant", "content": chunk.content})
            elif chunk.chunk_type == ChunkType.RAG_CONTEXT:
                # RAG context typically goes in system or as prefix to user message
                if messages and messages[-1]["role"] == "system":
                    messages[-1]["content"] += f"\n\n[Retrieved Context]\n{chunk.content}"
                else:
                    messages.insert(1, {
                        "role": "system",
                        "content": f"[Retrieved Context]\n{chunk.content}"
                    })
            elif chunk.chunk_type == ChunkType.FILE_CONTEXT:
                if messages and messages[-1]["role"] == "system":
                    messages[-1]["content"] += f"\n\n[File Context]\n{chunk.content}"

        return messages

    def _default_system_prompt(self) -> str:
        """Return default system prompt."""
        return """You are a helpful AI assistant with access to a knowledge base.
Use the provided context to answer questions accurately.
If you don't know the answer based on the context, say so.
Always cite sources when available."""


# Singleton instance
_long_context_service: Optional[LongContextService] = None


def get_long_context_service() -> LongContextService:
    """Get singleton instance of LongContextService."""
    global _long_context_service
    if _long_context_service is None:
        _long_context_service = LongContextService()
    return _long_context_service


async def initialize_long_context_service(
    conversation_repository=None,
    llm_service=None,
    config: Optional[LLMContextConfig] = None
) -> LongContextService:
    """Initialize long context service with dependencies."""
    global _long_context_service
    _long_context_service = LongContextService(
        conversation_repository=conversation_repository,
        llm_service=llm_service,
        default_config=config
    )
    return _long_context_service
