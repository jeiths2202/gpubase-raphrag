"""콘텐츠 파싱 모듈

ChatGPT-Quality Pipeline 개선 (PDCA: chatgpt-quality-pipeline):
- 컨텍스트 윈도우 확장: 200→500자 (이전), 500→1000자 (이후)
"""

import re
import logging
from typing import List, Dict, Optional, Set

from ..models.manual import ManualContent, TOCItem
from ..models.glossary import GlossaryTerm
from ..config import config

logger = logging.getLogger(__name__)


class ContentParser:
    """일반 콘텐츠 파서

    매뉴얼에서 용어, 개념, 컴포넌트 정보를 추출합니다.

    ChatGPT-Quality Pipeline 개선:
    - 컨텍스트 윈도우 확장으로 더 완전한 설명 추출
    """

    # ChatGPT-Quality Pipeline: 확장된 컨텍스트 윈도우
    CONTEXT_BEFORE = 500   # 200 → 500
    CONTEXT_AFTER = 1000   # 500 → 1000

    # 용어 정의 패턴들
    # "TJES（Tmax Job Entry Subsystem）"
    TERM_DEFINITION_PATTERN = re.compile(
        r"(?P<term>[A-Z][A-Za-z0-9]{2,})[（\(](?P<full_name>[^）\)]+)[）\)]"
    )

    # "• obmjschd\nジョブ・スケジューラーです。"
    COMPONENT_PATTERN = re.compile(
        r"[•・]\s*(?P<name>[a-z][a-z0-9_]+)\s*\n(?P<description>[^\n•・]+)"
    )

    # "1.1. 概要" 스타일 섹션
    SECTION_HEADER_PATTERN = re.compile(
        r"^\d+\.\d+\.?\s+(?P<title>.+)$", re.MULTILINE
    )

    # 알려진 용어 목록 (자동 감지용)
    KNOWN_TERMS = {
        "TJES", "TACF", "TSAM", "VSAM", "DSIO", "ICF", "AMS", "DSALC",
        "JCL", "JOB", "STEP", "DD", "PROC", "COBOL", "PL/I",
        "OSC", "OSI", "AIM", "NDB", "RDBII",
        "Tmax", "Tibero", "OpenFrame",
        "SPOOL", "CATALOG", "DATASET", "VOLUME",
        "TSO", "ISPF", "REXX",
    }

    def __init__(self):
        self.terms: Dict[str, GlossaryTerm] = {}
        self.components: List[Dict] = []

    def parse(self, content: ManualContent) -> Dict[str, GlossaryTerm]:
        """매뉴얼에서 용어 추출"""
        self.terms = {}
        source_file = content.metadata.file_name

        # 1. TOC에서 주요 용어 추출
        self._parse_toc(content.metadata.toc, source_file)

        # 2. 본문에서 용어 정의 추출
        self._parse_definitions(content.full_text, source_file)

        # 3. 개요 섹션에서 상세 정보 추출
        self._parse_overview_sections(content, source_file)

        # 4. 컴포넌트 정보 추출
        self._parse_components(content.full_text, source_file)

        logger.info(f"용어 추출 완료: {len(self.terms)}개")
        return self.terms

    def _parse_toc(self, toc: List[TOCItem], source_file: str) -> None:
        """목차에서 주요 용어 추출"""
        for item in toc:
            # "TJESの紹介", "OpenFrame Baseのエラーコード" 등에서 용어 추출
            title = item.title

            # 알려진 용어가 포함되어 있는지 확인
            for known_term in self.KNOWN_TERMS:
                if known_term in title:
                    self._add_or_update_term(
                        known_term,
                        source_file=source_file
                    )

    def _parse_definitions(self, text: str, source_file: str) -> None:
        """본문에서 용어 정의 추출"""
        # "TJES（Tmax Job Entry Subsystem）" 패턴
        for match in self.TERM_DEFINITION_PATTERN.finditer(text):
            term = match.group("term")
            full_name = match.group("full_name")

            # 문맥 추출 (용어 정의 전후 텍스트) - ChatGPT-Quality Pipeline 확장
            start = max(0, match.start() - self.CONTEXT_BEFORE)
            end = min(len(text), match.end() + self.CONTEXT_AFTER)
            context = text[start:end]

            description = self._extract_description_from_context(context, term)

            self._add_or_update_term(
                term,
                full_name=full_name,
                description=description,
                source_file=source_file
            )

    def _parse_overview_sections(self, content: ManualContent, source_file: str) -> None:
        """개요 섹션에서 상세 정보 추출"""
        # "概要", "紹介", "特徴" 섹션 찾기
        overview_keywords = ["概要", "紹介", "特徴", "構成要素"]

        for toc_item in content.metadata.toc:
            for keyword in overview_keywords:
                if keyword in toc_item.title:
                    section_text = content.get_section_by_toc(toc_item)
                    if section_text:
                        self._extract_features_from_section(section_text, source_file)
                    break

    def _extract_features_from_section(self, section_text: str, source_file: str) -> None:
        """섹션에서 기능 목록 추출"""
        # 불릿 포인트 패턴: "• ", "・", "◦"
        bullet_pattern = re.compile(r"[•・◦]\s*(.+?)(?=[•・◦\n]|$)")

        features = []
        for match in bullet_pattern.finditer(section_text):
            feature = match.group(1).strip()
            if len(feature) > 10:  # 너무 짧은 건 제외
                features.append(feature)

        # 해당 섹션의 주제 용어 찾기
        for term in self.terms.values():
            if term.term in section_text:
                term.features.extend(features[:10])  # 최대 10개
                term.source_files.append(source_file)

    def _parse_components(self, text: str, source_file: str) -> None:
        """컴포넌트 정보 추출"""
        # "• obmjschd\nジョブ・スケジューラーです。" 패턴
        for match in self.COMPONENT_PATTERN.finditer(text):
            name = match.group("name")
            description = match.group("description").strip()

            component = {
                "name": name,
                "description": description,
                "source_file": source_file
            }
            self.components.append(component)

            # 컴포넌트도 용어로 등록
            self._add_or_update_term(
                name,
                description=description,
                source_file=source_file
            )

    def _add_or_update_term(
        self,
        term: str,
        full_name: str = "",
        description: str = "",
        source_file: str = "",
        product: str = ""
    ) -> None:
        """용어 추가 또는 업데이트"""
        if term in self.terms:
            existing = self.terms[term]
            if full_name and not existing.full_name:
                existing.full_name = full_name
            if description and not existing.description:
                existing.description = description
            if source_file and source_file not in existing.source_files:
                existing.source_files.append(source_file)
        else:
            self.terms[term] = GlossaryTerm(
                term=term,
                full_name=full_name,
                description=description,
                source_files=[source_file] if source_file else [],
                product=product
            )

    def _extract_description_from_context(self, context: str, term: str) -> str:
        """문맥에서 설명 추출"""
        # 용어 정의 이후 첫 문장 또는 "です。" "ます。"로 끝나는 부분 찾기
        patterns = [
            rf"{term}[^。]*は[、,]([^。]+。)",  # "TJESは、〜です。"
            rf"{term}[^。]*です。([^。]+。)?",   # "〜です。〜"
            rf"以下[、,]([^。]+。)",              # "以下、〜です。"
        ]

        for pattern in patterns:
            match = re.search(pattern, context)
            if match:
                desc = match.group(0).strip()
                if len(desc) > 20:
                    # ChatGPT-Quality Pipeline: 설명 길이 제한 완화 (200→500)
                    return desc[:500]

        return ""

    def extract_related_terms(self, term: GlossaryTerm, all_terms: Dict[str, GlossaryTerm]) -> List[str]:
        """관련 용어 추출"""
        related = []

        # 같은 소스 파일에서 정의된 용어
        for other_term, other in all_terms.items():
            if other_term == term.term:
                continue

            # 같은 파일 참조
            common_files = set(term.source_files) & set(other.source_files)
            if common_files:
                related.append(other_term)

            # 설명에 다른 용어가 포함
            if other_term in term.description:
                related.append(other_term)

        return list(set(related))[:10]  # 최대 10개
