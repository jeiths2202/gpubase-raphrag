"""
FaithfulnessCheckerService: 응답 근거 검증

Implements ISSUP-style verification:
- FULLY_SUPPORTED: 모든 주장이 컨텍스트에 근거
- PARTIALLY_SUPPORTED: 일부만 근거 있음
- NOT_SUPPORTED: 근거 없음

Created as part of PDCA: rag-accuracy-improvement
"""

import re
import logging
from typing import List, Dict, Any, Optional

from ..models.rag_accuracy import (
    SupportLevel,
    ClaimVerification,
    FaithfulnessResult,
)

logger = logging.getLogger(__name__)


class FaithfulnessCheckerService:
    """응답 충실도 검증 서비스"""

    # Support level thresholds
    FULLY_SUPPORTED_THRESHOLD = 0.8   # 80% of claims supported
    PARTIALLY_SUPPORTED_THRESHOLD = 0.3  # 30% of claims supported

    # Minimum key terms required for meaningful verification
    MIN_KEY_TERMS = 2

    def check_faithfulness(
        self,
        answer: str,
        context: str,
        graded_results: Optional[List[Dict[str, Any]]] = None,
    ) -> FaithfulnessResult:
        """
        응답 충실도 검증

        Args:
            answer: 생성된 응답
            context: 검색된 컨텍스트 (연결된 문자열)
            graded_results: 그레이딩된 검색 결과 (선택사항)

        Returns:
            FaithfulnessResult: 충실도 검증 결과
        """
        logger.debug(f"[FaithfulnessChecker] Checking answer: {answer[:100]}...")

        # Handle empty answer
        if not answer or not answer.strip():
            return FaithfulnessResult(
                answer=answer or "",
                support_level=SupportLevel.NOT_SUPPORTED,
                verified_claims=[],
                unsupported_claims=[],
                confidence=0.0,
            )

        # Combine context from graded_results if provided
        if graded_results:
            additional_context = " ".join([
                r.get("content", "") or r.get("text", "")
                for r in graded_results
            ])
            context = f"{context} {additional_context}".strip()

        # Handle empty context
        if not context or not context.strip():
            return FaithfulnessResult(
                answer=answer,
                support_level=SupportLevel.NOT_SUPPORTED,
                verified_claims=[],
                unsupported_claims=[answer],
                confidence=0.0,
            )

        # Extract claims from answer
        claims = self._extract_claims(answer)

        if not claims:
            # If no claims extracted, check overall keyword match
            overall_supported = self._check_overall_support(answer, context)
            return FaithfulnessResult(
                answer=answer,
                support_level=SupportLevel.FULLY_SUPPORTED if overall_supported else SupportLevel.PARTIALLY_SUPPORTED,
                verified_claims=[],
                unsupported_claims=[],
                confidence=0.7 if overall_supported else 0.3,
            )

        # Verify each claim against context
        verified_claims: List[ClaimVerification] = []
        unsupported_claims: List[str] = []

        for claim in claims:
            verification = self._verify_claim(claim, context)
            if verification.supported:
                verified_claims.append(verification)
            else:
                unsupported_claims.append(claim)

        # Calculate support level
        support_level = self._calculate_support_level(
            total_claims=len(claims),
            supported_count=len(verified_claims),
        )

        # Calculate confidence
        confidence = len(verified_claims) / len(claims) if claims else 0.0

        result = FaithfulnessResult(
            answer=answer,
            support_level=support_level,
            verified_claims=verified_claims,
            unsupported_claims=unsupported_claims,
            confidence=round(confidence, 2),
        )

        logger.info(
            f"[FaithfulnessChecker] Result: {support_level.value}, "
            f"confidence={confidence:.2f}, "
            f"supported={len(verified_claims)}/{len(claims)}"
        )

        return result

    def _extract_claims(self, answer: str) -> List[str]:
        """응답에서 주장 추출"""
        # Split by sentence boundaries (multilingual)
        sentence_endings = r'[。．.!?！？\n]\s*'
        sentences = re.split(sentence_endings, answer)

        # Filter out empty or too short sentences
        claims = []
        for s in sentences:
            s = s.strip()
            # Skip short sentences or common phrases
            if len(s) < 10:
                continue
            # Skip meta sentences like "以下の情報があります"
            if self._is_meta_sentence(s):
                continue
            claims.append(s)

        return claims

    def _is_meta_sentence(self, sentence: str) -> bool:
        """메타 문장 여부 확인 (정보 안내 등)"""
        meta_patterns = [
            r'^以下の|^다음과|^The following|^Here is',
            r'情報があります|정보가 있습니다|information is|found',
            r'^はい|^예|^Yes',
            r'参照してください|참조하세요|please refer',
        ]
        for pattern in meta_patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                return True
        return False

    def _verify_claim(self, claim: str, context: str) -> ClaimVerification:
        """개별 주장 검증"""
        # Extract key terms from claim
        key_terms = self._extract_key_terms(claim)

        if len(key_terms) < self.MIN_KEY_TERMS:
            # Too few key terms, check substring match
            if claim.lower()[:30] in context.lower():
                return ClaimVerification(
                    claim=claim,
                    supported=True,
                    evidence=None,
                )
            return ClaimVerification(
                claim=claim,
                supported=False,
                evidence=None,
            )

        # Check if key terms appear in context
        context_lower = context.lower()
        matched_terms = [t for t in key_terms if t.lower() in context_lower]

        # Calculate match ratio
        match_ratio = len(matched_terms) / len(key_terms) if key_terms else 0.0

        # Determine if supported (threshold: 50% key terms)
        supported = match_ratio >= 0.5

        # Find evidence snippet if supported
        evidence = None
        if supported and matched_terms:
            evidence = self._find_evidence_snippet(matched_terms[0], context)

        return ClaimVerification(
            claim=claim,
            supported=supported,
            evidence=evidence,
        )

    def _extract_key_terms(self, text: str) -> List[str]:
        """핵심 용어 추출"""
        terms: List[str] = []

        # Technical terms (uppercase, mixed case)
        tech_terms = re.findall(r'\b[A-Z][A-Za-z0-9_.-]+\b', text)
        terms.extend(tech_terms)

        # Numbers and codes (filter short ones)
        codes = re.findall(r'\b\d{3,}\b', text)
        terms.extend(codes)

        # CJK terms (longer than 2 characters, more meaningful)
        cjk_terms = re.findall(r'[\u3040-\u9FFF]{2,}', text)
        terms.extend(cjk_terms)

        # Config file names
        config_files = re.findall(r'\w+\.conf', text, re.IGNORECASE)
        terms.extend(config_files)

        # Deduplicate
        return list(set(terms))

    def _find_evidence_snippet(
        self,
        term: str,
        context: str,
        window: int = 100,
    ) -> Optional[str]:
        """근거 스니펫 찾기"""
        idx = context.lower().find(term.lower())
        if idx == -1:
            return None

        start = max(0, idx - window)
        end = min(len(context), idx + len(term) + window)

        snippet = context[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(context):
            snippet = snippet + "..."

        return snippet

    def _check_overall_support(self, answer: str, context: str) -> bool:
        """전체적인 지원 여부 확인 (claims가 없을 때)"""
        key_terms = self._extract_key_terms(answer)
        if not key_terms:
            return False

        context_lower = context.lower()
        matched = sum(1 for t in key_terms if t.lower() in context_lower)
        return matched / len(key_terms) >= 0.5 if key_terms else False

    def _calculate_support_level(
        self,
        total_claims: int,
        supported_count: int,
    ) -> SupportLevel:
        """지원 수준 계산"""
        if total_claims == 0:
            return SupportLevel.PARTIALLY_SUPPORTED  # No claims to verify

        ratio = supported_count / total_claims

        if ratio >= self.FULLY_SUPPORTED_THRESHOLD:
            return SupportLevel.FULLY_SUPPORTED
        elif ratio >= self.PARTIALLY_SUPPORTED_THRESHOLD:
            return SupportLevel.PARTIALLY_SUPPORTED
        else:
            return SupportLevel.NOT_SUPPORTED


# =============================================================================
# Singleton Pattern
# =============================================================================

_faithfulness_checker_service: Optional[FaithfulnessCheckerService] = None


def get_faithfulness_checker_service() -> FaithfulnessCheckerService:
    """FaithfulnessCheckerService 싱글톤 반환"""
    global _faithfulness_checker_service
    if _faithfulness_checker_service is None:
        _faithfulness_checker_service = FaithfulnessCheckerService()
    return _faithfulness_checker_service
