"""
Dependency Injection Container
Centralized container for managing application dependencies.
"""
from typing import Optional, Dict, Any, Type, TypeVar, Callable
from dataclasses import dataclass, field
from enum import Enum
import os
import logging

# Repository interfaces
from ..repositories import (
    DocumentRepository,
    NoteRepository,
    ProjectRepository,
    UserRepository,
    HistoryRepository
)

# Port interfaces
from ..ports import (
    LLMPort,
    EmbeddingPort,
    VectorStorePort,
    GraphStorePort
)

# Infrastructure implementations
from ..infrastructure.memory import (
    MemoryDocumentRepository,
    MemoryNoteRepository,
    MemoryProjectRepository,
    MemoryUserRepository,
    MemoryHistoryRepository
)

# Adapter implementations
from ..adapters.mock import (
    MockLLMAdapter,
    MockEmbeddingAdapter,
    MockVectorStoreAdapter,
    MockGraphStoreAdapter
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class Environment(str, Enum):
    """Application environment"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class ContainerConfig:
    """Container configuration"""
    environment: Environment = Environment.DEVELOPMENT

    # API Keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # Database settings
    postgres_url: Optional[str] = None
    neo4j_uri: Optional[str] = None
    neo4j_username: Optional[str] = None
    neo4j_password: Optional[str] = None

    # Vector store settings
    vector_store_type: str = "mock"  # mock, pinecone, qdrant, weaviate
    pinecone_api_key: Optional[str] = None
    pinecone_environment: Optional[str] = None

    # LLM settings
    llm_provider: str = "mock"  # mock, openai, anthropic
    default_llm_model: str = "gpt-4"
    embedding_model: str = "text-embedding-3-small"

    # Cache settings
    enable_cache: bool = True
    cache_ttl: int = 3600

    # Extra settings
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "ContainerConfig":
        """Create config from environment variables"""
        env_str = os.getenv("APP_ENVIRONMENT", "development").lower()
        try:
            environment = Environment(env_str)
        except ValueError:
            environment = Environment.DEVELOPMENT

        return cls(
            environment=environment,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            postgres_url=os.getenv("DATABASE_URL"),
            neo4j_uri=os.getenv("NEO4J_URI"),
            neo4j_username=os.getenv("NEO4J_USERNAME"),
            neo4j_password=os.getenv("NEO4J_PASSWORD"),
            vector_store_type=os.getenv("VECTOR_STORE_TYPE", "mock"),
            pinecone_api_key=os.getenv("PINECONE_API_KEY"),
            pinecone_environment=os.getenv("PINECONE_ENVIRONMENT"),
            llm_provider=os.getenv("LLM_PROVIDER", "mock"),
            default_llm_model=os.getenv("DEFAULT_LLM_MODEL", "gpt-4"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            enable_cache=os.getenv("ENABLE_CACHE", "true").lower() == "true",
            cache_ttl=int(os.getenv("CACHE_TTL", "3600"))
        )


class Container:
    """
    Dependency Injection Container.

    Manages the lifecycle of application dependencies and provides
    factory methods for creating service instances.
    """

    _instance: Optional["Container"] = None

    def __init__(self, config: Optional[ContainerConfig] = None):
        self.config = config or ContainerConfig.from_env()
        self._singletons: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._initialized = False

        # Register default factories
        self._register_defaults()

    @classmethod
    def get_instance(cls) -> "Container":
        """Get singleton container instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset container (for testing)"""
        cls._instance = None

    def _register_defaults(self) -> None:
        """Register default factory methods"""
        # Repositories
        self.register_factory("document_repository", self._create_document_repository)
        self.register_factory("note_repository", self._create_note_repository)
        self.register_factory("project_repository", self._create_project_repository)
        self.register_factory("user_repository", self._create_user_repository)
        self.register_factory("history_repository", self._create_history_repository)

        # Ports/Adapters
        self.register_factory("llm", self._create_llm_adapter)
        self.register_factory("embedding", self._create_embedding_adapter)
        self.register_factory("vector_store", self._create_vector_store_adapter)
        self.register_factory("graph_store", self._create_graph_store_adapter)

    def register_factory(self, name: str, factory: Callable) -> None:
        """Register a factory method"""
        self._factories[name] = factory

    def register_singleton(self, name: str, instance: Any) -> None:
        """Register a singleton instance"""
        self._singletons[name] = instance

    def get(self, name: str) -> Any:
        """Get a dependency by name"""
        if name in self._singletons:
            return self._singletons[name]

        if name in self._factories:
            instance = self._factories[name]()
            self._singletons[name] = instance
            return instance

        raise KeyError(f"Dependency '{name}' not registered")

    def create(self, name: str) -> Any:
        """Create a new instance (not singleton)"""
        if name in self._factories:
            return self._factories[name]()
        raise KeyError(f"Factory '{name}' not registered")

    # ==================== Repository Factories ====================

    def _create_document_repository(self) -> DocumentRepository:
        """Create document repository"""
        if self.config.environment == Environment.PRODUCTION and self.config.postgres_url:
            # TODO: Return PostgreSQL implementation
            logger.warning("PostgreSQL repository not implemented, using memory")

        return MemoryDocumentRepository()

    def _create_note_repository(self) -> NoteRepository:
        """Create note repository"""
        if self.config.environment == Environment.PRODUCTION and self.config.postgres_url:
            logger.warning("PostgreSQL repository not implemented, using memory")

        return MemoryNoteRepository()

    def _create_project_repository(self) -> ProjectRepository:
        """Create project repository"""
        if self.config.environment == Environment.PRODUCTION and self.config.postgres_url:
            logger.warning("PostgreSQL repository not implemented, using memory")

        return MemoryProjectRepository()

    def _create_user_repository(self) -> UserRepository:
        """Create user repository"""
        if self.config.environment == Environment.PRODUCTION and self.config.postgres_url:
            logger.warning("PostgreSQL repository not implemented, using memory")

        return MemoryUserRepository()

    def _create_history_repository(self) -> HistoryRepository:
        """Create history repository"""
        if self.config.environment == Environment.PRODUCTION and self.config.postgres_url:
            logger.warning("PostgreSQL repository not implemented, using memory")

        return MemoryHistoryRepository()

    # ==================== Adapter Factories ====================

    def _create_llm_adapter(self) -> LLMPort:
        """Create LLM adapter"""
        if self.config.llm_provider == "openai" and self.config.openai_api_key:
            from ..adapters.langchain import LangChainLLMAdapter
            return LangChainLLMAdapter(
                api_key=self.config.openai_api_key,
                model=self.config.default_llm_model
            )

        logger.info("Using mock LLM adapter")
        return MockLLMAdapter()

    def _create_embedding_adapter(self) -> EmbeddingPort:
        """Create embedding adapter"""
        if self.config.llm_provider == "openai" and self.config.openai_api_key:
            from ..adapters.langchain import LangChainEmbeddingAdapter
            return LangChainEmbeddingAdapter(
                api_key=self.config.openai_api_key,
                model=self.config.embedding_model
            )

        logger.info("Using mock embedding adapter")
        return MockEmbeddingAdapter()

    def _create_vector_store_adapter(self) -> VectorStorePort:
        """Create vector store adapter"""
        if self.config.vector_store_type == "pinecone" and self.config.pinecone_api_key:
            # TODO: Implement Pinecone adapter
            logger.warning("Pinecone adapter not implemented, using mock")

        logger.info("Using mock vector store adapter")
        return MockVectorStoreAdapter()

    def _create_graph_store_adapter(self) -> GraphStorePort:
        """Create graph store adapter"""
        if self.config.neo4j_uri:
            # TODO: Implement Neo4j adapter
            logger.warning("Neo4j adapter not implemented, using mock")

        logger.info("Using mock graph store adapter")
        return MockGraphStoreAdapter()

    # ==================== Convenience Properties ====================

    @property
    def document_repository(self) -> DocumentRepository:
        return self.get("document_repository")

    @property
    def note_repository(self) -> NoteRepository:
        return self.get("note_repository")

    @property
    def project_repository(self) -> ProjectRepository:
        return self.get("project_repository")

    @property
    def user_repository(self) -> UserRepository:
        return self.get("user_repository")

    @property
    def history_repository(self) -> HistoryRepository:
        return self.get("history_repository")

    @property
    def llm(self) -> LLMPort:
        return self.get("llm")

    @property
    def embedding(self) -> EmbeddingPort:
        return self.get("embedding")

    @property
    def vector_store(self) -> VectorStorePort:
        return self.get("vector_store")

    @property
    def graph_store(self) -> GraphStorePort:
        return self.get("graph_store")


# Global container instance
def get_container() -> Container:
    """Get the global container instance"""
    return Container.get_instance()
