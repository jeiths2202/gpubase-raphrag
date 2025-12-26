"""
Enterprise Features Router
Security, Audit, Versioning, and Collaboration APIs
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from pydantic import BaseModel, Field

from ..services.security_service import (
    get_mfa_service, get_rate_limiter, get_session_manager,
    MFASetup, MFAVerification, RateLimitResult, SessionInfo,
    PasswordSecurity
)
from ..services.audit_service import (
    get_audit_service, AuditEventType, AuditSeverity,
    AuditSearchCriteria, AuditStats
)
from ..services.version_service import (
    get_version_service, VersionStatus, DocumentVersion,
    DocumentHistory, VersionDiff
)
from ..services.collaboration_service import (
    get_collaboration_service, CommentStatus, ReactionType,
    Comment, CommentThread
)
from ..core.deps import get_current_user

router = APIRouter(prefix="/enterprise", tags=["Enterprise"])


# ================== MFA Endpoints ==================

class MFASetupResponse(BaseModel):
    secret: str
    qr_code_uri: str
    backup_codes: List[str]


class MFAVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class MFAVerifyResponse(BaseModel):
    success: bool
    message: str
    remaining_attempts: int = 3


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    current_user: dict = Depends(get_current_user)
):
    """Set up MFA for current user"""
    mfa_service = get_mfa_service()

    result = mfa_service.setup_mfa(
        user_id=current_user.get("user_id") or current_user.get("id"),
        user_email=current_user.get("email", "user@example.com")
    )

    return MFASetupResponse(
        secret=result.secret,
        qr_code_uri=result.qr_code_uri,
        backup_codes=result.backup_codes
    )


@router.post("/mfa/verify", response_model=MFAVerifyResponse)
async def verify_mfa(
    request: MFAVerifyRequest,
    current_user: dict = Depends(get_current_user)
):
    """Verify MFA code"""
    mfa_service = get_mfa_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    result = mfa_service.verify_totp(user_id, request.code)

    return MFAVerifyResponse(
        success=result.success,
        message=result.message,
        remaining_attempts=result.remaining_attempts
    )


@router.post("/mfa/verify-backup", response_model=MFAVerifyResponse)
async def verify_backup_code(
    request: MFAVerifyRequest,
    current_user: dict = Depends(get_current_user)
):
    """Verify MFA backup code"""
    mfa_service = get_mfa_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    result = mfa_service.verify_backup_code(user_id, request.code)

    return MFAVerifyResponse(
        success=result.success,
        message=result.message,
        remaining_attempts=result.remaining_attempts
    )


@router.get("/mfa/status")
async def get_mfa_status(
    current_user: dict = Depends(get_current_user)
):
    """Get MFA status for current user"""
    mfa_service = get_mfa_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    return {
        "enabled": mfa_service.is_mfa_enabled(user_id)
    }


@router.delete("/mfa")
async def disable_mfa(
    current_user: dict = Depends(get_current_user)
):
    """Disable MFA for current user"""
    mfa_service = get_mfa_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    success = mfa_service.disable_mfa(user_id)
    return {"success": success}


# ================== Session Management ==================

class SessionResponse(BaseModel):
    session_id: str
    ip_address: str
    user_agent: str
    created_at: str
    last_activity: str
    is_current: bool = False


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """List all active sessions for current user"""
    session_manager = get_session_manager()
    user_id = current_user.get("user_id") or current_user.get("id")

    sessions = session_manager.get_user_sessions(user_id)
    current_ip = request.client.host if request.client else None

    return [
        SessionResponse(
            session_id=s.session_id[:12] + "...",
            ip_address=s.ip_address,
            user_agent=s.user_agent[:50] + "..." if len(s.user_agent) > 50 else s.user_agent,
            created_at=s.created_at.isoformat(),
            last_activity=s.last_activity.isoformat(),
            is_current=s.ip_address == current_ip
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def invalidate_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Invalidate a specific session"""
    session_manager = get_session_manager()
    session_manager.invalidate_session(session_id)
    return {"success": True}


@router.delete("/sessions")
async def invalidate_all_sessions(
    current_user: dict = Depends(get_current_user)
):
    """Invalidate all sessions (logout everywhere)"""
    session_manager = get_session_manager()
    user_id = current_user.get("user_id") or current_user.get("id")

    session_manager.invalidate_all_user_sessions(user_id)
    return {"success": True, "message": "All sessions invalidated"}


# ================== Password Management ==================

class PasswordValidateRequest(BaseModel):
    password: str = Field(..., min_length=1)


class PasswordValidateResponse(BaseModel):
    valid: bool
    violations: List[str]


@router.post("/password/validate", response_model=PasswordValidateResponse)
async def validate_password(request: PasswordValidateRequest):
    """Validate password against security policies"""
    valid, violations = PasswordSecurity.validate_password(request.password)

    return PasswordValidateResponse(
        valid=valid,
        violations=violations
    )


# ================== Audit Logging ==================

class AuditEventResponse(BaseModel):
    id: str
    timestamp: str
    event_type: str
    severity: str
    user_id: Optional[str]
    action: str
    ip_address: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Dict[str, Any]


class AuditSearchRequest(BaseModel):
    user_id: Optional[str] = None
    event_types: Optional[List[str]] = None
    severity_levels: Optional[List[str]] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AuditStatsResponse(BaseModel):
    total_events: int
    events_by_type: Dict[str, int]
    events_by_severity: Dict[str, int]
    events_by_user: Dict[str, int]
    events_by_hour: Dict[int, int]


@router.post("/audit/search", response_model=List[AuditEventResponse])
async def search_audit_logs(
    request: AuditSearchRequest,
    current_user: dict = Depends(get_current_user)
):
    """Search audit logs (admin only)"""
    audit_service = get_audit_service()

    # Build search criteria
    criteria = AuditSearchCriteria(
        user_id=request.user_id,
        event_types=[AuditEventType(et) for et in (request.event_types or [])],
        severity_levels=[AuditSeverity(sl) for sl in (request.severity_levels or [])],
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        start_time=datetime.fromisoformat(request.start_time) if request.start_time else None,
        end_time=datetime.fromisoformat(request.end_time) if request.end_time else None,
        limit=request.limit,
        offset=request.offset
    )

    events = audit_service.search(criteria)

    return [
        AuditEventResponse(
            id=e.id,
            timestamp=e.timestamp.isoformat(),
            event_type=e.event_type.value,
            severity=e.severity.value,
            user_id=e.user_id,
            action=e.action,
            ip_address=e.ip_address,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            details=e.details
        )
        for e in events
    ]


@router.get("/audit/stats", response_model=AuditStatsResponse)
async def get_audit_stats(
    hours: int = Query(default=24, ge=1, le=168),
    current_user: dict = Depends(get_current_user)
):
    """Get audit statistics"""
    audit_service = get_audit_service()
    stats = audit_service.get_stats(hours)

    return AuditStatsResponse(
        total_events=stats.total_events,
        events_by_type=stats.events_by_type,
        events_by_severity=stats.events_by_severity,
        events_by_user=stats.events_by_user,
        events_by_hour=stats.events_by_hour
    )


@router.get("/audit/security", response_model=List[AuditEventResponse])
async def get_security_events(
    hours: int = Query(default=24, ge=1, le=168),
    current_user: dict = Depends(get_current_user)
):
    """Get recent security events"""
    audit_service = get_audit_service()
    events = audit_service.get_security_events(hours)

    return [
        AuditEventResponse(
            id=e.id,
            timestamp=e.timestamp.isoformat(),
            event_type=e.event_type.value,
            severity=e.severity.value,
            user_id=e.user_id,
            action=e.action,
            ip_address=e.ip_address,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            details=e.details
        )
        for e in events
    ]


@router.get("/audit/export")
async def export_audit_logs(
    format: str = Query(default="json", regex="^(json|csv)$"),
    days: int = Query(default=7, ge=1, le=90),
    current_user: dict = Depends(get_current_user)
):
    """Export audit logs"""
    audit_service = get_audit_service()

    criteria = AuditSearchCriteria(
        start_time=datetime.utcnow() - timedelta(days=days),
        limit=10000
    )

    content = audit_service.export_logs(criteria, format)

    return {
        "format": format,
        "content": content,
        "exported_at": datetime.utcnow().isoformat()
    }


# ================== Document Versioning ==================

class VersionResponse(BaseModel):
    id: str
    document_id: str
    version_number: int
    title: str
    status: str
    created_by: str
    created_at: str
    change_type: str
    change_summary: str
    size_bytes: int


class VersionHistoryResponse(BaseModel):
    document_id: str
    current_version: int
    total_versions: int
    versions: List[VersionResponse]
    created_at: str
    last_modified_at: str


class CreateVersionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    change_summary: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class VersionDiffResponse(BaseModel):
    from_version: int
    to_version: int
    additions: int
    deletions: int
    unified_diff: str


@router.post("/versions/{document_id}", response_model=VersionResponse)
async def create_version(
    document_id: str,
    request: CreateVersionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create new version of a document"""
    version_service = get_version_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    version = version_service.create_new_version(
        document_id=document_id,
        title=request.title,
        content=request.content,
        created_by=user_id,
        change_summary=request.change_summary,
        metadata=request.metadata
    )

    if not version:
        raise HTTPException(status_code=400, detail="No changes detected")

    return VersionResponse(
        id=version.id,
        document_id=version.document_id,
        version_number=version.version_number,
        title=version.title,
        status=version.status.value,
        created_by=version.created_by,
        created_at=version.created_at.isoformat(),
        change_type=version.change_type.value,
        change_summary=version.change_summary,
        size_bytes=version.size_bytes
    )


@router.get("/versions/{document_id}", response_model=VersionHistoryResponse)
async def get_version_history(
    document_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """Get version history for a document"""
    version_service = get_version_service()
    history = version_service.get_version_history(document_id, limit, offset)

    return VersionHistoryResponse(
        document_id=history.document_id,
        current_version=history.current_version,
        total_versions=history.total_versions,
        versions=[
            VersionResponse(
                id=v.id,
                document_id=v.document_id,
                version_number=v.version_number,
                title=v.title,
                status=v.status.value,
                created_by=v.created_by,
                created_at=v.created_at.isoformat(),
                change_type=v.change_type.value,
                change_summary=v.change_summary,
                size_bytes=v.size_bytes
            )
            for v in history.versions
        ],
        created_at=history.created_at.isoformat(),
        last_modified_at=history.last_modified_at.isoformat()
    )


@router.get("/versions/{document_id}/{version_number}")
async def get_version_content(
    document_id: str,
    version_number: int,
    current_user: dict = Depends(get_current_user)
):
    """Get specific version content"""
    version_service = get_version_service()
    version = version_service.get_version_by_number(document_id, version_number)

    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    return {
        "id": version.id,
        "version_number": version.version_number,
        "title": version.title,
        "content": version.content,
        "metadata": version.metadata,
        "created_at": version.created_at.isoformat()
    }


@router.post("/versions/{document_id}/restore/{version_number}", response_model=VersionResponse)
async def restore_version(
    document_id: str,
    version_number: int,
    current_user: dict = Depends(get_current_user)
):
    """Restore a previous version"""
    version_service = get_version_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    version = version_service.restore_version(document_id, version_number, user_id)

    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    return VersionResponse(
        id=version.id,
        document_id=version.document_id,
        version_number=version.version_number,
        title=version.title,
        status=version.status.value,
        created_by=version.created_by,
        created_at=version.created_at.isoformat(),
        change_type=version.change_type.value,
        change_summary=version.change_summary,
        size_bytes=version.size_bytes
    )


@router.get("/versions/{document_id}/diff", response_model=VersionDiffResponse)
async def compare_versions(
    document_id: str,
    from_version: int = Query(...),
    to_version: int = Query(...),
    current_user: dict = Depends(get_current_user)
):
    """Compare two versions"""
    version_service = get_version_service()
    diff = version_service.compare_versions(document_id, from_version, to_version)

    if not diff:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    return VersionDiffResponse(
        from_version=diff.from_version,
        to_version=diff.to_version,
        additions=diff.additions,
        deletions=diff.deletions,
        unified_diff=diff.unified_diff
    )


# ================== Collaboration ==================

class CommentCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    thread_id: Optional[str] = None
    position: Optional[Dict[str, Any]] = None


class CommentResponse(BaseModel):
    id: str
    parent_type: str
    parent_id: str
    thread_id: Optional[str]
    author_id: str
    author_name: str
    content: str
    html_content: str
    status: str
    created_at: str
    updated_at: str
    reply_count: int
    is_pinned: bool
    reactions: Dict[str, int]


class ThreadResponse(BaseModel):
    id: str
    root_comment_id: str
    participant_count: int
    comment_count: int
    is_resolved: bool
    last_activity_at: str


class ReactionRequest(BaseModel):
    reaction_type: str = Field(..., regex="^(like|love|helpful|confused|celebrate|insightful)$")


@router.post("/comments/{parent_type}/{parent_id}", response_model=CommentResponse)
async def create_comment(
    parent_type: str,
    parent_id: str,
    request: CommentCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add a comment to a document or knowledge item"""
    collab_service = get_collaboration_service()

    comment = collab_service.add_comment(
        parent_type=parent_type,
        parent_id=parent_id,
        author_id=current_user.get("user_id") or current_user.get("id"),
        author_name=current_user.get("name", current_user.get("email", "User")),
        content=request.content,
        thread_id=request.thread_id,
        position=request.position
    )

    return _comment_to_response(comment)


@router.get("/comments/{parent_type}/{parent_id}", response_model=List[CommentResponse])
async def get_comments(
    parent_type: str,
    parent_id: str,
    include_resolved: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """Get comments for a document or knowledge item"""
    collab_service = get_collaboration_service()

    comments = collab_service.get_comments(
        parent_type=parent_type,
        parent_id=parent_id,
        include_resolved=include_resolved,
        limit=limit,
        offset=offset
    )

    return [_comment_to_response(c) for c in comments]


@router.put("/comments/{comment_id}")
async def update_comment(
    comment_id: str,
    request: CommentCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update a comment"""
    collab_service = get_collaboration_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    comment = collab_service.update_comment(comment_id, request.content, user_id)

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found or not authorized")

    return _comment_to_response(comment)


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a comment"""
    collab_service = get_collaboration_service()
    user_id = current_user.get("user_id") or current_user.get("id")
    is_admin = current_user.get("role") == "admin"

    success = collab_service.delete_comment(comment_id, user_id, is_admin)

    if not success:
        raise HTTPException(status_code=404, detail="Comment not found or not authorized")

    return {"success": True}


@router.post("/comments/{comment_id}/resolve")
async def resolve_comment(
    comment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Mark a comment as resolved"""
    collab_service = get_collaboration_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    success = collab_service.resolve_comment(comment_id, user_id)

    if not success:
        raise HTTPException(status_code=404, detail="Comment not found")

    return {"success": True}


@router.post("/comments/{comment_id}/unresolve")
async def unresolve_comment(
    comment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Unresolve a comment"""
    collab_service = get_collaboration_service()

    success = collab_service.unresolve_comment(comment_id)

    if not success:
        raise HTTPException(status_code=404, detail="Comment not found")

    return {"success": True}


@router.post("/comments/{comment_id}/reactions")
async def add_reaction(
    comment_id: str,
    request: ReactionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add a reaction to a comment"""
    collab_service = get_collaboration_service()

    success = collab_service.add_reaction(
        comment_id=comment_id,
        user_id=current_user.get("user_id") or current_user.get("id"),
        user_name=current_user.get("name", "User"),
        reaction_type=ReactionType(request.reaction_type)
    )

    if not success:
        raise HTTPException(status_code=400, detail="Unable to add reaction")

    return {"success": True}


@router.delete("/comments/{comment_id}/reactions/{reaction_type}")
async def remove_reaction(
    comment_id: str,
    reaction_type: str,
    current_user: dict = Depends(get_current_user)
):
    """Remove a reaction from a comment"""
    collab_service = get_collaboration_service()

    success = collab_service.remove_reaction(
        comment_id=comment_id,
        user_id=current_user.get("user_id") or current_user.get("id"),
        reaction_type=ReactionType(reaction_type)
    )

    return {"success": success}


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get thread details"""
    collab_service = get_collaboration_service()
    thread = collab_service.get_thread(thread_id)

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    return ThreadResponse(
        id=thread.id,
        root_comment_id=thread.root_comment_id,
        participant_count=len(thread.participant_ids),
        comment_count=thread.comment_count,
        is_resolved=thread.is_resolved,
        last_activity_at=thread.last_activity_at.isoformat()
    )


@router.get("/threads/{thread_id}/comments", response_model=List[CommentResponse])
async def get_thread_comments(
    thread_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all comments in a thread"""
    collab_service = get_collaboration_service()
    comments = collab_service.get_thread_comments(thread_id)

    return [_comment_to_response(c) for c in comments]


@router.get("/notifications")
async def get_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Get mention notifications for current user"""
    collab_service = get_collaboration_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    notifications = collab_service.get_user_notifications(user_id, unread_only, limit)

    return [
        {
            "id": n.id,
            "comment_id": n.comment_id,
            "mentioner_name": n.mentioner_name,
            "parent_type": n.parent_type,
            "parent_id": n.parent_id,
            "context_preview": n.context_preview,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat()
        }
        for n in notifications
    ]


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Mark notification as read"""
    collab_service = get_collaboration_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    success = collab_service.mark_notification_read(notification_id, user_id)
    return {"success": success}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    current_user: dict = Depends(get_current_user)
):
    """Mark all notifications as read"""
    collab_service = get_collaboration_service()
    user_id = current_user.get("user_id") or current_user.get("id")

    count = collab_service.mark_all_notifications_read(user_id)
    return {"success": True, "marked_count": count}


def _comment_to_response(comment: Comment) -> CommentResponse:
    """Convert Comment to response model"""
    reaction_counts = {
        rt: len(reactions)
        for rt, reactions in comment.reactions.items()
    }

    return CommentResponse(
        id=comment.id,
        parent_type=comment.parent_type,
        parent_id=comment.parent_id,
        thread_id=comment.thread_id,
        author_id=comment.author_id,
        author_name=comment.author_name,
        content=comment.content,
        html_content=comment.html_content,
        status=comment.status.value,
        created_at=comment.created_at.isoformat(),
        updated_at=comment.updated_at.isoformat(),
        reply_count=comment.reply_count,
        is_pinned=comment.is_pinned,
        reactions=reaction_counts
    )
