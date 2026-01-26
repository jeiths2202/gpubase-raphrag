"""
Use Cases Layer
Application-specific business rules and orchestration.

Use cases encapsulate and implement all of the use cases of the system.
They orchestrate the flow of data to and from entities/repositories
and direct those entities to use their enterprise-wide business rules
to achieve the goals of the use case.
"""
from .base import UseCase, UseCaseResult
from .mindmap import (
    GenerateMindmapUseCase,
    ExpandNodeUseCase,
    QueryNodeUseCase,
    MindmapInput,
    MindmapOutput
)
from .query import (
    ExecuteQueryUseCase,
    ClassifyQueryUseCase,
    QueryInput,
    QueryOutput
)
from .document import (
    UploadDocumentUseCase,
    ProcessDocumentUseCase,
    DeleteDocumentUseCase,
    DocumentInput,
    DocumentOutput
)

__all__ = [
    # Base
    "UseCase",
    "UseCaseResult",
    # Mindmap
    "GenerateMindmapUseCase",
    "ExpandNodeUseCase",
    "QueryNodeUseCase",
    "MindmapInput",
    "MindmapOutput",
    # Query
    "ExecuteQueryUseCase",
    "ClassifyQueryUseCase",
    "QueryInput",
    "QueryOutput",
    # Document
    "UploadDocumentUseCase",
    "ProcessDocumentUseCase",
    "DeleteDocumentUseCase",
    "DocumentInput",
    "DocumentOutput",
]
