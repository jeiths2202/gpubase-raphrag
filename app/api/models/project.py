"""
Project/Notebook models
프로젝트/노트북 관련 모델
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ProjectVisibility(str, Enum):
    """Project visibility levels"""
    PRIVATE = "private"
    SHARED = "shared"
    PUBLIC = "public"


class ProjectRole(str, Enum):
    """Project member roles"""
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class TemplateCategory(str, Enum):
    """Project template categories"""
    RESEARCH = "research"
    STUDY = "study"
    BUSINESS = "business"
    PERSONAL = "personal"
    CUSTOM = "custom"


# Request models
class CreateProjectRequest(BaseModel):
    """Request to create a new project"""
    name: str = Field(..., min_length=1, max_length=200, description="Project name")
    description: Optional[str] = Field(default=None, max_length=1000, description="Project description")
    visibility: ProjectVisibility = Field(default=ProjectVisibility.PRIVATE, description="Visibility")
    color: Optional[str] = Field(default=None, description="Project color (hex)")
    icon: Optional[str] = Field(default=None, description="Project icon")
    tags: list[str] = Field(default_factory=list, description="Project tags")
    template_id: Optional[str] = Field(default=None, description="Template to use")


class UpdateProjectRequest(BaseModel):
    """Request to update a project"""
    name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    visibility: Optional[ProjectVisibility] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    tags: Optional[list[str]] = None


class ShareProjectRequest(BaseModel):
    """Request to share a project"""
    user_ids: list[str] = Field(..., min_length=1, description="User IDs to share with")
    role: ProjectRole = Field(default=ProjectRole.VIEWER, description="Role for shared users")
    message: Optional[str] = Field(default=None, description="Invitation message")


class UpdateMemberRoleRequest(BaseModel):
    """Request to update member role"""
    user_id: str = Field(..., description="User ID")
    role: ProjectRole = Field(..., description="New role")


class CloneProjectRequest(BaseModel):
    """Request to clone a project"""
    new_name: str = Field(..., min_length=1, max_length=200, description="New project name")
    include_documents: bool = Field(default=True, description="Clone documents")
    include_notes: bool = Field(default=True, description="Clone notes")
    include_mindmaps: bool = Field(default=True, description="Clone mindmaps")
    include_conversations: bool = Field(default=False, description="Clone conversations")


class CreateTemplateRequest(BaseModel):
    """Request to create a template from project"""
    name: str = Field(..., min_length=1, max_length=200, description="Template name")
    description: Optional[str] = Field(default=None, max_length=1000)
    category: TemplateCategory = Field(default=TemplateCategory.CUSTOM)
    include_structure: bool = Field(default=True, description="Include folder structure")
    include_sample_notes: bool = Field(default=False, description="Include sample notes")
    is_public: bool = Field(default=False, description="Make template public")


class AddDocumentToProjectRequest(BaseModel):
    """Request to add document to project"""
    document_id: str = Field(..., description="Document ID to add")


class RemoveDocumentFromProjectRequest(BaseModel):
    """Request to remove document from project"""
    document_id: str = Field(..., description="Document ID to remove")


# Response models
class ProjectMember(BaseModel):
    """Project member"""
    user_id: str
    username: str
    email: Optional[str] = None
    role: ProjectRole
    joined_at: datetime


class ProjectStats(BaseModel):
    """Project statistics"""
    document_count: int = 0
    note_count: int = 0
    mindmap_count: int = 0
    conversation_count: int = 0
    member_count: int = 1
    total_queries: int = 0
    last_activity: Optional[datetime] = None


class ProjectListItem(BaseModel):
    """Project list item"""
    id: str
    name: str
    description: Optional[str] = None
    visibility: ProjectVisibility
    color: Optional[str] = None
    icon: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    owner_id: str
    owner_name: str
    document_count: int = 0
    note_count: int = 0
    is_owner: bool = False
    my_role: ProjectRole = ProjectRole.VIEWER
    created_at: datetime
    updated_at: datetime


class ProjectDetail(BaseModel):
    """Detailed project information"""
    id: str
    name: str
    description: Optional[str] = None
    visibility: ProjectVisibility
    color: Optional[str] = None
    icon: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    owner_id: str
    owner_name: str
    members: list[ProjectMember] = Field(default_factory=list)
    stats: ProjectStats
    is_owner: bool = False
    my_role: ProjectRole = ProjectRole.VIEWER
    created_at: datetime
    updated_at: datetime


class ProjectDocumentItem(BaseModel):
    """Document in project"""
    id: str
    filename: str
    original_name: str
    file_size: int
    status: str
    chunks_count: int = 0
    added_at: datetime


class ProjectTemplate(BaseModel):
    """Project template"""
    id: str
    name: str
    description: Optional[str] = None
    category: TemplateCategory
    color: Optional[str] = None
    icon: Optional[str] = None
    folder_structure: list[dict] = Field(default_factory=list)
    sample_note_count: int = 0
    is_public: bool = False
    usage_count: int = 0
    created_by: str
    created_at: datetime


class CloneProjectResponse(BaseModel):
    """Clone project response"""
    project_id: str
    name: str
    documents_cloned: int = 0
    notes_cloned: int = 0
    mindmaps_cloned: int = 0
    message: str


class ShareProjectResponse(BaseModel):
    """Share project response"""
    shared_with: list[str]
    role: ProjectRole
    message: str


class ProjectActivityItem(BaseModel):
    """Project activity item"""
    id: str
    action: str  # created, updated, shared, document_added, note_created, etc.
    actor_id: str
    actor_name: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    details: Optional[dict] = None
    timestamp: datetime
