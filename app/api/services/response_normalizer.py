"""
Response Normalizer

Normalizes responses from different Vision LLMs to a unified format.
Handles structured data extraction, multi-modal response assembly,
and language-specific formatting.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from app.api.models.vision import (
    ChartData,
    DiagramStructure,
    ExtractedVisualInfo,
    TableData,
    UnifiedQueryResponse,
    VisualElement,
)
from app.api.ports.vision_llm_port import VisionResponse

logger = logging.getLogger(__name__)


class ResponseFormat(str, Enum):
    """Output format types"""
    TEXT = "text"
    MARKDOWN = "markdown"
    JSON = "json"
    STRUCTURED = "structured"


class ContentType(str, Enum):
    """Content classification types"""
    NARRATIVE = "narrative"
    DATA_ANALYSIS = "data_analysis"
    CHART_DESCRIPTION = "chart_description"
    TABLE_EXTRACTION = "table_extraction"
    DIAGRAM_EXPLANATION = "diagram_explanation"
    CODE_ANALYSIS = "code_analysis"
    MIXED = "mixed"


@dataclass
class NormalizationConfig:
    """Configuration for response normalization"""
    output_format: ResponseFormat = ResponseFormat.MARKDOWN
    language: str = "auto"
    include_confidence: bool = True
    include_sources: bool = True
    max_length: Optional[int] = None
    extract_structured_data: bool = True
    preserve_original: bool = False


@dataclass
class NormalizedSection:
    """A normalized section of the response"""
    content_type: ContentType
    content: str
    confidence: float = 1.0
    structured_data: Optional[Dict[str, Any]] = None
    source_references: List[str] = field(default_factory=list)


@dataclass
class NormalizedResponse:
    """Fully normalized response"""
    # Main content
    text: str
    sections: List[NormalizedSection]

    # Metadata
    content_type: ContentType
    language: str
    confidence: float

    # Structured data
    extracted_charts: List[ChartData] = field(default_factory=list)
    extracted_tables: List[TableData] = field(default_factory=list)
    extracted_diagrams: List[DiagramStructure] = field(default_factory=list)

    # Source tracking
    sources: List[str] = field(default_factory=list)
    model_used: str = ""

    # Original response (if preserved)
    original_response: Optional[VisionResponse] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "text": self.text,
            "sections": [
                {
                    "content_type": s.content_type.value,
                    "content": s.content,
                    "confidence": s.confidence,
                    "structured_data": s.structured_data,
                }
                for s in self.sections
            ],
            "content_type": self.content_type.value,
            "language": self.language,
            "confidence": self.confidence,
            "extracted_charts": [c.to_dict() for c in self.extracted_charts],
            "extracted_tables": [t.to_dict() for t in self.extracted_tables],
            "sources": self.sources,
            "model_used": self.model_used,
        }


class ResponseNormalizer:
    """
    Normalizes responses from different Vision LLMs.

    Key features:
    1. Unified format across OpenAI, Anthropic, and other providers
    2. Structured data extraction (charts, tables, diagrams)
    3. Multi-language support (English, Korean, Japanese)
    4. Content classification and sectioning
    5. Confidence scoring

    Usage:
        normalizer = ResponseNormalizer()
        normalized = normalizer.normalize(vision_response)

        # Access structured data
        for chart in normalized.extracted_charts:
            print(chart.title, chart.data_points)
    """

    # Chart-related patterns (English/Korean)
    CHART_PATTERNS = [
        r'(?:bar|line|pie|scatter|histogram|area)\s*(?:chart|graph)',
        r'(?:막대|선|원|산점도|히스토그램|영역)\s*(?:그래프|차트)',
        r'(?:data|value|percentage|trend|axis|legend)',
        r'(?:데이터|값|퍼센트|추세|축|범례)',
    ]

    # Table patterns
    TABLE_PATTERNS = [
        r'\|.*\|.*\|',  # Markdown table
        r'(?:row|column|cell|header)',
        r'(?:행|열|셀|헤더)',
    ]

    # Diagram patterns
    DIAGRAM_PATTERNS = [
        r'(?:flow|process|architecture|structure|component)',
        r'(?:흐름|프로세스|아키텍처|구조|컴포넌트)',
        r'(?:arrow|box|connection|node)',
        r'(?:화살표|박스|연결|노드)',
    ]

    def __init__(
        self,
        default_config: Optional[NormalizationConfig] = None,
    ):
        """
        Initialize normalizer.

        Args:
            default_config: Default normalization configuration
        """
        self.default_config = default_config or NormalizationConfig()
        self._compiled_patterns = self._compile_patterns()

    def normalize(
        self,
        response: VisionResponse,
        config: Optional[NormalizationConfig] = None,
    ) -> NormalizedResponse:
        """
        Normalize a Vision LLM response.

        Args:
            response: Raw Vision LLM response
            config: Optional configuration override

        Returns:
            NormalizedResponse with unified format
        """
        cfg = config or self.default_config

        # Detect language if auto
        language = cfg.language
        if language == "auto":
            language = self._detect_language(response.text)

        # Classify content type
        content_type = self._classify_content(response.text)

        # Parse into sections
        sections = self._parse_sections(response.text, content_type)

        # Extract structured data if enabled
        extracted_charts = []
        extracted_tables = []
        extracted_diagrams = []

        if cfg.extract_structured_data:
            extracted_charts = self._extract_charts(response.text, sections)
            extracted_tables = self._extract_tables(response.text, sections)
            extracted_diagrams = self._extract_diagrams(response.text, sections)

        # Format output text
        formatted_text = self._format_output(
            sections,
            cfg.output_format,
            language,
        )

        # Apply length limit if specified
        if cfg.max_length and len(formatted_text) > cfg.max_length:
            formatted_text = self._truncate_intelligently(
                formatted_text,
                cfg.max_length,
                language,
            )

        return NormalizedResponse(
            text=formatted_text,
            sections=sections,
            content_type=content_type,
            language=language,
            confidence=response.confidence if hasattr(response, 'confidence') else 0.9,
            extracted_charts=extracted_charts,
            extracted_tables=extracted_tables,
            extracted_diagrams=extracted_diagrams,
            sources=[],  # Populated by caller if needed
            model_used=response.model,
            original_response=response if cfg.preserve_original else None,
        )

    def normalize_multi_source(
        self,
        responses: List[VisionResponse],
        config: Optional[NormalizationConfig] = None,
    ) -> NormalizedResponse:
        """
        Normalize and merge responses from multiple sources.

        Useful for combining Vision LLM response with text retrieval.

        Args:
            responses: List of responses to merge
            config: Optional configuration

        Returns:
            Merged NormalizedResponse
        """
        if not responses:
            return NormalizedResponse(
                text="",
                sections=[],
                content_type=ContentType.NARRATIVE,
                language="en",
                confidence=0.0,
            )

        if len(responses) == 1:
            return self.normalize(responses[0], config)

        # Normalize each response
        normalized = [self.normalize(r, config) for r in responses]

        # Merge sections
        all_sections = []
        for norm in normalized:
            all_sections.extend(norm.sections)

        # Deduplicate similar sections
        unique_sections = self._deduplicate_sections(all_sections)

        # Determine overall content type
        content_types = [n.content_type for n in normalized]
        overall_type = self._determine_overall_type(content_types)

        # Merge extracted data
        all_charts = []
        all_tables = []
        all_diagrams = []
        for norm in normalized:
            all_charts.extend(norm.extracted_charts)
            all_tables.extend(norm.extracted_tables)
            all_diagrams.extend(norm.extracted_diagrams)

        # Calculate average confidence
        avg_confidence = sum(n.confidence for n in normalized) / len(normalized)

        # Format merged text
        cfg = config or self.default_config
        merged_text = self._format_output(
            unique_sections,
            cfg.output_format,
            normalized[0].language,
        )

        return NormalizedResponse(
            text=merged_text,
            sections=unique_sections,
            content_type=overall_type,
            language=normalized[0].language,
            confidence=avg_confidence,
            extracted_charts=all_charts,
            extracted_tables=all_tables,
            extracted_diagrams=all_diagrams,
            sources=[n.model_used for n in normalized],
            model_used=", ".join(n.model_used for n in normalized if n.model_used),
        )

    def to_unified_response(
        self,
        normalized: NormalizedResponse,
        query: str,
        document_ids: List[str],
    ) -> UnifiedQueryResponse:
        """
        Convert NormalizedResponse to UnifiedQueryResponse for API output.

        Args:
            normalized: Normalized response
            query: Original query
            document_ids: Source document IDs

        Returns:
            UnifiedQueryResponse for API
        """
        # Build visual info if structured data exists
        visual_info = None
        if (normalized.extracted_charts or
            normalized.extracted_tables or
            normalized.extracted_diagrams):
            visual_info = ExtractedVisualInfo(
                charts=normalized.extracted_charts,
                tables=normalized.extracted_tables,
                diagrams=normalized.extracted_diagrams,
            )

        return UnifiedQueryResponse(
            query=query,
            answer=normalized.text,
            sources=document_ids,
            confidence=normalized.confidence,
            model_used=normalized.model_used,
            visual_info=visual_info,
            language=normalized.language,
        )

    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile regex patterns for detection."""
        return {
            "chart": [
                re.compile(p, re.IGNORECASE | re.UNICODE)
                for p in self.CHART_PATTERNS
            ],
            "table": [
                re.compile(p, re.IGNORECASE | re.UNICODE)
                for p in self.TABLE_PATTERNS
            ],
            "diagram": [
                re.compile(p, re.IGNORECASE | re.UNICODE)
                for p in self.DIAGRAM_PATTERNS
            ],
        }

    def _detect_language(self, text: str) -> str:
        """Detect language from text content."""
        # Korean characters
        korean = len(re.findall(r'[\uac00-\ud7af]', text))
        # Japanese characters
        japanese = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text))
        # ASCII
        ascii_chars = len(re.findall(r'[a-zA-Z]', text))

        total = korean + japanese + ascii_chars
        if total == 0:
            return "en"

        if korean / total > 0.3:
            return "ko"
        elif japanese / total > 0.3:
            return "ja"
        return "en"

    def _classify_content(self, text: str) -> ContentType:
        """Classify the type of content in the response."""
        text_lower = text.lower()

        # Check for chart content
        chart_score = sum(
            1 for p in self._compiled_patterns["chart"]
            if p.search(text_lower)
        )

        # Check for table content
        table_score = sum(
            1 for p in self._compiled_patterns["table"]
            if p.search(text_lower)
        )

        # Check for diagram content
        diagram_score = sum(
            1 for p in self._compiled_patterns["diagram"]
            if p.search(text_lower)
        )

        # Check for code
        code_patterns = [r'```', r'def\s+\w+', r'function\s+\w+', r'class\s+\w+']
        code_score = sum(
            1 for p in code_patterns
            if re.search(p, text)
        )

        # Determine type based on scores
        max_score = max(chart_score, table_score, diagram_score, code_score)

        if max_score == 0:
            return ContentType.NARRATIVE

        if chart_score > 0 and table_score > 0:
            return ContentType.DATA_ANALYSIS
        elif chart_score == max_score:
            return ContentType.CHART_DESCRIPTION
        elif table_score == max_score:
            return ContentType.TABLE_EXTRACTION
        elif diagram_score == max_score:
            return ContentType.DIAGRAM_EXPLANATION
        elif code_score == max_score:
            return ContentType.CODE_ANALYSIS

        return ContentType.MIXED

    def _parse_sections(
        self,
        text: str,
        content_type: ContentType,
    ) -> List[NormalizedSection]:
        """Parse text into logical sections."""
        sections = []

        # Split by markdown headers or double newlines
        header_pattern = r'(?:^|\n)(#{1,3})\s+(.+?)(?:\n|$)'
        parts = re.split(header_pattern, text)

        current_section = ""

        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue

            # Check if it's a header marker
            if part in ['#', '##', '###']:
                continue

            # If previous was a header marker, this is a header
            if i > 0 and parts[i-1] in ['#', '##', '###']:
                if current_section:
                    sections.append(self._create_section(
                        current_section,
                        content_type,
                    ))
                current_section = f"## {part}\n"
            else:
                current_section += part + "\n"

        # Add last section
        if current_section.strip():
            sections.append(self._create_section(
                current_section.strip(),
                content_type,
            ))

        # If no sections found, create one from entire text
        if not sections:
            sections.append(self._create_section(text, content_type))

        return sections

    def _create_section(
        self,
        content: str,
        parent_type: ContentType,
    ) -> NormalizedSection:
        """Create a normalized section from content."""
        # Determine section-specific content type
        section_type = self._classify_content(content)
        if section_type == ContentType.NARRATIVE:
            section_type = parent_type

        # Extract any structured data from section
        structured_data = None
        if section_type == ContentType.TABLE_EXTRACTION:
            structured_data = self._parse_markdown_table(content)

        return NormalizedSection(
            content_type=section_type,
            content=content,
            confidence=0.9,
            structured_data=structured_data,
        )

    def _extract_charts(
        self,
        text: str,
        sections: List[NormalizedSection],
    ) -> List[ChartData]:
        """Extract chart data from text."""
        charts = []

        # Look for chart descriptions
        chart_sections = [
            s for s in sections
            if s.content_type == ContentType.CHART_DESCRIPTION
        ]

        for section in chart_sections:
            chart = self._parse_chart_description(section.content)
            if chart:
                charts.append(chart)

        return charts

    def _parse_chart_description(self, text: str) -> Optional[ChartData]:
        """Parse chart description to structured data."""
        # Extract chart type
        chart_type = "unknown"
        type_patterns = {
            "bar": r'bar\s*(chart|graph)|막대\s*(그래프|차트)',
            "line": r'line\s*(chart|graph)|선\s*(그래프|차트)|꺾은선',
            "pie": r'pie\s*(chart|graph)|원\s*(그래프|차트)',
            "scatter": r'scatter\s*(plot|chart)|산점도',
        }

        for ctype, pattern in type_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                chart_type = ctype
                break

        # Extract title (first line often is title)
        lines = text.strip().split('\n')
        title = lines[0].strip('#').strip() if lines else "Chart"

        return ChartData(
            chart_type=chart_type,
            title=title,
            description=text,
            data_points=[],
            x_axis_label="",
            y_axis_label="",
        )

    def _extract_tables(
        self,
        text: str,
        sections: List[NormalizedSection],
    ) -> List[TableData]:
        """Extract table data from text."""
        tables = []

        # Look for markdown tables
        table_pattern = r'\|(.+)\|\n\|[-:\s|]+\|\n((?:\|.+\|\n?)+)'
        matches = re.finditer(table_pattern, text)

        for match in matches:
            header_row = match.group(1)
            body = match.group(2)

            headers = [h.strip() for h in header_row.split('|') if h.strip()]
            rows = []

            for line in body.strip().split('\n'):
                row = [c.strip() for c in line.split('|') if c.strip()]
                if row:
                    rows.append(row)

            tables.append(TableData(
                headers=headers,
                rows=rows,
                title="Extracted Table",
            ))

        return tables

    def _extract_diagrams(
        self,
        text: str,
        sections: List[NormalizedSection],
    ) -> List[DiagramStructure]:
        """Extract diagram descriptions from text."""
        diagrams = []

        diagram_sections = [
            s for s in sections
            if s.content_type == ContentType.DIAGRAM_EXPLANATION
        ]

        for section in diagram_sections:
            # Extract nodes and connections from description
            nodes = re.findall(r'(?:box|node|component|step)\s*[:\-]\s*["\']?([^"\'\n,]+)',
                             section.content, re.IGNORECASE)

            diagrams.append(DiagramStructure(
                diagram_type="flowchart",
                description=section.content,
                nodes=[{"id": str(i), "label": n.strip()} for i, n in enumerate(nodes)],
                connections=[],
            ))

        return diagrams

    def _parse_markdown_table(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse markdown table to structured data."""
        table_pattern = r'\|(.+)\|\n\|[-:\s|]+\|\n((?:\|.+\|\n?)+)'
        match = re.search(table_pattern, content)

        if not match:
            return None

        header_row = match.group(1)
        body = match.group(2)

        headers = [h.strip() for h in header_row.split('|') if h.strip()]
        rows = []

        for line in body.strip().split('\n'):
            row = [c.strip() for c in line.split('|') if c.strip()]
            if row:
                rows.append(row)

        return {
            "headers": headers,
            "rows": rows,
            "row_count": len(rows),
        }

    def _format_output(
        self,
        sections: List[NormalizedSection],
        output_format: ResponseFormat,
        language: str,
    ) -> str:
        """Format sections into output text."""
        if output_format == ResponseFormat.JSON:
            import json
            return json.dumps({
                "sections": [
                    {
                        "type": s.content_type.value,
                        "content": s.content,
                    }
                    for s in sections
                ],
                "language": language,
            }, ensure_ascii=False, indent=2)

        elif output_format == ResponseFormat.TEXT:
            return "\n\n".join(s.content for s in sections)

        elif output_format == ResponseFormat.STRUCTURED:
            parts = []
            for i, section in enumerate(sections, 1):
                parts.append(f"[Section {i} - {section.content_type.value}]")
                parts.append(section.content)
                parts.append("")
            return "\n".join(parts)

        else:  # MARKDOWN (default)
            return "\n\n".join(s.content for s in sections)

    def _truncate_intelligently(
        self,
        text: str,
        max_length: int,
        language: str,
    ) -> str:
        """Truncate text at natural boundaries."""
        if len(text) <= max_length:
            return text

        # Find last complete sentence before limit
        truncated = text[:max_length]

        # Find last sentence ending
        sentence_endings = ['.', '!', '?', '。', '！', '？']
        last_ending = -1

        for ending in sentence_endings:
            pos = truncated.rfind(ending)
            if pos > last_ending:
                last_ending = pos

        if last_ending > max_length * 0.7:
            truncated = truncated[:last_ending + 1]

        # Add continuation indicator
        if language == "ko":
            truncated += "\n\n... (계속)"
        elif language == "ja":
            truncated += "\n\n... (続く)"
        else:
            truncated += "\n\n... (continued)"

        return truncated

    def _deduplicate_sections(
        self,
        sections: List[NormalizedSection],
    ) -> List[NormalizedSection]:
        """Remove duplicate or highly similar sections."""
        unique = []
        seen_content = set()

        for section in sections:
            # Create fingerprint (first 100 chars)
            fingerprint = section.content[:100].strip().lower()

            if fingerprint not in seen_content:
                seen_content.add(fingerprint)
                unique.append(section)

        return unique

    def _determine_overall_type(
        self,
        content_types: List[ContentType],
    ) -> ContentType:
        """Determine overall content type from multiple types."""
        if len(set(content_types)) == 1:
            return content_types[0]

        # If mixed, use MIXED
        if len(set(content_types)) > 2:
            return ContentType.MIXED

        # If data + chart, use DATA_ANALYSIS
        if ContentType.CHART_DESCRIPTION in content_types:
            return ContentType.DATA_ANALYSIS

        return ContentType.MIXED


# Factory functions

def create_normalizer(
    output_format: str = "markdown",
    language: str = "auto",
) -> ResponseNormalizer:
    """Create normalizer with common configuration."""
    config = NormalizationConfig(
        output_format=ResponseFormat(output_format),
        language=language,
    )
    return ResponseNormalizer(default_config=config)


def create_korean_normalizer() -> ResponseNormalizer:
    """Create normalizer optimized for Korean content."""
    config = NormalizationConfig(
        output_format=ResponseFormat.MARKDOWN,
        language="ko",
        include_confidence=True,
        extract_structured_data=True,
    )
    return ResponseNormalizer(default_config=config)
