"""
Document Use Cases
Business logic for document management.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import time
import uuid
import hashlib
import logging

from .base import UseCase, UseCaseResult, UseCaseContext
from ..ports import EmbeddingPort, VectorStorePort
from ..ports.vector_store_port import VectorDocument
from ..repositories import DocumentRepository
from ..repositories.document_repository import DocumentEntity, DocumentStatus, ChunkEntity
from ..events import get_event_bus
from ..events.publishers import DocumentEventPublisher

logger = logging.getLogger(__name__)


# ==================== Input/Output DTOs ====================

@dataclass
class DocumentInput:
    """Input for document upload"""
    name: str
    content: str
    mime_type: str = "text/plain"
    file_size: int = 0
    project_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessDocumentInput:
    """Input for document processing"""
    document_id: str
    chunk_size: int = 512
    chunk_overlap: int = 50
    generate_embeddings: bool = True


@dataclass
class DeleteDocumentInput:
    """Input for document deletion"""
    document_id: str
    soft_delete: bool = True


@dataclass
class DocumentOutput:
    """Output of document operations"""
    document_id: str
    name: str
    status: str
    chunk_count: int = 0
    total_tokens: int = 0
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "name": self.name,
            "status": self.status,
            "chunk_count": self.chunk_count,
            "total_tokens": self.total_tokens,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


@dataclass
class ProcessDocumentOutput:
    """Output of document processing"""
    document_id: str
    chunk_count: int
    total_tokens: int
    vectors_indexed: int
    processing_time_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_count": self.chunk_count,
            "total_tokens": self.total_tokens,
            "vectors_indexed": self.vectors_indexed,
            "processing_time_ms": self.processing_time_ms
        }


# ==================== Use Cases ====================

class UploadDocumentUseCase(UseCase[DocumentInput, DocumentOutput]):
    """
    Upload and store a new document.

    This use case:
    1. Validates document input
    2. Creates document entity
    3. Stores in repository
    4. Publishes document created event

    Processing (chunking, embedding) is handled separately
    to allow async processing.
    """

    def __init__(self, document_repository: DocumentRepository):
        self.document_repo = document_repository

    async def execute(
        self,
        input: DocumentInput,
        context: UseCaseContext
    ) -> UseCaseResult[DocumentOutput]:
        """Execute document upload"""
        start_time = time.time()

        try:
            # 1. Validate
            validation_errors = self._validate(input)
            if validation_errors:
                return UseCaseResult.validation_error(validation_errors)

            # 2. Check for duplicates
            existing = await self.document_repo.get_by_name(
                input.name,
                context.user_id
            )
            if existing:
                return UseCaseResult.failure(
                    f"Document '{input.name}' already exists",
                    "DUPLICATE_DOCUMENT"
                )

            # 3. Create entity
            document = DocumentEntity(
                id=str(uuid.uuid4()),
                name=input.name,
                content=input.content,
                mime_type=input.mime_type,
                file_size=input.file_size or len(input.content.encode('utf-8')),
                status=DocumentStatus.PENDING,
                user_id=context.user_id,
                project_id=input.project_id,
                tags=input.tags,
                metadata=input.metadata
            )

            # 4. Store
            created = await self.document_repo.create(document)

            # 5. Publish event
            await DocumentEventPublisher.document_created(
                document_id=str(created.id),
                document_name=created.name,
                user_id=context.user_id,
                project_id=input.project_id,
                file_size=created.file_size,
                mime_type=created.mime_type
            )

            # 6. Build output
            output = DocumentOutput(
                document_id=str(created.id),
                name=created.name,
                status=created.status.value,
                created_at=created.created_at
            )

            execution_time = int((time.time() - start_time) * 1000)
            result = UseCaseResult.success(output, execution_time)
            self._log_execution(input, context, result)

            return result

        except Exception as e:
            logger.exception(f"Document upload failed: {e}")
            return UseCaseResult.failure(str(e), "UPLOAD_FAILED")

    def _validate(self, input: DocumentInput) -> List[Dict[str, Any]]:
        """Validate document input"""
        errors = []

        if not input.name or len(input.name) < 1:
            errors.append({
                "field": "name",
                "message": "Document name is required"
            })

        if not input.content or len(input.content) < 10:
            errors.append({
                "field": "content",
                "message": "Document content must be at least 10 characters"
            })

        if len(input.content) > 10_000_000:  # 10MB
            errors.append({
                "field": "content",
                "message": "Document content exceeds maximum size"
            })

        return errors


class ProcessDocumentUseCase(UseCase[ProcessDocumentInput, ProcessDocumentOutput]):
    """
    Process document: chunk, embed, and index.

    This use case:
    1. Fetches document
    2. Chunks content
    3. Generates embeddings
    4. Indexes in vector store
    5. Updates document status
    6. Publishes processed event
    """

    def __init__(
        self,
        document_repository: DocumentRepository,
        embedding: EmbeddingPort,
        vector_store: VectorStorePort
    ):
        self.document_repo = document_repository
        self.embedding = embedding
        self.vector_store = vector_store

    async def execute(
        self,
        input: ProcessDocumentInput,
        context: UseCaseContext
    ) -> UseCaseResult[ProcessDocumentOutput]:
        """Execute document processing"""
        start_time = time.time()

        try:
            # 1. Fetch document
            document = await self.document_repo.get_by_id(input.document_id)
            if not document:
                return UseCaseResult.not_found("Document", input.document_id)

            # 2. Update status to processing
            await self.document_repo.update_status(
                input.document_id,
                DocumentStatus.PROCESSING
            )

            # 3. Chunk content
            chunks = self._chunk_content(
                document.content,
                input.chunk_size,
                input.chunk_overlap
            )

            # 4. Generate embeddings
            total_tokens = 0
            chunk_entities = []

            if input.generate_embeddings:
                texts = [c["content"] for c in chunks]
                embedding_result = await self.embedding.embed_texts(texts)
                total_tokens = embedding_result.total_tokens

                for i, (chunk, emb_result) in enumerate(zip(chunks, embedding_result.embeddings)):
                    chunk_entity = ChunkEntity(
                        chunk_id=f"{input.document_id}_chunk_{i}",
                        document_id=input.document_id,
                        content=chunk["content"],
                        chunk_index=i,
                        token_count=emb_result.token_count,
                        embedding=emb_result.embedding,
                        metadata={"start": chunk["start"], "end": chunk["end"]}
                    )
                    chunk_entities.append(chunk_entity)

            # 5. Store chunks
            await self.document_repo.add_chunks(input.document_id, chunk_entities)

            # 6. Index in vector store
            vectors_indexed = 0
            if input.generate_embeddings:
                vector_docs = [
                    VectorDocument(
                        id=c.chunk_id,
                        embedding=c.embedding,
                        content=c.content,
                        metadata={
                            "document_id": input.document_id,
                            "doc_name": document.name,
                            "chunk_index": c.chunk_index
                        }
                    )
                    for c in chunk_entities
                ]

                await self.vector_store.upsert("documents", vector_docs)
                vectors_indexed = len(vector_docs)

            # 7. Update document status
            await self.document_repo.update_status(
                input.document_id,
                DocumentStatus.COMPLETED
            )

            processing_time = int((time.time() - start_time) * 1000)

            # 8. Publish event
            await DocumentEventPublisher.document_processed(
                document_id=input.document_id,
                document_name=document.name,
                user_id=context.user_id,
                chunk_count=len(chunk_entities),
                total_tokens=total_tokens,
                processing_time_ms=processing_time,
                success=True
            )

            # 9. Build output
            output = ProcessDocumentOutput(
                document_id=input.document_id,
                chunk_count=len(chunk_entities),
                total_tokens=total_tokens,
                vectors_indexed=vectors_indexed,
                processing_time_ms=processing_time
            )

            result = UseCaseResult.success(output, processing_time)
            self._log_execution(input, context, result)

            return result

        except Exception as e:
            logger.exception(f"Document processing failed: {e}")

            # Update status to failed
            await self.document_repo.update_status(
                input.document_id,
                DocumentStatus.FAILED,
                str(e)
            )

            # Publish failure event
            await DocumentEventPublisher.document_processed(
                document_id=input.document_id,
                document_name="",
                user_id=context.user_id,
                success=False,
                error_message=str(e)
            )

            return UseCaseResult.failure(str(e), "PROCESSING_FAILED")

    def _chunk_content(
        self,
        content: str,
        chunk_size: int,
        overlap: int
    ) -> List[Dict[str, Any]]:
        """Split content into overlapping chunks"""
        chunks = []
        start = 0

        while start < len(content):
            end = start + chunk_size
            chunk_content = content[start:end]

            # Try to break at sentence boundary
            if end < len(content):
                last_period = chunk_content.rfind('.')
                if last_period > chunk_size * 0.5:
                    end = start + last_period + 1
                    chunk_content = content[start:end]

            chunks.append({
                "content": chunk_content.strip(),
                "start": start,
                "end": end
            })

            start = end - overlap

        return chunks


class DeleteDocumentUseCase(UseCase[DeleteDocumentInput, DocumentOutput]):
    """
    Delete a document.

    This use case:
    1. Validates ownership/permissions
    2. Removes from vector store
    3. Deletes or soft-deletes from repository
    4. Publishes deleted event
    """

    def __init__(
        self,
        document_repository: DocumentRepository,
        vector_store: VectorStorePort
    ):
        self.document_repo = document_repository
        self.vector_store = vector_store

    async def execute(
        self,
        input: DeleteDocumentInput,
        context: UseCaseContext
    ) -> UseCaseResult[DocumentOutput]:
        """Execute document deletion"""
        start_time = time.time()

        try:
            # 1. Fetch document
            document = await self.document_repo.get_by_id(input.document_id)
            if not document:
                return UseCaseResult.not_found("Document", input.document_id)

            # 2. Check ownership
            if document.user_id != context.user_id and not context.is_admin():
                return UseCaseResult.failure(
                    "You don't have permission to delete this document",
                    "PERMISSION_DENIED"
                )

            # 3. Get chunks for cleanup
            chunks = await self.document_repo.get_chunks(input.document_id)
            chunk_ids = [c.chunk_id for c in chunks]

            # 4. Remove from vector store
            if chunk_ids:
                await self.vector_store.delete("documents", chunk_ids)

            # 5. Delete document
            deleted = await self.document_repo.delete(input.document_id)

            if not deleted:
                return UseCaseResult.failure(
                    "Failed to delete document",
                    "DELETE_FAILED"
                )

            # 6. Publish event
            await DocumentEventPublisher.document_deleted(
                document_id=input.document_id,
                document_name=document.name,
                user_id=context.user_id,
                project_id=document.project_id,
                soft_delete=input.soft_delete
            )

            # 7. Build output
            output = DocumentOutput(
                document_id=input.document_id,
                name=document.name,
                status="deleted"
            )

            execution_time = int((time.time() - start_time) * 1000)
            result = UseCaseResult.success(output, execution_time)
            self._log_execution(input, context, result)

            return result

        except Exception as e:
            logger.exception(f"Document deletion failed: {e}")
            return UseCaseResult.failure(str(e), "DELETE_FAILED")
