# Vision-Capable LLM Routing System Design

**Version**: 1.0
**Created**: 2025-12-26
**Status**: AWAITING APPROVAL
**Author**: Claude (AI Assistant)

---

## Executive Summary

이 문서는 GPU-Based Enterprise RAG KMS 플랫폼에 Vision-capable LLM 라우팅 시스템을 추가하기 위한 상세 설계입니다.

### 목표
- 이미지 기반 문서(차트, 다이어그램, 스캔 PDF 등)를 자동 감지
- 문서 특성에 따라 적절한 LLM(Text-only vs Vision)으로 라우팅
- 기존 RAG 파이프라인과 원활한 통합
- 비용 효율성과 성능 최적화

### 현재 아키텍처 요약

```
현재 LLM 구성:
├── RAG LLM: Nemotron Nano 9B v2 (GPU 7, 텍스트 전용)
├── Code LLM: Mistral NeMo 12B (GPU 0, 코드 생성)
└── VLM Service: Placeholder (vlm_service.py)

기존 강점:
✅ Port 패턴 (LLMPort) - 새 LLM 타입 추가 용이
✅ Query Router - 분류 인프라 존재
✅ VLM Service - 비전 서비스 스켈레톤 존재
✅ Multimodal Embedding - CLIP + ColPali 지원
✅ Processing Modes - VLM_ENHANCED 모드 정의됨
```

---

## 1. Document Type Detection Strategy

### 1.1 Detection Layers

```
┌─────────────────────────────────────────────────────────────┐
│                   Document Detection Pipeline               │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: MIME Type & Extension                              │
│ ├── Pure Image: .png, .jpg, .gif, .bmp, .tiff, .webp       │
│ ├── Image-likely: .pptx, .pdf (needs analysis)             │
│ └── Text-only: .txt, .md, .csv, .json                      │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Content Analysis (PDF/Office 전용)                 │
│ ├── Image Ratio: (이미지 면적 / 총 페이지 면적)             │
│ ├── Text Density: (텍스트 문자 수 / 페이지 수)              │
│ ├── OCR Necessity: (추출 가능 텍스트 < 임계값)              │
│ └── Table Detection: (테이블 영역 비율)                     │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Visual Complexity Score                            │
│ ├── Chart/Graph Detection (OpenCV/ML 기반)                  │
│ ├── Diagram Detection (화살표, 박스, 연결선)                │
│ ├── Screenshot Detection (UI 요소 패턴)                     │
│ └── Handwriting Detection (필기체 패턴)                     │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Detection Criteria

```python
@dataclass
class DocumentVisualProfile:
    """문서의 시각적 특성 프로필"""

    # Layer 1: Basic Classification
    mime_type: str
    extension: str
    is_pure_image: bool              # .png, .jpg 등

    # Layer 2: Content Metrics
    total_pages: int
    image_count: int
    image_area_ratio: float          # 0.0 ~ 1.0
    text_density: float              # chars per page
    extractable_text_ratio: float    # 추출 가능 텍스트 비율
    table_count: int
    table_area_ratio: float

    # Layer 3: Visual Complexity
    has_charts: bool                 # 차트/그래프 존재
    has_diagrams: bool               # 다이어그램/플로우차트
    has_screenshots: bool            # 스크린샷/UI
    has_handwriting: bool            # 필기체
    requires_ocr: bool               # OCR 필요 여부

    # Computed Score
    visual_complexity_score: float   # 0.0 ~ 1.0

    @property
    def requires_vision_llm(self) -> bool:
        """Vision LLM 필요 여부 판단"""
        return (
            self.is_pure_image or
            self.visual_complexity_score >= 0.4 or
            self.image_area_ratio >= 0.3 or
            self.has_charts or
            self.has_diagrams or
            self.requires_ocr
        )
```

### 1.3 Detection Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| `image_area_ratio` | >= 0.30 | Vision LLM 권장 |
| `text_density` | < 100 chars/page | OCR/Vision 필요 |
| `visual_complexity_score` | >= 0.40 | Vision LLM 필수 |
| `table_area_ratio` | >= 0.20 | Table extraction 활성화 |
| `extractable_text_ratio` | < 0.50 | OCR 활성화 |

### 1.4 Implementation: DocumentAnalyzer

```python
# 새 파일: app/api/services/document_analyzer.py

class DocumentAnalyzer:
    """문서 시각적 특성 분석기"""

    async def analyze(
        self,
        file_path: Path,
        mime_type: str
    ) -> DocumentVisualProfile:
        """
        문서를 분석하여 시각적 프로필 생성

        단계:
        1. MIME 타입 기반 1차 분류
        2. PDF/Office: 페이지별 이미지/텍스트 비율 계산
        3. 이미지 영역에서 차트/다이어그램 감지
        4. Visual Complexity Score 계산
        """

    def _calculate_image_ratio(self, doc) -> float:
        """PDF/Office 문서의 이미지 면적 비율 계산"""

    def _detect_charts(self, images: List[bytes]) -> bool:
        """OpenCV 기반 차트/그래프 감지"""

    def _detect_diagrams(self, images: List[bytes]) -> bool:
        """다이어그램 패턴 감지 (화살표, 박스, 연결선)"""

    def _calculate_visual_complexity(
        self, profile: DocumentVisualProfile
    ) -> float:
        """
        Visual Complexity Score 계산 공식:

        score = (
            image_area_ratio * 0.25 +
            (1 - text_density_normalized) * 0.20 +
            has_charts * 0.20 +
            has_diagrams * 0.15 +
            has_screenshots * 0.10 +
            requires_ocr * 0.10
        )
        """
```

---

## 2. Routing Decision Logic

### 2.1 Three-Level Routing Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Routing Decision Engine                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Level 1: Document-Time Routing (업로드 시)                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Document Upload                                          ││
│  │     │                                                    ││
│  │     ▼                                                    ││
│  │ DocumentAnalyzer.analyze()                               ││
│  │     │                                                    ││
│  │     ├── visual_complexity < 0.2 → TEXT_ONLY processing  ││
│  │     ├── visual_complexity < 0.4 → VLM_ENHANCED          ││
│  │     └── visual_complexity >= 0.4 → MULTIMODAL           ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  Level 2: Query-Time Routing (질의 시)                       │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Query Received                                           ││
│  │     │                                                    ││
│  │     ▼                                                    ││
│  │ QueryVisualSignalDetector.analyze()                      ││
│  │     │                                                    ││
│  │     ├── visual_signals detected → Vision LLM            ││
│  │     ├── code_signals detected → Code LLM (Mistral)      ││
│  │     └── text_only → RAG LLM (Nemotron)                  ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  Level 3: Context-Time Routing (검색 후)                     │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Retrieved Documents                                      ││
│  │     │                                                    ││
│  │     ▼                                                    ││
│  │ ContextVisualAnalyzer.analyze()                          ││
│  │     │                                                    ││
│  │     ├── visual_docs_ratio >= 0.3 → Vision LLM           ││
│  │     └── visual_docs_ratio < 0.3 → RAG LLM               ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Query Visual Signal Detection

```python
# 확장: app/src/query_router.py

class QueryVisualSignalDetector:
    """질의에서 시각적 신호 감지"""

    # 시각적 질의 패턴 (영어)
    VISUAL_PATTERNS_EN = [
        r'\b(chart|graph|diagram|figure|image|picture|photo)\b',
        r'\b(show|display|visualize|illustrate)\b',
        r'\b(look|appear|see|visible)\b',
        r'\b(layout|design|structure|format)\b',
        r'\b(screenshot|screen\s*shot|capture)\b',
        r'\b(table|grid|matrix)\b.*\b(data|information)\b',
    ]

    # 시각적 질의 패턴 (한국어)
    VISUAL_PATTERNS_KO = [
        r'(차트|그래프|다이어그램|도표|그림|이미지|사진)',
        r'(보여|표시|시각화|그려)',
        r'(레이아웃|디자인|구조|형식)',
        r'(스크린샷|화면|캡처)',
        r'(표|테이블).*(데이터|정보)',
        r'(어떻게\s*생겼|모양|형태)',
    ]

    def detect(self, query: str, language: str = "auto") -> VisualQuerySignals:
        """
        질의에서 시각적 신호 감지

        Returns:
            VisualQuerySignals:
                is_visual_query: bool
                visual_aspects: List[str]  # ["chart", "diagram", ...]
                confidence: float
                suggested_model: str  # "vision" | "text" | "code"
        """

@dataclass
class VisualQuerySignals:
    is_visual_query: bool
    visual_aspects: List[str]
    confidence: float
    suggested_model: Literal["vision", "text", "code"]
```

### 2.3 Routing Decision Matrix

```
┌────────────────────┬─────────────────┬─────────────────┬───────────────┐
│ Query Signal       │ Document Type   │ Context Visual  │ Selected LLM  │
├────────────────────┼─────────────────┼─────────────────┼───────────────┤
│ Visual (chart등)   │ ANY             │ ANY             │ Vision LLM    │
│ Code (implement등) │ ANY             │ ANY             │ Code LLM      │
│ Text              │ Pure Image      │ -               │ Vision LLM    │
│ Text              │ VLM_ENHANCED    │ visual >= 0.3   │ Vision LLM    │
│ Text              │ VLM_ENHANCED    │ visual < 0.3    │ RAG LLM       │
│ Text              │ TEXT_ONLY       │ ANY             │ RAG LLM       │
└────────────────────┴─────────────────┴─────────────────┴───────────────┘
```

### 2.4 Implementation: VisionAwareRouter

```python
# 새 파일: app/api/services/vision_router.py

class VisionAwareRouter:
    """Vision-aware 라우팅 결정 엔진"""

    def __init__(
        self,
        query_detector: QueryVisualSignalDetector,
        document_analyzer: DocumentAnalyzer,
    ):
        self.query_detector = query_detector
        self.document_analyzer = document_analyzer

    async def route(
        self,
        query: str,
        retrieved_docs: List[Document],
        language: str = "auto"
    ) -> RoutingDecision:
        """
        라우팅 결정 수행

        Returns:
            RoutingDecision:
                selected_llm: "vision" | "text" | "code"
                reasoning: str
                confidence: float
                visual_context: Optional[List[ImageContent]]
        """

        # Step 1: Query 분석
        query_signals = self.query_detector.detect(query, language)

        # Step 2: 검색된 문서의 시각적 특성 분석
        visual_doc_ratio = self._calculate_visual_doc_ratio(retrieved_docs)

        # Step 3: 라우팅 결정
        if query_signals.is_visual_query:
            return RoutingDecision(
                selected_llm="vision",
                reasoning="Query explicitly asks about visual content",
                confidence=query_signals.confidence
            )

        if query_signals.suggested_model == "code":
            return RoutingDecision(
                selected_llm="code",
                reasoning="Query asks for code generation",
                confidence=0.9
            )

        if visual_doc_ratio >= 0.3:
            return RoutingDecision(
                selected_llm="vision",
                reasoning=f"Retrieved docs are {visual_doc_ratio:.0%} visual",
                confidence=0.8
            )

        return RoutingDecision(
            selected_llm="text",
            reasoning="Standard text-based query",
            confidence=0.9
        )

@dataclass
class RoutingDecision:
    selected_llm: Literal["vision", "text", "code"]
    reasoning: str
    confidence: float
    visual_context: Optional[List[ImageContent]] = None
```

---

## 3. Vision Processing Pipeline

### 3.1 Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Vision Processing Pipeline                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Stage 1: Image Extraction & Preprocessing                           │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                                                                  ││
│  │  PDF/Office Document                                             ││
│  │       │                                                          ││
│  │       ▼                                                          ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           ││
│  │  │ Page Render  │→ │ Image Extract│→ │ Preprocessing│           ││
│  │  │ (pdf2image)  │  │ (embedded)   │  │ (resize/opt) │           ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘           ││
│  │                                                                  ││
│  │  Output: List[ProcessedImage]                                    ││
│  │    - image_bytes: bytes                                          ││
│  │    - page_number: int                                            ││
│  │    - region: BoundingBox (optional)                              ││
│  │    - image_type: "page" | "embedded" | "chart" | "table"         ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  Stage 2: Vision LLM Processing                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                                                                  ││
│  │  ProcessedImage[]                                                ││
│  │       │                                                          ││
│  │       ▼                                                          ││
│  │  ┌──────────────────────────────────────────────────────────┐   ││
│  │  │              Vision LLM Selection                         │   ││
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   ││
│  │  │  │ GPT-4 Vision│  │Claude 3 Vis│  │  LLaVA/Yi-VL│       │   ││
│  │  │  │ (Primary)   │  │ (Fallback) │  │  (Local)    │       │   ││
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘       │   ││
│  │  └──────────────────────────────────────────────────────────┘   ││
│  │                                                                  ││
│  │  Vision Tasks:                                                   ││
│  │    - describe: 이미지 전체 설명                                  ││
│  │    - extract_text: OCR 텍스트 추출                               ││
│  │    - analyze_chart: 차트 데이터 추출                             ││
│  │    - analyze_diagram: 다이어그램 구조 분석                       ││
│  │    - answer_question: 이미지 기반 Q&A                            ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  Stage 3: Result Integration                                         │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                                                                  ││
│  │  Vision LLM Output                                               ││
│  │       │                                                          ││
│  │       ▼                                                          ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           ││
│  │  │ Text Extract │→ │ Structured  │→ │ Embed in    │           ││
│  │  │ Normalization│  │ Data Extract│  │ RAG Context │           ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘           ││
│  │                                                                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 VisionLLMPort Interface

```python
# 새 파일: app/api/ports/vision_llm_port.py

from abc import ABC, abstractmethod
from typing import List, Optional, AsyncGenerator
from dataclasses import dataclass

@dataclass
class ImageContent:
    """Vision LLM에 전달할 이미지 컨텐츠"""
    image_bytes: bytes
    mime_type: str  # "image/png", "image/jpeg"
    description: Optional[str] = None  # 선택적 컨텍스트

@dataclass
class VisionMessage:
    """Vision LLM 메시지 (텍스트 + 이미지)"""
    role: str  # "user", "assistant", "system"
    content: str
    images: Optional[List[ImageContent]] = None

@dataclass
class VisionResponse:
    """Vision LLM 응답"""
    content: str
    model: str
    usage: TokenUsage
    extracted_data: Optional[Dict[str, Any]] = None  # 구조화된 데이터
    confidence: float = 1.0

class VisionLLMPort(ABC):
    """Vision LLM 추상 인터페이스"""

    @abstractmethod
    async def generate(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> VisionResponse:
        """Vision LLM 응답 생성"""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> AsyncGenerator[VisionStreamChunk, None]:
        """스트리밍 응답 생성"""
        pass

    @abstractmethod
    async def analyze_image(
        self,
        image: ImageContent,
        task: VisionTask,
        context: Optional[str] = None
    ) -> VisionAnalysisResult:
        """
        단일 이미지 분석

        Tasks:
        - DESCRIBE: 전체 설명
        - EXTRACT_TEXT: OCR
        - ANALYZE_CHART: 차트 데이터 추출
        - ANALYZE_DIAGRAM: 구조 분석
        - EXTRACT_TABLE: 테이블 데이터 추출
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """서비스 상태 확인"""
        pass

class VisionTask(str, Enum):
    DESCRIBE = "describe"
    EXTRACT_TEXT = "extract_text"
    ANALYZE_CHART = "analyze_chart"
    ANALYZE_DIAGRAM = "analyze_diagram"
    EXTRACT_TABLE = "extract_table"
    ANSWER_QUESTION = "answer_question"
```

### 3.3 Vision LLM Adapters

```python
# 새 파일: app/api/adapters/vision/openai_vision_adapter.py

class OpenAIVisionAdapter(VisionLLMPort):
    """GPT-4 Vision 어댑터"""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def generate(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> VisionResponse:
        """GPT-4 Vision API 호출"""

        # 메시지를 OpenAI 형식으로 변환
        openai_messages = []
        for msg in messages:
            content = []
            content.append({"type": "text", "text": msg.content})

            if msg.images:
                for img in msg.images:
                    # Base64 인코딩
                    b64_image = base64.b64encode(img.image_bytes).decode()
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img.mime_type};base64,{b64_image}",
                            "detail": config.detail if config else "auto"
                        }
                    })

            openai_messages.append({
                "role": msg.role,
                "content": content
            })

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            max_tokens=config.max_tokens if config else 4096,
            temperature=config.temperature if config else 0.7
        )

        return VisionResponse(
            content=response.choices[0].message.content,
            model=self.model,
            usage=TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens
            )
        )

# 새 파일: app/api/adapters/vision/anthropic_vision_adapter.py

class AnthropicVisionAdapter(VisionLLMPort):
    """Claude 3 Vision 어댑터 (Fallback)"""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate(
        self,
        messages: List[VisionMessage],
        config: Optional[VisionLLMConfig] = None
    ) -> VisionResponse:
        """Claude Vision API 호출"""
        # Anthropic 형식으로 변환
        ...
```

### 3.4 Image Preprocessing Pipeline

```python
# 새 파일: app/api/services/image_preprocessor.py

class ImagePreprocessor:
    """이미지 전처리 파이프라인"""

    # 최대 이미지 크기 (Vision LLM 제한)
    MAX_IMAGE_SIZE = (2048, 2048)
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

    # 지원 형식
    SUPPORTED_FORMATS = ["PNG", "JPEG", "GIF", "WEBP"]

    async def preprocess(
        self,
        image_bytes: bytes,
        target_format: str = "PNG"
    ) -> ProcessedImage:
        """
        이미지 전처리

        단계:
        1. 형식 검증 및 변환
        2. 크기 조정 (필요시)
        3. 최적화 (품질 vs 크기)
        4. 메타데이터 추출
        """

        image = Image.open(BytesIO(image_bytes))

        # 크기 조정
        if image.size[0] > self.MAX_IMAGE_SIZE[0] or \
           image.size[1] > self.MAX_IMAGE_SIZE[1]:
            image = self._resize_maintain_aspect(image, self.MAX_IMAGE_SIZE)

        # 형식 변환
        if image.format not in self.SUPPORTED_FORMATS:
            image = image.convert("RGB")

        # 바이트로 변환
        output = BytesIO()
        image.save(output, format=target_format, optimize=True)

        return ProcessedImage(
            image_bytes=output.getvalue(),
            original_size=image.size,
            processed_size=image.size,
            format=target_format
        )

    async def extract_from_pdf(
        self,
        pdf_path: Path,
        dpi: int = 150
    ) -> List[ProcessedImage]:
        """PDF에서 이미지 추출"""

        images = []

        # 페이지 렌더링
        pages = pdf2image.convert_from_path(
            pdf_path,
            dpi=dpi,
            fmt="PNG"
        )

        for i, page in enumerate(pages):
            processed = await self.preprocess(
                self._pil_to_bytes(page)
            )
            processed.page_number = i + 1
            processed.image_type = "page"
            images.append(processed)

        # 임베디드 이미지 추출 (선택적)
        embedded = await self._extract_embedded_images(pdf_path)
        images.extend(embedded)

        return images
```

### 3.5 Vision Pipeline Orchestrator

```python
# 새 파일: app/api/pipeline/vision_orchestrator.py

class VisionPipelineOrchestrator:
    """Vision 처리 파이프라인 오케스트레이터"""

    def __init__(
        self,
        vision_llm: VisionLLMPort,
        preprocessor: ImagePreprocessor,
        config: VisionPipelineConfig
    ):
        self.vision_llm = vision_llm
        self.preprocessor = preprocessor
        self.config = config

    async def process_document(
        self,
        document_path: Path,
        tasks: List[VisionTask]
    ) -> DocumentVisionResult:
        """
        문서 전체 Vision 처리

        단계:
        1. 이미지 추출 및 전처리
        2. 각 이미지에 대해 Vision LLM 호출
        3. 결과 통합 및 정규화
        """

        # 1. 이미지 추출
        images = await self.preprocessor.extract_from_pdf(document_path)

        # 2. Vision LLM 처리 (병렬)
        results = await asyncio.gather(*[
            self._process_single_image(img, tasks)
            for img in images
        ])

        # 3. 결과 통합
        return self._merge_results(results)

    async def answer_with_vision(
        self,
        query: str,
        images: List[ImageContent],
        context: Optional[str] = None
    ) -> VisionResponse:
        """
        이미지 기반 질의 응답

        Args:
            query: 사용자 질문
            images: 관련 이미지들
            context: 추가 텍스트 컨텍스트
        """

        # 시스템 프롬프트 구성
        system_prompt = self._build_vision_system_prompt(context)

        messages = [
            VisionMessage(role="system", content=system_prompt),
            VisionMessage(
                role="user",
                content=query,
                images=images
            )
        ]

        return await self.vision_llm.generate(messages)

    def _build_vision_system_prompt(self, context: Optional[str]) -> str:
        """Vision LLM 시스템 프롬프트 생성"""

        base_prompt = """You are an expert at analyzing images and documents.
When analyzing charts, extract specific data points and trends.
When analyzing diagrams, describe the structure and relationships.
Always provide accurate, detailed descriptions based on what you see.
If you're uncertain about something, say so."""

        if context:
            base_prompt += f"\n\nAdditional context:\n{context}"

        return base_prompt
```

---

## 4. Output Normalization

### 4.1 Unified Response Format

```python
# 확장: app/api/models/query.py

@dataclass
class UnifiedQueryResponse:
    """통합 질의 응답 형식"""

    # 기본 응답
    answer: str
    confidence: float

    # 라우팅 정보
    routing: RoutingInfo

    # 소스 정보
    sources: List[SourceInfo]

    # Vision 전용 필드
    visual_analysis: Optional[VisualAnalysis] = None

    # 메타데이터
    metadata: ResponseMetadata

@dataclass
class RoutingInfo:
    """라우팅 결정 정보"""
    selected_llm: str  # "vision" | "text" | "code"
    reasoning: str
    query_type: str  # "vector" | "graph" | "hybrid" | "code"
    visual_signals_detected: bool

@dataclass
class VisualAnalysis:
    """Vision LLM 분석 결과"""
    analyzed_images: List[ImageAnalysisResult]
    extracted_data: Dict[str, Any]  # 차트 데이터, 테이블 등
    visual_summary: str

@dataclass
class ImageAnalysisResult:
    """개별 이미지 분석 결과"""
    image_id: str
    page_number: Optional[int]
    description: str
    extracted_text: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    confidence: float

@dataclass
class ResponseMetadata:
    """응답 메타데이터"""
    total_tokens: int
    latency_ms: float
    model_used: str
    vision_model_used: Optional[str]
    cache_hit: bool
```

### 4.2 Response Normalizer

```python
# 새 파일: app/api/services/response_normalizer.py

class ResponseNormalizer:
    """응답 정규화 서비스"""

    async def normalize(
        self,
        routing_decision: RoutingDecision,
        llm_response: Union[LLMResponse, VisionResponse],
        sources: List[Document],
        visual_analysis: Optional[VisualAnalysis] = None
    ) -> UnifiedQueryResponse:
        """
        다양한 LLM 응답을 통합 형식으로 정규화
        """

        # 소스 정보 변환
        source_infos = [
            SourceInfo(
                document_id=doc.id,
                filename=doc.filename,
                page_number=doc.metadata.get("page"),
                chunk_text=doc.content[:200],
                relevance_score=doc.score,
                has_visual_content=doc.visual_profile.requires_vision_llm
                    if doc.visual_profile else False
            )
            for doc in sources
        ]

        return UnifiedQueryResponse(
            answer=llm_response.content,
            confidence=routing_decision.confidence,
            routing=RoutingInfo(
                selected_llm=routing_decision.selected_llm,
                reasoning=routing_decision.reasoning,
                query_type=routing_decision.query_type,
                visual_signals_detected=routing_decision.selected_llm == "vision"
            ),
            sources=source_infos,
            visual_analysis=visual_analysis,
            metadata=ResponseMetadata(
                total_tokens=llm_response.usage.total_tokens,
                latency_ms=llm_response.latency_ms,
                model_used=llm_response.model,
                vision_model_used=llm_response.model
                    if routing_decision.selected_llm == "vision" else None,
                cache_hit=False
            )
        )
```

### 4.3 Structured Data Extraction

```python
# 새 파일: app/api/services/structured_extractor.py

class StructuredDataExtractor:
    """Vision LLM 출력에서 구조화된 데이터 추출"""

    async def extract_chart_data(
        self,
        vision_response: VisionResponse
    ) -> ChartData:
        """
        차트 분석 결과에서 데이터 추출

        Returns:
            ChartData:
                chart_type: "bar" | "line" | "pie" | ...
                title: str
                x_axis: AxisInfo
                y_axis: AxisInfo
                data_points: List[DataPoint]
        """

    async def extract_table_data(
        self,
        vision_response: VisionResponse
    ) -> TableData:
        """
        테이블 분석 결과에서 데이터 추출

        Returns:
            TableData:
                headers: List[str]
                rows: List[List[str]]
                merged_cells: List[MergedCell]
        """

    async def extract_diagram_structure(
        self,
        vision_response: VisionResponse
    ) -> DiagramStructure:
        """
        다이어그램 구조 추출

        Returns:
            DiagramStructure:
                nodes: List[DiagramNode]
                edges: List[DiagramEdge]
                diagram_type: "flowchart" | "sequence" | "class" | ...
        """

@dataclass
class ChartData:
    chart_type: str
    title: Optional[str]
    x_axis: AxisInfo
    y_axis: AxisInfo
    data_points: List[DataPoint]
    legend: Optional[List[str]]

@dataclass
class DataPoint:
    x: Union[str, float]
    y: float
    series: Optional[str]
```

---

## 5. Cost, Performance, and Security Considerations

### 5.1 Cost Analysis

#### 5.1.1 Vision LLM Pricing (2025년 기준 추정)

| Model | Input (per 1K tokens) | Output (per 1K tokens) | Image (per image) |
|-------|----------------------|------------------------|-------------------|
| GPT-4o | $0.005 | $0.015 | ~$0.0085 (768px) |
| Claude 3.5 Sonnet | $0.003 | $0.015 | ~$0.0048 (1000px) |
| LLaVA (Local) | GPU cost only | GPU cost only | GPU cost only |

#### 5.1.2 Cost Optimization Strategies

```python
# 새 파일: app/api/services/cost_optimizer.py

class VisionCostOptimizer:
    """Vision LLM 비용 최적화"""

    # 비용 임계값 (월간)
    MONTHLY_BUDGET = 1000.0  # USD

    # 이미지당 최대 비용
    MAX_COST_PER_IMAGE = 0.02  # USD

    async def should_use_vision(
        self,
        document: Document,
        query: str,
        current_month_spend: float
    ) -> CostDecision:
        """
        비용 기반 Vision LLM 사용 결정

        고려 요소:
        1. 월간 예산 잔여량
        2. 문서의 시각적 복잡도
        3. 질의의 시각적 필요성
        4. 대안 (텍스트 LLM) 가능 여부
        """

        remaining_budget = self.MONTHLY_BUDGET - current_month_spend

        # 예산 소진 임박
        if remaining_budget < self.MONTHLY_BUDGET * 0.1:
            return CostDecision(
                use_vision=False,
                reason="Budget nearly exhausted",
                fallback="text"
            )

        # 비용 대비 효과 분석
        estimated_cost = self._estimate_vision_cost(document)
        visual_necessity = document.visual_profile.visual_complexity_score

        # ROI 계산: 시각적 필요성 / 비용
        roi = visual_necessity / estimated_cost if estimated_cost > 0 else 0

        return CostDecision(
            use_vision=roi > 10.0,  # ROI 임계값
            reason=f"ROI: {roi:.2f}",
            estimated_cost=estimated_cost
        )

    async def optimize_image_quality(
        self,
        image: ProcessedImage,
        task: VisionTask
    ) -> ProcessedImage:
        """
        작업에 따른 이미지 품질 최적화

        - OCR: 고해상도 필요
        - DESCRIBE: 중간 해상도 충분
        - CHART: 데이터 가독성 중요
        """

        quality_map = {
            VisionTask.EXTRACT_TEXT: "high",
            VisionTask.ANALYZE_CHART: "high",
            VisionTask.DESCRIBE: "medium",
            VisionTask.ANALYZE_DIAGRAM: "medium",
        }

        return await self._resize_for_quality(
            image,
            quality_map.get(task, "medium")
        )
```

### 5.2 Performance Optimization

#### 5.2.1 Caching Strategy

```python
# 확장: app/api/services/cache_service.py

class VisionCacheService:
    """Vision 결과 캐싱"""

    # 캐시 TTL (시간)
    DOCUMENT_ANALYSIS_TTL = 24 * 7  # 7일
    QUERY_RESPONSE_TTL = 1          # 1시간

    async def get_document_analysis(
        self,
        document_id: str,
        visual_profile_hash: str
    ) -> Optional[DocumentVisionResult]:
        """문서 Vision 분석 결과 캐시 조회"""

        cache_key = f"vision:doc:{document_id}:{visual_profile_hash}"
        return await self.cache.get(cache_key)

    async def cache_document_analysis(
        self,
        document_id: str,
        visual_profile_hash: str,
        result: DocumentVisionResult
    ):
        """문서 Vision 분석 결과 캐시 저장"""

        cache_key = f"vision:doc:{document_id}:{visual_profile_hash}"
        await self.cache.set(
            cache_key,
            result,
            ttl=self.DOCUMENT_ANALYSIS_TTL * 3600
        )

    async def get_query_response(
        self,
        query_hash: str,
        context_hash: str
    ) -> Optional[UnifiedQueryResponse]:
        """질의 응답 캐시 조회"""

        cache_key = f"vision:query:{query_hash}:{context_hash}"
        return await self.cache.get(cache_key)
```

#### 5.2.2 Batch Processing

```python
class VisionBatchProcessor:
    """배치 Vision 처리"""

    BATCH_SIZE = 5  # 동시 처리 이미지 수

    async def process_batch(
        self,
        images: List[ProcessedImage],
        task: VisionTask
    ) -> List[ImageAnalysisResult]:
        """
        이미지 배치 처리

        - 동시성 제한으로 API 레이트 리밋 회피
        - 실패 시 개별 재시도
        """

        results = []

        for batch in self._chunk(images, self.BATCH_SIZE):
            batch_results = await asyncio.gather(*[
                self._process_single(img, task)
                for img in batch
            ], return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    # 개별 재시도
                    result = await self._retry_single(img, task)
                results.append(result)

        return results
```

#### 5.2.3 Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Document Analysis Latency | < 30s (10 pages) | P95 |
| Query Response Latency | < 5s (with vision) | P95 |
| Cache Hit Rate | > 60% | 문서 분석 |
| API Success Rate | > 99.5% | Vision LLM 호출 |

### 5.3 Security Considerations

#### 5.3.1 Data Protection

```python
# 새 파일: app/api/services/vision_security.py

class VisionSecurityService:
    """Vision 처리 보안 서비스"""

    # 민감 정보 패턴
    SENSITIVE_PATTERNS = [
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b\d{16}\b',              # 신용카드
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # 이메일
    ]

    async def sanitize_vision_response(
        self,
        response: VisionResponse
    ) -> VisionResponse:
        """
        Vision 응답에서 민감 정보 마스킹

        - PII 자동 감지 및 마스킹
        - 감사 로그 기록
        """

        sanitized_content = response.content
        for pattern in self.SENSITIVE_PATTERNS:
            sanitized_content = re.sub(
                pattern,
                "[REDACTED]",
                sanitized_content
            )

        return VisionResponse(
            content=sanitized_content,
            model=response.model,
            usage=response.usage,
            extracted_data=self._sanitize_extracted_data(
                response.extracted_data
            )
        )

    async def validate_image_upload(
        self,
        image_bytes: bytes
    ) -> ImageValidationResult:
        """
        이미지 업로드 보안 검증

        - 실제 이미지 형식 확인 (magic bytes)
        - 악성 코드 스캔
        - 크기 제한 확인
        """

        # Magic bytes 확인
        mime_type = magic.from_buffer(image_bytes, mime=True)
        if mime_type not in self.ALLOWED_MIME_TYPES:
            return ImageValidationResult(
                valid=False,
                reason=f"Invalid MIME type: {mime_type}"
            )

        # 크기 확인
        if len(image_bytes) > self.MAX_IMAGE_SIZE:
            return ImageValidationResult(
                valid=False,
                reason="Image exceeds size limit"
            )

        return ImageValidationResult(valid=True)
```

#### 5.3.2 Access Control

```python
class VisionAccessControl:
    """Vision 기능 접근 제어"""

    async def can_use_vision(
        self,
        user: User,
        document: Document
    ) -> AccessDecision:
        """
        Vision LLM 사용 권한 확인

        - 사용자 권한 레벨
        - 문서 접근 권한
        - 월간 사용량 제한
        """

        # 사용자 권한 확인
        if not user.has_permission("vision.use"):
            return AccessDecision(
                allowed=False,
                reason="User lacks vision permission"
            )

        # 문서 접근 권한 확인
        if not await self._can_access_document(user, document):
            return AccessDecision(
                allowed=False,
                reason="Document access denied"
            )

        # 사용량 제한 확인
        monthly_usage = await self._get_monthly_usage(user.id)
        if monthly_usage >= user.vision_quota:
            return AccessDecision(
                allowed=False,
                reason="Monthly vision quota exceeded"
            )

        return AccessDecision(allowed=True)
```

#### 5.3.3 Audit Logging

```python
class VisionAuditLogger:
    """Vision 사용 감사 로깅"""

    async def log_vision_usage(
        self,
        user_id: str,
        document_id: str,
        task: VisionTask,
        model: str,
        tokens_used: int,
        cost: float
    ):
        """
        Vision LLM 사용 기록

        기록 내용:
        - 사용자 ID
        - 문서 ID
        - 작업 유형
        - 사용 모델
        - 토큰 사용량
        - 비용
        - 타임스탬프
        """

        await self.audit_log.insert({
            "event_type": "vision_usage",
            "user_id": user_id,
            "document_id": document_id,
            "task": task.value,
            "model": model,
            "tokens": tokens_used,
            "cost": cost,
            "timestamp": datetime.utcnow()
        })
```

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] `VisionLLMPort` 인터페이스 정의
- [ ] `OpenAIVisionAdapter` 구현
- [ ] `ImagePreprocessor` 구현
- [ ] 기본 Vision 캐싱

### Phase 2: Detection & Routing (Week 3-4)
- [ ] `DocumentAnalyzer` 구현
- [ ] `QueryVisualSignalDetector` 구현
- [ ] `VisionAwareRouter` 구현
- [ ] 라우팅 테스트

### Phase 3: Pipeline Integration (Week 5-6)
- [ ] `VisionPipelineOrchestrator` 구현
- [ ] RAG 파이프라인 통합
- [ ] API 엔드포인트 추가
- [ ] 응답 정규화

### Phase 4: Optimization & Security (Week 7-8)
- [ ] 비용 최적화 구현
- [ ] 배치 처리 구현
- [ ] 보안 기능 구현
- [ ] 감사 로깅

### Phase 5: Testing & Deployment (Week 9-10)
- [ ] 단위 테스트
- [ ] 통합 테스트
- [ ] 성능 테스트
- [ ] 프로덕션 배포

---

## 7. File Structure Summary

```
app/api/
├── ports/
│   └── vision_llm_port.py           # [NEW] Vision LLM 인터페이스
├── adapters/
│   └── vision/
│       ├── openai_vision_adapter.py  # [NEW] GPT-4 Vision
│       └── anthropic_vision_adapter.py # [NEW] Claude Vision
├── services/
│   ├── document_analyzer.py          # [NEW] 문서 시각적 분석
│   ├── vision_router.py              # [NEW] Vision-aware 라우팅
│   ├── image_preprocessor.py         # [NEW] 이미지 전처리
│   ├── response_normalizer.py        # [NEW] 응답 정규화
│   ├── structured_extractor.py       # [NEW] 구조화 데이터 추출
│   ├── cost_optimizer.py             # [NEW] 비용 최적화
│   ├── vision_security.py            # [NEW] 보안 서비스
│   └── vlm_service.py               # [MODIFY] 기존 VLM 통합
├── pipeline/
│   ├── vision_orchestrator.py        # [NEW] Vision 파이프라인
│   └── orchestrator.py              # [MODIFY] 기존 RAG 통합
├── models/
│   ├── vision.py                     # [NEW] Vision 데이터 모델
│   └── query.py                     # [MODIFY] 통합 응답 형식
└── routers/
    └── query.py                     # [MODIFY] Vision 엔드포인트

app/src/
└── query_router.py                  # [MODIFY] Visual signal detection
```

---

## 8. Configuration

```python
# 추가: app/api/core/settings.py

class VisionSettings(BaseSettings):
    """Vision LLM 설정"""

    # Primary Vision LLM
    vision_provider: str = "openai"  # openai, anthropic, local
    vision_model: str = "gpt-4o"
    vision_api_key: str = ""

    # Fallback Vision LLM
    fallback_provider: str = "anthropic"
    fallback_model: str = "claude-3-5-sonnet-20241022"
    fallback_api_key: str = ""

    # Cost Control
    monthly_budget: float = 1000.0
    max_cost_per_request: float = 0.50

    # Performance
    max_images_per_request: int = 20
    image_max_dimension: int = 2048
    batch_size: int = 5

    # Routing Thresholds
    visual_complexity_threshold: float = 0.4
    image_area_ratio_threshold: float = 0.3

    # Cache
    cache_ttl_hours: int = 168  # 7 days

    class Config:
        env_prefix = "VISION_"
```

---

## Approval Request

이 설계 문서를 검토해 주세요. 승인되면 Phase 1 (Foundation)부터 구현을 시작하겠습니다.

**승인하려면**: "APPROVED" 또는 "승인"으로 응답해주세요.

**수정 요청**: 특정 섹션에 대한 수정이 필요하면 말씀해주세요.

---

## Appendix: Glossary

| Term | Description |
|------|-------------|
| Vision LLM | 이미지를 이해하고 처리할 수 있는 LLM (GPT-4V, Claude 3 등) |
| VLM | Vision-Language Model, Vision LLM의 다른 표현 |
| OCR | Optical Character Recognition, 이미지에서 텍스트 추출 |
| Visual Complexity Score | 문서의 시각적 복잡도 (0.0~1.0) |
| Port Pattern | 인터페이스 추상화 패턴, 구현체 교체 용이 |
