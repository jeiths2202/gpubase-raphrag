"""요약본 품질 검사기

Summary Quality Improvement - Phase 1
세 가지 품질 문제를 탐지합니다:
1. 불완전한 설명 (장 번호만 있는 항목)
2. 중복 항목 (같은 이름의 여러 항목)
3. 타입 분류 오류 (command 패턴이지만 concept으로 분류)
"""

import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
from collections import defaultdict

from .models.quality import (
    QualityReport,
    IncompleteItem,
    DuplicateGroup,
    MisclassifiedItem,
    QualityIssueType,
)

logger = logging.getLogger(__name__)


class QualityChecker:
    """요약본 품질 검사기"""

    # 불완전 설명 패턴 (장 번호만 있는 경우)
    INCOMPLETE_PATTERNS = [
        (r'^[\d.]+\s+[a-zA-Z_]+$', "chapter_number_only"),           # "8.30. osctdlrm"
        (r'^[\d.]+\s*$', "number_only"),                              # "8.30"
        (r'^第[\d]+章', "japanese_chapter"),                          # "第8章"
        (r'^Chapter\s+\d+', "english_chapter"),                       # "Chapter 8"
        (r'^\d+\.\d+\.\d+\.?\s*$', "section_number"),                # "8.30.1"
        (r'^[\d.]+\s+[A-Z][a-z]+$', "chapter_with_name"),            # "8.30 Osctdlrm"
        (r'^表\s*[\d.]+', "table_reference"),                         # "表 8.1"
        (r'^図\s*[\d.]+', "figure_reference"),                        # "図 8.1"
    ]

    # 명령어 패턴 (concept으로 분류되면 안됨)
    COMMAND_PATTERNS = [
        (r'^[a-z]+mgr$', "manager_command"),              # tjesmgr, oscmgr, hidbmgr
        (r'^[a-z]+admin$', "admin_command"),              # oscadmin
        (r'^[a-z]+(init|rm|ctl)$', "utility_command"),    # osctdlinit, osctdlrm
        (r'^[a-z]+boot$', "boot_command"),                # oscboot, tjesboot
        (r'^[a-z]+down$', "down_command"),                # oscdown, tjesdown
        (r'^\$[A-Z]+', "system_variable"),                # $DISPLAY, $START
        (r'^(tmboot|tmdown|ofboot|ofdown)$', "system_command"),  # 시스템 명령어
        (r'^(idcams|iebgener|iebcopy|dfsort)$', "utility"),  # 유틸리티
        (r'^(dsmigin|dsmigout|dscreate)$', "dataset_command"),  # 데이터셋 명령
        (r'^(jesinit|jesdown)$', "jes_command"),          # JES 명령어
        (r'^(cobrun|prorun)$', "runtime_command"),        # 런타임 명령
    ]

    # 최소 설명 길이 (이보다 짧으면 불완전으로 간주)
    MIN_DESCRIPTION_LENGTH = 15

    def __init__(self, summaries_dir: Optional[Path] = None):
        """초기화

        Args:
            summaries_dir: 요약본 디렉토리 경로
        """
        self.summaries_dir = summaries_dir or Path("uploads/summaries")

    def check_all(self, summaries_dir: Optional[Path] = None) -> QualityReport:
        """모든 품질 검사 수행

        Args:
            summaries_dir: 요약본 디렉토리 (기본: self.summaries_dir)

        Returns:
            QualityReport: 품질 검사 리포트
        """
        if summaries_dir:
            self.summaries_dir = summaries_dir

        logger.info(f"품질 검사 시작: {self.summaries_dir}")

        # 모든 항목 로드
        all_items = self._load_all_items()
        logger.info(f"총 {len(all_items)}개 항목 로드됨")

        # 품질 검사 수행
        incomplete_items = self.check_incomplete_descriptions(all_items)
        duplicate_groups = self.check_duplicates(all_items)
        misclassified_items = self.check_type_classification(all_items)

        # 리포트 생성
        report = QualityReport(
            total_items=len(all_items),
            incomplete_items=incomplete_items,
            duplicate_groups=duplicate_groups,
            misclassified_items=misclassified_items,
            scan_timestamp=datetime.now().isoformat(),
            summaries_dir=str(self.summaries_dir),
        )

        logger.info(f"품질 검사 완료: 점수 {report.quality_score:.1f}%")
        logger.info(f"  - 불완전 설명: {report.incomplete_count}개")
        logger.info(f"  - 중복 항목: {report.duplicate_count}개")
        logger.info(f"  - 분류 오류: {report.misclassified_count}개")

        return report

    def _load_all_items(self) -> List[dict]:
        """모든 요약본 항목 로드

        learning_dataset.json 또는 index.json에서 로드
        """
        items = []

        # learning_dataset.json 우선 시도
        dataset_path = self.summaries_dir / "learning_dataset.json"
        if dataset_path.exists():
            try:
                with open(dataset_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict) and "items" in data:
                        items = data["items"]
                logger.info(f"learning_dataset.json에서 {len(items)}개 항목 로드")
                return items
            except Exception as e:
                logger.warning(f"learning_dataset.json 로드 실패: {e}")

        # index.json 시도
        index_path = self.summaries_dir / "index.json"
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items = data.get("items", [])
                logger.info(f"index.json에서 {len(items)}개 항목 로드")
                return items
            except Exception as e:
                logger.warning(f"index.json 로드 실패: {e}")

        # 마크다운 파일 직접 파싱
        items = self._parse_markdown_files()
        return items

    def _parse_markdown_files(self) -> List[dict]:
        """마크다운 파일에서 항목 파싱"""
        items = []
        md_dirs = ["commands", "configs", "apis", "concepts", "glossary"]

        for dir_name in md_dirs:
            dir_path = self.summaries_dir / dir_name
            if not dir_path.exists():
                continue

            for md_file in dir_path.glob("*.md"):
                file_items = self._parse_single_markdown(md_file, dir_name)
                items.extend(file_items)

        logger.info(f"마크다운 파일에서 {len(items)}개 항목 파싱됨")
        return items

    def _parse_single_markdown(self, md_path: Path, category: str) -> List[dict]:
        """단일 마크다운 파일 파싱"""
        items = []
        try:
            content = md_path.read_text(encoding="utf-8")

            # ## 항목명 패턴으로 항목 추출
            pattern = r'^##\s+(.+?)$'
            matches = list(re.finditer(pattern, content, re.MULTILINE))

            for i, match in enumerate(matches):
                name = match.group(1).strip()

                # 다음 항목까지의 내용 추출
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                section_content = content[start:end].strip()

                # 설명 추출 (- **설명**: 패턴)
                desc_match = re.search(r'-\s*\*\*설명\*\*:\s*(.+?)(?:\n|$)', section_content)
                description = desc_match.group(1).strip() if desc_match else ""

                # 타입 결정
                item_type = self._determine_type_from_category(category, name)

                items.append({
                    "name": name,
                    "description": description,
                    "type": item_type,
                    "source_file": str(md_path.relative_to(self.summaries_dir)),
                    "category": category,
                })

        except Exception as e:
            logger.error(f"마크다운 파싱 실패: {md_path} - {e}")

        return items

    def _determine_type_from_category(self, category: str, name: str) -> str:
        """카테고리와 이름으로 타입 결정"""
        category_type_map = {
            "commands": "command",
            "configs": "config",
            "apis": "api",
            "concepts": "concept",
            "glossary": "term",
            "error-codes": "error",
        }
        return category_type_map.get(category, "concept")

    def check_incomplete_descriptions(self, items: List[dict]) -> List[IncompleteItem]:
        """불완전한 설명 검출

        Args:
            items: 검사할 항목 목록

        Returns:
            불완전한 항목 목록
        """
        incomplete = []

        for item in items:
            name = item.get("name", "")
            description = item.get("description", "")
            source_file = item.get("source_file", "")
            item_type = item.get("type", "concept")

            # 빈 설명
            if not description or description.strip() == "":
                incomplete.append(IncompleteItem(
                    name=name,
                    description="",
                    source_file=source_file,
                    item_type=item_type,
                    pattern_matched="empty_description",
                ))
                continue

            # 너무 짧은 설명
            if len(description.strip()) < self.MIN_DESCRIPTION_LENGTH:
                # 단, 유효한 짧은 설명은 제외 (예: "削除する", "起動する")
                if not self._is_valid_short_description(description):
                    incomplete.append(IncompleteItem(
                        name=name,
                        description=description,
                        source_file=source_file,
                        item_type=item_type,
                        pattern_matched="too_short",
                    ))
                    continue

            # 불완전 패턴 매칭
            for pattern, pattern_name in self.INCOMPLETE_PATTERNS:
                if re.match(pattern, description.strip()):
                    incomplete.append(IncompleteItem(
                        name=name,
                        description=description,
                        source_file=source_file,
                        item_type=item_type,
                        pattern_matched=pattern_name,
                    ))
                    break

        logger.info(f"불완전 설명 {len(incomplete)}개 검출")
        return incomplete

    def _is_valid_short_description(self, description: str) -> bool:
        """짧지만 유효한 설명인지 확인"""
        # 동사로 끝나는 일본어 설명은 유효
        valid_endings = ["する", "です", "ます", "ある", "なる", "れる"]
        for ending in valid_endings:
            if description.strip().endswith(ending):
                return True
        return False

    def check_duplicates(self, items: List[dict]) -> List[DuplicateGroup]:
        """중복 항목 검출

        Args:
            items: 검사할 항목 목록

        Returns:
            중복 그룹 목록
        """
        # 이름별 항목 그룹화
        name_groups: Dict[str, List[dict]] = defaultdict(list)

        for item in items:
            name = item.get("name", "").lower().strip()
            if name:
                name_groups[name].append(item)

        # 중복 그룹 생성
        duplicate_groups = []

        for name, group_items in name_groups.items():
            if len(group_items) > 1:
                # 가장 완전한 항목 선택
                best_item = self._select_best_item(group_items)

                duplicate_groups.append(DuplicateGroup(
                    name=name,
                    items=group_items,
                    best_item=best_item,
                    merge_strategy="keep_best",
                ))

        logger.info(f"중복 그룹 {len(duplicate_groups)}개 검출")
        return duplicate_groups

    def _select_best_item(self, items: List[dict]) -> dict:
        """가장 완전한 항목 선택

        기준:
        1. 설명 길이
        2. syntax 정보 유무
        3. type이 command인 항목 우선
        """
        def score_item(item: dict) -> Tuple[int, int, int]:
            desc_len = len(item.get("description", ""))
            has_syntax = 1 if item.get("syntax") else 0
            is_command = 1 if item.get("type") == "command" else 0
            return (desc_len, has_syntax, is_command)

        return max(items, key=score_item)

    def check_type_classification(self, items: List[dict]) -> List[MisclassifiedItem]:
        """타입 분류 오류 검출

        Args:
            items: 검사할 항목 목록

        Returns:
            분류 오류 항목 목록
        """
        misclassified = []

        for item in items:
            name = item.get("name", "")
            current_type = item.get("type", "concept")
            source_file = item.get("source_file", "")

            # concept으로 분류된 항목 중 command 패턴과 매칭되는지 확인
            if current_type == "concept":
                for pattern, pattern_name in self.COMMAND_PATTERNS:
                    if re.match(pattern, name, re.IGNORECASE):
                        misclassified.append(MisclassifiedItem(
                            name=name,
                            current_type=current_type,
                            suggested_type="command",
                            pattern_matched=pattern_name,
                            confidence=0.9,
                            source_file=source_file,
                        ))
                        break

        logger.info(f"분류 오류 {len(misclassified)}개 검출")
        return misclassified

    def check_category(
        self,
        category: str,
        summaries_dir: Optional[Path] = None
    ) -> QualityReport:
        """특정 카테고리만 검사

        Args:
            category: 검사할 카테고리 (commands, configs, apis, concepts)
            summaries_dir: 요약본 디렉토리

        Returns:
            QualityReport
        """
        if summaries_dir:
            self.summaries_dir = summaries_dir

        # 해당 카테고리 항목만 로드
        all_items = self._load_all_items()
        category_items = [
            item for item in all_items
            if item.get("category") == category or
               category in item.get("source_file", "")
        ]

        logger.info(f"{category} 카테고리: {len(category_items)}개 항목")

        # 검사 수행
        incomplete_items = self.check_incomplete_descriptions(category_items)
        duplicate_groups = self.check_duplicates(category_items)
        misclassified_items = self.check_type_classification(category_items)

        return QualityReport(
            total_items=len(category_items),
            incomplete_items=incomplete_items,
            duplicate_groups=duplicate_groups,
            misclassified_items=misclassified_items,
            scan_timestamp=datetime.now().isoformat(),
            summaries_dir=str(self.summaries_dir),
        )

    def generate_summary(self, report: QualityReport) -> str:
        """품질 리포트 요약 문자열 생성"""
        lines = [
            "=" * 50,
            "요약본 품질 검사 리포트",
            "=" * 50,
            f"검사 시간: {report.scan_timestamp}",
            f"검사 대상: {report.summaries_dir}",
            "",
            f"총 항목 수: {report.total_items:,}개",
            f"품질 점수: {report.quality_score:.1f}% ",
            "",
            "--- 이슈 요약 ---",
            f"불완전 설명: {report.incomplete_count}개",
            f"중복 항목: {report.duplicate_count}개 ({len(report.duplicate_groups)}개 그룹)",
            f"분류 오류: {report.misclassified_count}개",
            f"총 이슈: {report.total_issues}개",
            "",
        ]

        # 주요 불완전 항목 (최대 10개)
        if report.incomplete_items:
            lines.append("--- 주요 불완전 항목 (최대 10개) ---")
            for item in report.incomplete_items[:10]:
                lines.append(f"  - {item.name}: \"{item.description[:30]}...\" ({item.pattern_matched})")
            if len(report.incomplete_items) > 10:
                lines.append(f"  ... 외 {len(report.incomplete_items) - 10}개")
            lines.append("")

        # 중복 그룹
        if report.duplicate_groups:
            lines.append("--- 중복 그룹 ---")
            for group in report.duplicate_groups[:10]:
                sources = [item.get("source_file", "")[:20] for item in group.items[:3]]
                lines.append(f"  - {group.name}: {len(group.items)}회 ({', '.join(sources)})")
            if len(report.duplicate_groups) > 10:
                lines.append(f"  ... 외 {len(report.duplicate_groups) - 10}개 그룹")
            lines.append("")

        # 분류 오류
        if report.misclassified_items:
            lines.append("--- 분류 오류 ---")
            for item in report.misclassified_items[:10]:
                lines.append(f"  - {item.name}: {item.current_type} → {item.suggested_type} ({item.pattern_matched})")
            if len(report.misclassified_items) > 10:
                lines.append(f"  ... 외 {len(report.misclassified_items) - 10}개")

        lines.append("=" * 50)
        return "\n".join(lines)
