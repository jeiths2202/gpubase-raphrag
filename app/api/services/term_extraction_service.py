"""
Term Extraction Service

Service for automatically extracting potentially ambiguous terms from
uploaded documents. Extracted terms become candidates for admin review.

Extraction methods:
1. Pattern-based: Regex patterns for known product names, acronyms
2. Frequency-based: Statistically significant uppercase terms
3. Context-based: Terms that appear in technical contexts
"""
import logging
import re
from collections import Counter
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field

from ..infrastructure.postgres.ambiguous_term_repository import (
    PostgresAmbiguousTermRepository,
)
from ..infrastructure.postgres.term_candidate_repository import (
    PostgresTermCandidateRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractedTerm:
    """Represents a term extracted from a document."""
    term: str
    term_normalized: str
    extraction_context: str  # 앞뒤 문맥 (~100자)
    extraction_method: str  # pattern, frequency, context
    confidence_score: float  # 0.0 ~ 1.0
    suggested_category: Optional[str] = None
    occurrence_count: int = 1
    positions: List[int] = field(default_factory=list)


class TermExtractionService:
    """
    Service for extracting ambiguous term candidates from documents.

    Provides:
    - Pattern-based extraction for known products/acronyms
    - Frequency-based extraction for significant terms
    - Context-aware extraction for technical terminology
    """

    # 제품명 패턴 (Tmax 제품군)
    PRODUCT_PATTERNS = [
        # Tmax 제품군
        r'\b(JEUS|Tmax|Tibero|OpenFrame|ProObject|ProBuilder|AnyLink)\b',
        r'\b(WebtoB|WBSM|Tuxedo)\b',
        # 일반적인 약어 패턴 (2-5자 대문자)
        r'\b([A-Z]{2,5})\b',
        # 대문자로 시작하는 복합어 (CamelCase)
        r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b',
    ]

    # 기술 용어 패턴
    TECH_PATTERNS = [
        r'\b(WebAdmin|Manager|Server|Agent|Monitor|Console|Client)\b',
        r'\b(Domain|Node|Cluster|Container|Instance|Pool)\b',
        r'\b(Session|Thread|Connection|Transaction|Request|Response)\b',
    ]

    # 문맥 키워드 (이 키워드 근처의 대문자 단어는 추출 대상)
    CONTEXT_KEYWORDS = [
        '설정', '에러', '오류', '문제', '방법', '가이드',
        'config', 'error', 'issue', 'problem', 'guide', 'setup',
        '실행', '시작', '중지', '재시작', 'start', 'stop', 'restart',
    ]

    # 제외할 일반 단어
    EXCLUDED_TERMS = {
        # 일반적인 약어
        'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL',
        'CAN', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'HAS', 'HIS',
        # 일반적인 기술 용어 (모호하지 않음)
        'API', 'URL', 'HTTP', 'HTTPS', 'HTML', 'CSS', 'JSON', 'XML',
        'SQL', 'TCP', 'UDP', 'IP', 'DNS', 'SSL', 'TLS', 'SSH', 'FTP',
        'CPU', 'RAM', 'SSD', 'HDD', 'GPU', 'USB', 'PDF', 'PNG', 'JPG',
        # 단위
        'MB', 'GB', 'TB', 'KB', 'MS', 'KB',
        # 시간
        'AM', 'PM',
        # 기타
        'OK', 'ID', 'UI', 'UX', 'OS', 'VM', 'DB',
    }

    # 카테고리 매핑 (패턴별 제안 카테고리)
    CATEGORY_MAPPING = {
        'JEUS': 'product_component',
        'Tmax': 'product_component',
        'Tibero': 'product_component',
        'OpenFrame': 'product_component',
        'WebAdmin': 'product_component',
        'Manager': 'product_component',
        'Server': 'product_component',
        'MFS': 'product_feature',
        'TP': 'technology',
    }

    def __init__(
        self,
        ambiguous_term_repo: PostgresAmbiguousTermRepository,
        term_candidate_repo: PostgresTermCandidateRepository,
    ):
        """
        Initialize with repositories.

        Args:
            ambiguous_term_repo: Repository for existing ambiguous terms
            term_candidate_repo: Repository for term candidates
        """
        self.ambiguous_term_repo = ambiguous_term_repo
        self.term_candidate_repo = term_candidate_repo

        # 컴파일된 정규식 패턴
        self._product_patterns = [re.compile(p, re.IGNORECASE) for p in self.PRODUCT_PATTERNS]
        self._tech_patterns = [re.compile(p) for p in self.TECH_PATTERNS]
        self._context_pattern = re.compile(
            r'\b(' + '|'.join(self.CONTEXT_KEYWORDS) + r')\b',
            re.IGNORECASE
        )

    async def extract_from_document(
        self,
        document_id: str,
        document_name: str,
        content: str,
        min_confidence: float = 0.3,
    ) -> List[ExtractedTerm]:
        """
        Extract potentially ambiguous terms from document content.

        Args:
            document_id: Source document ID
            document_name: Source document name
            content: Document text content
            min_confidence: Minimum confidence threshold (default 0.3)

        Returns:
            List of extracted terms above confidence threshold
        """
        candidates: List[ExtractedTerm] = []

        # 1. 패턴 기반 추출
        pattern_candidates = self._extract_by_patterns(content)
        candidates.extend(pattern_candidates)

        # 2. 빈도 기반 추출 (자주 등장하는 대문자 단어)
        frequency_candidates = self._extract_by_frequency(content)
        candidates.extend(frequency_candidates)

        # 3. 문맥 기반 추출 (기술 키워드 근처의 용어)
        context_candidates = self._extract_by_context(content)
        candidates.extend(context_candidates)

        # 4. 중복 제거 및 병합
        merged_candidates = self._merge_candidates(candidates)

        # 5. 기존 용어와 비교하여 필터링
        filtered_candidates = await self._filter_existing_terms(merged_candidates)

        # 6. 최소 신뢰도 이상만 반환
        result = [c for c in filtered_candidates if c.confidence_score >= min_confidence]

        logger.info(
            f"Extracted {len(result)} term candidates from document {document_id}"
        )

        return result

    async def extract_and_save(
        self,
        document_id: str,
        document_name: str,
        content: str,
        min_confidence: float = 0.3,
    ) -> List[int]:
        """
        Extract terms and save to term_candidates table.

        Args:
            document_id: Source document ID
            document_name: Source document name
            content: Document text content
            min_confidence: Minimum confidence threshold

        Returns:
            List of created candidate IDs
        """
        extracted = await self.extract_from_document(
            document_id, document_name, content, min_confidence
        )

        if not extracted:
            return []

        # 후보들을 DB에 저장
        candidates_data = [
            {
                "term": term.term,
                "source_document_id": document_id,
                "source_document_name": document_name,
                "extraction_context": term.extraction_context,
                "extraction_method": term.extraction_method,
                "confidence_score": term.confidence_score,
                "suggested_category": term.suggested_category,
            }
            for term in extracted
        ]

        candidate_ids = await self.term_candidate_repo.create_batch(candidates_data)

        logger.info(
            f"Saved {len(candidate_ids)} term candidates from document {document_id}"
        )

        return candidate_ids

    def _extract_by_patterns(self, content: str) -> List[ExtractedTerm]:
        """
        Extract terms using regex patterns.

        Args:
            content: Document content

        Returns:
            List of pattern-matched terms
        """
        candidates = []
        found_terms: Set[str] = set()

        # 제품명 패턴
        for pattern in self._product_patterns:
            for match in pattern.finditer(content):
                term = match.group(1)
                term_normalized = term.lower().strip()

                # 중복 및 제외 단어 필터링
                if term_normalized in found_terms:
                    continue
                if term.upper() in self.EXCLUDED_TERMS:
                    continue

                found_terms.add(term_normalized)

                # 문맥 추출
                context = self._extract_context(content, match.start(), match.end())

                # 신뢰도 계산 (알려진 제품명은 높은 신뢰도)
                confidence = self._calculate_pattern_confidence(term, context)

                # 카테고리 제안
                category = self.CATEGORY_MAPPING.get(term, 'product_component')

                candidates.append(ExtractedTerm(
                    term=term,
                    term_normalized=term_normalized,
                    extraction_context=context,
                    extraction_method='pattern',
                    confidence_score=confidence,
                    suggested_category=category,
                    positions=[match.start()],
                ))

        # 기술 용어 패턴
        for pattern in self._tech_patterns:
            for match in pattern.finditer(content):
                term = match.group(1)
                term_normalized = term.lower().strip()

                if term_normalized in found_terms:
                    continue

                found_terms.add(term_normalized)

                context = self._extract_context(content, match.start(), match.end())
                confidence = 0.5  # 기술 용어는 중간 신뢰도
                category = self.CATEGORY_MAPPING.get(term, 'technology')

                candidates.append(ExtractedTerm(
                    term=term,
                    term_normalized=term_normalized,
                    extraction_context=context,
                    extraction_method='pattern',
                    confidence_score=confidence,
                    suggested_category=category,
                    positions=[match.start()],
                ))

        return candidates

    def _extract_by_frequency(self, content: str) -> List[ExtractedTerm]:
        """
        Extract terms based on frequency analysis.

        Args:
            content: Document content

        Returns:
            List of frequently occurring terms
        """
        candidates = []

        # 대문자 단어 추출 (2-6자)
        uppercase_pattern = re.compile(r'\b([A-Z]{2,6})\b')
        matches = uppercase_pattern.findall(content)

        # 빈도 계산
        term_counts = Counter(matches)

        # 최소 3회 이상 등장하는 용어만
        for term, count in term_counts.items():
            if count < 3:
                continue

            # 제외 단어 필터링
            if term in self.EXCLUDED_TERMS:
                continue

            term_normalized = term.lower().strip()

            # 첫 번째 출현 위치의 문맥
            first_match = re.search(rf'\b{term}\b', content)
            if first_match:
                context = self._extract_context(
                    content, first_match.start(), first_match.end()
                )
            else:
                context = ""

            # 빈도 기반 신뢰도 (3회=0.3, 10회이상=0.7)
            confidence = min(0.7, 0.1 * count)

            candidates.append(ExtractedTerm(
                term=term,
                term_normalized=term_normalized,
                extraction_context=context,
                extraction_method='frequency',
                confidence_score=confidence,
                suggested_category=None,
                occurrence_count=count,
            ))

        return candidates

    def _extract_by_context(self, content: str) -> List[ExtractedTerm]:
        """
        Extract terms based on surrounding context keywords.

        Args:
            content: Document content

        Returns:
            List of context-identified terms
        """
        candidates = []
        found_terms: Set[str] = set()

        # 문맥 키워드 주변의 대문자 단어 찾기
        for match in self._context_pattern.finditer(content):
            # 키워드 앞뒤 50자 범위에서 대문자 단어 찾기
            start = max(0, match.start() - 50)
            end = min(len(content), match.end() + 50)
            window = content[start:end]

            # 대문자 단어 추출
            terms = re.findall(r'\b([A-Z][A-Za-z]{2,15})\b', window)

            for term in terms:
                term_normalized = term.lower().strip()

                if term_normalized in found_terms:
                    continue
                if term.upper() in self.EXCLUDED_TERMS:
                    continue

                found_terms.add(term_normalized)

                # 원본 위치에서 문맥 추출
                term_match = re.search(rf'\b{term}\b', content)
                if term_match:
                    context = self._extract_context(
                        content, term_match.start(), term_match.end()
                    )
                else:
                    context = window

                candidates.append(ExtractedTerm(
                    term=term,
                    term_normalized=term_normalized,
                    extraction_context=context,
                    extraction_method='context',
                    confidence_score=0.4,  # 문맥 기반은 중간 신뢰도
                    suggested_category=None,
                ))

        return candidates

    def _extract_context(
        self,
        content: str,
        start: int,
        end: int,
        context_length: int = 100,
    ) -> str:
        """
        Extract surrounding context for a matched term.

        Args:
            content: Full document content
            start: Term start position
            end: Term end position
            context_length: Characters to include before/after

        Returns:
            Context string with the term highlighted
        """
        ctx_start = max(0, start - context_length // 2)
        ctx_end = min(len(content), end + context_length // 2)

        context = content[ctx_start:ctx_end]

        # 줄바꿈을 공백으로 변환
        context = ' '.join(context.split())

        # 앞뒤가 잘렸으면 ... 추가
        if ctx_start > 0:
            context = "..." + context
        if ctx_end < len(content):
            context = context + "..."

        return context

    def _calculate_pattern_confidence(self, term: str, context: str) -> float:
        """
        Calculate confidence score for pattern-matched terms.

        Args:
            term: Matched term
            context: Surrounding context

        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.5  # 기본 신뢰도

        # 알려진 Tmax 제품군은 높은 신뢰도
        tmax_products = {'JEUS', 'Tmax', 'Tibero', 'OpenFrame', 'ProObject'}
        if term in tmax_products:
            confidence = 0.8

        # 알려진 모호한 용어 (MFS, WebAdmin 등)
        known_ambiguous = {'MFS', 'WebAdmin', 'Manager', 'TP', 'Server'}
        if term in known_ambiguous:
            confidence = 0.9

        # 문맥에 기술 키워드가 있으면 신뢰도 상승
        context_lower = context.lower()
        if any(kw in context_lower for kw in ['설정', 'config', '에러', 'error']):
            confidence = min(1.0, confidence + 0.1)

        return confidence

    def _merge_candidates(
        self,
        candidates: List[ExtractedTerm],
    ) -> List[ExtractedTerm]:
        """
        Merge duplicate candidates, keeping highest confidence.

        Args:
            candidates: List of candidates with possible duplicates

        Returns:
            Deduplicated list with merged counts
        """
        merged: Dict[str, ExtractedTerm] = {}

        for candidate in candidates:
            key = candidate.term_normalized

            if key in merged:
                existing = merged[key]
                # 더 높은 신뢰도 유지
                if candidate.confidence_score > existing.confidence_score:
                    merged[key] = candidate
                # occurrence_count 합산
                merged[key].occurrence_count += candidate.occurrence_count
            else:
                merged[key] = candidate

        return list(merged.values())

    async def _filter_existing_terms(
        self,
        candidates: List[ExtractedTerm],
    ) -> List[ExtractedTerm]:
        """
        Filter out terms that already exist in ambiguous_terms.

        Args:
            candidates: List of extracted candidates

        Returns:
            Filtered list excluding existing terms
        """
        if not candidates:
            return []

        # 기존 모호한 용어 조회
        try:
            existing_terms = await self.ambiguous_term_repo.get_all_active()
            existing_normalized = {t['term_normalized'] for t in existing_terms}
        except Exception as e:
            logger.warning(f"Failed to get existing terms: {e}")
            existing_normalized = set()

        # 이미 등록된 용어 필터링
        filtered = [
            c for c in candidates
            if c.term_normalized not in existing_normalized
        ]

        if len(filtered) < len(candidates):
            logger.debug(
                f"Filtered {len(candidates) - len(filtered)} existing terms"
            )

        return filtered


# =============================================================================
# Service Factory
# =============================================================================

_term_extraction_service: Optional[TermExtractionService] = None


def get_term_extraction_service() -> TermExtractionService:
    """Get the term extraction service singleton."""
    global _term_extraction_service
    if _term_extraction_service is None:
        raise RuntimeError(
            "TermExtractionService not initialized. "
            "Call initialize_term_extraction_service first."
        )
    return _term_extraction_service


def initialize_term_extraction_service(
    ambiguous_term_repo: PostgresAmbiguousTermRepository,
    term_candidate_repo: PostgresTermCandidateRepository,
) -> TermExtractionService:
    """
    Initialize the term extraction service singleton.

    Args:
        ambiguous_term_repo: Repository for existing ambiguous terms
        term_candidate_repo: Repository for term candidates

    Returns:
        Initialized TermExtractionService
    """
    global _term_extraction_service
    _term_extraction_service = TermExtractionService(
        ambiguous_term_repo=ambiguous_term_repo,
        term_candidate_repo=term_candidate_repo,
    )
    logger.info("TermExtractionService initialized")
    return _term_extraction_service


def set_term_extraction_service(service: TermExtractionService) -> None:
    """Set the term extraction service singleton."""
    global _term_extraction_service
    _term_extraction_service = service
