"""
External Document Service
Manages external resource connections, document sync, and user-scoped vector store.
"""
import asyncio
import uuid
import hashlib
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
from functools import lru_cache
import os
import sys

# Add src directory for embeddings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

try:
    from embeddings import NeMoEmbeddingService
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False

from ..models.external_connection import (
    ExternalResourceType, ConnectionStatus, SyncStatus, AuthType,
    ExternalConnection, ExternalDocument, ExternalDocumentStatus,
    ExternalChunk, ExternalSearchResult
)
from ..connectors import ConnectorManager, get_connector_manager


class UserVectorStore:
    """
    User-scoped vector store for external resources.
    Keeps user's external document embeddings separate from global knowledge base.
    """

    def __init__(self, dimension: int = 4096):
        self.dimension = dimension
        # user_id -> list of (chunk_id, embedding, metadata)
        self._store: Dict[str, List[Tuple[str, np.ndarray, Dict]]] = defaultdict(list)
        self._chunk_lookup: Dict[str, ExternalChunk] = {}

    def add_chunks(self, user_id: str, chunks: List[ExternalChunk]):
        """Add chunks with embeddings for a user"""
        for chunk in chunks:
            if chunk.embedding:
                embedding_array = np.array(chunk.embedding, dtype=np.float32)
                self._store[user_id].append((
                    chunk.id,
                    embedding_array,
                    {
                        "document_id": chunk.document_id,
                        "connection_id": chunk.connection_id,
                        "source": chunk.source,
                        "source_name": chunk.source_name,
                        "source_url": chunk.source_url,
                        "section_title": chunk.section_title,
                        "index": chunk.index
                    }
                ))
                self._chunk_lookup[chunk.id] = chunk

    def search(
        self,
        user_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_score: float = 0.3,
        connection_ids: Optional[List[str]] = None
    ) -> List[ExternalSearchResult]:
        """
        Search for similar chunks in user's external resources.
        Optionally filter by specific connection IDs.
        """
        if user_id not in self._store or not self._store[user_id]:
            return []

        query_vector = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vector)

        if query_norm == 0:
            return []

        results = []
        for chunk_id, embedding, metadata in self._store[user_id]:
            # Filter by connection if specified
            if connection_ids and metadata["connection_id"] not in connection_ids:
                continue

            # Cosine similarity
            embedding_norm = np.linalg.norm(embedding)
            if embedding_norm == 0:
                continue

            score = float(np.dot(query_vector, embedding) / (query_norm * embedding_norm))

            if score >= min_score:
                chunk = self._chunk_lookup.get(chunk_id)
                if chunk:
                    results.append(ExternalSearchResult(
                        chunk_id=chunk_id,
                        document_id=metadata["document_id"],
                        user_id=user_id,
                        connection_id=metadata["connection_id"],
                        source=metadata["source"],
                        content=chunk.content,
                        score=score,
                        source_name=metadata["source_name"],
                        source_url=metadata.get("source_url"),
                        section_title=metadata.get("section_title"),
                        metadata=metadata
                    ))

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get stats for a user's vector store"""
        chunks = self._store.get(user_id, [])

        # Group by connection
        connections = defaultdict(int)
        for _, _, metadata in chunks:
            connections[metadata["connection_id"]] += 1

        return {
            "total_chunks": len(chunks),
            "connections": dict(connections),
            "dimension": self.dimension
        }

    def remove_document_chunks(self, user_id: str, document_id: str):
        """Remove all chunks for a specific document"""
        if user_id not in self._store:
            return

        # Filter out chunks from this document
        remaining = []
        for chunk_id, embedding, metadata in self._store[user_id]:
            if metadata["document_id"] != document_id:
                remaining.append((chunk_id, embedding, metadata))
            else:
                if chunk_id in self._chunk_lookup:
                    del self._chunk_lookup[chunk_id]

        self._store[user_id] = remaining

    def remove_connection_chunks(self, user_id: str, connection_id: str):
        """Remove all chunks for a specific connection"""
        if user_id not in self._store:
            return

        remaining = []
        for chunk_id, embedding, metadata in self._store[user_id]:
            if metadata["connection_id"] != connection_id:
                remaining.append((chunk_id, embedding, metadata))
            else:
                if chunk_id in self._chunk_lookup:
                    del self._chunk_lookup[chunk_id]

        self._store[user_id] = remaining

    def clear_user(self, user_id: str):
        """Clear all data for a user"""
        if user_id in self._store:
            for chunk_id, _, _ in self._store[user_id]:
                if chunk_id in self._chunk_lookup:
                    del self._chunk_lookup[chunk_id]
            del self._store[user_id]


class ExternalDocumentService:
    """
    Service for managing external resource connections and documents.
    Handles OAuth, sync, chunking, and embedding.
    """

    # Singleton stores
    _vector_store: UserVectorStore = UserVectorStore()
    _connections: Dict[str, ExternalConnection] = {}
    _documents: Dict[str, ExternalDocument] = {}

    # Token encryption key - SECURITY: Required, no default value
    # Uses ENCRYPTION_MASTER_KEY from centralized secrets management
    _ENCRYPTION_KEY = os.environ.get("ENCRYPTION_MASTER_KEY")

    @classmethod
    def _get_encryption_key(cls) -> str:
        """Get encryption key with validation"""
        if not cls._ENCRYPTION_KEY:
            raise RuntimeError(
                "ENCRYPTION_MASTER_KEY environment variable is required. "
                "Generate a secure key with: openssl rand -base64 32"
            )
        return cls._ENCRYPTION_KEY

    def __init__(self):
        self._connector_manager = get_connector_manager()
        self._embedding_service = None
        if EMBEDDING_AVAILABLE:
            try:
                self._embedding_service = NeMoEmbeddingService()
            except Exception as e:
                print(f"[ExternalDocumentService] Embedding service unavailable: {e}")

    # ================== Connection Management ==================

    def get_user_connections(self, user_id: str) -> List[ExternalConnection]:
        """Get all connections for a user"""
        return [
            conn for conn in self._connections.values()
            if conn.user_id == user_id
        ]

    def get_connection(self, connection_id: str) -> Optional[ExternalConnection]:
        """Get a specific connection"""
        return self._connections.get(connection_id)

    def get_connection_by_type(
        self,
        user_id: str,
        resource_type: ExternalResourceType
    ) -> Optional[ExternalConnection]:
        """Get connection by user and resource type"""
        for conn in self._connections.values():
            if conn.user_id == user_id and conn.resource_type == resource_type:
                return conn
        return None

    async def create_connection(
        self,
        user_id: str,
        resource_type: ExternalResourceType,
        api_token: Optional[str] = None,
        config: Optional[Dict] = None
    ) -> ExternalConnection:
        """
        Create a new external resource connection.
        For OAuth resources, this initializes the connection (tokens added after OAuth flow).
        For API token resources, this completes the connection.
        """
        connection_id = f"conn_{uuid.uuid4().hex[:12]}"

        # Determine auth type
        from ..models.external_connection import EXTERNAL_RESOURCE_CONFIGS
        resource_config = EXTERNAL_RESOURCE_CONFIGS.get(resource_type)
        auth_type = resource_config.auth_type if resource_config else AuthType.OAUTH2

        connection = ExternalConnection(
            id=connection_id,
            user_id=user_id,
            resource_type=resource_type,
            auth_type=auth_type,
            status=ConnectionStatus.NOT_CONNECTED,
            resource_config=config or {}
        )

        # For API token auth, store token and validate
        if auth_type == AuthType.API_TOKEN and api_token:
            connection.api_token = self._encrypt_token(api_token)
            connection.status = ConnectionStatus.CONNECTING

            # Validate connection
            connector = self._connector_manager.get_connector(
                resource_type,
                api_token=api_token,
                config=config
            )
            result = await connector.validate_connection()

            if result.status.value == "success":
                connection.status = ConnectionStatus.CONNECTED
            else:
                connection.status = ConnectionStatus.ERROR
                connection.sync_error = result.error

        self._connections[connection_id] = connection
        return connection

    def get_oauth_url(
        self,
        connection_id: str,
        redirect_uri: str
    ) -> Optional[str]:
        """Get OAuth authorization URL for a connection"""
        connection = self._connections.get(connection_id)
        if not connection:
            return None

        # Generate state token
        state = f"{connection_id}:{uuid.uuid4().hex[:8]}"

        connector = self._connector_manager.get_connector(
            connection.resource_type,
            config=connection.resource_config
        )

        try:
            return connector.get_oauth_url(redirect_uri, state)
        except NotImplementedError:
            return None

    async def complete_oauth(
        self,
        connection_id: str,
        code: str,
        redirect_uri: str
    ) -> ExternalConnection:
        """Complete OAuth flow and store tokens"""
        connection = self._connections.get(connection_id)
        if not connection:
            raise ValueError(f"Connection not found: {connection_id}")

        connector = self._connector_manager.get_connector(
            connection.resource_type,
            config=connection.resource_config
        )

        result = await connector.exchange_code(code, redirect_uri)

        if result.status.value == "success":
            tokens = result.data
            connection.access_token = self._encrypt_token(tokens.get("access_token"))
            if tokens.get("refresh_token"):
                connection.refresh_token = self._encrypt_token(tokens.get("refresh_token"))
            if tokens.get("expires_in"):
                connection.token_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=tokens["expires_in"]
                )
            connection.status = ConnectionStatus.CONNECTED
            connection.updated_at = datetime.now(timezone.utc)

            # Store additional metadata
            for key in ["workspace_id", "workspace_name", "bot_id"]:
                if key in tokens:
                    connection.resource_config[key] = tokens[key]
        else:
            connection.status = ConnectionStatus.ERROR
            connection.sync_error = result.error

        self._connections[connection_id] = connection
        return connection

    async def disconnect(self, connection_id: str) -> bool:
        """Disconnect and remove an external resource connection"""
        connection = self._connections.get(connection_id)
        if not connection:
            return False

        # Remove all documents and chunks
        self._vector_store.remove_connection_chunks(
            connection.user_id,
            connection_id
        )

        # Remove documents
        to_remove = [
            doc_id for doc_id, doc in self._documents.items()
            if doc.connection_id == connection_id
        ]
        for doc_id in to_remove:
            del self._documents[doc_id]

        # Remove connection
        del self._connections[connection_id]
        return True

    # ================== Sync Operations ==================

    async def sync_connection(
        self,
        connection_id: str,
        full_sync: bool = False
    ) -> Dict[str, Any]:
        """
        Sync documents from external resource.
        Full sync fetches all documents, incremental only fetches changes.
        """
        connection = self._connections.get(connection_id)
        if not connection:
            raise ValueError(f"Connection not found: {connection_id}")

        if connection.status != ConnectionStatus.CONNECTED:
            raise ValueError(f"Connection not active: {connection.status}")

        # Update status
        connection.status = ConnectionStatus.SYNCING
        connection.sync_status = SyncStatus.IN_PROGRESS
        self._connections[connection_id] = connection

        stats = {
            "documents_synced": 0,
            "documents_added": 0,
            "documents_updated": 0,
            "documents_deleted": 0,
            "errors": []
        }

        try:
            # Get connector
            connector = self._connector_manager.get_connector(
                connection.resource_type,
                access_token=self._decrypt_token(connection.access_token),
                refresh_token=self._decrypt_token(connection.refresh_token) if connection.refresh_token else None,
                api_token=self._decrypt_token(connection.api_token) if connection.api_token else None,
                config=connection.resource_config
            )

            # Determine sync point
            modified_since = None
            if not full_sync and connection.last_sync_at:
                modified_since = connection.last_sync_at

            # Track seen documents for deletion detection
            seen_external_ids = set()

            # List and sync documents
            async for doc_meta in connector.list_documents(modified_since=modified_since):
                try:
                    external_id = doc_meta["external_id"]
                    seen_external_ids.add(external_id)

                    # Check if document exists
                    existing_doc = self._find_document_by_external_id(
                        connection_id, external_id
                    )

                    # Fetch full document
                    result = await connector.fetch_document(external_id)
                    if result.status.value != "success":
                        stats["errors"].append(f"Failed to fetch {external_id}: {result.error}")
                        continue

                    doc_data = result.data

                    if existing_doc:
                        # Check if content changed
                        if existing_doc.content_hash != doc_data.content_hash:
                            # Update document
                            await self._update_document(existing_doc.id, doc_data)
                            stats["documents_updated"] += 1
                    else:
                        # Create new document
                        await self._create_document(
                            connection_id,
                            connection.user_id,
                            connection.resource_type,
                            doc_data
                        )
                        stats["documents_added"] += 1

                    stats["documents_synced"] += 1

                except Exception as e:
                    stats["errors"].append(f"Error processing document: {e}")

            # Handle deleted documents (only for full sync)
            if full_sync:
                for doc_id, doc in list(self._documents.items()):
                    if (doc.connection_id == connection_id and
                        doc.external_id not in seen_external_ids):
                        # Document was deleted from source
                        await self._delete_document(doc_id)
                        stats["documents_deleted"] += 1

            # Update connection
            connection.status = ConnectionStatus.CONNECTED
            connection.sync_status = SyncStatus.COMPLETED
            connection.last_sync_at = datetime.now(timezone.utc)
            connection.sync_error = None
            connection.document_count = len([
                d for d in self._documents.values()
                if d.connection_id == connection_id
            ])
            connection.chunk_count = self._vector_store.get_user_stats(
                connection.user_id
            ).get("connections", {}).get(connection_id, 0)
            self._connections[connection_id] = connection

        except Exception as e:
            connection.status = ConnectionStatus.ERROR
            connection.sync_status = SyncStatus.FAILED
            connection.sync_error = str(e)
            self._connections[connection_id] = connection
            stats["errors"].append(str(e))

        return stats

    def _find_document_by_external_id(
        self,
        connection_id: str,
        external_id: str
    ) -> Optional[ExternalDocument]:
        """Find document by connection and external ID"""
        for doc in self._documents.values():
            if doc.connection_id == connection_id and doc.external_id == external_id:
                return doc
        return None

    async def _create_document(
        self,
        connection_id: str,
        user_id: str,
        source: ExternalResourceType,
        doc_data
    ) -> ExternalDocument:
        """Create new document from connector data"""
        doc_id = f"edoc_{uuid.uuid4().hex[:12]}"

        doc = ExternalDocument(
            id=doc_id,
            user_id=user_id,
            connection_id=connection_id,
            source=source,
            external_id=doc_data.external_id,
            external_url=doc_data.external_url,
            title=doc_data.title,
            path=doc_data.path,
            mime_type=doc_data.mime_type,
            sections=doc_data.sections,
            text_content=doc_data.content,
            metadata=doc_data.metadata,
            status=ExternalDocumentStatus.DISCOVERED,
            external_modified_at=doc_data.modified_at,
            content_hash=doc_data.content_hash
        )

        self._documents[doc_id] = doc

        # Process document (chunk and embed)
        await self._process_document(doc_id)

        return doc

    async def _update_document(self, doc_id: str, doc_data) -> ExternalDocument:
        """Update existing document with new content"""
        doc = self._documents.get(doc_id)
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")

        # Remove old chunks
        self._vector_store.remove_document_chunks(doc.user_id, doc_id)

        # Update document
        doc.title = doc_data.title
        doc.path = doc_data.path
        doc.sections = doc_data.sections
        doc.text_content = doc_data.content
        doc.metadata = doc_data.metadata
        doc.external_modified_at = doc_data.modified_at
        doc.content_hash = doc_data.content_hash
        doc.status = ExternalDocumentStatus.DISCOVERED
        doc.updated_at = datetime.now(timezone.utc)

        self._documents[doc_id] = doc

        # Reprocess document
        await self._process_document(doc_id)

        return doc

    async def _delete_document(self, doc_id: str):
        """Delete a document and its chunks"""
        doc = self._documents.get(doc_id)
        if not doc:
            return

        # Remove chunks
        self._vector_store.remove_document_chunks(doc.user_id, doc_id)

        # Remove document
        del self._documents[doc_id]

    # ================== Document Processing ==================

    async def _process_document(self, doc_id: str):
        """Process document: chunk and embed"""
        doc = self._documents.get(doc_id)
        if not doc or not doc.text_content:
            return

        try:
            # Chunking
            doc.status = ExternalDocumentStatus.CHUNKING
            self._documents[doc_id] = doc

            chunks = self._chunk_document(doc)

            if not chunks:
                doc.status = ExternalDocumentStatus.ERROR
                doc.error_message = "No content to chunk"
                self._documents[doc_id] = doc
                return

            # Embedding
            doc.status = ExternalDocumentStatus.EMBEDDING
            self._documents[doc_id] = doc

            if self._embedding_service:
                await self._generate_embeddings(chunks)

            # Store in vector store
            self._vector_store.add_chunks(doc.user_id, chunks)

            # Update document
            doc.chunk_count = len(chunks)
            doc.status = ExternalDocumentStatus.READY
            doc.last_synced_at = datetime.now(timezone.utc)
            self._documents[doc_id] = doc

        except Exception as e:
            doc.status = ExternalDocumentStatus.ERROR
            doc.error_message = str(e)
            self._documents[doc_id] = doc
            print(f"[ExternalDocumentService] Processing error: {e}")

    def _chunk_document(self, doc: ExternalDocument) -> List[ExternalChunk]:
        """Chunk document content"""
        chunks = []
        chunk_size = 800
        overlap_chars = 100

        # Use sections if available
        if doc.sections:
            for section in doc.sections:
                section_content = section.get("content", "")
                if isinstance(section_content, list):
                    section_content = "\n".join(str(c) for c in section_content)

                section_title = section.get("title", "")
                section_type = section.get("type", "text")

                # Special handling for code and tables
                if section_type in ["code", "table"]:
                    chunks.append(self._create_chunk(
                        doc, section_content, len(chunks),
                        section_title=section_title,
                        is_code=(section_type == "code"),
                        is_table=(section_type == "table")
                    ))
                else:
                    # Split large sections
                    section_chunks = self._split_text(
                        section_content, chunk_size, overlap_chars
                    )
                    for chunk_text in section_chunks:
                        chunks.append(self._create_chunk(
                            doc, chunk_text, len(chunks),
                            section_title=section_title
                        ))
        else:
            # Chunk plain text
            text_chunks = self._split_text(
                doc.text_content, chunk_size, overlap_chars
            )
            for chunk_text in text_chunks:
                chunks.append(self._create_chunk(doc, chunk_text, len(chunks)))

        return chunks

    def _split_text(
        self,
        text: str,
        chunk_size: int,
        overlap: int
    ) -> List[str]:
        """Split text into chunks with overlap"""
        if not text or not text.strip():
            return []

        chunks = []
        paragraphs = text.split("\n\n")

        current_chunk = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += "\n\n" + para if current_chunk else para
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                # Create overlap
                words = current_chunk.split()
                overlap_word_count = min(20, len(words) // 5)
                overlap_text = " ".join(words[-overlap_word_count:]) if overlap_word_count > 0 else ""

                current_chunk = overlap_text + " " + para if overlap_text else para

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _create_chunk(
        self,
        doc: ExternalDocument,
        content: str,
        index: int,
        section_title: Optional[str] = None,
        is_code: bool = False,
        is_table: bool = False
    ) -> ExternalChunk:
        """Create a chunk object"""
        chunk_id = f"echunk_{uuid.uuid4().hex[:8]}"

        return ExternalChunk(
            id=chunk_id,
            user_id=doc.user_id,
            document_id=doc.id,
            connection_id=doc.connection_id,
            source=doc.source,
            content=content,
            index=index,
            source_name=doc.title,
            source_url=doc.external_url,
            section_title=section_title,
            is_code=is_code,
            is_table=is_table,
            metadata={
                "path": doc.path,
                "is_code": is_code,
                "is_table": is_table
            }
        )

    async def _generate_embeddings(self, chunks: List[ExternalChunk]):
        """Generate embeddings for chunks"""
        if not self._embedding_service:
            return

        try:
            contents = [c.content for c in chunks]

            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                self._embedding_service.embed_batch,
                contents,
                "passage"
            )

            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding

        except Exception as e:
            print(f"[ExternalDocumentService] Embedding generation failed: {e}")

    # ================== Search ==================

    async def search_user_resources(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        min_score: float = 0.3,
        connection_ids: Optional[List[str]] = None
    ) -> List[ExternalSearchResult]:
        """Search user's external resources"""
        if not self._embedding_service:
            return []

        # Check if user has any connections
        user_connections = self.get_user_connections(user_id)
        if not user_connections:
            return []

        try:
            # Generate query embedding
            loop = asyncio.get_event_loop()
            query_embedding = await loop.run_in_executor(
                None,
                self._embedding_service.embed_text,
                query,
                "query"
            )

            # Search vector store
            results = self._vector_store.search(
                user_id,
                query_embedding,
                top_k,
                min_score,
                connection_ids
            )

            return results

        except Exception as e:
            print(f"[ExternalDocumentService] Search error: {e}")
            return []

    # ================== Utility Methods ==================

    def _encrypt_token(self, token: Optional[str]) -> Optional[str]:
        """Encrypt token for storage (simplified - use proper encryption in production)"""
        if not token:
            return None
        # In production, use proper encryption (e.g., Fernet, AWS KMS)
        import base64
        return base64.b64encode(token.encode()).decode()

    def _decrypt_token(self, encrypted: Optional[str]) -> Optional[str]:
        """Decrypt token for use"""
        if not encrypted:
            return None
        import base64
        try:
            return base64.b64decode(encrypted.encode()).decode()
        except Exception:
            return encrypted

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics for a user's external resources"""
        connections = self.get_user_connections(user_id)
        documents = [d for d in self._documents.values() if d.user_id == user_id]
        vector_stats = self._vector_store.get_user_stats(user_id)

        return {
            "total_connections": len(connections),
            "active_connections": len([c for c in connections if c.status == ConnectionStatus.CONNECTED]),
            "total_documents": len(documents),
            "ready_documents": len([d for d in documents if d.status == ExternalDocumentStatus.READY]),
            "total_chunks": vector_stats["total_chunks"],
            "by_connection": vector_stats["connections"],
            "by_source": {
                rt.value: len([c for c in connections if c.resource_type == rt])
                for rt in ExternalResourceType
            }
        }

    def get_available_resources(self) -> Dict[str, Dict]:
        """Get available external resource types"""
        return self._connector_manager.get_available_resources()


# Singleton instance
_external_document_service: Optional[ExternalDocumentService] = None


def get_external_document_service() -> ExternalDocumentService:
    """Get or create external document service instance"""
    global _external_document_service
    if _external_document_service is None:
        _external_document_service = ExternalDocumentService()
    return _external_document_service
