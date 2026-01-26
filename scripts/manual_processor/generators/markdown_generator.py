"""Markdown 생성 모듈"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

from ..models.error_code import ErrorCodeModule
from ..models.glossary import GlossaryTerm, GlossarySection
from ..config import config

logger = logging.getLogger(__name__)


class MarkdownGenerator:
    """Markdown 파일 생성기"""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or config.summaries_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_error_codes(
        self,
        modules: Dict[str, ErrorCodeModule],
        language: str = "ja"
    ) -> List[Path]:
        """에러 코드 마크다운 파일 생성"""
        error_dir = self.output_dir / "error-codes"
        error_dir.mkdir(parents=True, exist_ok=True)

        generated_files = []

        for module_name, module in modules.items():
            content = module.to_markdown(language)
            file_path = error_dir / module.filename

            file_path.write_text(content, encoding="utf-8")
            generated_files.append(file_path)
            logger.info(f"에러 코드 파일 생성: {file_path}")

        # 인덱스 파일 생성
        index_path = self._generate_error_index(modules, error_dir, language)
        generated_files.append(index_path)

        return generated_files

    def _generate_error_index(
        self,
        modules: Dict[str, ErrorCodeModule],
        error_dir: Path,
        language: str
    ) -> Path:
        """에러 코드 인덱스 파일 생성"""
        lines = [
            "---",
            "type: error-codes-index",
            f"language: {language}",
            f"generated: {datetime.now().isoformat()}",
            f"module_count: {len(modules)}",
            "---",
            "",
            "# 에러 코드 인덱스",
            "",
            "OpenFrame 에러 코드 참조입니다. 에러 번호로 검색하세요.",
            "",
            "## 모듈별 에러 범위",
            "",
            "| 모듈 | 범위 | 설명 | 에러 수 |",
            "|------|------|------|--------|",
        ]

        # 범위 순으로 정렬
        sorted_modules = sorted(modules.values(), key=lambda m: m.range_start)

        for module in sorted_modules:
            desc = module.description[:50] + "..." if len(module.description) > 50 else module.description
            lines.append(
                f"| [{module.module_name}]({module.filename}) | {module.range_str} | {desc} | {len(module.errors)} |"
            )

        lines.extend([
            "",
            "## 빠른 검색",
            "",
            "에러 코드로 빠르게 찾기:",
            "",
            "- `-5212` → [DSALC](BASE-5000.md)에서 검색",
            "- `-1001` → [TSAM](BASE-1000.md)에서 검색",
            "",
        ])

        index_path = error_dir / "index.md"
        index_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"에러 인덱스 생성: {index_path}")

        return index_path

    def generate_glossary(
        self,
        terms: Dict[str, GlossaryTerm],
        language: str = "ja"
    ) -> List[Path]:
        """용어 사전 마크다운 파일 생성"""
        glossary_dir = self.output_dir / "glossary"
        glossary_dir.mkdir(parents=True, exist_ok=True)

        generated_files = []

        # 첫 글자별로 그룹화
        sections: Dict[str, GlossarySection] = defaultdict(
            lambda: GlossarySection(letter="", language=language)
        )

        for term_name, term in terms.items():
            letter = term.first_letter
            if letter not in sections:
                sections[letter] = GlossarySection(letter=letter, language=language)
            sections[letter].add_term(term)

        # 각 섹션 파일 생성
        for letter, section in sorted(sections.items()):
            if not section.terms:
                continue

            content = section.to_markdown()
            file_path = glossary_dir / section.filename

            file_path.write_text(content, encoding="utf-8")
            generated_files.append(file_path)
            logger.info(f"용어 파일 생성: {file_path} ({len(section.terms)}개 용어)")

        # 인덱스 파일 생성
        index_path = self._generate_glossary_index(sections, glossary_dir, language)
        generated_files.append(index_path)

        return generated_files

    def _generate_glossary_index(
        self,
        sections: Dict[str, GlossarySection],
        glossary_dir: Path,
        language: str
    ) -> Path:
        """용어 사전 인덱스 파일 생성"""
        total_terms = sum(len(s.terms) for s in sections.values())

        lines = [
            "---",
            "type: glossary-index",
            f"language: {language}",
            f"generated: {datetime.now().isoformat()}",
            f"total_terms: {total_terms}",
            "---",
            "",
            "# 용어 사전 인덱스",
            "",
            "OpenFrame 용어 사전입니다. 알파벳 또는 용어명으로 검색하세요.",
            "",
            "## 알파벳별 바로가기",
            "",
        ]

        # 알파벳 링크
        letters = sorted(s for s in sections.keys() if sections[s].terms)
        links = [f"[{l}]({l}.md)" for l in letters]
        lines.append(" | ".join(links))
        lines.append("")

        # 전체 용어 목록
        lines.extend([
            "## 전체 용어 목록",
            "",
            "| 용어 | 정식명칭 | 제품군 |",
            "|------|----------|--------|",
        ])

        all_terms = []
        for section in sections.values():
            all_terms.extend(section.terms)

        for term in sorted(all_terms, key=lambda t: t.term.upper()):
            full_name = term.full_name or "-"
            product = term.product or "-"
            letter = term.first_letter
            lines.append(f"| [{term.term}]({letter}.md#{term.term.lower()}) | {full_name} | {product} |")

        index_path = glossary_dir / "index.md"
        index_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"용어 인덱스 생성: {index_path}")

        return index_path

    def generate_product_summary(
        self,
        product_id: str,
        product_info: Dict,
        related_files: List[str],
        language: str = "ja"
    ) -> Path:
        """제품 요약 마크다운 파일 생성"""
        products_dir = self.output_dir / "products"
        products_dir.mkdir(parents=True, exist_ok=True)

        lines = [
            "---",
            "type: product",
            f"product_id: {product_id}",
            f"language: {language}",
            f"generated: {datetime.now().isoformat()}",
            "source_files:",
        ]
        for f in related_files[:10]:
            lines.append(f"  - {f}")
        lines.extend([
            "---",
            "",
            f"# {product_info.get('name', product_id)}",
            "",
            "## 개요",
            product_info.get("description", ""),
            "",
        ])

        # 컴포넌트
        if product_info.get("components"):
            lines.extend([
                "## 주요 컴포넌트",
                "",
                "| 컴포넌트 | 설명 |",
                "|---------|------|",
            ])
            for comp in product_info["components"]:
                lines.append(f"| {comp} | - |")
            lines.append("")

        # 관련 매뉴얼
        if related_files:
            lines.extend([
                "## 관련 매뉴얼",
                "",
            ])
            for f in related_files:
                lines.append(f"- {f}")
            lines.append("")

        file_path = products_dir / f"{product_id.lower()}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"제품 요약 생성: {file_path}")

        return file_path
