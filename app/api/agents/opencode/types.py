"""
OpenCode Agent Types and Data Models

Core types for the 5-step mandatory workflow:
1. Keyword Extraction
2. Summary Search
3. PDF Page Verification
4. Tool Selection (Vision/vLLM/Embedding)
5. Answer Generation
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
import uuid


class StepStatus(str, Enum):
    """Status of a pipeline step"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolType(str, Enum):
    """Tool types for Step 4 selection"""
    VISION = "vision"       # MiniCPM-V for visual content (port 12803)
    VLLM = "vllm"          # Text LLM for generation (port 12800)
    EMBEDDING = "embedding" # Semantic search (port 12801)


class AnswerStatus(str, Enum):
    """Answer generation status from the specification"""
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    RETRY = "RETRY"


@dataclass
class StepResult:
    """Result of a single pipeline step"""
    step_name: str
    step_number: int
    status: StepStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "step_name": self.step_name,
            "step_number": self.step_number,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class ExtractedKeywords:
    """Output of Step 1: Keyword Extraction"""
    primary_keywords: List[str] = field(default_factory=list)      # Main query terms
    secondary_keywords: List[str] = field(default_factory=list)    # Related terms
    product_keywords: List[str] = field(default_factory=list)      # OpenFrame products (TJES, TACF, etc.)
    error_codes: List[str] = field(default_factory=list)           # Detected error codes (-5212, etc.)
    command_names: List[str] = field(default_factory=list)         # Commands (tjesmgr, oscboot, etc.)
    language: str = "auto"

    def all_keywords(self) -> List[str]:
        """Get all keywords in original order"""
        return (
            self.primary_keywords +
            self.product_keywords +
            self.error_codes +
            self.command_names +
            self.secondary_keywords
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_keywords": self.primary_keywords,
            "secondary_keywords": self.secondary_keywords,
            "product_keywords": self.product_keywords,
            "error_codes": self.error_codes,
            "command_names": self.command_names,
            "language": self.language,
        }


@dataclass
class SummarySearchResult:
    """Output of Step 2: Summary Search"""
    keyword: str = ""
    matched_documents: List[Dict[str, Any]] = field(default_factory=list)
    error_context: Optional[str] = None
    term_context: Optional[str] = None
    command_context: Optional[str] = None
    api_context: Optional[str] = None
    product_context: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "matched_documents": self.matched_documents,
            "has_error_context": self.error_context is not None,
            "has_term_context": self.term_context is not None,
            "has_command_context": self.command_context is not None,
            "has_api_context": self.api_context is not None,
            "has_product_context": self.product_context is not None,
        }


@dataclass
class PDFVerificationResult:
    """Output of Step 3: PDF Page Verification"""
    document_name: str = ""
    page_numbers: List[int] = field(default_factory=list)
    verified_chunks: List[Dict[str, Any]] = field(default_factory=list)
    has_visual_content: bool = False
    visual_elements: List[Dict[str, Any]] = field(default_factory=list)  # Charts, tables, diagrams
    content_types: List[str] = field(default_factory=list)  # "text", "image", "table", "chart"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document": self.document_name,
            "pages": self.page_numbers,
            "chunk_count": len(self.verified_chunks),
            "has_visual_content": self.has_visual_content,
            "content_types": self.content_types,
        }


@dataclass
class ToolSelectionResult:
    """Output of Step 4: Tool Selection"""
    selected_tools: List[ToolType] = field(default_factory=list)
    reasoning: str = ""
    vision_required: bool = False
    estimated_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tools": [t.value for t in self.selected_tools],
            "vision_required": self.vision_required,
            "reasoning": self.reasoning,
        }


@dataclass
class HallucinationCheckResult:
    """Result of hallucination check"""
    is_hallucination: bool = False
    confidence: float = 0.0              # 0.0 - 1.0 (higher = more confident it's hallucination)
    reasons: List[str] = field(default_factory=list)
    ungrounded_claims: List[str] = field(default_factory=list)   # Claims without source
    suggested_corrections: List[str] = field(default_factory=list)
    retry_recommended: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_hallucination": self.is_hallucination,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "ungrounded_claims": self.ungrounded_claims,
            "retry_recommended": self.retry_recommended,
        }


@dataclass
class OpenCodeConfig:
    """Configuration for OpenCode Agent"""
    max_retries: int = 3
    hallucination_threshold: float = 0.6  # Confidence threshold for hallucination detection
    min_source_confidence: float = 0.5    # Minimum confidence for source matching
    vision_dpi: int = 150                 # PDF rendering DPI
    max_keywords: int = 10                # Maximum keywords to extract
    max_pages_per_doc: int = 5            # Maximum pages to verify per document
    max_documents: int = 5                # Maximum documents to verify
    timeout_seconds: float = 300.0        # Total execution timeout
    stream_progress: bool = True          # Stream detailed progress to UI


@dataclass
class OpenCodeContext:
    """Context passed through the 5-step pipeline"""
    # Request
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    session_id: str = ""
    user_id: Optional[str] = None
    language: str = "auto"

    # Configuration
    config: OpenCodeConfig = field(default_factory=OpenCodeConfig)

    # Pipeline state (accumulated through steps)
    keywords: Optional[ExtractedKeywords] = None
    summary_searches: List[SummarySearchResult] = field(default_factory=list)
    pdf_verifications: List[PDFVerificationResult] = field(default_factory=list)
    tool_selection: Optional[ToolSelectionResult] = None

    # File context (session-only, not stored in DB)
    file_context: Optional[str] = None
    url_context: Optional[str] = None

    # Execution tracking
    retry_count: int = 0
    step_history: List[StepResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)

    # Hallucination detection
    hallucination_check: Optional[HallucinationCheckResult] = None

    def get_all_sources(self) -> List[Dict[str, Any]]:
        """Get all verified sources from PDF verification results"""
        sources = []
        for pdf_result in self.pdf_verifications:
            for chunk in pdf_result.verified_chunks:
                sources.append({
                    "document": pdf_result.document_name,
                    "page": chunk.get("page_number"),
                    "content": chunk.get("content", "")[:500],
                    "content_type": chunk.get("content_type", "text"),
                })
        return sources

    def to_log_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for execution logging"""
        return {
            "run_id": self.run_id,
            "query": self.query,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "language": self.language,
            "keywords": self.keywords.to_dict() if self.keywords else None,
            "summary_searches": [s.to_dict() for s in self.summary_searches],
            "pdf_verifications": [p.to_dict() for p in self.pdf_verifications],
            "tool_selection": self.tool_selection.to_dict() if self.tool_selection else None,
            "retry_count": self.retry_count,
            "step_history": [s.to_dict() for s in self.step_history],
            "hallucination_check": self.hallucination_check.to_dict() if self.hallucination_check else None,
        }


@dataclass
class OpenCodeResult:
    """Final result of OpenCode execution"""
    answer: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    status: AnswerStatus = AnswerStatus.SUCCESS
    confidence: float = 0.0
    execution_time_ms: float = 0.0
    steps_executed: int = 0
    retry_count: int = 0
    hallucination_checked: bool = False
    vision_used: bool = False
    failure_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Verification checklist from specification
    verification_checklist: Dict[str, bool] = field(default_factory=lambda: {
        "all_keywords_extracted": False,
        "all_summary_documents_searched": False,
        "all_relevant_pdfs_opened": False,
        "pages_verified": False,
        "correct_tools_used": False,
        "all_claims_sourced": False,
        "no_hallucination_detected": False,
    })

    def is_verified(self) -> bool:
        """Check if all verification checklist items passed"""
        return all(self.verification_checklist.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": self.sources,
            "status": self.status.value,
            "confidence": self.confidence,
            "execution_time_ms": self.execution_time_ms,
            "steps_executed": self.steps_executed,
            "retry_count": self.retry_count,
            "hallucination_checked": self.hallucination_checked,
            "vision_used": self.vision_used,
            "failure_reason": self.failure_reason,
            "verification_checklist": self.verification_checklist,
            "verification_status": "PASSED" if self.is_verified() else "FAILED",
            "metadata": self.metadata,
        }

    def format_output(self) -> str:
        """Format output according to specification"""
        lines = [
            "ANSWER:",
            self.answer,
            "",
            "SOURCES:",
        ]
        for source in self.sources:
            doc = source.get("document", "Unknown")
            page = source.get("page", "N/A")
            lines.append(f"- {doc} / Page {page}")

        lines.append("")
        lines.append(f"VERIFICATION STATUS:")
        lines.append("PASSED" if self.is_verified() else "FAILED")

        return "\n".join(lines)
