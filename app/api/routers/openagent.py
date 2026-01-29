"""
OpenAgent API Router

Provides endpoints for vLLM-based chat using OpenAI-compatible API.
Connects directly to vLLM server (192.168.8.11:12800) with Qwen2.5-7B-Instruct model.
"""
import logging
import os
import uuid
import aiofiles
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..core.deps import get_current_user
from ..services.opencode_service import get_openagent_service, OpenAgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/openagent", tags=["OpenAgent"])


# Request/Response models
class ChatMessage(BaseModel):
    """A single chat message."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat request for OpenAgent."""
    message: str = Field(..., min_length=1, max_length=16000, description="The message/question to send")
    system_prompt: Optional[str] = Field(None, description="Optional system prompt")
    file_content: Optional[str] = Field(None, description="Optional file content as context")
    history: Optional[List[ChatMessage]] = Field(None, description="Optional conversation history")


class ChatResponse(BaseModel):
    """Chat response from OpenAgent."""
    success: bool
    message: str
    response: str
    model: str = "Qwen/Qwen2.5-7B-Instruct"


class HealthResponse(BaseModel):
    """Health check response."""
    available: bool
    message: str
    model: Optional[str] = None
    base_url: Optional[str] = None


# Dependency for OpenAgent service
def get_service() -> OpenAgentService:
    """Get the OpenAgent service."""
    return get_openagent_service()


@router.get("/health", response_model=HealthResponse)
async def health_check(
    service: OpenAgentService = Depends(get_service)
) -> HealthResponse:
    """
    Check if vLLM server is available.

    Returns:
        HealthResponse with availability status
    """
    available = await service.health_check()

    if available:
        return HealthResponse(
            available=True,
            message="vLLM server is available",
            model=service.config.model,
            base_url=service.config.base_url,
        )
    else:
        return HealthResponse(
            available=False,
            message=f"vLLM server not available at {service.config.base_url}",
            model=service.config.model,
            base_url=service.config.base_url,
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    service: OpenAgentService = Depends(get_service)
) -> ChatResponse:
    """
    Send a chat message to OpenAgent (vLLM).

    Args:
        request: Chat request with message and optional context
        current_user: Authenticated user
        service: OpenAgent service

    Returns:
        ChatResponse with the AI response
    """
    try:
        logger.info(f"OpenAgent chat request from user {current_user.get('user_id', 'unknown')}")

        # Convert history if provided
        history = None
        if request.history:
            history = [{"role": m.role, "content": m.content} for m in request.history]

        response = await service.chat(
            message=request.message,
            system_prompt=request.system_prompt,
            file_content=request.file_content,
            history=history,
        )

        return ChatResponse(
            success=True,
            message="Response generated successfully",
            response=response,
            model=service.config.model,
        )

    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request timed out. The model may be overloaded."
        )
    except Exception as e:
        logger.exception(f"Unexpected error in OpenAgent chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    service: OpenAgentService = Depends(get_service)
):
    """
    Stream a chat response from OpenAgent (vLLM).

    Args:
        request: Chat request with message and optional context
        current_user: Authenticated user
        service: OpenAgent service

    Returns:
        Server-Sent Events stream with the response
    """
    logger.info(f"OpenAgent stream request from user {current_user.get('user_id', 'unknown')}")

    # Convert history if provided
    history = None
    if request.history:
        history = [{"role": m.role, "content": m.content} for m in request.history]

    async def generate():
        """Generate SSE events from vLLM stream."""
        try:
            async for chunk in service.stream(
                message=request.message,
                system_prompt=request.system_prompt,
                file_content=request.file_content,
                history=history,
            ):
                # Format as SSE
                yield f"data: {chunk}\n\n"

            # Send completion event
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: [ERROR: {str(e)}]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/chat-with-file", response_model=ChatResponse)
async def chat_with_file(
    message: str = Form(...),
    system_prompt: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    service: OpenAgentService = Depends(get_service)
) -> ChatResponse:
    """
    Send a chat message with an uploaded file as context.

    Args:
        message: The question/prompt
        system_prompt: Optional system prompt
        file: The file to use as context
        current_user: Authenticated user
        service: OpenAgent service

    Returns:
        ChatResponse with the AI response
    """
    # Validate file type
    allowed_extensions = {'.txt', '.md', '.py', '.js', '.ts', '.json', '.yaml', '.yml', '.xml', '.html', '.css', '.java', '.go', '.rs', '.c', '.cpp', '.h'}
    file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ''

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file_ext}' not supported. Allowed: {', '.join(sorted(allowed_extensions))}"
        )

    # Read file content
    try:
        content = await file.read()
        file_content = content.decode('utf-8', errors='replace')

        # Limit file content size (approximate token limit)
        max_chars = 24000  # ~6000 tokens
        if len(file_content) > max_chars:
            file_content = file_content[:max_chars] + "\n\n[... content truncated ...]"
            logger.warning(f"File content truncated from {len(content)} to {max_chars} chars")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read file: {str(e)}"
        )

    logger.info(f"Chat with file: {file.filename} ({len(file_content)} chars)")

    try:
        response = await service.chat(
            message=message,
            system_prompt=system_prompt,
            file_content=file_content,
        )

        return ChatResponse(
            success=True,
            message=f"Response generated with file context: {file.filename}",
            response=response,
            model=service.config.model,
        )

    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request timed out. The model may be overloaded."
        )
    except Exception as e:
        logger.exception(f"Error in chat with file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/config")
async def get_config(
    current_user: dict = Depends(get_current_user),
    service: OpenAgentService = Depends(get_service)
):
    """
    Get current OpenAgent configuration.

    Returns:
        Current vLLM configuration (base_url, model, etc.)
    """
    return {
        "base_url": service.config.base_url,
        "model": service.config.model,
        "max_tokens": service.config.max_tokens,
        "temperature": service.config.temperature,
    }


# ============================================================
# RAG Endpoints - Summary-based Retrieval Augmented Generation
# ============================================================

class RAGChatRequest(BaseModel):
    """RAG-enhanced chat request."""
    message: str = Field(..., min_length=1, max_length=16000, description="The message/question to send")
    file_content: Optional[str] = Field(None, description="Optional file content as context")
    history: Optional[List[ChatMessage]] = Field(None, description="Optional conversation history")
    use_summaries: bool = Field(True, description="Whether to use summary-based RAG")
    language: Optional[str] = Field("ja", description="UI language setting (en, ko, ja) - response will be in this language")


class RAGSource(BaseModel):
    """A source reference from RAG search."""
    type: str = Field(..., description="Source type: error_code, command, glossary, api")
    file: str = Field(..., description="Source file name")


class TokenUsage(BaseModel):
    """Token usage information."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class TableContent(BaseModel):
    """Table content from Neo4j."""
    chunk_id: Optional[str] = None
    content: str = Field(..., description="Table content in markdown format")
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    doc_filename: Optional[str] = None


class ImageContent(BaseModel):
    """Image content from Neo4j."""
    chunk_id: Optional[str] = None
    content: str = Field(..., description="Image caption/description")
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    doc_filename: Optional[str] = None
    image_url: Optional[str] = Field(None, description="URL to image file if available")


class RAGChatResponse(BaseModel):
    """RAG-enhanced chat response."""
    success: bool
    response: str
    sources: List[RAGSource] = Field(default_factory=list, description="Source references")
    confidence: str = Field("low", description="Confidence level: high, medium, low")
    summary_context: str = Field("", description="Context used from summaries")
    model: str = "Qwen/Qwen2.5-7B-Instruct"
    token_usage: Optional[TokenUsage] = Field(None, description="Token usage for this request")
    tables: List[TableContent] = Field(default_factory=list, description="Related tables from documents")
    images: List[ImageContent] = Field(default_factory=list, description="Related images from documents")


class SummarySearchResponse(BaseModel):
    """Response from summary search (without LLM call)."""
    results: List[dict] = Field(default_factory=list)
    confidence: str = "low"
    context_string: str = ""
    total_results: int = 0
    error: Optional[str] = None


@router.post("/rag/chat", response_model=RAGChatResponse)
async def rag_chat(
    request: RAGChatRequest,
    current_user: dict = Depends(get_current_user),
    service: OpenAgentService = Depends(get_service)
) -> RAGChatResponse:
    """
    RAG-enhanced chat using summary documents.

    This endpoint:
    1. Searches summaries for relevant context (commands, errors, terms, APIs)
    2. Enriches the prompt with summary information
    3. Sends to vLLM for response generation
    4. Returns response with source references

    Args:
        request: RAG chat request
        current_user: Authenticated user

    Returns:
        RAGChatResponse with AI response and source references
    """
    try:
        logger.info(f"RAG chat request from user {current_user.get('user_id', 'unknown')}")

        # Convert history if provided
        history = None
        if request.history:
            history = [{"role": m.role, "content": m.content} for m in request.history]

        result = await service.rag_chat(
            message=request.message,
            file_content=request.file_content,
            history=history,
            use_summaries=request.use_summaries,
            language=request.language or "ja",
        )

        # Extract token usage
        token_usage_data = result.get("token_usage")
        token_usage = None
        if token_usage_data:
            token_usage = TokenUsage(
                prompt_tokens=token_usage_data.get("prompt_tokens", 0),
                completion_tokens=token_usage_data.get("completion_tokens", 0),
                total_tokens=token_usage_data.get("total_tokens", 0),
            )

        # Extract tables from result
        tables = []
        for t in result.get("tables", []):
            tables.append(TableContent(
                chunk_id=t.get("chunk_id"),
                content=t.get("content", ""),
                page_start=t.get("page_start"),
                page_end=t.get("page_end"),
                doc_filename=t.get("doc_filename"),
            ))

        # Extract images from result
        images = []
        for img in result.get("images", []):
            images.append(ImageContent(
                chunk_id=img.get("chunk_id"),
                content=img.get("content", ""),
                page_start=img.get("page_start"),
                page_end=img.get("page_end"),
                doc_filename=img.get("doc_filename"),
                image_url=img.get("image_url"),
            ))

        # Use model from result (may be vision/minicpm-v or text/qwen), fallback to service config
        actual_model = result.get("model", service.config.model)

        return RAGChatResponse(
            success=True,
            response=result["response"],
            sources=[RAGSource(type=s["type"], file=s["file"]) for s in result.get("sources", [])],
            confidence=result.get("confidence", "low"),
            summary_context=result.get("summary_context", ""),
            model=actual_model,
            token_usage=token_usage,
            tables=tables,
            images=images,
        )

    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request timed out. The model may be overloaded."
        )
    except Exception as e:
        logger.exception(f"Error in RAG chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/rag/stream")
async def rag_stream_chat(
    request: RAGChatRequest,
    current_user: dict = Depends(get_current_user),
    service: OpenAgentService = Depends(get_service)
):
    """
    RAG-enhanced streaming chat.

    Streams:
    1. First, context info (sources, confidence)
    2. Then, response chunks
    3. Finally, completion info

    Args:
        request: RAG chat request
        current_user: Authenticated user

    Returns:
        Server-Sent Events stream with JSON-formatted events
    """
    import json

    logger.info(f"RAG stream request from user {current_user.get('user_id', 'unknown')}")

    # Convert history if provided
    history = None
    if request.history:
        history = [{"role": m.role, "content": m.content} for m in request.history]

    async def generate():
        """Generate SSE events from RAG stream."""
        try:
            async for item in service.rag_stream(
                message=request.message,
                file_content=request.file_content,
                history=history,
                use_summaries=request.use_summaries,
                language=request.language or "ja",
            ):
                # Format as SSE with JSON data
                yield f"data: {json.dumps(item)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"RAG stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/rag/search", response_model=SummarySearchResponse)
async def search_summaries(
    request: RAGChatRequest,
    current_user: dict = Depends(get_current_user),
    service: OpenAgentService = Depends(get_service)
) -> SummarySearchResponse:
    """
    Search summaries without calling LLM.

    Useful for:
    - Debugging RAG retrieval
    - Getting raw summary data
    - Understanding what context would be used

    Args:
        request: Search request (only message field is used)
        current_user: Authenticated user

    Returns:
        SummarySearchResponse with search results
    """
    try:
        result = await service.search_summaries(request.message)

        return SummarySearchResponse(
            results=result.get("results", []),
            confidence=result.get("confidence", "low"),
            context_string=result.get("context_string", ""),
            total_results=result.get("total_results", 0),
            error=result.get("error"),
        )

    except Exception as e:
        logger.exception(f"Error in summary search: {e}")
        return SummarySearchResponse(
            results=[],
            confidence="low",
            error=str(e),
        )


@router.get("/rag/summary/{file_path:path}")
async def read_summary_file(
    file_path: str,
    current_user: dict = Depends(get_current_user),
    service: OpenAgentService = Depends(get_service)
):
    """
    Read a specific summary file.

    Args:
        file_path: Relative path within summaries directory
                  (e.g., "commands/OpenFrame_TJES_MVS.md")
        current_user: Authenticated user

    Returns:
        File content or error
    """
    content = await service.read_summary_file(file_path)

    if content:
        return {
            "success": True,
            "file_path": file_path,
            "content": content,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Summary file not found: {file_path}"
        )
