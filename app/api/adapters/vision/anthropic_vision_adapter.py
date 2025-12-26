"""
Anthropic Vision Adapter

Implementation of VisionLLMPort for Claude 3 Vision models.
Used as fallback when OpenAI Vision is unavailable.
"""

import asyncio
import base64
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from anthropic import AsyncAnthropic

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


class AnthropicVisionAdapter(VisionLLMPort):
    """
    Anthropic Vision LLM Adapter (Claude 3 Vision)

    Fallback Vision LLM implementation supporting:
    - Claude 3.5 Sonnet, Claude 3 Opus, Claude 3 Haiku
    - Multi-image analysis
    - Streaming responses
    """

    # Pricing (USD per token, as of 2025)
    PRICING = {
        "claude-3-5-sonnet-20241022": {
            "input": 0.003 / 1000,
            "output": 0.015 / 1000,
            "image_base": 0.0048,  # Varies by image size
        },
        "claude-3-opus-20240229": {
            "input": 0.015 / 1000,
            "output": 0.075 / 1000,
            "image_base": 0.024,
        },
        "claude-3-haiku-20240307": {
            "input": 0.00025 / 1000,
            "output": 0.00125 / 1000,
            "image_base": 0.0004,
        },
    }

    # Limits
    MAX_IMAGES_PER_REQUEST = 20
    MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB
    SUPPORTED_FORMATS = {"image/png", "image/jpeg", "image/gif", "image/webp"}

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        max_retries: int = 3,
        timeout: int = 60,
    ):
        """
        Initialize Anthropic Vision adapter.

        Args:
            api_key: Anthropic API key
            model: Model name (claude-3-5-sonnet, claude-3-opus, claude-3-haiku)
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds
        """
        self.client = AsyncAnthropic(
            api_key=api_key,
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
        """Generate a response from Claude Vision."""
        config = config or VisionLLMConfig()
        start_time = time.time()

        # Extract system message and convert messages
        system_prompt, anthropic_messages = self._convert_messages(messages, config)

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=config.max_tokens,
                system=system_prompt,
                messages=anthropic_messages,
            )

            latency_ms = (time.time() - start_time) * 1000

            # Extract text content
            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            return VisionResponse(
                content=content,
                model=self.model,
                usage=VisionTokenUsage(
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    image_tokens=0,  # Anthropic includes images in input tokens
                ),
                confidence=1.0,
                latency_ms=latency_ms,
                finish_reason=response.stop_reason or "end_turn",
            )

        except Exception as e:
            logger.error(f"Anthropic Vision API error: {e}")
            raise

    async def generate_stream(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> AsyncGenerator[VisionStreamChunk, None]:
        """Generate a streaming response from Claude Vision."""
        config = config or VisionLLMConfig()

        # Extract system message and convert messages
        system_prompt, anthropic_messages = self._convert_messages(messages, config)

        try:
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=config.max_tokens,
                system=system_prompt,
                messages=anthropic_messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield VisionStreamChunk(
                        content=text,
                        is_final=False,
                    )

                # Final chunk
                yield VisionStreamChunk(
                    content="",
                    is_final=True,
                )

        except Exception as e:
            logger.error(f"Anthropic Vision streaming error: {e}")
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

        return VisionAnalysisResult(
            task=task,
            content=response.content,
            extracted_data=None,
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
        batch_size = 5
        results = []

        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]

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
        """Check if Anthropic Vision API is available."""
        try:
            # Simple message to check connectivity
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hello"}],
            )
            return len(response.content) > 0
        except Exception as e:
            logger.error(f"Anthropic Vision health check failed: {e}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the Vision model."""
        return {
            "provider": "anthropic",
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
                "max_image_size_bytes": self.MAX_IMAGE_SIZE_BYTES,
                "supported_formats": list(self.SUPPORTED_FORMATS),
            },
            "pricing": self.PRICING.get(self.model, self.PRICING["claude-3-5-sonnet-20241022"]),
        }

    def estimate_cost(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> float:
        """Estimate the cost of a Vision LLM call."""
        config = config or VisionLLMConfig()
        pricing = self.PRICING.get(self.model, self.PRICING["claude-3-5-sonnet-20241022"])

        # Estimate text tokens
        text_tokens = sum(len(msg.content) // 4 for msg in messages)
        text_cost = text_tokens * pricing["input"]

        # Estimate image cost
        image_count = sum(
            len(msg.images) if msg.images else 0
            for msg in messages
        )
        image_cost = image_count * pricing["image_base"]

        # Estimate output tokens
        output_tokens = config.max_tokens // 2
        output_cost = output_tokens * pricing["output"]

        return text_cost + image_cost + output_cost

    def validate_image(self, image: ImageContent) -> ImageValidationResult:
        """Validate an image before sending to the API."""
        if image.mime_type not in self.SUPPORTED_FORMATS:
            return ImageValidationResult(
                valid=False,
                reason=f"Unsupported format: {image.mime_type}",
                mime_type=image.mime_type,
            )

        file_size = len(image.image_bytes)
        if file_size > self.MAX_IMAGE_SIZE_BYTES:
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
    ) -> tuple:
        """
        Convert VisionMessage to Anthropic message format.

        Returns:
            Tuple of (system_prompt, messages_list)
        """
        system_prompt = ""
        anthropic_messages = []

        for msg in messages:
            # Extract system message
            if msg.role == "system":
                system_prompt = msg.content
                continue

            content = []

            # Add images first (Anthropic prefers images before text)
            if msg.images:
                for img in msg.images:
                    validation = self.validate_image(img)
                    if not validation.valid:
                        logger.warning(f"Skipping invalid image: {validation.reason}")
                        continue

                    # Encode to base64
                    b64_image = base64.b64encode(img.image_bytes).decode("utf-8")

                    # Anthropic format
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.mime_type,
                            "data": b64_image,
                        }
                    })

            # Add text content
            if msg.content:
                content.append({
                    "type": "text",
                    "text": msg.content
                })

            anthropic_messages.append({
                "role": msg.role,
                "content": content if content else msg.content,
            })

        return system_prompt, anthropic_messages
