"""
Dependency Injection for FastAPI

SECURITY FEATURES:
- HttpOnly cookie authentication (prevents XSS token theft)
- Authorization header fallback for API clients
- No DEBUG bypass - authentication always required
- bcrypt password hashing (salted, resistant to rainbow tables)
"""
import logging
import hashlib
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt

from .config import api_settings
from .cookie_auth import get_token_from_request

logger = logging.getLogger(__name__)


# Password hashing utilities (bcrypt with salt)
def hash_password(password: str) -> str:
    """Hash password using bcrypt with auto-generated salt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify password against hash.
    Supports both bcrypt (preferred) and legacy SHA256 hashes for migration.
    """
    try:
        # Try bcrypt first (preferred)
        if hashed.startswith("$2"):  # bcrypt hash prefix
            return bcrypt.checkpw(password.encode(), hashed.encode())
        else:
            # Legacy SHA256 support for existing users (migration path)
            legacy_hash = hashlib.sha256(password.encode()).hexdigest()
            return hashed == legacy_hash
    except Exception:
        return False

# Security scheme (still accepts Authorization header for API clients)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Validate JWT token and return current user.

    SECURITY FEATURES:
    - Accepts token from HttpOnly cookie (preferred, more secure)
    - Falls back to Authorization header for API clients
    - NO DEBUG BYPASS - Authentication is ALWAYS required
    - Token validation includes expiration check
    """
    # Extract token from cookie or header
    # Cookie takes priority (more secure for browser clients)
    authorization_header = None
    if credentials:
        authorization_header = f"Bearer {credentials.credentials}"

    token = get_token_from_request(request, authorization_header)

    # SECURITY: Authentication is ALWAYS required - no bypass for any mode
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "인증이 필요합니다."},
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        payload = jwt.decode(
            token,
            api_settings.JWT_SECRET_KEY,
            algorithms=[api_settings.JWT_ALGORITHM]
        )

        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "AUTH_INVALID_TOKEN", "message": "유효하지 않은 토큰입니다."}
            )

        # Check expiration
        exp = payload.get("exp")
        if exp and datetime.now(timezone.utc) > datetime.fromtimestamp(exp, tz=timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "AUTH_TOKEN_EXPIRED", "message": "토큰이 만료되었습니다."}
            )

        return {
            "id": user_id,
            "username": payload.get("username", ""),
            "email": payload.get("email"),
            "role": payload.get("role", "user"),
            "is_active": True
        }

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID_TOKEN", "message": "유효하지 않은 토큰입니다."}
        )


async def get_admin_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Require admin role"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTH_INSUFFICIENT_PERMISSION", "message": "관리자 권한이 필요합니다."}
        )
    return current_user


# API Key Header scheme
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user_or_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = Depends(api_key_header)
) -> dict:
    """
    Validate JWT token OR API key and return auth context.

    SECURITY FEATURES:
    - Accepts JWT token from HttpOnly cookie or Authorization header
    - Accepts API key from X-API-Key header
    - Returns unified auth context with auth_type indicator

    Returns:
        dict with keys:
        - id: user_id or api_key_id
        - auth_type: "jwt" or "api_key"
        - For JWT: username, email, role, is_active
        - For API Key: api_key_id, allowed_endpoints, allowed_agent_types
    """
    from ..services.api_key_service import get_api_key_service

    # Try JWT authentication first
    authorization_header = None
    if credentials:
        authorization_header = f"Bearer {credentials.credentials}"

    token = get_token_from_request(request, authorization_header)

    if token:
        try:
            payload = jwt.decode(
                token,
                api_settings.JWT_SECRET_KEY,
                algorithms=[api_settings.JWT_ALGORITHM]
            )

            user_id: str = payload.get("sub")
            if user_id:
                exp = payload.get("exp")
                if not exp or datetime.now(timezone.utc) <= datetime.fromtimestamp(exp, tz=timezone.utc):
                    return {
                        "id": user_id,
                        "auth_type": "jwt",
                        "username": payload.get("username", ""),
                        "email": payload.get("email"),
                        "role": payload.get("role", "user"),
                        "is_active": True
                    }
        except JWTError:
            pass  # Try API key next

    # Try API key authentication
    if api_key:
        api_key_service = get_api_key_service()
        if api_key_service:
            result = await api_key_service.validate_api_key(api_key)

            if result.is_valid:
                # Check rate limit
                is_allowed, rate_status = await api_key_service.check_and_increment_rate_limit(
                    result.api_key_id
                )

                if not is_allowed:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "API 요청 한도를 초과했습니다.",
                            "rate_limit": {
                                "minute_remaining": rate_status.minute_remaining if rate_status else 0,
                                "hour_remaining": rate_status.hour_remaining if rate_status else 0,
                                "day_remaining": rate_status.day_remaining if rate_status else 0
                            }
                        }
                    )

                return {
                    "id": str(result.api_key_id),
                    "auth_type": "api_key",
                    "api_key_id": result.api_key_id,
                    "owner_id": result.owner_id,
                    "allowed_endpoints": result.allowed_endpoints,
                    "allowed_agent_types": result.allowed_agent_types,
                    "role": "api_key",  # For compatibility
                    "is_active": True
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "INVALID_API_KEY", "message": result.error or "유효하지 않은 API 키입니다."}
                )

    # No valid authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "AUTH_REQUIRED", "message": "인증이 필요합니다. JWT 토큰 또는 API 키를 제공하세요."},
        headers={"WWW-Authenticate": "Bearer"}
    )


async def get_api_key_only(
    request: Request,
    api_key: Optional[str] = Depends(api_key_header)
) -> dict:
    """
    Validate API key only (no JWT).

    Use this for public endpoints that ONLY accept API keys.

    Returns:
        dict with API key auth context
    """
    from ..services.api_key_service import get_api_key_service

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "API_KEY_REQUIRED", "message": "X-API-Key 헤더가 필요합니다."}
        )

    api_key_service = get_api_key_service()
    if not api_key_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "API Key 서비스를 사용할 수 없습니다."}
        )

    result = await api_key_service.validate_api_key(api_key)

    if not result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_API_KEY", "message": result.error or "유효하지 않은 API 키입니다."}
        )

    # Check rate limit
    is_allowed, rate_status = await api_key_service.check_and_increment_rate_limit(
        result.api_key_id
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "API 요청 한도를 초과했습니다.",
                "rate_limit": {
                    "minute_remaining": rate_status.minute_remaining if rate_status else 0,
                    "hour_remaining": rate_status.hour_remaining if rate_status else 0,
                    "day_remaining": rate_status.day_remaining if rate_status else 0
                }
            }
        )

    # Store request info for usage tracking
    request.state.api_key_id = result.api_key_id
    request.state.client_ip = request.client.host if request.client else None
    request.state.user_agent = request.headers.get("user-agent")

    return {
        "id": str(result.api_key_id),
        "auth_type": "api_key",
        "api_key_id": result.api_key_id,
        "owner_id": result.owner_id,
        "allowed_endpoints": result.allowed_endpoints,
        "allowed_agent_types": result.allowed_agent_types,
        "role": "api_key",
        "is_active": True
    }


# Service Dependencies
# Import actual service implementations
from ..services.rag_service import RAGService, get_rag_service as _get_rag_service
from ..services.stats_service import StatsService, get_stats_service as _get_stats_service
from ..services.health_service import HealthService, get_health_service as _get_health_service
from ..services.conversation_service import ConversationService, get_conversation_service as _get_conversation_service

# PostgreSQL-backed Authentication Service
from ..services.auth_service import get_auth_service


class DocumentService:
    """
    Document Service with multimodal support.
    Handles document upload, parsing, and management.
    Uses PostgreSQL for persistent storage.
    """

    # In-memory cache (loaded from database on startup)
    _documents: dict = {}  # document_id -> document data
    _tasks: dict = {}  # task_id -> task status (in-memory only)
    _chunks: dict = {}  # document_id -> list of chunks
    _db_loaded: bool = False  # Flag to track if documents loaded from DB
    _repository = None  # PostgreSQL repository

    @classmethod
    def _get_document_type(cls, filename: str, mime_type: str = None) -> tuple:
        """Determine document type from filename or MIME type."""
        from ..models.document import EXTENSION_TO_MIME, SUPPORTED_MIME_TYPES, DocumentType
        import os

        ext = os.path.splitext(filename)[1].lower()

        if not mime_type:
            mime_type = EXTENSION_TO_MIME.get(ext, "application/octet-stream")

        doc_type = SUPPORTED_MIME_TYPES.get(mime_type, DocumentType.TEXT)

        return doc_type, mime_type

    @classmethod
    async def _ensure_loaded(cls):
        """Ensure documents are loaded from database."""
        if cls._db_loaded:
            return

        try:
            from ..infrastructure.postgres.document_repository import get_document_repository
            cls._repository = await get_document_repository()

            # Load all documents from database into memory cache
            docs = await cls._repository.get_all_documents_dict()
            cls._documents.update(docs)
            cls._db_loaded = True
            logger.info(f"Loaded {len(docs)} documents from database")
        except Exception as e:
            logger.warning(f"Failed to load documents from database: {e}")
            cls._db_loaded = True  # Prevent repeated failures

    @classmethod
    async def _save_to_db(cls, doc_id: str, doc: dict):
        """Save document to database."""
        if cls._repository is None:
            return

        try:
            await cls._repository.save_document(
                doc_id=doc_id,
                filename=doc.get("filename", ""),
                original_name=doc.get("original_name", ""),
                file_size=doc.get("file_size", 0),
                mime_type=doc.get("mime_type", ""),
                document_type=doc.get("document_type", "text"),
                status=doc.get("status", "processing"),
                language=doc.get("language", "auto"),
                tags=doc.get("tags", []),
                processing_mode=doc.get("processing_mode", "text_only"),
                vlm_processed=doc.get("vlm_processed", False),
                chunks_count=doc.get("chunks_count", 0),
                entities_count=doc.get("entities_count", 0),
                embedding_status=doc.get("embedding_status", "pending"),
                stats=doc.get("stats"),
                processing_info=doc.get("processing_info")
            )
        except Exception as e:
            logger.error(f"Failed to save document to database: {e}")

    @classmethod
    async def _update_status_in_db(cls, doc_id: str, **kwargs):
        """Update document status in database."""
        if cls._repository is None:
            return

        try:
            await cls._repository.update_status(doc_id, **kwargs)
        except Exception as e:
            logger.error(f"Failed to update document status in database: {e}")

    async def list_documents(
        self,
        page: int,
        limit: int,
        search: str = None,
        status: str = None,
        document_type: str = None
    ) -> dict:
        """List documents with filtering."""
        # Ensure documents are loaded from database
        await self._ensure_loaded()

        documents = []

        for doc_id, doc in self._documents.items():
            # Apply filters
            if search and search.lower() not in doc["filename"].lower():
                continue
            if status and doc["status"] != status:
                continue
            if document_type and doc.get("document_type") != document_type:
                continue

            documents.append({
                "id": doc["id"],
                "filename": doc["filename"],
                "original_name": doc["original_name"],
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
            })

        # Sort by created_at descending
        documents.sort(key=lambda x: x["created_at"], reverse=True)

        total = len(documents)
        start = (page - 1) * limit
        end = start + limit

        return {"documents": documents[start:end], "total": total}

    async def upload_document(
        self,
        file_content: bytes,
        filename: str,
        display_name: str = None,
        language: str = "auto",
        tags: list = None,
        processing_mode: str = "text_only",
        enable_vlm: bool = False,
        extract_tables: bool = True,
        extract_images: bool = True
    ) -> dict:
        """
        Upload and process a document.

        Supports: PDF, Word, Excel, PowerPoint, Text, Markdown, CSV, JSON, Images
        """
        import uuid
        import asyncio

        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # Determine document type
        doc_type, mime_type = self._get_document_type(filename)

        # Ensure database connection is ready
        await self._ensure_loaded()

        # Store document metadata
        self._documents[doc_id] = {
            "id": doc_id,
            "filename": display_name or filename,
            "original_name": filename,
            "file_size": len(file_content),
            "mime_type": mime_type,
            "document_type": doc_type.value if hasattr(doc_type, 'value') else doc_type,
            "status": "processing",
            "chunks_count": 0,
            "entities_count": 0,
            "embedding_status": "pending",
            "language": language,
            "tags": tags or [],
            "processing_mode": processing_mode,
            "vlm_processed": False,
            "enable_vlm": enable_vlm,
            "extract_tables": extract_tables,
            "extract_images": extract_images,
            "created_at": now,
            "updated_at": now,
            "stats": None,
            "processing_info": None,
            "multimodal_content": None
        }

        # Save to database for persistence
        await self._save_to_db(doc_id, self._documents[doc_id])

        # Store task status
        self._tasks[task_id] = {
            "document_id": doc_id,
            "status": "processing",
            "current_step": "uploading",
            "steps": [
                {"name": "uploading", "status": "completed", "progress": 100},
                {"name": "parsing", "status": "pending", "progress": 0},
                {"name": "chunking", "status": "pending", "progress": 0},
                {"name": "embedding", "status": "pending", "progress": 0}
            ],
            "overall_progress": 10,
            "started_at": now,
            "estimated_completion": None
        }

        # Start background processing
        asyncio.create_task(self._process_document_async(
            doc_id, task_id, file_content, filename,
            processing_mode, enable_vlm, extract_tables, extract_images
        ))

        return {
            "document_id": doc_id,
            "filename": filename,
            "task_id": task_id
        }

    async def _process_document_async(
        self,
        doc_id: str,
        task_id: str,
        file_content: bytes,
        filename: str,
        processing_mode: str,
        enable_vlm: bool,
        extract_tables: bool,
        extract_images: bool
    ):
        """Process document asynchronously with real parsing."""
        import asyncio
        from ..services.document_parser import get_document_parser_factory

        try:
            # Step 1: Parse document using real parser
            self._update_task(task_id, "parsing", 25)

            # Get VLM service if OCR/VLM processing is enabled
            vlm_service = None
            if processing_mode in ["image_only", "vlm_enhanced"] or enable_vlm:
                try:
                    from ..services.ollama_vlm_service import get_ollama_vlm_service
                    vlm_service = get_ollama_vlm_service()
                except Exception as vlm_err:
                    print(f"VLM service not available, continuing without OCR: {vlm_err}")

            # Use real document parser with VLM service for OCR
            factory = get_document_parser_factory(vlm_service)
            parse_options = {
                "extract_tables": extract_tables,
                "extract_images": extract_images,
                "filename": filename,
                "processing_mode": processing_mode,
                "enable_vlm": enable_vlm,
                "language": "auto"  # Auto-detect language for OCR
            }

            try:
                parsed_doc = await factory.parse_document(
                    file_content,
                    filename,
                    options=parse_options
                )
                # Get real parsed data
                parsed_text = parsed_doc.text_content or ""
                parsed_pages = parsed_doc.pages or []
                parsed_images = parsed_doc.images or []
                parsed_tables = parsed_doc.tables or []
                parsed_metadata = parsed_doc.metadata or {}
            except Exception as parse_error:
                # Fallback if parsing fails
                print(f"Document parsing failed: {parse_error}")
                parsed_text = f"문서 '{filename}'의 내용을 추출할 수 없습니다."
                parsed_pages = [{"page_number": 1, "content": parsed_text}]
                parsed_images = []
                parsed_tables = []
                parsed_metadata = {"pages": 1}

            # Step 2: Chunking
            self._update_task(task_id, "chunking", 50)
            await asyncio.sleep(0.3)

            # Create chunks from actual parsed content with real embeddings
            # Use page-aware chunking to preserve page numbers
            chunks = await self._create_chunks(
                doc_id,
                text=parsed_text,
                parsed_pages=parsed_pages
            )
            self._chunks[doc_id] = chunks

            # Step 2.5: Save chunks to PostgreSQL for LocalRAGService vector search
            await self._save_chunks_to_postgres(doc_id, chunks)

            # Calculate actual statistics
            total_chars = sum(len(page.get("content", "")) for page in parsed_pages)
            avg_chunk_size = total_chars // len(chunks) if chunks else 0

            # Step 3: Embedding
            self._update_task(task_id, "embedding", 75)
            await asyncio.sleep(0.3)

            # Update document with REAL results
            doc = self._documents.get(doc_id)
            if doc:
                doc["status"] = "ready"
                doc["chunks_count"] = len(chunks)
                doc["entities_count"] = 0  # Would need NER for real entity count
                doc["embedding_status"] = "completed"
                doc["vlm_processed"] = enable_vlm
                doc["updated_at"] = datetime.now(timezone.utc)

                # Use REAL statistics from parsed document
                doc["stats"] = {
                    "pages": parsed_metadata.get("pages", len(parsed_pages)),
                    "chunks_count": len(chunks),
                    "entities_count": 0,
                    "avg_chunk_size": avg_chunk_size,
                    "embedding_dimension": 4096,
                    "images_count": len(parsed_images) if extract_images else 0,
                    "tables_count": len(parsed_tables) if extract_tables else 0,
                    "figures_count": 0,
                    "vlm_processed": enable_vlm,
                    "total_characters": total_chars,
                    "title": parsed_metadata.get("title", ""),
                    "author": parsed_metadata.get("author", "")
                }

                # Calculate processing time
                started_at = self._tasks[task_id]["started_at"]
                completed_at = datetime.now(timezone.utc)
                processing_seconds = (completed_at - started_at).total_seconds()

                doc["processing_info"] = {
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "processing_time_seconds": round(processing_seconds, 2)
                }

                # Persist updated status to database
                await self._save_to_db(doc_id, doc)

            # Step 4: Sync to Neo4j
            await self._sync_to_neo4j(doc_id, filename, chunks)

            # Step 5: Store image embeddings if images were extracted
            if extract_images and parsed_images:
                logger.info(f"Storing {len(parsed_images)} image embeddings for {doc_id}")
                await self._store_image_embeddings(
                    doc_id, parsed_images, file_content, filename
                )

            # Complete task
            self._update_task(task_id, "completed", 100)
            self._tasks[task_id]["status"] = "ready"

            # Run automatic quality verification after embedding completes
            await self._run_auto_quality_check(doc_id)

        except Exception as e:
            # Handle error
            if doc_id in self._documents:
                self._documents[doc_id]["status"] = "error"
                # Persist error status to database
                await self._update_status_in_db(doc_id, status="error")
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = "error"
                self._tasks[task_id]["error"] = str(e)

    def _update_task(self, task_id: str, step: str, progress: int):
        """Update task progress."""
        if task_id not in self._tasks:
            return

        task = self._tasks[task_id]
        task["current_step"] = step
        task["overall_progress"] = progress

        # Get step names list
        step_names = [ss["name"] for ss in task["steps"]]

        # Handle "completed" step (not in steps list)
        if step == "completed":
            for s in task["steps"]:
                s["status"] = "completed"
                s["progress"] = 100
            return

        # Check if step exists in steps list
        if step not in step_names:
            return

        step_index = step_names.index(step)

        for i, s in enumerate(task["steps"]):
            if s["name"] == step:
                s["status"] = "in_progress"
                s["progress"] = 50
            elif i < step_index:
                s["status"] = "completed"
                s["progress"] = 100

    async def _create_chunks(
        self,
        doc_id: str,
        text: str = None,
        parsed_pages: list = None,
        chunk_size: int = 500
    ) -> list:
        """
        Create text chunks from document with real embeddings.

        Args:
            doc_id: Document ID
            text: Full text content (fallback if parsed_pages not provided)
            parsed_pages: List of page dicts with 'page_number' and 'content'
            chunk_size: Target chunk size in characters

        Returns:
            List of chunk dicts with embeddings and page numbers
        """
        import uuid
        from ..services.multimodal_embedding import TextEmbeddingService

        def is_valid_chunk(chunk_text: str) -> bool:
            """Filter out low-quality chunks that would be semantically isolated."""
            # Too short chunks lack context
            if len(chunk_text) < 50:
                return False

            # Check alphanumeric ratio (filter out formatting-heavy chunks)
            # Note: 0.15 threshold to allow TOC pages with dots (.....)
            alnum_count = sum(1 for c in chunk_text if c.isalnum())
            total_count = len(chunk_text)
            alnum_ratio = alnum_count / total_count if total_count > 0 else 0
            if alnum_ratio < 0.15:
                return False

            # Filter chunks with too many digits (tables, data, etc.)
            digit_count = sum(1 for c in chunk_text if c.isdigit())
            if total_count > 0 and digit_count / total_count > 0.5:
                return False

            # Filter chunks with very few unique characters (repetitive content)
            unique_chars = len(set(chunk_text.lower()))
            if unique_chars < 10:
                return False

            return True

        raw_chunks = []

        # Use page-aware chunking if parsed_pages provided
        if parsed_pages:
            for page in parsed_pages:
                page_number = page.get("page_number", 1)
                page_content = page.get("content", "")

                if not page_content or not page_content.strip():
                    continue

                # Chunk each page separately to preserve page boundaries
                words = page_content.split()
                current_chunk = []
                current_length = 0

                for word in words:
                    current_chunk.append(word)
                    current_length += len(word) + 1

                    if current_length >= chunk_size:
                        chunk_text = " ".join(current_chunk)
                        if is_valid_chunk(chunk_text):
                            raw_chunks.append({
                                "id": f"chunk_{uuid.uuid4().hex[:8]}",
                                "index": len(raw_chunks),
                                "content": chunk_text,
                                "content_length": len(chunk_text),
                                "has_embedding": False,
                                "embedding": None,
                                "entities": [],
                                "page_number": page_number,
                                "chunk_type": "text",
                                "source_image_id": None,
                                "source_table_id": None,
                                "metadata": {"source_page": page_number}
                            })
                        current_chunk = []
                        current_length = 0

                # Add remaining text from page
                if current_chunk:
                    chunk_text = " ".join(current_chunk)
                    if is_valid_chunk(chunk_text):
                        raw_chunks.append({
                            "id": f"chunk_{uuid.uuid4().hex[:8]}",
                            "index": len(raw_chunks),
                            "content": chunk_text,
                            "content_length": len(chunk_text),
                            "has_embedding": False,
                            "embedding": None,
                            "entities": [],
                            "page_number": page_number,
                            "chunk_type": "text",
                            "source_image_id": None,
                            "source_table_id": None,
                            "metadata": {"source_page": page_number}
                        })
        else:
            # Fallback: chunk full text without page info
            words = (text or "").split()
            current_chunk = []
            current_length = 0

            for word in words:
                current_chunk.append(word)
                current_length += len(word) + 1

                if current_length >= chunk_size:
                    chunk_text = " ".join(current_chunk)
                    if is_valid_chunk(chunk_text):
                        raw_chunks.append({
                            "id": f"chunk_{uuid.uuid4().hex[:8]}",
                            "index": len(raw_chunks),
                            "content": chunk_text,
                            "content_length": len(chunk_text),
                            "has_embedding": False,
                            "embedding": None,
                            "entities": [],
                            "page_number": 1,
                            "chunk_type": "text",
                            "source_image_id": None,
                            "source_table_id": None,
                            "metadata": {}
                        })
                    current_chunk = []
                    current_length = 0

            # Add remaining text
            if current_chunk:
                chunk_text = " ".join(current_chunk)
                if is_valid_chunk(chunk_text):
                    raw_chunks.append({
                        "id": f"chunk_{uuid.uuid4().hex[:8]}",
                        "index": len(raw_chunks),
                        "content": chunk_text,
                        "content_length": len(chunk_text),
                        "has_embedding": False,
                        "embedding": None,
                        "entities": [],
                        "page_number": 1,
                        "chunk_type": "text",
                        "source_image_id": None,
                        "source_table_id": None,
                        "metadata": {}
                    })

        # Generate real embeddings using TextEmbeddingService
        if raw_chunks:
            try:
                embedding_service = TextEmbeddingService()
                texts = [chunk["content"] for chunk in raw_chunks]
                embeddings = await embedding_service.embed_texts(texts)

                for chunk, embedding in zip(raw_chunks, embeddings):
                    chunk["embedding"] = embedding
                    chunk["has_embedding"] = True

                logger.info(f"Generated {len(raw_chunks)} embeddings for document {doc_id}")
            except Exception as e:
                logger.error(f"Failed to generate embeddings for {doc_id}: {e}")
                # Keep chunks without embeddings rather than failing completely

        return raw_chunks

    async def get_upload_status(self, task_id: str) -> dict:
        """Get document upload/processing status."""
        return self._tasks.get(task_id)

    async def get_document(self, document_id: str) -> dict:
        """Get document details."""
        # Ensure documents are loaded from database
        await self._ensure_loaded()

        doc = self._documents.get(document_id)
        if not doc:
            return None

        return {
            **doc,
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"]
        }

    async def delete_document(self, document_id: str) -> dict:
        """Delete a document and all related data from all storage backends."""
        # Ensure documents are loaded from database
        await self._ensure_loaded()

        # Check if document exists in memory cache
        doc_exists_in_cache = document_id in self._documents
        doc = self._documents.get(document_id, {})
        chunks = self._chunks.get(document_id, [])

        deleted_counts = {
            "deleted_chunks": len(chunks),
            "deleted_entities": doc.get("entities_count", 0),
            "deleted_text_chunks": 0,
            "deleted_images": 0,
            "deleted_neo4j_nodes": 0,
            "deleted_rag_profiles": 0
        }

        # 1. Delete from Neo4j (Document and Chunk nodes)
        try:
            deleted_counts["deleted_neo4j_nodes"] = await self._delete_from_neo4j(document_id)
            logger.info(f"Deleted {deleted_counts['deleted_neo4j_nodes']} nodes from Neo4j for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete from Neo4j: {e}")

        # 2. Delete from PostgreSQL text_chunks table
        try:
            deleted_counts["deleted_text_chunks"] = await self._delete_text_chunks(document_id)
            logger.info(f"Deleted {deleted_counts['deleted_text_chunks']} text chunks from PostgreSQL for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete text chunks from PostgreSQL: {e}")

        # 3. Delete from PostgreSQL image_embeddings table
        try:
            deleted_counts["deleted_images"] = await self._delete_image_embeddings(document_id)
            logger.info(f"Deleted {deleted_counts['deleted_images']} images from PostgreSQL for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete images from PostgreSQL: {e}")

        # 4. Delete from PostgreSQL document_rag_profiles table
        try:
            deleted_counts["deleted_rag_profiles"] = await self._delete_rag_profiles(document_id)
            logger.info(f"Deleted {deleted_counts['deleted_rag_profiles']} RAG profile assignments from PostgreSQL for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete RAG profiles from PostgreSQL: {e}")

        # 5. Delete from document repository (original implementation)
        if self._repository:
            try:
                await self._repository.delete_document(document_id)
            except Exception as e:
                logger.error(f"Failed to delete document from repository: {e}")

        # 6. Delete from memory cache (if exists)
        if doc_exists_in_cache:
            del self._documents[document_id]
            if document_id in self._chunks:
                del self._chunks[document_id]

        # Check if any data was actually deleted
        total_deleted = sum([
            deleted_counts["deleted_neo4j_nodes"],
            deleted_counts["deleted_text_chunks"],
            deleted_counts["deleted_images"],
            deleted_counts["deleted_rag_profiles"]
        ])

        if not doc_exists_in_cache and total_deleted == 0:
            # Document doesn't exist and no related data found
            logger.warning(f"Document {document_id} not found in any storage")
            return None

        logger.info(f"Document {document_id} deleted. Stats: {deleted_counts}")

        return deleted_counts

    async def _delete_from_neo4j(self, document_id: str) -> int:
        """Delete document and related chunks from Neo4j."""
        try:
            from langchain_neo4j import Neo4jGraph
            from app.src.config import config

            graph = Neo4jGraph(
                url=config.neo4j.uri,
                username=config.neo4j.user,
                password=config.neo4j.password
            )

            # First, delete Chunk nodes linked to Document via CONTAINS relationship
            chunk_result = graph.query("""
                MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c:Chunk)
                DETACH DELETE c
                RETURN count(*) as deleted_count
            """, params={"doc_id": document_id})

            chunk_count = chunk_result[0]["deleted_count"] if chunk_result else 0

            # Then delete the Document node
            doc_result = graph.query("""
                MATCH (d:Document {id: $doc_id})
                DETACH DELETE d
                RETURN count(*) as deleted_count
            """, params={"doc_id": document_id})

            doc_count = doc_result[0]["deleted_count"] if doc_result else 0

            return chunk_count + doc_count

        except Exception as e:
            logger.error(f"Neo4j deletion error: {e}")
            raise

    async def _delete_text_chunks(self, document_id: str) -> int:
        """Delete text chunks from PostgreSQL."""
        try:
            import asyncpg
            from ..core.config import api_settings

            pool = await asyncpg.create_pool(
                host=api_settings.POSTGRES_HOST,
                port=int(api_settings.POSTGRES_PORT),
                user=api_settings.POSTGRES_USER,
                password=api_settings.POSTGRES_PASSWORD,
                database=api_settings.POSTGRES_DB,
                min_size=1,
                max_size=3
            )

            try:
                async with pool.acquire() as conn:
                    result = await conn.execute("""
                        DELETE FROM text_chunks WHERE document_id = $1
                    """, document_id)
                    # Parse "DELETE N" to get count
                    count = int(result.split()[-1]) if result else 0
                    return count
            finally:
                await pool.close()

        except Exception as e:
            logger.error(f"PostgreSQL text_chunks deletion error: {e}")
            raise

    async def _delete_image_embeddings(self, document_id: str) -> int:
        """Delete image embeddings from PostgreSQL."""
        try:
            import asyncpg
            from ..core.config import api_settings

            pool = await asyncpg.create_pool(
                host=api_settings.POSTGRES_HOST,
                port=int(api_settings.POSTGRES_PORT),
                user=api_settings.POSTGRES_USER,
                password=api_settings.POSTGRES_PASSWORD,
                database=api_settings.POSTGRES_DB,
                min_size=1,
                max_size=3
            )

            try:
                async with pool.acquire() as conn:
                    result = await conn.execute("""
                        DELETE FROM image_embeddings WHERE document_id = $1
                    """, document_id)
                    # Parse "DELETE N" to get count
                    count = int(result.split()[-1]) if result else 0
                    return count
            finally:
                await pool.close()

        except Exception as e:
            logger.error(f"PostgreSQL image_embeddings deletion error: {e}")
            raise

    async def _delete_rag_profiles(self, document_id: str) -> int:
        """Delete RAG profile assignments from PostgreSQL."""
        try:
            import asyncpg
            from ..core.config import api_settings

            pool = await asyncpg.create_pool(
                host=api_settings.POSTGRES_HOST,
                port=int(api_settings.POSTGRES_PORT),
                user=api_settings.POSTGRES_USER,
                password=api_settings.POSTGRES_PASSWORD,
                database=api_settings.POSTGRES_DB,
                min_size=1,
                max_size=3
            )

            try:
                async with pool.acquire() as conn:
                    result = await conn.execute("""
                        DELETE FROM document_rag_profiles WHERE document_id = $1
                    """, document_id)
                    # Parse "DELETE N" to get count
                    count = int(result.split()[-1]) if result else 0
                    return count
            finally:
                await pool.close()

        except Exception as e:
            logger.error(f"PostgreSQL document_rag_profiles deletion error: {e}")
            raise

    async def get_document_chunks(
        self,
        document_id: str,
        page: int,
        limit: int
    ) -> dict:
        """Get document chunks with pagination."""
        # Ensure documents are loaded from database
        await self._ensure_loaded()

        if document_id not in self._documents:
            return None

        chunks = self._chunks.get(document_id, [])
        total = len(chunks)
        start = (page - 1) * limit
        end = start + limit

        return {"chunks": chunks[start:end], "total": total}

    async def reprocess_document(
        self,
        document_id: str,
        processing_mode: str = None,
        enable_vlm: bool = None
    ) -> dict:
        """Reprocess an existing document with different options."""
        # Ensure documents are loaded from database
        await self._ensure_loaded()

        if document_id not in self._documents:
            return None

        doc = self._documents[document_id]

        # Update processing options
        if processing_mode:
            doc["processing_mode"] = processing_mode
        if enable_vlm is not None:
            doc["enable_vlm"] = enable_vlm

        doc["status"] = "processing"
        doc["updated_at"] = datetime.now(timezone.utc)

        # In production, trigger reprocessing here
        return {"document_id": document_id, "status": "reprocessing"}

    # =========================================================================
    # Embedding Quality Verification
    # =========================================================================

    # In-memory storage for quality results
    _quality_results: dict = {}  # document_id -> quality result

    async def verify_embedding_quality(
        self,
        document_id: str,
        sample_size: int = 10
    ) -> dict:
        """
        Verify embedding quality for a document.

        Performs quality tests including:
        - Self-retrieval accuracy
        - Similarity distribution analysis
        - Coverage verification
        """
        from ..services.embedding_quality_service import (
            get_embedding_quality_service,
            EmbeddingQualityResult
        )

        # Ensure documents are loaded
        await self._ensure_loaded()

        if document_id not in self._documents:
            return None

        # Get chunks with embeddings
        chunks = self._chunks.get(document_id, [])
        if not chunks:
            # Return empty result if no chunks
            return self._create_empty_quality_result(document_id, "No chunks available")

        # Run quality verification
        quality_service = get_embedding_quality_service()
        result = await quality_service.verify_document_embeddings(
            document_id=document_id,
            chunks=chunks,
            sample_size=sample_size
        )

        # Convert to dict and store
        result_dict = result.to_dict()

        # Store result
        self._quality_results[document_id] = result_dict

        # Update document with quality summary
        doc = self._documents.get(document_id)
        if doc:
            doc["embedding_quality"] = {
                "overall_score": result_dict["overall_score"],
                "quality_level": result_dict["quality_level"],
                "verified_at": result_dict["verified_at"],
                "has_issues": len(result_dict.get("issues", [])) > 0
            }
            doc["updated_at"] = datetime.now(timezone.utc)

            # Persist to database if available
            await self._save_to_db(document_id, doc)

        return result_dict

    async def get_embedding_quality(self, document_id: str) -> dict:
        """Get stored embedding quality verification result."""
        # Ensure documents are loaded
        await self._ensure_loaded()

        # Check cached result
        if document_id in self._quality_results:
            return self._quality_results[document_id]

        # Check if quality info exists in document
        doc = self._documents.get(document_id)
        if doc and "embedding_quality" in doc:
            # Return summary if full result not cached
            quality_summary = doc["embedding_quality"]
            return {
                "document_id": document_id,
                "verified_at": quality_summary.get("verified_at"),
                "overall_score": quality_summary.get("overall_score", 0),
                "quality_level": quality_summary.get("quality_level", "poor"),
                "retrieval_accuracy": 0,
                "avg_similarity": 0,
                "similarity_std": 0,
                "coverage_score": 0,
                "embedding_dimension": doc.get("stats", {}).get("embedding_dimension", 0),
                "chunks_tested": 0,
                "chunks_total": doc.get("chunks_count", 0),
                "test_results": [],
                "issues": ["Full results not available - please run verification again"],
                "recommendations": []
            }

        return None

    def _create_empty_quality_result(self, document_id: str, reason: str) -> dict:
        """Create an empty quality result when verification cannot be performed."""
        return {
            "document_id": document_id,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "overall_score": 0.0,
            "quality_level": "poor",
            "retrieval_accuracy": 0.0,
            "avg_similarity": 0.0,
            "similarity_std": 0.0,
            "coverage_score": 0.0,
            "embedding_dimension": 0,
            "chunks_tested": 0,
            "chunks_total": 0,
            "test_results": [],
            "issues": [reason],
            "recommendations": ["Re-process document to generate embeddings"]
        }

    async def _run_auto_quality_check(self, document_id: str):
        """
        Automatically run quality check after embedding completes.
        Called from _process_document_async.
        """
        try:
            logger.info(f"Running automatic quality verification for document {document_id}")
            result = await self.verify_embedding_quality(document_id, sample_size=5)

            if result:
                quality_level = result.get("quality_level", "unknown")
                overall_score = result.get("overall_score", 0)
                logger.info(
                    f"Quality verification completed for {document_id}: "
                    f"score={overall_score:.2f}, level={quality_level}"
                )

                # Log issues if any
                issues = result.get("issues", [])
                if issues:
                    logger.warning(f"Quality issues found for {document_id}: {issues}")

        except Exception as e:
            logger.error(f"Auto quality check failed for {document_id}: {e}")

    # =========================================================================
    # Re-Embedding
    # =========================================================================

    async def re_embed_document(
        self,
        document_id: str,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        processing_mode: str = "text_only",
        enable_vlm: bool = False,
        extract_tables: bool = True,
        extract_images: bool = True
    ) -> dict:
        """
        Re-embed a document with custom parameters.

        Args:
            document_id: Document ID to re-embed
            chunk_size: Size of each text chunk in characters
            chunk_overlap: Overlap between consecutive chunks
            processing_mode: Processing mode (text_only, vlm_enhanced, multimodal, ocr)
            enable_vlm: Enable Vision Language Model processing
            extract_tables: Extract tables from document
            extract_images: Extract images from document

        Returns:
            dict with task_id and status
        """
        import asyncio
        import uuid

        # Ensure documents are loaded
        await self._ensure_loaded()

        if document_id not in self._documents:
            return None

        doc = self._documents[document_id]

        # Create new task for re-embedding
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # Update document status
        doc["status"] = "processing"
        doc["embedding_status"] = "pending"
        doc["processing_mode"] = processing_mode
        doc["enable_vlm"] = enable_vlm
        doc["extract_tables"] = extract_tables
        doc["extract_images"] = extract_images
        doc["updated_at"] = now

        # Clear existing chunks and quality results
        if document_id in self._chunks:
            del self._chunks[document_id]
        if document_id in self._quality_results:
            del self._quality_results[document_id]

        # Store new task status
        self._tasks[task_id] = {
            "document_id": document_id,
            "status": "processing",
            "current_step": "re-chunking",
            "steps": [
                {"name": "re-chunking", "status": "pending", "progress": 0},
                {"name": "embedding", "status": "pending", "progress": 0},
                {"name": "quality-check", "status": "pending", "progress": 0}
            ],
            "overall_progress": 10,
            "started_at": now,
            "estimated_completion": None,
            "parameters": {
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "processing_mode": processing_mode,
                "enable_vlm": enable_vlm,
                "extract_tables": extract_tables,
                "extract_images": extract_images
            }
        }

        # Persist status update to database
        await self._save_to_db(document_id, doc)

        # Start background re-embedding process
        asyncio.create_task(self._re_embed_document_async(
            document_id, task_id, chunk_size, chunk_overlap,
            processing_mode, enable_vlm, extract_tables, extract_images
        ))

        return {
            "task_id": task_id,
            "status": "processing"
        }

    async def _re_embed_document_async(
        self,
        document_id: str,
        task_id: str,
        chunk_size: int,
        chunk_overlap: int,
        processing_mode: str,
        enable_vlm: bool,
        extract_tables: bool,
        extract_images: bool
    ):
        """Process re-embedding asynchronously."""
        import asyncio

        try:
            doc = self._documents.get(document_id)
            if not doc:
                return

            # Step 1: Re-chunking with new parameters
            self._update_reembed_task(task_id, "re-chunking", 30)

            # Get original document content (would need to store or re-read)
            # For now, use placeholder text
            original_text = f"문서 '{doc.get('filename', 'unknown')}'의 내용입니다. " * 100
            await asyncio.sleep(0.5)

            # Create new chunks with custom parameters and real embeddings
            chunks = await self._create_chunks_with_overlap(
                document_id, original_text, chunk_size, chunk_overlap
            )
            self._chunks[document_id] = chunks

            # Step 2: Generate embeddings
            self._update_reembed_task(task_id, "embedding", 60)
            await asyncio.sleep(0.5)

            # Step 3: Quality check
            self._update_reembed_task(task_id, "quality-check", 80)

            # Update document with new stats
            doc["status"] = "ready"
            doc["chunks_count"] = len(chunks)
            doc["embedding_status"] = "completed"
            doc["vlm_processed"] = enable_vlm
            doc["updated_at"] = datetime.now(timezone.utc)

            if doc.get("stats"):
                doc["stats"]["chunks_count"] = len(chunks)
                doc["stats"]["avg_chunk_size"] = chunk_size
                doc["stats"]["vlm_processed"] = enable_vlm

            # Calculate processing time
            started_at = self._tasks[task_id]["started_at"]
            completed_at = datetime.now(timezone.utc)
            processing_seconds = (completed_at - started_at).total_seconds()

            doc["processing_info"] = {
                "started_at": started_at,
                "completed_at": completed_at,
                "processing_time_seconds": round(processing_seconds, 2)
            }

            # Persist to database
            await self._save_to_db(document_id, doc)

            # Complete task
            self._update_reembed_task(task_id, "completed", 100)
            self._tasks[task_id]["status"] = "ready"

            # Run automatic quality verification
            await self._run_auto_quality_check(document_id)

            logger.info(f"Re-embedding completed for document {document_id}")

        except Exception as e:
            logger.error(f"Re-embedding failed for {document_id}: {e}")
            if document_id in self._documents:
                self._documents[document_id]["status"] = "error"
                await self._update_status_in_db(document_id, status="error")
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = "error"
                self._tasks[task_id]["error"] = str(e)

    def _update_reembed_task(self, task_id: str, step: str, progress: int):
        """Update re-embed task progress."""
        if task_id not in self._tasks:
            return

        task = self._tasks[task_id]
        task["current_step"] = step
        task["overall_progress"] = progress

        step_names = [s["name"] for s in task["steps"]]

        if step == "completed":
            for s in task["steps"]:
                s["status"] = "completed"
                s["progress"] = 100
            return

        if step not in step_names:
            return

        step_index = step_names.index(step)

        for i, s in enumerate(task["steps"]):
            if s["name"] == step:
                s["status"] = "in_progress"
                s["progress"] = 50
            elif i < step_index:
                s["status"] = "completed"
                s["progress"] = 100

    async def _create_chunks_with_overlap(
        self,
        doc_id: str,
        text: str,
        chunk_size: int = 512,
        chunk_overlap: int = 50
    ) -> list:
        """Create text chunks with configurable size and overlap using real embeddings."""
        import uuid
        from ..services.multimodal_embedding import TextEmbeddingService

        raw_chunks = []

        # Split by characters with overlap
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end].strip()

            if chunk_text:
                raw_chunks.append({
                    "id": f"chunk_{uuid.uuid4().hex[:8]}",
                    "index": len(raw_chunks),
                    "content": chunk_text,
                    "content_length": len(chunk_text),
                    "has_embedding": False,
                    "embedding": None,
                    "entities": [],
                    "page_number": 1,
                    "chunk_type": "text",
                    "source_image_id": None,
                    "source_table_id": None,
                    "metadata": {
                        "chunk_size": chunk_size,
                        "chunk_overlap": chunk_overlap
                    }
                })

            # Move forward with overlap
            start = end - chunk_overlap if end < len(text) else len(text)

            # Prevent infinite loop
            if start >= len(text) or (end == len(text) and start == end - chunk_overlap):
                break

        # Generate real embeddings using TextEmbeddingService
        if raw_chunks:
            try:
                embedding_service = TextEmbeddingService()
                texts = [chunk["content"] for chunk in raw_chunks]
                embeddings = await embedding_service.embed_texts(texts)

                for chunk, embedding in zip(raw_chunks, embeddings):
                    chunk["embedding"] = embedding
                    chunk["has_embedding"] = True

                logger.info(f"Generated {len(raw_chunks)} embeddings for document {doc_id}")
            except Exception as e:
                logger.error(f"Failed to generate embeddings for {doc_id}: {e}")

        return raw_chunks

    @classmethod
    async def _save_chunks_to_postgres(cls, doc_id: str, chunks: list):
        """
        Save chunks to PostgreSQL's text_chunks table for LocalRAGService vector search.

        This enables the LocalRAGService to search documents using PostgreSQL's pgvector
        extension, complementing the Neo4j storage for graph-based retrieval.
        """
        try:
            import asyncpg
            from ..infrastructure.postgres.text_chunk_repository import PostgresTextChunkRepository
            from ..core.config import api_settings

            # Create a connection pool for PostgreSQL
            pool = await asyncpg.create_pool(
                host=api_settings.POSTGRES_HOST,
                port=int(api_settings.POSTGRES_PORT),
                user=api_settings.POSTGRES_USER,
                password=api_settings.POSTGRES_PASSWORD,
                database=api_settings.POSTGRES_DB,
                min_size=1,
                max_size=3
            )

            try:
                repo = PostgresTextChunkRepository(pool)

                # Save chunks with embeddings and page numbers
                saved_count = await repo.save_chunks_batch(chunks, doc_id)
                logger.info(f"Saved {saved_count}/{len(chunks)} chunks to PostgreSQL for document {doc_id}")
            finally:
                await pool.close()

        except Exception as e:
            logger.error(f"Failed to save chunks to PostgreSQL for {doc_id}: {e}")
            # Don't fail the entire upload - Neo4j storage is still available

    @classmethod
    async def _sync_to_neo4j(cls, doc_id: str, filename: str, chunks: list):
        """Sync document and chunks to Neo4j for graph-based retrieval."""
        try:
            from langchain_neo4j import Neo4jGraph
            from config import config

            graph = Neo4jGraph(
                url=config.neo4j.uri,
                username=config.neo4j.user,
                password=config.neo4j.password
            )

            # Create Document node
            graph.query(
                """
                MERGE (d:Document {id: $doc_id})
                SET d.filename = $filename,
                    d.type = 'upload',
                    d.indexed_at = datetime(),
                    d.chunk_count = $chunk_count
                """,
                {
                    "doc_id": doc_id,
                    "filename": filename,
                    "chunk_count": len(chunks)
                }
            )

            # Index chunks with embeddings and page numbers
            for chunk in chunks:
                chunk_id = chunk.get("id", f"chunk_{doc_id}_{chunk.get('index', 0)}")
                embedding = chunk.get("embedding", [])
                page_number = chunk.get("page_number", 1)

                if embedding:
                    graph.query(
                        """
                        MERGE (c:Chunk {id: $chunk_id})
                        SET c.content = $content,
                            c.index = $index,
                            c.page_number = $page_number,
                            c.embedding = $embedding,
                            c.source_type = 'upload'
                        WITH c
                        MATCH (d:Document {id: $doc_id})
                        MERGE (d)-[:CONTAINS]->(c)
                        """,
                        {
                            "chunk_id": chunk_id,
                            "content": chunk.get("content", ""),
                            "index": chunk.get("index", 0),
                            "page_number": page_number,
                            "embedding": embedding,
                            "doc_id": doc_id
                        }
                    )
                else:
                    graph.query(
                        """
                        MERGE (c:Chunk {id: $chunk_id})
                        SET c.content = $content,
                            c.index = $index,
                            c.page_number = $page_number,
                            c.source_type = 'upload'
                        WITH c
                        MATCH (d:Document {id: $doc_id})
                        MERGE (d)-[:CONTAINS]->(c)
                        """,
                        {
                            "chunk_id": chunk_id,
                            "content": chunk.get("content", ""),
                            "index": chunk.get("index", 0),
                            "page_number": page_number,
                            "doc_id": doc_id
                        }
                    )

            logger.info(f"Synced document {doc_id} with {len(chunks)} chunks to Neo4j")

        except ImportError:
            logger.warning("Neo4j dependencies not available, skipping sync")
        except Exception as e:
            logger.error(f"Failed to sync to Neo4j for {doc_id}: {e}")

    @classmethod
    async def _store_image_embeddings(
        cls,
        doc_id: str,
        parsed_images: list,
        file_content: bytes,
        filename: str
    ):
        """Store image embeddings to PostgreSQL with VLM-generated descriptions.

        Uses ImageEmbeddingService to:
        1. Generate descriptions via VLM (port 12803)
        2. Generate embeddings via NIM (port 12801)
        3. Store both description and embedding in PostgreSQL
        """
        try:
            from ..services.multimodal_embedding import ImageEmbeddingService
            from ..repositories.image_embedding_repository import ImageEmbeddingEntity

            repository = await _get_image_embedding_repository()
            embedding_service = ImageEmbeddingService()

            stored_count = 0
            skipped_count = 0
            vlm_success_count = 0

            for idx, img_info in enumerate(parsed_images):
                try:
                    image_id = f"{doc_id}_img_{idx:03d}"

                    # Get image data from parsed image info
                    image_data = img_info.get("data", b"") if isinstance(img_info, dict) else getattr(img_info, "data", b"")
                    if not image_data:
                        skipped_count += 1
                        continue

                    # Get image metadata
                    page_number = img_info.get("page_number", 1) if isinstance(img_info, dict) else getattr(img_info, "page_number", 1)
                    width = img_info.get("width", 0) if isinstance(img_info, dict) else getattr(img_info, "width", 0)
                    height = img_info.get("height", 0) if isinstance(img_info, dict) else getattr(img_info, "height", 0)

                    # Use document context for VLM description generation
                    document_context = f"Document: {filename}, Page {page_number}"

                    # Generate VLM description AND embedding together
                    # This uses VLM to analyze the image and generate a description,
                    # then embeds that description for semantic search
                    vlm_result = await embedding_service.describe_and_embed_image(
                        image_data=image_data,
                        context=document_context,
                        use_cache=True
                    )

                    # Use VLM-generated description (fallback to placeholder if VLM fails)
                    description = vlm_result.get("description", "")
                    embedding = vlm_result.get("embedding", [0.0] * 4096)
                    has_vlm_description = vlm_result.get("has_embedding", False)

                    if has_vlm_description:
                        vlm_success_count += 1
                        logger.info(f"VLM description generated for image {idx} on page {page_number}: {len(description)} chars")
                    else:
                        # Fallback to placeholder if VLM failed
                        placeholder = img_info.get("description", "") if isinstance(img_info, dict) else getattr(img_info, "description", "")
                        if not description:
                            description = placeholder or f"Image on page {page_number}"
                        logger.warning(f"VLM description failed for image {idx}, using placeholder")

                    # Create entity with VLM-generated description
                    entity = ImageEmbeddingEntity(
                        id=None,  # Will be generated
                        document_id=doc_id,
                        image_id=image_id,
                        page_number=page_number,
                        image_data=image_data,
                        mime_type="image/png",
                        width=width,
                        height=height,
                        file_size=len(image_data),
                        description=description,
                        embedding=embedding,
                        metadata={
                            "source_file": filename,
                            "has_vlm_description": has_vlm_description,
                            "vlm_confidence": vlm_result.get("confidence", 0.0)
                        }
                    )

                    await repository.store_image(entity)
                    stored_count += 1

                except Exception as img_error:
                    logger.warning(f"Failed to store image {idx} for {doc_id}: {img_error}")

            logger.info(
                f"Stored {stored_count} image embeddings for {doc_id} "
                f"(VLM descriptions: {vlm_success_count}, skipped: {skipped_count})"
            )

        except Exception as e:
            logger.error(f"Failed to store image embeddings for {doc_id}: {e}")


class HistoryService:
    """Mock History Service with enhanced conversation features"""

    _conversations: dict = {}  # conversation_id -> {title, queries, ...}
    _queries: dict = {}  # query_id -> query data

    async def list_history(self, user_id: str, page: int, limit: int, **filters) -> dict:
        return {"history": [], "total": 0}

    async def get_history_detail(self, query_id: str) -> dict:
        return self._queries.get(query_id)

    async def delete_history(self, query_id: str) -> bool:
        if query_id in self._queries:
            del self._queries[query_id]
            return True
        return False

    async def list_conversations(self, user_id: str, page: int, limit: int) -> dict:
        convs = [
            {
                "id": cid,
                "title": c.get("title", "Untitled"),
                "queries_count": len(c.get("queries", [])),
                "last_query_at": c.get("last_query_at"),
                "created_at": c.get("created_at")
            }
            for cid, c in self._conversations.items()
            if c.get("user_id") == user_id
        ]
        total = len(convs)
        start = (page - 1) * limit
        end = start + limit
        return {"conversations": convs[start:end], "total": total}

    async def create_conversation(self, user_id: str, title: str) -> dict:
        import uuid
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        self._conversations[conv_id] = {
            "id": conv_id,
            "title": title,
            "user_id": user_id,
            "queries": [],
            "last_query_at": None,
            "created_at": now.isoformat()
        }

        return {
            "id": conv_id,
            "title": title,
            "queries_count": 0,
            "last_query_at": None,
            "created_at": now
        }

    async def delete_conversation(self, conversation_id: str) -> dict:
        if conversation_id in self._conversations:
            conv = self._conversations[conversation_id]
            deleted_count = len(conv.get("queries", []))
            del self._conversations[conversation_id]
            return {"deleted_queries": deleted_count}
        return None

    async def export_conversation(
        self,
        conversation_id: str,
        format: str,
        include_sources: bool
    ) -> dict:
        """Export conversation to various formats"""
        if conversation_id not in self._conversations:
            return None

        conv = self._conversations[conversation_id]
        queries = conv.get("queries", [])

        if format == "markdown":
            content = f"# {conv.get('title', 'Conversation')}\n\n"
            content += f"*Exported: {datetime.now(timezone.utc).isoformat()}*\n\n---\n\n"
            for q in queries:
                content += f"## Q: {q.get('question', '')}\n\n"
                content += f"{q.get('answer', '')}\n\n"
                if include_sources and q.get("sources"):
                    content += "### Sources:\n"
                    for src in q.get("sources", []):
                        content += f"- {src.get('doc_name')}: {src.get('content', '')[:100]}...\n"
                content += "\n---\n\n"
            filename = f"conversation_{conversation_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
        elif format == "json":
            import json
            content = json.dumps({
                "title": conv.get("title"),
                "created_at": conv.get("created_at"),
                "queries": queries
            }, indent=2, ensure_ascii=False)
            filename = f"conversation_{conversation_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
        elif format == "html":
            content = f"<html><head><title>{conv.get('title', 'Conversation')}</title></head><body>\n"
            content += f"<h1>{conv.get('title', 'Conversation')}</h1>\n"
            for q in queries:
                content += f"<div class='qa'>\n"
                content += f"<h3>Q: {q.get('question', '')}</h3>\n"
                content += f"<p>{q.get('answer', '')}</p>\n"
                if include_sources and q.get("sources"):
                    content += "<ul class='sources'>\n"
                    for src in q.get("sources", []):
                        content += f"<li>{src.get('doc_name')}</li>\n"
                    content += "</ul>\n"
                content += "</div>\n"
            content += "</body></html>"
            filename = f"conversation_{conversation_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.html"
        else:
            content = f"{conv.get('title', 'Conversation')}\n\n"
            for q in queries:
                content += f"Q: {q.get('question', '')}\nA: {q.get('answer', '')}\n\n"
            filename = f"conversation_{conversation_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.txt"

        return {
            "format": format,
            "filename": filename,
            "content": content,
            "query_count": len(queries),
            "export_date": datetime.now(timezone.utc).isoformat()
        }

    async def branch_conversation(
        self,
        conversation_id: str,
        from_query_id: str,
        new_title: str,
        user_id: str
    ) -> dict:
        """Branch conversation from a specific point"""
        import uuid

        if conversation_id not in self._conversations:
            return None

        conv = self._conversations[conversation_id]
        queries = conv.get("queries", [])

        # Find the query index
        query_idx = None
        for i, q in enumerate(queries):
            if q.get("id") == from_query_id:
                query_idx = i
                break

        if query_idx is None:
            return None

        # Create new conversation with queries up to and including the branch point
        new_conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        self._conversations[new_conv_id] = {
            "id": new_conv_id,
            "title": new_title or f"Branch of {conv.get('title', 'Untitled')}",
            "user_id": user_id,
            "queries": queries[:query_idx + 1].copy(),
            "branched_from": {
                "conversation_id": conversation_id,
                "query_id": from_query_id
            },
            "last_query_at": now.isoformat(),
            "created_at": now.isoformat()
        }

        return {
            "id": new_conv_id,
            "title": new_title or f"Branch of {conv.get('title', 'Untitled')}",
            "queries_count": query_idx + 1,
            "last_query_at": now,
            "created_at": now
        }

    async def get_suggested_questions(
        self,
        conversation_id: str,
        limit: int = 5
    ) -> list:
        """Get suggested follow-up questions based on conversation context"""
        if conversation_id not in self._conversations:
            return []

        conv = self._conversations[conversation_id]
        queries = conv.get("queries", [])

        # In production, this would use LLM to generate contextual questions
        # For now, return mock suggestions based on last query
        if not queries:
            return [
                "문서의 주요 내용은 무엇인가요?",
                "가장 중요한 개념을 설명해주세요.",
                "이 주제에 대한 예시를 보여주세요.",
                "관련된 다른 주제는 무엇인가요?",
                "핵심 용어를 정의해주세요."
            ][:limit]

        last_query = queries[-1]
        topic = last_query.get("question", "")[:30]

        suggestions = [
            f"{topic}에 대해 더 자세히 설명해주세요.",
            f"이와 관련된 예시를 보여주세요.",
            "이 정보의 출처는 어디인가요?",
            "비슷한 다른 개념은 무엇이 있나요?",
            "실제 적용 사례를 알려주세요.",
            "이것의 장단점은 무엇인가요?",
            "초보자를 위해 쉽게 설명해주세요."
        ]

        return suggestions[:limit]




class SettingsService:
    """Mock Settings Service"""

    async def get_settings(self) -> dict:
        return {
            "rag": {
                "default_strategy": "auto",
                "top_k": 5,
                "vector_weight": 0.5,
                "chunk_size": 1000,
                "chunk_overlap": 200
            },
            "llm": {
                "temperature": 0.1,
                "max_tokens": 2048
            },
            "ui": {
                "language": "auto",
                "theme": "dark",
                "show_sources": True
            }
        }

    async def update_settings(self, updates: dict) -> bool:
        return True


class AuthService:
    """Auth Service with registration and email verification

    SECURITY NOTE:
    - No hardcoded users - admin must be initialized via environment variable
    - Use ADMIN_INITIAL_PASSWORD environment variable to set initial admin password
    - In production, use a proper user database instead of in-memory storage
    """

    # In-memory storage (replace with database in production)
    # SECURITY: No hardcoded users - admin must be initialized at startup
    _users: dict = {}
    _pending_verifications: dict = {}  # email -> {code, user_data, expires_at}
    _verified_emails: set = set()
    _sso_tokens: dict = {}  # token -> {email, created_at}
    _admin_initialized: bool = False

    @classmethod
    async def initialize_admin_user(cls) -> bool:
        """
        Initialize admin user from environment variable.

        Call this at application startup. The admin password must be set via
        ADMIN_INITIAL_PASSWORD environment variable.

        Returns:
            True if admin was initialized, False if already exists or env var not set
        """
        import os
        import hashlib

        if cls._admin_initialized:
            return False

        if "admin" in cls._users:
            cls._admin_initialized = True
            return False

        admin_password = os.environ.get("ADMIN_INITIAL_PASSWORD")
        if not admin_password:
            # Log warning but don't fail - allows running without admin
            import logging
            logging.getLogger(__name__).warning(
                "ADMIN_INITIAL_PASSWORD not set. No admin user will be created. "
                "Set this environment variable to create an initial admin user."
            )
            return False

        # Validate password strength
        if len(admin_password) < 12:
            raise ValueError(
                "ADMIN_INITIAL_PASSWORD must be at least 12 characters. "
                "Generate a secure password for production use."
            )

        # Check for insecure passwords
        insecure_passwords = ["admin", "password", "123456", "admin123", "password123"]
        if admin_password.lower() in insecure_passwords:
            raise ValueError(
                "ADMIN_INITIAL_PASSWORD contains an insecure default value. "
                "Use a strong, unique password."
            )

        admin_email = os.environ.get("ADMIN_EMAIL", "admin@localhost")

        cls._users["admin"] = {
            "id": "user_admin",
            "username": "admin",
            "email": admin_email,
            "password_hash": hash_password(admin_password),  # bcrypt with salt
            "role": "admin",
            "is_verified": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_active": True
        }
        cls._verified_emails.add(admin_email)
        cls._admin_initialized = True

        import logging
        logging.getLogger(__name__).info(
            f"Admin user initialized with email: {admin_email}"
        )
        return True

    async def authenticate(self, username: str, password: str) -> dict:
        """Authenticate user with username and password"""
        # Check registered users
        if username in self._users:
            user = self._users[username]
            # Use bcrypt verification (with legacy SHA256 fallback for migration)
            if verify_password(password, user["password_hash"]) and user.get("is_verified", False):
                if not user.get("is_active", True):
                    return None  # User is deactivated
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": user.get("role", "user")
                }
        return None

    async def register_user(self, user_id: str, email: str, password: str) -> dict:
        """Register a new user and send verification email"""
        import random
        import uuid

        # Check if user_id already exists
        if user_id in self._users:
            return {"error": "USER_EXISTS", "message": "이미 존재하는 사용자 ID입니다."}

        # Check if email already registered
        for u in self._users.values():
            if u["email"] == email:
                return {"error": "EMAIL_EXISTS", "message": "이미 등록된 이메일입니다."}

        # Generate verification code
        verification_code = str(random.randint(100000, 999999))

        # Hash password with bcrypt (salted)
        password_hashed = hash_password(password)

        # Store pending verification
        self._pending_verifications[email] = {
            "code": verification_code,
            "user_data": {
                "id": f"user_{uuid.uuid4().hex[:12]}",
                "username": user_id,
                "email": email,
                "password_hash": password_hashed,
                "role": "user",
                "is_verified": False
            },
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)
        }

        # Send verification email (mock for now)
        await self._send_verification_email(email, verification_code)

        return {
            "success": True,
            "user_id": user_id,
            "email": email,
            "message": "인증 코드가 이메일로 발송되었습니다."
        }

    async def verify_email(self, email: str, code: str) -> dict:
        """Verify email with code"""
        if email not in self._pending_verifications:
            return {"error": "NO_PENDING", "message": "인증 대기 중인 이메일이 없습니다."}

        pending = self._pending_verifications[email]

        # Check expiration
        if datetime.now(timezone.utc) > pending["expires_at"]:
            del self._pending_verifications[email]
            return {"error": "CODE_EXPIRED", "message": "인증 코드가 만료되었습니다."}

        # Verify code
        if pending["code"] != code:
            return {"error": "INVALID_CODE", "message": "잘못된 인증 코드입니다."}

        # Create user
        user_data = pending["user_data"]
        user_data["is_verified"] = True
        self._users[user_data["username"]] = user_data
        self._verified_emails.add(email)

        # Clean up
        del self._pending_verifications[email]

        return {
            "success": True,
            "user": {
                "id": user_data["id"],
                "username": user_data["username"],
                "email": user_data["email"],
                "role": user_data["role"]
            }
        }

    async def resend_verification(self, email: str) -> dict:
        """Resend verification code"""
        import random

        if email not in self._pending_verifications:
            return {"error": "NO_PENDING", "message": "인증 대기 중인 이메일이 없습니다."}

        # Generate new code
        new_code = str(random.randint(100000, 999999))
        self._pending_verifications[email]["code"] = new_code
        self._pending_verifications[email]["expires_at"] = datetime.now(timezone.utc) + timedelta(minutes=10)

        # Send email
        await self._send_verification_email(email, new_code)

        return {"success": True, "message": "새 인증 코드가 발송되었습니다."}

    async def _send_verification_email(self, email: str, code: str) -> bool:
        """Send verification email (mock implementation)"""
        # TODO: Implement actual email sending (SMTP, SendGrid, etc.)
        # SECURITY: Don't log verification codes - only log that email was sent
        logger.debug(f"[EMAIL] Verification email sent to {email}")
        return True

    async def authenticate_google(self, credential: str) -> dict:
        """
        Authenticate with Google OAuth access token.

        Args:
            credential: Google OAuth access token from frontend

        Returns:
            User dict with id, username, email, role, provider, picture
        """
        import httpx

        try:
            # Verify access token by fetching user info from Google
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {credential}"}
                )

                if response.status_code != 200:
                    print(f"[GOOGLE AUTH] Failed to verify token: {response.status_code}")
                    return None

                userinfo = response.json()

                # Extract user info from Google response
                google_id = userinfo.get("sub")
                email = userinfo.get("email")
                name = userinfo.get("name", email.split("@")[0] if email else "Google User")
                picture = userinfo.get("picture")

                if not google_id or not email:
                    print("[GOOGLE AUTH] Missing required fields in Google response")
                    return None

                print(f"[GOOGLE AUTH] Successfully verified: {email}")

                return {
                    "id": f"google_{google_id}",
                    "username": name,
                    "email": email,
                    "name": name,
                    "picture": picture,
                    "role": "user",
                    "provider": "google"
                }

        except Exception as e:
            print(f"[GOOGLE AUTH] Error: {e}")
            return None

    async def initiate_sso(self, email: str) -> dict:
        """Initiate corporate SSO flow"""
        # NOTE: Corporate email validation temporarily disabled for debugging
        # TODO: Re-enable validation after resolving configuration loading issues

        # Generate SSO token and store it temporarily
        import uuid
        token = uuid.uuid4().hex

        # Store token with email and timestamp (valid for 5 minutes)
        self._sso_tokens[token] = {
            "email": email,
            "created_at": datetime.now(timezone.utc)
        }

        # Clean up old tokens (older than 5 minutes)
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        self._sso_tokens = {
            k: v for k, v in self._sso_tokens.items()
            if v["created_at"] > cutoff_time
        }

        # TODO: Implement actual SSO (SAML/OIDC) flow
        # For now, return SSO URL mock
        return {
            "success": True,
            "sso_url": f"/auth/sso/callback?token={token}",
            "message": "SSO 인증 페이지로 이동합니다."
        }

    async def handle_sso_callback(self, token: str) -> dict:
        """Handle SSO callback and authenticate user"""
        # Validate token
        if token not in self._sso_tokens:
            return {
                "error": "INVALID_TOKEN",
                "message": "유효하지 않은 SSO 토큰입니다."
            }

        token_data = self._sso_tokens[token]

        # Check token expiration (5 minutes)
        if datetime.now(timezone.utc) - token_data["created_at"] > timedelta(minutes=5):
            del self._sso_tokens[token]
            return {
                "error": "TOKEN_EXPIRED",
                "message": "SSO 토큰이 만료되었습니다."
            }

        email = token_data["email"]

        # Clean up used token
        del self._sso_tokens[token]

        # Find or create user based on email
        username = email.split("@")[0]  # Use email prefix as username

        # Check if user exists
        user = None
        for existing_user in self._users.values():
            if existing_user.get("email") == email:
                user = existing_user
                break

        # Create user if doesn't exist
        if not user:
            user_id = f"user_{username}"
            user = {
                "id": user_id,
                "username": username,
                "email": email,
                "role": "user",  # Default role for SSO users
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "auth_method": "sso"
            }
            self._users[username] = user

        # Update last login
        user["last_login_at"] = datetime.now(timezone.utc).isoformat()

        return {
            "success": True,
            "user": user
        }

    async def create_access_token(self, user: dict) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=api_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": user["id"],
            "username": user["username"],
            "email": user.get("email", ""),
            "role": user.get("role", "user"),
            "exp": expire
        }
        return jwt.encode(payload, api_settings.JWT_SECRET_KEY, algorithm=api_settings.JWT_ALGORITHM)

    async def create_refresh_token(self, user: dict) -> str:
        expire = datetime.now(timezone.utc) + timedelta(days=api_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {
            "sub": user["id"],
            "type": "refresh",
            "exp": expire
        }
        return jwt.encode(payload, api_settings.JWT_SECRET_KEY, algorithm=api_settings.JWT_ALGORITHM)

    async def verify_refresh_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, api_settings.JWT_SECRET_KEY, algorithms=[api_settings.JWT_ALGORITHM])
            if payload.get("type") != "refresh":
                return None
            return {"id": payload.get("sub"), "username": "", "role": "user"}
        except JWTError:
            return None

    async def invalidate_tokens(self, user_id: str) -> bool:
        # TODO: Implement token blacklist
        return True

    # User Management Methods (Admin)
    async def list_users(self, page: int = 1, limit: int = 20, search: str = None) -> dict:
        """List all users with pagination"""
        users_list = []
        for username, user in self._users.items():
            if search and search.lower() not in username.lower() and search.lower() not in user.get("email", "").lower():
                continue
            users_list.append({
                "id": user["id"],
                "username": user["username"],
                "email": user.get("email", ""),
                "role": user.get("role", "user"),
                "is_active": user.get("is_active", True),
                "is_verified": user.get("is_verified", False),
                "created_at": user.get("created_at", "")
            })

        total = len(users_list)
        start = (page - 1) * limit
        end = start + limit
        paginated = users_list[start:end]

        return {
            "users": paginated,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }

    async def get_user(self, user_id: str) -> dict:
        """Get user by ID"""
        for user in self._users.values():
            if user["id"] == user_id:
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user.get("email", ""),
                    "role": user.get("role", "user"),
                    "is_active": user.get("is_active", True),
                    "is_verified": user.get("is_verified", False),
                    "created_at": user.get("created_at", "")
                }
        return None

    async def update_user(self, user_id: str, updates: dict) -> dict:
        """Update user details"""
        for username, user in self._users.items():
            if user["id"] == user_id:
                # Update allowed fields
                if "role" in updates:
                    user["role"] = updates["role"]
                if "is_active" in updates:
                    user["is_active"] = updates["is_active"]
                if "email" in updates:
                    user["email"] = updates["email"]

                self._users[username] = user
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user.get("email", ""),
                    "role": user.get("role", "user"),
                    "is_active": user.get("is_active", True),
                    "is_verified": user.get("is_verified", False)
                }
        return None

    async def delete_user(self, user_id: str) -> bool:
        """Delete user by ID"""
        for username, user in list(self._users.items()):
            if user["id"] == user_id:
                # Prevent deleting admin
                if user.get("role") == "admin" and username == "admin":
                    return False
                del self._users[username]
                return True
        return False

    async def get_user_stats(self) -> dict:
        """Get user statistics for dashboard"""
        total_users = len(self._users)
        active_users = sum(1 for u in self._users.values() if u.get("is_active", True))
        admin_users = sum(1 for u in self._users.values() if u.get("role") == "admin")
        pending_verification = len(self._pending_verifications)

        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users,
            "admin_users": admin_users,
            "regular_users": total_users - admin_users,
            "pending_verification": pending_verification
        }


class TokenStatsService:
    """Service for tracking and analyzing token usage statistics from query_log"""

    # Cost per 1K tokens (USD)
    COST_PER_1K = 0.002

    def __init__(self):
        self._pool = None

    async def _get_pool(self):
        """Get database connection pool"""
        if self._pool is None:
            import asyncpg
            # SECURITY: Use separate parameters instead of DSN string
            # to prevent password exposure in logs/error messages
            self._pool = await asyncpg.create_pool(
                host=api_settings.POSTGRES_HOST,
                port=int(api_settings.POSTGRES_PORT),
                user=api_settings.POSTGRES_USER,
                password=api_settings.POSTGRES_PASSWORD,
                database=api_settings.POSTGRES_DB,
                min_size=1,
                max_size=5
            )
        return self._pool

    async def get_token_overview(self) -> dict:
        """Get overall token statistics from query_log"""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                today_start = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                week_ago = datetime.now(timezone.utc) - timedelta(days=7)
                month_ago = datetime.now(timezone.utc) - timedelta(days=30)

                row = await conn.fetchrow("""
                    SELECT
                        COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                        COALESCE(SUM(input_tokens + output_tokens) FILTER (WHERE created_at >= $1), 0) as today_tokens,
                        COALESCE(AVG(execution_time_ms), 0) as avg_latency,
                        COUNT(*) as total_queries,
                        COUNT(*) FILTER (WHERE created_at >= $1) as today_queries
                    FROM query_log
                    WHERE created_at >= $2
                """, today_start, month_ago)

                # Get slowest query
                slowest = await conn.fetchrow("""
                    SELECT user_id, execution_time_ms, strategy, created_at
                    FROM query_log
                    WHERE created_at >= $1
                    ORDER BY execution_time_ms DESC NULLS LAST
                    LIMIT 1
                """, week_ago)

                total_tokens = int(row["total_tokens"] or 0)
                today_tokens = int(row["today_tokens"] or 0)
                total_queries = int(row["total_queries"] or 0)
                today_queries = int(row["today_queries"] or 0)

                return {
                    "total_tokens_issued": total_tokens,
                    "daily_average": round(total_tokens / 30, 1) if total_tokens else 0,
                    "avg_processing_time_ms": round(float(row["avg_latency"] or 0), 1),
                    "slowest_token": {
                        "token_id": "N/A",
                        "user_id": slowest["user_id"] if slowest else "N/A",
                        "processing_time_ms": int(slowest["execution_time_ms"]) if slowest else 0,
                        "endpoint": slowest["strategy"] if slowest else "N/A",
                        "issued_at": slowest["created_at"].isoformat() if slowest else None
                    } if slowest else None,
                    "today_count": today_queries,
                    "today_tokens": today_tokens,
                    "today_avg_time_ms": round(today_tokens / today_queries, 1) if today_queries else 0
                }
        except Exception as e:
            logger.error(f"Error getting token overview: {e}")
            return {
                "total_tokens_issued": 0,
                "daily_average": 0,
                "avg_processing_time_ms": 0,
                "slowest_token": None,
                "today_count": 0,
                "today_tokens": 0,
                "today_avg_time_ms": 0
            }

    async def get_daily_stats(self, days: int = 7) -> list:
        """Get daily token statistics from query_log"""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                start_date = datetime.now(timezone.utc) - timedelta(days=days)

                rows = await conn.fetch("""
                    SELECT
                        DATE(created_at) as date,
                        COUNT(*) as count,
                        COALESCE(SUM(input_tokens + output_tokens), 0) as tokens,
                        COALESCE(AVG(execution_time_ms), 0) as avg_latency
                    FROM query_log
                    WHERE created_at >= $1
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                """, start_date)

                # Create date map
                date_map = {row["date"]: row for row in rows}

                # Fill in missing dates
                result = []
                for i in range(days):
                    date = (datetime.now(timezone.utc) - timedelta(days=i)).date()
                    if date in date_map:
                        row = date_map[date]
                        tokens = int(row["tokens"] or 0)
                        result.append({
                            "date": str(date),
                            "count": row["count"],
                            "tokens": tokens,
                            "avg_processing_time_ms": round(float(row["avg_latency"] or 0), 1),
                            "estimated_cost": round((tokens / 1000) * self.COST_PER_1K, 4)
                        })
                    else:
                        result.append({
                            "date": str(date),
                            "count": 0,
                            "tokens": 0,
                            "avg_processing_time_ms": 0,
                            "estimated_cost": 0
                        })

                return result
        except Exception as e:
            logger.error(f"Error getting daily stats: {e}")
            return []

    async def get_user_token_stats(self) -> list:
        """Get token usage statistics per user from query_log"""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        user_id,
                        COUNT(*) as query_count,
                        COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                        COALESCE(AVG(execution_time_ms), 0) as avg_latency,
                        MAX(execution_time_ms) as max_latency,
                        MIN(execution_time_ms) as min_latency,
                        MAX(created_at) as last_activity
                    FROM query_log
                    WHERE user_id IS NOT NULL
                    GROUP BY user_id
                    ORDER BY total_tokens DESC
                    LIMIT 50
                """)

                result = []
                for row in rows:
                    total_tokens = int(row["total_tokens"] or 0)
                    result.append({
                        "user_id": row["user_id"],
                        "total_tokens": total_tokens,
                        "query_count": row["query_count"],
                        "avg_processing_time_ms": round(float(row["avg_latency"] or 0), 1),
                        "max_processing_time_ms": int(row["max_latency"] or 0),
                        "min_processing_time_ms": int(row["min_latency"] or 0),
                        "estimated_cost": round((total_tokens / 1000) * self.COST_PER_1K, 4),
                        "last_activity": row["last_activity"].isoformat() if row["last_activity"] else None
                    })

                return result
        except Exception as e:
            logger.error(f"Error getting user token stats: {e}")
            return []

    async def get_endpoint_stats(self) -> list:
        """Get token statistics per strategy/endpoint from query_log"""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        COALESCE(strategy, 'unknown') as endpoint,
                        COUNT(*) as count,
                        COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                        COALESCE(AVG(execution_time_ms), 0) as avg_latency,
                        MAX(execution_time_ms) as max_latency
                    FROM query_log
                    GROUP BY strategy
                    ORDER BY count DESC
                """)

                result = []
                for row in rows:
                    total_tokens = int(row["total_tokens"] or 0)
                    result.append({
                        "endpoint": row["endpoint"],
                        "count": row["count"],
                        "total_tokens": total_tokens,
                        "avg_processing_time_ms": round(float(row["avg_latency"] or 0), 1),
                        "max_processing_time_ms": int(row["max_latency"] or 0),
                        "estimated_cost": round((total_tokens / 1000) * self.COST_PER_1K, 4)
                    })

                return result
        except Exception as e:
            logger.error(f"Error getting endpoint stats: {e}")
            return []


# Dependency injection functions
_use_local_rag = None  # Cache for local RAG decision


def get_rag_service():
    """
    Get RAG service instance.

    Returns LocalRAGAdapter if Neo4j is not available,
    otherwise returns the standard RAGService.
    """
    global _use_local_rag

    # Check if we should use local RAG (cached)
    if _use_local_rag is None:
        # Try to connect to Neo4j
        try:
            import os
            from neo4j import GraphDatabase
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "")
            driver = GraphDatabase.driver(
                neo4j_uri,
                auth=(neo4j_user, neo4j_password)
            )
            driver.verify_connectivity()
            driver.close()
            _use_local_rag = False
            print(f"[RAG] Using Neo4j RAG service ({neo4j_uri})")
        except Exception as e:
            _use_local_rag = True
            print(f"[RAG] Neo4j not available ({e}), using Local RAG service")

    if _use_local_rag:
        from ..services.local_rag_adapter import LocalRAGAdapter
        return LocalRAGAdapter.get_instance()
    else:
        return _get_rag_service()


def get_document_service() -> DocumentService:
    return DocumentService()


def get_history_service() -> HistoryService:
    return HistoryService()


def get_stats_service() -> StatsService:
    """Get stats service instance (real implementation)"""
    return _get_stats_service()


def get_settings_service() -> SettingsService:
    return SettingsService()


async def get_auth_service():
    """Get PostgreSQL-backed AuthService singleton instance."""
    from ..services.auth_service import get_auth_service as _get_auth_service
    return await _get_auth_service()


def get_token_stats_service() -> TokenStatsService:
    return TokenStatsService()


def get_health_service() -> HealthService:
    """Get health service instance (real implementation)"""
    return _get_health_service()


def get_conversation_service() -> ConversationService:
    """Get conversation service instance (real implementation)"""
    return _get_conversation_service()


# ==================== Content Generation Service ====================

class ContentService:
    """Service for AI-based content generation"""

    _contents: dict = {}  # content_id -> content data

    async def start_generation(
        self,
        document_ids: list,
        content_type: str,
        language: str,
        options: dict,
        user_id: str
    ) -> dict:
        """Start content generation process"""
        import uuid
        content_id = f"content_{uuid.uuid4().hex[:12]}"

        self._contents[content_id] = {
            "id": content_id,
            "content_type": content_type.value if hasattr(content_type, 'value') else content_type,
            "status": "generating",
            "document_ids": document_ids,
            "language": language,
            "options": options,
            "user_id": user_id,
            "content": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None
        }

        return {"content_id": content_id}

    async def generate_content_async(self, content_id: str):
        """Generate content asynchronously (background task)"""
        import asyncio
        import random

        if content_id not in self._contents:
            return

        content_data = self._contents[content_id]
        content_type = content_data["content_type"]

        # Simulate generation time
        await asyncio.sleep(2)

        # Generate mock content based on type
        if content_type == "summary":
            content_data["content"] = {
                "title": "문서 요약",
                "overview": "이 문서는 시스템의 주요 기능과 구성에 대해 설명합니다.",
                "key_points": [
                    "핵심 기능 1: 문서 관리 및 검색",
                    "핵심 기능 2: AI 기반 질의응답",
                    "핵심 기능 3: 마인드맵 시각화"
                ],
                "detailed_summary": "본 문서는 지식관리시스템의 전반적인 아키텍처와 주요 기능들을 상세히 설명합니다. 시스템은 문서 업로드, RAG 기반 검색, 마인드맵 생성 등의 핵심 기능을 제공합니다.",
                "word_count": 150
            }
        elif content_type == "faq":
            content_data["content"] = {
                "title": "자주 묻는 질문",
                "description": "문서 기반으로 생성된 FAQ입니다.",
                "questions": [
                    {"question": "시스템의 주요 기능은 무엇인가요?", "answer": "문서 관리, AI 검색, 마인드맵 생성 기능을 제공합니다.", "difficulty": "easy", "source_refs": []},
                    {"question": "문서 업로드 용량 제한은 얼마인가요?", "answer": "PDF 파일 기준 최대 50MB까지 업로드 가능합니다.", "difficulty": "easy", "source_refs": []},
                    {"question": "지원하는 언어는 무엇인가요?", "answer": "한국어, 영어, 일본어를 지원합니다.", "difficulty": "medium", "source_refs": []}
                ],
                "categories": ["기능", "제한사항", "지원"]
            }
        elif content_type == "study_guide":
            content_data["content"] = {
                "title": "학습 가이드",
                "learning_objectives": [
                    "시스템 구조 이해하기",
                    "주요 기능 활용법 학습",
                    "고급 검색 기법 익히기"
                ],
                "sections": [
                    {
                        "title": "시스템 개요",
                        "summary": "지식관리시스템의 전반적인 구조와 목적을 설명합니다.",
                        "key_concepts": ["RAG", "마인드맵", "시맨틱 검색"],
                        "definitions": {"RAG": "Retrieval-Augmented Generation의 약자로, 검색 기반 생성 기술"}
                    }
                ],
                "quiz_questions": [
                    {
                        "question": "RAG는 무엇의 약자인가요?",
                        "options": ["Rapid AI Generation", "Retrieval-Augmented Generation", "Random Access Gateway", "Real-time Analytics Graph"],
                        "correct_answer": "Retrieval-Augmented Generation",
                        "explanation": "RAG는 검색 기반 생성 기술을 의미합니다."
                    }
                ],
                "review_summary": "이 가이드를 통해 시스템의 핵심 개념과 활용법을 학습할 수 있습니다."
            }
        elif content_type == "briefing":
            content_data["content"] = {
                "title": "브리핑 문서",
                "executive_summary": "본 브리핑은 지식관리시스템의 현황과 주요 기능을 요약합니다.",
                "sections": [
                    {
                        "heading": "현재 상황",
                        "content": "시스템은 정상 운영 중이며 모든 핵심 기능이 활성화되어 있습니다.",
                        "bullet_points": ["문서 처리 파이프라인 정상", "검색 엔진 최적화 완료", "사용자 인증 시스템 강화"]
                    }
                ],
                "recommendations": [
                    "정기적인 시스템 모니터링 수행",
                    "사용자 피드백 수집 및 반영",
                    "보안 업데이트 적용"
                ],
                "conclusion": "시스템은 안정적으로 운영되고 있으며, 지속적인 개선이 이루어지고 있습니다."
            }
        elif content_type == "timeline":
            content_data["content"] = {
                "title": "타임라인",
                "description": "문서에서 추출한 주요 이벤트 타임라인입니다.",
                "date_range": {"start": "2024-01", "end": "2025-01"},
                "events": [
                    {"date": "2024-01", "title": "프로젝트 시작", "description": "지식관리시스템 개발 착수", "category": "개발", "importance": "high"},
                    {"date": "2024-06", "title": "베타 출시", "description": "내부 테스트 버전 배포", "category": "릴리즈", "importance": "high"},
                    {"date": "2024-12", "title": "정식 출시", "description": "일반 사용자 대상 서비스 시작", "category": "릴리즈", "importance": "high"}
                ],
                "summary": "프로젝트는 2024년 초에 시작되어 약 1년간의 개발 기간을 거쳐 정식 출시되었습니다."
            }
        elif content_type == "toc":
            content_data["content"] = {
                "title": "목차",
                "document_title": "종합 가이드",
                "items": [
                    {"level": 1, "title": "소개", "page": 1, "children": [
                        {"level": 2, "title": "시스템 개요", "page": 2, "children": []},
                        {"level": 2, "title": "주요 기능", "page": 5, "children": []}
                    ]},
                    {"level": 1, "title": "사용 가이드", "page": 10, "children": [
                        {"level": 2, "title": "시작하기", "page": 11, "children": []},
                        {"level": 2, "title": "고급 기능", "page": 20, "children": []}
                    ]}
                ],
                "total_sections": 6
            }
        elif content_type == "key_topics":
            content_data["content"] = {
                "title": "핵심 주제",
                "topics": [
                    {"topic": "RAG (검색 증강 생성)", "relevance_score": 0.95, "description": "AI 기반 문서 검색 및 응답 생성 기술", "related_topics": ["LLM", "벡터 검색"], "document_refs": []},
                    {"topic": "마인드맵", "relevance_score": 0.88, "description": "지식 구조의 시각적 표현", "related_topics": ["그래프 DB", "시각화"], "document_refs": []},
                    {"topic": "문서 관리", "relevance_score": 0.82, "description": "PDF 문서 업로드 및 처리", "related_topics": ["청킹", "임베딩"], "document_refs": []}
                ],
                "topic_relationships": [
                    {"from": "RAG", "to": "마인드맵", "relationship": "활용"},
                    {"from": "문서 관리", "to": "RAG", "relationship": "기반"}
                ]
            }
        else:
            content_data["content"] = {"message": "Content generated"}

        content_data["status"] = "completed"
        content_data["completed_at"] = datetime.now(timezone.utc).isoformat()

    async def list_contents(
        self,
        user_id: str,
        page: int,
        limit: int,
        content_type: str = None,
        status: str = None
    ) -> dict:
        """List generated contents"""
        contents = []
        for cid, content in self._contents.items():
            if content["user_id"] != user_id :
                continue
            if content_type and content["content_type"] != content_type:
                continue
            if status and content["status"] != status:
                continue

            contents.append({
                "id": content["id"],
                "content_type": content["content_type"],
                "status": content["status"],
                "title": content.get("content", {}).get("title", "생성 중...") if content["content"] else "생성 중...",
                "document_count": len(content["document_ids"]),
                "created_at": content["created_at"]
            })

        total = len(contents)
        start = (page - 1) * limit
        end = start + limit
        return {"contents": contents[start:end], "total": total}

    async def get_content(self, content_id: str) -> dict:
        """Get content details"""
        return self._contents.get(content_id)

    async def get_content_status(self, content_id: str) -> dict:
        """Get content generation status"""
        content = self._contents.get(content_id)
        if not content:
            return None
        return {
            "content_id": content_id,
            "status": content["status"],
            "created_at": content["created_at"],
            "completed_at": content.get("completed_at")
        }

    async def delete_content(self, content_id: str) -> bool:
        """Delete content"""
        if content_id in self._contents:
            del self._contents[content_id]
            return True
        return False


def get_content_service() -> ContentService:
    return ContentService()


# ==================== Note Service ====================

class NoteService:
    """Service for notes and memos management"""

    _notes: dict = {}  # note_id -> note data
    _folders: dict = {}  # folder_id -> folder data

    async def create_note(
        self,
        title: str,
        content: str,
        note_type: str,
        folder_id: str,
        project_id: str,
        tags: list,
        source: str,
        source_reference: dict,
        color: str,
        user_id: str
    ) -> dict:
        """Create a new note"""
        import uuid
        note_id = f"note_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        note = {
            "id": note_id,
            "title": title,
            "content": content,
            "note_type": note_type.value if hasattr(note_type, 'value') else note_type,
            "source": source.value if hasattr(source, 'value') else source,
            "source_reference": source_reference,
            "folder_id": folder_id,
            "folder_name": self._folders.get(folder_id, {}).get("name") if folder_id else None,
            "project_id": project_id,
            "project_name": None,  # Would be fetched from project service
            "tags": tags or [],
            "color": color,
            "is_pinned": False,
            "word_count": len(content.split()),
            "created_at": now,
            "updated_at": now,
            "created_by": user_id
        }

        self._notes[note_id] = note
        return note

    async def list_notes(
        self,
        user_id: str,
        page: int,
        limit: int,
        folder_id: str = None,
        project_id: str = None,
        note_type: str = None,
        tags: list = None,
        pinned_only: bool = False
    ) -> dict:
        """List notes with filtering"""
        notes = []
        for nid, note in self._notes.items():
            if note.get("created_by") != user_id :
                continue
            if folder_id and note.get("folder_id") != folder_id:
                continue
            if project_id and note.get("project_id") != project_id:
                continue
            if note_type and note.get("note_type") != note_type:
                continue
            if pinned_only and not note.get("is_pinned"):
                continue
            if tags:
                if not any(t in note.get("tags", []) for t in tags):
                    continue

            notes.append({
                "id": note["id"],
                "title": note["title"],
                "preview": note["content"][:100] + "..." if len(note["content"]) > 100 else note["content"],
                "note_type": note["note_type"],
                "source": note["source"],
                "folder_id": note.get("folder_id"),
                "folder_name": note.get("folder_name"),
                "project_id": note.get("project_id"),
                "tags": note.get("tags", []),
                "color": note.get("color"),
                "is_pinned": note.get("is_pinned", False),
                "created_at": note["created_at"],
                "updated_at": note["updated_at"]
            })

        # Sort by pinned first, then by updated_at
        notes.sort(key=lambda x: (not x["is_pinned"], x["updated_at"]), reverse=True)

        total = len(notes)
        start = (page - 1) * limit
        end = start + limit
        return {"notes": notes[start:end], "total": total}

    async def get_note(self, note_id: str) -> dict:
        """Get note details"""
        return self._notes.get(note_id)

    async def update_note(
        self,
        note_id: str,
        title: str = None,
        content: str = None,
        folder_id: str = None,
        tags: list = None,
        color: str = None,
        is_pinned: bool = None
    ) -> dict:
        """Update a note"""
        if note_id not in self._notes:
            return None

        note = self._notes[note_id]
        if title is not None:
            note["title"] = title
        if content is not None:
            note["content"] = content
            note["word_count"] = len(content.split())
        if folder_id is not None:
            note["folder_id"] = folder_id
            note["folder_name"] = self._folders.get(folder_id, {}).get("name")
        if tags is not None:
            note["tags"] = tags
        if color is not None:
            note["color"] = color
        if is_pinned is not None:
            note["is_pinned"] = is_pinned

        note["updated_at"] = datetime.now(timezone.utc).isoformat()
        return note

    async def delete_note(self, note_id: str) -> bool:
        """Delete a note"""
        if note_id in self._notes:
            del self._notes[note_id]
            return True
        return False

    async def toggle_pin(self, note_id: str) -> dict:
        """Toggle note pin status"""
        if note_id not in self._notes:
            return None
        note = self._notes[note_id]
        note["is_pinned"] = not note.get("is_pinned", False)
        note["updated_at"] = datetime.now(timezone.utc).isoformat()
        return {"is_pinned": note["is_pinned"]}

    async def save_ai_response(
        self,
        query_id: str,
        title: str,
        folder_id: str,
        project_id: str,
        tags: list,
        user_id: str
    ) -> dict:
        """Save AI response as note"""
        # Mock: In real implementation, fetch query from history service
        return await self.create_note(
            title=title or f"AI 응답 - {query_id[:8]}",
            content=f"이것은 쿼리 {query_id}에 대한 AI 응답입니다.\n\n(실제 구현에서는 히스토리 서비스에서 응답을 가져옵니다.)",
            note_type="ai_response",
            folder_id=folder_id,
            project_id=project_id,
            tags=tags,
            source="ai_chat",
            source_reference={"query_id": query_id},
            color=None,
            user_id=user_id
        )

    async def create_folder(
        self,
        name: str,
        parent_id: str,
        project_id: str,
        color: str,
        icon: str,
        user_id: str
    ) -> dict:
        """Create a folder"""
        import uuid
        folder_id = f"folder_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        folder = {
            "id": folder_id,
            "name": name,
            "parent_id": parent_id,
            "project_id": project_id,
            "color": color,
            "icon": icon,
            "note_count": 0,
            "children": [],
            "created_at": now,
            "updated_at": now,
            "created_by": user_id
        }

        self._folders[folder_id] = folder
        return folder

    async def list_folders(self, user_id: str, project_id: str = None) -> list:
        """List folders in tree structure"""
        folders = []
        for fid, folder in self._folders.items():
            if folder.get("created_by") != user_id :
                continue
            if project_id and folder.get("project_id") != project_id:
                continue
            if folder.get("parent_id") is None:  # Only root folders
                folders.append(self._build_folder_tree(folder))
        return folders

    def _build_folder_tree(self, folder: dict) -> dict:
        """Build folder tree recursively"""
        children = []
        for fid, f in self._folders.items():
            if f.get("parent_id") == folder["id"]:
                children.append(self._build_folder_tree(f))

        note_count = sum(1 for n in self._notes.values() if n.get("folder_id") == folder["id"])

        return {
            **folder,
            "note_count": note_count,
            "children": children
        }

    async def update_folder(
        self,
        folder_id: str,
        name: str = None,
        parent_id: str = None,
        color: str = None,
        icon: str = None
    ) -> dict:
        """Update a folder"""
        if folder_id not in self._folders:
            return None

        folder = self._folders[folder_id]
        if name is not None:
            folder["name"] = name
        if parent_id is not None:
            folder["parent_id"] = parent_id
        if color is not None:
            folder["color"] = color
        if icon is not None:
            folder["icon"] = icon

        folder["updated_at"] = datetime.now(timezone.utc).isoformat()
        return folder

    async def delete_folder(self, folder_id: str, move_to_root: bool = True) -> dict:
        """Delete a folder"""
        if folder_id not in self._folders:
            return None

        notes_affected = 0
        for nid, note in self._notes.items():
            if note.get("folder_id") == folder_id:
                if move_to_root:
                    note["folder_id"] = None
                    note["folder_name"] = None
                notes_affected += 1

        del self._folders[folder_id]
        return {"notes_moved_to_root": notes_affected}

    async def search_notes(
        self,
        user_id: str,
        query: str,
        folder_id: str = None,
        project_id: str = None,
        tags: list = None,
        note_type: str = None,
        date_from: datetime = None,
        date_to: datetime = None,
        page: int = 1,
        limit: int = 20
    ) -> dict:
        """Search notes"""
        results = []
        query_lower = query.lower()

        for nid, note in self._notes.items():
            if note.get("created_by") != user_id :
                continue

            # Text search
            if query_lower not in note["title"].lower() and query_lower not in note["content"].lower():
                continue

            # Filters
            if folder_id and note.get("folder_id") != folder_id:
                continue
            if project_id and note.get("project_id") != project_id:
                continue
            if note_type and note.get("note_type") != note_type:
                continue
            if tags and not any(t in note.get("tags", []) for t in tags):
                continue

            # Find highlights
            highlights = []
            content_lower = note["content"].lower()
            idx = content_lower.find(query_lower)
            if idx != -1:
                start = max(0, idx - 30)
                end = min(len(note["content"]), idx + len(query) + 30)
                highlights.append(f"...{note['content'][start:end]}...")

            results.append({
                "id": note["id"],
                "title": note["title"],
                "preview": note["content"][:100],
                "highlights": highlights,
                "relevance_score": 1.0 if query_lower in note["title"].lower() else 0.8,
                "note_type": note["note_type"],
                "folder_name": note.get("folder_name"),
                "tags": note.get("tags", []),
                "created_at": note["created_at"]
            })

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        total = len(results)
        start = (page - 1) * limit
        end = start + limit
        return {"results": results[start:end], "total": total}

    async def export_notes(
        self,
        note_ids: list,
        format: str,
        include_metadata: bool
    ) -> dict:
        """Export notes to various formats"""
        notes = [self._notes.get(nid) for nid in note_ids if nid in self._notes]

        if format == "markdown":
            content = ""
            for note in notes:
                content += f"# {note['title']}\n\n"
                if include_metadata:
                    content += f"*Created: {note['created_at']}*\n"
                    content += f"*Tags: {', '.join(note.get('tags', []))}*\n\n"
                content += f"{note['content']}\n\n---\n\n"
            filename = f"notes_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
        elif format == "json":
            import json
            content = json.dumps(notes, indent=2, ensure_ascii=False)
            filename = f"notes_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        elif format == "html":
            content = "<html><body>\n"
            for note in notes:
                content += f"<h1>{note['title']}</h1>\n"
                if include_metadata:
                    content += f"<p><em>Created: {note['created_at']}</em></p>\n"
                content += f"<div>{note['content']}</div>\n<hr>\n"
            content += "</body></html>"
            filename = f"notes_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.html"
        else:
            content = "\n".join(f"{n['title']}: {n['content']}" for n in notes)
            filename = f"notes_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.txt"

        return {
            "format": format,
            "filename": filename,
            "content": content,
            "note_count": len(notes),
            "export_date": datetime.now(timezone.utc).isoformat()
        }

    async def get_stats(self, user_id: str) -> dict:
        """Get note statistics"""
        notes = [n for n in self._notes.values() if n.get("created_by") == user_id ]

        by_type = {}
        by_source = {}
        all_tags = {}

        for note in notes:
            nt = note.get("note_type", "text")
            by_type[nt] = by_type.get(nt, 0) + 1

            src = note.get("source", "manual")
            by_source[src] = by_source.get(src, 0) + 1

            for tag in note.get("tags", []):
                all_tags[tag] = all_tags.get(tag, 0) + 1

        most_used_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_notes": len(notes),
            "by_type": by_type,
            "by_source": by_source,
            "total_folders": len(self._folders),
            "total_tags": len(all_tags),
            "most_used_tags": [{"tag": t, "count": c} for t, c in most_used_tags],
            "recent_activity": []
        }

    async def list_tags(self, user_id: str) -> list:
        """List all tags used by user"""
        tags = set()
        for note in self._notes.values():
            if note.get("created_by") == user_id :
                tags.update(note.get("tags", []))
        return sorted(list(tags))


def get_note_service() -> NoteService:
    return NoteService()


# ==================== Project Service ====================

class ProjectService:
    """Service for project/notebook management"""

    _projects: dict = {}  # project_id -> project data
    _project_documents: dict = {}  # project_id -> [document_ids]
    _project_members: dict = {}  # project_id -> [member_data]
    _templates: dict = {}  # template_id -> template data
    _activities: dict = {}  # project_id -> [activity]

    async def create_project(
        self,
        name: str,
        description: str,
        visibility: str,
        color: str,
        icon: str,
        tags: list,
        template_id: str,
        user_id: str,
        username: str
    ) -> dict:
        """Create a new project"""
        import uuid
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        project = {
            "id": project_id,
            "name": name,
            "description": description,
            "visibility": visibility.value if hasattr(visibility, 'value') else visibility,
            "color": color,
            "icon": icon,
            "tags": tags or [],
            "owner_id": user_id,
            "owner_name": username,
            "created_at": now,
            "updated_at": now
        }

        self._projects[project_id] = project
        self._project_documents[project_id] = []
        self._project_members[project_id] = [{
            "user_id": user_id,
            "username": username,
            "role": "owner",
            "joined_at": now
        }]
        self._activities[project_id] = [{
            "id": f"act_{uuid.uuid4().hex[:8]}",
            "action": "created",
            "actor_id": user_id,
            "actor_name": username,
            "timestamp": now
        }]

        return self._get_project_detail(project_id, user_id)

    def _get_project_detail(self, project_id: str, user_id: str) -> dict:
        """Get detailed project info"""
        project = self._projects.get(project_id)
        if not project:
            return None

        members = self._project_members.get(project_id, [])
        docs = self._project_documents.get(project_id, [])

        my_role = "viewer"
        for m in members:
            if m["user_id"] == user_id:
                my_role = m["role"]
                break

        return {
            **project,
            "members": members,
            "stats": {
                "document_count": len(docs),
                "note_count": 0,  # Would count from note service
                "mindmap_count": 0,
                "conversation_count": 0,
                "member_count": len(members),
                "total_queries": 0,
                "last_activity": None
            },
            "is_owner": project["owner_id"] == user_id,
            "my_role": my_role
        }

    async def list_projects(
        self,
        user_id: str,
        page: int,
        limit: int,
        visibility: str = None,
        search: str = None,
        include_shared: bool = True
    ) -> dict:
        """List projects"""
        projects = []

        for pid, project in self._projects.items():
            # Check access
            is_owner = project["owner_id"] == user_id
            is_member = any(m["user_id"] == user_id for m in self._project_members.get(pid, []))

            if not is_owner and not (include_shared and is_member):
                if project.get("visibility") != "public":
                    continue

            if visibility and project.get("visibility") != visibility:
                continue
            if search and search.lower() not in project["name"].lower():
                continue

            docs = self._project_documents.get(pid, [])
            my_role = "viewer"
            for m in self._project_members.get(pid, []):
                if m["user_id"] == user_id:
                    my_role = m["role"]
                    break

            projects.append({
                "id": project["id"],
                "name": project["name"],
                "description": project.get("description"),
                "visibility": project.get("visibility", "private"),
                "color": project.get("color"),
                "icon": project.get("icon"),
                "tags": project.get("tags", []),
                "owner_id": project["owner_id"],
                "owner_name": project["owner_name"],
                "document_count": len(docs),
                "note_count": 0,
                "is_owner": is_owner,
                "my_role": my_role,
                "created_at": project["created_at"],
                "updated_at": project["updated_at"]
            })

        total = len(projects)
        start = (page - 1) * limit
        end = start + limit
        return {"projects": projects[start:end], "total": total}

    async def get_project(self, project_id: str, user_id: str) -> dict:
        """Get project details"""
        return self._get_project_detail(project_id, user_id)

    async def update_project(
        self,
        project_id: str,
        user_id: str,
        name: str = None,
        description: str = None,
        visibility: str = None,
        color: str = None,
        icon: str = None,
        tags: list = None
    ) -> dict:
        """Update project"""
        if project_id not in self._projects:
            return None

        project = self._projects[project_id]

        # Check permission
        if project["owner_id"] != user_id:
            member = next((m for m in self._project_members.get(project_id, []) if m["user_id"] == user_id and m["role"] == "editor"), None)
            if not member:
                return None

        if name is not None:
            project["name"] = name
        if description is not None:
            project["description"] = description
        if visibility is not None:
            project["visibility"] = visibility.value if hasattr(visibility, 'value') else visibility
        if color is not None:
            project["color"] = color
        if icon is not None:
            project["icon"] = icon
        if tags is not None:
            project["tags"] = tags

        project["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self._get_project_detail(project_id, user_id)

    async def delete_project(
        self,
        project_id: str,
        user_id: str,
        delete_documents: bool = False
    ) -> dict:
        """Delete project"""
        if project_id not in self._projects:
            return None

        project = self._projects[project_id]
        if project["owner_id"] != user_id:
            return None

        docs = self._project_documents.get(project_id, [])
        del self._projects[project_id]
        if project_id in self._project_documents:
            del self._project_documents[project_id]
        if project_id in self._project_members:
            del self._project_members[project_id]
        if project_id in self._activities:
            del self._activities[project_id]

        return {"documents_affected": len(docs), "documents_deleted": len(docs) if delete_documents else 0}

    async def list_project_documents(
        self,
        project_id: str,
        user_id: str,
        page: int,
        limit: int
    ) -> dict:
        """List documents in project"""
        if project_id not in self._projects:
            return None

        docs = self._project_documents.get(project_id, [])
        # Mock document data
        documents = [{"id": doc_id, "filename": f"doc_{doc_id}.pdf", "original_name": f"Document {doc_id}", "file_size": 1024000, "status": "ready", "chunks_count": 10, "added_at": datetime.now(timezone.utc).isoformat()} for doc_id in docs]

        total = len(documents)
        start = (page - 1) * limit
        end = start + limit
        return {"documents": documents[start:end], "total": total}

    async def add_document(
        self,
        project_id: str,
        document_id: str,
        user_id: str
    ) -> dict:
        """Add document to project"""
        if project_id not in self._projects:
            return None

        if project_id not in self._project_documents:
            self._project_documents[project_id] = []

        if document_id not in self._project_documents[project_id]:
            self._project_documents[project_id].append(document_id)

        return {"document_id": document_id, "project_id": project_id}

    async def remove_document(
        self,
        project_id: str,
        document_id: str,
        user_id: str
    ) -> dict:
        """Remove document from project"""
        if project_id not in self._projects:
            return None

        if project_id in self._project_documents and document_id in self._project_documents[project_id]:
            self._project_documents[project_id].remove(document_id)
            return {"removed": True}

        return None

    async def share_project(
        self,
        project_id: str,
        owner_id: str,
        user_ids: list,
        role: str,
        message: str = None
    ) -> dict:
        """Share project with users"""
        if project_id not in self._projects:
            return None

        project = self._projects[project_id]
        if project["owner_id"] != owner_id:
            return None

        role_value = role.value if hasattr(role, 'value') else role
        now = datetime.now(timezone.utc).isoformat()

        for uid in user_ids:
            # Check if already a member
            existing = next((m for m in self._project_members.get(project_id, []) if m["user_id"] == uid), None)
            if not existing:
                self._project_members[project_id].append({
                    "user_id": uid,
                    "username": f"user_{uid}",
                    "role": role_value,
                    "joined_at": now
                })

        return {
            "shared_with": user_ids,
            "role": role_value,
            "message": f"{len(user_ids)}명의 사용자와 공유되었습니다."
        }

    async def list_members(self, project_id: str, user_id: str) -> list:
        """List project members"""
        if project_id not in self._projects:
            return None
        return self._project_members.get(project_id, [])

    async def update_member_role(
        self,
        project_id: str,
        owner_id: str,
        target_user_id: str,
        role: str
    ) -> dict:
        """Update member role"""
        if project_id not in self._projects:
            return None

        project = self._projects[project_id]
        if project["owner_id"] != owner_id:
            return None

        for member in self._project_members.get(project_id, []):
            if member["user_id"] == target_user_id:
                member["role"] = role.value if hasattr(role, 'value') else role
                return {"user_id": target_user_id, "new_role": member["role"]}

        return None

    async def remove_member(
        self,
        project_id: str,
        owner_id: str,
        target_user_id: str
    ) -> dict:
        """Remove member from project"""
        if project_id not in self._projects:
            return None

        project = self._projects[project_id]
        if project["owner_id"] != owner_id:
            return None

        members = self._project_members.get(project_id, [])
        for i, m in enumerate(members):
            if m["user_id"] == target_user_id and m["role"] != "owner":
                del members[i]
                return {"removed": True}

        return None

    async def clone_project(
        self,
        project_id: str,
        user_id: str,
        username: str,
        new_name: str,
        include_documents: bool,
        include_notes: bool,
        include_mindmaps: bool,
        include_conversations: bool
    ) -> dict:
        """Clone a project"""
        if project_id not in self._projects:
            return None

        original = self._projects[project_id]

        # Create new project
        new_project = await self.create_project(
            name=new_name,
            description=original.get("description"),
            visibility="private",
            color=original.get("color"),
            icon=original.get("icon"),
            tags=original.get("tags", []),
            template_id=None,
            user_id=user_id,
            username=username
        )

        docs_cloned = 0
        if include_documents:
            docs = self._project_documents.get(project_id, [])
            self._project_documents[new_project["id"]] = docs.copy()
            docs_cloned = len(docs)

        return {
            "project_id": new_project["id"],
            "name": new_name,
            "documents_cloned": docs_cloned,
            "notes_cloned": 0,
            "mindmaps_cloned": 0,
            "message": "프로젝트가 복제되었습니다."
        }

    async def list_templates(
        self,
        user_id: str,
        category: str = None,
        include_public: bool = True
    ) -> list:
        """List project templates"""
        # Return default templates
        templates = [
            {
                "id": "tpl_research",
                "name": "연구 프로젝트",
                "description": "학술 연구를 위한 템플릿",
                "category": "research",
                "color": "#4A90D9",
                "icon": "research",
                "folder_structure": [{"name": "문헌 조사"}, {"name": "실험 데이터"}, {"name": "분석 결과"}],
                "sample_note_count": 0,
                "is_public": True,
                "usage_count": 150,
                "created_by": "system",
                "created_at": "2024-01-01T00:00:00Z"
            },
            {
                "id": "tpl_study",
                "name": "학습 노트북",
                "description": "학습 및 정리를 위한 템플릿",
                "category": "study",
                "color": "#27AE60",
                "icon": "study",
                "folder_structure": [{"name": "강의 노트"}, {"name": "복습"}, {"name": "퀴즈"}],
                "sample_note_count": 0,
                "is_public": True,
                "usage_count": 230,
                "created_by": "system",
                "created_at": "2024-01-01T00:00:00Z"
            },
            {
                "id": "tpl_business",
                "name": "비즈니스 분석",
                "description": "비즈니스 문서 분석을 위한 템플릿",
                "category": "business",
                "color": "#E74C3C",
                "icon": "business",
                "folder_structure": [{"name": "시장 조사"}, {"name": "경쟁 분석"}, {"name": "전략"}],
                "sample_note_count": 0,
                "is_public": True,
                "usage_count": 85,
                "created_by": "system",
                "created_at": "2024-01-01T00:00:00Z"
            }
        ]

        if category:
            category_value = category.value if hasattr(category, 'value') else category
            templates = [t for t in templates if t["category"] == category_value]

        return templates

    async def create_template(
        self,
        project_id: str,
        user_id: str,
        name: str,
        description: str,
        category: str,
        include_structure: bool,
        include_sample_notes: bool,
        is_public: bool
    ) -> dict:
        """Create template from project"""
        import uuid

        if project_id not in self._projects:
            return None

        template_id = f"tpl_{uuid.uuid4().hex[:12]}"

        template = {
            "id": template_id,
            "name": name,
            "description": description,
            "category": category.value if hasattr(category, 'value') else category,
            "color": self._projects[project_id].get("color"),
            "icon": self._projects[project_id].get("icon"),
            "folder_structure": [],
            "sample_note_count": 0,
            "is_public": is_public,
            "usage_count": 0,
            "created_by": user_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        self._templates[template_id] = template
        return template

    async def get_activity(
        self,
        project_id: str,
        user_id: str,
        page: int,
        limit: int
    ) -> dict:
        """Get project activity"""
        if project_id not in self._projects:
            return None

        activities = self._activities.get(project_id, [])
        total = len(activities)
        start = (page - 1) * limit
        end = start + limit
        return {"activities": activities[start:end], "total": total}


def get_project_service() -> ProjectService:
    return ProjectService()


# ==================== Multimodal RAG Service ====================

# Singleton instances for multimodal RAG
_image_embedding_repository = None
_multimodal_rag_service = None


async def _get_image_embedding_repository():
    """Get or create image embedding repository with PostgreSQL pool."""
    global _image_embedding_repository
    if _image_embedding_repository is None:
        import asyncpg
        from ..infrastructure.postgres.image_embedding_repository import PostgresImageEmbeddingRepository

        # SECURITY: Use separate parameters instead of DSN string
        # to prevent password exposure in logs/error messages
        pool = await asyncpg.create_pool(
            host=api_settings.POSTGRES_HOST,
            port=int(api_settings.POSTGRES_PORT),
            user=api_settings.POSTGRES_USER,
            password=api_settings.POSTGRES_PASSWORD,
            database=api_settings.POSTGRES_DB,
            min_size=1,
            max_size=5
        )
        _image_embedding_repository = PostgresImageEmbeddingRepository(pool)

    return _image_embedding_repository


async def get_image_repository():
    """
    Get image embedding repository for image lookup operations.

    Public wrapper for _get_image_embedding_repository().
    Used by orchestrator for fetching images by page numbers or figure references.
    """
    return await _get_image_embedding_repository()


async def get_multimodal_rag_service():
    """
    Get MultimodalRAGService singleton instance.

    Used for:
    - Image extraction from PDFs
    - Image embedding and storage
    - Image similarity search
    - RAG context enhancement with images
    """
    global _multimodal_rag_service
    if _multimodal_rag_service is None:
        from ..services.multimodal_rag_service import MultimodalRAGService

        repository = await _get_image_embedding_repository()
        _multimodal_rag_service = MultimodalRAGService(image_repository=repository)

    return _multimodal_rag_service


def get_multimodal_rag_service_sync():
    """
    Synchronous wrapper for multimodal RAG service.
    Returns None if service not yet initialized.
    Use get_multimodal_rag_service() for async contexts.
    """
    return _multimodal_rag_service


# Singleton instance for figure image service
_figure_image_service = None


async def get_figure_image_service():
    """
    Get FigureImageService singleton instance.

    Used for:
    - Detecting figure references in LLM responses
    - Fetching images by page numbers from source documents
    - Including images in RAG responses
    """
    global _figure_image_service
    if _figure_image_service is None:
        from ..services.figure_image_service import FigureImageService

        repository = await _get_image_embedding_repository()
        _figure_image_service = FigureImageService(image_repository=repository)

    return _figure_image_service


# =============================================================================
# Adaptive Embedding Service (PDF Structure-Preserving Embedding)
# =============================================================================

# Singleton instances for adaptive embedding service
_adaptive_embedding_service = None
_adaptive_chunk_repository = None
_pdf_structure_repository = None
_coverage_repository = None


_adaptive_db_pool = None


async def _get_db_pool():
    """Get or create database pool for adaptive embedding service."""
    global _adaptive_db_pool

    if _adaptive_db_pool is None:
        import asyncpg
        from .config import api_settings

        _adaptive_db_pool = await asyncpg.create_pool(
            host=api_settings.POSTGRES_HOST,
            port=int(api_settings.POSTGRES_PORT),
            user=api_settings.POSTGRES_USER,
            password=api_settings.POSTGRES_PASSWORD,
            database=api_settings.POSTGRES_DB,
            min_size=2,
            max_size=10
        )
        logger.info("Created database pool for adaptive embedding service")

    return _adaptive_db_pool


async def get_adaptive_embedding_service():
    """
    Get PDFAdaptiveEmbeddingService singleton instance.

    Used for:
    - Adaptive PDF structure analysis
    - Semantic boundary-based chunking
    - Parallel embedding generation
    - Coverage validation and quality evaluation
    """
    global _adaptive_embedding_service
    global _adaptive_chunk_repository
    global _pdf_structure_repository
    global _coverage_repository

    if _adaptive_embedding_service is None:
        from ..services.pdf_adaptive_embedding_service import (
            create_pdf_adaptive_embedding_service
        )
        from ..infrastructure.postgres.adaptive_chunk_repository import (
            PostgresAdaptiveChunkRepository,
            PostgresPDFStructureRepository,
            PostgresCoverageRepository,
        )

        # Get database pool
        pool = await _get_db_pool()
        if pool is None:
            raise RuntimeError("Database pool not available for adaptive embedding service")

        # Create repositories
        _adaptive_chunk_repository = PostgresAdaptiveChunkRepository(pool)
        _pdf_structure_repository = PostgresPDFStructureRepository(pool)
        _coverage_repository = PostgresCoverageRepository(pool)

        # Create embedding executor with NIM TextEmbeddingService
        from ..services.parallel_embedding_executor import ParallelEmbeddingExecutor
        from ..services.multimodal_embedding import TextEmbeddingService
        from ..ports.embedding_port import EmbeddingResult

        # Create adapter wrapper for TextEmbeddingService
        class NIMEmbeddingAdapter:
            """Adapter to make TextEmbeddingService compatible with EmbeddingPort interface."""

            def __init__(self):
                self.service = TextEmbeddingService()

            async def embed_text(self, text: str) -> EmbeddingResult:
                """Generate embedding and return as EmbeddingResult."""
                embedding = await self.service.embed_text(text, input_type="passage")
                return EmbeddingResult(
                    text=text,
                    embedding=embedding,
                    token_count=len(text) // 4,  # Estimate
                    metadata={"model": "nvidia/nv-embedqa-mistral-7b-v2"}
                )

        embedding_executor = ParallelEmbeddingExecutor(
            embedding_service=NIMEmbeddingAdapter(),
            default_concurrency=5,
            default_retry_count=3
        )

        # Create service with embedding executor
        _adaptive_embedding_service = create_pdf_adaptive_embedding_service(
            chunk_repository=_adaptive_chunk_repository,
            structure_repository=_pdf_structure_repository,
            coverage_repository=_coverage_repository,
            embedding_executor=embedding_executor
        )

        logger.info("Adaptive embedding service initialized")

    return _adaptive_embedding_service


async def get_embedding_service():
    """
    Get text embedding service for adaptive embedding.

    Uses NV-EmbedQA-Mistral 7B v2 via NIM container (port 12801).
    """
    from ..services.multimodal_embedding import TextEmbeddingService

    return TextEmbeddingService()
