"""에러 코드 파싱 모듈"""

import re
import logging
from typing import List, Dict, Optional, Tuple

from ..models.manual import ManualContent
from ..models.error_code import ErrorCode, ErrorCodeModule
from ..config import config

logger = logging.getLogger(__name__)


class ErrorCodeParser:
    """에러 코드 파서

    Error Reference Guide PDF에서 에러 코드를 추출합니다.
    """

    # 에러 코드 패턴: MODULE_ERR_NAME (-1234)
    ERROR_PATTERN = re.compile(
        r"(?P<name>[A-Z][A-Z0-9_]+_ERR_[A-Z0-9_]+)\s*\((?P<code>-?\d+)\)"
    )

    # 섹션 헤더 패턴: 1.7. DSALC (-5000)
    # 점선(. . .)이 뒤따르지 않는 본문 섹션만 매칭 (목차 제외)
    # Non-VSAM 등 하이픈이 포함된 모듈명도 지원
    SECTION_PATTERN = re.compile(
        r"^\d+\.\d+\.?\s*(?P<module>[A-Za-z][A-Za-z0-9_-]+)\s*\((?P<code>-?\d+)\)\s*$",
        re.MULTILINE
    )

    # 설명/대처방법 패턴
    DESCRIPTION_PATTERN = re.compile(r"説明\s*\n(.+?)(?=対処方法|$)", re.DOTALL)
    SOLUTION_PATTERN = re.compile(r"対処方法\s*\n(.+?)(?=参考|[A-Z].*_ERR_|$)", re.DOTALL)
    REFERENCE_PATTERN = re.compile(r"参考\s*\n(.+?)(?=[A-Z].*_ERR_|\d+\.\d+\.|$)", re.DOTALL)

    def __init__(self):
        self.modules: Dict[str, ErrorCodeModule] = {}

    def parse(self, content: ManualContent) -> Dict[str, ErrorCodeModule]:
        """에러 참조 가이드에서 에러 코드 추출"""
        if not content.metadata.is_error_guide:
            logger.warning(f"에러 가이드가 아닙니다: {content.metadata.file_name}")
            return {}

        self.modules = {}
        full_text = content.full_text
        source_file = content.metadata.file_name

        # 모듈별 섹션 분리
        sections = self._split_sections(full_text)

        for module_name, section_text in sections.items():
            module = self._parse_module_section(module_name, section_text, source_file)
            if module and module.errors:
                self.modules[module_name] = module
                logger.info(f"모듈 파싱 완료: {module_name} ({len(module.errors)}개 에러)")

        return self.modules

    def _split_sections(self, text: str) -> Dict[str, str]:
        """텍스트를 모듈별 섹션으로 분리"""
        sections = {}

        # 섹션 헤더 위치 찾기
        matches = list(self.SECTION_PATTERN.finditer(text))

        for i, match in enumerate(matches):
            module_name = match.group("module")
            start_pos = match.start()

            # 다음 섹션까지 또는 끝까지
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(text)

            section_text = text[start_pos:end_pos]
            sections[module_name] = section_text

        return sections

    def _parse_module_section(
        self,
        module_name: str,
        section_text: str,
        source_file: str
    ) -> Optional[ErrorCodeModule]:
        """모듈 섹션에서 에러 코드 추출"""
        # 모듈 정보 가져오기
        module_info = config.error_code_modules.get(module_name)
        if not module_info:
            # 알려지지 않은 모듈도 처리
            logger.warning(f"알 수 없는 모듈: {module_name}")
            range_start, range_end = self._guess_module_range(module_name, section_text)
            prefix = "UNKNOWN"
        else:
            range_start, range_end = module_info["range"]
            prefix = module_info["prefix"]

        # 모듈 설명 추출 (첫 문단)
        description = self._extract_module_description(section_text)

        module = ErrorCodeModule(
            module_name=module_name,
            range_start=range_start,
            range_end=range_end,
            description=description,
            prefix=prefix,
            source_files=[source_file]
        )

        # 개별 에러 코드 추출
        errors = self._extract_errors(section_text, source_file)
        for error in errors:
            module.add_error(error)

        return module

    def _extract_module_description(self, section_text: str) -> str:
        """모듈 설명 추출"""
        # 첫 줄 이후 첫 번째 에러 코드 이전까지의 텍스트
        lines = section_text.split("\n")
        description_lines = []

        started = False
        for line in lines:
            # 섹션 헤더 건너뛰기
            if self.SECTION_PATTERN.match(line):
                started = True
                continue

            if not started:
                continue

            # 에러 코드 시작하면 종료
            if self.ERROR_PATTERN.search(line):
                break

            line = line.strip()
            if line and not line.startswith("|"):
                description_lines.append(line)

        return " ".join(description_lines[:3])  # 최대 3줄

    def _extract_errors(self, section_text: str, source_file: str) -> List[ErrorCode]:
        """섹션에서 에러 코드 추출"""
        errors = []

        # 에러 코드 위치 찾기
        matches = list(self.ERROR_PATTERN.finditer(section_text))

        for i, match in enumerate(matches):
            error_name = match.group("name")
            error_code = int(match.group("code"))

            # 해당 에러의 설명 범위 (다음 에러까지)
            start_pos = match.end()
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(section_text)

            error_text = section_text[start_pos:end_pos]

            # 설명, 대처방법, 참고 추출
            description = self._extract_field(error_text, self.DESCRIPTION_PATTERN)
            solution = self._extract_field(error_text, self.SOLUTION_PATTERN)
            reference = self._extract_field(error_text, self.REFERENCE_PATTERN)

            error = ErrorCode(
                code=error_code,
                name=error_name,
                description=description,
                solution=solution,
                reference=reference,
                source_file=source_file
            )
            errors.append(error)

        return errors

    def _extract_field(self, text: str, pattern: re.Pattern) -> str:
        """정규식 패턴으로 필드 추출"""
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            # 정제
            value = re.sub(r"\s+", " ", value)
            value = value.strip()
            # 너무 길면 자르기
            if len(value) > 500:
                value = value[:500] + "..."
            return value
        return ""

    def _guess_module_range(self, module_name: str, section_text: str) -> Tuple[int, int]:
        """알 수 없는 모듈의 범위 추측"""
        codes = [int(m.group("code")) for m in self.ERROR_PATTERN.finditer(section_text)]
        if codes:
            min_code = min(abs(c) for c in codes)
            max_code = max(abs(c) for c in codes)
            # 1000 단위로 정렬
            range_start = (min_code // 1000) * 1000
            range_end = range_start + 999
            return range_start, range_end
        return 0, 999

    def find_error(self, code: int) -> Optional[ErrorCode]:
        """에러 코드로 검색"""
        code = abs(code)
        for module in self.modules.values():
            error = module.find_error(code)
            if error:
                return error
        return None

    def get_module_for_code(self, code: int) -> Optional[ErrorCodeModule]:
        """에러 코드의 모듈 반환"""
        code = abs(code)
        for module in self.modules.values():
            if module.range_start <= code <= module.range_end:
                return module
        return None
