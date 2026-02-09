"""
Template Response Builder

정형 질문(명령어, 에러코드, 설정)에 대한 Markdown 템플릿 기반 응답 생성.
LLM을 사용하지 않으므로 환각(Hallucination)이 0%입니다.
"""
import logging
import re
from typing import List, Optional

from ..models.agentic_rag import QueryType
from .structured_knowledge_store import SearchResult, enrich_content_with_tables

logger = logging.getLogger(__name__)


_METADATA_PREFIXES = (
    '製品/product', '**製品/product',
    '出典/source', '**出典/source',
)

# 섹션 번호 패턴: "1.3." "1.3.1" 등으로 시작하는 행 → 마크다운 헤딩으로
_SECTION_NUM_RE = re.compile(r'^(\d+(?:\.\d+)+\.?)\s+(.+)')
# 불릿 마커: ●, •, ■, ▶, ◆, ○, ▪ → 마크다운 불릿
_BULLET_CHARS = set('●•■▶◆○▪◇►')
# 일본어 문장 종결 후 줄바꿈 보장 패턴
_JP_SENTENCE_END = re.compile(r'(。)\s*(?=[^\n])')


def format_as_markdown(text: str) -> str:
    """
    PDF 원문 텍스트를 깔끔한 Markdown으로 변환.

    변환 규칙:
    - ● ■ ▶ 등 → '- ' (마크다운 불릿)
    - "1.3. 제목" → "#### 1.3. 제목" (서브헤딩)
    - 일본어 문장 종결(。) 후 줄바꿈 보장
    - 연속 공백 정리, 빈 행 중복 제거
    """
    if not text:
        return text

    lines = text.split('\n')
    result: list = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        # 코드블록 (```) 내부는 변환하지 않고 그대로 유지
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            result.append(line)
            continue

        if in_code_block:
            result.append(line)
            continue

        if not stripped:
            result.append('')
            continue

        # 1) 섹션 번호 행 → 마크다운 헤딩
        m = _SECTION_NUM_RE.match(stripped)
        if m:
            num, title = m.group(1), m.group(2)
            depth = num.count('.')
            level = min(depth + 2, 5)  # 1.→h3, 1.1.→h4, 1.1.1.→h5
            result.append('')
            result.append(f"{'#' * level} {num} {title}")
            result.append('')
            continue

        # 2) 불릿 마커로 시작하는 행 → 마크다운 불릿
        if stripped[0] in _BULLET_CHARS:
            body = stripped[1:].strip()
            result.append(f"- {body}")
            continue

        # 3) 일반 텍스트: 인라인 불릿 분리 (文末。●次の文 → 줄 분리)
        # "。  ●" 패턴이 있으면 분리
        parts = re.split(r'(?<=。)\s*(?=[●•■▶◆○▪])', stripped)
        if len(parts) > 1:
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                if p[0] in _BULLET_CHARS:
                    result.append(f"- {p[1:].strip()}")
                else:
                    result.append(p)
            continue

        result.append(stripped)

    # 후처리: 3줄 이상 연속 빈 줄 → 2줄로
    output = '\n'.join(result)
    output = re.sub(r'\n{3,}', '\n\n', output)
    return output.strip()


class TemplateResponseBuilder:
    """
    정형 질문 템플릿 응답 생성기

    특징:
    - LLM 없음 → 환각 0%
    - 검색 결과를 Markdown 형식으로 포맷팅
    - 질문 유형별 다른 템플릿 적용
    """

    @staticmethod
    def _clean_content(content: str) -> str:
        """인라인 메타데이터 행(製品/Product, 出典/Source) 제거"""
        lines = content.split('\n')
        cleaned = [l for l in lines if not l.strip().lower().startswith(_METADATA_PREFIXES)]
        return '\n'.join(cleaned).strip()

    def build(
        self,
        query: str,
        query_type: QueryType,
        results: List[SearchResult],
        language: str = "ja",
    ) -> Optional[str]:
        """
        템플릿 기반 응답 생성

        Args:
            query: 사용자 쿼리
            query_type: 질문 유형
            results: 구조화 검색 결과
            language: UI 언어

        Returns:
            Markdown 형식 응답 또는 None (결과 없음)
        """
        if not results:
            return None

        # PDF 우선: PDF 결과가 있으면 요약본/학습데이터 제외
        pdf_results = [r for r in results if r.domain == "pdf_manuals"]
        if pdf_results:
            results = pdf_results

        if query_type == QueryType.COMMAND:
            return self._build_command_response(results, language)
        elif query_type == QueryType.ERROR_CODE:
            return self._build_error_code_response(results, language)
        elif query_type == QueryType.PARAMETER:
            return self._build_parameter_response(results, language)
        elif query_type == QueryType.CONFIG:
            return self._build_config_response(results, language)
        else:
            return None  # FREEFORM은 LLM 처리

    def _build_section(self, r: SearchResult) -> str:
        """공통 섹션 빌드: 콘텐츠 정리 + 마크다운 변환 + 출처"""
        content = format_as_markdown(self._clean_content(enrich_content_with_tables(r)))
        section = f"### {r.title}\n\n{content}"
        if r.source_file:
            section += f"\n\n> 出典: {r.source_file}"
            if r.source_page:
                section += f" ({r.source_page})"
        return section

    def _build_command_response(
        self,
        results: List[SearchResult],
        language: str,
    ) -> str:
        """명령어 응답 템플릿"""
        return "\n\n---\n\n".join(self._build_section(r) for r in results[:3])

    def _build_error_code_response(
        self,
        results: List[SearchResult],
        language: str,
    ) -> str:
        """에러코드 응답 템플릿"""
        return "\n\n---\n\n".join(self._build_section(r) for r in results[:3])

    def _build_parameter_response(
        self,
        results: List[SearchResult],
        language: str,
    ) -> str:
        """파라미터 응답 템플릿"""
        return "\n\n---\n\n".join(self._build_section(r) for r in results[:3])

    def _build_config_response(
        self,
        results: List[SearchResult],
        language: str,
    ) -> str:
        """설정 파일 응답 템플릿"""
        return "\n\n---\n\n".join(self._build_section(r) for r in results[:3])


# Singleton
_builder_instance: Optional[TemplateResponseBuilder] = None


def get_template_response_builder() -> TemplateResponseBuilder:
    """Get singleton TemplateResponseBuilder"""
    global _builder_instance
    if _builder_instance is None:
        _builder_instance = TemplateResponseBuilder()
    return _builder_instance
