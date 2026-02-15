"""
Pattern B: Competitive Hypothesis Verification

동일 컨텍스트에 대해 서로 다른 temperature + 프롬프트 변형으로
복수 답변을 생성하고, 다차원 평가 + 교차 검증으로 최적 답변 선택.
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =========================================================================
# Prompt Variants (temperature + system instruction)
# =========================================================================

PROMPT_VARIANTS = {
    "precise": (
        "以下のコンテキストに基づいて正確に回答してください。"
        "コンテキストにない情報は絶対に含めないでください。"
        "エラーコード、コマンド名、設定パラメータは正確に引用してください。"
    ),
    "detailed": (
        "以下のコンテキストに基づいて詳細に説明してください。"
        "手順がある場合はステップごとに説明し、"
        "関連する注意点や前提条件も含めてください。"
    ),
    "concise": (
        "以下のコンテキストに基づいて簡潔に回答してください。"
        "要点のみを箇条書きまたは短い段落で説明してください。"
        "不要な前置きは省いてください。"
    ),
}


@dataclass
class HypothesisConfig:
    """가설 생성 설정"""
    temperature: float
    label: str
    prompt_variant: str  # key in PROMPT_VARIANTS
    max_tokens: int = 2048


DEFAULT_HYPOTHESES = [
    HypothesisConfig(temperature=0.1, label="precise", prompt_variant="precise"),
    HypothesisConfig(temperature=0.3, label="detailed", prompt_variant="detailed"),
    HypothesisConfig(temperature=0.5, label="concise", prompt_variant="concise"),
]


@dataclass
class ScoredHypothesis:
    """평가 완료된 가설"""
    answer: str
    config: HypothesisConfig
    score: float
    issues: List[str] = field(default_factory=list)
    detail_scores: Dict[str, float] = field(default_factory=dict)


# =========================================================================
# CJK-aware patterns
# =========================================================================

# 환각 표현 (일본어/한국어/영어)
HALLUCINATION_MARKERS_JA = [
    "一般的に", "通常は", "おそらく", "かもしれません",
    "と思われます", "可能性があります",
]
HALLUCINATION_MARKERS_KO = [
    "일반적으로", "보통", "아마도", "것 같습니다",
    "추정됩니다", "가능성이",
]
HALLUCINATION_MARKERS_EN = [
    "typically", "usually", "probably", "I think",
    "it seems", "might be", "possibly",
]
ALL_HALLUCINATION_MARKERS = (
    HALLUCINATION_MARKERS_JA + HALLUCINATION_MARKERS_KO + HALLUCINATION_MARKERS_EN
)

# 기술 용어 패턴 (OpenFrame 도메인)
TECHNICAL_TERM_PATTERN = re.compile(
    r'[A-Z][A-Z_]{1,}|'           # TJES, TACF, OSC, ...
    r'[a-z]+mgr\b|'               # tjesmgr, hidbmgr, ...
    r'-\d{4,5}\b|'                 # 에러코드: -5212
    r'[A-Z]\d{3,4}\b|'            # S0C7, S806
    r'\b\w+\.conf\b|'             # tjes.conf, osc.conf
    r'\b\w+\.cfg\b'               # 설정 파일
)

# 구조화 출력 마커
STRUCTURED_MARKERS = [
    r'^#{1,3}\s',        # Markdown 헤더
    r'^\s*[-*]\s',       # 리스트
    r'^\s*\d+\.\s',      # 번호 리스트
    r'```',              # 코드 블록
    r'\|.*\|.*\|',       # 테이블
]


class CompetitiveHypothesisService:
    """
    다양한 프롬프트 변형으로 복수 답변을 생성하고
    다차원 평가 + 교차 검증으로 최적 답변 선택.
    """

    def __init__(
        self,
        hypotheses: Optional[List[HypothesisConfig]] = None,
    ):
        self._hypotheses = hypotheses or DEFAULT_HYPOTHESES

    async def generate_and_evaluate(
        self,
        query: str,
        context: str,
        product: str,
    ) -> Dict[str, Any]:
        """
        복수 가설 생성 + 다차원 평가 + 교차 검증.

        Returns:
            Dict with 'winner', 'all_hypotheses', 'winner_label',
            'consensus_terms', 'agreement_ratio'
        """
        from ...adapters.learning_llm.vllm_adapter import get_vllm_adapter

        adapter = get_vllm_adapter()
        if not adapter:
            return {
                "winner": None, "all_hypotheses": [],
                "winner_label": None, "agreement_ratio": 0.0,
            }

        # 병렬 생성
        async def _gen_one(config: HypothesisConfig) -> Optional[str]:
            try:
                variant_prompt = PROMPT_VARIANTS.get(config.prompt_variant, "")
                full_question = f"{variant_prompt}\n\n質問: {query}"
                return await adapter.generate(
                    question=full_question,
                    context=context,
                    max_new_tokens=config.max_tokens,
                    temperature=config.temperature,
                    product=product,
                )
            except Exception as e:
                logger.warning(f"Hypothesis {config.label} failed: {e}")
                return None

        tasks = [_gen_one(h) for h in self._hypotheses]
        raw_answers = await asyncio.gather(*tasks)

        # 개별 평가
        scored = []
        for answer, config in zip(raw_answers, self._hypotheses):
            if not answer:
                continue
            score, issues, details = self._evaluate_answer(answer, query, context)
            scored.append(ScoredHypothesis(
                answer=answer,
                config=config,
                score=score,
                issues=issues,
                detail_scores=details,
            ))

        if not scored:
            return {
                "winner": None, "all_hypotheses": [],
                "winner_label": None, "agreement_ratio": 0.0,
            }

        # 교차 검증: 합의된 용어/코드 보너스
        consensus_info = self._cross_validate(scored)
        for hyp in scored:
            hyp.score += consensus_info.get(hyp.config.label, 0.0)
            hyp.score = min(hyp.score, 1.0)

        scored.sort(key=lambda h: h.score, reverse=True)
        winner = scored[0]

        return {
            "winner": winner,
            "all_hypotheses": scored,
            "winner_label": winner.config.label,
            "consensus_terms": consensus_info.get("_consensus_terms", []),
            "agreement_ratio": consensus_info.get("_agreement_ratio", 0.0),
        }

    def _evaluate_answer(
        self, answer: str, query: str, context: str
    ) -> Tuple[float, List[str], Dict[str, float]]:
        """
        다차원 답변 평가 (LLM 미사용).

        Returns:
            (total_score, issues, detail_scores)
        """
        details = {}
        issues = []

        # 1. 길이 적절성 (0.0 - 0.15)
        answer_len = len(answer)
        if answer_len < 30:
            details["length"] = 0.0
            issues.append("too_short")
        elif answer_len < 100:
            details["length"] = 0.05
        elif answer_len < 1500:
            details["length"] = 0.15
        else:
            details["length"] = 0.10  # 너무 긴 것도 감점

        # 2. 기술 용어 커버리지 (0.0 - 0.25)
        ctx_terms = set(TECHNICAL_TERM_PATTERN.findall(context))
        ans_terms = set(TECHNICAL_TERM_PATTERN.findall(answer))
        if ctx_terms:
            term_coverage = len(ctx_terms & ans_terms) / len(ctx_terms)
            details["term_coverage"] = term_coverage * 0.25
        else:
            details["term_coverage"] = 0.12  # 중립

        # 3. 쿼리 키워드 매칭 (0.0 - 0.15)
        query_words = set(re.findall(r'\w{2,}', query.lower()))
        answer_lower = answer.lower()
        if query_words:
            query_hits = sum(1 for w in query_words if w in answer_lower)
            details["query_match"] = (query_hits / len(query_words)) * 0.15
        else:
            details["query_match"] = 0.07

        # 4. 에러코드 정확성 (0.0 - 0.15)
        ctx_codes = set(re.findall(r'-\d{4,5}', context))
        ans_codes = set(re.findall(r'-\d{4,5}', answer))
        if ctx_codes:
            code_coverage = len(ctx_codes & ans_codes) / len(ctx_codes)
            # 환각 코드 (컨텍스트에 없는 코드) 페널티
            halluc_codes = ans_codes - ctx_codes
            penalty = len(halluc_codes) * 0.03
            details["error_code"] = max(code_coverage * 0.15 - penalty, 0.0)
            if halluc_codes:
                issues.append(f"hallucinated_codes:{','.join(halluc_codes)}")
        else:
            details["error_code"] = 0.07

        # 5. 구조화 품질 (0.0 - 0.15)
        structure_score = 0.0
        for pattern in STRUCTURED_MARKERS:
            if re.search(pattern, answer, re.MULTILINE):
                structure_score += 0.03
        details["structure"] = min(structure_score, 0.15)

        # 6. 환각 패턴 감지 (-0.15 ~ 0.0)
        halluc_penalty = 0.0
        for marker in ALL_HALLUCINATION_MARKERS:
            if marker in answer:
                halluc_penalty -= 0.03
                issues.append(f"vague:{marker}")
        details["hallucination"] = max(halluc_penalty, -0.15)

        # 7. 컨텍스트 충실도 (0.0 - 0.15)
        # 컨텍스트의 핵심 문장이 답변에 반영되었는지
        ctx_sentences = [s.strip() for s in context.split('\n') if len(s.strip()) > 20]
        if ctx_sentences:
            reflected = 0
            for sent in ctx_sentences[:10]:
                # 핵심 단어 3개 이상 매칭
                sent_words = set(re.findall(r'\w{3,}', sent.lower()))
                common = sent_words & set(re.findall(r'\w{3,}', answer_lower))
                if len(common) >= 3:
                    reflected += 1
            fidelity = reflected / min(len(ctx_sentences), 10)
            details["fidelity"] = fidelity * 0.15
        else:
            details["fidelity"] = 0.07

        total = sum(details.values())
        return min(max(total, 0.0), 1.0), issues, details

    def _cross_validate(
        self, hypotheses: List[ScoredHypothesis]
    ) -> Dict[str, Any]:
        """
        교차 검증: 여러 가설이 공통적으로 언급한 용어에 보너스.
        과반수(2/3) 이상이 동의한 기술 용어를 consensus로 판정.
        """
        if len(hypotheses) < 2:
            return {"_consensus_terms": [], "_agreement_ratio": 0.0}

        term_sets = []
        for hyp in hypotheses:
            terms = set(TECHNICAL_TERM_PATTERN.findall(hyp.answer))
            term_sets.append(terms)

        # 과반수 합의 용어
        all_terms = set()
        for ts in term_sets:
            all_terms |= ts

        consensus_terms = []
        threshold = len(hypotheses) / 2
        for term in all_terms:
            count = sum(1 for ts in term_sets if term in ts)
            if count > threshold:
                consensus_terms.append(term)

        # 합의율
        if all_terms:
            agreement_ratio = len(consensus_terms) / len(all_terms)
        else:
            agreement_ratio = 0.0

        # 합의 용어를 많이 포함한 가설에 보너스
        bonuses = {}
        for hyp in hypotheses:
            hyp_terms = set(TECHNICAL_TERM_PATTERN.findall(hyp.answer))
            if consensus_terms:
                consensus_coverage = len(
                    hyp_terms & set(consensus_terms)
                ) / len(consensus_terms)
                bonuses[hyp.config.label] = consensus_coverage * 0.1
            else:
                bonuses[hyp.config.label] = 0.0

        bonuses["_consensus_terms"] = consensus_terms
        bonuses["_agreement_ratio"] = agreement_ratio
        return bonuses
