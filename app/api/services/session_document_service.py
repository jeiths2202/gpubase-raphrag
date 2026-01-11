"""
Session Document Service
Handles document upload, parsing, chunking, and embedding for chat session context
Uses in-memory vector store for session-scoped retrieval
"""
import asyncio
import uuid
import hashlib
import numpy as np
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import sys
import os
import re

# Add src directory for embeddings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

try:
    from embeddings import NeMoEmbeddingService
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False

from .document_parser import DocumentParserFactory, get_document_parser_factory
from ..models.session_document import (
    SessionDocument, SessionDocumentType, SessionDocumentStatus,
    SessionChunk, SessionContext, SessionSearchResult,
    SessionDocumentListItem
)


class InMemoryVectorStore:
    """
    In-memory vector store for session documents.
    Uses numpy for efficient similarity search.
    Session-scoped and automatically cleaned up.
    """

    def __init__(self, dimension: int = 4096):
        self.dimension = dimension
        # session_id -> list of (chunk_id, embedding, metadata)
        self._store: Dict[str, List[Tuple[str, np.ndarray, Dict]]] = defaultdict(list)
        self._chunk_lookup: Dict[str, SessionChunk] = {}

    def add_chunks(
        self,
        session_id: str,
        chunks: List[SessionChunk]
    ):
        """Add chunks with embeddings to the store"""
        for chunk in chunks:
            if chunk.embedding:
                embedding_array = np.array(chunk.embedding, dtype=np.float32)
                self._store[session_id].append((
                    chunk.id,
                    embedding_array,
                    {
                        "document_id": chunk.document_id,
                        "source_name": chunk.source_name,
                        "page_number": chunk.page_number,
                        "index": chunk.index
                    }
                ))
                self._chunk_lookup[chunk.id] = chunk

    def search(
        self,
        session_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[SessionSearchResult]:
        """
        Search for similar chunks in session using cosine similarity
        """
        if session_id not in self._store or not self._store[session_id]:
            return []

        query_vector = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vector)

        if query_norm == 0:
            return []

        results = []
        for chunk_id, embedding, metadata in self._store[session_id]:
            # Cosine similarity
            embedding_norm = np.linalg.norm(embedding)
            if embedding_norm == 0:
                continue

            score = float(np.dot(query_vector, embedding) / (query_norm * embedding_norm))

            if score >= min_score:
                chunk = self._chunk_lookup.get(chunk_id)
                if chunk:
                    results.append(SessionSearchResult(
                        chunk_id=chunk_id,
                        document_id=metadata["document_id"],
                        session_id=session_id,
                        content=chunk.content,
                        score=score,
                        source_name=metadata["source_name"],
                        source_type="session",
                        page_number=metadata.get("page_number"),
                        metadata=metadata
                    ))

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def get_session_stats(self, session_id: str) -> Dict[str, int]:
        """Get stats for a session"""
        chunks = self._store.get(session_id, [])
        return {
            "chunk_count": len(chunks),
            "dimension": self.dimension
        }

    def clear_session(self, session_id: str):
        """Clear all chunks for a session"""
        if session_id in self._store:
            # Remove from chunk lookup
            for chunk_id, _, _ in self._store[session_id]:
                if chunk_id in self._chunk_lookup:
                    del self._chunk_lookup[chunk_id]
            del self._store[session_id]

    def get_all_sessions(self) -> List[str]:
        """Get all active session IDs"""
        return list(self._store.keys())


class SessionDocumentService:
    """
    Service for managing session documents with priority-based retrieval.
    Documents are stored in-memory and cleared when session ends.
    """

    # Singleton store
    _vector_store: InMemoryVectorStore = InMemoryVectorStore()
    _sessions: Dict[str, SessionContext] = {}
    _documents: Dict[str, SessionDocument] = {}

    # Session TTL (default 2 hours)
    SESSION_TTL_HOURS = 2

    def __init__(self):
        self._parser_factory = get_document_parser_factory()
        self._embedding_service = None
        if EMBEDDING_AVAILABLE:
            try:
                self._embedding_service = NeMoEmbeddingService()
            except Exception as e:
                print(f"[SessionDocumentService] Embedding service unavailable: {e}")

    def _get_or_create_session(self, session_id: str) -> SessionContext:
        """Get or create a session context"""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionContext(
                session_id=session_id,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=self.SESSION_TTL_HOURS)
            )
        return self._sessions[session_id]

    async def upload_file(
        self,
        session_id: str,
        file_content: bytes,
        filename: str,
        mime_type: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> SessionDocument:
        """
        Upload and process a file for the session.
        """
        doc_id = f"sdoc_{uuid.uuid4().hex[:12]}"

        # Create document record
        doc = SessionDocument(
            id=doc_id,
            session_id=session_id,
            user_id=user_id,
            document_type=SessionDocumentType.FILE,
            filename=filename,
            mime_type=mime_type,
            file_size=len(file_content),
            status=SessionDocumentStatus.PENDING
        )

        self._documents[doc_id] = doc

        # Get or create session
        session = self._get_or_create_session(session_id)
        session.document_ids.append(doc_id)

        # Start async processing
        asyncio.create_task(self._process_document(doc_id, file_content))

        return doc

    async def upload_text(
        self,
        session_id: str,
        text_content: str,
        title: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> SessionDocument:
        """
        Upload pasted text for the session.
        """
        doc_id = f"sdoc_{uuid.uuid4().hex[:12]}"

        # Generate title from content if not provided
        if not title:
            first_line = text_content.strip().split('\n')[0][:50]
            title = first_line if first_line else "Pasted Text"

        doc = SessionDocument(
            id=doc_id,
            session_id=session_id,
            user_id=user_id,
            document_type=SessionDocumentType.TEXT,
            filename=f"{title}.txt",
            mime_type="text/plain",
            file_size=len(text_content.encode('utf-8')),
            original_content=text_content,
            text_content=text_content,
            status=SessionDocumentStatus.PENDING
        )

        self._documents[doc_id] = doc

        # Get or create session
        session = self._get_or_create_session(session_id)
        session.document_ids.append(doc_id)

        # Process text (simpler than file)
        asyncio.create_task(self._process_text_document(doc_id))

        return doc

    async def _process_document(self, doc_id: str, file_content: bytes):
        """Process uploaded file document"""
        doc = self._documents.get(doc_id)
        if not doc:
            return

        try:
            # Parse document
            doc.status = SessionDocumentStatus.PARSING
            self._documents[doc_id] = doc

            parsed = await self._parser_factory.parse_document(
                file_content,
                doc.filename or "unknown",
                doc.mime_type,
                {"extract_tables": True, "extract_images": False}
            )

            if not parsed or not parsed.text_content:
                doc.status = SessionDocumentStatus.ERROR
                doc.error_message = "Failed to parse document"
                self._documents[doc_id] = doc
                return

            doc.text_content = parsed.text_content
            doc.metadata = parsed.metadata

            # Chunk and embed
            await self._chunk_and_embed_document(doc)

        except Exception as e:
            doc.status = SessionDocumentStatus.ERROR
            doc.error_message = str(e)
            self._documents[doc_id] = doc
            print(f"[SessionDocumentService] Processing error: {e}")

    async def _process_text_document(self, doc_id: str):
        """Process pasted text document"""
        doc = self._documents.get(doc_id)
        if not doc:
            return

        try:
            doc.status = SessionDocumentStatus.CHUNKING
            self._documents[doc_id] = doc

            # Chunk and embed
            await self._chunk_and_embed_document(doc)

        except Exception as e:
            doc.status = SessionDocumentStatus.ERROR
            doc.error_message = str(e)
            self._documents[doc_id] = doc

    async def _chunk_and_embed_document(self, doc: SessionDocument):
        """Chunk document and generate embeddings"""
        doc_id = doc.id

        # Chunking
        doc.status = SessionDocumentStatus.CHUNKING
        self._documents[doc_id] = doc

        chunks = self._chunk_text(
            doc.text_content,
            doc_id,
            doc.session_id,
            doc.filename or "Pasted Text"
        )

        if not chunks:
            doc.status = SessionDocumentStatus.ERROR
            doc.error_message = "No content to chunk"
            self._documents[doc_id] = doc
            return

        # Embedding
        doc.status = SessionDocumentStatus.EMBEDDING
        self._documents[doc_id] = doc

        if self._embedding_service:
            await self._generate_embeddings(chunks)

        # Store in vector store
        self._vector_store.add_chunks(doc.session_id, chunks)

        # Update document
        doc.chunks = chunks
        doc.chunk_count = len(chunks)
        doc.status = SessionDocumentStatus.READY
        doc.processed_at = datetime.now(timezone.utc)
        self._documents[doc_id] = doc

        # Update session stats
        session = self._sessions.get(doc.session_id)
        if session:
            session.total_chunks += len(chunks)

    def _chunk_text(
        self,
        text: str,
        document_id: str,
        session_id: str,
        source_name: str
    ) -> List[SessionChunk]:
        """
        Chunk text using semantic boundaries.
        Preserves tables and code blocks as separate chunks.
        """
        if not text or not text.strip():
            return []

        chunks = []
        chunk_size = 800  # Characters per chunk
        overlap_chars = 100

        # Split by headings, paragraphs, and special blocks
        segments = self._split_by_semantic_boundaries(text)

        current_chunk = ""
        current_page = 1

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            # Check for page markers
            if segment.startswith("--- Page") or segment.startswith("=== Page"):
                match = re.search(r'(\d+)', segment)
                if match:
                    current_page = int(match.group(1))
                continue

            # Tables and code blocks get their own chunks
            is_special = (
                segment.startswith("|") or
                segment.startswith("```") or
                segment.startswith("    ") and len(segment) > 100
            )

            if is_special:
                # Save current chunk first
                if current_chunk.strip():
                    chunks.append(self._create_chunk(
                        current_chunk.strip(),
                        document_id,
                        session_id,
                        source_name,
                        len(chunks),
                        current_page
                    ))
                    current_chunk = ""

                # Add special block as its own chunk
                chunks.append(self._create_chunk(
                    segment,
                    document_id,
                    session_id,
                    source_name,
                    len(chunks),
                    current_page,
                    is_table=segment.startswith("|"),
                    is_code=segment.startswith("```")
                ))
            else:
                # Regular text - accumulate
                if len(current_chunk) + len(segment) < chunk_size:
                    current_chunk += "\n\n" + segment if current_chunk else segment
                else:
                    # Save current chunk
                    if current_chunk.strip():
                        chunks.append(self._create_chunk(
                            current_chunk.strip(),
                            document_id,
                            session_id,
                            source_name,
                            len(chunks),
                            current_page
                        ))

                    # Start new chunk with overlap
                    words = current_chunk.split()
                    overlap_word_count = min(20, len(words) // 5)
                    overlap_text = ' '.join(words[-overlap_word_count:]) if overlap_word_count > 0 else ""
                    current_chunk = overlap_text + " " + segment if overlap_text else segment

        # Add final chunk
        if current_chunk.strip():
            chunks.append(self._create_chunk(
                current_chunk.strip(),
                document_id,
                session_id,
                source_name,
                len(chunks),
                current_page
            ))

        return chunks

    def _split_by_semantic_boundaries(self, text: str) -> List[str]:
        """Split text by semantic boundaries (headings, paragraphs, etc.)"""
        # Split by double newlines first
        paragraphs = re.split(r'\n\s*\n', text)

        segments = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Check for heading patterns
            if re.match(r'^#{1,6}\s', para) or re.match(r'^[0-9]+\.\s', para):
                segments.append(para)
            elif para.startswith("|") or para.startswith("```"):
                segments.append(para)
            else:
                segments.append(para)

        return segments

    def _create_chunk(
        self,
        content: str,
        document_id: str,
        session_id: str,
        source_name: str,
        index: int,
        page_number: int,
        is_table: bool = False,
        is_code: bool = False
    ) -> SessionChunk:
        """Create a chunk object"""
        chunk_id = f"schunk_{uuid.uuid4().hex[:8]}"

        metadata = {
            "is_table": is_table,
            "is_code": is_code,
            "char_count": len(content),
            "word_count": len(content.split())
        }

        return SessionChunk(
            id=chunk_id,
            session_id=session_id,
            document_id=document_id,
            content=content,
            index=index,
            source_type="session",
            source_name=source_name,
            page_number=page_number,
            metadata=metadata
        )

    async def _generate_embeddings(self, chunks: List[SessionChunk]):
        """Generate embeddings for chunks using batch processing"""
        if not self._embedding_service:
            return

        try:
            contents = [c.content for c in chunks]

            # Run sync embedding in thread pool
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
            print(f"[SessionDocumentService] Embedding generation failed: {e}")

    async def search_session(
        self,
        session_id: str,
        query: str,
        top_k: int = 5,
        min_score: float = 0.3
    ) -> List[SessionSearchResult]:
        """Search session documents for relevant content"""
        if not self._embedding_service:
            return []

        session = self._sessions.get(session_id)
        if not session or not session.document_ids:
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
                session_id,
                query_embedding,
                top_k,
                min_score
            )

            return results

        except Exception as e:
            print(f"[SessionDocumentService] Search error: {e}")
            return []

    def get_document(self, document_id: str) -> Optional[SessionDocument]:
        """Get session document by ID"""
        return self._documents.get(document_id)

    def list_session_documents(
        self,
        session_id: str
    ) -> List[SessionDocumentListItem]:
        """List all documents for a session"""
        session = self._sessions.get(session_id)
        if not session:
            return []

        items = []
        for doc_id in session.document_ids:
            doc = self._documents.get(doc_id)
            if doc:
                items.append(SessionDocumentListItem(
                    id=doc.id,
                    session_id=doc.session_id,
                    document_type=doc.document_type,
                    filename=doc.filename,
                    status=doc.status,
                    chunk_count=doc.chunk_count,
                    word_count=len(doc.text_content.split()) if doc.text_content else 0,
                    created_at=doc.created_at,
                    error_message=doc.error_message
                ))

        return items

    def get_session_context(self, session_id: str) -> Optional[SessionContext]:
        """Get session context"""
        return self._sessions.get(session_id)

    def delete_session_document(
        self,
        session_id: str,
        document_id: str
    ) -> bool:
        """Delete a document from session"""
        doc = self._documents.get(document_id)
        if not doc or doc.session_id != session_id:
            return False

        # Remove from session
        session = self._sessions.get(session_id)
        if session and document_id in session.document_ids:
            session.document_ids.remove(document_id)
            session.total_chunks -= doc.chunk_count

        # Remove document
        del self._documents[document_id]

        # Note: Chunks remain in vector store until session cleared
        # This is acceptable for session-scoped data

        return True

    def clear_session(self, session_id: str):
        """Clear all documents and data for a session"""
        session = self._sessions.get(session_id)
        if session:
            # Remove all documents
            for doc_id in session.document_ids:
                if doc_id in self._documents:
                    del self._documents[doc_id]

            # Clear vector store
            self._vector_store.clear_session(session_id)

            # Remove session
            del self._sessions[session_id]

    def cleanup_expired_sessions(self):
        """Clean up expired sessions (call periodically)"""
        now = datetime.now(timezone.utc)
        expired = []

        for session_id, session in self._sessions.items():
            if session.expires_at and session.expires_at < now:
                expired.append(session_id)

        for session_id in expired:
            self.clear_session(session_id)

        return len(expired)

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            "active_sessions": len(self._sessions),
            "total_documents": len(self._documents),
            "embedding_available": EMBEDDING_AVAILABLE and self._embedding_service is not None,
            "sessions": {
                sid: {
                    "document_count": len(s.document_ids),
                    "total_chunks": s.total_chunks,
                    "created_at": s.created_at.isoformat(),
                    "expires_at": s.expires_at.isoformat() if s.expires_at else None
                }
                for sid, s in self._sessions.items()
            }
        }


# Singleton instance
_session_document_service: Optional[SessionDocumentService] = None


def get_session_document_service() -> SessionDocumentService:
    """Get or create session document service instance"""
    global _session_document_service
    if _session_document_service is None:
        _session_document_service = SessionDocumentService()
    return _session_document_service
