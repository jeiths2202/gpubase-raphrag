"""
Agent Work Service (AGENT_WORK_{userid} Role)

Provides user-specific work memory for Agent-Driven RAG.
Enables session restoration, search history tracking, and preference management.

Uses existing MemoryStoreService for persistence with namespace: /agent_work/
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class SearchScope:
    """Selected search scope for a query."""
    documents: List[str] = field(default_factory=list)  # pdf_ids
    sections: List[str] = field(default_factory=list)   # section_paths
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchScope':
        return cls(
            documents=data.get("documents", []),
            sections=data.get("sections", []),
            keywords=data.get("keywords", [])
        )


@dataclass
class SearchHistoryEntry:
    """A single search history entry."""
    query: str
    timestamp: str
    selected_scope: Optional[SearchScope] = None
    result_count: int = 0
    was_successful: bool = True

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "query": self.query,
            "timestamp": self.timestamp,
            "result_count": self.result_count,
            "was_successful": self.was_successful
        }
        if self.selected_scope:
            result["selected_scope"] = self.selected_scope.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchHistoryEntry':
        scope = None
        if data.get("selected_scope"):
            scope = SearchScope.from_dict(data["selected_scope"])
        return cls(
            query=data.get("query", ""),
            timestamp=data.get("timestamp", ""),
            selected_scope=scope,
            result_count=data.get("result_count", 0),
            was_successful=data.get("was_successful", True)
        )


@dataclass
class SessionState:
    """State of a user's last session."""
    timestamp: str
    last_query: str
    selected_scope: Optional[SearchScope] = None
    conversation_id: Optional[str] = None
    agent_type: str = "rag"

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "timestamp": self.timestamp,
            "last_query": self.last_query,
            "agent_type": self.agent_type
        }
        if self.selected_scope:
            result["selected_scope"] = self.selected_scope.to_dict()
        if self.conversation_id:
            result["conversation_id"] = self.conversation_id
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionState':
        scope = None
        if data.get("selected_scope"):
            scope = SearchScope.from_dict(data["selected_scope"])
        return cls(
            timestamp=data.get("timestamp", ""),
            last_query=data.get("last_query", ""),
            selected_scope=scope,
            conversation_id=data.get("conversation_id"),
            agent_type=data.get("agent_type", "rag")
        )


@dataclass
class UserPreferences:
    """User preferences for RAG behavior."""
    default_documents: List[str] = field(default_factory=list)
    language: str = "auto"
    always_confirm_scope: bool = True
    max_history_items: int = 50
    auto_restore_session: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPreferences':
        return cls(
            default_documents=data.get("default_documents", []),
            language=data.get("language", "auto"),
            always_confirm_scope=data.get("always_confirm_scope", True),
            max_history_items=data.get("max_history_items", 50),
            auto_restore_session=data.get("auto_restore_session", True)
        )


@dataclass
class AgentWorkData:
    """Complete agent work data for a user."""
    user_id: str
    last_session: Optional[SessionState] = None
    search_history: List[SearchHistoryEntry] = field(default_factory=list)
    preferences: UserPreferences = field(default_factory=UserPreferences)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "user_id": self.user_id,
            "search_history": [h.to_dict() for h in self.search_history],
            "preferences": self.preferences.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
        if self.last_session:
            result["last_session"] = self.last_session.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentWorkData':
        last_session = None
        if data.get("last_session"):
            last_session = SessionState.from_dict(data["last_session"])

        history = [
            SearchHistoryEntry.from_dict(h)
            for h in data.get("search_history", [])
        ]

        prefs = UserPreferences.from_dict(data.get("preferences", {}))

        return cls(
            user_id=data.get("user_id", ""),
            last_session=last_session,
            search_history=history,
            preferences=prefs,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", "")
        )


class AgentWorkService:
    """
    Service for managing user-specific agent work memory.

    Provides:
    - Session state persistence and restoration
    - Search history tracking
    - User preference management
    - Search scope suggestions based on history
    """

    NAMESPACE = "/agent_work/"
    MAX_HISTORY_DEFAULT = 50

    def __init__(self, memory_store=None):
        """
        Initialize Agent Work Service.

        Args:
            memory_store: MemoryStoreService instance (optional)
        """
        self._memory_store = memory_store
        self._cache: Dict[str, AgentWorkData] = {}

    def _ensure_memory_store(self):
        """Ensure memory store is available."""
        if self._memory_store is not None:
            return

        from .memory_store_service import get_memory_store_service
        self._memory_store = get_memory_store_service()

    async def get_agent_work(self, user_id: str) -> AgentWorkData:
        """
        Get agent work data for a user.

        Args:
            user_id: User ID

        Returns:
            AgentWorkData for the user
        """
        # Check cache first
        if user_id in self._cache:
            return self._cache[user_id]

        self._ensure_memory_store()

        try:
            data = await self._memory_store.get(
                namespace=self.NAMESPACE,
                key=user_id,
                user_id=user_id
            )

            if data:
                work_data = AgentWorkData.from_dict(data)
            else:
                # Create new work data for user
                now = datetime.now(timezone.utc).isoformat()
                work_data = AgentWorkData(
                    user_id=user_id,
                    created_at=now,
                    updated_at=now
                )

            self._cache[user_id] = work_data
            return work_data

        except Exception as e:
            logger.error(f"AgentWorkService: Failed to get work data for {user_id}: {e}")
            # Return empty work data
            return AgentWorkData(user_id=user_id)

    async def save_agent_work(self, work_data: AgentWorkData) -> bool:
        """
        Save agent work data.

        Args:
            work_data: AgentWorkData to save

        Returns:
            True if successful
        """
        self._ensure_memory_store()

        try:
            work_data.updated_at = datetime.now(timezone.utc).isoformat()

            await self._memory_store.put(
                namespace=self.NAMESPACE,
                key=work_data.user_id,
                value=work_data.to_dict(),
                user_id=work_data.user_id
            )

            self._cache[work_data.user_id] = work_data
            return True

        except Exception as e:
            logger.error(f"AgentWorkService: Failed to save work data: {e}")
            return False

    async def update_session_state(
        self,
        user_id: str,
        query: str,
        selected_scope: Optional[SearchScope] = None,
        conversation_id: Optional[str] = None,
        agent_type: str = "rag"
    ) -> bool:
        """
        Update the user's session state.

        Args:
            user_id: User ID
            query: Last query
            selected_scope: Selected search scope
            conversation_id: Active conversation ID
            agent_type: Agent type being used

        Returns:
            True if successful
        """
        work_data = await self.get_agent_work(user_id)

        work_data.last_session = SessionState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            last_query=query,
            selected_scope=selected_scope,
            conversation_id=conversation_id,
            agent_type=agent_type
        )

        return await self.save_agent_work(work_data)

    async def add_search_history(
        self,
        user_id: str,
        query: str,
        selected_scope: Optional[SearchScope] = None,
        result_count: int = 0,
        was_successful: bool = True
    ) -> bool:
        """
        Add an entry to search history.

        Args:
            user_id: User ID
            query: Search query
            selected_scope: Selected search scope
            result_count: Number of results found
            was_successful: Whether the search was successful

        Returns:
            True if successful
        """
        work_data = await self.get_agent_work(user_id)

        entry = SearchHistoryEntry(
            query=query,
            timestamp=datetime.now(timezone.utc).isoformat(),
            selected_scope=selected_scope,
            result_count=result_count,
            was_successful=was_successful
        )

        # Add to beginning (most recent first)
        work_data.search_history.insert(0, entry)

        # Trim to max history items
        max_items = work_data.preferences.max_history_items
        if len(work_data.search_history) > max_items:
            work_data.search_history = work_data.search_history[:max_items]

        return await self.save_agent_work(work_data)

    async def get_session_for_restore(
        self,
        user_id: str,
        max_age_hours: int = 24
    ) -> Optional[Dict[str, Any]]:
        """
        Get session state for restoration if within time limit.

        Args:
            user_id: User ID
            max_age_hours: Maximum session age in hours

        Returns:
            Session state dict if available and within time limit
        """
        work_data = await self.get_agent_work(user_id)

        if not work_data.last_session:
            return None

        # Check session age
        try:
            session_time = datetime.fromisoformat(
                work_data.last_session.timestamp.replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            age_hours = (now - session_time).total_seconds() / 3600

            if age_hours > max_age_hours:
                return None

            return {
                "timestamp": work_data.last_session.timestamp,
                "last_query": work_data.last_session.last_query,
                "selected_scope": work_data.last_session.selected_scope.to_dict()
                if work_data.last_session.selected_scope else None,
                "conversation_id": work_data.last_session.conversation_id,
                "agent_type": work_data.last_session.agent_type,
                "age_hours": age_hours
            }
        except Exception as e:
            logger.warning(f"AgentWorkService: Failed to parse session timestamp: {e}")
            return None

    async def get_suggested_scope(
        self,
        user_id: str,
        query: str
    ) -> Optional[SearchScope]:
        """
        Get suggested search scope based on history.

        Analyzes search history to find similar queries and suggest scope.

        Args:
            user_id: User ID
            query: Current query

        Returns:
            Suggested SearchScope or None
        """
        work_data = await self.get_agent_work(user_id)

        if not work_data.search_history:
            return None

        query_lower = query.lower()
        query_words = set(query_lower.split())

        best_match: Optional[SearchHistoryEntry] = None
        best_score = 0.0

        # Find most similar previous query
        for entry in work_data.search_history[:20]:  # Check recent 20
            if not entry.selected_scope:
                continue

            entry_lower = entry.query.lower()
            entry_words = set(entry_lower.split())

            # Calculate Jaccard similarity
            intersection = len(query_words & entry_words)
            union = len(query_words | entry_words)
            similarity = intersection / union if union > 0 else 0

            if similarity > best_score and similarity > 0.3:
                best_score = similarity
                best_match = entry

        if best_match and best_match.selected_scope:
            return best_match.selected_scope

        return None

    async def update_preferences(
        self,
        user_id: str,
        preferences: Dict[str, Any]
    ) -> bool:
        """
        Update user preferences.

        Args:
            user_id: User ID
            preferences: Preference updates (partial update supported)

        Returns:
            True if successful
        """
        work_data = await self.get_agent_work(user_id)

        # Update only provided fields
        if "default_documents" in preferences:
            work_data.preferences.default_documents = preferences["default_documents"]
        if "language" in preferences:
            work_data.preferences.language = preferences["language"]
        if "always_confirm_scope" in preferences:
            work_data.preferences.always_confirm_scope = preferences["always_confirm_scope"]
        if "max_history_items" in preferences:
            work_data.preferences.max_history_items = preferences["max_history_items"]
        if "auto_restore_session" in preferences:
            work_data.preferences.auto_restore_session = preferences["auto_restore_session"]

        return await self.save_agent_work(work_data)

    async def get_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Get user preferences.

        Args:
            user_id: User ID

        Returns:
            User preferences dict
        """
        work_data = await self.get_agent_work(user_id)
        return work_data.preferences.to_dict()

    async def clear_history(self, user_id: str) -> bool:
        """
        Clear search history for a user.

        Args:
            user_id: User ID

        Returns:
            True if successful
        """
        work_data = await self.get_agent_work(user_id)
        work_data.search_history = []
        return await self.save_agent_work(work_data)

    async def clear_session(self, user_id: str) -> bool:
        """
        Clear session state for a user.

        Args:
            user_id: User ID

        Returns:
            True if successful
        """
        work_data = await self.get_agent_work(user_id)
        work_data.last_session = None
        return await self.save_agent_work(work_data)

    def invalidate_cache(self, user_id: Optional[str] = None):
        """
        Invalidate cache for a user or all users.

        Args:
            user_id: User ID (None to invalidate all)
        """
        if user_id:
            self._cache.pop(user_id, None)
        else:
            self._cache.clear()


# Singleton instance
_agent_work_service: Optional[AgentWorkService] = None


def get_agent_work_service() -> AgentWorkService:
    """Get the singleton AgentWorkService instance."""
    global _agent_work_service
    if _agent_work_service is None:
        _agent_work_service = AgentWorkService()
    return _agent_work_service


async def initialize_agent_work_service(memory_store=None) -> AgentWorkService:
    """
    Initialize the agent work service with optional memory store.

    Args:
        memory_store: MemoryStoreService instance

    Returns:
        Initialized AgentWorkService
    """
    global _agent_work_service
    _agent_work_service = AgentWorkService(memory_store=memory_store)
    return _agent_work_service
