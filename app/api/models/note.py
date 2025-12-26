"""
Note and memo models
노트 및 메모 관련 모델
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class NoteType(str, Enum):
    """Note types"""
    TEXT = "text"
    AI_RESPONSE = "ai_response"
    HIGHLIGHT = "highlight"
    ANNOTATION = "annotation"


class NoteSource(str, Enum):
    """Note source types"""
    MANUAL = "manual"
    AI_CHAT = "ai_chat"
    DOCUMENT = "document"
    MINDMAP = "mindmap"


# Request models
class CreateNoteRequest(BaseModel):
    """Request to create a new note"""
    title: str = Field(..., min_length=1, max_length=200, description="Note title")
    content: str = Field(..., min_length=1, description="Note content (markdown supported)")
    note_type: NoteType = Field(default=NoteType.TEXT, description="Type of note")
    folder_id: Optional[str] = Field(default=None, description="Parent folder ID")
    project_id: Optional[str] = Field(default=None, description="Associated project ID")
    tags: list[str] = Field(default_factory=list, description="Note tags")
    source: NoteSource = Field(default=NoteSource.MANUAL, description="Note source")
    source_reference: Optional[dict] = Field(default=None, description="Source reference info")
    color: Optional[str] = Field(default=None, description="Note color (hex)")


class UpdateNoteRequest(BaseModel):
    """Request to update a note"""
    title: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = None
    folder_id: Optional[str] = None
    tags: Optional[list[str]] = None
    color: Optional[str] = None
    is_pinned: Optional[bool] = None


class CreateFolderRequest(BaseModel):
    """Request to create a note folder"""
    name: str = Field(..., min_length=1, max_length=100, description="Folder name")
    parent_id: Optional[str] = Field(default=None, description="Parent folder ID")
    project_id: Optional[str] = Field(default=None, description="Associated project ID")
    color: Optional[str] = Field(default=None, description="Folder color (hex)")
    icon: Optional[str] = Field(default=None, description="Folder icon")


class UpdateFolderRequest(BaseModel):
    """Request to update a folder"""
    name: Optional[str] = Field(default=None, max_length=100)
    parent_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class SaveAIResponseRequest(BaseModel):
    """Request to save AI response as note"""
    query_id: str = Field(..., description="Query ID from history")
    title: Optional[str] = Field(default=None, description="Note title (auto-generated if not provided)")
    folder_id: Optional[str] = Field(default=None, description="Target folder")
    project_id: Optional[str] = Field(default=None, description="Associated project")
    tags: list[str] = Field(default_factory=list, description="Note tags")


class ExportNotesRequest(BaseModel):
    """Request to export notes"""
    note_ids: list[str] = Field(..., min_length=1, description="Note IDs to export")
    format: str = Field(default="markdown", description="Export format: markdown, pdf, html, json")
    include_metadata: bool = Field(default=True, description="Include note metadata")


class SearchNotesRequest(BaseModel):
    """Request to search notes"""
    query: str = Field(..., min_length=1, description="Search query")
    folder_id: Optional[str] = Field(default=None, description="Limit to folder")
    project_id: Optional[str] = Field(default=None, description="Limit to project")
    tags: Optional[list[str]] = Field(default=None, description="Filter by tags")
    note_type: Optional[NoteType] = Field(default=None, description="Filter by note type")
    date_from: Optional[datetime] = Field(default=None, description="Created after")
    date_to: Optional[datetime] = Field(default=None, description="Created before")


# Response models
class NoteFolder(BaseModel):
    """Note folder"""
    id: str
    name: str
    parent_id: Optional[str] = None
    project_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    note_count: int = 0
    children: list["NoteFolder"] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class NoteListItem(BaseModel):
    """Note list item"""
    id: str
    title: str
    preview: str = Field(description="First 100 chars of content")
    note_type: NoteType
    source: NoteSource
    folder_id: Optional[str] = None
    folder_name: Optional[str] = None
    project_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    color: Optional[str] = None
    is_pinned: bool = False
    created_at: datetime
    updated_at: datetime


class NoteDetail(BaseModel):
    """Detailed note information"""
    id: str
    title: str
    content: str
    note_type: NoteType
    source: NoteSource
    source_reference: Optional[dict] = None
    folder_id: Optional[str] = None
    folder_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    color: Optional[str] = None
    is_pinned: bool = False
    word_count: int = 0
    created_at: datetime
    updated_at: datetime
    created_by: str


class NoteExportResult(BaseModel):
    """Note export result"""
    format: str
    filename: str
    content: str
    note_count: int
    export_date: datetime


class NoteSearchResult(BaseModel):
    """Note search result"""
    id: str
    title: str
    preview: str
    highlights: list[str] = Field(default_factory=list, description="Matched text highlights")
    relevance_score: float
    note_type: NoteType
    folder_name: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


class NoteStats(BaseModel):
    """Note statistics"""
    total_notes: int
    by_type: dict[str, int] = Field(default_factory=dict)
    by_source: dict[str, int] = Field(default_factory=dict)
    total_folders: int
    total_tags: int
    most_used_tags: list[dict] = Field(default_factory=list)
    recent_activity: list[dict] = Field(default_factory=list)
