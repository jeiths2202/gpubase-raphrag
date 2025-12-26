"""
OpenAI Vision Adapter

Implementation of VisionLLMPort for GPT-4 Vision (GPT-4V, GPT-4o).
Primary Vision LLM adapter for the system.
"""

import asyncio
import base64
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI

from app.api.ports.vision_llm_port import (
    ImageContent,
    ImageValidationResult,
    VisionAnalysisResult,
    VisionLLMConfig,
    VisionLLMPort,
    VisionMessage,
    VisionResponse,
    VisionStreamChunk,
    VisionTask,
    VisionTokenUsage,
    VISION_TASK_PROMPTS,
)

logger = logging.getLogger(__name__)


class OpenAIVisionAdapter(VisionLLMPort):
    """
    OpenAI Vision LLM Adapter (GPT-4V, GPT-4o)

    Primary Vision LLM implementation supporting:
    - Multi-image analysis
    - Streaming responses
    - Cost estimation
    - Automatic retry with exponential backoff
    """

    # Pricing (USD per token, as of 2025)
    PRICING = {
        "gpt-4o": {
            "input": 0.005 / 1000,      # $0.005 per 1K input tokens
            "output": 0.015 / 1000,     # $0.015 per 1K output tokens
            "image_base": 0.0085,       # Base cost per image (varies by size)
        },
        "gpt-4o-mini": {
            "input": 0.00015 / 1000,
            "output": 0.0006 / 1000,
            "image_base": 0.001275,
        },
        "gpt-4-turbo": {
            "input": 0.01 / 1000,
            "output": 0.03 / 1000,
            "image_base": 0.0085,
        },
    }

    # Image token estimation (approximate)
    # Low detail: 85 tokens, High detail: 85 + 170 * tiles
    IMAGE_TOKENS_LOW = 85
    IMAGE_TOKENS_HIGH_BASE = 85
    IMAGE_TOKENS_PER_TILE = 170
    TILE_SIZE = 512

    # Limits
    MAX_IMAGES_PER_REQUEST = 20
    MAX_IMAGE_DIMENSION = 2048
    SUPPORTED_FORMATS = {"image/png", "image/jpeg", "image/gif", "image/webp"}

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 60,
    ):
        """
        Initialize OpenAI Vision adapter.

        Args:
            api_key: OpenAI API key
            model: Model name (gpt-4o, gpt-4o-mini, gpt-4-turbo)
            base_url: Optional custom base URL
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds
        """
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
        )
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout

    async def generate(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> VisionResponse:
        """Generate a response from GPT-4 Vision."""
        config = config or VisionLLMConfig()
        start_time = time.time()

        # Convert messages to OpenAI format
        openai_messages = self._convert_messages(messages, config)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

            latency_ms = (time.time() - start_time) * 1000

            # Calculate image tokens
            image_tokens = self._estimate_image_tokens(messages, config)

            return VisionResponse(
                content=response.choices[0].message.content or "",
                model=self.model,
                usage=VisionTokenUsage(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    image_tokens=image_tokens,
                ),
                confidence=1.0,
                latency_ms=latency_ms,
                finish_reason=response.choices[0].finish_reason or "stop",
            )

        except Exception as e:
            logger.error(f"OpenAI Vision API error: {e}")
            raise

    async def generate_stream(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> AsyncGenerator[VisionStreamChunk, None]:
        """Generate a streaming response from GPT-4 Vision."""
        config = config or VisionLLMConfig()

        # Convert messages to OpenAI format
        openai_messages = self._convert_messages(messages, config)

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield VisionStreamChunk(
                        content=chunk.choices[0].delta.content,
                        is_final=chunk.choices[0].finish_reason is not None,
                    )

        except Exception as e:
            logger.error(f"OpenAI Vision streaming error: {e}")
            raise

    async def analyze_image(
        self,
        image: ImageContent,
        task: VisionTask,
        context: Optional[str] = None
    ) -> VisionAnalysisResult:
        """Analyze a single image for a specific task."""
        start_time = time.time()

        # Build prompt based on task
        prompt = VISION_TASK_PROMPTS.get(task, "Describe this image.")
        if context:
            prompt = f"{prompt}\n\nAdditional context: {context}"

        if task == VisionTask.ANSWER_QUESTION and context:
            prompt = f"{VISION_TASK_PROMPTS[task]}\n\nQuestion: {context}"

        messages = [
            VisionMessage(
                role="user",
                content=prompt,
                images=[image]
            )
        ]

        response = await self.generate(messages)
        processing_time = (time.time() - start_time) * 1000

        # Extract structured data if applicable
        extracted_data = self._extract_structured_data(response.content, task)

        return VisionAnalysisResult(
            task=task,
            content=response.content,
            extracted_data=extracted_data,
            confidence=1.0,
            processing_time_ms=processing_time,
        )

    async def analyze_images_batch(
        self,
        images: List[ImageContent],
        task: VisionTask,
        context: Optional[str] = None
    ) -> List[VisionAnalysisResult]:
        """Analyze multiple images for the same task."""
        # Process in batches to respect API limits
        batch_size = min(5, self.MAX_IMAGES_PER_REQUEST)
        results = []

        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]

            # Process batch concurrently
            batch_results = await asyncio.gather(*[
                self.analyze_image(img, task, context)
                for img in batch
            ], return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Batch image analysis error: {result}")
                    results.append(VisionAnalysisResult(
                        task=task,
                        content=f"Error: {str(result)}",
                        confidence=0.0,
                    ))
                else:
                    results.append(result)

        return results

    async def health_check(self) -> bool:
        """Check if OpenAI Vision API is available."""
        try:
            # Simple API call to check connectivity
            response = await self.client.models.retrieve(self.model)
            return response.id == self.model
        except Exception as e:
            logger.error(f"OpenAI Vision health check failed: {e}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the Vision model."""
        return {
            "provider": "openai",
            "model": self.model,
            "capabilities": [
                "image_understanding",
                "text_extraction",
                "chart_analysis",
                "diagram_analysis",
                "multi_image",
                "streaming",
            ],
            "limits": {
                "max_images_per_request": self.MAX_IMAGES_PER_REQUEST,
                "max_image_dimension": self.MAX_IMAGE_DIMENSION,
                "supported_formats": list(self.SUPPORTED_FORMATS),
            },
            "pricing": self.PRICING.get(self.model, self.PRICING["gpt-4o"]),
        }

    def estimate_cost(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> float:
        """Estimate the cost of a Vision LLM call."""
        config = config or VisionLLMConfig()
        pricing = self.PRICING.get(self.model, self.PRICING["gpt-4o"])

        # Estimate text tokens (rough approximation: 4 chars per token)
        text_tokens = sum(len(msg.content) // 4 for msg in messages)
        text_cost = text_tokens * pricing["input"]

        # Estimate image cost
        image_count = sum(
            len(msg.images) if msg.images else 0
            for msg in messages
        )
        image_cost = image_count * pricing["image_base"]

        # Estimate output tokens
        output_tokens = config.max_tokens // 2  # Conservative estimate
        output_cost = output_tokens * pricing["output"]

        return text_cost + image_cost + output_cost

    def validate_image(self, image: ImageContent) -> ImageValidationResult:
        """Validate an image before sending to the API."""
        # Check MIME type
        if image.mime_type not in self.SUPPORTED_FORMATS:
            return ImageValidationResult(
                valid=False,
                reason=f"Unsupported format: {image.mime_type}",
                mime_type=image.mime_type,
            )

        # Check file size (20MB limit)
        file_size = len(image.image_bytes)
        if file_size > 20 * 1024 * 1024:
            return ImageValidationResult(
                valid=False,
                reason=f"Image too large: {file_size / 1024 / 1024:.1f}MB (max 20MB)",
                file_size=file_size,
            )

        return ImageValidationResult(
            valid=True,
            mime_type=image.mime_type,
            file_size=file_size,
        )

    def _convert_messages(
        self,
        messages: List[VisionMessage],
        config: VisionLLMConfig
    ) -> List[Dict[str, Any]]:
        """Convert VisionMessage to OpenAI message format."""
        openai_messages = []

        for msg in messages:
            content = []

            # Add text content
            if msg.content:
                content.append({
                    "type": "text",
                    "text": msg.content
                })

            # Add images
            if msg.images:
                for img in msg.images:
                    # Validate image
                    validation = self.validate_image(img)
                    if not validation.valid:
                        logger.warning(f"Skipping invalid image: {validation.reason}")
                        continue

                    # Encode to base64
                    b64_image = base64.b64encode(img.image_bytes).decode("utf-8")

                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img.mime_type};base64,{b64_image}",
                            "detail": config.detail,
                        }
                    })

            openai_messages.append({
                "role": msg.role,
                "content": content if len(content) > 1 or msg.images else msg.content,
            })

        return openai_messages

    def _estimate_image_tokens(
        self,
        messages: List[VisionMessage],
        config: VisionLLMConfig
    ) -> int:
        """Estimate tokens used by images."""
        total_tokens = 0

        for msg in messages:
            if not msg.images:
                continue

            for img in msg.images:
                if config.detail == "low":
                    total_tokens += self.IMAGE_TOKENS_LOW
                else:
                    # High detail: base + tiles
                    # Simplified estimation without actual image dimensions
                    total_tokens += self.IMAGE_TOKENS_HIGH_BASE + (4 * self.IMAGE_TOKENS_PER_TILE)

        return total_tokens

    def _extract_structured_data(
        self,
        content: str,
        task: VisionTask
    ) -> Optional[Dict[str, Any]]:
        """
        Extract structured data from Vision LLM response.

        For complex extraction, this would use additional parsing.
        Currently returns None - structured extraction is handled
        by StructuredDataExtractor service.
        """
        # Placeholder for future structured extraction
        # Real implementation would parse JSON/tables from content
        return None
