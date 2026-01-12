"""
Vision Middleware and Tools for Deep Agents
Vision (이미지/문서 분석) 기능을 Deep Agents에서 사용할 수 있도록 제공

비전 분석, 차트 해석, 다이어그램 분석, OCR 등의 기능 제공
"""
import os
import logging
import base64
from typing import List, Optional, Any, Callable

logger = logging.getLogger(__name__)

# 의존성 체크
try:
    from langchain_core.tools import tool
    LANGCHAIN_TOOLS_AVAILABLE = True
except ImportError:
    LANGCHAIN_TOOLS_AVAILABLE = False


class VisionToolsProvider:
    """
    Vision 도구 제공자

    이미지 분석, 차트 해석, OCR 등의 도구를 Deep Agent에 전달합니다.
    """

    def __init__(self):
        self._vision_service = None

    @property
    def vision_service(self):
        """Lazy load vision service"""
        if self._vision_service is None:
            try:
                from ...services.vision_service import get_vision_service
                self._vision_service = get_vision_service()
            except ImportError:
                logger.warning("Vision service not available")
        return self._vision_service

    def _analyze_image(self, image_path: str, prompt: str = "") -> str:
        """이미지 분석 (동기)"""
        try:
            if self.vision_service is None:
                return "Vision service not available"

            # 이미지 파일 읽기
            if not os.path.exists(image_path):
                return f"Image file not found: {image_path}"

            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            # Vision LLM 호출 (동기 래퍼)
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self.vision_service.analyze_image(image_data, prompt)
                        )
                        result = future.result()
                else:
                    result = loop.run_until_complete(
                        self.vision_service.analyze_image(image_data, prompt)
                    )
            except RuntimeError:
                result = asyncio.run(
                    self.vision_service.analyze_image(image_data, prompt)
                )

            return result

        except Exception as e:
            logger.error(f"[VisionTools] Image analysis error: {e}")
            return f"Image analysis error: {str(e)}"

    def _search_knowledge_base(self, query: str, top_k: int = 5) -> str:
        """Knowledge base search for context (동기)"""
        try:
            from ..tools import VectorSearchTool
            from ..types import AgentContext

            vector_tool = VectorSearchTool()
            context = AgentContext()

            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            vector_tool.execute(context, query=query, top_k=top_k)
                        )
                        result = future.result()
                else:
                    result = loop.run_until_complete(
                        vector_tool.execute(context, query=query, top_k=top_k)
                    )
            except RuntimeError:
                result = asyncio.run(
                    vector_tool.execute(context, query=query, top_k=top_k)
                )

            if result.get("success"):
                output = result.get("output", {})
                if isinstance(output, dict):
                    results = output.get("results", [])
                    if results:
                        formatted = []
                        for r in results[:top_k]:
                            formatted.append(f"- {r.get('content', '')[:300]}")
                        return "\n".join(formatted)
                return str(output)
            return "No results found"

        except Exception as e:
            logger.error(f"[VisionTools] Knowledge search error: {e}")
            return f"Search error: {str(e)}"

    def get_tools(self) -> List[Callable]:
        """Vision 도구 목록 반환"""
        if not LANGCHAIN_TOOLS_AVAILABLE:
            logger.warning("[VisionTools] langchain_core.tools not available")
            return []

        provider = self

        @tool
        def analyze_image(image_path: str, analysis_type: str = "general", prompt: str = "") -> str:
            """Analyze an image using Vision LLM.

            Use this tool to analyze images, charts, diagrams, or documents.

            Args:
                image_path: Path to the image file
                analysis_type: Type of analysis - "general" (describe content),
                              "chart" (extract data from charts),
                              "diagram" (interpret technical diagrams),
                              "ocr" (extract text from image)
                prompt: Additional prompt for specific analysis instructions

            Returns:
                Analysis result with description, extracted data, or text
            """
            try:
                analysis_prompts = {
                    "general": "Describe this image in detail. Include all visible elements, colors, and composition.",
                    "chart": "This is a chart or graph. Extract all data points, labels, values, and trends. Present as structured data.",
                    "diagram": "This is a technical diagram. Identify all components, their relationships, and flow of information.",
                    "ocr": "Extract all text visible in this image. Preserve the layout and structure if possible."
                }

                base_prompt = analysis_prompts.get(analysis_type, analysis_prompts["general"])
                full_prompt = f"{base_prompt}\n\n{prompt}" if prompt else base_prompt

                result = provider._analyze_image(image_path, full_prompt)
                return result

            except Exception as e:
                logger.error(f"[VisionTools] analyze_image error: {e}")
                return f"Image analysis error: {str(e)}"

        @tool
        def search_visual_context(query: str, top_k: int = 5) -> str:
            """Search the knowledge base for visual content related context.

            Use this to find relevant documentation or examples related to visual content.

            Args:
                query: Search query for related visual documentation
                top_k: Number of results to return (default: 5)

            Returns:
                Related content from knowledge base
            """
            try:
                result = provider._search_knowledge_base(query, top_k)
                return result
            except Exception as e:
                logger.error(f"[VisionTools] search error: {e}")
                return f"Search error: {str(e)}"

        return [analyze_image, search_visual_context]


def get_vision_tools() -> List[Callable]:
    """
    Vision 도구 목록 반환 (간편 함수)

    Returns:
        List of Vision tools for use with create_deep_agent
    """
    provider = VisionToolsProvider()
    return provider.get_tools()


# Vision 시스템 프롬프트
VISION_SYSTEM_PROMPT = """
## Vision Analysis Guidelines

You are a visual content analysis specialist with access to Vision LLM.

### Available Tools:

1. **analyze_image**: Analyze images, charts, diagrams, or documents
   - analysis_type: "general", "chart", "diagram", "ocr"
   - Can extract data from charts, interpret diagrams, or read text from images

2. **search_visual_context**: Search knowledge base for related visual documentation
   - Use to find context about visual elements you're analyzing

### Important Rules:

1. **Describe Objectively**: Start with objective description of visual content
2. **Extract Data**: For charts/graphs, extract specific data points and values
3. **Identify Relationships**: For diagrams, identify components and their connections
4. **Preserve Text**: For OCR, maintain original formatting when possible
5. **Note Uncertainties**: If analysis is uncertain, clearly state limitations

### Response Format:

For image analysis:
- Description of visual content
- Key elements identified
- Data or text extracted
- Interpretation and insights
- Confidence level in analysis
"""
