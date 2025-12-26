"""
In-Memory Note Repository Implementation
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from .base import MemoryBaseRepository
from ...repositories.note_repository import (
    NoteRepository,
    NoteEntity,
    FolderEntity
)
from ...repositories.base import EntityId


class MemoryNoteRepository(MemoryBaseRepository[NoteEntity], NoteRepository):
    """In-memory note repository implementation"""

    def __init__(self):
        super().__init__()
        self._folders: Dict[str, FolderEntity] = {}

    # ==================== Note Operations ====================

    async def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        include_archived: bool = False
    ) -> List[NoteEntity]:
        notes = [n for n in self._storage.values() if n.user_id == user_id]
        if not include_archived:
            notes = [n for n in notes if not n.is_archived]
        notes.sort(key=lambda x: (not x.is_pinned, x.updated_at), reverse=True)
        return notes[skip:skip + limit]

    async def get_by_folder(
        self,
        folder_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[NoteEntity]:
        notes = [n for n in self._storage.values() if n.folder_id == folder_id]
        notes.sort(key=lambda x: x.updated_at, reverse=True)
        return notes[skip:skip + limit]

    async def get_by_project(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[NoteEntity]:
        notes = [n for n in self._storage.values() if n.project_id == project_id]
        notes.sort(key=lambda x: x.updated_at, reverse=True)
        return notes[skip:skip + limit]

    async def get_pinned(self, user_id: str) -> List[NoteEntity]:
        notes = [n for n in self._storage.values()
                 if n.user_id == user_id and n.is_pinned and not n.is_archived]
        notes.sort(key=lambda x: x.updated_at, reverse=True)
        return notes

    async def get_archived(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[NoteEntity]:
        notes = [n for n in self._storage.values()
                 if n.user_id == user_id and n.is_archived]
        notes.sort(key=lambda x: x.updated_at, reverse=True)
        return notes[skip:skip + limit]

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[NoteEntity]:
        query_lower = query.lower()
        results = []

        for note in self._storage.values():
            if note.user_id != user_id:
                continue
            if query_lower in note.title.lower() or query_lower in note.content.lower():
                results.append(note)

        results.sort(key=lambda x: x.updated_at, reverse=True)
        return results[:limit]

    async def search_by_tags(
        self,
        user_id: str,
        tags: List[str],
        match_all: bool = False
    ) -> List[NoteEntity]:
        results = []

        for note in self._storage.values():
            if note.user_id != user_id:
                continue

            if match_all:
                if all(tag in note.tags for tag in tags):
                    results.append(note)
            else:
                if any(tag in note.tags for tag in tags):
                    results.append(note)

        return results

    async def toggle_pin(self, note_id: EntityId) -> bool:
        note = await self.get_by_id(note_id)
        if not note:
            return False
        note.is_pinned = not note.is_pinned
        note.updated_at = datetime.utcnow()
        return True

    async def toggle_archive(self, note_id: EntityId) -> bool:
        note = await self.get_by_id(note_id)
        if not note:
            return False
        note.is_archived = not note.is_archived
        note.updated_at = datetime.utcnow()
        return True

    async def move_to_folder(
        self,
        note_id: EntityId,
        folder_id: Optional[str]
    ) -> bool:
        note = await self.get_by_id(note_id)
        if not note:
            return False

        old_folder_id = note.folder_id
        note.folder_id = folder_id
        note.updated_at = datetime.utcnow()

        # Update folder counts
        if old_folder_id and old_folder_id in self._folders:
            self._folders[old_folder_id].note_count -= 1
        if folder_id and folder_id in self._folders:
            self._folders[folder_id].note_count += 1

        return True

    async def add_link(
        self,
        note_id: EntityId,
        linked_id: str,
        link_type: str
    ) -> bool:
        note = await self.get_by_id(note_id)
        if not note:
            return False

        if link_type == "document":
            if linked_id not in note.linked_documents:
                note.linked_documents.append(linked_id)
        elif link_type == "note":
            if linked_id not in note.linked_notes:
                note.linked_notes.append(linked_id)

        note.updated_at = datetime.utcnow()
        return True

    async def remove_link(
        self,
        note_id: EntityId,
        linked_id: str,
        link_type: str
    ) -> bool:
        note = await self.get_by_id(note_id)
        if not note:
            return False

        if link_type == "document":
            if linked_id in note.linked_documents:
                note.linked_documents.remove(linked_id)
        elif link_type == "note":
            if linked_id in note.linked_notes:
                note.linked_notes.remove(linked_id)

        note.updated_at = datetime.utcnow()
        return True

    # ==================== Folder Operations ====================

    async def create_folder(self, folder: FolderEntity) -> FolderEntity:
        if not folder.id:
            self._id_counter += 1
            folder.id = f"folder_{self._id_counter:08d}"

        folder.created_at = datetime.utcnow()
        folder.updated_at = datetime.utcnow()
        self._folders[str(folder.id)] = folder
        return folder

    async def get_folder(self, folder_id: str) -> Optional[FolderEntity]:
        return self._folders.get(folder_id)

    async def get_folders(
        self,
        user_id: str,
        parent_id: Optional[str] = None
    ) -> List[FolderEntity]:
        folders = [f for f in self._folders.values()
                   if f.user_id == user_id and f.parent_id == parent_id]
        folders.sort(key=lambda x: x.name)
        return folders

    async def update_folder(
        self,
        folder_id: str,
        data: Dict[str, Any]
    ) -> Optional[FolderEntity]:
        folder = self._folders.get(folder_id)
        if not folder:
            return None

        for key, value in data.items():
            if hasattr(folder, key):
                setattr(folder, key, value)

        folder.updated_at = datetime.utcnow()
        return folder

    async def delete_folder(
        self,
        folder_id: str,
        move_notes_to: Optional[str] = None
    ) -> bool:
        if folder_id not in self._folders:
            return False

        # Move notes to new folder or root
        for note in self._storage.values():
            if note.folder_id == folder_id:
                note.folder_id = move_notes_to
                if move_notes_to and move_notes_to in self._folders:
                    self._folders[move_notes_to].note_count += 1

        del self._folders[folder_id]
        return True

    # ==================== Statistics ====================

    async def get_stats(self, user_id: str) -> Dict[str, Any]:
        notes = [n for n in self._storage.values() if n.user_id == user_id]

        return {
            "total_notes": len(notes),
            "active_notes": len([n for n in notes if not n.is_archived]),
            "archived_notes": len([n for n in notes if n.is_archived]),
            "pinned_notes": len([n for n in notes if n.is_pinned]),
            "total_folders": len([f for f in self._folders.values() if f.user_id == user_id]),
            "notes_with_links": len([n for n in notes if n.linked_documents or n.linked_notes])
        }
