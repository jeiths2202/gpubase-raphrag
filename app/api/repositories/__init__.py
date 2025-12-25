"""
Repository Layer
Abstract repository interfaces for data access.
"""
from .base import BaseRepository, Entity, EntityId
from .document_repository import DocumentRepository, DocumentEntity
from .note_repository import NoteRepository, NoteEntity
from .project_repository import ProjectRepository, ProjectEntity
from .user_repository import UserRepository, UserEntity
from .history_repository import HistoryRepository, HistoryEntity

__all__ = [
    "BaseRepository",
    "Entity",
    "EntityId",
    "DocumentRepository",
    "DocumentEntity",
    "NoteRepository",
    "NoteEntity",
    "ProjectRepository",
    "ProjectEntity",
    "UserRepository",
    "UserEntity",
    "HistoryRepository",
    "HistoryEntity",
]
