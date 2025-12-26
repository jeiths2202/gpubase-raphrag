"""
External Connection Router
API endpoints for managing external resource connections (OneNote, GitHub, Google Drive, Notion, Confluence)
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..models.external_connection import (
    ExternalResourceType, ConnectionStatus, SyncStatus,
    ExternalConnectionCreate, ExternalConnectionResponse,
    OAuthCallbackRequest, OAuthInitResponse,
    ConnectionListResponse, SyncRequest, SyncResponse,
    ExternalDocumentListResponse, EXTERNAL_RESOURCE_CONFIGS
)
from ..services.external_document_service import get_external_document_service

router = APIRouter(
    prefix="/external-connections",
    tags=["External Connections"]
)


# ================== Response Models ==================

class AvailableResourcesResponse(BaseModel):
    """List of available external resources"""
    resources: List[dict]


class UserStatsResponse(BaseModel):
    """User's external resource statistics"""
    total_connections: int
    active_connections: int
    total_documents: int
    ready_documents: int
    total_chunks: int
    by_connection: dict
    by_source: dict


class OAuthUrlResponse(BaseModel):
    """OAuth URL response"""
    oauth_url: str
    connection_id: str


# ================== Endpoints ==================

@router.get("/available", response_model=AvailableResourcesResponse)
async def get_available_resources():
    """
    Get list of available external resource types.
    Returns configuration for each supported resource.
    """
    service = get_external_document_service()
    resources = service.get_available_resources()

    return AvailableResourcesResponse(
        resources=[
            {
                "type": rt,
                **info
            }
            for rt, info in resources.items()
        ]
    )


@router.get("", response_model=ConnectionListResponse)
async def list_connections(
    user_id: str = Query(..., description="User ID")
):
    """
    List all external connections for a user.
    """
    service = get_external_document_service()
    connections = service.get_user_connections(user_id)

    return ConnectionListResponse(
        connections=[
            ExternalConnectionResponse(
                id=conn.id,
                user_id=conn.user_id,
                resource_type=conn.resource_type,
                status=conn.status,
                auth_type=conn.auth_type,
                last_sync_at=conn.last_sync_at,
                sync_status=conn.sync_status,
                document_count=conn.document_count,
                chunk_count=conn.chunk_count,
                created_at=conn.created_at,
                error_message=conn.sync_error
            )
            for conn in connections
        ],
        total=len(connections)
    )


@router.post("", response_model=ExternalConnectionResponse)
async def create_connection(
    request: ExternalConnectionCreate,
    user_id: str = Query(..., description="User ID")
):
    """
    Create a new external resource connection.

    For OAuth resources (OneNote, GitHub, Google Drive, Notion):
    - Creates connection in 'not_connected' state
    - Call /oauth-url to get authorization URL

    For API token resources (Confluence):
    - Provide api_token in request
    - Connection validated immediately
    """
    service = get_external_document_service()

    try:
        connection = await service.create_connection(
            user_id=user_id,
            resource_type=request.resource_type,
            api_token=request.api_token,
            config=request.config
        )

        return ExternalConnectionResponse(
            id=connection.id,
            user_id=connection.user_id,
            resource_type=connection.resource_type,
            status=connection.status,
            auth_type=connection.auth_type,
            last_sync_at=connection.last_sync_at,
            sync_status=connection.sync_status,
            document_count=connection.document_count,
            chunk_count=connection.chunk_count,
            created_at=connection.created_at,
            error_message=connection.sync_error
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{connection_id}", response_model=ExternalConnectionResponse)
async def get_connection(connection_id: str):
    """Get connection details"""
    service = get_external_document_service()
    connection = service.get_connection(connection_id)

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    return ExternalConnectionResponse(
        id=connection.id,
        user_id=connection.user_id,
        resource_type=connection.resource_type,
        status=connection.status,
        auth_type=connection.auth_type,
        last_sync_at=connection.last_sync_at,
        sync_status=connection.sync_status,
        document_count=connection.document_count,
        chunk_count=connection.chunk_count,
        created_at=connection.created_at,
        error_message=connection.sync_error
    )


@router.delete("/{connection_id}")
async def disconnect(connection_id: str):
    """
    Disconnect and remove an external resource.
    This removes all synced documents and chunks.
    """
    service = get_external_document_service()
    success = await service.disconnect(connection_id)

    if not success:
        raise HTTPException(status_code=404, detail="Connection not found")

    return {"success": True, "message": "Connection removed"}


# ================== OAuth Flow ==================

@router.get("/{connection_id}/oauth-url", response_model=OAuthUrlResponse)
async def get_oauth_url(
    connection_id: str,
    redirect_uri: str = Query(..., description="OAuth callback URI")
):
    """
    Get OAuth authorization URL for a connection.
    Redirect user to this URL to authorize access.
    """
    service = get_external_document_service()
    oauth_url = service.get_oauth_url(connection_id, redirect_uri)

    if not oauth_url:
        raise HTTPException(
            status_code=400,
            detail="OAuth not available for this resource type"
        )

    return OAuthUrlResponse(
        oauth_url=oauth_url,
        connection_id=connection_id
    )


@router.post("/{connection_id}/oauth-callback")
async def oauth_callback(
    connection_id: str,
    code: str = Query(..., description="Authorization code"),
    redirect_uri: str = Query(..., description="Redirect URI used in initial request")
):
    """
    Complete OAuth flow with authorization code.
    Called after user authorizes access in the OAuth flow.
    """
    service = get_external_document_service()

    try:
        connection = await service.complete_oauth(
            connection_id=connection_id,
            code=code,
            redirect_uri=redirect_uri
        )

        return ExternalConnectionResponse(
            id=connection.id,
            user_id=connection.user_id,
            resource_type=connection.resource_type,
            status=connection.status,
            auth_type=connection.auth_type,
            last_sync_at=connection.last_sync_at,
            sync_status=connection.sync_status,
            document_count=connection.document_count,
            chunk_count=connection.chunk_count,
            created_at=connection.created_at,
            error_message=connection.sync_error
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ================== Sync Operations ==================

@router.post("/{connection_id}/sync", response_model=SyncResponse)
async def sync_connection(
    connection_id: str,
    request: Optional[SyncRequest] = None
):
    """
    Sync documents from external resource.

    - full_sync=False (default): Incremental sync (only changes since last sync)
    - full_sync=True: Full sync (re-fetch all documents)
    """
    service = get_external_document_service()
    full_sync = request.full_sync if request else False

    try:
        stats = await service.sync_connection(connection_id, full_sync)

        return SyncResponse(
            connection_id=connection_id,
            status=SyncStatus.COMPLETED if not stats.get("errors") else SyncStatus.FAILED,
            documents_synced=stats["documents_synced"],
            documents_added=stats["documents_added"],
            documents_updated=stats["documents_updated"],
            documents_deleted=stats["documents_deleted"],
            message=f"Synced {stats['documents_synced']} documents"
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{connection_id}/documents", response_model=ExternalDocumentListResponse)
async def list_connection_documents(
    connection_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    List synced documents for a connection.
    """
    service = get_external_document_service()
    connection = service.get_connection(connection_id)

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Get documents for this connection
    all_docs = [
        doc for doc in service._documents.values()
        if doc.connection_id == connection_id
    ]

    # Sort by updated_at descending
    all_docs.sort(key=lambda d: d.updated_at, reverse=True)

    # Paginate
    docs = all_docs[offset:offset + limit]

    return ExternalDocumentListResponse(
        documents=[
            {
                "id": doc.id,
                "title": doc.title,
                "path": doc.path,
                "external_url": doc.external_url,
                "status": doc.status.value,
                "chunk_count": doc.chunk_count,
                "last_synced_at": doc.last_synced_at.isoformat() if doc.last_synced_at else None,
                "external_modified_at": doc.external_modified_at.isoformat() if doc.external_modified_at else None
            }
            for doc in docs
        ],
        total=len(all_docs),
        connection_id=connection_id,
        resource_type=connection.resource_type
    )


# ================== User Stats ==================

@router.get("/stats/{user_id}", response_model=UserStatsResponse)
async def get_user_stats(user_id: str):
    """
    Get external resource statistics for a user.
    """
    service = get_external_document_service()
    stats = service.get_user_stats(user_id)

    return UserStatsResponse(**stats)


# ================== Search ==================

class ExternalSearchRequest(BaseModel):
    """Search request for external resources"""
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.3, ge=0.0, le=1.0)
    connection_ids: Optional[List[str]] = Field(default=None)


class ExternalSearchResultItem(BaseModel):
    """Search result item"""
    chunk_id: str
    document_id: str
    connection_id: str
    source: str
    content: str
    score: float
    source_name: str
    source_url: Optional[str] = None
    section_title: Optional[str] = None


class ExternalSearchResponse(BaseModel):
    """Search response"""
    results: List[ExternalSearchResultItem]
    total: int
    query: str


@router.post("/search", response_model=ExternalSearchResponse)
async def search_external_resources(
    request: ExternalSearchRequest,
    user_id: str = Query(..., description="User ID")
):
    """
    Search user's external resources.
    Returns relevant chunks from connected external resources.
    """
    service = get_external_document_service()

    results = await service.search_user_resources(
        user_id=user_id,
        query=request.query,
        top_k=request.top_k,
        min_score=request.min_score,
        connection_ids=request.connection_ids
    )

    return ExternalSearchResponse(
        results=[
            ExternalSearchResultItem(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                connection_id=r.connection_id,
                source=r.source.value if hasattr(r.source, 'value') else r.source,
                content=r.content,
                score=r.score,
                source_name=r.source_name,
                source_url=r.source_url,
                section_title=r.section_title
            )
            for r in results
        ],
        total=len(results),
        query=request.query
    )
