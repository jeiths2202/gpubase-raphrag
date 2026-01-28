"""
Summary Data Models

Data models for the Summary-First RAG system.
Provides structured types for summary documents, search results, and page references.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SummaryDocType(str, Enum):
    """Summary document types"""
    ERROR_CODES = "error-codes"
    COMMANDS = "commands"
    GLOSSARY = "glossary"
    CONFIGS = "configs"
    APIS = "apis"
    TERMS = "terms"
    CONCEPTS = "concepts"
    PROCEDURES = "procedures"


class ConfidenceLevel(str, Enum):
    """Search confidence levels for routing decisions"""
    HIGH = "high"      # >= 0.7: Use summary directly
    MEDIUM = "medium"  # 0.4 ~ 0.7: Combine with vector search
    LOW = "low"        # < 0.4: Fall back to vector search


@dataclass
class PageReference:
    """Reference to a specific page in a PDF document"""
    pdf_path: str
    page_number: int
    source_file: str  # Summary file that contains this reference

    def __hash__(self):
        return hash((self.pdf_path, self.page_number))

    def __eq__(self, other):
        if not isinstance(other, PageReference):
            return False
        return self.pdf_path == other.pdf_path and self.page_number == other.page_number


@dataclass
class SummaryDocument:
    """
    Represents a summary document loaded from the summaries directory.

    Summary documents are pre-processed markdown files containing
    error codes, commands, glossary terms, etc. extracted from PDF manuals.
    """
    id: str
    content: str
    doc_type: SummaryDocType
    source_file: str  # Markdown file name (e.g., "T.md", "BASE-5000.md")
    source_pdf: Optional[str] = None  # Original PDF if known
    page_numbers: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Extracted structured fields (varies by doc_type)
    name: Optional[str] = None  # Error name, command name, term name
    description: Optional[str] = None
    syntax: Optional[str] = None  # For commands
    solution: Optional[str] = None  # For error codes
    product: Optional[str] = None  # Product name (OpenFrame, Tibero, etc.)

    # Platform/Version fields for multi-product search
    platform: Optional[str] = None  # MVS, MSP, XSP, VOS3
    product_version: Optional[str] = None  # 7.1, 7.3
    document_version: Optional[str] = None  # v3.3.1

    # Parent tool field for subcommand grouping (e.g., "tjesmgr" for "BOOT" command)
    parent_tool: Optional[str] = None

    def __hash__(self):
        return hash(self.id)


@dataclass
class ProductVariant:
    """
    Single product/version variant of a command or error code.

    Represents how a specific command or error behaves on a particular
    platform (MVS, MSP, XSP, VOS3) and version.
    """
    platform: str  # MVS, MSP, XSP, VOS3
    product_version: Optional[str] = None  # 7.1, 7.3
    description: Optional[str] = None
    syntax: Optional[str] = None
    source_pdf: Optional[str] = None
    page_numbers: List[int] = field(default_factory=list)
    solution: Optional[str] = None  # For error codes
    document_version: Optional[str] = None  # v3.3.1


@dataclass
class MultiProductResult:
    """
    Aggregated result across multiple platforms/versions.

    Groups the same command or error code across different platforms
    to show platform-specific differences.
    """
    name: str  # Command/error name
    doc_type: SummaryDocType
    variants: List[ProductVariant] = field(default_factory=list)
    score: float = 0.0

    @property
    def has_differences(self) -> bool:
        """Check if variants have different descriptions (platform-specific behavior)"""
        if len(self.variants) <= 1:
            return False
        descriptions = [v.description for v in self.variants if v.description]
        return len(set(descriptions)) > 1

    @property
    def available_platforms(self) -> List[str]:
        """Get list of platforms where this command/error exists"""
        return [v.platform for v in self.variants]


@dataclass
class SummarySearchResult:
    """
    Result from BM25 summary search.

    Contains the matched document, relevance score, and matched terms
    for debugging and explanation purposes.
    """
    document: SummaryDocument
    score: float
    matched_terms: List[str] = field(default_factory=list)
    rank: int = 0

    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Determine confidence level based on score"""
        if self.score >= 0.7:
            return ConfidenceLevel.HIGH
        elif self.score >= 0.4:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW


@dataclass
class ComprehensiveSearchResult:
    """
    Comprehensive search result combining multiple summary types.

    Used when searching across all summary categories (error codes,
    commands, glossary, etc.) in a single query.
    """
    results: List[SummarySearchResult] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    query: str = ""
    matched_categories: List[SummaryDocType] = field(default_factory=list)
    page_references: List[PageReference] = field(default_factory=list)

    # Query analysis results
    detected_error_codes: List[str] = field(default_factory=list)
    detected_commands: List[str] = field(default_factory=list)
    detected_terms: List[str] = field(default_factory=list)

    @property
    def total_results(self) -> int:
        return len(self.results)

    @property
    def has_high_confidence(self) -> bool:
        return self.confidence == ConfidenceLevel.HIGH

    def get_top_result(self) -> Optional[SummarySearchResult]:
        """Get the highest scoring result"""
        if not self.results:
            return None
        return max(self.results, key=lambda r: r.score)

    def get_context_string(self, max_results: int = 3) -> str:
        """
        Generate a context string for RAG query enrichment.

        Args:
            max_results: Maximum number of results to include

        Returns:
            Formatted context string for LLM consumption
        """
        if not self.results:
            return ""

        context_parts = []
        for result in self.results[:max_results]:
            doc = result.document

            if doc.doc_type == SummaryDocType.ERROR_CODES:
                ctx = f"[에러 {doc.name}: {doc.description or ''}]"
                if doc.solution:
                    ctx += f" 대처: {doc.solution[:100]}"
            elif doc.doc_type == SummaryDocType.COMMANDS:
                ctx = f"[명령어 {doc.name}"
                if doc.product:
                    ctx += f" ({doc.product})"
                ctx += f": {doc.description or ''}]"
                if doc.syntax:
                    ctx += f" 구문: {doc.syntax}"
            elif doc.doc_type == SummaryDocType.GLOSSARY:
                ctx = f"[{doc.name}: {doc.description or ''}]"
            else:
                ctx = f"[{doc.doc_type.value}: {doc.content[:200]}]"

            context_parts.append(ctx)

        return "\n".join(context_parts)


# Pydantic models for API responses

class SummarySearchResultResponse(BaseModel):
    """API response model for summary search result"""
    id: str = Field(..., description="Document ID")
    doc_type: str = Field(..., description="Document type (error-codes, commands, etc.)")
    name: Optional[str] = Field(None, description="Entity name (error name, command name, etc.)")
    description: Optional[str] = Field(None, description="Description")
    score: float = Field(..., description="Relevance score (0.0-1.0)")
    confidence: str = Field(..., description="Confidence level (high, medium, low)")
    source_file: str = Field(..., description="Source summary file")
    matched_terms: List[str] = Field(default_factory=list, description="Matched search terms")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "error_5212",
                "doc_type": "error-codes",
                "name": "DSALC_ERR_DATASET_NOT_FOUND",
                "description": "데이터셋을 찾을 수 없습니다",
                "score": 0.85,
                "confidence": "high",
                "source_file": "BASE-5000.md",
                "matched_terms": ["5212", "DATASET", "NOT_FOUND"]
            }
        }
    }


class ComprehensiveSearchResultResponse(BaseModel):
    """API response model for comprehensive summary search"""
    query: str = Field(..., description="Original search query")
    confidence: str = Field(..., description="Overall confidence level")
    total_results: int = Field(..., description="Total number of results")
    results: List[SummarySearchResultResponse] = Field(
        default_factory=list,
        description="Search results"
    )
    detected_error_codes: List[str] = Field(
        default_factory=list,
        description="Error codes detected in query"
    )
    detected_commands: List[str] = Field(
        default_factory=list,
        description="Commands detected in query"
    )
    detected_terms: List[str] = Field(
        default_factory=list,
        description="Technical terms detected in query"
    )
    context_string: Optional[str] = Field(
        None,
        description="Generated context string for RAG enrichment"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "에러코드 -5212 원인",
                "confidence": "high",
                "total_results": 1,
                "results": [{
                    "id": "error_5212",
                    "doc_type": "error-codes",
                    "name": "DSALC_ERR_DATASET_NOT_FOUND",
                    "description": "데이터셋을 찾을 수 없습니다",
                    "score": 0.85,
                    "confidence": "high",
                    "source_file": "BASE-5000.md",
                    "matched_terms": ["5212"]
                }],
                "detected_error_codes": ["-5212"],
                "detected_commands": [],
                "detected_terms": [],
                "context_string": "[에러 DSALC_ERR_DATASET_NOT_FOUND: 데이터셋을 찾을 수 없습니다]"
            }
        }
    }


class ProductVariantResponse(BaseModel):
    """API response model for a single product/version variant"""
    platform: str = Field(..., description="Platform identifier (MVS, MSP, XSP, VOS3)")
    product_version: Optional[str] = Field(None, description="Product version (e.g., 7.1, 7.3)")
    description: Optional[str] = Field(None, description="Platform-specific description")
    syntax: Optional[str] = Field(None, description="Platform-specific syntax")
    source_pdf: Optional[str] = Field(None, description="Source PDF filename")
    page_numbers: List[int] = Field(default_factory=list, description="Page numbers in source PDF")
    solution: Optional[str] = Field(None, description="Platform-specific solution (for error codes)")
    document_version: Optional[str] = Field(None, description="Document version (e.g., v3.3.1)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "platform": "MVS",
                "product_version": "7.3",
                "description": "TJES 노드를 초기화합니다",
                "syntax": "tjesmgr BOOT [node_name]",
                "source_pdf": "OF_Common_MVS_7.3_Tool-Reference-Guide_v3.3.1_ja.pdf",
                "page_numbers": [45, 46],
                "document_version": "v3.3.1"
            }
        }
    }


class MultiProductResultResponse(BaseModel):
    """API response model for aggregated multi-product search result"""
    name: str = Field(..., description="Command/error/term name")
    doc_type: str = Field(..., description="Document type (error-codes, commands, glossary, etc.)")
    variants: List[ProductVariantResponse] = Field(
        default_factory=list,
        description="Platform-specific variants"
    )
    has_differences: bool = Field(
        default=False,
        description="True if variants have different behavior across platforms"
    )
    available_platforms: List[str] = Field(
        default_factory=list,
        description="List of platforms where this item exists"
    )
    score: float = Field(default=0.0, description="Best match score across variants")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "tjesmgr",
                "doc_type": "commands",
                "variants": [
                    {
                        "platform": "MVS",
                        "product_version": "7.3",
                        "description": "TJES 관리자 유틸리티 (MVS)",
                        "syntax": "tjesmgr [command] [options]"
                    },
                    {
                        "platform": "MSP",
                        "product_version": "7.3",
                        "description": "TJES 관리자 유틸리티 (MSP)",
                        "syntax": "tjesmgr [command] [options]"
                    }
                ],
                "has_differences": True,
                "available_platforms": ["MVS", "MSP", "XSP", "VOS3"],
                "score": 0.95
            }
        }
    }
