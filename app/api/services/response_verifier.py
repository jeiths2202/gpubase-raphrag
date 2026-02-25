"""
Response Verifier

LLM 생성 응답의 문장별 사후 검증.
각 문장을 소스 청크와 비교하여 신뢰도 등급(verified/inferred/unverified)을 부여합니다.
용어 교정: LLM이 자주 혼동하는 고유명사를 정식명칭으로 자동 교정합니다.
"""
import logging
import re
from typing import Dict, List, Optional, Tuple

from ..models.agentic_rag import VerifiedSentence, VerificationLevel
from .structured_knowledge_store import SearchResult

logger = logging.getLogger(__name__)

# ============================================================================
# OpenFrame 용어 교정 사전
# ============================================================================
# LLM(Qwen2.5 등)이 자주 혼동하는 TmaxSoft 고유명사를 교정합니다.
# 예: TJES를 IBM의 "Tivoli Job Entry"로 환각하는 현상 방지
# ============================================================================
TERM_CORRECTIONS: Dict[str, str] = {
    # TJES: LLM이 IBM Tivoli와 혼동
    "TJE (Tivoli Job Entry)": "TJES (Tmax Job Entry Subsystem)",
    "TJE(Tivoli Job Entry)": "TJES(Tmax Job Entry Subsystem)",
    "TJE （Tivoli Job Entry）": "TJES（Tmax Job Entry Subsystem）",
    "Tivoli Job Entry Subsystem": "Tmax Job Entry Subsystem",
    "Tivoli Job Entry": "Tmax Job Entry Subsystem",
    # TACF: LLM이 IBM RACF나 CA Top Secret과 혼동
    "TAC (Tivoli Access Control)": "TACF (Tmax Access Control Facility)",
    "RACF (Resource Access Control)": "TACF (Tmax Access Control Facility)",
    # OSC: CICS와의 관계에서 잘못된 풀네임 생성 방지
    "Online Service Controller": "Online SC (CICS equivalent)",
    # 제품 소속 오류: OpenFrame 제품을 IBM/Fujitsu 제품으로 귀속
    "IBM TJES": "TmaxSoft TJES",
    "IBM TACF": "TmaxSoft TACF",
    "Fujitsu TJES": "TmaxSoft TJES",
}


class ResponseVerifier:
    """
    LLM 응답 사후 검증기

    각 문장에 대해:
    - 소스 청크와 단어 겹침(word overlap) 기반 유사도 계산
    - similarity >= 0.7 → VERIFIED (🟢)
    - 0.4 <= similarity < 0.7 → INFERRED (🟡)
    - similarity < 0.4 → UNVERIFIED (🔴)
    """

    VERIFIED_THRESHOLD = 0.7
    INFERRED_THRESHOLD = 0.4

    def correct_terminology(self, text: str) -> Tuple[str, List[Dict[str, str]]]:
        """
        LLM 응답에서 알려진 용어 오류를 자동 교정

        Returns:
            (교정된 텍스트, 교정 내역 리스트)
        """
        corrections: List[Dict[str, str]] = []
        for wrong, correct in TERM_CORRECTIONS.items():
            if wrong in text:
                text = text.replace(wrong, correct)
                corrections.append({"from": wrong, "to": correct})
                logger.info(f"[TermCorrection] '{wrong}' → '{correct}'")
        return text, corrections

    def verify(
        self,
        response_text: str,
        source_results: List[SearchResult],
    ) -> List[VerifiedSentence]:
        """
        응답 텍스트의 각 문장을 소스와 비교하여 검증

        Args:
            response_text: LLM 생성 응답 텍스트
            source_results: 검색된 소스 결과

        Returns:
            문장별 검증 결과 리스트
        """
        sentences = self._split_sentences(response_text)
        if not sentences or not source_results:
            return []

        # 소스 텍스트 결합
        source_texts = [r.content for r in source_results if r.content]

        verified_sentences: List[VerifiedSentence] = []

        for sentence in sentences:
            if len(sentence.strip()) < 5:
                continue

            best_similarity = 0.0
            best_source_chunk = None
            best_source_doc = None

            for i, source_text in enumerate(source_texts):
                sim = self._calculate_word_overlap(sentence, source_text)
                if sim > best_similarity:
                    best_similarity = sim
                    best_source_chunk = source_text[:200]
                    best_source_doc = source_results[i].source_file if i < len(source_results) else None

            level = self._get_level(best_similarity)

            verified_sentences.append(VerifiedSentence(
                text=sentence.strip(),
                level=level,
                similarity=round(best_similarity, 3),
                source_chunk=best_source_chunk,
                source_doc=best_source_doc,
            ))

        return verified_sentences

    def _split_sentences(self, text: str) -> List[str]:
        """텍스트를 문장 단위로 분할"""
        # 일본어/한국어/영어 혼합 문장 분할
        # 마침표, 느낌표, 물음표, 일본어 구두점으로 분할
        sentences = re.split(r'(?<=[。！？\.\!\?])\s*', text)
        # 빈 문자열 제거, Markdown 헤더/코드블록 제외
        return [
            s.strip() for s in sentences
            if s.strip()
            and not s.strip().startswith('#')
            and not s.strip().startswith('```')
            and not s.strip().startswith('>')
            and not s.strip().startswith('---')
        ]

    def _calculate_word_overlap(self, sentence: str, source: str) -> float:
        """단어 겹침 기반 유사도 계산 (0.0 ~ 1.0)"""
        sentence_tokens = self._tokenize(sentence.lower())
        source_tokens = self._tokenize(source.lower())

        if not sentence_tokens or not source_tokens:
            return 0.0

        sentence_set = set(sentence_tokens)
        source_set = set(source_tokens)

        overlap = sentence_set & source_set
        # Jaccard-like: overlap / sentence tokens (문장 커버리지)
        return len(overlap) / max(len(sentence_set), 1)

    def _tokenize(self, text: str) -> List[str]:
        """간단한 토큰화 (영문 단어 + CJK 문자)"""
        # 영문 단어, 숫자, CJK 문자(2글자 이상)
        tokens = re.findall(
            r'[a-zA-Z0-9_\-]{2,}|[\u3040-\u309f\u30a0-\u30ff]{2,}|[\u4e00-\u9fff]{1,}|[\uac00-\ud7af]{2,}',
            text,
        )
        # 불용어 제거
        stopwords = {"the", "is", "are", "was", "were", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "です", "ます", "の", "は", "が", "を", "に", "で", "と"}
        return [t for t in tokens if t not in stopwords]

    def _get_level(self, similarity: float) -> VerificationLevel:
        """유사도에 따른 검증 등급 결정"""
        if similarity >= self.VERIFIED_THRESHOLD:
            return VerificationLevel.VERIFIED
        elif similarity >= self.INFERRED_THRESHOLD:
            return VerificationLevel.INFERRED
        else:
            return VerificationLevel.UNVERIFIED


# Singleton
_verifier_instance: Optional[ResponseVerifier] = None


def get_response_verifier() -> ResponseVerifier:
    """Get singleton ResponseVerifier"""
    global _verifier_instance
    if _verifier_instance is None:
        _verifier_instance = ResponseVerifier()
    return _verifier_instance
