"""
Note Repository Interface
Repository for note management operations.
"""
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

from .base import BaseRepository, Entity, EntityId


@dataclass
class NoteEntity(Entity):
    """Note entity"""
    title: str = ""
    content: str = ""
    user_id: str = ""

    # Organization
    folder_id: Optional[str] = None
    project_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Properties
    is_pinned: bool = False
    is_archived: bool = False
    color: Optional[str] = None

    # Linked items
    linked_documents: List[str] = field(default_factory=list)
    linked_notes: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FolderEntity(Entity):
    """Folder entity for organizing notes"""
    name: str = ""
    user_id: str = ""
    parent_id: Optional[str] = None
    color: Optional[str] = None
    note_count: int = 0


class NoteRepository(BaseRepository[NoteEntity]):
    """
    Repository interface for note operations.
    """

    # ==================== Note Operations ====================

    @abstractmethod
    async def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        include_archived: bool = False
    ) -> List[NoteEntity]:
        """Get all notes for a user"""
        pass

    @abstractmethod
    async def get_by_folder(
        self,
        folder_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[NoteEntity]:
        """Get notes in a folder"""
        pass

    @abstractmethod
    async def get_by_project(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[NoteEntity]:
        """Get notes linked to a project"""
        pass

    @abstractmethod
    async def get_pinned(self, user_id: str) -> List[NoteEntity]:
        """Get pinned notes for a user"""
        pass

    @abstractmethod
    async def get_archived(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[NoteEntity]:
        """Get archived notes"""
        pass

    @abstractmethod
    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[NoteEntity]:
        """Search notes by title and content"""
        pass

    @abstractmethod
    async def search_by_tags(
        self,
        user_id: str,
        tags: List[str],
        match_all: bool = False
    ) -> List[NoteEntity]:
        """Search notes by tags"""
        pass

    @abstractmethod
    async def toggle_pin(self, note_id: EntityId) -> bool:
        """Toggle note pinned status"""
        pass

    @abstractmethod
    async def toggle_archive(self, note_id: EntityId) -> bool:
        """Toggle note archived status"""
        pass

    @abstractmethod
    async def move_to_folder(
        self,
        note_id: EntityId,
        folder_id: Optional[str]
    ) -> bool:
        """Move note to a folder (None for root)"""
        pass

    @abstractmethod
    async def add_link(
        self,
        note_id: EntityId,
        linked_id: str,
        link_type: str  # "document" or "note"
    ) -> bool:
        """Add a link to document or note"""
        pass

    @abstractmethod
    async def remove_link(
        self,
        note_id: EntityId,
        linked_id: str,
        link_type: str
    ) -> bool:
        """Remove a link"""
        pass

    # ==================== Folder Operations ====================

    @abstractmethod
    async def create_folder(self, folder: FolderEntity) -> FolderEntity:
        """Create a new folder"""
        pass

    @abstractmethod
    async def get_folder(self, folder_id: str) -> Optional[FolderEntity]:
        """Get folder by ID"""
        pass

    @abstractmethod
    async def get_folders(
        self,
        user_id: str,
        parent_id: Optional[str] = None
    ) -> List[FolderEntity]:
        """Get folders for a user, optionally under a parent"""
        pass

    @abstractmethod
    async def update_folder(
        self,
        folder_id: str,
        data: Dict[str, Any]
    ) -> Optional[FolderEntity]:
        """Update folder"""
        pass

    @abstractmethod
    async def delete_folder(
        self,
        folder_id: str,
        move_notes_to: Optional[str] = None
    ) -> bool:
        """Delete folder, optionally moving notes to another folder"""
        pass

    # ==================== Statistics ====================

    @abstractmethod
    async def get_stats(self, user_id: str) -> Dict[str, Any]:
        """Get note statistics for a user"""
        pass
