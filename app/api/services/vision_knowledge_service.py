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
        │ - 페이지 이미지 렌더링 (pypdfium2)
        │ - MiniCPM-V 호출
        ▼
    [Stage 1] Quick Relevance Filter (키워드 기반, <10ms)
        │ - 쿼리 키워드 포함 여부 확인
        │ - 짧은 응답/에러 응답 제거
        ▼
    [Stage 2] LLM Consolidation (MiniCPM-V, ~3-5s)
        │ - 관련 정보 추출 및 통합
        │ - 중복 제거
        │ - 출처 정보 유지
        ▼
    Consolidated Response with Tables/Charts/Images
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

# ============================================================
# Product Keyword Mapping (쿼리 키워드 → 제품 매핑)
# ============================================================
# 키워드가 속한 제품을 식별하여 올바른 PDF 문서에서 검색

PRODUCT_KEYWORD_MAP = {
    # OSC 제품 (Online CICS)
    "OSC": ["OSC", "oscmgr", "oscboot", "CICS", "BMS", "マップ", "맵", "map",
            "DFHCOMMAREA", "EIBTRNID", "EIBCALEN", "トランザクション", "트랜잭션"],

    # TJES 제품 (Job Entry Subsystem)
    "TJES": ["TJES", "tjesmgr", "JES", "JCL", "JOB", "SPOOL", "SUBMIT",
             "ジョブ", "잡", "スプール", "스풀", "JESINIT", "JESDOWN"],

    # HiDB 제품 (Hierarchical Database)
    "HiDB": ["HiDB", "hidbmgr", "IMS", "DL/I", "PSB", "DBD", "PCB",
             "階層型", "계층형", "データベース", "데이터베이스"],

    # TACF 제품 (Security)
    "TACF": ["TACF", "tacfmgr", "RACF", "セキュリティ", "보안", "認証", "인증",
             "アクセス制御", "접근제어", "権限", "권한"],

    # OSI 제품 (Online System Interface / IMS DC equivalent)
    "OSI": ["OSI", "osimgr", "MFS", "DL/I", "IMS DC", "メッセージフォーマット",
            "메시지포맷", "VTAM", "SNA", "ネットワーク", "네트워크"],

    # NDB 제품 (Network Database)
    "NDB": ["NDB", "ndbmgr", "IDMS", "ネットワークDB", "네트워크DB"],

    # Batch/Utility 제품 (공통 유틸리티)
    "Utility": ["IDCAMS", "ALTER", "DEFINE", "DELETE", "LISTCAT", "REPRO", "PRINT",
                "IEBGENER", "IEBCOPY", "DFSORT", "SYNCSORT", "ICETOOL",
                "VSAM", "KSDS", "ESDS", "RRDS", "GDG", "PDS",
                "ユーティリティ", "유틸리티", "データセット", "데이터셋"],

    # Base 제품 (공통 기반)
    "Base": ["OpenFrame", "tmboot", "tmdown", "ofboot", "ofdown",
             "tmax", "構成", "구성", "設定", "설정", "インストール", "설치"],
}

# 제품별 PDF 파일명 패턴 (파일명에 포함되어야 하는 문자열)
# 요약문서의 실제 PDF 파일명 기반:
#   OF_OSC_*, OF_OSI_*, OF_HiDB_*, OF_TACF_*, OF_NDB_*, OF_AIM_*,
#   OF_Base_*, OF_Batch_*, OF_Common_*, OF_VOS3_*, Tibero_*, Tmax_*
PRODUCT_PDF_PATTERNS = {
    # OpenFrame 제품별 패턴
    "OSC": ["OF_OSC_", "OSC_"],                    # OpenFrame Server For CICS
    "OSI": ["OF_OSI_", "OSI_"],                    # OpenFrame Server For IMS
    "HiDB": ["OF_HiDB_", "HiDB_"],                 # Hierarchical Database
    "TACF": ["OF_TACF_", "TACF_"],                 # Security (RACF 호환)
    "NDB": ["OF_NDB_", "NDB_"],                    # Network Database
    "AIM": ["OF_AIM_", "AIM_"],                    # Application Interface Manager

    # TJES는 Batch 내 TJES-Guide에 있음
    "TJES": ["TJES-Guide", "OF_Batch_"],

    # 공통/유틸리티 (IDCAMS, VSAM 등)
    "Utility": ["Utility-Reference", "OF_Common_"],

    # 플랫폼별 공통
    "MSP": ["_MSP_", "OF_Common_MSP_", "OF_Batch_MSP_"],   # Fujitsu MSP 호환
    "XSP": ["_XSP_", "OF_Common_XSP_", "OF_Batch_XSP_"],   # Fujitsu XSP 호환
    "VOS3": ["OF_VOS3_", "VOS3_"],                          # Hitachi VOS3 호환
    "MVS": ["_MVS_", "OF_Common_MVS_", "OF_Batch_MVS_"],   # IBM MVS 호환

    # 기본/공통 문서
    "Base": ["OF_Base_", "Base-Guide", "Dataset-Guide"],
    "Batch": ["OF_Batch_", "Batch-Guide", "JCL-Reference"],
    "GW": ["OF_GW_"],

    # 외부 제품
    "Tibero": ["Tibero_"],
    "Tmax": ["Tmax_"],
}


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
        pdf_filter: Optional[str] = None,
        page_numbers: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        키워드 기반 요약 검색 + Vision LLM 분석 통합

        Args:
            query: 사용자 질문
            language: 응답 언어 ("ja", "ko", "en")
            max_pages: PDF당 최대 페이지 수
            pdf_filter: 특정 PDF 파일명 (구조 검색에서 전달)
            page_numbers: 특정 페이지 번호 리스트 (구조 검색에서 전달)

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

        # Direct page access mode: Skip summary search, use specified PDF and pages
        if pdf_filter and page_numbers:
            logger.info(f"[VisionKnowledge] Direct mode: {pdf_filter} pages {page_numbers}")

            # Build page_refs directly from provided parameters
            page_refs = [
                {"pdf_name": pdf_filter, "page_num": p}
                for p in page_numbers[:max_pages]
            ]

            # Collect images for specified pages
            images, sources, page_metadata = await self._collect_page_images(page_refs, max_pages)

            if not images:
                return {
                    "type": "text_only",
                    "summary_context": "",
                    "message": f"Could not load pages {page_numbers} from {pdf_filter}",
                }

            # Skip to Vision analysis
            try:
                vision_response, relevant_sources, relevant_images = await self._analyze_with_vision(
                    query=query,
                    images=images,
                    page_metadata=page_metadata,
                    context="",  # No summary context in direct mode
                    language=language,
                )

                filtered_sources = [
                    f"{s['pdf_name']}, p.{s['page_num']}" for s in relevant_sources
                ]

                return {
                    "type": "vision_enriched",
                    "answer": vision_response,
                    "summary_context": "",
                    "sources": filtered_sources or [f"{pdf_filter}, p.{p}" for p in page_numbers],
                    "image_count": len(images),
                    "page_references": page_refs,
                    "page_images": relevant_images,
                }
            except Exception as e:
                logger.error(f"[VisionKnowledge] Direct mode analysis failed: {e}")
                return {
                    "type": "text_only",
                    "summary_context": "",
                    "message": f"Vision analysis failed: {e}",
                }

        # Standard mode: Summary search + page reference collection
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
        images, sources, page_metadata = await self._collect_page_images(page_refs, max_pages)

        if not images:
            return {
                "type": "text_only",
                "summary_context": summary_context,
                "results": results,
                "confidence": summary_results.get("confidence", "low"),
                "message": "Could not load PDF pages",
            }

        logger.info(f"[VisionKnowledge] Collected {len(images)} page images from {len(sources)} sources")

        # Step 4: MiniCPM-V 분석 + 필터링/통합
        try:
            vision_response, relevant_sources, relevant_images = await self._analyze_with_vision(
                query=query,
                images=images,
                page_metadata=page_metadata,  # 페이지 정보 전달
                context=summary_context,
                language=language,
            )

            # 필터링된 소스 정보로 sources 업데이트
            filtered_sources = [
                f"{s['pdf_name']}, p.{s['page_num']}" for s in relevant_sources
            ]

            return {
                "type": "vision_enriched",
                "answer": vision_response,
                "summary_context": summary_context,
                "sources": filtered_sources if filtered_sources else sources,
                "image_count": len(relevant_images),
                "page_references": page_refs,
                "page_images": relevant_images if relevant_images else page_metadata,  # 필터링된 이미지만
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

        # 제품 감지 (OSC, TJES, HiDB 등)
        detected_product = self._detect_product_from_query(query, query_keywords)
        if detected_product:
            logger.info(f"[VisionKnowledge] Filtering PDFs for product: {detected_product}")

        for result in summary_results[:10]:  # 최대 10개 결과 처리
            source_file = result.get("source_file", "")
            result_type = result.get("type", "")

            # 요약 파일에서 PDF 참조 추출
            # 형식: OF_Utility.md → OF_Common_MVS_7.1_Utility-Reference-Guide_v3.1.3_JP.pdf
            pdf_name = self._infer_pdf_from_summary(source_file, result_type)

            # 제품 필터링: 감지된 제품과 관련 없는 PDF는 제외
            if pdf_name and not self._filter_pdf_by_product(pdf_name, detected_product):
                logger.debug(f"[VisionKnowledge] Skipping PDF '{pdf_name}' (not matching product '{detected_product}')")
                continue

            if pdf_name and pdf_name not in seen_pdfs:
                seen_pdfs.add(pdf_name)

                # 결과에서 페이지 번호 추출 시도
                pages = self._extract_page_numbers(result)
                logger.debug(f"[VisionKnowledge] {pdf_name}: extracted pages = {pages}")

                # 페이지 번호가 없으면 PDF 텍스트 검색으로 찾기
                if not pages and query_keywords:
                    pdf_path = await self._resolve_pdf_path(pdf_name, detected_product)
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

        # Step 3: 제품이 감지되었지만 page_refs가 비어있으면, 제품별 summary 파일 직접 검색
        if detected_product and not page_refs:
            logger.info(f"[VisionKnowledge] No refs found, searching product-specific summary for: {detected_product}")
            product_summary_mapping = {
                "OSC": ("commands/OpenFrame_OSC_MVS.md", "OF_OSC_"),
                "OSI": ("commands/OpenFrame_OSI_MVS.md", "OF_OSI_"),
                "TJES": ("commands/OpenFrame_TJES_MVS.md", "TJES-Guide"),
                "HiDB": ("commands/OpenFrame_HiDB.md", "OF_HiDB_"),
                "TACF": ("commands/OpenFrame_TACF_MVS.md", "OF_TACF_"),
                "NDB": ("commands/OpenFrame_NDB.md", "OF_NDB_"),
                "AIM": ("commands/OpenFrame_AIM.md", "OF_AIM_"),
                "Utility": ("commands/OpenFrame_Utility.md", "Utility-Reference-Guide"),
            }

            if detected_product in product_summary_mapping:
                summary_file, pdf_prefix = product_summary_mapping[detected_product]
                summary_path = Path("uploads/summaries") / summary_file
                if summary_path.exists():
                    logger.info(f"[VisionKnowledge] Found product summary: {summary_file}")

                    # PDF 경로 해결
                    pdf_path = await self._resolve_pdf_path(pdf_prefix, detected_product)
                    if pdf_path:
                        logger.info(f"[VisionKnowledge] Resolved PDF: {pdf_path.name}")

                        # 키워드로 페이지 검색
                        pages = []
                        if query_keywords:
                            pages = await self._find_pages_by_keyword(
                                pdf_path, query_keywords, max_pages=3
                            )
                            logger.info(f"[VisionKnowledge] Found pages via keyword: {pages}")

                        page_refs.append({
                            "pdf_name": pdf_path.name,
                            "pages": pages or [1],
                            "source_file": summary_file,
                            "result_type": "product_specific",
                        })
                else:
                    logger.debug(f"[VisionKnowledge] Product summary not found: {summary_path}")

        logger.info(f"[VisionKnowledge] Collected {len(page_refs)} page references")
        return page_refs

    def _infer_pdf_from_summary(self, source_file: str, result_type: str) -> Optional[str]:
        """
        요약 파일명에서 원본 PDF 파일명 추론

        Mappings:
        - commands/OpenFrame_OSC_MVS.md → OF_OSC_
        - commands/I.md, commands/T.md → Utility-Reference-Guide
        - error-codes/*.md → Error-Reference-Guide
        - glossary/*.md → 여러 가이드 (Base-Guide 우선)
        """
        if not source_file:
            return None

        source_lower = source_file.lower()

        # 에러 코드 파일
        if "error" in source_lower or result_type == "error_code":
            return "Error-Reference-Guide"

        # 제품별 명령어 요약 파일 → 제품별 PDF 패턴
        # 요약문서 형식: commands/OpenFrame_OSC_MVS.md, OpenFrame_TJES_MVS.md 등
        product_pdf_mapping = {
            "openframe_osc": "OF_OSC_",           # OSC 제품 PDF
            "openframe_osi": "OF_OSI_",           # OSI 제품 PDF
            "openframe_hidb": "OF_HiDB_",         # HiDB 제품 PDF
            "openframe_tacf": "OF_TACF_",         # TACF 제품 PDF
            "openframe_tjes": "TJES-Guide",       # TJES는 Batch 내 TJES-Guide
            "openframe_ndb": "OF_NDB_",           # NDB 제품 PDF
            "openframe_aim": "OF_AIM_",           # AIM 제품 PDF
            "openframe_base": "OF_Base_",         # Base 제품 PDF
            "openframe_batch": "OF_Batch_",       # Batch 제품 PDF
            "openframe_common": "OF_Common_",     # Common 유틸리티 PDF
            "openframe_msp": "OF_Common_MSP_",    # MSP 플랫폼 PDF
            "openframe_xsp": "OF_Common_XSP_",    # XSP 플랫폼 PDF
            "openframe_vos3": "OF_VOS3_",         # VOS3 플랫폼 PDF
            "openframe_mvs": "OF_Common_MVS_",    # MVS 플랫폼 PDF
            "tibero": "Tibero_",                  # Tibero PDF
            "tmax": "Tmax_",                      # Tmax PDF
        }

        for pattern, pdf_prefix in product_pdf_mapping.items():
            if pattern in source_lower:
                return pdf_prefix

        # 단일 글자 명령어 파일 (I.md, T.md 등) → 유틸리티 가이드
        if source_file.endswith(".md") and len(source_file) <= 5:
            return "Utility-Reference-Guide"

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
        en_stop_words = {'what', 'when', 'where', 'which', 'that', 'this', 'with',
                         'about', 'from', 'into', 'have', 'does'}
        for kw in lower_keywords:
            if kw.lower() not in en_stop_words:
                keywords.append(kw)

        # 일본어 키워드 추출 (カタカナ + 漢字 조합)
        # マップ, 構成, フローチャート 등
        ja_keywords = re.findall(r'[\u30A0-\u30FF\u4E00-\u9FFF]{2,}', query)
        ja_stop_words = {'について', 'ください', 'できる', 'コマンド', 'する', 'ある',
                         'です', 'ます', 'こと', 'もの', 'なに', 'どの', 'これ', 'それ',
                         'という', 'として'}
        for kw in ja_keywords:
            if kw not in ja_stop_words:
                keywords.append(kw)

        # 한국어 키워드 추출
        ko_keywords = re.findall(r'[\uAC00-\uD7AF]{2,}', query)
        ko_stop_words = {'에서', '에게', '으로', '대해', '해주세요', '합니다', '입니다',
                         '것은', '것이', '무엇'}
        for kw in ko_keywords:
            if kw not in ko_stop_words:
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

        # 중복 제거 및 상위 7개 (일본어/한국어 키워드 포함으로 증가)
        seen = set()
        unique = []
        for kw in keywords:
            # CJK 문자는 원본 유지, 영어는 대문자로 비교
            kw_normalized = kw if re.search(r'[\u3040-\u9FFF\uAC00-\uD7AF]', kw) else kw.upper()
            if kw_normalized not in seen and len(kw) >= 2:
                seen.add(kw_normalized)
                unique.append(kw)

        logger.debug(f"[VisionKnowledge] Extracted keywords from query: {unique}")
        return unique[:7]

    def _detect_product_from_query(self, query: str, keywords: List[str]) -> Optional[str]:
        """
        쿼리와 키워드에서 제품 식별

        Args:
            query: 사용자 질문
            keywords: 추출된 키워드 목록

        Returns:
            감지된 제품명 (OSC, TJES, HiDB, etc.) 또는 None
        """
        query_upper = query.upper()
        detected_products = {}  # {product: match_count}

        # 1. 키워드를 제품에 매핑
        for product, product_keywords in PRODUCT_KEYWORD_MAP.items():
            match_count = 0

            # 쿼리에서 직접 매칭
            for pk in product_keywords:
                pk_upper = pk.upper()
                if pk_upper in query_upper:
                    match_count += 2  # 직접 매칭은 가중치 2

            # 추출된 키워드와 매칭
            for kw in keywords:
                kw_upper = kw.upper()
                for pk in product_keywords:
                    pk_upper = pk.upper()
                    if kw_upper == pk_upper or pk_upper in kw_upper:
                        match_count += 1

            if match_count > 0:
                detected_products[product] = match_count

        if not detected_products:
            logger.debug("[VisionKnowledge] No specific product detected from query")
            return None

        # 가장 높은 매칭 점수를 가진 제품 선택
        best_product = max(detected_products, key=detected_products.get)
        logger.info(
            f"[VisionKnowledge] Detected product: {best_product} "
            f"(scores: {detected_products})"
        )
        return best_product

    def _filter_pdf_by_product(self, pdf_name: str, product: Optional[str]) -> bool:
        """
        PDF 파일이 해당 제품과 관련 있는지 확인

        Args:
            pdf_name: PDF 파일명
            product: 감지된 제품명

        Returns:
            관련있으면 True, 아니면 False
        """
        if not product:
            return True  # 제품 미지정이면 모든 PDF 허용

        pdf_upper = pdf_name.upper()

        # 제품별 PDF 패턴 확인
        product_patterns = PRODUCT_PDF_PATTERNS.get(product, [])
        for pattern in product_patterns:
            if pattern.upper() in pdf_upper:
                logger.debug(f"[VisionKnowledge] PDF '{pdf_name}' matches product '{product}'")
                return True

        logger.debug(f"[VisionKnowledge] PDF '{pdf_name}' filtered out (not matching product '{product}')")
        return False

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
        if not keywords:
            logger.debug(f"[VisionKnowledge] No keywords to search in {pdf_path.name}")
            return []

        from . import pdf_compat

        found_pages = []
        page_scores = []  # (page_num, match_count, matched_keywords)

        try:
            path_str = str(pdf_path)
            total_pages = pdf_compat.get_page_count(path_str)

            logger.debug(f"[VisionKnowledge] Searching {total_pages} pages in {pdf_path.name} for keywords: {keywords}")

            for page_num in range(total_pages):
                text = pdf_compat.extract_text_plain(path_str, page_num).upper()

                # 각 키워드 매칭 확인
                matched = []
                for kw in keywords:
                    if kw.upper() in text:
                        matched.append(kw)

                if matched:
                    page_scores.append((page_num + 1, len(matched), matched))

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
    ) -> Tuple[List[bytes], List[str], List[Dict]]:
        """
        PDF 페이지를 이미지로 변환

        Returns:
            (images, sources, page_metadata) tuple
            page_metadata: List of {"pdf_name": str, "page_num": int, "image_base64": str}
        """
        import base64

        images = []
        sources = []
        page_metadata = []  # 각 이미지의 출처 정보

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

                for i, img_bytes in enumerate(page_images):
                    if len(images) >= MAX_TOTAL_IMAGES:
                        break
                    images.append(img_bytes)
                    page_num = pages[i] if i < len(pages) else pages[-1]
                    page_metadata.append({
                        "pdf_name": pdf_path.name,
                        "page_num": page_num,
                        "image_base64": base64.b64encode(img_bytes).decode("utf-8"),
                    })

                if page_images:
                    page_str = ",".join(str(p) for p in pages[:len(page_images)])
                    sources.append(f"{pdf_path.name}, p.{page_str}")

                if len(images) >= MAX_TOTAL_IMAGES:
                    break

            except Exception as e:
                logger.error(f"[VisionKnowledge] Failed to render {pdf_path}: {e}")
                continue

        return images[:MAX_TOTAL_IMAGES], sources, page_metadata[:MAX_TOTAL_IMAGES]

    async def _resolve_pdf_path(
        self,
        pdf_name: str,
        detected_product: Optional[str] = None,
    ) -> Optional[Path]:
        """
        PDF 이름을 실제 파일 경로로 해석

        Args:
            pdf_name: PDF 파일 이름 또는 가이드 키워드
                      (예: "OF_OSC_", "Utility-Reference-Guide", "OF_Common_*.pdf")
            detected_product: 감지된 제품 (필터링에 사용)
        """
        cache_key = f"{pdf_name}:{detected_product or ''}"

        # 캐시 확인
        if cache_key in self._pdf_path_cache:
            return self._pdf_path_cache[cache_key]

        matched_files = []

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
                        self._pdf_path_cache[cache_key] = pdf_file
                        return pdf_file

                    # 프리픽스 매칭 (예: "OF_OSC_" → OF_OSC_7.1_Administrator-Guide_*.pdf)
                    if pdf_file.name.startswith(pdf_name):
                        matched_files.append(pdf_file)
                        continue

                    # 키워드 매칭 (예: "Utility-Reference-Guide" → OF_Common_MVS_7.1_Utility-Reference-Guide_*.pdf)
                    if pdf_name.lower() in pdf_file.name.lower():
                        matched_files.append(pdf_file)

        # 매칭된 파일 중 제품 필터링 및 선택
        if matched_files:
            # 제품 필터링 적용
            if detected_product:
                filtered = [f for f in matched_files if self._filter_pdf_by_product(f.name, detected_product)]
                if filtered:
                    matched_files = filtered

            # 첫 번째 매칭 파일 반환 (우선순위: Administrator-Guide > 기타)
            for pdf_file in matched_files:
                if "administrator" in pdf_file.name.lower() or "mapping" in pdf_file.name.lower():
                    self._pdf_path_cache[cache_key] = pdf_file
                    logger.debug(f"[VisionKnowledge] Resolved '{pdf_name}' → {pdf_file.name}")
                    return pdf_file

            # 첫 번째 파일 반환
            self._pdf_path_cache[cache_key] = matched_files[0]
            logger.debug(f"[VisionKnowledge] Resolved '{pdf_name}' → {matched_files[0].name}")
            return matched_files[0]

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
        from . import pdf_compat

        images = []
        path_str = str(pdf_path)

        try:
            total_pages = pdf_compat.get_page_count(path_str)
            zoom = PDF_RENDER_DPI / 72  # Convert DPI to zoom factor

            for page_num in pages:
                # 1-based to 0-based index
                idx = page_num - 1

                if 0 <= idx < total_pages:
                    png_bytes = pdf_compat.render_page_png(path_str, idx, zoom=zoom)
                    images.append(png_bytes)
                    logger.debug(f"Rendered page {page_num} from {pdf_path.name}")
                else:
                    logger.warning(f"Page {page_num} out of range (total: {total_pages})")

        except Exception as e:
            logger.error(f"Failed to render PDF {pdf_path}: {e}")

        return images

    async def _analyze_with_vision(
        self,
        query: str,
        images: List[bytes],
        page_metadata: List[Dict],
        context: str,
        language: str,
    ) -> Tuple[str, List[Dict], List[Dict]]:
        """
        MiniCPM-V로 이미지 분석 및 관련성 필터링

        Args:
            query: 사용자 질문
            images: PDF 페이지 이미지 목록
            page_metadata: 각 이미지의 출처 정보 [{pdf_name, page_num, ...}]
            context: 요약 검색 컨텍스트
            language: 응답 언어

        Returns:
            Tuple of (consolidated_answer, relevant_sources, relevant_page_images)
        """
        from app.api.ports.vision_llm_port import ImageContent, VisionTask
        from app.api.core.config import get_api_settings

        settings = get_api_settings()

        # 이미지를 ImageContent로 변환
        image_contents = [
            ImageContent(image_bytes=img, mime_type="image/png")
            for img in images
        ]

        # 쿼리 키워드 추출 (필터링용)
        query_keywords = self._extract_query_keywords(query)
        logger.info(f"[VisionKnowledge] Query keywords for filtering: {query_keywords}")

        # 각 이미지를 개별 분석 (페이지 정보 포함)
        per_page_data = []

        for i, (img_content, meta) in enumerate(zip(image_contents, page_metadata)):
            pdf_name = meta.get("pdf_name", "Unknown")
            page_num = meta.get("page_num", i + 1)

            # 페이지별 프롬프트 구성 (중앙화된 언어 정책 사용)
            from .language_policy import get_language_policy_service
            lang_service = get_language_policy_service()
            lang_instruction = lang_service.get_language_instruction(language)

            if language == "ja":
                prompt = f"""{lang_instruction}

この画像は「{pdf_name}」のページ{page_num}です。
以下の質問に、この画像の内容を参照して回答してください。
表やチャートがあれば、その内容を詳しく説明してください。

質問: {query}

参照コンテキスト:
{context}

重要: 画像に表示されている具体的な情報（属性名、パラメータ、値など）を箇条書きで列挙してください。"""
            elif language == "ko":
                prompt = f"""{lang_instruction}

이 이미지는 「{pdf_name}」의 {page_num}페이지입니다.
다음 질문에 이 이미지 내용을 참고하여 답변해주세요.
표나 차트가 있으면 그 내용을 상세히 설명해주세요.

질문: {query}

참조 컨텍스트:
{context}

중요: 이미지에 표시된 구체적인 정보(속성명, 파라미터, 값 등)를 목록으로 나열해주세요."""
            else:
                prompt = f"""{lang_instruction}

This image is page {page_num} from "{pdf_name}".
Please answer the following question by referencing this image content.
If there are tables or charts, explain their content in detail.

Question: {query}

Reference Context:
{context}

Important: List the specific information shown in the image (attribute names, parameters, values, etc.) in bullet points."""

            try:
                result = await self.vision_adapter.analyze_image(
                    image=img_content,
                    task=VisionTask.ANSWER_QUESTION,
                    context=prompt,
                    language=language,
                )

                per_page_data.append({
                    "pdf_name": pdf_name,
                    "page_num": page_num,
                    "analysis": result.content,
                    "image_base64": meta.get("image_base64", ""),
                })

                # GPU 과부하 방지
                await asyncio.sleep(0.3)

            except Exception as e:
                logger.warning(f"[VisionKnowledge] Analysis failed for {pdf_name} p.{page_num}: {e}")
                per_page_data.append({
                    "pdf_name": pdf_name,
                    "page_num": page_num,
                    "analysis": f"[分析失敗: {str(e)}]",
                    "image_base64": meta.get("image_base64", ""),
                })

        # 필터링 및 통합 수행
        if settings.VISION_CONSOLIDATION_ENABLED and len(per_page_data) > 1:
            return await self._filter_and_consolidate_responses(
                query=query,
                per_page_responses=per_page_data,
                query_keywords=query_keywords,
                language=language,
                max_relevant_pages=settings.VISION_MAX_RELEVANT_PAGES,
            )
        else:
            # 통합 비활성화 또는 단일 페이지: 기존 동작
            all_results = []
            relevant_sources = []
            relevant_images = []

            for data in per_page_data:
                all_results.append(f"### 📄 {data['pdf_name']} (p.{data['page_num']})\n{data['analysis']}")
                relevant_sources.append({
                    "pdf_name": data["pdf_name"],
                    "page_num": data["page_num"],
                })
                relevant_images.append({
                    "pdf_name": data["pdf_name"],
                    "page_num": data["page_num"],
                    "image_base64": data["image_base64"],
                })

            return "\n\n".join(all_results), relevant_sources, relevant_images

    def _quick_relevance_check(
        self,
        query: str,
        page_analysis: str,
        query_keywords: List[str],
    ) -> Tuple[bool, float]:
        """
        Stage 1: 빠른 키워드 기반 관련성 체크

        Args:
            query: 사용자 질문
            page_analysis: 페이지 분석 결과
            query_keywords: 쿼리에서 추출된 키워드

        Returns:
            (is_relevant, keyword_score)
        """
        from app.api.core.config import get_api_settings
        settings = get_api_settings()

        # 분석 결과가 너무 짧거나 에러인 경우 제외
        if len(page_analysis) < 50:
            return False, 0.0

        if "分析失敗" in page_analysis or "[Error" in page_analysis:
            return False, 0.0

        # 키워드가 없으면 일단 관련있다고 판단
        if not query_keywords:
            return True, 0.5

        # 키워드 매칭 점수 계산
        analysis_upper = page_analysis.upper()
        matched_count = 0

        for kw in query_keywords:
            if kw.upper() in analysis_upper:
                matched_count += 1

        keyword_score = matched_count / len(query_keywords) if query_keywords else 0.0

        # 최소 매칭 비율 체크
        is_relevant = keyword_score >= settings.VISION_MIN_KEYWORD_MATCH_RATIO

        return is_relevant, keyword_score

    async def _filter_and_consolidate_responses(
        self,
        query: str,
        per_page_responses: List[Dict],
        query_keywords: List[str],
        language: str,
        max_relevant_pages: int = 3,
    ) -> Tuple[str, List[Dict], List[Dict]]:
        """
        Stage 1 + Stage 2: 관련성 필터링 및 LLM 통합

        Args:
            query: 사용자 질문
            per_page_responses: 페이지별 분석 결과 [{pdf_name, page_num, analysis, image_base64}]
            query_keywords: 쿼리 키워드
            language: 응답 언어
            max_relevant_pages: 최대 관련 페이지 수

        Returns:
            (consolidated_answer, relevant_sources, relevant_page_images)
        """
        # Stage 1: Quick Relevance Filter
        scored_pages = []

        for data in per_page_responses:
            is_relevant, score = self._quick_relevance_check(
                query, data["analysis"], query_keywords
            )

            if is_relevant:
                scored_pages.append({
                    **data,
                    "relevance_score": score,
                })
            else:
                logger.debug(
                    f"[VisionKnowledge] Filtered out: {data['pdf_name']} p.{data['page_num']} "
                    f"(score: {score:.2f})"
                )

        # 관련 페이지가 없으면 "정보 없음" 반환 (할루시네이션 방지)
        if not scored_pages:
            logger.warning(f"[VisionKnowledge] No relevant pages found for query: {query}")
            logger.warning(f"[VisionKnowledge] Query keywords: {query_keywords}")
            no_info_messages = {
                "ja": f"申し訳ありませんが、「{query}」に関連する情報がPDF文書の画像から見つかりませんでした。",
                "ko": f"죄송합니다. '{query}'와 관련된 정보를 PDF 문서 이미지에서 찾을 수 없습니다.",
                "en": f"Sorry, no relevant information about '{query}' was found in the PDF document images.",
            }
            no_info_msg = no_info_messages.get(language, no_info_messages["ja"])
            return no_info_msg, [], []

        # 점수 순으로 정렬하고 상위 N개 선택
        scored_pages.sort(key=lambda x: x["relevance_score"], reverse=True)
        filtered_pages = scored_pages[:max_relevant_pages]

        logger.info(
            f"[VisionKnowledge] Filtered {len(per_page_responses)} pages → {len(filtered_pages)} relevant pages"
        )
        for p in filtered_pages:
            logger.info(f"  - {p['pdf_name']} p.{p['page_num']} (score: {p['relevance_score']:.2f})")

        # Stage 2: LLM Consolidation (3개 이상일 때만)
        if len(filtered_pages) >= 2:
            try:
                consolidated = await self._llm_consolidate(
                    query=query,
                    filtered_analyses=filtered_pages,
                    language=language,
                )
            except Exception as e:
                logger.warning(f"[VisionKnowledge] LLM consolidation failed: {e}, using simple concat")
                consolidated = self._simple_concat_responses(filtered_pages)
        else:
            # 단일 페이지는 통합 불필요
            consolidated = self._simple_concat_responses(filtered_pages)

        # 관련 소스 및 이미지 수집
        relevant_sources = [
            {"pdf_name": p["pdf_name"], "page_num": p["page_num"]}
            for p in filtered_pages
        ]
        relevant_images = [
            {
                "pdf_name": p["pdf_name"],
                "page_num": p["page_num"],
                "image_base64": p.get("image_base64", ""),
            }
            for p in filtered_pages
        ]

        return consolidated, relevant_sources, relevant_images

    def _simple_concat_responses(self, pages: List[Dict]) -> str:
        """단순 연결 (폴백용)"""
        results = []
        for p in pages:
            results.append(f"### 📄 {p['pdf_name']} (p.{p['page_num']})\n{p['analysis']}")
        return "\n\n".join(results)

    async def _llm_consolidate(
        self,
        query: str,
        filtered_analyses: List[Dict],
        language: str,
    ) -> str:
        """
        Stage 2: MiniCPM-V로 필터링된 응답 통합

        Args:
            query: 사용자 질문
            filtered_analyses: 필터링된 페이지 분석 결과
            language: 응답 언어

        Returns:
            통합된 응답 문자열
        """
        from app.api.ports.vision_llm_port import VisionTask
        from .language_policy import get_language_policy_service

        # 중앙화된 언어 정책 적용
        lang_service = get_language_policy_service()
        lang_instruction = lang_service.get_language_instruction(language)

        # 페이지별 분석 결과를 텍스트로 구성
        per_page_text = ""
        for i, p in enumerate(filtered_analyses, 1):
            per_page_text += f"\n--- Page {i}: {p['pdf_name']} (p.{p['page_num']}) ---\n"
            per_page_text += p["analysis"]
            per_page_text += "\n"

        # 언어별 통합 프롬프트 (언어 정책 먼저 주입)
        if language == "ja":
            task_prompt = f"""以下のPDFページ分析結果から、質問に最も関連性の高い情報を抽出・統合してください。

質問: {query}

ページ分析結果:
{per_page_text}

指示:
1. 質問に直接関連する情報のみを抽出
2. 関連性の低い情報は除外
3. 出典（ファイル名、ページ番号）を必ず含める
4. 重複情報は統合
5. 箇条書きで整理

出力形式:
### 関連情報
- [内容] (出典: ファイル名, p.XX)"""

        elif language == "ko":
            task_prompt = f"""다음 PDF 페이지 분석 결과에서 질문과 가장 관련 높은 정보를 추출・통합하세요.

질문: {query}

페이지 분석 결과:
{per_page_text}

지시:
1. 질문과 직접 관련된 정보만 추출
2. 관련성 낮은 정보는 제외
3. 출처(파일명, 페이지)를 반드시 포함
4. 중복 정보는 통합
5. 목록 형식으로 정리

출력 형식:
### 관련 정보
- [내용] (출처: 파일명, p.XX)"""

        else:
            task_prompt = f"""Extract and consolidate the most relevant information from the following PDF page analyses.

Question: {query}

Page Analyses:
{per_page_text}

Instructions:
1. Extract only information directly relevant to the question
2. Exclude low-relevance information
3. Always include source (filename, page number)
4. Consolidate duplicate information
5. Format as bullet points

Output Format:
### Relevant Information
- [Content] (Source: filename, p.XX)"""

        # 언어 정책을 최상단에 주입
        consolidation_prompt = f"{lang_instruction}\n\n{task_prompt}"

        try:
            # 텍스트 기반 통합 (이미지 없이)
            # Vision Adapter의 텍스트 전용 호출
            result = await self.vision_adapter.generate_text(
                prompt=consolidation_prompt,
                max_tokens=2048,
            )

            # 출처 정보 추가
            source_info = "\n\n---\n📚 **参照ページ / Referenced Pages:**\n"
            for p in filtered_analyses:
                source_info += f"- {p['pdf_name']} (p.{p['page_num']})\n"

            return result + source_info

        except AttributeError:
            # generate_text가 없으면 이미지 없이 analyze_image 호출 시도
            logger.warning("[VisionKnowledge] generate_text not available, using simple concat")
            return self._simple_concat_responses(filtered_analyses)
        except Exception as e:
            logger.error(f"[VisionKnowledge] LLM consolidation error: {e}")
            return self._simple_concat_responses(filtered_analyses)

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
