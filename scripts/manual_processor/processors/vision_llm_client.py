"""
Vision LLM Client

MiniCPM-V 2.6 Vision LLM을 호출하여 이미지 설명을 생성합니다.
OpenAI-compatible API (vLLM)를 사용합니다.
"""

import os
import base64
import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ImageType(Enum):
    """이미지 유형"""
    DIAGRAM = "diagram"
    FLOWCHART = "flowchart"
    SCREENSHOT = "screenshot"
    TABLE_IMAGE = "table_image"
    CHART = "chart"
    OTHER = "other"


@dataclass
class VisionResponse:
    """Vision LLM 응답"""
    description: str
    image_type: ImageType
    confidence: float
    raw_response: Dict[str, Any]


class VisionLLMClient:
    """MiniCPM-V 2.6 Vision LLM 클라이언트

    OpenAI-compatible API를 통해 이미지를 분석하고 설명을 생성합니다.

    환경 변수:
    - VISION_LLM_URL: Vision LLM API URL (기본값: http://localhost:12803/v1)
    - VISION_LLM_MODEL: 모델 이름 (기본값: openbmb/MiniCPM-V-2_6)
    - VISION_LLM_TIMEOUT: 타임아웃 초 (기본값: 60)
    """

    DEFAULT_URL = "http://localhost:12803/v1"
    DEFAULT_MODEL = "openbmb/MiniCPM-V-2_6"
    DEFAULT_TIMEOUT = 60

    # 이미지 분석 프롬프트
    ANALYSIS_PROMPT = """Analyze this image from a technical document and provide:
1. A detailed description of what the image shows (2-3 sentences)
2. The type of image (one of: diagram, flowchart, screenshot, table_image, chart, other)
3. Key technical terms or concepts visible in the image

Format your response as:
TYPE: [image_type]
DESCRIPTION: [description]
KEYWORDS: [comma-separated keywords]"""

    # 일본어 프롬프트 (OpenFrame 문서용)
    ANALYSIS_PROMPT_JA = """この技術文書の画像を分析してください：
1. 画像が示している内容の詳細な説明（2-3文）
2. 画像の種類（diagram, flowchart, screenshot, table_image, chart, other のいずれか）
3. 画像に見える主要な技術用語や概念

以下の形式で回答してください：
TYPE: [画像の種類]
DESCRIPTION: [説明]
KEYWORDS: [キーワード（カンマ区切り）]"""

    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        timeout: int = None,
        language: str = "ja"
    ):
        """
        Args:
            base_url: Vision LLM API URL
            model: 모델 이름
            timeout: 요청 타임아웃 (초)
            language: 프롬프트 언어 ("ja" 또는 "en")
        """
        self.base_url = base_url or os.getenv("VISION_LLM_URL", self.DEFAULT_URL)
        self.model = model or os.getenv("VISION_LLM_MODEL", self.DEFAULT_MODEL)
        self.timeout = timeout or int(os.getenv("VISION_LLM_TIMEOUT", self.DEFAULT_TIMEOUT))
        self.language = language

        # API 엔드포인트
        self.chat_endpoint = f"{self.base_url}/chat/completions"

        logger.info(f"VisionLLMClient 초기화: {self.base_url} ({self.model})")

    def _get_prompt(self) -> str:
        """언어에 맞는 프롬프트 반환"""
        return self.ANALYSIS_PROMPT_JA if self.language == "ja" else self.ANALYSIS_PROMPT

    def _encode_image(self, image_data: bytes) -> str:
        """이미지를 base64로 인코딩"""
        return base64.b64encode(image_data).decode('utf-8')

    def _parse_response(self, content: str) -> VisionResponse:
        """응답 파싱

        Args:
            content: LLM 응답 텍스트

        Returns:
            VisionResponse
        """
        lines = content.strip().split('\n')

        image_type = ImageType.OTHER
        description = content
        keywords = []

        for line in lines:
            line = line.strip()
            if line.upper().startswith("TYPE:"):
                type_str = line[5:].strip().lower()
                try:
                    image_type = ImageType(type_str)
                except ValueError:
                    image_type = ImageType.OTHER
            elif line.upper().startswith("DESCRIPTION:"):
                description = line[12:].strip()
            elif line.upper().startswith("KEYWORDS:"):
                keywords = [k.strip() for k in line[9:].split(',')]

        # 설명이 너무 짧으면 전체 응답 사용
        if len(description) < 20:
            description = content

        return VisionResponse(
            description=description,
            image_type=image_type,
            confidence=0.8,  # MiniCPM-V는 confidence를 반환하지 않음
            raw_response={"content": content, "keywords": keywords}
        )

    async def analyze_image(
        self,
        image_data: bytes,
        custom_prompt: str = None
    ) -> Optional[VisionResponse]:
        """이미지 분석

        Args:
            image_data: 이미지 바이너리 데이터 (PNG/JPEG)
            custom_prompt: 커스텀 프롬프트 (선택)

        Returns:
            VisionResponse 또는 None (실패 시)
        """
        prompt = custom_prompt or self._get_prompt()
        base64_image = self._encode_image(image_data)

        # OpenAI-compatible 요청 구성
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            "max_tokens": 500,
            "temperature": 0.3
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.chat_endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Vision LLM 오류 {response.status}: {error_text}")
                        return None

                    result = await response.json()
                    content = result["choices"][0]["message"]["content"]

                    return self._parse_response(content)

        except asyncio.TimeoutError:
            logger.error(f"Vision LLM 타임아웃 ({self.timeout}초)")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"Vision LLM 연결 오류: {e}")
            return None
        except Exception as e:
            logger.error(f"Vision LLM 예외: {e}")
            return None

    async def analyze_images_batch(
        self,
        images: List[bytes],
        max_concurrent: int = 3
    ) -> List[Optional[VisionResponse]]:
        """여러 이미지 배치 분석

        Args:
            images: 이미지 데이터 리스트
            max_concurrent: 최대 동시 요청 수

        Returns:
            VisionResponse 리스트 (실패한 항목은 None)
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_limit(image_data: bytes) -> Optional[VisionResponse]:
            async with semaphore:
                return await self.analyze_image(image_data)

        tasks = [analyze_with_limit(img) for img in images]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 예외를 None으로 변환
        return [
            r if isinstance(r, VisionResponse) else None
            for r in results
        ]

    async def health_check(self) -> bool:
        """Vision LLM 서비스 상태 확인

        Returns:
            서비스 가용 여부
        """
        try:
            models_endpoint = f"{self.base_url}/models"
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(models_endpoint) as response:
                    return response.status == 200
        except Exception as e:
            logger.warning(f"Vision LLM 헬스체크 실패: {e}")
            return False

    def analyze_image_sync(
        self,
        image_data: bytes,
        custom_prompt: str = None
    ) -> Optional[VisionResponse]:
        """이미지 분석 (동기 버전)

        기존 동기 코드와의 호환성을 위한 래퍼
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.analyze_image(image_data, custom_prompt)
            )
        finally:
            loop.close()
