"""
Vision Knowledge Service

Summary 검색 결과의 페이지 참조를 기반으로
PDF 페이지 이미지를 MiniCPM-V에 전송하여 답변을 생성합니다.

Architecture:
    User Query
        │
        ▼
    SummarySearchService.comprehensive_search()
        │ - 키워드 추출
        │ - 요약문서 검색
        │ - page_references 추출
        ▼
    VisionKnowledgeService.enrich_with_vision()
        │ - PDF 경로 해석
        │ - 페이지 이미지 렌더링 (PyMuPDF)
        │ - MiniCPM-V 호출
        ▼
    Response with Tables/Charts/Images
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Feature toggle
ENABLE_VISION_KNOWLEDGE = os.getenv("ENABLE_VISION_KNOWLEDGE", "true").lower() == "true"

# Limits
MAX_PDF_REFERENCES = 3  # Maximum PDF files to process
MAX_PAGES_PER_PDF = 5   # Maximum pages per PDF
MAX_TOTAL_IMAGES = 10   # Maximum total images to send to Vision LLM
PDF_RENDER_DPI = 150    # DPI for PDF rendering


class VisionKnowledgeService:
    """
    Summary 검색 + PDF Vision 분석 통합 서비스

    사용자 쿼리에서 키워드를 추출하고, 요약문서에서 관련 정보를 찾은 후
    해당 PDF 페이지를 MiniCPM-V로 분석하여 표, 차트, 이미지를 포함한
    상세 답변을 제공합니다.
    """

    def __init__(
        self,
        manuals_dir: Optional[Path] = None,
        vision_base_url: Optional[str] = None,
        vision_model: Optional[str] = None,
    ):
        """
        Initialize VisionKnowledgeService.

        Args:
            manuals_dir: Directory containing PDF manuals
            vision_base_url: MiniCPM-V vLLM server URL
            vision_model: Vision model name
        """
        # Manual directories to search
        self._manuals_dirs: List[Path] = []

        # Check /opt/kms first (production), then local
        opt_path = Path("/opt/kms/uploads/manuals")
        local_path = Path("uploads/manuals")

        if manuals_dir:
            self._manuals_dirs.append(manuals_dir)
        if opt_path.exists():
            self._manuals_dirs.append(opt_path)
        if local_path.exists():
            self._manuals_dirs.append(local_path)

        self._vision_base_url = vision_base_url
        self._vision_model = vision_model
        self._vision_adapter = None
        self._summary_service = None

        # PDF name to path cache
        self._pdf_path_cache: Dict[str, Path] = {}

    @property
    def summary_service(self):
        """Lazy load SummarySearchService"""
        if self._summary_service is None:
            from .summary_search_service import get_summary_search_service
            self._summary_service = get_summary_search_service()
        return self._summary_service

    @property
    def vision_adapter(self):
        """Lazy load MiniCPM Vision Adapter"""
        if self._vision_adapter is None:
            try:
                from app.api.core.config import get_api_settings
                from app.api.adapters.vision.minicpm_vision_adapter import MiniCPMVisionAdapter

                settings = get_api_settings()
                base_url = self._vision_base_url or settings.VISION_API_URL
                model = self._vision_model or settings.VISION_LLM_MODEL

                self._vision_adapter = MiniCPMVisionAdapter(
                    base_url=base_url,
                    model=model,
                    max_tokens=settings.VISION_MAX_TOKENS,
                    timeout=settings.VISION_TIMEOUT,
                )
                logger.info(f"VisionKnowledgeService: MiniCPM adapter initialized at {base_url}")
            except Exception as e:
                logger.error(f"Failed to initialize Vision adapter: {e}")
                raise
        return self._vision_adapter

    async def search_with_vision(
        self,
        query: str,
        language: str = "ja",
        max_pages: int = MAX_PAGES_PER_PDF,
    ) -> Dict[str, Any]:
        """
        키워드 기반 요약 검색 + Vision LLM 분석 통합

        Args:
            query: 사용자 질문
            language: 응답 언어 ("ja", "ko", "en")
            max_pages: PDF당 최대 페이지 수

        Returns:
            {
                "type": "vision_enriched" | "text_only",
                "answer": str,  # Vision LLM 응답 (vision_enriched인 경우)
                "summary_context": str,  # 요약 검색 컨텍스트
                "sources": List[str],  # 출처 목록
                "image_count": int,  # 분석된 이미지 수
                "page_references": List[Dict],  # 참조된 페이지 정보
            }
        """
        if not ENABLE_VISION_KNOWLEDGE:
            return {
                "type": "disabled",
                "summary_context": "",
                "message": "Vision Knowledge Service is disabled",
            }

        # Step 1: Summary 검색
        summary_results = await self.summary_service.comprehensive_search(query)

        summary_context = summary_results.get("context_string", "")
        results = summary_results.get("results", [])

        # Step 2: 페이지 참조 수집
        page_refs = await self._collect_page_references(results, query)

        if not page_refs:
            return {
                "type": "text_only",
                "summary_context": summary_context,
                "results": results,
                "confidence": summary_results.get("confidence", "low"),
            }

        logger.info(f"[VisionKnowledge] Found {len(page_refs)} page references for query: {query[:50]}")

        # Step 3: PDF 페이지 이미지 수집
        images, sources = await self._collect_page_images(page_refs, max_pages)

        if not images:
            return {
                "type": "text_only",
                "summary_context": summary_context,
                "results": results,
                "confidence": summary_results.get("confidence", "low"),
                "message": "Could not load PDF pages",
            }

        logger.info(f"[VisionKnowledge] Collected {len(images)} page images from {len(sources)} sources")

        # Step 4: MiniCPM-V 분석
        try:
            vision_response = await self._analyze_with_vision(
                query=query,
                images=images,
                context=summary_context,
                language=language,
            )

            return {
                "type": "vision_enriched",
                "answer": vision_response,
                "summary_context": summary_context,
                "sources": sources,
                "image_count": len(images),
                "page_references": page_refs,
                "confidence": "high",
            }

        except Exception as e:
            logger.error(f"[VisionKnowledge] Vision analysis failed: {e}")
            return {
                "type": "text_only",
                "summary_context": summary_context,
                "results": results,
                "confidence": summary_results.get("confidence", "low"),
                "error": str(e),
            }

    async def _collect_page_references(
        self,
        summary_results: List[Dict],
        query: str,
    ) -> List[Dict[str, Any]]:
        """
        요약 검색 결과에서 페이지 참조 수집

        Returns:
            List of {
                "pdf_name": str,
                "pages": List[int],
                "source_file": str,
            }
        """
        page_refs = []
        seen_pdfs = set()

        # Extract command/keyword from query for PDF text search
        query_keywords = self._extract_query_keywords(query)
        logger.info(f"[VisionKnowledge] Query keywords: {query_keywords}")

        for result in summary_results[:10]:  # 최대 10개 결과 처리
            source_file = result.get("source_file", "")
            result_type = result.get("type", "")

            # 요약 파일에서 PDF 참조 추출
            # 형식: OF_Utility.md → OF_Common_MVS_7.1_Utility-Reference-Guide_v3.1.3_JP.pdf
            pdf_name = self._infer_pdf_from_summary(source_file, result_type)

            if pdf_name and pdf_name not in seen_pdfs:
                seen_pdfs.add(pdf_name)

                # 결과에서 페이지 번호 추출 시도
                pages = self._extract_page_numbers(result)
                logger.debug(f"[VisionKnowledge] {pdf_name}: extracted pages = {pages}")

                # 페이지 번호가 없으면 PDF 텍스트 검색으로 찾기
                if not pages and query_keywords:
                    pdf_path = await self._resolve_pdf_path(pdf_name)
                    if pdf_path:
                        logger.info(f"[VisionKnowledge] Searching PDF {pdf_path.name} for keywords...")
                        pages = await self._find_pages_by_keyword(
                            pdf_path, query_keywords, max_pages=3
                        )
                        logger.info(f"[VisionKnowledge] Found pages via keyword search: {pages}")
                    else:
                        logger.warning(f"[VisionKnowledge] Could not resolve PDF path for: {pdf_name}")

                page_refs.append({
                    "pdf_name": pdf_name,
                    "pages": pages or [1],  # 페이지 없으면 첫 페이지
                    "source_file": source_file,
                    "result_type": result_type,
                })

                if len(page_refs) >= MAX_PDF_REFERENCES:
                    break

        # 추가: 쿼리에서 직접 페이지 참조 추출
        query_refs = await self.summary_service.extract_page_references(query)
        for ref in query_refs:
            pdf_name = ref.get("pdf_path", "")
            if pdf_name and pdf_name not in seen_pdfs:
                seen_pdfs.add(pdf_name)
                page_refs.append({
                    "pdf_name": pdf_name,
                    "pages": ref.get("page_numbers", [1]),
                    "source_file": "query",
                    "result_type": "explicit_reference",
                })

        logger.info(f"[VisionKnowledge] Collected {len(page_refs)} page references")
        return page_refs

    def _infer_pdf_from_summary(self, source_file: str, result_type: str) -> Optional[str]:
        """
        요약 파일명에서 원본 PDF 파일명 추론

        Mappings:
        - commands/I.md, commands/T.md → Utility-Reference-Guide
        - error-codes/*.md → Error-Reference-Guide
        - glossary/*.md → 여러 가이드 (Base-Guide 우선)
        """
        if not source_file:
            return None

        # 에러 코드 파일
        if "error" in source_file.lower() or result_type == "error_code":
            return "Error-Reference-Guide"

        # 명령어 파일
        if source_file.endswith(".md") and len(source_file) <= 5:  # I.md, T.md 등
            return "Utility-Reference-Guide"

        # 특정 제품 명령어
        product_patterns = {
            "TJES": "TJES-Guide",
            "OSC": "Administrator-Guide",
            "OSI": "Administrator-Guide",
            "TACF": "Administrator-Guide",
            "HiDB": "HiDB-Guide",
            "Batch": "Batch-Guide",
            "Base": "Base-Guide",
        }

        for product, guide in product_patterns.items():
            if product.lower() in source_file.lower():
                return guide

        # 기본값
        return "Utility-Reference-Guide"

    def _extract_page_numbers(self, result: Dict) -> List[int]:
        """결과에서 페이지 번호 추출"""
        pages = []

        # reference 필드에서 페이지 추출
        reference = result.get("reference", "") or result.get("source", "")
        if reference:
            # p.43, p.43-45, page 43 등의 패턴
            page_matches = re.findall(r'p\.?\s*(\d+)(?:-(\d+))?', reference, re.IGNORECASE)
            for match in page_matches:
                start = int(match[0])
                end = int(match[1]) if match[1] else start
                pages.extend(range(start, min(end + 1, start + MAX_PAGES_PER_PDF)))

        # context 필드에서 페이지 추출
        context = result.get("context", "")
        if context and not pages:
            page_matches = re.findall(r'(?:페이지|page|p\.?)\s*(\d+)', context, re.IGNORECASE)
            pages = [int(p) for p in page_matches[:MAX_PAGES_PER_PDF]]

        return pages[:MAX_PAGES_PER_PDF]

    def _extract_query_keywords(self, query: str) -> List[str]:
        """쿼리에서 검색할 키워드 추출 (일본어/한국어 혼합 텍스트 지원)"""
        keywords = []

        # 대문자 명령어/유틸리티 (IDCAMS, ALTER, DEFINE 등)
        # \b가 CJK 문자 경계에서 작동하지 않으므로 패턴 수정
        upper_keywords = re.findall(r'([A-Z]{2,}[A-Z0-9]*)', query)
        keywords.extend(upper_keywords)

        # 소문자 명령어 (tjesmgr, oscboot 등)
        lower_keywords = re.findall(r'([a-z]{4,}[a-z0-9]*)', query)
        stop_words = {'what', 'when', 'where', 'which', 'that', 'this', 'with',
                      'about', 'from', 'into', 'have', 'does', 'できる', 'ください',
                      'について', 'コマンド'}
        for kw in lower_keywords:
            if kw.lower() not in stop_words:
                keywords.append(kw)

        # 알려진 OpenFrame 명령어/유틸리티 직접 매칭
        known_commands = [
            'IDCAMS', 'ALTER', 'DEFINE', 'DELETE', 'LISTCAT', 'REPRO', 'PRINT',
            'IEBGENER', 'IEBCOPY', 'DFSORT', 'SYNCSORT', 'ICETOOL',
            'tjesmgr', 'oscmgr', 'tacfmgr', 'hidbmgr', 'ndbmgr', 'osimgr',
            'BOOT', 'DOWN', 'STATUS', 'START', 'STOP',
        ]
        for cmd in known_commands:
            if cmd.upper() in query.upper():
                keywords.append(cmd)

        # 중복 제거 및 상위 5개
        seen = set()
        unique = []
        for kw in keywords:
            kw_upper = kw.upper()
            if kw_upper not in seen and len(kw) >= 2:
                seen.add(kw_upper)
                unique.append(kw)

        logger.debug(f"[VisionKnowledge] Extracted keywords from query: {unique}")
        return unique[:5]

    async def _find_pages_by_keyword(
        self,
        pdf_path: Path,
        keywords: List[str],
        max_pages: int = 3,
    ) -> List[int]:
        """
        PDF에서 키워드가 포함된 페이지 찾기

        Args:
            pdf_path: PDF 파일 경로
            keywords: 검색할 키워드 목록
            max_pages: 반환할 최대 페이지 수
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("[VisionKnowledge] PyMuPDF not available for keyword search")
            return []

        if not keywords:
            logger.debug(f"[VisionKnowledge] No keywords to search in {pdf_path.name}")
            return []

        found_pages = []
        page_scores = []  # (page_num, match_count, matched_keywords)

        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            logger.debug(f"[VisionKnowledge] Searching {total_pages} pages in {pdf_path.name} for keywords: {keywords}")

            for page_num in range(total_pages):
                page = doc[page_num]
                text = page.get_text().upper()

                # 각 키워드 매칭 확인
                matched = []
                for kw in keywords:
                    if kw.upper() in text:
                        matched.append(kw)

                if matched:
                    page_scores.append((page_num + 1, len(matched), matched))

            doc.close()

            # 매칭 점수로 정렬 (가장 많은 키워드 매칭 우선)
            page_scores.sort(key=lambda x: x[1], reverse=True)

            # 먼저 모든 키워드가 매칭된 페이지 선택
            full_match_pages = [(p, s, m) for p, s, m in page_scores if s == len(keywords)]
            partial_match_pages = [(p, s, m) for p, s, m in page_scores if s < len(keywords)]

            # 전체 매칭 우선, 그 다음 부분 매칭
            selected = full_match_pages[:max_pages]
            remaining_slots = max_pages - len(selected)
            if remaining_slots > 0:
                selected.extend(partial_match_pages[:remaining_slots])

            # 상위 페이지 선택
            for page_num, score, matched in selected:
                found_pages.append(page_num)
                match_type = "FULL" if score == len(keywords) else "partial"
                logger.debug(f"[VisionKnowledge] Found {match_type} match on p.{page_num}: {matched} ({score}/{len(keywords)})")

            if found_pages:
                logger.info(f"[VisionKnowledge] Found pages {found_pages} in {pdf_path.name}")
            else:
                logger.debug(f"[VisionKnowledge] No keyword matches found in {pdf_path.name}")

        except Exception as e:
            logger.warning(f"[VisionKnowledge] PDF keyword search failed for {pdf_path}: {e}")

        return found_pages

    async def _collect_page_images(
        self,
        page_refs: List[Dict],
        max_pages: int,
    ) -> Tuple[List[bytes], List[str]]:
        """
        PDF 페이지를 이미지로 변환

        Returns:
            (images, sources) tuple
        """
        images = []
        sources = []

        for ref in page_refs:
            pdf_name = ref["pdf_name"]
            pages = ref["pages"][:max_pages]

            # PDF 경로 찾기
            pdf_path = await self._resolve_pdf_path(pdf_name)
            if not pdf_path:
                logger.warning(f"[VisionKnowledge] PDF not found: {pdf_name}")
                continue

            # 페이지 렌더링
            try:
                page_images = await self._render_pdf_pages(pdf_path, pages)
                images.extend(page_images)

                if page_images:
                    page_str = ",".join(str(p) for p in pages[:len(page_images)])
                    sources.append(f"{pdf_path.name}, p.{page_str}")

                if len(images) >= MAX_TOTAL_IMAGES:
                    break

            except Exception as e:
                logger.error(f"[VisionKnowledge] Failed to render {pdf_path}: {e}")
                continue

        return images[:MAX_TOTAL_IMAGES], sources

    async def _resolve_pdf_path(self, pdf_name: str) -> Optional[Path]:
        """
        PDF 이름을 실제 파일 경로로 해석

        Args:
            pdf_name: PDF 파일 이름 또는 가이드 키워드
                      (예: "Utility-Reference-Guide", "OF_Common_*.pdf")
        """
        # 캐시 확인
        if pdf_name in self._pdf_path_cache:
            return self._pdf_path_cache[pdf_name]

        # 모든 매뉴얼 디렉토리 검색
        for manuals_dir in self._manuals_dirs:
            if not manuals_dir.exists():
                continue

            # 하위 디렉토리 포함 검색
            for subdir in manuals_dir.iterdir():
                if not subdir.is_dir():
                    continue

                for pdf_file in subdir.glob("*.pdf"):
                    # 정확한 이름 매칭
                    if pdf_file.name == pdf_name:
                        self._pdf_path_cache[pdf_name] = pdf_file
                        return pdf_file

                    # 키워드 매칭 (예: "Utility-Reference-Guide" → OF_Common_MVS_7.1_Utility-Reference-Guide_*.pdf)
                    if pdf_name.lower() in pdf_file.name.lower():
                        self._pdf_path_cache[pdf_name] = pdf_file
                        return pdf_file

        return None

    async def _render_pdf_pages(
        self,
        pdf_path: Path,
        pages: List[int],
    ) -> List[bytes]:
        """
        PDF 페이지를 PNG 이미지로 렌더링

        Args:
            pdf_path: PDF 파일 경로
            pages: 렌더링할 페이지 번호 목록 (1-based)
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF (fitz) not installed")
            return []

        images = []

        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            zoom = PDF_RENDER_DPI / 72  # Convert DPI to zoom factor
            mat = fitz.Matrix(zoom, zoom)

            for page_num in pages:
                # 1-based to 0-based index
                idx = page_num - 1

                if 0 <= idx < total_pages:
                    page = doc[idx]
                    pix = page.get_pixmap(matrix=mat)
                    images.append(pix.tobytes("png"))
                    logger.debug(f"Rendered page {page_num} from {pdf_path.name}")
                else:
                    logger.warning(f"Page {page_num} out of range (total: {total_pages})")

            doc.close()

        except Exception as e:
            logger.error(f"Failed to render PDF {pdf_path}: {e}")

        return images

    async def _analyze_with_vision(
        self,
        query: str,
        images: List[bytes],
        context: str,
        language: str,
    ) -> str:
        """
        MiniCPM-V로 이미지 분석

        Args:
            query: 사용자 질문
            images: PDF 페이지 이미지 목록
            context: 요약 검색 컨텍스트
            language: 응답 언어
        """
        from app.api.ports.vision_llm_port import ImageContent, VisionTask

        # 프롬프트 구성
        if language == "ja":
            prompt = f"""以下の質問に、画像の内容を参照して詳しく回答してください。
表やチャートがあれば、その内容も整理して説明してください。

質問: {query}

参照コンテキスト:
{context}

詳細に、できるだけ長く説明してください。箇条書きで整理してください。"""
        elif language == "ko":
            prompt = f"""다음 질문에 이미지 내용을 참고하여 상세히 답변해주세요.
표나 차트가 있으면 그 내용도 정리해서 설명해주세요.

질문: {query}

참조 컨텍스트:
{context}

상세하게, 가능한 길게 설명해주세요. 목록 형식으로 정리해주세요."""
        else:
            prompt = f"""Please answer the following question by referencing the image content.
If there are tables or charts, organize and explain their content.

Question: {query}

Reference Context:
{context}

Please provide a detailed, comprehensive explanation in bullet points."""

        # 이미지를 ImageContent로 변환
        image_contents = [
            ImageContent(image_bytes=img, mime_type="image/png")
            for img in images
        ]

        # 모든 이미지를 하나의 요청으로 분석 (최대 5개)
        if len(image_contents) > 5:
            # MiniCPM-V는 요청당 최대 5개 이미지
            # 여러 번 호출하여 결과 통합
            all_results = []
            for i in range(0, len(image_contents), 5):
                batch = image_contents[i:i+5]
                result = await self._call_vision_batch(batch, prompt, language)
                all_results.append(result)

            return "\n\n---\n\n".join(all_results)
        else:
            return await self._call_vision_batch(image_contents, prompt, language)

    async def _call_vision_batch(
        self,
        images: List,  # List[ImageContent]
        prompt: str,
        language: str,
    ) -> str:
        """Vision LLM 배치 호출"""
        from app.api.ports.vision_llm_port import VisionTask

        # 첫 번째 이미지로 분석 (배치)
        if len(images) == 1:
            result = await self.vision_adapter.analyze_image(
                image=images[0],
                task=VisionTask.ANSWER_QUESTION,
                context=prompt,
                language=language,
            )
            return result.content
        else:
            # 여러 이미지: 순차 처리 후 통합
            results = []
            for i, img in enumerate(images):
                result = await self.vision_adapter.analyze_image(
                    image=img,
                    task=VisionTask.ANSWER_QUESTION,
                    context=f"[Image {i+1}/{len(images)}]\n\n{prompt}",
                    language=language,
                )
                results.append(f"### Page {i+1}\n{result.content}")

                # GPU 과부하 방지
                await asyncio.sleep(0.3)

            return "\n\n".join(results)

    def clear_cache(self):
        """PDF 경로 캐시 초기화"""
        self._pdf_path_cache.clear()


# Singleton instance
_vision_knowledge_service: Optional[VisionKnowledgeService] = None


def get_vision_knowledge_service() -> VisionKnowledgeService:
    """Get or create singleton VisionKnowledgeService instance"""
    global _vision_knowledge_service
    if _vision_knowledge_service is None:
        _vision_knowledge_service = VisionKnowledgeService()
    return _vision_knowledge_service


async def reset_vision_knowledge_service():
    """Reset singleton (for testing)"""
    global _vision_knowledge_service
    if _vision_knowledge_service:
        _vision_knowledge_service.clear_cache()
    _vision_knowledge_service = None
