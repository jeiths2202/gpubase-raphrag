"""
Vision LLM Port Interface

Abstract interface for Vision-capable LLMs (GPT-4V, Claude 3 Vision, etc.)
Follows the Port pattern for easy adapter swapping.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Union


class VisionTask(str, Enum):
    """Vision LLM task types"""
    DESCRIBE = "describe"              # Full image description
    EXTRACT_TEXT = "extract_text"      # OCR text extraction
    ANALYZE_CHART = "analyze_chart"    # Chart data extraction
    ANALYZE_DIAGRAM = "analyze_diagram"  # Diagram structure analysis
    EXTRACT_TABLE = "extract_table"    # Table data extraction
    ANSWER_QUESTION = "answer_question"  # Image-based Q&A


@dataclass
class ImageContent:
    """Image content for Vision LLM input"""
    image_bytes: bytes
    mime_type: str  # "image/png", "image/jpeg", "image/gif", "image/webp"
    description: Optional[str] = None  # Optional context for the image

    def __post_init__(self):
        valid_types = {"image/png", "image/jpeg", "image/gif", "image/webp"}
        if self.mime_type not in valid_types:
            raise ValueError(f"Invalid MIME type: {self.mime_type}. Must be one of {valid_types}")


@dataclass
class VisionMessage:
    """Vision LLM message with optional images"""
    role: str  # "user", "assistant", "system"
    content: str
    images: Optional[List[ImageContent]] = None

    def __post_init__(self):
        valid_roles = {"user", "assistant", "system"}
        if self.role not in valid_roles:
            raise ValueError(f"Invalid role: {self.role}. Must be one of {valid_roles}")


@dataclass
class VisionTokenUsage:
    """Token usage for Vision LLM calls"""
    prompt_tokens: int
    completion_tokens: int
    image_tokens: int = 0  # Some models count image tokens separately

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens + self.image_tokens


@dataclass
class VisionResponse:
    """Vision LLM response"""
    content: str
    model: str
    usage: VisionTokenUsage
    extracted_data: Optional[Dict[str, Any]] = None  # Structured data if applicable
    confidence: float = 1.0
    latency_ms: float = 0.0
    finish_reason: str = "stop"


@dataclass
class VisionStreamChunk:
    """Streaming chunk from Vision LLM"""
    content: str
    is_final: bool = False
    usage: Optional[VisionTokenUsage] = None


@dataclass
class VisionLLMConfig:
    """Configuration for Vision LLM calls"""
    max_tokens: int = 4096
    temperature: float = 0.7
    detail: str = "auto"  # "low", "high", "auto" - image detail level
    timeout: int = 60

    # Cost control
    max_images: int = 20
    max_image_dimension: int = 2048


@dataclass
class VisionAnalysisResult:
    """Result from single image analysis"""
    task: VisionTask
    content: str
    extracted_data: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    processing_time_ms: float = 0.0


@dataclass
class ImageValidationResult:
    """Result of image validation"""
    valid: bool
    reason: Optional[str] = None
    mime_type: Optional[str] = None
    dimensions: Optional[tuple] = None
    file_size: Optional[int] = None


class VisionLLMPort(ABC):
    """
    Abstract interface for Vision-capable LLMs.

    Implementations:
    - OpenAIVisionAdapter: GPT-4V, GPT-4o
    - AnthropicVisionAdapter: Claude 3 Vision
    - LocalVisionAdapter: LLaVA, Yi-VL (local models)
    """

    @abstractmethod
    async def generate(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> VisionResponse:
        """
        Generate a response from the Vision LLM.

        Args:
            messages: List of messages with optional images
            config: Optional configuration overrides

        Returns:
            VisionResponse with content and metadata
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> AsyncGenerator[VisionStreamChunk, None]:
        """
        Generate a streaming response from the Vision LLM.

        Args:
            messages: List of messages with optional images
            config: Optional configuration overrides

        Yields:
            VisionStreamChunk with content fragments
        """
        pass

    @abstractmethod
    async def analyze_image(
        self,
        image: ImageContent,
        task: VisionTask,
        context: Optional[str] = None
    ) -> VisionAnalysisResult:
        """
        Analyze a single image for a specific task.

        Args:
            image: The image to analyze
            task: The analysis task (DESCRIBE, EXTRACT_TEXT, etc.)
            context: Optional context to guide the analysis

        Returns:
            VisionAnalysisResult with extracted information
        """
        pass

    @abstractmethod
    async def analyze_images_batch(
        self,
        images: List[ImageContent],
        task: VisionTask,
        context: Optional[str] = None
    ) -> List[VisionAnalysisResult]:
        """
        Analyze multiple images for the same task.

        Args:
            images: List of images to analyze
            task: The analysis task
            context: Optional shared context

        Returns:
            List of VisionAnalysisResult
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the Vision LLM service is available.

        Returns:
            True if service is healthy
        """
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the Vision LLM model.

        Returns:
            Dict with model name, capabilities, limits, etc.
        """
        pass

    @abstractmethod
    def estimate_cost(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> float:
        """
        Estimate the cost of a Vision LLM call.

        Args:
            messages: Messages including images
            config: Configuration

        Returns:
            Estimated cost in USD
        """
        pass

    @abstractmethod
    def validate_image(self, image: ImageContent) -> ImageValidationResult:
        """
        Validate an image before sending to the Vision LLM.

        Args:
            image: Image to validate

        Returns:
            Validation result with any issues
        """
        pass


# Task-specific prompt templates
VISION_TASK_PROMPTS = {
    VisionTask.DESCRIBE: """Describe this image in detail. Include:
- Main subject and content
- Visual elements (colors, layout, composition)
- Any text visible in the image
- Context and purpose if apparent""",

    VisionTask.EXTRACT_TEXT: """Extract all text visible in this image.
- Preserve the original formatting and structure
- Include headers, labels, and captions
- Note any text that is unclear or partially visible""",

    VisionTask.ANALYZE_CHART: """Analyze this chart/graph and extract:
- Chart type (bar, line, pie, etc.)
- Title and axis labels
- All data points and values
- Trends and key insights
- Legend information if present

Return the data in a structured format.""",

    VisionTask.ANALYZE_DIAGRAM: """Analyze this diagram and describe:
- Diagram type (flowchart, sequence, architecture, etc.)
- All nodes/elements and their labels
- Connections and relationships between elements
- Flow direction and logic
- Any annotations or notes

Return the structure in a format suitable for reconstruction.""",

    VisionTask.EXTRACT_TABLE: """Extract the table data from this image:
- Identify all column headers
- Extract all row data
- Preserve the table structure
- Note any merged cells or special formatting

Return as structured tabular data.""",

    VisionTask.ANSWER_QUESTION: """Based on the image provided, answer the following question.
Be specific and reference visual elements when relevant.""",
}
