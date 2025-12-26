"""
Vision Pipeline Orchestrator

Orchestrates the complete Vision LLM processing pipeline:
1. Image extraction and preprocessing
2. Vision LLM processing
3. Result integration and normalization

Integrates with the existing RAG pipeline for hybrid text+vision queries.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from app.api.models.vision import (
    ChartData,
    DiagramStructure,
    DocumentVisionResult,
    DocumentVisualProfile,
    ImageAnalysisResult,
    ProcessedImage,
    RoutingDecision,
    TableData,
    UnifiedQueryResponse,
    VisualAnalysis,
    RoutingInfo,
    SourceInfo,
    ResponseMetadata,
)
from app.api.ports.vision_llm_port import (
    ImageContent,
    VisionLLMConfig,
    VisionLLMPort,
    VisionMessage,
    VisionResponse,
    VisionTask,
)
from app.api.services.document_analyzer import DocumentAnalyzer
from app.api.services.image_preprocessor import ImagePreprocessor
from app.api.services.vision_cache import VisionCacheService, hash_content
from app.api.services.vision_router import VisionAwareRouter

logger = logging.getLogger(__name__)


@dataclass
class VisionPipelineConfig:
    """Configuration for Vision pipeline"""
    # Image processing
    max_images_per_request: int = 20
    max_image_dimension: int = 2048
    default_image_format: str = "PNG"
    pdf_dpi: int = 150

    # Vision LLM
    default_task: VisionTask = VisionTask.DESCRIBE
    max_tokens: int = 4096
    temperature: float = 0.7

    # Performance
    batch_size: int = 5
    timeout: int = 60
    enable_cache: bool = True

    # Cost control
    max_cost_per_request: float = 0.50


@dataclass
class VisionQueryRequest:
    """Request for Vision-enhanced query"""
    query: str
    language: str = "auto"

    # Document context
    document_ids: List[str] = field(default_factory=list)
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)

    # Visual content
    images: List[bytes] = field(default_factory=list)
    image_paths: List[Path] = field(default_factory=list)

    # Options
    force_vision: bool = False
    include_extracted_data: bool = True
    stream: bool = False


class VisionPipelineOrchestrator:
    """
    Orchestrates Vision LLM processing pipeline.

    Coordinates:
    - Document analysis and image extraction
    - Vision LLM calls (primary and fallback)
    - Result caching and normalization
    - Integration with text-based RAG

    Usage:
        # Initialize with Vision LLM adapter
        orchestrator = VisionPipelineOrchestrator(
            vision_llm=OpenAIVisionAdapter(api_key="..."),
            config=VisionPipelineConfig()
        )

        # Process a visual query
        response = await orchestrator.process_query(
            request=VisionQueryRequest(
                query="이 차트의 트렌드를 분석해주세요",
                document_ids=["doc1", "doc2"]
            )
        )
    """

    def __init__(
        self,
        vision_llm: VisionLLMPort,
        fallback_llm: Optional[VisionLLMPort] = None,
        preprocessor: Optional[ImagePreprocessor] = None,
        analyzer: Optional[DocumentAnalyzer] = None,
        router: Optional[VisionAwareRouter] = None,
        cache: Optional[VisionCacheService] = None,
        config: Optional[VisionPipelineConfig] = None,
    ):
        """
        Initialize Vision pipeline.

        Args:
            vision_llm: Primary Vision LLM adapter
            fallback_llm: Fallback Vision LLM (optional)
            preprocessor: Image preprocessor
            analyzer: Document analyzer
            router: Vision-aware router
            cache: Vision cache service
            config: Pipeline configuration
        """
        self.vision_llm = vision_llm
        self.fallback_llm = fallback_llm
        self.preprocessor = preprocessor or ImagePreprocessor()
        self.analyzer = analyzer or DocumentAnalyzer()
        self.router = router or VisionAwareRouter()
        self.cache = cache or VisionCacheService()
        self.config = config or VisionPipelineConfig()

    async def process_query(
        self,
        request: VisionQueryRequest,
    ) -> UnifiedQueryResponse:
        """
        Process a Vision-enhanced query.

        This is the main entry point for visual queries.

        Args:
            request: Vision query request

        Returns:
            UnifiedQueryResponse with answer and visual analysis
        """
        start_time = time.time()

        try:
            # Step 1: Collect and preprocess images
            images = await self._collect_images(request)

            if not images:
                # No visual content, return text-only placeholder
                return self._create_text_only_response(
                    request.query,
                    "No visual content available for analysis"
                )

            # Step 2: Check cache
            if self.config.enable_cache:
                cached = await self._check_cache(request, images)
                if cached:
                    return cached

            # Step 3: Build Vision LLM messages
            messages = self._build_vision_messages(
                request.query,
                images,
                request.language
            )

            # Step 4: Call Vision LLM
            vision_response = await self._call_vision_llm(messages)

            # Step 5: Extract structured data if requested
            visual_analysis = None
            if request.include_extracted_data:
                visual_analysis = await self._extract_visual_analysis(
                    images,
                    vision_response
                )

            # Step 6: Build unified response
            latency_ms = (time.time() - start_time) * 1000

            response = UnifiedQueryResponse(
                answer=vision_response.content,
                confidence=0.9,
                routing=RoutingInfo(
                    selected_llm="vision",
                    reasoning="Visual content detected",
                    query_type="hybrid",
                    visual_signals_detected=True,
                ),
                sources=self._build_sources(request.retrieved_chunks),
                visual_analysis=visual_analysis,
                metadata=ResponseMetadata(
                    total_tokens=vision_response.usage.total_tokens,
                    latency_ms=latency_ms,
                    model_used=vision_response.model,
                    vision_model_used=vision_response.model,
                    cache_hit=False,
                ),
            )

            # Step 7: Cache response
            if self.config.enable_cache:
                await self._cache_response(request, images, response)

            return response

        except Exception as e:
            logger.error(f"Vision pipeline error: {e}")
            return self._create_error_response(request.query, str(e))

    async def process_query_stream(
        self,
        request: VisionQueryRequest,
    ) -> AsyncGenerator[str, None]:
        """
        Process query with streaming response.

        Yields:
            Chunks of the response text
        """
        # Collect images
        images = await self._collect_images(request)

        if not images:
            yield "No visual content available for analysis."
            return

        # Build messages
        messages = self._build_vision_messages(
            request.query,
            images,
            request.language
        )

        # Stream from Vision LLM
        try:
            async for chunk in self.vision_llm.generate_stream(messages):
                yield chunk.content
        except Exception as e:
            logger.error(f"Vision streaming error: {e}")
            yield f"\n\nError: {str(e)}"

    async def analyze_document(
        self,
        document_path: Path,
        tasks: Optional[List[VisionTask]] = None,
    ) -> DocumentVisionResult:
        """
        Analyze a document with Vision LLM.

        Performs complete visual analysis including:
        - Page rendering and image extraction
        - Visual element detection
        - Chart/table/diagram extraction

        Args:
            document_path: Path to the document
            tasks: Analysis tasks to perform

        Returns:
            DocumentVisionResult with all extracted data
        """
        start_time = time.time()
        tasks = tasks or [VisionTask.DESCRIBE]

        # Step 1: Analyze document profile
        profile = await self.analyzer.analyze(document_path)

        # Step 2: Extract images from document
        extracted_images = []
        if profile.mime_type == "application/pdf":
            extracted_images = await self.preprocessor.extract_from_pdf(
                document_path,
                dpi=self.config.pdf_dpi
            )
        elif profile.is_pure_image:
            with open(document_path, "rb") as f:
                image_bytes = f.read()
            processed = await self.preprocessor.preprocess(image_bytes)
            extracted_images = [processed]

        # Step 3: Analyze each image
        analysis_results = []
        charts = []
        tables = []
        diagrams = []
        all_text = []

        for i, image in enumerate(extracted_images):
            for task in tasks:
                result = await self._analyze_single_image(
                    image,
                    task,
                    f"image_{i}"
                )
                analysis_results.append(result)

                # Collect extracted text
                if result.extracted_text:
                    all_text.append(result.extracted_text)

                # Collect structured data
                if result.extracted_data:
                    if "chart" in task.value:
                        charts.append(self._parse_chart_data(result.extracted_data))
                    elif "table" in task.value:
                        tables.append(self._parse_table_data(result.extracted_data))
                    elif "diagram" in task.value:
                        diagrams.append(self._parse_diagram_data(result.extracted_data))

        processing_time = (time.time() - start_time) * 1000

        return DocumentVisionResult(
            document_id=str(document_path),
            visual_profile=profile,
            extracted_images=extracted_images,
            analysis_results=analysis_results,
            all_extracted_text="\n\n".join(all_text),
            charts=charts,
            tables=tables,
            diagrams=diagrams,
            processing_time_ms=processing_time,
            vision_model_used=self.vision_llm.get_model_info()["model"],
        )

    async def answer_with_images(
        self,
        query: str,
        images: List[bytes],
        context: Optional[str] = None,
        language: str = "auto",
    ) -> VisionResponse:
        """
        Answer a question using provided images.

        Simplified interface for direct image-based Q&A.

        Args:
            query: User question
            images: List of image bytes
            context: Optional text context
            language: Language hint

        Returns:
            VisionResponse with answer
        """
        # Preprocess images
        processed_images = []
        for img_bytes in images:
            processed = await self.preprocessor.preprocess(img_bytes)
            processed_images.append(processed)

        # Convert to ImageContent
        image_contents = [
            ImageContent(
                image_bytes=img.image_bytes,
                mime_type=img.mime_type
            )
            for img in processed_images
        ]

        # Build message
        prompt = self._build_qa_prompt(query, context, language)
        messages = [
            VisionMessage(
                role="user",
                content=prompt,
                images=image_contents
            )
        ]

        return await self._call_vision_llm(messages)

    async def _collect_images(
        self,
        request: VisionQueryRequest,
    ) -> List[ProcessedImage]:
        """Collect and preprocess all images for the request."""
        images = []

        # From direct image bytes
        for img_bytes in request.images:
            try:
                processed = await self.preprocessor.preprocess(img_bytes)
                images.append(processed)
            except Exception as e:
                logger.warning(f"Failed to preprocess image: {e}")

        # From image paths
        for path in request.image_paths:
            try:
                with open(path, "rb") as f:
                    img_bytes = f.read()
                processed = await self.preprocessor.preprocess(img_bytes)
                images.append(processed)
            except Exception as e:
                logger.warning(f"Failed to load image {path}: {e}")

        # Limit number of images
        if len(images) > self.config.max_images_per_request:
            logger.warning(
                f"Too many images ({len(images)}), "
                f"limiting to {self.config.max_images_per_request}"
            )
            images = images[:self.config.max_images_per_request]

        return images

    def _build_vision_messages(
        self,
        query: str,
        images: List[ProcessedImage],
        language: str,
    ) -> List[VisionMessage]:
        """Build messages for Vision LLM."""
        # System prompt
        system_prompt = self._get_system_prompt(language)

        # Convert images to ImageContent
        image_contents = [
            ImageContent(
                image_bytes=img.image_bytes,
                mime_type=img.mime_type,
                description=f"Page {img.page_number}" if img.page_number else None
            )
            for img in images
        ]

        return [
            VisionMessage(role="system", content=system_prompt),
            VisionMessage(
                role="user",
                content=query,
                images=image_contents
            )
        ]

    def _get_system_prompt(self, language: str) -> str:
        """Get system prompt based on language."""
        if language == "ko":
            return """당신은 이미지와 문서를 분석하는 전문가입니다.
차트를 분석할 때는 구체적인 데이터 포인트와 트렌드를 추출하세요.
다이어그램을 분석할 때는 구조와 관계를 설명하세요.
항상 보이는 것에 기반하여 정확하고 상세한 설명을 제공하세요.
확실하지 않은 것이 있다면 그렇게 말씀하세요."""

        elif language == "ja":
            return """あなたは画像とドキュメントを分析する専門家です。
チャートを分析する際は、具体的なデータポイントとトレンドを抽出してください。
ダイアグラムを分析する際は、構造と関係を説明してください。
常に見えるものに基づいて正確で詳細な説明を提供してください。
不確かなことがあれば、そう言ってください。"""

        else:
            return """You are an expert at analyzing images and documents.
When analyzing charts, extract specific data points and trends.
When analyzing diagrams, describe the structure and relationships.
Always provide accurate, detailed descriptions based on what you see.
If you're uncertain about something, say so."""

    async def _call_vision_llm(
        self,
        messages: List[VisionMessage],
    ) -> VisionResponse:
        """Call Vision LLM with fallback support."""
        config = VisionLLMConfig(
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            timeout=self.config.timeout,
        )

        try:
            return await self.vision_llm.generate(messages, config)
        except Exception as e:
            logger.warning(f"Primary Vision LLM failed: {e}")

            if self.fallback_llm:
                logger.info("Trying fallback Vision LLM")
                return await self.fallback_llm.generate(messages, config)

            raise

    async def _analyze_single_image(
        self,
        image: ProcessedImage,
        task: VisionTask,
        image_id: str,
    ) -> ImageAnalysisResult:
        """Analyze a single image."""
        start_time = time.time()

        image_content = ImageContent(
            image_bytes=image.image_bytes,
            mime_type=image.mime_type
        )

        result = await self.vision_llm.analyze_image(
            image_content,
            task
        )

        return ImageAnalysisResult(
            image_id=image_id,
            page_number=image.page_number,
            description=result.content,
            extracted_text=result.content if task == VisionTask.EXTRACT_TEXT else None,
            extracted_data=result.extracted_data,
            confidence=result.confidence,
            processing_time_ms=(time.time() - start_time) * 1000,
        )

    async def _extract_visual_analysis(
        self,
        images: List[ProcessedImage],
        vision_response: VisionResponse,
    ) -> VisualAnalysis:
        """Extract visual analysis from response."""
        # Build analysis results for each image
        analysis_results = [
            ImageAnalysisResult(
                image_id=f"image_{i}",
                page_number=img.page_number,
                description="Analyzed as part of query response",
                confidence=0.9,
            )
            for i, img in enumerate(images)
        ]

        return VisualAnalysis(
            analyzed_images=analysis_results,
            extracted_data={},  # Could parse structured data from response
            visual_summary=vision_response.content[:500] + "..." if len(vision_response.content) > 500 else vision_response.content,
        )

    def _build_sources(
        self,
        chunks: List[Dict[str, Any]],
    ) -> List[SourceInfo]:
        """Build source information from chunks."""
        return [
            SourceInfo(
                document_id=chunk.get("document_id", ""),
                filename=chunk.get("filename", ""),
                page_number=chunk.get("page"),
                chunk_text=chunk.get("content", "")[:200],
                relevance_score=chunk.get("score", 0.0),
                has_visual_content=chunk.get("has_visual", False),
            )
            for chunk in chunks
        ]

    def _build_qa_prompt(
        self,
        query: str,
        context: Optional[str],
        language: str,
    ) -> str:
        """Build Q&A prompt."""
        if language == "ko":
            prompt = f"다음 이미지를 보고 질문에 답해주세요.\n\n질문: {query}"
            if context:
                prompt = f"맥락: {context}\n\n{prompt}"
        else:
            prompt = f"Please look at the image(s) and answer the following question.\n\nQuestion: {query}"
            if context:
                prompt = f"Context: {context}\n\n{prompt}"

        return prompt

    async def _check_cache(
        self,
        request: VisionQueryRequest,
        images: List[ProcessedImage],
    ) -> Optional[UnifiedQueryResponse]:
        """Check cache for existing response."""
        # Build cache key from query and image hashes
        image_hashes = [hash_content(img.image_bytes) for img in images]
        query_hash = hash_content(request.query.encode())
        context_hash = hash_content(":".join(image_hashes).encode())

        return await self.cache.get_query_response(query_hash, context_hash)

    async def _cache_response(
        self,
        request: VisionQueryRequest,
        images: List[ProcessedImage],
        response: UnifiedQueryResponse,
    ) -> None:
        """Cache the response."""
        image_hashes = [hash_content(img.image_bytes) for img in images]
        query_hash = hash_content(request.query.encode())
        context_hash = hash_content(":".join(image_hashes).encode())

        await self.cache.cache_query_response(query_hash, context_hash, response)

    def _create_text_only_response(
        self,
        query: str,
        message: str,
    ) -> UnifiedQueryResponse:
        """Create response for text-only queries."""
        return UnifiedQueryResponse(
            answer=message,
            confidence=0.5,
            routing=RoutingInfo(
                selected_llm="text",
                reasoning="No visual content",
                query_type="vector",
                visual_signals_detected=False,
            ),
            sources=[],
            metadata=ResponseMetadata(
                total_tokens=0,
                latency_ms=0,
                model_used="none",
                cache_hit=False,
            ),
        )

    def _create_error_response(
        self,
        query: str,
        error: str,
    ) -> UnifiedQueryResponse:
        """Create error response."""
        return UnifiedQueryResponse(
            answer=f"Error processing visual query: {error}",
            confidence=0.0,
            routing=RoutingInfo(
                selected_llm="vision",
                reasoning=f"Error: {error}",
                query_type="hybrid",
                visual_signals_detected=True,
            ),
            sources=[],
            metadata=ResponseMetadata(
                total_tokens=0,
                latency_ms=0,
                model_used="error",
                cache_hit=False,
            ),
        )

    def _parse_chart_data(self, data: Dict) -> ChartData:
        """Parse chart data from extracted data."""
        return ChartData(
            chart_type=data.get("type", "unknown"),
            title=data.get("title"),
            data_points=[],
        )

    def _parse_table_data(self, data: Dict) -> TableData:
        """Parse table data from extracted data."""
        return TableData(
            headers=data.get("headers", []),
            rows=data.get("rows", []),
            title=data.get("title"),
        )

    def _parse_diagram_data(self, data: Dict) -> DiagramStructure:
        """Parse diagram data from extracted data."""
        return DiagramStructure(
            diagram_type=data.get("type", "unknown"),
            title=data.get("title"),
        )

    def get_pipeline_info(self) -> Dict[str, Any]:
        """Get pipeline information."""
        return {
            "vision_llm": self.vision_llm.get_model_info(),
            "fallback_llm": self.fallback_llm.get_model_info() if self.fallback_llm else None,
            "config": {
                "max_images": self.config.max_images_per_request,
                "max_dimension": self.config.max_image_dimension,
                "cache_enabled": self.config.enable_cache,
            },
        }
