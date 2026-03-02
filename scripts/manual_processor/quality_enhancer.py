"""요약본 품질 개선기

Summary Quality Improvement - Phase 2
QualityChecker가 탐지한 문제를 수정합니다:
1. 불완전한 설명 → PDF에서 재추출
2. 중복 항목 → 병합
3. 타입 분류 오류 → 재분류
"""

import re
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from collections import defaultdict

from .models.quality import (
    QualityReport,
    IncompleteItem,
    DuplicateGroup,
    MisclassifiedItem,
    EnhancementResult,
)
from .parsers import PDFParser

logger = logging.getLogger(__name__)


class QualityEnhancer:
    """요약본 품질 개선기"""

    # 설명 추출 컨텍스트 윈도우
    CONTEXT_BEFORE = 100   # 항목 이전 문자
    CONTEXT_AFTER = 2000   # 항목 이후 문자

    # 일본어/영어 설명 패턴
    DESCRIPTION_PATTERNS = [
        # 일본어 정의 패턴
        (r'は[、,]?([^。]+)。', "japanese_definition"),
        (r'は([^。]+ための[^。]+)です。', "japanese_tool"),
        (r'は([^。]+を[^。]+)します。', "japanese_action"),
        (r'とは[、,]?([^。]+)。', "japanese_explanation"),
        # 영문 정의 패턴
        (r'\s+is\s+([^.]+)\.', "english_definition"),
        (r'\s+-\s+([^.]+)\.', "english_dash"),
        (r':\s+([^.]+)\.', "english_colon"),
    ]

    def __init__(
        self,
        pdf_parser: PDFParser,
        summaries_dir: Path,
        manuals_dir: Optional[Path] = None
    ):
        """초기화

        Args:
            pdf_parser: PDF 파서
            summaries_dir: 요약본 디렉토리
            manuals_dir: PDF 매뉴얼 디렉토리
        """
        self.pdf_parser = pdf_parser
        self.summaries_dir = Path(summaries_dir)
        self.manuals_dir = Path(manuals_dir) if manuals_dir else Path("uploads/manuals")

        # PDF 캐시 (파싱 결과 재사용)
        self._pdf_cache: Dict[str, str] = {}

    def enhance_all(
        self,
        report: QualityReport,
        skip_pdf_extraction: bool = False
    ) -> EnhancementResult:
        """모든 품질 문제 수정

        Args:
            report: 품질 검사 리포트
            skip_pdf_extraction: PDF 재추출 건너뛰기

        Returns:
            EnhancementResult: 개선 결과
        """
        result = EnhancementResult()

        # 1. 불완전 설명 수정
        if report.incomplete_items and not skip_pdf_extraction:
            logger.info(f"불완전 설명 수정 중... ({len(report.incomplete_items)}개)")
            fixed = self._fix_incomplete_descriptions(report.incomplete_items)
            result.fixed_incomplete = fixed
            logger.info(f"  수정 완료: {fixed}개")

        # 2. 중복 항목 병합
        if report.duplicate_groups:
            logger.info(f"중복 항목 병합 중... ({len(report.duplicate_groups)}개 그룹)")
            merged = self._merge_all_duplicates(report.duplicate_groups)
            result.merged_duplicates = merged
            logger.info(f"  병합 완료: {merged}개")

        # 3. 타입 재분류
        if report.misclassified_items:
            logger.info(f"타입 재분류 중... ({len(report.misclassified_items)}개)")
            reclassified = self._reclassify_all_types(report.misclassified_items)
            result.reclassified_items = reclassified
            logger.info(f"  재분류 완료: {reclassified}개")

        # 4. learning_dataset.json 재생성
        if result.total_fixed > 0:
            logger.info("learning_dataset.json 재생성 중...")
            self._regenerate_learning_dataset()

        return result

    def _fix_incomplete_descriptions(self, items: List[IncompleteItem]) -> int:
        """불완전한 설명 수정

        Args:
            items: 불완전 항목 목록

        Returns:
            수정된 항목 수
        """
        fixed_count = 0
        updates_by_file: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

        for item in items:
            # PDF에서 설명 추출 시도
            new_description = self._extract_description_from_pdf(
                item.name,
                item.pdf_source
            )

            if new_description and len(new_description) > len(item.description):
                # 마크다운 파일 업데이트 예약
                updates_by_file[item.source_file].append((item.name, new_description))
                fixed_count += 1
                logger.debug(f"  {item.name}: 설명 추출 성공")
            else:
                logger.debug(f"  {item.name}: 설명 추출 실패")

        # 파일별 업데이트 적용
        for source_file, updates in updates_by_file.items():
            self._update_markdown_descriptions(source_file, updates)

        return fixed_count

    def _extract_description_from_pdf(
        self,
        item_name: str,
        pdf_source: Optional[str] = None
    ) -> Optional[str]:
        """PDF에서 항목 설명 추출

        Args:
            item_name: 항목 이름
            pdf_source: 원본 PDF 경로 (힌트)

        Returns:
            추출된 설명 또는 None
        """
        # PDF 파일 찾기
        pdf_files = self._find_related_pdfs(item_name, pdf_source)

        for pdf_path in pdf_files:
            # PDF 텍스트 로드 (캐시 활용)
            text = self._get_pdf_text(pdf_path)
            if not text:
                continue

            # 항목 위치 찾기
            pattern = rf'\b{re.escape(item_name)}\b'
            matches = list(re.finditer(pattern, text, re.IGNORECASE))

            for match in matches:
                # 컨텍스트 추출
                start = match.end()
                end = min(len(text), start + self.CONTEXT_AFTER)
                context = text[start:end]

                # 설명 패턴 추출
                description = self._extract_description_patterns(context, item_name)
                if description:
                    return description

        return None

    def _extract_description_patterns(
        self,
        context: str,
        item_name: str
    ) -> Optional[str]:
        """컨텍스트에서 설명 패턴 추출

        Args:
            context: 항목 이후 텍스트
            item_name: 항목 이름

        Returns:
            추출된 설명 또는 None
        """
        # 항목 이름을 포함한 패턴 시도
        for pattern_suffix, pattern_name in self.DESCRIPTION_PATTERNS:
            full_pattern = rf'{re.escape(item_name)}{pattern_suffix}'
            match = re.search(full_pattern, context, re.IGNORECASE)
            if match:
                description = match.group(0).strip()
                # 최대 500자로 제한
                return description[:500] if len(description) > 500 else description

        # 폴백: 첫 번째 문장
        first_sentence = re.match(r'^[^。.]+[。.]', context.strip())
        if first_sentence:
            desc = first_sentence.group(0).strip()
            if len(desc) > 20:  # 너무 짧은 건 제외
                return desc[:300]

        return None

    def _find_related_pdfs(
        self,
        item_name: str,
        pdf_hint: Optional[str] = None
    ) -> List[Path]:
        """관련 PDF 파일 찾기

        Args:
            item_name: 항목 이름
            pdf_hint: PDF 경로 힌트

        Returns:
            관련 PDF 파일 목록
        """
        pdf_files = []

        # 힌트가 있으면 우선 시도
        if pdf_hint:
            hint_path = self.manuals_dir / pdf_hint
            if hint_path.exists():
                pdf_files.append(hint_path)
            else:
                # 파일명만으로 검색
                hint_name = Path(pdf_hint).name
                for pdf in self.manuals_dir.glob(f"**/{hint_name}"):
                    pdf_files.append(pdf)

        # 항목 이름에서 제품 추론
        product_patterns = [
            (r'^osc', "OSC"),
            (r'^tjes', "TJES"),
            (r'^tacf', "TACF"),
            (r'^hidb', "HIDB"),
            (r'^ndb', "NDB"),
            (r'^of', "OpenFrame"),
        ]

        for pattern, product in product_patterns:
            if re.match(pattern, item_name.lower()):
                for pdf in self.manuals_dir.glob(f"**/*{product}*.pdf"):
                    if pdf not in pdf_files:
                        pdf_files.append(pdf)
                break

        # 최대 5개로 제한
        return pdf_files[:5]

    def _get_pdf_text(self, pdf_path: Path) -> Optional[str]:
        """PDF 텍스트 로드 (캐시 활용)

        Args:
            pdf_path: PDF 경로

        Returns:
            PDF 텍스트 또는 None
        """
        cache_key = str(pdf_path)

        if cache_key in self._pdf_cache:
            return self._pdf_cache[cache_key]

        try:
            content = self.pdf_parser.parse(pdf_path)
            if content:
                text = content.full_text
                self._pdf_cache[cache_key] = text
                return text
        except Exception as e:
            logger.warning(f"PDF 파싱 실패: {pdf_path} - {e}")

        return None

    def _update_markdown_descriptions(
        self,
        source_file: str,
        updates: List[Tuple[str, str]]
    ) -> bool:
        """마크다운 파일의 설명 업데이트

        Args:
            source_file: 소스 파일 경로
            updates: (항목명, 새 설명) 튜플 목록

        Returns:
            성공 여부
        """
        md_path = self.summaries_dir / source_file

        if not md_path.exists():
            logger.warning(f"파일 없음: {md_path}")
            return False

        try:
            content = md_path.read_text(encoding="utf-8")

            for item_name, new_description in updates:
                # - **설명**: 패턴 찾아서 교체
                old_pattern = rf'(##\s+{re.escape(item_name)}.*?-\s*\*\*설명\*\*:\s*)([^\n]+)'
                new_replacement = rf'\g<1>{new_description}'

                content = re.sub(old_pattern, new_replacement, content, flags=re.DOTALL)

            md_path.write_text(content, encoding="utf-8")
            return True

        except Exception as e:
            logger.error(f"마크다운 업데이트 실패: {source_file} - {e}")
            return False

    def _merge_all_duplicates(self, groups: List[DuplicateGroup]) -> int:
        """모든 중복 항목 병합

        Args:
            groups: 중복 그룹 목록

        Returns:
            병합된 항목 수
        """
        merged_count = 0
        items_to_remove: Dict[str, List[str]] = defaultdict(list)

        for group in groups:
            if not group.best_item:
                continue

            # 최상 항목 외의 항목들을 제거 대상으로 표시
            best_name = group.best_item.get("name", "")
            best_source = group.best_item.get("source_file", "")

            for item in group.items:
                item_source = item.get("source_file", "")
                if item_source != best_source:
                    items_to_remove[item_source].append(item.get("name", ""))
                    merged_count += 1

        # 파일별 항목 제거 (주석 처리)
        for source_file, names in items_to_remove.items():
            self._mark_items_as_duplicate(source_file, names)

        return merged_count

    def _mark_items_as_duplicate(
        self,
        source_file: str,
        item_names: List[str]
    ) -> bool:
        """중복 항목 표시 (주석 처리)

        Args:
            source_file: 소스 파일 경로
            item_names: 중복 항목 이름 목록

        Returns:
            성공 여부
        """
        md_path = self.summaries_dir / source_file

        if not md_path.exists():
            return False

        try:
            content = md_path.read_text(encoding="utf-8")

            for name in item_names:
                # 항목 섹션 찾아서 주석 추가
                pattern = rf'(##\s+{re.escape(name)})'
                replacement = rf'<!-- DUPLICATE -->\n\g<1>'
                content = re.sub(pattern, replacement, content)

            md_path.write_text(content, encoding="utf-8")
            return True

        except Exception as e:
            logger.error(f"중복 표시 실패: {source_file} - {e}")
            return False

    def _reclassify_all_types(self, items: List[MisclassifiedItem]) -> int:
        """모든 타입 재분류

        Args:
            items: 분류 오류 항목 목록

        Returns:
            재분류된 항목 수
        """
        reclassified_count = 0
        updates_by_file: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

        for item in items:
            updates_by_file[item.source_file].append((item.name, item.suggested_type))
            reclassified_count += 1

        # 파일별 타입 업데이트
        for source_file, updates in updates_by_file.items():
            self._update_item_types(source_file, updates)

        return reclassified_count

    def _update_item_types(
        self,
        source_file: str,
        updates: List[Tuple[str, str]]
    ) -> bool:
        """항목 타입 업데이트

        Args:
            source_file: 소스 파일 경로
            updates: (항목명, 새 타입) 튜플 목록

        Returns:
            성공 여부
        """
        md_path = self.summaries_dir / source_file

        if not md_path.exists():
            return False

        try:
            content = md_path.read_text(encoding="utf-8")

            for item_name, new_type in updates:
                # - **타입**: 패턴 찾아서 교체
                old_pattern = rf'(##\s+{re.escape(item_name)}.*?-\s*\*\*타입\*\*:\s*)([^\n]+)'
                new_replacement = rf'\g<1>{new_type}'

                content = re.sub(old_pattern, new_replacement, content, flags=re.DOTALL)

            md_path.write_text(content, encoding="utf-8")
            return True

        except Exception as e:
            logger.error(f"타입 업데이트 실패: {source_file} - {e}")
            return False

    def _regenerate_learning_dataset(self) -> bool:
        """learning_dataset.json 재생성

        업데이트된 마크다운 파일들을 기반으로 학습 데이터셋을 재생성합니다.
        """
        try:
            # 기존 파일 백업
            dataset_path = self.summaries_dir / "learning_dataset.json"
            if dataset_path.exists():
                backup_path = self.summaries_dir / "learning_dataset.json.bak"
                dataset_path.rename(backup_path)
                logger.info(f"백업 생성: {backup_path}")

            # 새 데이터셋 생성 (strategy_aware_parser 활용)
            from .parsers.strategy_aware_parser import generate_learning_dataset
            from .config import config

            strategy_file = self.summaries_dir / "strategy_analysis.json"

            if strategy_file.exists():
                stats = generate_learning_dataset(
                    manuals_dir=config.manuals_dir,
                    output_path=dataset_path,
                    strategy_file=strategy_file
                )
                logger.info(f"learning_dataset.json 재생성 완료: {stats['total_items']}개 항목")
                return True
            else:
                logger.warning("strategy_analysis.json 없음 - 재생성 건너뜀")
                return False

        except Exception as e:
            logger.error(f"learning_dataset.json 재생성 실패: {e}")
            return False

    def fix_single_item(
        self,
        item_name: str,
        pdf_source: Optional[str] = None
    ) -> Optional[str]:
        """단일 항목 수정

        Args:
            item_name: 항목 이름
            pdf_source: PDF 소스 힌트

        Returns:
            추출된 새 설명 또는 None
        """
        return self._extract_description_from_pdf(item_name, pdf_source)
