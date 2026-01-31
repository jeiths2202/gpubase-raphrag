"""
MiniCPM-V Vision Adapter

Implementation of VisionLLMPort for MiniCPM-V 2.6 via vLLM.
Provides local Vision LLM capabilities for PDF/image analysis.
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


class MiniCPMVisionAdapter(VisionLLMPort):
    """
    MiniCPM-V 2.6 Vision LLM Adapter via vLLM

    Local Vision LLM implementation supporting:
    - PDF page image analysis
    - Table/chart extraction
    - OCR text recognition
    - Multi-language support (Korean, Japanese, English)

    Configuration:
        - Model: openbmb/MiniCPM-V-2_6
        - GPU: Device 5, 6 (Tensor Parallel)
        - Port: 12803
        - Max Context: 4096 tokens
    """

    # Local models have no per-token cost
    PRICING = {
        "openbmb/MiniCPM-V-2_6": {
            "input": 0.0,
            "output": 0.0,
            "image_base": 0.0,
        },
        "Qwen/Qwen2-VL-2B-Instruct": {
            "input": 0.0,
            "output": 0.0,
            "image_base": 0.0,
        },
    }

    # Image token estimation for MiniCPM-V
    # MiniCPM-V uses dynamic resolution, roughly 1000-2000 tokens per image
    IMAGE_TOKENS_ESTIMATE = 1500

    # Limits
    MAX_IMAGES_PER_REQUEST = 5  # MiniCPM-V context limit
    MAX_IMAGE_DIMENSION = 1344  # MiniCPM-V optimal size
    MAX_CONTEXT_TOKENS = 4096
    SUPPORTED_FORMATS = {"image/png", "image/jpeg", "image/gif", "image/webp"}

    def __init__(
        self,
        base_url: str = "http://192.168.8.11:12803/v1",
        model: str = "openbmb/MiniCPM-V-2_6",
        max_retries: int = 3,
        timeout: int = 180,
        max_tokens: int = 2048,
    ):
        """
        Initialize MiniCPM-V adapter.

        Args:
            base_url: vLLM server URL (default: 192.168.8.11:12803)
            model: Model name
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds (longer for vision)
            max_tokens: Maximum output tokens
        """
        self.client = AsyncOpenAI(
            api_key="EMPTY",  # vLLM doesn't require API key
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
        )
        self.base_url = base_url
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self.default_max_tokens = max_tokens

    async def generate(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> VisionResponse:
        """Generate a response from MiniCPM-V."""
        config = config or VisionLLMConfig()
        start_time = time.time()

        # Convert messages to OpenAI format
        openai_messages = self._convert_messages(messages, config)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                max_tokens=min(config.max_tokens, self.default_max_tokens),
                temperature=config.temperature,
            )

            latency_ms = (time.time() - start_time) * 1000

            # Estimate image tokens
            image_tokens = self._estimate_image_tokens(messages)

            return VisionResponse(
                content=response.choices[0].message.content or "",
                model=self.model,
                usage=VisionTokenUsage(
                    prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                    completion_tokens=response.usage.completion_tokens if response.usage else 0,
                    image_tokens=image_tokens,
                ),
                confidence=0.85,  # Local model confidence
                latency_ms=latency_ms,
                finish_reason=response.choices[0].finish_reason or "stop",
            )

        except Exception as e:
            logger.error(f"MiniCPM-V API error: {e}")
            raise

    async def generate_stream(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> AsyncGenerator[VisionStreamChunk, None]:
        """Generate a streaming response from MiniCPM-V."""
        config = config or VisionLLMConfig()

        # Convert messages to OpenAI format
        openai_messages = self._convert_messages(messages, config)

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                max_tokens=min(config.max_tokens, self.default_max_tokens),
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
            logger.error(f"MiniCPM-V streaming error: {e}")
            raise

    async def analyze_image(
        self,
        image: ImageContent,
        task: VisionTask,
        context: Optional[str] = None,
        language: str = "ja"
    ) -> VisionAnalysisResult:
        """Analyze a single image for a specific task.

        Args:
            image: Image content to analyze
            task: Vision task type
            context: Optional context/question
            language: Language for response ("ja", "ko", "en"). Default "ja".
        """
        start_time = time.time()

        # Build prompt based on task with multilingual support
        prompt = self._build_task_prompt(task, context, language)

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
            confidence=0.85,
            processing_time_ms=processing_time,
        )

    async def analyze_images_batch(
        self,
        images: List[ImageContent],
        task: VisionTask,
        context: Optional[str] = None,
        language: str = "ja"
    ) -> List[VisionAnalysisResult]:
        """Analyze multiple images for the same task.

        Args:
            images: List of image contents
            task: Vision task type
            context: Optional context
            language: Language for response ("ja", "ko", "en"). Default "ja".
        """
        # Process sequentially due to context limits
        results = []

        for img in images:
            try:
                result = await self.analyze_image(img, task, context, language)
                results.append(result)
            except Exception as e:
                logger.error(f"Image analysis error: {e}")
                results.append(VisionAnalysisResult(
                    task=task,
                    content=f"Error: {str(e)}",
                    confidence=0.0,
                ))

            # Small delay to avoid overwhelming the GPU
            await asyncio.sleep(0.5)

        return results

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """
        Generate text-only response (no images).

        Used for consolidation and summarization tasks.

        Args:
            prompt: Text prompt
            max_tokens: Maximum output tokens
            temperature: Generation temperature

        Returns:
            Generated text
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=min(max_tokens, self.default_max_tokens),
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"MiniCPM-V text generation error: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if MiniCPM-V vLLM server is available."""
        try:
            response = await self.client.models.list()
            models = [m.id for m in response.data]
            return self.model in models or len(models) > 0
        except Exception as e:
            logger.error(f"MiniCPM-V health check failed: {e}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about MiniCPM-V model."""
        return {
            "provider": "vllm",
            "model": self.model,
            "base_url": self.base_url,
            "capabilities": [
                "image_understanding",
                "text_extraction",
                "table_extraction",
                "chart_analysis",
                "diagram_analysis",
                "multilingual",  # Korean, Japanese, English
                "streaming",
            ],
            "limits": {
                "max_images_per_request": self.MAX_IMAGES_PER_REQUEST,
                "max_image_dimension": self.MAX_IMAGE_DIMENSION,
                "max_context_tokens": self.MAX_CONTEXT_TOKENS,
                "supported_formats": list(self.SUPPORTED_FORMATS),
            },
            "pricing": self.PRICING.get(self.model, {"input": 0, "output": 0}),
            "gpu_config": {
                "devices": [5, 6],
                "tensor_parallel": True,
            },
        }

    def estimate_cost(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> float:
        """Estimate cost (always 0 for local model)."""
        return 0.0

    def validate_image(self, image: ImageContent) -> ImageValidationResult:
        """Validate an image before sending to MiniCPM-V."""
        # Check MIME type
        if image.mime_type not in self.SUPPORTED_FORMATS:
            return ImageValidationResult(
                valid=False,
                reason=f"Unsupported format: {image.mime_type}",
                mime_type=image.mime_type,
            )

        # Check file size (10MB limit for local processing)
        file_size = len(image.image_bytes)
        if file_size > 10 * 1024 * 1024:
            return ImageValidationResult(
                valid=False,
                reason=f"Image too large: {file_size / 1024 / 1024:.1f}MB (max 10MB)",
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
        """Convert VisionMessage to OpenAI-compatible format for vLLM."""
        openai_messages = []

        for msg in messages:
            content = []

            # Add images first (MiniCPM-V prefers images before text)
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
                        }
                    })

            # Add text content
            if msg.content:
                content.append({
                    "type": "text",
                    "text": msg.content
                })

            openai_messages.append({
                "role": msg.role,
                "content": content if content else msg.content,
            })

        return openai_messages

    def _estimate_image_tokens(self, messages: List[VisionMessage]) -> int:
        """Estimate tokens used by images."""
        total_images = sum(
            len(msg.images) if msg.images else 0
            for msg in messages
        )
        return total_images * self.IMAGE_TOKENS_ESTIMATE

    def _build_task_prompt(
        self,
        task: VisionTask,
        context: Optional[str] = None,
        language: str = "auto"
    ) -> str:
        """Build task-specific prompt with multilingual instructions.

        Note: MiniCPM-V with vLLM tends to generate short responses for Japanese prompts.
        Adding detailed instructions suffix helps generate comprehensive responses.
        """
        # Japanese prompts with detailed instructions (fixes early EOS issue)
        task_prompts_ja = {
            VisionTask.DESCRIBE: """この画像の内容を詳しく説明してください。
- 主要な内容と構造
- テキストがあれば全て読んでください
- 表、チャート、ダイアグラムがあれば説明してください

詳細に、できるだけ長く説明してください。箇条書きで整理してください。""",

            VisionTask.EXTRACT_TEXT: """この画像から全てのテキストを抽出してください。
- 元のフォーマットと構造を維持してください
- ヘッダー、ラベル、キャプションを含めてください
- 不明瞭なテキストは[不明瞭]と表示してください

全ての情報を漏れなく記載してください。""",

            VisionTask.ANALYZE_CHART: """このチャート/グラフを分析してください。
- チャートタイプ（棒、線、円など）
- タイトルと軸ラベル
- 全てのデータポイントと値
- 主要なトレンドとインサイト
- 凡例情報

Markdown表形式でデータを整理してください。詳細に説明してください。""",

            VisionTask.ANALYZE_DIAGRAM: """このダイアグラムを分析してください。
- ダイアグラムタイプ（フローチャート、シーケンス、アーキテクチャなど）
- 全てのノード/要素とラベル
- 要素間の接続と関係
- フロー方向とロジック
- 注釈やメモ

構造化された形式で詳しく説明してください。""",

            VisionTask.EXTRACT_TABLE: """この画像から表データを抽出してください。
- 全ての列ヘッダーを識別
- 全ての行データを抽出
- 表構造を維持
- 結合セルや特殊フォーマットを表示

Markdown表形式で出力してください。全ての情報を漏れなく記載してください。""",

            VisionTask.ANSWER_QUESTION: """画像を参照して以下の質問に答えてください。
関連する視覚的要素を具体的に言及してください。
詳細に、できるだけ長く説明してください。""",
        }

        # Korean prompts
        task_prompts_ko = {
            VisionTask.DESCRIBE: """이 이미지의 내용을 상세히 설명해주세요.
- 주요 내용과 구조
- 텍스트가 있다면 모두 읽어주세요
- 표, 차트, 다이어그램이 있다면 설명해주세요

상세하게, 가능한 길게 설명해주세요. 목록 형식으로 정리해주세요.""",

            VisionTask.EXTRACT_TEXT: """이 이미지에서 모든 텍스트를 추출해주세요.
- 원본 형식과 구조를 유지해주세요
- 헤더, 라벨, 캡션을 포함해주세요
- 불분명한 텍스트는 [불분명]으로 표시해주세요

모든 정보를 빠짐없이 기재해주세요.""",

            VisionTask.ANALYZE_CHART: """이 차트/그래프를 분석해주세요.
- 차트 유형 (막대, 선, 원형 등)
- 제목과 축 라벨
- 모든 데이터 포인트와 값
- 주요 트렌드와 인사이트
- 범례 정보

Markdown 표 형식으로 데이터를 정리해주세요. 상세하게 설명해주세요.""",

            VisionTask.ANALYZE_DIAGRAM: """이 다이어그램을 분석해주세요.
- 다이어그램 유형 (플로우차트, 시퀀스, 아키텍처 등)
- 모든 노드/요소와 라벨
- 요소 간 연결과 관계
- 흐름 방향과 로직
- 주석이나 메모

구조화된 형식으로 상세하게 설명해주세요.""",

            VisionTask.EXTRACT_TABLE: """이 이미지에서 표 데이터를 추출해주세요.
- 모든 열 헤더를 식별
- 모든 행 데이터를 추출
- 표 구조를 유지
- 병합된 셀이나 특수 형식을 표시

Markdown 표 형식으로 출력해주세요. 모든 정보를 빠짐없이 기재해주세요.""",

            VisionTask.ANSWER_QUESTION: """이미지를 참고하여 다음 질문에 답변해주세요.
관련 시각적 요소를 구체적으로 언급해주세요.
상세하게, 가능한 길게 설명해주세요.""",
        }

        # Select prompt based on language
        if language == "ja":
            task_prompts = task_prompts_ja
        elif language == "ko":
            task_prompts = task_prompts_ko
        else:
            # Default to Japanese for Japanese documents
            task_prompts = task_prompts_ja

        prompt = task_prompts.get(task, VISION_TASK_PROMPTS.get(task, "この画像を説明してください。詳細に説明してください。"))

        if context:
            if task == VisionTask.ANSWER_QUESTION:
                prompt = f"{prompt}\n\n質問: {context}" if language == "ja" else f"{prompt}\n\n질문: {context}"
            else:
                prompt = f"{prompt}\n\n追加コンテキスト: {context}" if language == "ja" else f"{prompt}\n\n추가 컨텍스트: {context}"

        return prompt

    def _extract_structured_data(
        self,
        content: str,
        task: VisionTask
    ) -> Optional[Dict[str, Any]]:
        """Extract structured data from response."""
        # Parse markdown tables if present
        if task == VisionTask.EXTRACT_TABLE and "|" in content:
            return {"has_table": True, "raw_content": content}

        if task == VisionTask.ANALYZE_CHART and any(kw in content.lower() for kw in ["데이터", "값", "data", "value"]):
            return {"has_data": True, "raw_content": content}

        return None


# Convenience function for creating adapter
def create_minicpm_adapter(
    base_url: str = "http://192.168.8.11:12803/v1",
    model: str = "openbmb/MiniCPM-V-2_6",
    **kwargs
) -> MiniCPMVisionAdapter:
    """Create MiniCPM-V adapter with default settings."""
    return MiniCPMVisionAdapter(
        base_url=base_url,
        model=model,
        **kwargs
    )
