"""
Auto Agent Memory Manager

Manages three-layer memory for the Auto Agent orchestration:
1. User Memory - persisted across sessions (Neo4j)
2. System Memory - agent statistics and patterns (Neo4j)
3. Conversation Memory - current session context (PostgreSQL)
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from .types import (
    AutoAgentMemoryContext, UserMemory, SystemMemory, ConversationMemory,
    ExecutionPlan, VerificationResult, ComposedAnswer
)
from ..types import AgentType

logger = logging.getLogger(__name__)


class AutoAgentMemoryManager:
    """
    Memory manager for the Auto Agent orchestration system.

    Integrates with:
    - Neo4j: Long-term user and system memory
    - PostgreSQL: Conversation history and summaries
    """

    # Memory namespaces in Neo4j
    USER_MEMORY_NAMESPACE = "/memories/user"
    SYSTEM_MEMORY_NAMESPACE = "/memories/system"

    # Default preferences
    DEFAULT_LANGUAGE = "auto"
    DEFAULT_MAX_TURNS = 10

    def __init__(
        self,
        memory_store_service=None,
        conversation_service=None
    ):
        """
        Initialize the memory manager.

        Args:
            memory_store_service: Neo4j memory store service for long-term memory
            conversation_service: PostgreSQL service for conversation management
        """
        self._memory_store = memory_store_service
        self._conversation_service = conversation_service

    @property
    def memory_store(self):
        """Lazy load memory store service"""
        if self._memory_store is None:
            try:
                from ...services.memory_store_service import get_memory_store_service
                self._memory_store = get_memory_store_service()
            except ImportError:
                logger.warning("Memory store service not available")
        return self._memory_store

    @property
    def conversation_service(self):
        """Lazy load conversation service"""
        if self._conversation_service is None:
            try:
                from ...services.conversation_service import get_conversation_service
                self._conversation_service = get_conversation_service()
            except ImportError:
                logger.warning("Conversation service not available")
        return self._conversation_service

    async def get_context_for_planner(
        self,
        user_id: Optional[str],
        session_id: str,
        task: str
    ) -> AutoAgentMemoryContext:
        """
        Get aggregated memory context for the Planner Agent.

        Args:
            user_id: User identifier
            session_id: Current session identifier
            task: Current task being planned

        Returns:
            AutoAgentMemoryContext with all available memory
        """
        user_memory = await self._load_user_memory(user_id) if user_id else None
        system_memory = await self._load_system_memory()
        conversation_memory = await self._load_conversation_memory(session_id)

        # Derive insights for planner
        suggested_agents = self._suggest_agents_for_task(task, system_memory)
        relevant_queries = self._find_relevant_past_queries(task, user_memory)
        domain_context = self._extract_domain_context(user_memory, conversation_memory)

        return AutoAgentMemoryContext(
            user_memory=user_memory,
            system_memory=system_memory,
            conversation_memory=conversation_memory,
            suggested_agents=suggested_agents,
            relevant_past_queries=relevant_queries,
            domain_context=domain_context
        )

    async def _load_user_memory(self, user_id: str) -> Optional[UserMemory]:
        """Load user-specific memory from Neo4j"""
        if not self.memory_store:
            return None

        try:
            # Load user preferences
            prefs = await self.memory_store.get(
                namespace=f"{self.USER_MEMORY_NAMESPACE}/{user_id}",
                key="preferences"
            )

            # Load interaction history
            history = await self.memory_store.get(
                namespace=f"{self.USER_MEMORY_NAMESPACE}/{user_id}",
                key="interaction_history"
            )

            if not prefs and not history:
                return None

            prefs = prefs or {}
            history = history or {}

            return UserMemory(
                user_id=user_id,
                language_preference=prefs.get("language", self.DEFAULT_LANGUAGE),
                domain_expertise=prefs.get("domains", []),
                frequently_asked_topics=history.get("frequent_topics", []),
                response_style_preference=prefs.get("response_style"),
                last_interaction=self._parse_datetime(history.get("last_interaction")),
                interaction_count=history.get("count", 0),
                custom_preferences=prefs.get("custom", {})
            )

        except Exception as e:
            logger.error(f"[MemoryManager] Failed to load user memory: {e}")
            return None

    async def _load_system_memory(self) -> Optional[SystemMemory]:
        """Load system-wide memory from Neo4j"""
        if not self.memory_store:
            return None

        try:
            # Load agent statistics
            agent_stats = await self.memory_store.get(
                namespace=self.SYSTEM_MEMORY_NAMESPACE,
                key="agent_stats"
            )

            # Load failure patterns
            patterns = await self.memory_store.get(
                namespace=self.SYSTEM_MEMORY_NAMESPACE,
                key="failure_patterns"
            )

            if not agent_stats:
                # Return default statistics
                return SystemMemory(
                    agent_success_rates={
                        AgentType.RAG.value: 0.85,
                        AgentType.IMS.value: 0.80,
                        AgentType.CODE.value: 0.75,
                        AgentType.VISION.value: 0.70
                    },
                    common_failure_patterns=[],
                    average_execution_times={
                        AgentType.RAG.value: 5.0,
                        AgentType.IMS.value: 8.0,
                        AgentType.CODE.value: 10.0,
                        AgentType.VISION.value: 15.0
                    }
                )

            return SystemMemory(
                agent_success_rates=agent_stats.get("success_rates", {}),
                common_failure_patterns=(patterns or {}).get("patterns", []),
                average_execution_times=agent_stats.get("avg_times", {}),
                popular_query_patterns=agent_stats.get("query_patterns", [])
            )

        except Exception as e:
            logger.error(f"[MemoryManager] Failed to load system memory: {e}")
            return None

    async def _load_conversation_memory(
        self,
        session_id: str
    ) -> Optional[ConversationMemory]:
        """Load current conversation context"""
        if not self.conversation_service:
            return ConversationMemory(session_id=session_id)

        try:
            # Get recent conversation turns
            recent_messages = await self.conversation_service.get_recent_messages(
                session_id=session_id,
                limit=self.DEFAULT_MAX_TURNS
            )

            # Get conversation summary if available
            summary = await self.conversation_service.get_conversation_summary(
                session_id=session_id
            )

            # Extract key topics from recent messages
            key_topics = self._extract_topics_from_messages(recent_messages)

            return ConversationMemory(
                session_id=session_id,
                conversation_summary=summary,
                recent_turns=recent_messages,
                key_topics=key_topics,
                turn_count=len(recent_messages)
            )

        except Exception as e:
            logger.error(f"[MemoryManager] Failed to load conversation memory: {e}")
            return ConversationMemory(session_id=session_id)

    def _suggest_agents_for_task(
        self,
        task: str,
        system_memory: Optional[SystemMemory]
    ) -> List[AgentType]:
        """Suggest agents based on task content and success rates"""
        suggested = []
        task_lower = task.lower()

        # Keyword-based suggestions
        if any(kw in task_lower for kw in ['ims', '이슈', 'issue', 'bug', '버그', '장애']):
            suggested.append(AgentType.IMS)

        if any(kw in task_lower for kw in ['코드', 'code', '소스', '생성', 'generate', 'sample']):
            suggested.append(AgentType.CODE)

        if any(kw in task_lower for kw in ['이미지', 'image', '사진', 'chart', '차트']):
            suggested.append(AgentType.VISION)

        # Default to RAG for knowledge queries
        if not suggested or any(kw in task_lower for kw in ['문서', 'document', '검색', 'search', '찾아']):
            suggested.append(AgentType.RAG)

        # Sort by success rate if available
        if system_memory and system_memory.agent_success_rates:
            suggested.sort(
                key=lambda a: system_memory.agent_success_rates.get(a.value, 0.5),
                reverse=True
            )

        return suggested

    def _find_relevant_past_queries(
        self,
        task: str,
        user_memory: Optional[UserMemory]
    ) -> List[str]:
        """Find relevant past queries from user history"""
        if not user_memory or not user_memory.frequently_asked_topics:
            return []

        # Simple keyword matching for now
        # Could be enhanced with embedding similarity
        task_words = set(task.lower().split())
        relevant = []

        for topic in user_memory.frequently_asked_topics[:20]:
            topic_words = set(topic.lower().split())
            if task_words & topic_words:  # Intersection
                relevant.append(topic)
                if len(relevant) >= 5:
                    break

        return relevant

    def _extract_domain_context(
        self,
        user_memory: Optional[UserMemory],
        conversation_memory: Optional[ConversationMemory]
    ) -> Optional[str]:
        """Extract domain context from memories"""
        context_parts = []

        if user_memory and user_memory.domain_expertise:
            context_parts.append(f"User expertise: {', '.join(user_memory.domain_expertise[:5])}")

        if conversation_memory and conversation_memory.key_topics:
            context_parts.append(f"Current topics: {', '.join(conversation_memory.key_topics[:5])}")

        return ". ".join(context_parts) if context_parts else None

    def _extract_topics_from_messages(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[str]:
        """Extract key topics from conversation messages"""
        # Simple extraction - could be enhanced with NLP
        topics = []
        for msg in messages:
            content = msg.get("content", "") or msg.get("question", "")
            # Extract nouns/key phrases (simplified)
            words = content.split()
            for word in words:
                if len(word) > 4 and word.isalpha():
                    topics.append(word.lower())

        # Return unique topics
        seen = set()
        unique_topics = []
        for topic in topics:
            if topic not in seen:
                seen.add(topic)
                unique_topics.append(topic)
                if len(unique_topics) >= 10:
                    break

        return unique_topics

    async def store_execution_result(
        self,
        user_id: Optional[str],
        session_id: str,
        task: str,
        plan: ExecutionPlan,
        verification: VerificationResult,
        answer: ComposedAnswer
    ) -> None:
        """
        Store execution results for future learning.

        Args:
            user_id: User identifier
            session_id: Session identifier
            task: Original task
            plan: Execution plan used
            verification: Verification result
            answer: Final composed answer
        """
        # Update system memory with execution statistics
        await self._update_system_stats(plan, verification)

        # Update user memory with interaction
        if user_id:
            await self._update_user_memory(user_id, task, answer)

        # Update conversation memory
        await self._update_conversation_memory(session_id, task, answer)

    async def _update_system_stats(
        self,
        plan: ExecutionPlan,
        verification: VerificationResult
    ) -> None:
        """Update system-wide statistics based on execution"""
        if not self.memory_store:
            return

        try:
            # Load existing stats
            current_stats = await self.memory_store.get(
                namespace=self.SYSTEM_MEMORY_NAMESPACE,
                key="agent_stats"
            ) or {"success_rates": {}, "execution_counts": {}}

            success_rates = current_stats.get("success_rates", {})
            exec_counts = current_stats.get("execution_counts", {})

            # Update success rates based on verification
            for task in plan.decomposed_tasks:
                agent_type = task.agent_type.value
                current_count = exec_counts.get(agent_type, 0)
                current_rate = success_rates.get(agent_type, 0.8)

                # Check if this task was successful
                task_success = task.task_id not in verification.tasks_to_retry

                # Exponential moving average
                alpha = 0.1  # Learning rate
                new_rate = current_rate * (1 - alpha) + (1.0 if task_success else 0.0) * alpha

                success_rates[agent_type] = new_rate
                exec_counts[agent_type] = current_count + 1

            # Save updated stats
            await self.memory_store.put(
                namespace=self.SYSTEM_MEMORY_NAMESPACE,
                key="agent_stats",
                value={
                    "success_rates": success_rates,
                    "execution_counts": exec_counts,
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
            )

        except Exception as e:
            logger.error(f"[MemoryManager] Failed to update system stats: {e}")

    async def _update_user_memory(
        self,
        user_id: str,
        task: str,
        answer: ComposedAnswer
    ) -> None:
        """Update user-specific memory"""
        if not self.memory_store:
            return

        try:
            # Load existing history
            history = await self.memory_store.get(
                namespace=f"{self.USER_MEMORY_NAMESPACE}/{user_id}",
                key="interaction_history"
            ) or {"frequent_topics": [], "count": 0}

            # Update interaction count
            history["count"] = history.get("count", 0) + 1
            history["last_interaction"] = datetime.now(timezone.utc).isoformat()

            # Add to frequent topics (simple approach)
            topics = history.get("frequent_topics", [])
            task_words = [w for w in task.split() if len(w) > 4]
            for word in task_words[:3]:
                if word not in topics:
                    topics.append(word)
            history["frequent_topics"] = topics[-50:]  # Keep last 50

            # Save updated history
            await self.memory_store.put(
                namespace=f"{self.USER_MEMORY_NAMESPACE}/{user_id}",
                key="interaction_history",
                value=history,
                user_id=user_id
            )

        except Exception as e:
            logger.error(f"[MemoryManager] Failed to update user memory: {e}")

    async def _update_conversation_memory(
        self,
        session_id: str,
        task: str,
        answer: ComposedAnswer
    ) -> None:
        """Update conversation memory with new turn"""
        if not self.conversation_service:
            return

        try:
            await self.conversation_service.add_message(
                session_id=session_id,
                role="user",
                content=task
            )
            await self.conversation_service.add_message(
                session_id=session_id,
                role="assistant",
                content=answer.content
            )

        except Exception as e:
            logger.error(f"[MemoryManager] Failed to update conversation memory: {e}")

    def _parse_datetime(self, dt_string: Optional[str]) -> Optional[datetime]:
        """Parse datetime string to datetime object"""
        if not dt_string:
            return None
        try:
            return datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None


# Singleton instance
_memory_manager: Optional[AutoAgentMemoryManager] = None


def get_memory_manager(
    memory_store_service=None,
    conversation_service=None
) -> AutoAgentMemoryManager:
    """Get or create the memory manager instance"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = AutoAgentMemoryManager(
            memory_store_service=memory_store_service,
            conversation_service=conversation_service
        )
    return _memory_manager
