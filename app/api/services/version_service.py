"""
Document Versioning Service
Enterprise document version control with history tracking
"""
import uuid
import hashlib
import difflib
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict


class VersionStatus(str, Enum):
    """Version status"""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ChangeType(str, Enum):
    """Type of change"""
    CREATED = "created"
    CONTENT_UPDATED = "content_updated"
    METADATA_UPDATED = "metadata_updated"
    TITLE_CHANGED = "title_changed"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    RESTORED = "restored"


@dataclass
class DocumentVersion:
    """A specific version of a document"""
    id: str
    document_id: str
    version_number: int
    title: str
    content: str
    content_hash: str
    metadata: Dict[str, Any]
    status: VersionStatus
    created_by: str
    created_at: datetime
    change_type: ChangeType
    change_summary: str
    previous_version_id: Optional[str] = None
    size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["status"] = self.status.value
        data["change_type"] = self.change_type.value
        return data


@dataclass
class VersionDiff:
    """Difference between two versions"""
    from_version: int
    to_version: int
    additions: int
    deletions: int
    changes: List[Dict[str, Any]]
    unified_diff: str


@dataclass
class DocumentHistory:
    """Complete history of a document"""
    document_id: str
    current_version: int
    total_versions: int
    versions: List[DocumentVersion]
    created_at: datetime
    last_modified_at: datetime
    created_by: str
    last_modified_by: str


class VersionService:
    """
    Document version control service.
    Provides Git-like versioning for documents.
    """

    # In-memory storage (use database in production)
    _versions: Dict[str, List[DocumentVersion]] = defaultdict(list)
    _version_index: Dict[str, DocumentVersion] = {}
    _current_versions: Dict[str, str] = {}  # document_id -> current version_id

    # Settings
    MAX_VERSIONS_PER_DOCUMENT = 100
    AUTO_PRUNE_OLD_VERSIONS = True

    def create_initial_version(
        self,
        document_id: str,
        title: str,
        content: str,
        created_by: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentVersion:
        """
        Create initial version of a document.

        Args:
            document_id: Document identifier
            title: Document title
            content: Document content
            created_by: User ID of creator
            metadata: Optional metadata

        Returns:
            Created DocumentVersion
        """
        version = DocumentVersion(
            id=f"ver_{uuid.uuid4().hex}",
            document_id=document_id,
            version_number=1,
            title=title,
            content=content,
            content_hash=self._compute_hash(content),
            metadata=metadata or {},
            status=VersionStatus.DRAFT,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            change_type=ChangeType.CREATED,
            change_summary="Initial version created",
            size_bytes=len(content.encode('utf-8'))
        )

        self._versions[document_id].append(version)
        self._version_index[version.id] = version
        self._current_versions[document_id] = version.id

        return version

    def create_new_version(
        self,
        document_id: str,
        title: str,
        content: str,
        created_by: str,
        change_summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[DocumentVersion]:
        """
        Create a new version of a document.

        Args:
            document_id: Document identifier
            title: New title
            content: New content
            created_by: User ID
            change_summary: Description of changes
            metadata: Updated metadata

        Returns:
            New DocumentVersion or None if no changes
        """
        versions = self._versions.get(document_id, [])
        if not versions:
            return self.create_initial_version(
                document_id, title, content, created_by, metadata
            )

        current = versions[-1]
        new_hash = self._compute_hash(content)

        # Skip if content unchanged
        if new_hash == current.content_hash and title == current.title:
            return None

        # Determine change type
        change_type = ChangeType.CONTENT_UPDATED
        if title != current.title:
            change_type = ChangeType.TITLE_CHANGED
        elif new_hash != current.content_hash:
            change_type = ChangeType.CONTENT_UPDATED

        # Auto-generate change summary if not provided
        if not change_summary:
            change_summary = self._generate_change_summary(
                current.content, content, current.title, title
            )

        version = DocumentVersion(
            id=f"ver_{uuid.uuid4().hex}",
            document_id=document_id,
            version_number=current.version_number + 1,
            title=title,
            content=content,
            content_hash=new_hash,
            metadata={**current.metadata, **(metadata or {})},
            status=VersionStatus.DRAFT,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            change_type=change_type,
            change_summary=change_summary,
            previous_version_id=current.id,
            size_bytes=len(content.encode('utf-8'))
        )

        self._versions[document_id].append(version)
        self._version_index[version.id] = version
        self._current_versions[document_id] = version.id

        # Prune old versions if needed
        if self.AUTO_PRUNE_OLD_VERSIONS:
            self._prune_versions(document_id)

        return version

    def get_version(self, version_id: str) -> Optional[DocumentVersion]:
        """Get a specific version by ID"""
        return self._version_index.get(version_id)

    def get_version_by_number(
        self,
        document_id: str,
        version_number: int
    ) -> Optional[DocumentVersion]:
        """Get a specific version by number"""
        versions = self._versions.get(document_id, [])
        for v in versions:
            if v.version_number == version_number:
                return v
        return None

    def get_current_version(self, document_id: str) -> Optional[DocumentVersion]:
        """Get the current (latest) version"""
        version_id = self._current_versions.get(document_id)
        if version_id:
            return self._version_index.get(version_id)
        return None

    def get_version_history(
        self,
        document_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> DocumentHistory:
        """
        Get complete version history for a document.

        Args:
            document_id: Document identifier
            limit: Maximum versions to return
            offset: Offset for pagination

        Returns:
            DocumentHistory with versions
        """
        all_versions = self._versions.get(document_id, [])

        if not all_versions:
            return DocumentHistory(
                document_id=document_id,
                current_version=0,
                total_versions=0,
                versions=[],
                created_at=datetime.now(timezone.utc),
                last_modified_at=datetime.now(timezone.utc),
                created_by="",
                last_modified_by=""
            )

        # Get paginated versions (most recent first)
        sorted_versions = sorted(
            all_versions,
            key=lambda v: v.version_number,
            reverse=True
        )
        paginated = sorted_versions[offset:offset + limit]

        return DocumentHistory(
            document_id=document_id,
            current_version=all_versions[-1].version_number,
            total_versions=len(all_versions),
            versions=paginated,
            created_at=all_versions[0].created_at,
            last_modified_at=all_versions[-1].created_at,
            created_by=all_versions[0].created_by,
            last_modified_by=all_versions[-1].created_by
        )

    def restore_version(
        self,
        document_id: str,
        version_number: int,
        restored_by: str
    ) -> Optional[DocumentVersion]:
        """
        Restore a previous version as the new current version.

        Args:
            document_id: Document identifier
            version_number: Version number to restore
            restored_by: User ID performing restore

        Returns:
            New version created from restore
        """
        target = self.get_version_by_number(document_id, version_number)
        if not target:
            return None

        current = self.get_current_version(document_id)
        if not current:
            return None

        # Create new version from restored content
        version = DocumentVersion(
            id=f"ver_{uuid.uuid4().hex}",
            document_id=document_id,
            version_number=current.version_number + 1,
            title=target.title,
            content=target.content,
            content_hash=target.content_hash,
            metadata=target.metadata,
            status=VersionStatus.DRAFT,
            created_by=restored_by,
            created_at=datetime.now(timezone.utc),
            change_type=ChangeType.RESTORED,
            change_summary=f"Restored from version {version_number}",
            previous_version_id=current.id,
            size_bytes=target.size_bytes
        )

        self._versions[document_id].append(version)
        self._version_index[version.id] = version
        self._current_versions[document_id] = version.id

        return version

    def compare_versions(
        self,
        document_id: str,
        from_version: int,
        to_version: int
    ) -> Optional[VersionDiff]:
        """
        Compare two versions and generate diff.

        Args:
            document_id: Document identifier
            from_version: Source version number
            to_version: Target version number

        Returns:
            VersionDiff with changes
        """
        v1 = self.get_version_by_number(document_id, from_version)
        v2 = self.get_version_by_number(document_id, to_version)

        if not v1 or not v2:
            return None

        # Generate unified diff
        diff_lines = list(difflib.unified_diff(
            v1.content.splitlines(keepends=True),
            v2.content.splitlines(keepends=True),
            fromfile=f"v{from_version}",
            tofile=f"v{to_version}",
            lineterm=""
        ))

        # Count additions and deletions
        additions = sum(1 for line in diff_lines if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in diff_lines if line.startswith('-') and not line.startswith('---'))

        # Generate structured changes
        changes = []
        current_hunk = None

        for line in diff_lines:
            if line.startswith('@@'):
                if current_hunk:
                    changes.append(current_hunk)
                current_hunk = {
                    "header": line,
                    "lines": []
                }
            elif current_hunk is not None:
                current_hunk["lines"].append({
                    "type": "add" if line.startswith('+') else ("del" if line.startswith('-') else "context"),
                    "content": line[1:] if line and line[0] in '+-' else line
                })

        if current_hunk:
            changes.append(current_hunk)

        return VersionDiff(
            from_version=from_version,
            to_version=to_version,
            additions=additions,
            deletions=deletions,
            changes=changes,
            unified_diff="".join(diff_lines)
        )

    def publish_version(
        self,
        document_id: str,
        published_by: str
    ) -> Optional[DocumentVersion]:
        """Mark current version as published"""
        current = self.get_current_version(document_id)
        if not current:
            return None

        current.status = VersionStatus.PUBLISHED
        current.change_type = ChangeType.PUBLISHED
        return current

    def archive_document(
        self,
        document_id: str,
        archived_by: str
    ) -> Optional[DocumentVersion]:
        """Archive a document"""
        current = self.get_current_version(document_id)
        if not current:
            return None

        current.status = VersionStatus.ARCHIVED
        current.change_type = ChangeType.ARCHIVED
        return current

    def delete_version_history(self, document_id: str) -> bool:
        """Delete all versions of a document"""
        if document_id not in self._versions:
            return False

        # Remove from index
        for version in self._versions[document_id]:
            if version.id in self._version_index:
                del self._version_index[version.id]

        # Remove versions and current pointer
        del self._versions[document_id]
        if document_id in self._current_versions:
            del self._current_versions[document_id]

        return True

    def get_version_stats(self, document_id: str) -> Dict[str, Any]:
        """Get statistics about document versions"""
        versions = self._versions.get(document_id, [])

        if not versions:
            return {
                "total_versions": 0,
                "total_size_bytes": 0,
                "contributors": [],
                "change_types": {}
            }

        contributors = set()
        change_types: Dict[str, int] = defaultdict(int)
        total_size = 0

        for v in versions:
            contributors.add(v.created_by)
            change_types[v.change_type.value] += 1
            total_size += v.size_bytes

        return {
            "total_versions": len(versions),
            "total_size_bytes": total_size,
            "contributors": list(contributors),
            "change_types": dict(change_types),
            "first_version_at": versions[0].created_at.isoformat(),
            "last_version_at": versions[-1].created_at.isoformat()
        }

    def _compute_hash(self, content: str) -> str:
        """Compute hash of content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _generate_change_summary(
        self,
        old_content: str,
        new_content: str,
        old_title: str,
        new_title: str
    ) -> str:
        """Auto-generate change summary"""
        parts = []

        if old_title != new_title:
            parts.append(f"Title changed from '{old_title}' to '{new_title}'")

        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        diff = list(difflib.unified_diff(old_lines, new_lines))

        additions = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))

        if additions or deletions:
            parts.append(f"{additions} line(s) added, {deletions} line(s) deleted")

        return "; ".join(parts) if parts else "Minor changes"

    def _prune_versions(self, document_id: str):
        """Remove old versions beyond limit"""
        versions = self._versions.get(document_id, [])
        if len(versions) <= self.MAX_VERSIONS_PER_DOCUMENT:
            return

        # Keep the most recent versions
        to_remove = versions[:-self.MAX_VERSIONS_PER_DOCUMENT]
        self._versions[document_id] = versions[-self.MAX_VERSIONS_PER_DOCUMENT:]

        for old in to_remove:
            if old.id in self._version_index:
                del self._version_index[old.id]


# Singleton instance
_version_service: Optional[VersionService] = None


def get_version_service() -> VersionService:
    """Get version service singleton"""
    global _version_service
    if _version_service is None:
        _version_service = VersionService()
    return _version_service
