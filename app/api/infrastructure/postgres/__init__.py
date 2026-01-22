"""
PostgreSQL Infrastructure Implementations

Production-ready PostgreSQL repository implementations with:
- Async operations using asyncpg
- Row-Level Security (RLS) support
- Connection pooling
- Transaction management
"""
from .conversation_repository import PostgresConversationRepository
from .enhancement_repository import PostgresEnhancementRepository
from .external_connection_repository import (
    PostgresExternalConnectionRepository,
    get_external_connection_repository
)
from .external_document_repository import (
    PostgresExternalDocumentRepository,
    get_external_document_repository
)
from .external_chunk_repository import (
    PostgresExternalChunkRepository,
    get_external_chunk_repository
)
from .web_source_repository import (
    PostgresWebSourceRepository,
    get_web_source_repository
)

__all__ = [
    "PostgresConversationRepository",
    "PostgresEnhancementRepository",
    # External connector repositories
    "PostgresExternalConnectionRepository",
    "PostgresExternalDocumentRepository",
    "PostgresExternalChunkRepository",
    "get_external_connection_repository",
    "get_external_document_repository",
    "get_external_chunk_repository",
    # Web source repository
    "PostgresWebSourceRepository",
    "get_web_source_repository",
]
