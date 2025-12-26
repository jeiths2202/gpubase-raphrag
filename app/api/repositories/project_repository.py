"""
Project Repository Interface
Repository for project management operations.
"""
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from .base import BaseRepository, Entity, EntityId


class ProjectStatus(str, Enum):
    """Project status"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class MemberRole(str, Enum):
    """Project member role"""
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


@dataclass
class ProjectMemberEntity:
    """Project member entity"""
    user_id: str
    project_id: str
    role: MemberRole
    joined_at: datetime = field(default_factory=datetime.utcnow)
    invited_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "project_id": self.project_id,
            "role": self.role.value,
            "joined_at": self.joined_at.isoformat(),
            "invited_by": self.invited_by
        }


@dataclass
class ProjectEntity(Entity):
    """Project entity"""
    name: str = ""
    description: str = ""
    owner_id: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE

    # Settings
    is_public: bool = False
    allow_external_resources: bool = True

    # Stats
    document_count: int = 0
    member_count: int = 1

    # Metadata
    tags: List[str] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Members (loaded separately)
    members: List[ProjectMemberEntity] = field(default_factory=list)


class ProjectRepository(BaseRepository[ProjectEntity]):
    """
    Repository interface for project operations.
    """

    # ==================== Project Operations ====================

    @abstractmethod
    async def get_by_owner(
        self,
        owner_id: str,
        include_archived: bool = False
    ) -> List[ProjectEntity]:
        """Get projects owned by a user"""
        pass

    @abstractmethod
    async def get_by_member(
        self,
        user_id: str,
        roles: Optional[List[MemberRole]] = None,
        include_archived: bool = False
    ) -> List[ProjectEntity]:
        """Get projects where user is a member"""
        pass

    @abstractmethod
    async def get_public_projects(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[ProjectEntity]:
        """Get public projects"""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[ProjectEntity]:
        """Search projects by name and description"""
        pass

    @abstractmethod
    async def archive(self, project_id: EntityId) -> bool:
        """Archive a project"""
        pass

    @abstractmethod
    async def restore(self, project_id: EntityId) -> bool:
        """Restore an archived project"""
        pass

    @abstractmethod
    async def update_stats(
        self,
        project_id: EntityId,
        document_delta: int = 0,
        member_delta: int = 0
    ) -> bool:
        """Update project statistics"""
        pass

    # ==================== Member Operations ====================

    @abstractmethod
    async def add_member(
        self,
        project_id: EntityId,
        user_id: str,
        role: MemberRole,
        invited_by: Optional[str] = None
    ) -> ProjectMemberEntity:
        """Add a member to project"""
        pass

    @abstractmethod
    async def remove_member(
        self,
        project_id: EntityId,
        user_id: str
    ) -> bool:
        """Remove a member from project"""
        pass

    @abstractmethod
    async def update_member_role(
        self,
        project_id: EntityId,
        user_id: str,
        new_role: MemberRole
    ) -> bool:
        """Update member role"""
        pass

    @abstractmethod
    async def get_members(
        self,
        project_id: EntityId,
        role: Optional[MemberRole] = None
    ) -> List[ProjectMemberEntity]:
        """Get project members"""
        pass

    @abstractmethod
    async def get_member(
        self,
        project_id: EntityId,
        user_id: str
    ) -> Optional[ProjectMemberEntity]:
        """Get specific member"""
        pass

    @abstractmethod
    async def is_member(
        self,
        project_id: EntityId,
        user_id: str,
        min_role: Optional[MemberRole] = None
    ) -> bool:
        """Check if user is a member with optional minimum role"""
        pass

    # ==================== Permission Helpers ====================

    @abstractmethod
    async def can_edit(self, project_id: EntityId, user_id: str) -> bool:
        """Check if user can edit project"""
        pass

    @abstractmethod
    async def can_manage(self, project_id: EntityId, user_id: str) -> bool:
        """Check if user can manage project (admin/owner)"""
        pass

    # ==================== Statistics ====================

    @abstractmethod
    async def get_stats(self, project_id: EntityId) -> Dict[str, Any]:
        """Get project statistics"""
        pass
