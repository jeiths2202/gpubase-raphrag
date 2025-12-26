"""
In-Memory Project Repository Implementation
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from .base import MemoryBaseRepository
from ...repositories.project_repository import (
    ProjectRepository,
    ProjectEntity,
    ProjectStatus,
    ProjectMemberEntity,
    MemberRole
)
from ...repositories.base import EntityId


class MemoryProjectRepository(MemoryBaseRepository[ProjectEntity], ProjectRepository):
    """In-memory project repository implementation"""

    def __init__(self):
        super().__init__()
        self._members: Dict[str, List[ProjectMemberEntity]] = {}  # project_id -> members

    # ==================== Project Operations ====================

    async def get_by_owner(
        self,
        owner_id: str,
        include_archived: bool = False
    ) -> List[ProjectEntity]:
        projects = [p for p in self._storage.values() if p.owner_id == owner_id]
        if not include_archived:
            projects = [p for p in projects if p.status != ProjectStatus.ARCHIVED]
        projects.sort(key=lambda x: x.updated_at, reverse=True)
        return projects

    async def get_by_member(
        self,
        user_id: str,
        roles: Optional[List[MemberRole]] = None,
        include_archived: bool = False
    ) -> List[ProjectEntity]:
        project_ids = set()

        for project_id, members in self._members.items():
            for member in members:
                if member.user_id == user_id:
                    if roles is None or member.role in roles:
                        project_ids.add(project_id)

        projects = [p for p in self._storage.values() if str(p.id) in project_ids]
        if not include_archived:
            projects = [p for p in projects if p.status != ProjectStatus.ARCHIVED]
        projects.sort(key=lambda x: x.updated_at, reverse=True)
        return projects

    async def get_public_projects(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[ProjectEntity]:
        projects = [p for p in self._storage.values()
                    if p.is_public and p.status == ProjectStatus.ACTIVE]
        projects.sort(key=lambda x: x.updated_at, reverse=True)
        return projects[skip:skip + limit]

    async def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[ProjectEntity]:
        query_lower = query.lower()
        results = []

        for project in self._storage.values():
            # Check access
            if not project.is_public and user_id:
                if project.owner_id != user_id and not await self.is_member(project.id, user_id):
                    continue

            if query_lower in project.name.lower() or query_lower in project.description.lower():
                results.append(project)

        results.sort(key=lambda x: x.updated_at, reverse=True)
        return results[:limit]

    async def archive(self, project_id: EntityId) -> bool:
        project = await self.get_by_id(project_id)
        if not project:
            return False
        project.status = ProjectStatus.ARCHIVED
        project.updated_at = datetime.utcnow()
        return True

    async def restore(self, project_id: EntityId) -> bool:
        project = await self.get_by_id(project_id)
        if not project:
            return False
        project.status = ProjectStatus.ACTIVE
        project.updated_at = datetime.utcnow()
        return True

    async def update_stats(
        self,
        project_id: EntityId,
        document_delta: int = 0,
        member_delta: int = 0
    ) -> bool:
        project = await self.get_by_id(project_id)
        if not project:
            return False

        project.document_count += document_delta
        project.member_count += member_delta
        project.updated_at = datetime.utcnow()
        return True

    # ==================== Member Operations ====================

    async def add_member(
        self,
        project_id: EntityId,
        user_id: str,
        role: MemberRole,
        invited_by: Optional[str] = None
    ) -> ProjectMemberEntity:
        pid = self._normalize_id(project_id)

        if pid not in self._members:
            self._members[pid] = []

        member = ProjectMemberEntity(
            user_id=user_id,
            project_id=pid,
            role=role,
            invited_by=invited_by,
            joined_at=datetime.utcnow()
        )

        self._members[pid].append(member)
        await self.update_stats(project_id, member_delta=1)
        return member

    async def remove_member(
        self,
        project_id: EntityId,
        user_id: str
    ) -> bool:
        pid = self._normalize_id(project_id)
        members = self._members.get(pid, [])

        for i, member in enumerate(members):
            if member.user_id == user_id:
                members.pop(i)
                await self.update_stats(project_id, member_delta=-1)
                return True

        return False

    async def update_member_role(
        self,
        project_id: EntityId,
        user_id: str,
        new_role: MemberRole
    ) -> bool:
        pid = self._normalize_id(project_id)
        members = self._members.get(pid, [])

        for member in members:
            if member.user_id == user_id:
                member.role = new_role
                return True

        return False

    async def get_members(
        self,
        project_id: EntityId,
        role: Optional[MemberRole] = None
    ) -> List[ProjectMemberEntity]:
        pid = self._normalize_id(project_id)
        members = self._members.get(pid, [])

        if role:
            members = [m for m in members if m.role == role]

        return members

    async def get_member(
        self,
        project_id: EntityId,
        user_id: str
    ) -> Optional[ProjectMemberEntity]:
        pid = self._normalize_id(project_id)
        members = self._members.get(pid, [])

        for member in members:
            if member.user_id == user_id:
                return member

        return None

    async def is_member(
        self,
        project_id: EntityId,
        user_id: str,
        min_role: Optional[MemberRole] = None
    ) -> bool:
        member = await self.get_member(project_id, user_id)
        if not member:
            return False

        if min_role:
            role_order = [MemberRole.VIEWER, MemberRole.EDITOR, MemberRole.ADMIN, MemberRole.OWNER]
            return role_order.index(member.role) >= role_order.index(min_role)

        return True

    # ==================== Permission Helpers ====================

    async def can_edit(self, project_id: EntityId, user_id: str) -> bool:
        project = await self.get_by_id(project_id)
        if not project:
            return False

        if project.owner_id == user_id:
            return True

        return await self.is_member(project_id, user_id, MemberRole.EDITOR)

    async def can_manage(self, project_id: EntityId, user_id: str) -> bool:
        project = await self.get_by_id(project_id)
        if not project:
            return False

        if project.owner_id == user_id:
            return True

        return await self.is_member(project_id, user_id, MemberRole.ADMIN)

    # ==================== Statistics ====================

    async def get_stats(self, project_id: EntityId) -> Dict[str, Any]:
        project = await self.get_by_id(project_id)
        if not project:
            return {}

        members = await self.get_members(project_id)
        role_counts = {}
        for member in members:
            role = member.role.value
            role_counts[role] = role_counts.get(role, 0) + 1

        return {
            "document_count": project.document_count,
            "member_count": len(members),
            "role_breakdown": role_counts,
            "is_public": project.is_public,
            "status": project.status.value
        }

    async def create(self, entity: ProjectEntity) -> ProjectEntity:
        """Override to add owner as member"""
        result = await super().create(entity)

        # Add owner as member
        await self.add_member(result.id, entity.owner_id, MemberRole.OWNER)

        return result
