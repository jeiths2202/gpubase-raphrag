"""
Audit Logging Service
Enterprise-grade audit trail for compliance and security
"""
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict


class AuditEventType(str, Enum):
    """Types of audit events"""
    # Authentication events
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    MFA_ENABLED = "auth.mfa.enabled"
    MFA_DISABLED = "auth.mfa.disabled"
    MFA_VERIFIED = "auth.mfa.verified"
    MFA_FAILED = "auth.mfa.failed"
    PASSWORD_CHANGED = "auth.password.changed"
    PASSWORD_RESET_REQUESTED = "auth.password.reset_requested"
    SESSION_CREATED = "auth.session.created"
    SESSION_EXPIRED = "auth.session.expired"
    SESSION_INVALIDATED = "auth.session.invalidated"

    # Document events
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    DOCUMENT_VIEWED = "document.viewed"
    DOCUMENT_DOWNLOADED = "document.downloaded"
    DOCUMENT_SHARED = "document.shared"
    DOCUMENT_UNSHARED = "document.unshared"
    DOCUMENT_VERSION_CREATED = "document.version.created"
    DOCUMENT_VERSION_RESTORED = "document.version.restored"

    # Knowledge events
    KNOWLEDGE_REGISTERED = "knowledge.registered"
    KNOWLEDGE_APPROVED = "knowledge.approved"
    KNOWLEDGE_REJECTED = "knowledge.rejected"
    KNOWLEDGE_PUBLISHED = "knowledge.published"
    KNOWLEDGE_ARCHIVED = "knowledge.archived"
    KNOWLEDGE_QUERIED = "knowledge.queried"

    # External resource events
    EXTERNAL_CONNECTED = "external.connected"
    EXTERNAL_DISCONNECTED = "external.disconnected"
    EXTERNAL_SYNCED = "external.synced"
    EXTERNAL_SYNC_FAILED = "external.sync.failed"

    # Admin events
    USER_CREATED = "admin.user.created"
    USER_UPDATED = "admin.user.updated"
    USER_DELETED = "admin.user.deleted"
    USER_ROLE_CHANGED = "admin.user.role_changed"
    PERMISSION_GRANTED = "admin.permission.granted"
    PERMISSION_REVOKED = "admin.permission.revoked"
    SETTINGS_CHANGED = "admin.settings.changed"

    # Security events
    RATE_LIMIT_EXCEEDED = "security.rate_limit.exceeded"
    SUSPICIOUS_ACTIVITY = "security.suspicious_activity"
    IP_BLOCKED = "security.ip.blocked"
    ACCESS_DENIED = "security.access.denied"

    # API events
    API_CALL = "api.call"
    API_ERROR = "api.error"


class AuditSeverity(str, Enum):
    """Severity levels for audit events"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event record"""
    id: str
    timestamp: datetime
    event_type: AuditEventType
    severity: AuditSeverity
    user_id: Optional[str]
    user_email: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[str]
    action: str
    details: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["event_type"] = self.event_type.value
        data["severity"] = self.severity.value
        return data

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class AuditSearchCriteria:
    """Search criteria for audit logs"""
    user_id: Optional[str] = None
    event_types: Optional[List[AuditEventType]] = None
    severity_levels: Optional[List[AuditSeverity]] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


@dataclass
class AuditStats:
    """Audit statistics"""
    total_events: int
    events_by_type: Dict[str, int]
    events_by_severity: Dict[str, int]
    events_by_user: Dict[str, int]
    events_by_hour: Dict[int, int]
    recent_security_events: List[AuditEvent]


class AuditService:
    """
    Comprehensive audit logging service.
    For production, integrate with:
    - ELK Stack (Elasticsearch, Logstash, Kibana)
    - Splunk
    - AWS CloudTrail
    - Azure Monitor
    """

    # In-memory storage (use database/external service in production)
    _events: List[AuditEvent] = []
    _events_by_user: Dict[str, List[str]] = defaultdict(list)
    _events_by_resource: Dict[str, List[str]] = defaultdict(list)
    _event_index: Dict[str, AuditEvent] = {}

    # Retention settings
    RETENTION_DAYS = 90
    MAX_EVENTS = 100000

    def log(
        self,
        event_type: AuditEventType,
        action: str,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        details: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """
        Log an audit event.

        Args:
            event_type: Type of event
            action: Human-readable action description
            user_id: User performing the action
            user_email: User's email
            ip_address: Client IP address
            user_agent: Client user agent
            resource_type: Type of resource affected
            resource_id: ID of resource affected
            severity: Event severity level
            details: Additional event details
            metadata: Extra metadata

        Returns:
            Created AuditEvent
        """
        event = AuditEvent(
            id=f"audit_{uuid.uuid4().hex}",
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details or {},
            metadata=metadata or {}
        )

        # Store event
        self._events.append(event)
        self._event_index[event.id] = event

        if user_id:
            self._events_by_user[user_id].append(event.id)

        if resource_id:
            key = f"{resource_type}:{resource_id}"
            self._events_by_resource[key].append(event.id)

        # Enforce retention
        self._enforce_retention()

        return event

    def log_auth_success(
        self,
        user_id: str,
        user_email: str,
        ip_address: str,
        user_agent: str,
        auth_method: str = "password"
    ) -> AuditEvent:
        """Log successful authentication"""
        return self.log(
            event_type=AuditEventType.LOGIN_SUCCESS,
            action=f"User logged in via {auth_method}",
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"auth_method": auth_method}
        )

    def log_auth_failure(
        self,
        user_email: str,
        ip_address: str,
        user_agent: str,
        reason: str = "invalid_credentials"
    ) -> AuditEvent:
        """Log failed authentication attempt"""
        return self.log(
            event_type=AuditEventType.LOGIN_FAILURE,
            action=f"Login failed: {reason}",
            user_email=user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            severity=AuditSeverity.WARNING,
            details={"reason": reason}
        )

    def log_document_access(
        self,
        user_id: str,
        document_id: str,
        document_name: str,
        action_type: str,  # view, download, edit, delete
        ip_address: Optional[str] = None
    ) -> AuditEvent:
        """Log document access"""
        event_map = {
            "view": AuditEventType.DOCUMENT_VIEWED,
            "download": AuditEventType.DOCUMENT_DOWNLOADED,
            "edit": AuditEventType.DOCUMENT_UPDATED,
            "delete": AuditEventType.DOCUMENT_DELETED,
            "create": AuditEventType.DOCUMENT_CREATED
        }

        return self.log(
            event_type=event_map.get(action_type, AuditEventType.DOCUMENT_VIEWED),
            action=f"Document {action_type}: {document_name}",
            user_id=user_id,
            ip_address=ip_address,
            resource_type="document",
            resource_id=document_id,
            details={"document_name": document_name, "action_type": action_type}
        )

    def log_knowledge_query(
        self,
        user_id: str,
        query: str,
        strategy: str,
        sources_count: int,
        ip_address: Optional[str] = None
    ) -> AuditEvent:
        """Log knowledge base query"""
        return self.log(
            event_type=AuditEventType.KNOWLEDGE_QUERIED,
            action=f"Knowledge query executed",
            user_id=user_id,
            ip_address=ip_address,
            resource_type="knowledge",
            details={
                "query_preview": query[:100] + "..." if len(query) > 100 else query,
                "strategy": strategy,
                "sources_count": sources_count
            }
        )

    def log_security_event(
        self,
        event_type: AuditEventType,
        action: str,
        ip_address: str,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Log security-related event"""
        return self.log(
            event_type=event_type,
            action=action,
            user_id=user_id,
            ip_address=ip_address,
            severity=AuditSeverity.WARNING,
            details=details or {}
        )

    def log_api_call(
        self,
        user_id: Optional[str],
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: int,
        ip_address: Optional[str] = None
    ) -> AuditEvent:
        """Log API call"""
        severity = AuditSeverity.INFO
        if status_code >= 500:
            severity = AuditSeverity.ERROR
        elif status_code >= 400:
            severity = AuditSeverity.WARNING

        return self.log(
            event_type=AuditEventType.API_CALL if status_code < 400 else AuditEventType.API_ERROR,
            action=f"{method} {endpoint} -> {status_code}",
            user_id=user_id,
            ip_address=ip_address,
            severity=severity,
            details={
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "response_time_ms": response_time_ms
            }
        )

    def search(self, criteria: AuditSearchCriteria) -> List[AuditEvent]:
        """
        Search audit logs with criteria.

        Args:
            criteria: Search criteria

        Returns:
            List of matching events
        """
        results = []

        for event in reversed(self._events):  # Most recent first
            # Apply filters
            if criteria.user_id and event.user_id != criteria.user_id:
                continue

            if criteria.event_types and event.event_type not in criteria.event_types:
                continue

            if criteria.severity_levels and event.severity not in criteria.severity_levels:
                continue

            if criteria.resource_type and event.resource_type != criteria.resource_type:
                continue

            if criteria.resource_id and event.resource_id != criteria.resource_id:
                continue

            if criteria.ip_address and event.ip_address != criteria.ip_address:
                continue

            if criteria.start_time and event.timestamp < criteria.start_time:
                continue

            if criteria.end_time and event.timestamp > criteria.end_time:
                continue

            results.append(event)

            if len(results) >= criteria.offset + criteria.limit:
                break

        return results[criteria.offset:criteria.offset + criteria.limit]

    def get_user_activity(
        self,
        user_id: str,
        days: int = 30,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get user activity for specified period"""
        criteria = AuditSearchCriteria(
            user_id=user_id,
            start_time=datetime.now(timezone.utc) - timedelta(days=days),
            limit=limit
        )
        return self.search(criteria)

    def get_resource_history(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 50
    ) -> List[AuditEvent]:
        """Get history of actions on a resource"""
        key = f"{resource_type}:{resource_id}"
        event_ids = self._events_by_resource.get(key, [])

        events = []
        for event_id in reversed(event_ids[-limit:]):
            if event_id in self._event_index:
                events.append(self._event_index[event_id])

        return events

    def get_security_events(
        self,
        hours: int = 24,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get recent security-related events"""
        security_types = [
            AuditEventType.LOGIN_FAILURE,
            AuditEventType.MFA_FAILED,
            AuditEventType.RATE_LIMIT_EXCEEDED,
            AuditEventType.SUSPICIOUS_ACTIVITY,
            AuditEventType.IP_BLOCKED,
            AuditEventType.ACCESS_DENIED
        ]

        criteria = AuditSearchCriteria(
            event_types=security_types,
            start_time=datetime.now(timezone.utc) - timedelta(hours=hours),
            limit=limit
        )
        return self.search(criteria)

    def get_stats(self, hours: int = 24) -> AuditStats:
        """Get audit statistics for specified period"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        events_by_type: Dict[str, int] = defaultdict(int)
        events_by_severity: Dict[str, int] = defaultdict(int)
        events_by_user: Dict[str, int] = defaultdict(int)
        events_by_hour: Dict[int, int] = defaultdict(int)
        security_events: List[AuditEvent] = []
        total = 0

        for event in self._events:
            if event.timestamp < cutoff:
                continue

            total += 1
            events_by_type[event.event_type.value] += 1
            events_by_severity[event.severity.value] += 1

            if event.user_id:
                events_by_user[event.user_id] += 1

            events_by_hour[event.timestamp.hour] += 1

            if event.severity in [AuditSeverity.WARNING, AuditSeverity.ERROR, AuditSeverity.CRITICAL]:
                security_events.append(event)

        return AuditStats(
            total_events=total,
            events_by_type=dict(events_by_type),
            events_by_severity=dict(events_by_severity),
            events_by_user=dict(events_by_user),
            events_by_hour=dict(events_by_hour),
            recent_security_events=security_events[:20]
        )

    def export_logs(
        self,
        criteria: AuditSearchCriteria,
        format: str = "json"  # json, csv
    ) -> str:
        """Export audit logs in specified format"""
        events = self.search(criteria)

        if format == "json":
            return json.dumps(
                [e.to_dict() for e in events],
                ensure_ascii=False,
                indent=2
            )
        elif format == "csv":
            if not events:
                return "id,timestamp,event_type,severity,user_id,action,ip_address"

            headers = "id,timestamp,event_type,severity,user_id,action,ip_address"
            rows = [headers]
            for e in events:
                row = f'"{e.id}","{e.timestamp.isoformat()}","{e.event_type.value}","{e.severity.value}","{e.user_id or ""}","{e.action}","{e.ip_address or ""}"'
                rows.append(row)
            return "\n".join(rows)

        return ""

    def _enforce_retention(self):
        """Enforce retention policies"""
        # Remove old events
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.RETENTION_DAYS)

        while self._events and self._events[0].timestamp < cutoff:
            old_event = self._events.pop(0)
            if old_event.id in self._event_index:
                del self._event_index[old_event.id]

        # Enforce max events
        while len(self._events) > self.MAX_EVENTS:
            old_event = self._events.pop(0)
            if old_event.id in self._event_index:
                del self._event_index[old_event.id]


# Singleton instance
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get audit service singleton"""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service
