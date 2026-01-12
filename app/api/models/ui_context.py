"""
UI Context Models

Defines Pydantic models for UI context that is shared between
frontend and backend for context-aware AI responses.

These models are used to:
- Validate UI context received from frontend
- Filter context based on user role
- Provide type safety for context processing
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PageType(str, Enum):
    """Page types in the application"""
    HOME = "home"
    KNOWLEDGE = "knowledge"
    FAQ = "faq"
    IMS = "ims"
    AGENT = "agent"
    DOCUMENTS = "documents"
    SETTINGS = "settings"
    ADMIN = "admin"
    AI_STUDIO = "ai-studio"
    EXTERNAL_PORTAL = "external-portal"
    UNKNOWN = "unknown"


class SelectedItemType(str, Enum):
    """Types of items that can be selected"""
    FAQ_ITEM = "faq_item"
    DOCUMENT = "document"
    IMS_ISSUE = "ims_issue"
    KNOWLEDGE_ARTICLE = "knowledge_article"
    AGENT_CONVERSATION = "agent_conversation"
    SEARCH_RESULT = "search_result"
    NONE = "none"


class SelectedItem(BaseModel):
    """Selected item with content"""
    type: SelectedItemType = Field(..., description="Type of the selected item")
    id: str = Field(..., description="Unique identifier")
    title: str = Field(..., description="Display title")
    content: Optional[str] = Field(None, description="Full content (may be filtered by role)")
    summary: Optional[str] = Field(None, description="Brief summary (always visible)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class PageMetadata(BaseModel):
    """Page-specific metadata"""
    faq_category: Optional[str] = Field(None, description="FAQ category if on FAQ page")
    search_query: Optional[str] = Field(None, description="Search query if searching")
    active_filters: Optional[Dict[str, Any]] = Field(None, description="Active filters")
    ims_job_id: Optional[str] = Field(None, description="IMS job ID if crawling")
    document_path: Optional[str] = Field(None, description="Document folder path")

    class Config:
        extra = "allow"  # Allow additional fields


class UIContext(BaseModel):
    """
    Complete UI Context sent from frontend to AI.

    This context allows the AI assistant to understand:
    - What page the user is currently viewing
    - What item/content is selected or expanded
    - User's language and theme preferences
    - User's permission scope for role-based filtering
    """
    current_page: PageType = Field(..., description="Current page identifier")
    page_title: str = Field(..., description="Human-readable page title")
    page_metadata: Optional[PageMetadata] = Field(None, description="Page-specific metadata")
    selected_item: Optional[SelectedItem] = Field(None, description="Currently selected/expanded item")
    visible_components: List[str] = Field(default_factory=list, description="List of visible UI components")
    language: str = Field("ko", description="User's preferred language")
    theme: str = Field("dark", description="Current theme")
    user_permission_scope: str = Field("user", description="User's permission scope")
    captured_at: Optional[str] = Field(None, description="Timestamp when context was captured")

    class Config:
        use_enum_values = True


class FilteredUIContext(BaseModel):
    """
    Filtered context for non-admin users.
    Content fields are redacted to protect sensitive information.
    """
    current_page: PageType
    page_title: str
    selected_item_summary: Optional[Dict[str, Any]] = Field(
        None,
        description="Summary of selected item (content redacted for non-admin)"
    )
    visible_components: List[str] = Field(default_factory=list)
    language: str = "ko"
    theme: str = "dark"
    user_permission_scope: str = "user"

    class Config:
        use_enum_values = True


# Page titles for reference
PAGE_TITLES = {
    PageType.HOME: "Home",
    PageType.KNOWLEDGE: "Knowledge Base",
    PageType.FAQ: "FAQ",
    PageType.IMS: "IMS Search",
    PageType.AGENT: "AI Agent",
    PageType.DOCUMENTS: "Documents",
    PageType.SETTINGS: "Settings",
    PageType.ADMIN: "Admin Dashboard",
    PageType.AI_STUDIO: "AI Studio",
    PageType.EXTERNAL_PORTAL: "External Portal",
    PageType.UNKNOWN: "Unknown",
}

# Detailed page descriptions for context-aware AI
PAGE_DESCRIPTIONS = {
    PageType.HOME: """The Home Dashboard page displays:
- System overview and quick stats (document count, query count, user activity)
- Recent activity feed showing latest queries and document uploads
- Quick action buttons for common tasks
- System health indicators""",

    PageType.KNOWLEDGE: """The Knowledge Base page allows users to:
- Browse and search the knowledge article library
- View article details, categories, and tags
- Filter articles by category, date, or author
- Access linked documents and related content""",

    PageType.FAQ: """The FAQ (Frequently Asked Questions) page shows:
- List of common questions organized by category
- Search functionality to find specific answers
- Ability to view full answer content
- Related questions and helpful resources""",

    PageType.IMS: """The IMS (Issue Management System) Search page provides:
- Search interface for bug reports and issues
- Filter by status, priority, assignee, and date
- View issue details including description, steps to reproduce
- Link issues to knowledge articles""",

    PageType.AGENT: """The AI Agent page is a full-featured chat interface with:
- Multiple agent types (RAG, IMS, Vision, Code, Planner)
- Streaming responses with tool call visualization
- Conversation history management
- Source document display and artifact panel""",

    PageType.DOCUMENTS: """The Documents management page allows:
- Upload and manage documents for the RAG system
- View document metadata, chunk counts, and indexing status
- Organize documents by folder or category
- Monitor document processing pipeline""",

    PageType.SETTINGS: """The Settings page provides configuration for:
- User profile and preferences
- Language and theme settings
- Notification preferences
- API key management
- External resource connections""",

    PageType.ADMIN: """The Admin Dashboard shows system administration features:
- User management (create, edit, delete users)
- System analytics and usage metrics
- RAG configuration and governance settings
- Audit logs and security monitoring
- Performance metrics and health status""",

    PageType.AI_STUDIO: """The AI Studio page provides advanced AI features:
- Vision LLM for image and chart analysis
- Sequential pipeline for multi-step document processing
- Code generation and analysis tools
- Custom prompt templates""",

    PageType.EXTERNAL_PORTAL: """The External Portal page manages:
- Connected external resources (Notion, GitHub, Google Drive, Confluence)
- OAuth connection management
- Sync status and content indexing
- Resource-specific search and retrieval""",

    PageType.UNKNOWN: "Unknown page - no specific context available.",
}


# Maximum content length to include in context
MAX_CONTENT_LENGTH = 2000


def filter_ui_context_by_role(
    context: UIContext,
    user_role: str
) -> FilteredUIContext:
    """
    Filter UI context based on user role.

    Admin users: See full context including content
    Regular users: See redacted content (summary only)

    Args:
        context: Full UI context from frontend
        user_role: User's role ('admin' or 'user')

    Returns:
        FilteredUIContext with appropriate content filtering
    """
    # Build selected item summary
    selected_item_summary = None
    if context.selected_item:
        selected_item_summary = {
            "type": context.selected_item.type,
            "id": context.selected_item.id,
            "title": context.selected_item.title,
        }

        # Admin sees full content, user sees truncated summary
        if user_role == "admin" and context.selected_item.content:
            selected_item_summary["content"] = context.selected_item.content[:MAX_CONTENT_LENGTH]
        elif context.selected_item.content:
            # Non-admin gets truncated preview
            content = context.selected_item.content
            selected_item_summary["content_preview"] = (
                content[:200] + "..." if len(content) > 200 else content
            )

        # Summary is always included
        if context.selected_item.summary:
            selected_item_summary["summary"] = context.selected_item.summary

        # Metadata included for all users
        if context.selected_item.metadata:
            selected_item_summary["metadata"] = context.selected_item.metadata

    return FilteredUIContext(
        current_page=context.current_page,
        page_title=context.page_title,
        selected_item_summary=selected_item_summary,
        visible_components=context.visible_components,
        language=context.language,
        theme=context.theme,
        user_permission_scope=user_role,
    )


def build_context_prompt_section(filtered_context: FilteredUIContext) -> str:
    """
    Build a context section to inject into the LLM prompt.

    This creates a human-readable description of the UI context
    that the AI can use to provide relevant responses.

    Args:
        filtered_context: Role-filtered UI context

    Returns:
        Formatted context string for prompt injection
    """
    parts = []

    # Page context with detailed description
    page_type = filtered_context.current_page
    parts.append(f"=== USER'S CURRENT SCREEN ===")
    parts.append(f"Page: {filtered_context.page_title}")

    # Add detailed page description
    if page_type in PAGE_DESCRIPTIONS:
        parts.append(f"\nPage Description:\n{PAGE_DESCRIPTIONS[page_type]}")

    # Selected item context
    if filtered_context.selected_item_summary:
        item = filtered_context.selected_item_summary
        item_type = item.get("type", "item")
        item_title = item.get("title", "Unknown")
        parts.append(f"\n=== SELECTED ITEM ===")
        parts.append(f"Type: {item_type}")
        parts.append(f"Title: \"{item_title}\"")

        # Include content preview if available
        if "content" in item:
            content = item["content"]
            if len(content) > 500:
                content = content[:500] + "..."
            parts.append(f"Content:\n{content}")
        elif "content_preview" in item:
            parts.append(f"Preview: {item['content_preview']}")

    # User preferences
    lang_names = {"ko": "Korean", "en": "English", "ja": "Japanese"}
    lang = lang_names.get(filtered_context.language, filtered_context.language)
    parts.append(f"\n=== USER PREFERENCES ===")
    parts.append(f"Response Language: {lang}")
    parts.append(f"User Role: {filtered_context.user_permission_scope}")

    return "\n".join(parts)
