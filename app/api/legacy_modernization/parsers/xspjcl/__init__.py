"""XSP JCL C 파서 통합 패키지.

OF7 xspjcl C 파서의 모든 기능을 Python에서 사용할 수 있는 어댑터 패턴 구현.

패키지 구성:
  - models.py: C 파서 출력을 위한 Pydantic 모델 (43 stmt + 21 errors + params + relex + instream)
  - wrapper.py: ctypes 래퍼 (libxspjcl_kms.so 로드 + JSON 변환)
  - converter.py: XSPParseResult → ParserResult(NormalizedFeature + ASTNode) 변환
  - __init__.py: XSPParserAdapter (JCLParser 통합용 어댑터)

사용법:
    from app.api.legacy_modernization.parsers.xspjcl import XSPParserAdapter

    adapter = XSPParserAdapter()
    if adapter.is_c_parser_available:
        result = await adapter.parse(source, file_path)
        # result.features: NormalizedFeature 목록
        # result.ast: ASTNode 트리
"""

import logging
from typing import List, Optional

from ..base import ParserResult
from .converter import XSPResultConverter
from .models import XSPParseResult
from .wrapper import XSPJCLCWrapper

logger = logging.getLogger(__name__)

__all__ = [
    "XSPParserAdapter",
    "XSPJCLCWrapper",
    "XSPResultConverter",
    "XSPParseResult",
]


class XSPParserAdapter:
    """XSP JCL C 파서 어댑터.

    C 파서 가용 시: C 파서 호출 → JSON → XSPParseResult → ParserResult
    C 파서 불가 시: Python regex 폴백 (기존 JCLParser._parse_xsp)

    JCLParser에서 XSP 방언 감지 시 이 어댑터를 통해 파싱.
    """

    def __init__(self) -> None:
        self._wrapper = XSPJCLCWrapper.get_instance()

    @property
    def is_c_parser_available(self) -> bool:
        """C 파서 라이브러리 가용 여부."""
        return self._wrapper.is_available

    @property
    def parser_version(self) -> str:
        """C 파서 버전."""
        return self._wrapper.version()

    async def parse(
        self, source: str, file_path: str = "<string>"
    ) -> Optional[ParserResult]:
        """XSP JCL 소스를 C 파서로 파싱.

        C 파서 사용 불가 시 None을 반환하여 호출자가 폴백을 처리하도록 함.

        Args:
            source: XSP JCL 소스 코드
            file_path: 소스 파일 경로 (SYSIN 상대경로 해석용)

        Returns:
            ParserResult or None (C 파서 불가 시)
        """
        if not self._wrapper.is_available:
            logger.debug("C parser not available, returning None for fallback")
            return None

        try:
            # C 파서 호출 (모든 기능: macro, SYSIN, instream, relex, errors, stream)
            xsp_result = self._wrapper.parse(source, flags=1)

            # ParserResult로 변환
            converter = XSPResultConverter(file_path=file_path)
            return converter.convert(xsp_result, source=source)

        except RuntimeError as e:
            logger.warning("C parser failed: %s, falling back", e)
            return None

    async def parse_file(
        self, file_path: str
    ) -> Optional[ParserResult]:
        """XSP JCL 파일을 C 파서로 파싱.

        파일 기반 파싱은 SYSIN 포함 시 상대경로 해석이 가능.

        Args:
            file_path: XSP JCL 소스 파일 경로

        Returns:
            ParserResult or None (C 파서 불가 시)
        """
        if not self._wrapper.is_available:
            return None

        try:
            xsp_result = self._wrapper.parse_file(file_path, flags=1)

            # 소스 읽기 (trace evidence용)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    source = f.read()
            except (OSError, UnicodeDecodeError):
                source = ""

            converter = XSPResultConverter(file_path=file_path)
            return converter.convert(xsp_result, source=source)

        except RuntimeError as e:
            logger.warning("C parser failed for file %s: %s", file_path, e)
            return None

    def get_raw_parse_result(
        self, source: str, flags: int = 1
    ) -> Optional[XSPParseResult]:
        """C 파서의 raw 결과를 직접 반환 (변환 없이).

        디버깅, 테스트, 또는 C 파서 결과를 직접 사용하고 싶을 때.
        """
        if not self._wrapper.is_available:
            return None
        try:
            return self._wrapper.parse(source, flags=flags)
        except RuntimeError:
            return None
