"""
Use Case Factory
Factory for creating use case instances with injected dependencies.
"""
from typing import Optional
from functools import lru_cache

from .mindmap import GenerateMindmapUseCase, ExpandNodeUseCase, QueryNodeUseCase
from .query import ExecuteQueryUseCase, ClassifyQueryUseCase
from .document import UploadDocumentUseCase, ProcessDocumentUseCase, DeleteDocumentUseCase

from ..core.container import Container, get_container


class UseCaseFactory:
    """
    Factory for creating use case instances.

    All use cases receive their dependencies through constructor injection,
    making them fully testable with mock implementations.

    Usage:
        # Production
        factory = UseCaseFactory.create()
        use_case = factory.generate_mindmap()
        result = await use_case.execute(input, context)

        # Testing
        factory = UseCaseFactory.create_for_testing()
        use_case = factory.generate_mindmap()  # Uses mock adapters
    """

    def __init__(self, container: Container):
        self.container = container

    @classmethod
    def create(cls) -> "UseCaseFactory":
        """Create factory with production container"""
        return cls(get_container())

    @classmethod
    def create_for_testing(
        cls,
        llm=None,
        embedding=None,
        vector_store=None,
        graph_store=None,
        document_repo=None,
        history_repo=None
    ) -> "UseCaseFactory":
        """
        Create factory with mock dependencies for testing.

        Args:
            llm: Mock LLM adapter (uses MockLLMAdapter if None)
            embedding: Mock embedding adapter
            vector_store: Mock vector store
            graph_store: Mock graph store
            document_repo: Mock document repository
            history_repo: Mock history repository
        """
        from ..adapters.mock import (
            MockLLMAdapter,
            MockEmbeddingAdapter,
            MockVectorStoreAdapter,
            MockGraphStoreAdapter
        )
        from ..infrastructure.memory import (
            MemoryDocumentRepository,
            MemoryHistoryRepository
        )
        from ..core.container import Container, ContainerConfig, Environment

        # Create test container
        config = ContainerConfig(
            environment=Environment.TESTING,
            llm_provider="mock",
            vector_store_type="mock"
        )
        container = Container(config)

        # Register mock implementations
        container.register_singleton("llm", llm or MockLLMAdapter())
        container.register_singleton("embedding", embedding or MockEmbeddingAdapter())
        container.register_singleton("vector_store", vector_store or MockVectorStoreAdapter())
        container.register_singleton("graph_store", graph_store or MockGraphStoreAdapter())
        container.register_singleton("document_repository", document_repo or MemoryDocumentRepository())
        container.register_singleton("history_repository", history_repo or MemoryHistoryRepository())

        return cls(container)

    # ==================== Mindmap Use Cases ====================

    def generate_mindmap(self) -> GenerateMindmapUseCase:
        """Create GenerateMindmapUseCase with dependencies"""
        return GenerateMindmapUseCase(
            llm=self.container.llm,
            document_repository=self.container.document_repository
        )

    def expand_node(self) -> ExpandNodeUseCase:
        """Create ExpandNodeUseCase with dependencies"""
        return ExpandNodeUseCase(
            llm=self.container.llm,
            vector_store=self.container.vector_store,
            embedding=self.container.embedding
        )

    def query_node(self) -> QueryNodeUseCase:
        """Create QueryNodeUseCase with dependencies"""
        return QueryNodeUseCase(
            llm=self.container.llm,
            vector_store=self.container.vector_store,
            embedding=self.container.embedding
        )

    # ==================== Query Use Cases ====================

    def execute_query(self) -> ExecuteQueryUseCase:
        """Create ExecuteQueryUseCase with dependencies"""
        return ExecuteQueryUseCase(
            llm=self.container.llm,
            embedding=self.container.embedding,
            vector_store=self.container.vector_store,
            graph_store=self.container.graph_store,
            document_repository=self.container.document_repository,
            history_repository=self.container.history_repository
        )

    def classify_query(self) -> ClassifyQueryUseCase:
        """Create ClassifyQueryUseCase with dependencies"""
        return ClassifyQueryUseCase(
            llm=self.container.llm
        )

    # ==================== Document Use Cases ====================

    def upload_document(self) -> UploadDocumentUseCase:
        """Create UploadDocumentUseCase with dependencies"""
        return UploadDocumentUseCase(
            document_repository=self.container.document_repository
        )

    def process_document(self) -> ProcessDocumentUseCase:
        """Create ProcessDocumentUseCase with dependencies"""
        return ProcessDocumentUseCase(
            document_repository=self.container.document_repository,
            embedding=self.container.embedding,
            vector_store=self.container.vector_store
        )

    def delete_document(self) -> DeleteDocumentUseCase:
        """Create DeleteDocumentUseCase with dependencies"""
        return DeleteDocumentUseCase(
            document_repository=self.container.document_repository,
            vector_store=self.container.vector_store
        )


# ==================== FastAPI Dependencies ====================

@lru_cache()
def get_use_case_factory() -> UseCaseFactory:
    """Get cached use case factory for FastAPI dependency injection"""
    return UseCaseFactory.create()


# Convenience functions for FastAPI Depends
def get_generate_mindmap_use_case() -> GenerateMindmapUseCase:
    return get_use_case_factory().generate_mindmap()


def get_expand_node_use_case() -> ExpandNodeUseCase:
    return get_use_case_factory().expand_node()


def get_query_node_use_case() -> QueryNodeUseCase:
    return get_use_case_factory().query_node()


def get_execute_query_use_case() -> ExecuteQueryUseCase:
    return get_use_case_factory().execute_query()


def get_classify_query_use_case() -> ClassifyQueryUseCase:
    return get_use_case_factory().classify_query()


def get_upload_document_use_case() -> UploadDocumentUseCase:
    return get_use_case_factory().upload_document()


def get_process_document_use_case() -> ProcessDocumentUseCase:
    return get_use_case_factory().process_document()


def get_delete_document_use_case() -> DeleteDocumentUseCase:
    return get_use_case_factory().delete_document()
