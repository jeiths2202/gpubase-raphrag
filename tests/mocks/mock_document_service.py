"""
Mock Document Service

Provides in-memory document storage and management
without requiring file system or database access.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid


class MockDocumentService:
    """
    Mock document service for testing.

    Features:
    - In-memory document storage
    - File upload simulation
    - Document metadata management
    - No external dependencies
    """

    def __init__(self):
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._chunks: Dict[str, List[Dict[str, Any]]] = {}
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._call_history: List[Dict[str, Any]] = []

        # Add some default test documents
        self._add_default_documents()

    def _add_default_documents(self) -> None:
        """Add default test documents"""
        self._documents = {
            "doc_test_001": {
                "id": "doc_test_001",
                "filename": "test_document.pdf",
                "original_name": "Test Document.pdf",
                "file_size": 1024000,
                "mime_type": "application/pdf",
                "document_type": "pdf",
                "status": "completed",
                "chunks_count": 10,
                "entities_count": 5,
                "embedding_status": "completed",
                "language": "en",
                "processing_mode": "text_only",
                "vlm_processed": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "content": "This is test document content for testing purposes."
            },
            "doc_test_002": {
                "id": "doc_test_002",
                "filename": "test_image_doc.pdf",
                "original_name": "Test Image Document.pdf",
                "file_size": 2048000,
                "mime_type": "application/pdf",
                "document_type": "pdf",
                "status": "completed",
                "chunks_count": 15,
                "entities_count": 8,
                "embedding_status": "completed",
                "language": "ko",
                "processing_mode": "multimodal",
                "vlm_processed": True,
                "has_images": True,
                "image_count": 3,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "content": "이것은 테스트 문서 내용입니다."
            }
        }

    async def list_documents(
        self,
        page: int = 1,
        limit: int = 20,
        search: str = None,
        status: str = None,
        document_type: str = None
    ) -> Dict[str, Any]:
        """List documents with filtering and pagination"""
        self._call_history.append({
            "method": "list_documents",
            "page": page,
            "limit": limit,
            "search": search,
            "status": status,
            "document_type": document_type,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        documents = []

        for doc_id, doc in self._documents.items():
            # Apply filters
            if search and search.lower() not in doc["filename"].lower():
                continue
            if status and doc["status"] != status:
                continue
            if document_type and doc.get("document_type") != document_type:
                continue

            documents.append(self._format_document(doc))

        # Sort by created_at descending
        documents.sort(key=lambda x: x["created_at"], reverse=True)

        total = len(documents)
        start = (page - 1) * limit
        end = start + limit

        return {
            "documents": documents[start:end],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit
        }

    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID"""
        self._call_history.append({
            "method": "get_document",
            "document_id": document_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        doc = self._documents.get(document_id)
        return self._format_document(doc) if doc else None

    async def upload_document(
        self,
        file_content: bytes,
        filename: str,
        display_name: str = None,
        language: str = "auto",
        tags: List[str] = None,
        processing_mode: str = "text_only",
        enable_vlm: bool = False
    ) -> Dict[str, Any]:
        """Upload and process a document"""
        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        task_id = f"task_{uuid.uuid4().hex[:12]}"

        self._call_history.append({
            "method": "upload_document",
            "document_id": doc_id,
            "filename": filename,
            "file_size": len(file_content),
            "processing_mode": processing_mode,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Determine MIME type from filename
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
        mime_types = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain",
            "md": "text/markdown",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
        }
        mime_type = mime_types.get(ext, "application/octet-stream")

        # Create document
        doc = {
            "id": doc_id,
            "filename": filename,
            "original_name": display_name or filename,
            "file_size": len(file_content),
            "mime_type": mime_type,
            "document_type": ext,
            "status": "processing",
            "chunks_count": 0,
            "entities_count": 0,
            "embedding_status": "pending",
            "language": language,
            "processing_mode": processing_mode,
            "vlm_processed": False,
            "tags": tags or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "content": file_content.decode("utf-8", errors="ignore") if isinstance(file_content, bytes) else str(file_content)
        }

        self._documents[doc_id] = doc

        # Create processing task
        self._tasks[task_id] = {
            "id": task_id,
            "document_id": doc_id,
            "status": "processing",
            "progress": 0,
            "started_at": datetime.now(timezone.utc).isoformat()
        }

        # Simulate instant completion for testing
        doc["status"] = "completed"
        doc["chunks_count"] = len(file_content) // 100 + 1
        doc["embedding_status"] = "completed"
        self._tasks[task_id]["status"] = "completed"
        self._tasks[task_id]["progress"] = 100

        return {
            "document_id": doc_id,
            "task_id": task_id,
            "filename": filename,
            "status": "completed",
            "message": "Document uploaded and processed successfully"
        }

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document"""
        self._call_history.append({
            "method": "delete_document",
            "document_id": document_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        if document_id in self._documents:
            del self._documents[document_id]
            # Remove associated chunks
            if document_id in self._chunks:
                del self._chunks[document_id]
            return True
        return False

    async def get_document_chunks(
        self,
        document_id: str,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Get chunks for a document"""
        self._call_history.append({
            "method": "get_document_chunks",
            "document_id": document_id,
            "page": page,
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        doc = self._documents.get(document_id)
        if not doc:
            return {"chunks": [], "total": 0}

        # Generate mock chunks if not exists
        if document_id not in self._chunks:
            self._chunks[document_id] = self._generate_mock_chunks(doc)

        chunks = self._chunks[document_id]
        total = len(chunks)
        start = (page - 1) * limit
        end = start + limit

        return {
            "chunks": chunks[start:end],
            "total": total,
            "page": page,
            "limit": limit
        }

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get processing task status"""
        return self._tasks.get(task_id)

    def _format_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format document for response"""
        if not doc:
            return None
        return {
            "id": doc["id"],
            "filename": doc["filename"],
            "original_name": doc.get("original_name", doc["filename"]),
            "file_size": doc["file_size"],
            "mime_type": doc["mime_type"],
            "document_type": doc.get("document_type", "pdf"),
            "status": doc["status"],
            "chunks_count": doc.get("chunks_count", 0),
            "entities_count": doc.get("entities_count", 0),
            "embedding_status": doc.get("embedding_status", "pending"),
            "language": doc.get("language", "auto"),
            "processing_mode": doc.get("processing_mode", "text_only"),
            "vlm_processed": doc.get("vlm_processed", False),
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"]
        }

    def _generate_mock_chunks(self, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate mock chunks for a document"""
        chunks = []
        content = doc.get("content", "Mock document content.")
        chunk_count = doc.get("chunks_count", 5)

        for i in range(chunk_count):
            chunks.append({
                "id": f"chunk_{doc['id']}_{i}",
                "document_id": doc["id"],
                "content": f"Chunk {i+1}: {content[:100]}...",
                "page_number": i // 3 + 1,
                "chunk_index": i,
                "metadata": {
                    "source": doc["filename"],
                    "page": i // 3 + 1
                }
            })

        return chunks

    # ==================== Test Helpers ====================

    def add_test_document(
        self,
        document_id: str = None,
        filename: str = "test.pdf",
        content: str = "Test content",
        status: str = "completed",
        **kwargs
    ) -> Dict[str, Any]:
        """Add a test document"""
        doc_id = document_id or f"doc_{uuid.uuid4().hex[:12]}"

        doc = {
            "id": doc_id,
            "filename": filename,
            "original_name": kwargs.get("original_name", filename),
            "file_size": len(content),
            "mime_type": kwargs.get("mime_type", "application/pdf"),
            "document_type": kwargs.get("document_type", "pdf"),
            "status": status,
            "chunks_count": kwargs.get("chunks_count", 5),
            "entities_count": kwargs.get("entities_count", 0),
            "embedding_status": kwargs.get("embedding_status", "completed"),
            "language": kwargs.get("language", "en"),
            "processing_mode": kwargs.get("processing_mode", "text_only"),
            "vlm_processed": kwargs.get("vlm_processed", False),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "content": content
        }

        self._documents[doc_id] = doc
        return doc

    def get_call_history(self) -> List[Dict[str, Any]]:
        """Get call history for assertions"""
        return self._call_history

    def get_document_count(self) -> int:
        """Get total document count"""
        return len(self._documents)

    def reset(self) -> None:
        """Reset mock state to default"""
        self._call_history.clear()
        self._chunks.clear()
        self._tasks.clear()
        self._add_default_documents()
