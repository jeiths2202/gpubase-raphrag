"""
Image Processor

PDF에서 이미지를 추출하고 Vision LLM으로 설명을 생성합니다.
캐시를 활용하여 중복 처리를 방지합니다.
"""

import io
import re
import logging
import asyncio
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import fitz  # PyMuPDF

from .vision_llm_client import VisionLLMClient, VisionResponse, ImageType
from ..cache.image_cache import ImageCache
from ..models.chunk import ExtractedImage, ImageChunk

logger = logging.getLogger(__name__)


class ImageProcessor:
    """PDF 이미지 추출 및 Vision LLM 처리

    주요 기능:
    1. PDF에서 이미지 추출 (PyMuPDF)
    2. 이미지 필터링 (크기, 중복)
    3. Vision LLM으로 설명 생성
    4. 캐시 활용

    환경 변수:
    - MIN_IMAGE_WIDTH: 최소 이미지 너비 (기본값: 100)
    - MIN_IMAGE_HEIGHT: 최소 이미지 높이 (기본값: 100)
    - MAX_IMAGES_PER_PAGE: 페이지당 최대 이미지 수 (기본값: 10)
    """

    MIN_IMAGE_WIDTH = 100
    MIN_IMAGE_HEIGHT = 100
    MAX_IMAGES_PER_PAGE = 10

    # 캡션 패턴 (일본어/한국어/영어)
    CAPTION_PATTERNS = [
        r'(図|Figure|Fig\.?|그림)\s*[\d.]+[:\s]*(.+)',
        r'(表|Table|테이블)\s*[\d.]+[:\s]*(.+)',
        r'(画面|Screen|화면)\s*[\d.]+[:\s]*(.+)',
    ]

    def __init__(
        self,
        vision_client: VisionLLMClient = None,
        cache: ImageCache = None,
        use_cache: bool = True,
        max_concurrent: int = 3
    ):
        """
        Args:
            vision_client: VisionLLMClient 인스턴스
            cache: ImageCache 인스턴스
            use_cache: 캐시 사용 여부
            max_concurrent: 최대 동시 Vision LLM 호출 수
        """
        self.vision_client = vision_client or VisionLLMClient()
        self.cache = cache or ImageCache() if use_cache else None
        self.use_cache = use_cache
        self.max_concurrent = max_concurrent

    def extract_images_from_pdf(
        self,
        pdf_path: str,
        page_range: Tuple[int, int] = None
    ) -> List[ExtractedImage]:
        """PDF에서 이미지 추출

        Args:
            pdf_path: PDF 파일 경로
            page_range: 추출할 페이지 범위 (1-indexed, 포함)

        Returns:
            ExtractedImage 리스트
        """
        extracted = []

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"PDF 열기 실패: {pdf_path} - {e}")
            return []

        try:
            start_page = (page_range[0] - 1) if page_range else 0
            end_page = page_range[1] if page_range else len(doc)

            for page_num in range(start_page, min(end_page, len(doc))):
                page = doc[page_num]
                page_images = self._extract_page_images(page, page_num + 1)
                extracted.extend(page_images[:self.MAX_IMAGES_PER_PAGE])

        finally:
            doc.close()

        logger.info(f"이미지 추출 완료: {len(extracted)}개 ({pdf_path})")
        return extracted

    def _extract_page_images(
        self,
        page: fitz.Page,
        page_number: int
    ) -> List[ExtractedImage]:
        """페이지에서 이미지 추출

        Args:
            page: fitz.Page 객체
            page_number: 페이지 번호 (1-indexed)

        Returns:
            ExtractedImage 리스트
        """
        images = []
        seen_hashes = set()

        # 페이지 텍스트 (캡션 추출용)
        page_text = page.get_text()

        for img_info in page.get_images(full=True):
            try:
                xref = img_info[0]

                # 이미지 데이터 추출
                base_image = page.parent.extract_image(xref)
                if not base_image:
                    continue

                image_data = base_image["image"]
                width = base_image["width"]
                height = base_image["height"]

                # 크기 필터링
                if width < self.MIN_IMAGE_WIDTH or height < self.MIN_IMAGE_HEIGHT:
                    continue

                # 중복 제거
                image_hash = ExtractedImage.compute_hash(image_data)
                if image_hash in seen_hashes:
                    continue
                seen_hashes.add(image_hash)

                # 이미지 위치 (bbox)
                rects = page.get_image_rects(xref)
                bbox = (0, 0, width, height)
                if rects:
                    r = rects[0]
                    bbox = (r.x0, r.y0, r.x1, r.y1)

                # 캡션 추출 시도
                caption, ref_id = self._find_caption(page_text, bbox, page)

                images.append(ExtractedImage(
                    page_number=page_number,
                    bbox=bbox,
                    image_data=image_data,
                    image_hash=image_hash,
                    width=width,
                    height=height,
                    ref_id=ref_id,
                    caption=caption
                ))

            except Exception as e:
                logger.warning(f"이미지 추출 실패 (page {page_number}): {e}")
                continue

        return images

    def _find_caption(
        self,
        page_text: str,
        bbox: Tuple[float, float, float, float],
        page: fitz.Page
    ) -> Tuple[str, str]:
        """이미지 캡션 찾기

        Args:
            page_text: 페이지 전체 텍스트
            bbox: 이미지 위치
            page: fitz.Page 객체

        Returns:
            (caption, ref_id) 튜플
        """
        # 이미지 아래 영역 텍스트 추출
        x0, y0, x1, y1 = bbox
        caption_rect = fitz.Rect(x0 - 10, y1, x1 + 10, y1 + 50)

        try:
            caption_text = page.get_text("text", clip=caption_rect).strip()
        except Exception:
            caption_text = ""

        # 캡션 패턴 매칭
        for pattern in self.CAPTION_PATTERNS:
            match = re.search(pattern, caption_text, re.IGNORECASE)
            if match:
                ref_type = match.group(1)
                caption_content = match.group(2).strip() if match.lastindex > 1 else ""
                ref_id = f"{ref_type} {caption_text.split()[1] if len(caption_text.split()) > 1 else ''}"
                return caption_content[:200], ref_id.strip()

        # 짧은 텍스트면 캡션으로 간주
        if caption_text and len(caption_text) < 100:
            return caption_text, ""

        return "", ""

    async def process_images(
        self,
        images: List[ExtractedImage]
    ) -> List[ImageChunk]:
        """이미지 목록을 처리하여 ImageChunk 생성

        캐시를 확인하고, 캐시 미스인 경우 Vision LLM 호출

        Args:
            images: ExtractedImage 리스트

        Returns:
            ImageChunk 리스트
        """
        chunks = []
        to_process = []  # (index, image) 튜플

        # 1단계: 캐시 확인
        for i, img in enumerate(images):
            if self.use_cache and self.cache:
                cached = self.cache.get(img.image_hash)
                if cached:
                    chunk = ImageChunk(
                        image_id=img.image_hash,
                        image_type=ImageType[cached.get("image_type", "other").upper()],
                        description=cached["description"],
                        caption=img.caption,
                        page_number=img.page_number,
                        ref_id=img.ref_id
                    )
                    chunks.append((i, chunk))
                    logger.debug(f"캐시 히트: {img.image_hash}")
                    continue

            to_process.append((i, img))

        logger.info(f"이미지 처리: {len(to_process)}개 신규, {len(chunks)}개 캐시")

        # 2단계: Vision LLM 호출 (배치)
        if to_process:
            image_data_list = [img.image_data for _, img in to_process]
            responses = await self.vision_client.analyze_images_batch(
                image_data_list,
                max_concurrent=self.max_concurrent
            )

            for (idx, img), response in zip(to_process, responses):
                if response:
                    chunk = self._create_image_chunk(img, response)

                    # 캐시 저장
                    if self.use_cache and self.cache:
                        self.cache.set(
                            img.image_hash,
                            response.description,
                            response.image_type.value,
                            {"page": img.page_number, "ref_id": img.ref_id}
                        )
                else:
                    # Vision LLM 실패 시 기본 설명
                    chunk = ImageChunk(
                        image_id=img.image_hash,
                        image_type=ImageType.OTHER,
                        description=f"[이미지: {img.width}x{img.height}px, 페이지 {img.page_number}]",
                        caption=img.caption,
                        page_number=img.page_number,
                        ref_id=img.ref_id
                    )

                chunks.append((idx, chunk))

        # 원래 순서로 정렬
        chunks.sort(key=lambda x: x[0])
        return [chunk for _, chunk in chunks]

    def _create_image_chunk(
        self,
        image: ExtractedImage,
        response: VisionResponse
    ) -> ImageChunk:
        """ExtractedImage와 VisionResponse로 ImageChunk 생성"""
        # Vision LLM의 ImageType을 모델의 ImageType으로 변환
        from ..models.chunk import ImageType as ModelImageType

        try:
            image_type = ModelImageType(response.image_type.value)
        except ValueError:
            image_type = ModelImageType.OTHER

        return ImageChunk(
            image_id=image.image_hash,
            image_type=image_type,
            description=response.description,
            caption=image.caption,
            page_number=image.page_number,
            ref_id=image.ref_id
        )

    def process_images_sync(
        self,
        images: List[ExtractedImage]
    ) -> List[ImageChunk]:
        """이미지 처리 (동기 버전)"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.process_images(images))
        finally:
            loop.close()

    async def process_pdf_images(
        self,
        pdf_path: str,
        page_range: Tuple[int, int] = None
    ) -> List[ImageChunk]:
        """PDF의 이미지를 추출하고 처리

        편의 메서드: extract + process 결합

        Args:
            pdf_path: PDF 파일 경로
            page_range: 페이지 범위 (선택)

        Returns:
            ImageChunk 리스트
        """
        extracted = self.extract_images_from_pdf(pdf_path, page_range)

        if not extracted:
            return []

        return await self.process_images(extracted)
