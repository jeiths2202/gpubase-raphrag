"""
Query Clarification Models

Pydantic models for the query clarification system that handles
ambiguous terms in user queries before database search.

Phase 2 extensions:
- MLRecommendation: ML-based entity recommendation with confidence score
- TermCandidate: Auto-extracted term candidate from documents
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# =============================================================================
# Entity Models
# =============================================================================

class PossibleEntity(BaseModel):
    """A possible meaning/interpretation of an ambiguous term."""
    id: str = Field(..., description="Unique identifier for this entity")
    name: str = Field(..., description="Display name of the entity")
    description: str = Field(..., description="Description of what this entity means")
    keywords: List[str] = Field(default_factory=list, description="Related keywords for context")


class MLRecommendation(BaseModel):
    """ML-based entity recommendation from embedding similarity."""
    entity_id: str = Field(..., description="Recommended entity ID")
    entity_name: str = Field(..., description="Recommended entity name")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0) based on query-entity similarity"
    )


class AmbiguousTerm(BaseModel):
    """An ambiguous term that requires clarification."""
    id: int = Field(..., description="Database ID")
    term: str = Field(..., description="Original term text")
    term_normalized: str = Field(..., description="Normalized form for matching")
    category: Optional[str] = Field(None, description="Category for grouping")
    possible_entities: List[PossibleEntity] = Field(..., description="List of possible meanings")
    match_patterns: List[str] = Field(default_factory=list, description="Additional match patterns")
    priority: int = Field(default=0, description="Priority for conflict resolution")
    is_active: bool = Field(default=True, description="Whether this term is active")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserTermPreference(BaseModel):
    """User's saved preference for an ambiguous term."""
    id: int = Field(..., description="Database ID")
    user_id: str = Field(..., description="User UUID")
    term_normalized: str = Field(..., description="Normalized term")
    selected_entity_id: str = Field(..., description="Selected entity ID")
    selected_entity_name: str = Field(..., description="Selected entity name")
    is_permanent: bool = Field(default=True, description="Remember this choice")
    usage_count: int = Field(default=1, description="Times this preference was used")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# Request Models
# =============================================================================

class ClarificationCheckRequest(BaseModel):
    """Request to check if a query needs clarification."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User query to check for ambiguous terms",
        json_schema_extra={"example": "MFS 에러 해결방법"}
    )


class TermSelection(BaseModel):
    """User's selection for a single ambiguous term."""
    term: str = Field(..., description="The ambiguous term")
    selected_entity_id: str = Field(..., description="Selected entity ID")
    selected_entity_name: str = Field(..., description="Selected entity name for display")
    remember: bool = Field(default=False, description="Save this preference for future queries")


class ClarificationApplyRequest(BaseModel):
    """Request to apply user's clarification selections."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Original user query",
        json_schema_extra={"example": "MFS 에러 해결방법"}
    )
    selections: List[TermSelection] = Field(
        ...,
        min_length=1,
        description="User's selections for ambiguous terms"
    )


# =============================================================================
# Response Models
# =============================================================================

class DetectedAmbiguousTerm(BaseModel):
    """An ambiguous term detected in the user's query."""
    term: str = Field(..., description="The detected ambiguous term")
    term_normalized: str = Field(..., description="Normalized form")
    position_start: int = Field(..., description="Start position in query")
    position_end: int = Field(..., description="End position in query")
    possible_entities: List[PossibleEntity] = Field(..., description="Possible meanings")
    category: Optional[str] = Field(None, description="Term category")
    user_preference: Optional[str] = Field(
        None,
        description="User's saved preference entity ID (if exists)"
    )
    ml_recommendation: Optional[MLRecommendation] = Field(
        None,
        description="ML-based entity recommendation (Phase 2)"
    )


class ClarificationCheckResponse(BaseModel):
    """Response from clarification check."""
    needs_clarification: bool = Field(
        ...,
        description="Whether the query contains ambiguous terms needing clarification"
    )
    detected_terms: List[DetectedAmbiguousTerm] = Field(
        default_factory=list,
        description="List of detected ambiguous terms"
    )
    resolved_query: Optional[str] = Field(
        None,
        description="Query with auto-resolved terms (if all have user preferences)"
    )
    auto_resolved_count: int = Field(
        default=0,
        description="Number of terms auto-resolved using user preferences"
    )
    message: Optional[str] = Field(
        None,
        description="Optional message to display to user"
    )


class ClarificationApplyResponse(BaseModel):
    """Response from applying clarification selections."""
    success: bool = Field(..., description="Whether the operation succeeded")
    resolved_query: str = Field(..., description="Query with clarified terms")
    applied_selections: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of applied term -> entity mappings"
    )
    preferences_saved: int = Field(
        default=0,
        description="Number of preferences saved (where remember=True)"
    )
    message: Optional[str] = Field(None, description="Optional status message")


# =============================================================================
# Admin Models (for term management)
# =============================================================================

class AmbiguousTermCreate(BaseModel):
    """Request to create a new ambiguous term."""
    term: str = Field(..., min_length=1, max_length=100, description="Term text")
    category: Optional[str] = Field(None, max_length=50, description="Category")
    possible_entities: List[PossibleEntity] = Field(
        ...,
        min_length=2,
        description="At least 2 possible entities required"
    )
    match_patterns: List[str] = Field(default_factory=list, description="Match patterns")
    priority: int = Field(default=0, ge=0, le=1000, description="Priority (0-1000)")
    is_active: bool = Field(default=True, description="Active status")


class AmbiguousTermUpdate(BaseModel):
    """Request to update an ambiguous term."""
    term: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    possible_entities: Optional[List[PossibleEntity]] = None
    match_patterns: Optional[List[str]] = None
    priority: Optional[int] = Field(None, ge=0, le=1000)
    is_active: Optional[bool] = None


class AmbiguousTermListResponse(BaseModel):
    """Response for listing ambiguous terms."""
    terms: List[AmbiguousTerm] = Field(default_factory=list)
    total: int = Field(default=0)
    page: int = Field(default=1)
    page_size: int = Field(default=20)


class UserPreferenceListResponse(BaseModel):
    """Response for listing user preferences."""
    preferences: List[UserTermPreference] = Field(default_factory=list)
    total: int = Field(default=0)


# =============================================================================
# Term Candidate Models (Phase 2 - Auto Term Extraction)
# =============================================================================

class TermCandidate(BaseModel):
    """Auto-extracted term candidate from documents."""
    id: int = Field(..., description="Database ID")
    term: str = Field(..., description="Extracted term text")
    term_normalized: str = Field(..., description="Normalized form")
    source_document_id: Optional[str] = Field(None, description="Source document ID")
    source_document_name: Optional[str] = Field(None, description="Source document name")
    extraction_context: Optional[str] = Field(
        None,
        description="Surrounding context where term was found"
    )
    extraction_method: str = Field(
        default="pattern",
        description="How term was extracted: pattern, ner, frequency"
    )
    confidence_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="ML confidence score that this term needs clarification"
    )
    suggested_category: Optional[str] = Field(None, description="Auto-suggested category")
    occurrence_count: int = Field(default=1, description="Times this term appeared")
    status: str = Field(
        default="pending",
        description="Review status: pending, approved, rejected, merged"
    )
    reviewed_by: Optional[str] = Field(None, description="Admin who reviewed")
    reviewed_at: Optional[datetime] = None
    approved_term_id: Optional[int] = Field(
        None,
        description="Links to created/merged ambiguous_term after approval"
    )
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Similarity info from view (optional)
    match_status: Optional[str] = Field(
        None,
        description="Whether similar term exists: 'new' or 'similar_exists'"
    )
    similar_term_id: Optional[int] = Field(
        None,
        description="ID of similar existing term"
    )
    similar_term: Optional[str] = Field(
        None,
        description="Text of similar existing term"
    )

    class Config:
        from_attributes = True


class TermCandidateListResponse(BaseModel):
    """Response for listing term candidates."""
    candidates: List[TermCandidate] = Field(default_factory=list)
    total: int = Field(default=0)
    page: int = Field(default=1)
    page_size: int = Field(default=20)


class TermCandidateApproveRequest(BaseModel):
    """Request to approve a term candidate and create ambiguous term."""
    possible_entities: List[PossibleEntity] = Field(
        ...,
        min_length=2,
        description="At least 2 possible entities required for the new term"
    )
    category: Optional[str] = Field(None, max_length=50, description="Category")
    match_patterns: List[str] = Field(default_factory=list, description="Match patterns")
    priority: int = Field(default=0, ge=0, le=1000, description="Priority (0-1000)")


class TermCandidateMergeRequest(BaseModel):
    """Request to merge a term candidate into existing ambiguous term."""
    target_term_id: int = Field(..., description="Existing ambiguous_term ID to merge into")
    add_match_pattern: bool = Field(
        default=True,
        description="Whether to add the candidate term as a match pattern"
    )


class TermCandidateRejectRequest(BaseModel):
    """Request to reject a term candidate."""
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Reason for rejection (optional but recommended)"
    )


class TermCandidateStatistics(BaseModel):
    """Statistics about term candidates."""
    total: int = Field(..., description="Total number of candidates")
    by_status: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts by status (pending, approved, rejected, merged)"
    )
    by_method: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts by extraction method"
    )
    avg_confidence_by_status: Dict[str, float] = Field(
        default_factory=dict,
        description="Average confidence score by status"
    )


class GenerateEmbeddingsResponse(BaseModel):
    """Response from generating entity embeddings."""
    term_id: int = Field(..., description="Ambiguous term ID")
    entities_processed: int = Field(..., description="Number of entities processed")
    success: bool = Field(..., description="Whether all embeddings were generated")
    message: Optional[str] = Field(None, description="Status message")
