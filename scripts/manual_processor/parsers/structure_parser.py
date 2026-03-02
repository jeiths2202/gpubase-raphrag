"""
PDF 구조 파서

PDF 문서의 계층적 구조(Chapter/Section/Subsection)를 추출합니다.
"""

import re
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

import pymupdf

from ..models.document_structure import (
    DocumentStructure, HierarchyNode, ImageReference, NodeType
)
from ..models.manual import ManualContent, TOCItem
from ..config import config

logger = logging.getLogger(__name__)


class StructureParser:
    """PDF 문서 구조 파서

    TOC(목차)를 기반으로 계층적 구조를 추출하고,
    각 섹션의 요약과 키워드를 생성합니다.
    """

    # Level 1: Chapter 패턴
    CHAPTER_PATTERNS = [
        (r"^第(\d+)章\s+(.+)$", "chapter"),           # 第1章 タイトル
        (r"^Chapter\s+(\d+)[.:]?\s*(.+)$", "chapter"),
        (r"^CHAPTER\s+(\d+)[.:]?\s*(.+)$", "chapter"),
        (r"^付録\s*([A-Z])[.:]?\s*(.+)$", "appendix"), # 付録 A.
        (r"^Appendix\s+([A-Z])[.:]?\s*(.+)$", "appendix"),
        (r"^APPENDIX\s+([A-Z])[.:]?\s*(.+)$", "appendix"),
    ]

    # Level 2: Section 패턴
    SECTION_PATTERNS = [
        r"^(\d+)\.(\d+)[.:]?\s+(.+)$",    # 1.2. Title
        r"^([A-Z])\.(\d+)[.:]?\s+(.+)$",  # A.1. Title
    ]

    # Level 3: Subsection 패턴
    SUBSECTION_PATTERNS = [
        r"^(\d+)\.(\d+)\.(\d+)[.:]?\s+(.+)$",  # 1.2.3. Title
        r"^([A-Z])\.(\d+)\.(\d+)[.:]?\s+(.+)$",  # A.1.2. Title
    ]

    # Level 4: Paragraph 패턴
    PARAGRAPH_PATTERNS = [
        r"^(\d+)\.(\d+)\.(\d+)\.(\d+)[.:]?\s+(.+)$",  # 1.2.3.4. Title
    ]

    # 이미지 참조 패턴
    IMAGE_PATTERNS = [
        (r"\[図\s*(\d+[.\-]?\d*)\]\s*([^\n]*)", "figure"),
        (r"図\s*(\d+[.\-]?\d*)[:\s]*([^\n]{0,100})", "figure"),
        (r"\[表\s*(\d+[.\-]?\d*)\]\s*([^\n]*)", "table"),
        (r"表\s*(\d+[.\-]?\d*)[:\s]*([^\n]{0,100})", "table"),
        (r"\[Figure\s+([A-Z]?\d+[.\-]?\d*)\]\s*([^\n]*)", "figure"),
        (r"Figure\s+([A-Z]?\d+[.\-]?\d*)[:\s]*([^\n]{0,100})", "figure"),
        (r"\[Table\s+([A-Z]?\d+[.\-]?\d*)\]\s*([^\n]*)", "table"),
        (r"Table\s+([A-Z]?\d+[.\-]?\d*)[:\s]*([^\n]{0,100})", "table"),
    ]

    # 키워드 추출용 기술 용어 패턴
    KEYWORD_PATTERNS = [
        r"\b([A-Z]{2,}[A-Z0-9]*)\b",  # 대문자 약어 (TJES, VSAM, etc.)
        r"\b([a-z]+(?:init|boot|down|start|stop|mgr|ctl|cmd))\b",  # 명령어
        r"\b(tjes[a-z]*|osc[a-z]*|tac[a-z]*)\b",  # OpenFrame 명령어
    ]

    def __init__(self, language: str = "ja"):
        self.language = language

    def parse(self, pdf_path: Path) -> Optional[DocumentStructure]:
        """PDF 파일을 파싱하여 DocumentStructure 반환

        Args:
            pdf_path: PDF 파일 경로

        Returns:
            DocumentStructure 객체 또는 None
        """
        if not pdf_path.exists():
            logger.error(f"파일을 찾을 수 없습니다: {pdf_path}")
            return None

        try:
            doc = pymupdf.open(str(pdf_path))
            total_pages = len(doc)

            # TOC 추출
            toc = doc.get_toc()
            toc_items = [TOCItem(level=item[0], title=item[1], page=item[2]) for item in toc]

            logger.info(f"TOC 항목 {len(toc_items)}개 발견: {pdf_path.name}")

            # 계층 구조 생성
            hierarchy = self._build_hierarchy(doc, toc_items)

            # 페이지 범위 계산
            self._calculate_page_ranges(hierarchy, total_pages)

            # 이미지 참조 추출
            images_index = self._extract_all_image_references(doc)

            # 이미지를 적절한 노드에 할당
            self._assign_images_to_nodes(hierarchy, images_index)

            # 요약 및 키워드 생성
            self._generate_summaries_and_keywords(hierarchy, doc)

            # 검증
            validation = self._validate_structure(hierarchy, toc_items)

            doc.close()

            # DocumentStructure 생성
            structure = DocumentStructure(
                title=self._extract_title(pdf_path, toc_items),
                file_name=pdf_path.name,
                file_path=pdf_path,
                version=self._extract_version(pdf_path.name),
                total_pages=total_pages,
                language=self.language,
                hierarchy=hierarchy,
                images_index=images_index,
                validation=validation,
                processing_log={
                    "toc_count": len(toc_items),
                    "hierarchy_count": sum(self._count_nodes(node) for node in hierarchy),
                    "images_count": len(images_index),
                }
            )

            logger.info(f"구조 추출 완료: {pdf_path.name} "
                       f"(노드: {structure.count_all_nodes()}, "
                       f"이미지: {len(images_index)}, "
                       f"검증: {validation.get('valid', False)})")

            return structure

        except Exception as e:
            logger.error(f"PDF 구조 파싱 실패: {pdf_path} - {e}")
            import traceback
            traceback.print_exc()
            return None

    def _build_hierarchy(
        self, doc: pymupdf.Document, toc_items: List[TOCItem]
    ) -> List[HierarchyNode]:
        """TOC 항목에서 계층 구조 생성"""
        if not toc_items:
            # TOC가 없으면 텍스트에서 제목 패턴 추출
            return self._build_hierarchy_from_text(doc)

        hierarchy = []
        stack: List[HierarchyNode] = []  # 현재 계층의 부모 노드 스택
        node_counter = 0

        for item in toc_items:
            node_counter += 1
            node_id = f"node_{node_counter}"

            # 노드 타입 결정
            node_type = self._determine_node_type(item.title, item.level)

            # 노드 생성
            node = HierarchyNode(
                id=node_id,
                level=item.level,
                node_type=node_type,
                title=item.title.strip(),
                page_start=item.page,
            )

            # 계층 구조에 추가
            if item.level == 1:
                # 최상위 레벨
                hierarchy.append(node)
                stack = [node]
            else:
                # 적절한 부모 찾기
                while stack and stack[-1].level >= item.level:
                    stack.pop()

                if stack:
                    parent = stack[-1]
                    node.parent_id = parent.id
                    parent.children.append(node)
                else:
                    # 부모가 없으면 최상위에 추가
                    hierarchy.append(node)

                stack.append(node)

        return hierarchy

    def _build_hierarchy_from_text(self, doc: pymupdf.Document) -> List[HierarchyNode]:
        """텍스트에서 제목 패턴을 추출하여 계층 구조 생성 (TOC 없는 경우)"""
        hierarchy = []
        node_counter = 0
        stack: List[HierarchyNode] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()

            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                # 제목 패턴 확인
                level, title, node_type = self._match_title_pattern(line)
                if level is None:
                    continue

                node_counter += 1
                node = HierarchyNode(
                    id=f"node_{node_counter}",
                    level=level,
                    node_type=node_type,
                    title=title,
                    page_start=page_num + 1,
                )

                # 계층 구조에 추가
                if level == 1:
                    hierarchy.append(node)
                    stack = [node]
                else:
                    while stack and stack[-1].level >= level:
                        stack.pop()

                    if stack:
                        parent = stack[-1]
                        node.parent_id = parent.id
                        parent.children.append(node)
                    else:
                        hierarchy.append(node)

                    stack.append(node)

        return hierarchy

    def _match_title_pattern(self, line: str) -> Tuple[Optional[int], str, NodeType]:
        """제목 패턴 매칭"""
        # Level 1: Chapter
        for pattern, type_str in self.CHAPTER_PATTERNS:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                groups = match.groups()
                title = groups[-1] if len(groups) > 1 else groups[0]
                node_type = NodeType.APPENDIX if type_str == "appendix" else NodeType.CHAPTER
                return 1, title.strip(), node_type

        # Level 2: Section
        for pattern in self.SECTION_PATTERNS:
            match = re.match(pattern, line)
            if match:
                groups = match.groups()
                title = groups[-1]
                return 2, title.strip(), NodeType.SECTION

        # Level 3: Subsection
        for pattern in self.SUBSECTION_PATTERNS:
            match = re.match(pattern, line)
            if match:
                groups = match.groups()
                title = groups[-1]
                return 3, title.strip(), NodeType.SUBSECTION

        # Level 4: Paragraph
        for pattern in self.PARAGRAPH_PATTERNS:
            match = re.match(pattern, line)
            if match:
                groups = match.groups()
                title = groups[-1]
                return 4, title.strip(), NodeType.PARAGRAPH

        return None, "", NodeType.PARAGRAPH

    def _determine_node_type(self, title: str, level: int) -> NodeType:
        """TOC 항목의 노드 타입 결정"""
        title_lower = title.lower()

        # 부록 확인
        if any(kw in title_lower for kw in ["付録", "appendix"]):
            return NodeType.APPENDIX

        # 레벨에 따른 기본 타입
        if level == 1:
            return NodeType.CHAPTER
        elif level == 2:
            return NodeType.SECTION
        elif level == 3:
            return NodeType.SUBSECTION
        else:
            return NodeType.PARAGRAPH

    def _calculate_page_ranges(
        self, hierarchy: List[HierarchyNode], total_pages: int
    ) -> None:
        """각 노드의 페이지 범위 계산"""
        all_nodes = []

        def collect_nodes(nodes: List[HierarchyNode]):
            for node in nodes:
                all_nodes.append(node)
                collect_nodes(node.children)

        collect_nodes(hierarchy)

        # 시작 페이지 순으로 정렬
        sorted_nodes = sorted(all_nodes, key=lambda n: n.page_start)

        for i, node in enumerate(sorted_nodes):
            if i + 1 < len(sorted_nodes):
                # 다음 노드의 시작 페이지 - 1
                node.page_end = sorted_nodes[i + 1].page_start - 1
                if node.page_end < node.page_start:
                    node.page_end = node.page_start
            else:
                # 마지막 노드
                node.page_end = total_pages

    def _extract_all_image_references(
        self, doc: pymupdf.Document
    ) -> List[ImageReference]:
        """문서에서 모든 이미지 참조 추출"""
        images = []
        seen_refs = set()  # 중복 방지

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()

            for pattern, ref_type in self.IMAGE_PATTERNS:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    ref_id = match.group(1)
                    caption = match.group(2).strip() if len(match.groups()) > 1 else ""

                    # 중복 확인
                    key = f"{ref_type}_{ref_id}_{page_num + 1}"
                    if key in seen_refs:
                        continue
                    seen_refs.add(key)

                    # 컨텍스트 추출 (매칭 위치 주변 100자)
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end].replace("\n", " ").strip()

                    images.append(ImageReference(
                        ref_type=ref_type,
                        ref_id=ref_id,
                        caption=caption[:200],  # 캡션 길이 제한
                        page_number=page_num + 1,
                        context=context[:150],
                    ))

        return images

    def _assign_images_to_nodes(
        self, hierarchy: List[HierarchyNode], images: List[ImageReference]
    ) -> None:
        """이미지를 해당 노드에 할당"""
        all_nodes = []

        def collect_nodes(nodes: List[HierarchyNode]):
            for node in nodes:
                all_nodes.append(node)
                collect_nodes(node.children)

        collect_nodes(hierarchy)

        for img in images:
            # 이미지가 속하는 노드 찾기
            for node in all_nodes:
                if node.page_start <= img.page_number <= node.page_end:
                    node.images.append(img)
                    node.has_images = True
                    break

    def _generate_summaries_and_keywords(
        self, hierarchy: List[HierarchyNode], doc: pymupdf.Document
    ) -> None:
        """각 노드의 요약과 키워드 생성"""
        def process_node(node: HierarchyNode):
            # 해당 페이지 범위의 텍스트 추출
            text = self._get_page_text(doc, node.page_start, node.page_end)
            node.raw_text = text[:5000]  # 저장용으로 5000자 제한

            # 요약 생성 (첫 300자, 문장 경계에서 자름)
            if text:
                summary = self._generate_summary(text)
                node.summary = summary

            # 키워드 추출
            keywords = self._extract_keywords(text, node.title)
            node.keywords = keywords[:7]  # 최대 7개

            # 자식 노드 처리
            for child in node.children:
                process_node(child)

        for node in hierarchy:
            process_node(node)

    def _get_page_text(
        self, doc: pymupdf.Document, start: int, end: int
    ) -> str:
        """페이지 범위의 텍스트 추출"""
        texts = []
        for page_num in range(start - 1, min(end, len(doc))):
            page = doc[page_num]
            texts.append(page.get_text())
        return "\n".join(texts)

    def _generate_summary(self, text: str, max_length: int = 300) -> str:
        """텍스트 요약 생성 (첫 문장들 추출)"""
        # 정리
        text = re.sub(r'\s+', ' ', text).strip()

        if len(text) <= max_length:
            return text

        # 문장 경계에서 자르기
        sentences = re.split(r'[。.!?]\s*', text)
        summary = ""

        for sentence in sentences:
            if len(summary) + len(sentence) + 1 > max_length:
                break
            if summary:
                summary += "。" if self.language == "ja" else ". "
            summary += sentence

        return summary.strip() or text[:max_length]

    def _extract_keywords(self, text: str, title: str) -> List[str]:
        """텍스트에서 키워드 추출 (CJK 지원)

        변경: 영문만 추출하던 로직을 CJK 언어 지원으로 확장
        - 일본어: fugashi(MeCab) 기반 명사/동사 추출
        - 한국어: 2자 이상 연속 한글 추출
        - 영문: 기존 대문자 약어 패턴 유지
        """
        try:
            from app.api.services.cjk_tokenizer_service import get_cjk_tokenizer_service

            tokenizer = get_cjk_tokenizer_service()
            keywords = tokenizer.extract_all_keywords(
                text=text,
                title=title,
                min_frequency=2 if len(text) > 1000 else 1
            )
            return keywords[:7]  # 최대 7개

        except ImportError:
            # Fallback: 기존 영문만 추출 로직
            logger.warning("[StructureParser] CJKTokenizerService not available, using English-only extraction")
            return self._extract_keywords_english_only(text, title)

    def _extract_keywords_english_only(self, text: str, title: str) -> List[str]:
        """기존 영문 전용 키워드 추출 (fallback)"""
        keywords = set()

        # 제목에서 키워드 추출
        title_words = re.findall(r'\b[A-Z][a-z]+\b|\b[A-Z]{2,}\b', title)
        keywords.update(title_words)

        # 텍스트에서 키워드 추출
        for pattern in self.KEYWORD_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            # 빈도 계산
            freq = {}
            for m in matches:
                m_upper = m.upper()
                freq[m_upper] = freq.get(m_upper, 0) + 1

            # 빈도 높은 것 추가
            for kw, count in sorted(freq.items(), key=lambda x: -x[1])[:5]:
                if len(kw) >= 2 and count >= 2:  # 2회 이상 등장한 것만
                    keywords.add(kw)

        # 너무 일반적인 단어 제거
        common_words = {"THE", "AND", "FOR", "NOT", "ARE", "ALL", "WITH", "THIS", "THAT"}
        keywords = keywords - common_words

        return sorted(list(keywords))[:7]

    def _validate_structure(
        self, hierarchy: List[HierarchyNode], toc_items: List[TOCItem]
    ) -> Dict[str, Any]:
        """구조 검증"""
        extracted_count = sum(self._count_nodes(node) for node in hierarchy)

        # 매칭 확인
        matched = 0
        missing = []

        for toc_item in toc_items:
            found = self._find_node_by_title(hierarchy, toc_item.title)
            if found:
                matched += 1
            else:
                missing.append(toc_item.title)

        coverage_ratio = matched / len(toc_items) if toc_items else 1.0

        return {
            "toc_items": len(toc_items),
            "extracted_items": extracted_count,
            "matched_items": matched,
            "missing_items": missing[:10],  # 최대 10개만 기록
            "coverage_ratio": round(coverage_ratio, 3),
            "valid": coverage_ratio >= 0.9,
        }

    def _count_nodes(self, node: HierarchyNode) -> int:
        """노드 수 계산"""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count

    def _find_node_by_title(
        self, hierarchy: List[HierarchyNode], title: str
    ) -> Optional[HierarchyNode]:
        """제목으로 노드 검색"""
        for node in hierarchy:
            if node.title == title:
                return node
            found = self._find_node_by_title(node.children, title)
            if found:
                return found
        return None

    def _extract_title(self, pdf_path: Path, toc_items: List[TOCItem]) -> str:
        """문서 제목 추출"""
        # 파일명에서 추출
        name = pdf_path.stem
        # 언더스코어를 공백으로
        name = name.replace("_", " ")
        # 버전 정보 제거
        name = re.sub(r'\s*v[\d.]+\s*', ' ', name)
        return name.strip()

    def _extract_version(self, filename: str) -> str:
        """파일명에서 버전 추출"""
        match = re.search(r'v([\d.]+)', filename)
        return match.group(1) if match else ""
