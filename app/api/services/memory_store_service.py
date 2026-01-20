"""
Memory Store Service

Provides persistent long-term memory for Deep Agents using LangGraph's StoreBackend.
Enables:
- User preferences persistence across sessions
- Knowledge base building from multiple conversations
- Self-improving agent instructions based on feedback
- Research progress maintenance across sessions

Uses Neo4j as the durable storage backend for seamless integration with existing infrastructure.
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Check for LangGraph store availability
try:
    from langgraph.store.memory import InMemoryStore
    from langgraph.store.base import BaseStore
    LANGGRAPH_STORE_AVAILABLE = True
except ImportError:
    LANGGRAPH_STORE_AVAILABLE = False
    logger.warning("LangGraph store not available. Long-term memory will be limited.")

# Check for deepagents backends
try:
    from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
    DEEPAGENTS_BACKENDS_AVAILABLE = True
except ImportError:
    DEEPAGENTS_BACKENDS_AVAILABLE = False
    logger.warning("Deep Agents backends not available.")

# Check for Neo4j availability (using langchain_neo4j pattern)
try:
    from langchain_neo4j import Neo4jGraph
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    logger.info("langchain_neo4j not available, will use file-based storage")


class Neo4jMemoryStore:
    """
    Neo4j-based persistent memory store for LangGraph.

    Stores memory items in Neo4j graph database for durability
    and enables cross-session persistence.

    Auto-connects to Neo4j using environment variables (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD).
    Falls back to file-based storage if Neo4j is unavailable.
    """

    def __init__(
        self,
        driver: Optional[Any] = None,
        database: str = "neo4j"
    ):
        """
        Initialize Neo4j memory store.

        Args:
            driver: Neo4j driver instance (optional, will auto-connect if not provided)
            database: Database name to use
        """
        self._driver = driver
        self._graph: Optional[Any] = None  # Neo4jGraph instance
        self._database = database
        self._initialized = False
        self._use_neo4j = False

    def _get_neo4j_graph(self) -> Optional[Any]:
        """Get or create Neo4jGraph instance using environment variables."""
        if self._graph is not None:
            return self._graph

        if not NEO4J_AVAILABLE:
            return None

        try:
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "")

            if not neo4j_password:
                logger.info("NEO4J_PASSWORD not set, using file-based storage")
                return None

            self._graph = Neo4jGraph(
                url=neo4j_uri,
                username=neo4j_user,
                password=neo4j_password
            )
            logger.info(f"Connected to Neo4j at {neo4j_uri} for memory storage")
            return self._graph
        except Exception as e:
            logger.warning(f"Failed to connect to Neo4j: {e}, using file-based storage")
            return None

    async def initialize(self):
        """Initialize the store and create necessary indexes."""
        if self._initialized:
            return

        graph = self._get_neo4j_graph()
        if graph is None:
            logger.info("Using file-based storage for agent memory")
            return

        try:
            # Create memory node index using Neo4jGraph
            graph.query("""
                CREATE INDEX memory_namespace_key IF NOT EXISTS
                FOR (m:AgentMemory)
                ON (m.namespace, m.key)
            """)
            self._use_neo4j = True
            self._initialized = True
            logger.info("Neo4j memory store initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Neo4j memory store: {e}, using file fallback")
            self._use_neo4j = False

    async def put(
        self,
        namespace: str,
        key: str,
        value: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> None:
        """
        Store a memory item.

        Args:
            namespace: Memory namespace (e.g., "/memories/preferences")
            key: Unique key within namespace
            value: Value to store (dict)
            user_id: Optional user ID for user-specific memories
        """
        graph = self._get_neo4j_graph()
        if graph is None or not self._use_neo4j:
            await self._put_file_fallback(namespace, key, value, user_id)
            return

        try:
            graph.query("""
                MERGE (m:AgentMemory {namespace: $namespace, key: $key})
                SET m.value = $value,
                    m.user_id = $user_id,
                    m.updated_at = datetime()
            """, {
                "namespace": namespace,
                "key": key,
                "value": json.dumps(value),
                "user_id": user_id
            })
        except Exception as e:
            logger.error(f"Failed to store memory in Neo4j: {e}")
            # Fallback to file storage
            await self._put_file_fallback(namespace, key, value, user_id)

    async def get(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a memory item.

        Args:
            namespace: Memory namespace
            key: Key to retrieve
            user_id: Optional user ID filter

        Returns:
            Stored value or None if not found
        """
        graph = self._get_neo4j_graph()
        if graph is None or not self._use_neo4j:
            return await self._get_file_fallback(namespace, key, user_id)

        try:
            result = graph.query("""
                MATCH (m:AgentMemory {namespace: $namespace, key: $key})
                WHERE m.user_id IS NULL OR m.user_id = $user_id
                RETURN m.value as value
            """, {
                "namespace": namespace,
                "key": key,
                "user_id": user_id
            })
            if result and len(result) > 0 and result[0].get("value"):
                return json.loads(result[0]["value"])
        except Exception as e:
            logger.error(f"Failed to retrieve memory from Neo4j: {e}")
            return await self._get_file_fallback(namespace, key, user_id)

        return None

    async def delete(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str] = None
    ) -> None:
        """Delete a memory item."""
        graph = self._get_neo4j_graph()
        if graph is None or not self._use_neo4j:
            await self._delete_file_fallback(namespace, key, user_id)
            return

        try:
            graph.query("""
                MATCH (m:AgentMemory {namespace: $namespace, key: $key})
                WHERE m.user_id IS NULL OR m.user_id = $user_id
                DELETE m
            """, {
                "namespace": namespace,
                "key": key,
                "user_id": user_id
            })
        except Exception as e:
            logger.error(f"Failed to delete memory from Neo4j: {e}")

    async def list_keys(
        self,
        namespace: str,
        user_id: Optional[str] = None
    ) -> List[str]:
        """List all keys in a namespace."""
        graph = self._get_neo4j_graph()
        if graph is None or not self._use_neo4j:
            return await self._list_keys_file_fallback(namespace, user_id)

        try:
            result = graph.query("""
                MATCH (m:AgentMemory)
                WHERE m.namespace STARTS WITH $namespace
                AND (m.user_id IS NULL OR m.user_id = $user_id)
                RETURN m.key as key
            """, {
                "namespace": namespace,
                "user_id": user_id
            })
            return [record["key"] for record in result]
        except Exception as e:
            logger.error(f"Failed to list memory keys from Neo4j: {e}")
            return []

    # File-based fallback methods
    def _get_storage_dir(self) -> Path:
        """Get the file-based storage directory."""
        base_dir = os.getenv("MEMORY_STORE_DIR", "data/agent_memory")
        path = Path(base_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _get_file_path(self, namespace: str, key: str, user_id: Optional[str]) -> Path:
        """Get file path for a memory item."""
        storage_dir = self._get_storage_dir()
        safe_namespace = namespace.replace("/", "_").strip("_")
        safe_key = key.replace("/", "_").strip("_")
        user_prefix = f"user_{user_id}_" if user_id else ""
        return storage_dir / f"{user_prefix}{safe_namespace}_{safe_key}.json"

    async def _put_file_fallback(
        self,
        namespace: str,
        key: str,
        value: Dict[str, Any],
        user_id: Optional[str]
    ) -> None:
        """Store memory to file as fallback."""
        try:
            file_path = self._get_file_path(namespace, key, user_id)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({
                    "namespace": namespace,
                    "key": key,
                    "value": value,
                    "user_id": user_id,
                    "updated_at": datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"File fallback storage failed: {e}")

    async def _get_file_fallback(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Retrieve memory from file as fallback."""
        try:
            file_path = self._get_file_path(namespace, key, user_id)
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("value")
        except Exception as e:
            logger.error(f"File fallback retrieval failed: {e}")
        return None

    async def _delete_file_fallback(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str]
    ) -> None:
        """Delete memory file as fallback."""
        try:
            file_path = self._get_file_path(namespace, key, user_id)
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            logger.error(f"File fallback deletion failed: {e}")

    async def _list_keys_file_fallback(
        self,
        namespace: str,
        user_id: Optional[str]
    ) -> List[str]:
        """List keys from files as fallback."""
        try:
            storage_dir = self._get_storage_dir()
            safe_namespace = namespace.replace("/", "_").strip("_")
            user_prefix = f"user_{user_id}_" if user_id else ""
            pattern = f"{user_prefix}{safe_namespace}_*.json"

            keys = []
            for file_path in storage_dir.glob(pattern):
                # Extract key from filename
                filename = file_path.stem
                parts = filename.split("_")
                if len(parts) >= 2:
                    keys.append(parts[-1])
            return keys
        except Exception as e:
            logger.error(f"File fallback key listing failed: {e}")
            return []


class LangGraphStoreAdapter:
    """
    Adapter that wraps Neo4jMemoryStore for LangGraph StoreBackend compatibility.

    Implements the interface expected by deepagents.backends.StoreBackend.
    """

    def __init__(self, neo4j_store: Neo4jMemoryStore):
        """
        Initialize the adapter.

        Args:
            neo4j_store: Neo4j memory store instance
        """
        self._store = neo4j_store
        self._cache: Dict[str, Any] = {}

    def put(self, namespace: tuple, key: str, value: Any) -> None:
        """Store a value (sync wrapper for async store)."""
        import asyncio
        ns_str = "/".join(namespace) if isinstance(namespace, (list, tuple)) else str(namespace)

        # Cache for sync access
        cache_key = f"{ns_str}/{key}"
        self._cache[cache_key] = value

        # Try to store asynchronously
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._store.put(ns_str, key, {"value": value}))
            else:
                loop.run_until_complete(self._store.put(ns_str, key, {"value": value}))
        except Exception as e:
            logger.warning(f"Async store failed, using cache only: {e}")

    def get(self, namespace: tuple, key: str) -> Optional[Any]:
        """Retrieve a value (sync wrapper for async store)."""
        import asyncio
        ns_str = "/".join(namespace) if isinstance(namespace, (list, tuple)) else str(namespace)

        # Check cache first
        cache_key = f"{ns_str}/{key}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try to retrieve asynchronously
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                result = loop.run_until_complete(self._store.get(ns_str, key))
                if result and "value" in result:
                    self._cache[cache_key] = result["value"]
                    return result["value"]
        except Exception as e:
            logger.warning(f"Async retrieval failed: {e}")

        return None

    def delete(self, namespace: tuple, key: str) -> None:
        """Delete a value (sync wrapper for async store)."""
        import asyncio
        ns_str = "/".join(namespace) if isinstance(namespace, (list, tuple)) else str(namespace)

        # Remove from cache
        cache_key = f"{ns_str}/{key}"
        self._cache.pop(cache_key, None)

        # Try to delete asynchronously
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._store.delete(ns_str, key))
            else:
                loop.run_until_complete(self._store.delete(ns_str, key))
        except Exception as e:
            logger.warning(f"Async deletion failed: {e}")

    def search(self, namespace: tuple) -> List[Dict[str, Any]]:
        """Search for all items in a namespace."""
        import asyncio
        ns_str = "/".join(namespace) if isinstance(namespace, (list, tuple)) else str(namespace)

        results = []
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                keys = loop.run_until_complete(self._store.list_keys(ns_str))
                for key in keys:
                    value = self.get(namespace, key)
                    if value is not None:
                        results.append({"key": key, "value": value})
        except Exception as e:
            logger.warning(f"Async search failed: {e}")

        return results


class MemoryStoreService:
    """
    Service for managing agent long-term memory.

    Provides:
    - CompositeBackend configuration for Deep Agents
    - User-specific memory namespaces
    - Memory lifecycle management
    """

    # Default memory paths that persist
    PERSISTENT_PATHS = [
        "/memories/",           # General long-term memory
        "/preferences/",        # User preferences
        "/knowledge/",          # Accumulated knowledge
        "/instructions/",       # Self-improving instructions
        "/research/",           # Research progress
    ]

    def __init__(
        self,
        neo4j_driver: Optional[Any] = None,
        database: str = "neo4j"
    ):
        """
        Initialize memory store service.

        Args:
            neo4j_driver: Neo4j driver instance
            database: Database name
        """
        self._neo4j_store = Neo4jMemoryStore(driver=neo4j_driver, database=database)
        self._langgraph_adapter: Optional[LangGraphStoreAdapter] = None
        self._composite_backend: Optional[Any] = None
        self._user_stores: Dict[str, Any] = {}

    async def initialize(self):
        """Initialize the memory store service."""
        await self._neo4j_store.initialize()
        self._langgraph_adapter = LangGraphStoreAdapter(self._neo4j_store)
        logger.info("Memory store service initialized")

    def get_composite_backend(self, user_id: Optional[str] = None) -> Any:
        """
        Get a CompositeBackend configured for long-term memory.

        This backend routes:
        - /memories/* -> Persistent StoreBackend (Neo4j/File)
        - Everything else -> Ephemeral StateBackend

        Args:
            user_id: Optional user ID for user-specific memory

        Returns:
            CompositeBackend instance or None if not available
        """
        if not DEEPAGENTS_BACKENDS_AVAILABLE:
            logger.warning("Deep Agents backends not available, returning None")
            return None

        # Create user-specific store if needed
        if user_id and user_id not in self._user_stores:
            self._user_stores[user_id] = self._create_user_store(user_id)

        store = self._user_stores.get(user_id, self._get_default_store())

        # Build routes for all persistent paths
        routes = {}
        for path in self.PERSISTENT_PATHS:
            routes[path] = StoreBackend(store=store)

        return CompositeBackend(
            default=StateBackend(),
            routes=routes
        )

    def _get_default_store(self):
        """Get the default LangGraph store."""
        if LANGGRAPH_STORE_AVAILABLE and self._langgraph_adapter:
            return self._langgraph_adapter
        elif LANGGRAPH_STORE_AVAILABLE:
            return InMemoryStore()
        return None

    def _create_user_store(self, user_id: str):
        """Create a user-specific memory store."""
        # For now, use the same adapter with user context
        # In the future, could create isolated stores per user
        return self._get_default_store()

    async def store_memory(
        self,
        namespace: str,
        key: str,
        value: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> bool:
        """
        Store a memory item directly.

        Args:
            namespace: Memory namespace (e.g., "preferences", "knowledge")
            key: Unique key
            value: Value to store
            user_id: Optional user ID

        Returns:
            True if successful
        """
        try:
            full_namespace = f"/memories/{namespace}" if not namespace.startswith("/") else namespace
            await self._neo4j_store.put(full_namespace, key, value, user_id)
            return True
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return False

    async def retrieve_memory(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a memory item directly.

        Args:
            namespace: Memory namespace
            key: Key to retrieve
            user_id: Optional user ID

        Returns:
            Stored value or None
        """
        try:
            full_namespace = f"/memories/{namespace}" if not namespace.startswith("/") else namespace
            return await self._neo4j_store.get(full_namespace, key, user_id)
        except Exception as e:
            logger.error(f"Failed to retrieve memory: {e}")
            return None

    async def delete_memory(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str] = None
    ) -> bool:
        """Delete a memory item."""
        try:
            full_namespace = f"/memories/{namespace}" if not namespace.startswith("/") else namespace
            await self._neo4j_store.delete(full_namespace, key, user_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False

    async def list_memories(
        self,
        namespace: str,
        user_id: Optional[str] = None
    ) -> List[str]:
        """List all memory keys in a namespace."""
        try:
            full_namespace = f"/memories/{namespace}" if not namespace.startswith("/") else namespace
            return await self._neo4j_store.list_keys(full_namespace, user_id)
        except Exception as e:
            logger.error(f"Failed to list memories: {e}")
            return []

    # ============================================
    # Compatibility methods for AutoAgentMemoryManager
    # These proxy to Neo4jMemoryStore methods for interface compatibility
    # ============================================

    async def get(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a memory item (compatibility method for AutoAgentMemoryManager).

        Args:
            namespace: Memory namespace
            key: Key to retrieve
            user_id: Optional user ID

        Returns:
            Stored value or None
        """
        return await self._neo4j_store.get(namespace, key, user_id)

    async def put(
        self,
        namespace: str,
        key: str,
        value: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> None:
        """
        Store a memory item (compatibility method for AutoAgentMemoryManager).

        Args:
            namespace: Memory namespace
            key: Key to store
            value: Value to store
            user_id: Optional user ID
        """
        await self._neo4j_store.put(namespace, key, value, user_id)

    async def delete(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str] = None
    ) -> None:
        """
        Delete a memory item (compatibility method for AutoAgentMemoryManager).

        Args:
            namespace: Memory namespace
            key: Key to delete
            user_id: Optional user ID
        """
        await self._neo4j_store.delete(namespace, key, user_id)

    async def store_user_preference(
        self,
        user_id: str,
        preference_key: str,
        preference_value: Any
    ) -> bool:
        """
        Store a user preference.

        Args:
            user_id: User ID
            preference_key: Preference key (e.g., "language", "theme")
            preference_value: Preference value

        Returns:
            True if successful
        """
        return await self.store_memory(
            namespace="/preferences/",
            key=preference_key,
            value={"preference": preference_value, "updated_at": datetime.now().isoformat()},
            user_id=user_id
        )

    async def get_user_preference(
        self,
        user_id: str,
        preference_key: str,
        default: Any = None
    ) -> Any:
        """
        Get a user preference.

        Args:
            user_id: User ID
            preference_key: Preference key
            default: Default value if not found

        Returns:
            Preference value or default
        """
        result = await self.retrieve_memory(
            namespace="/preferences/",
            key=preference_key,
            user_id=user_id
        )
        if result and "preference" in result:
            return result["preference"]
        return default

    async def accumulate_knowledge(
        self,
        user_id: str,
        topic: str,
        knowledge_item: Dict[str, Any]
    ) -> bool:
        """
        Add to accumulated knowledge base.

        Args:
            user_id: User ID
            topic: Knowledge topic
            knowledge_item: Knowledge to store

        Returns:
            True if successful
        """
        # Get existing knowledge for topic
        existing = await self.retrieve_memory(
            namespace="/knowledge/",
            key=topic,
            user_id=user_id
        )

        if existing and "items" in existing:
            items = existing["items"]
            items.append({
                **knowledge_item,
                "added_at": datetime.now().isoformat()
            })
        else:
            items = [{
                **knowledge_item,
                "added_at": datetime.now().isoformat()
            }]

        return await self.store_memory(
            namespace="/knowledge/",
            key=topic,
            value={"items": items, "updated_at": datetime.now().isoformat()},
            user_id=user_id
        )


# Singleton instance
_memory_store_service: Optional[MemoryStoreService] = None


def get_memory_store_service() -> MemoryStoreService:
    """Get the singleton memory store service instance."""
    global _memory_store_service
    if _memory_store_service is None:
        _memory_store_service = MemoryStoreService()
    return _memory_store_service


async def initialize_memory_store(neo4j_driver: Optional[Any] = None) -> MemoryStoreService:
    """
    Initialize the memory store service with optional Neo4j driver.

    Args:
        neo4j_driver: Neo4j driver instance

    Returns:
        Initialized MemoryStoreService
    """
    global _memory_store_service
    _memory_store_service = MemoryStoreService(neo4j_driver=neo4j_driver)
    await _memory_store_service.initialize()
    return _memory_store_service
