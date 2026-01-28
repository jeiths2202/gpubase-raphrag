"""
Answer Verification Service

Learning LLM 답변을 Summary 데이터로 검증하여
할루시네이션을 탐지하고 신뢰도를 평가합니다.

Usage:
    from app.api.services.answer_verification_service import get_answer_verification_service

    service = get_answer_verification_service()
    result = await service.verify_answer(
        answer="에러 -5212는 DATASET_NOT_FOUND입니다...",
        mentioned_codes=["-5212"],
        mentioned_terms=["TJES"]
    )
    print(result.is_valid, result.verification_score)
"""
import re
import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class VerificationStatus(Enum):
    """검증 결과 상태"""
    VERIFIED = "verified"          # 모든 내용 검증됨
    PARTIALLY_VERIFIED = "partial" # 일부만 검증됨
    UNVERIFIED = "unverified"      # 검증 불가
    HALLUCINATION = "hallucination" # 할루시네이션 탐지


@dataclass
class VerificationResult:
    """검증 결과"""
    is_valid: bool
    verification_score: float  # 0.0 ~ 1.0
    status: VerificationStatus
    verified_codes: List[str] = field(default_factory=list)
    unverified_codes: List[str] = field(default_factory=list)
    verified_terms: List[str] = field(default_factory=list)
    unverified_terms: List[str] = field(default_factory=list)
    verified_commands: List[str] = field(default_factory=list)
    hallucination_patterns: List[str] = field(default_factory=list)
    additional_context: str = ""
    source_references: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "verification_score": self.verification_score,
            "status": self.status.value,
            "verified_codes": self.verified_codes,
            "unverified_codes": self.unverified_codes,
            "verified_terms": self.verified_terms,
            "unverified_terms": self.unverified_terms,
            "verified_commands": self.verified_commands,
            "hallucination_patterns": self.hallucination_patterns,
            "additional_context": self.additional_context,
            "source_references": self.source_references,
        }


@dataclass
class LearningLLMResult:
    """Learning LLM 답변 결과"""
    answer: str
    confidence: float
    mentioned_codes: List[str] = field(default_factory=list)
    mentioned_terms: List[str] = field(default_factory=list)
    mentioned_commands: List[str] = field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None


class AnswerVerificationService:
    """
    Learning LLM 답변을 Summary 데이터로 검증

    검증 기준:
    - 에러코드가 실제 존재하는지 확인
    - 에러 설명이 Summary와 일치하는지 확인
    - 명령어 구문이 정확한지 확인
    - 할루시네이션 패턴 탐지
    """

    # Hallucination patterns (common LLM fabrication patterns)
    HALLUCINATION_PATTERNS = [
        r'에러\s*코드\s*(-?\d{5,})',  # Very large error codes are suspicious
        r'버전\s*(\d+\.\d+\.\d+\.\d+)',  # Too specific version numbers
        r'(\d{4}년\s*\d{1,2}월)',  # Specific dates are often hallucinated
        r'공식\s*문서에\s*따르면',  # Claims about official docs without reference
        r'일반적으로\s*알려진',  # Vague authority claims
    ]

    def __init__(self, summary_bm25_service=None):
        self.summary_bm25_service = summary_bm25_service
        self._error_code_cache: Dict[str, Dict] = {}
        self._command_cache: Dict[str, Dict] = {}
        self._term_cache: Dict[str, Dict] = {}

    async def _get_summary_service(self):
        """Lazy load summary BM25 service"""
        if self.summary_bm25_service is None:
            try:
                from .summary_bm25_service import get_summary_bm25_service
                self.summary_bm25_service = get_summary_bm25_service()
            except Exception as e:
                logger.error(f"Failed to get summary BM25 service: {e}")
        return self.summary_bm25_service

    async def verify_answer(
        self,
        answer: str,
        mentioned_codes: Optional[List[str]] = None,
        mentioned_terms: Optional[List[str]] = None,
        mentioned_commands: Optional[List[str]] = None,
    ) -> VerificationResult:
        """
        Learning LLM 답변을 검증합니다.

        Args:
            answer: LLM이 생성한 답변
            mentioned_codes: 답변에서 언급된 에러 코드들
            mentioned_terms: 답변에서 언급된 기술 용어들
            mentioned_commands: 답변에서 언급된 명령어들

        Returns:
            VerificationResult with validation details
        """
        mentioned_codes = mentioned_codes or []
        mentioned_terms = mentioned_terms or []
        mentioned_commands = mentioned_commands or []

        # Extract additional mentions from answer text
        additional_codes = self._extract_error_codes(answer)
        additional_terms = self._extract_terms(answer)
        additional_commands = self._extract_commands(answer)

        all_codes = list(set(mentioned_codes + additional_codes))
        all_terms = list(set(mentioned_terms + additional_terms))
        all_commands = list(set(mentioned_commands + additional_commands))

        # Initialize result
        verified_codes = []
        unverified_codes = []
        verified_terms = []
        unverified_terms = []
        verified_commands = []
        hallucination_patterns = []
        source_references = []

        service = await self._get_summary_service()

        # Verify error codes
        if all_codes and service and service.is_initialized:
            for code in all_codes:
                try:
                    # search_error_code returns Optional[SummarySearchResult]
                    result = await service.search_error_code(code)
                    if result:
                        verified_codes.append(code)
                        # Add source reference from the single result
                        source_references.append({
                            "type": "error_code",
                            "code": code,
                            "source_pdf": result.document.source_pdf,
                            "page_numbers": result.document.page_numbers,
                        })
                    else:
                        unverified_codes.append(code)
                except Exception as e:
                    logger.warning(f"Error verifying code {code}: {e}")
                    unverified_codes.append(code)

        # Verify commands
        if all_commands and service and service.is_initialized:
            for cmd in all_commands:
                try:
                    # search_command returns List[SummarySearchResult]
                    results = await service.search_command(cmd)
                    if results:
                        verified_commands.append(cmd)
                        # Add source reference from first result
                        r = results[0]
                        source_references.append({
                            "type": "command",
                            "name": cmd,
                            "source_pdf": r.document.source_pdf,
                            "page_numbers": r.document.page_numbers,
                        })
                except Exception as e:
                    logger.warning(f"Error verifying command {cmd}: {e}")

        # Verify terms
        if all_terms and service and service.is_initialized:
            for term in all_terms:
                try:
                    # search_term returns Optional[SummarySearchResult]
                    result = await service.search_term(term)
                    if result:
                        verified_terms.append(term)
                        source_references.append({
                            "type": "term",
                            "name": term,
                            "source_pdf": result.document.source_pdf,
                        })
                    else:
                        unverified_terms.append(term)
                except Exception as e:
                    logger.warning(f"Error verifying term {term}: {e}")
                    unverified_terms.append(term)

        # Detect hallucination patterns
        hallucination_patterns = self.detect_hallucination(answer)

        # Calculate verification score
        score = self.calculate_verification_score(
            verified_codes=verified_codes,
            unverified_codes=unverified_codes,
            verified_terms=verified_terms,
            unverified_terms=unverified_terms,
            verified_commands=verified_commands,
            hallucination_count=len(hallucination_patterns),
            answer_length=len(answer),
        )

        # Determine status
        if hallucination_patterns:
            status = VerificationStatus.HALLUCINATION
            is_valid = False
        elif score >= 0.8:
            status = VerificationStatus.VERIFIED
            is_valid = True
        elif score >= 0.5:
            status = VerificationStatus.PARTIALLY_VERIFIED
            is_valid = True
        else:
            status = VerificationStatus.UNVERIFIED
            is_valid = score >= 0.3  # Low threshold for unverified

        # Build additional context from verified sources
        additional_context = await self._build_additional_context(
            verified_codes, verified_commands, verified_terms
        )

        return VerificationResult(
            is_valid=is_valid,
            verification_score=score,
            status=status,
            verified_codes=verified_codes,
            unverified_codes=unverified_codes,
            verified_terms=verified_terms,
            unverified_terms=unverified_terms,
            verified_commands=verified_commands,
            hallucination_patterns=hallucination_patterns,
            additional_context=additional_context,
            source_references=source_references,
        )

    def calculate_verification_score(
        self,
        verified_codes: List[str],
        unverified_codes: List[str],
        verified_terms: List[str],
        unverified_terms: List[str],
        verified_commands: List[str],
        hallucination_count: int,
        answer_length: int,
    ) -> float:
        """
        검증 점수 계산 (0.0 ~ 1.0)

        Scoring:
        - 에러코드 존재 확인: +0.3 (per verified code)
        - 설명 일치: +0.2 (per verified term)
        - 명령어 검증: +0.2 (per verified command)
        - 할루시네이션 패턴: -0.2 (per pattern)
        """
        score = 0.5  # Base score

        total_codes = len(verified_codes) + len(unverified_codes)
        total_terms = len(verified_terms) + len(unverified_terms)

        # Error code verification
        if total_codes > 0:
            code_ratio = len(verified_codes) / total_codes
            score += code_ratio * 0.3

        # Term verification
        if total_terms > 0:
            term_ratio = len(verified_terms) / total_terms
            score += term_ratio * 0.2

        # Command verification bonus
        if verified_commands:
            score += min(len(verified_commands) * 0.1, 0.2)

        # Hallucination penalty
        score -= hallucination_count * 0.15

        # Length bonus for detailed answers (but not too long)
        if 100 < answer_length < 1000:
            score += 0.05
        elif answer_length > 2000:
            score -= 0.05  # Penalty for overly verbose

        return max(0.0, min(1.0, score))

    def detect_hallucination(self, answer: str) -> List[str]:
        """
        할루시네이션 패턴 탐지

        Returns:
            List of detected hallucination patterns
        """
        detected = []

        for pattern in self.HALLUCINATION_PATTERNS:
            matches = re.findall(pattern, answer, re.IGNORECASE)
            if matches:
                detected.append(f"Pattern: {pattern[:30]}... ({len(matches)} matches)")

        # Check for suspiciously specific claims without references
        if "100%" in answer or "항상" in answer or "반드시" in answer:
            detected.append("Absolute certainty claims")

        # Check for fabricated URLs
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, answer)
        for url in urls:
            if 'openframe' in url.lower() and 'tmaxsoft' not in url.lower():
                detected.append(f"Suspicious URL: {url[:50]}")

        return detected

    def _extract_error_codes(self, text: str) -> List[str]:
        """Extract error codes from text"""
        pattern = r'-?\d{4,5}'
        matches = re.findall(pattern, text)
        return [m if m.startswith('-') else f"-{m}" for m in matches if len(m) >= 4]

    def _extract_terms(self, text: str) -> List[str]:
        """Extract technical terms from text"""
        # Common OpenFrame terms pattern
        pattern = r'\b(TJES|TACF|TSO|JCL|VSAM|COBOL|CICS|IMS|OSC|OSI|HiDB|NDB)\b'
        return list(set(re.findall(pattern, text, re.IGNORECASE)))

    def _extract_commands(self, text: str) -> List[str]:
        """Extract command names from text"""
        # Common command patterns
        patterns = [
            r'\b(tjesmgr|hidbmgr|tacfmgr|oscmgr)\b',
            r'\b(BOOT|SHUTDOWN|CANCEL|SUBMIT|START|STOP|HOLD|RELEASE)\b',
            r'\b(DS\w+|PSPOOL\w*|JCL\w+)\b',
        ]
        commands = []
        for pattern in patterns:
            commands.extend(re.findall(pattern, text, re.IGNORECASE))
        return list(set(commands))

    async def _build_additional_context(
        self,
        verified_codes: List[str],
        verified_commands: List[str],
        verified_terms: List[str],
    ) -> str:
        """Build additional context from verified sources"""
        context_parts = []
        service = await self._get_summary_service()

        if not service or not service.is_initialized:
            return ""

        # Add verified error code details
        for code in verified_codes[:2]:
            try:
                # search_error_code returns Optional[SummarySearchResult]
                result = await service.search_error_code(code)
                if result:
                    doc = result.document
                    desc = doc.description[:200] if doc.description else ""
                    context_parts.append(
                        f"[Error {code}] {doc.name}: {desc}"
                    )
            except Exception:
                pass

        # Add verified command details
        for cmd in verified_commands[:2]:
            try:
                # search_command returns List[SummarySearchResult]
                results = await service.search_command(cmd)
                if results:
                    doc = results[0].document
                    desc = doc.description[:200] if doc.description else ""
                    context_parts.append(
                        f"[Command {cmd}] {desc}"
                    )
            except Exception:
                pass

        return "\n".join(context_parts)


# ============================================
# Singleton Instance
# ============================================

_verification_service: Optional[AnswerVerificationService] = None


def get_answer_verification_service() -> AnswerVerificationService:
    """Get answer verification service singleton"""
    global _verification_service

    if _verification_service is None:
        _verification_service = AnswerVerificationService()
        logger.info("Answer verification service initialized")

    return _verification_service


async def initialize_answer_verification_service(
    summary_bm25_service=None,
) -> AnswerVerificationService:
    """Initialize answer verification service with dependencies"""
    global _verification_service

    _verification_service = AnswerVerificationService(
        summary_bm25_service=summary_bm25_service
    )

    logger.info("Answer verification service initialized with dependencies")
    return _verification_service
