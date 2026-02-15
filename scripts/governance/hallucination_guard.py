#!/usr/bin/env python3
"""
Hallucination Auto-Detection & Guard Engine.

Three-stage verification:
1. Citation enforcement: Every claim must reference source chunk ID
2. Self-verification pass: Re-ask model to verify grounding
3. Fabrication detection: Entity cross-check against known corpus

Usage:
    from scripts.governance.hallucination_guard import HallucinationGuard
    guard = HallucinationGuard(tokenizer, known_entities)
    result = guard.evaluate(response, context_chunks)
"""

import re
import json
import logging
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class HallucinationResult:
    """단일 응답에 대한 환각 검사 결과."""
    grounded: bool
    missing_citations: int
    total_claims: int
    citation_ratio: float
    fabrication_score: float
    fabricated_entities: List[str]
    self_verification_score: float
    confidence: float
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ProductHallucinationReport:
    """제품별 환각 검사 집계 결과."""
    product_id: str
    total_responses: int
    grounded_count: int
    hallucination_count: int
    hallucination_rate: float
    avg_citation_ratio: float
    avg_fabrication_score: float
    avg_confidence: float
    worst_cases: List[Dict]
    passed: bool
    fail_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


class HallucinationGuard:
    """
    3단계 환각 검출 엔진.

    Stage 1: Citation Enforcement (패턴 매칭)
    Stage 2: Self-Verification Pass (LLM 재질의)
    Stage 3: Fabrication Detection (엔티티 교차 검증)
    """

    # 인용 패턴: [Source: ...], 出典:..., **출처**: ..., (p.XX)
    CITATION_PATTERNS = [
        r'\[(?:Source|출처|出典)[:\s].*?\]',
        r'\*\*(?:Source|출처|出典)\*\*[:\s].*',
        r'\((?:p\.|page|페이지)\s*\d+\)',
        r'(?:출처|Source|出典|Reference)[:\s]+\S+\.pdf',
        r'\[chunk[_\-]?\d+\]',
        r'【.*?】',
    ]

    # claim 분리 패턴: 문장 단위
    CLAIM_SPLIT_PATTERN = r'(?<=[.。!！?？])\s+'

    # 제외 패턴: 질문, 메타 텍스트 등
    NON_CLAIM_PATTERNS = [
        r'^(다음은|以下は|The following|Here)',
        r'^(참고|注意|Note|Warning)',
        r'^\s*[-•]\s*$',
        r'^\s*\d+\.\s*$',
    ]

    def __init__(
        self,
        max_hallucination_rate: float = 0.05,
        min_citation_ratio: float = 0.8,
        max_fabrication_score: float = 0.1,
        confidence_threshold: float = 0.7,
        known_entities: Optional[Set[str]] = None,
    ):
        self.max_hallucination_rate = max_hallucination_rate
        self.min_citation_ratio = min_citation_ratio
        self.max_fabrication_score = max_fabrication_score
        self.confidence_threshold = confidence_threshold
        self.known_entities = known_entities or set()

    def load_known_entities(self, entity_sources: List[str]):
        """요약본/엔티티 파일에서 알려진 엔티티 로드."""
        for source_path in entity_sources:
            path = Path(source_path)
            if not path.exists():
                continue

            if path.suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, str):
                            self.known_entities.add(item.lower())
                        elif isinstance(item, dict):
                            for v in item.values():
                                if isinstance(v, str):
                                    self.known_entities.add(v.lower())
            elif path.suffix == ".md":
                # 마크다운에서 **볼드** 용어 추출
                content = path.read_text(encoding="utf-8")
                for match in re.findall(r'\*\*(.+?)\*\*', content):
                    self.known_entities.add(match.lower())

        logger.info(f"Loaded {len(self.known_entities)} known entities")

    # ──────────────────────────────────────
    # Stage 1: Citation Enforcement
    # ──────────────────────────────────────

    def check_citations(self, response: str) -> Tuple[int, int, float]:
        """
        응답에서 주장(claim)과 인용(citation)을 분리하여 인용률 계산.

        Returns:
            (missing_citations, total_claims, citation_ratio)
        """
        claims = self._extract_claims(response)
        if not claims:
            return 0, 0, 1.0

        cited = 0
        for claim in claims:
            if self._has_citation(claim):
                cited += 1

        missing = len(claims) - cited
        ratio = cited / len(claims)
        return missing, len(claims), ratio

    def _extract_claims(self, text: str) -> List[str]:
        """텍스트에서 사실적 주장(claim) 추출."""
        sentences = re.split(self.CLAIM_SPLIT_PATTERN, text)
        claims = []

        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 10:
                continue
            # 비-주장 패턴 제외
            is_non_claim = False
            for pattern in self.NON_CLAIM_PATTERNS:
                if re.match(pattern, sent):
                    is_non_claim = True
                    break
            if not is_non_claim:
                claims.append(sent)

        return claims

    def _has_citation(self, claim: str) -> bool:
        """해당 주장에 인용이 포함되어 있는지 확인."""
        for pattern in self.CITATION_PATTERNS:
            if re.search(pattern, claim, re.IGNORECASE):
                return True
        return False

    # ──────────────────────────────────────
    # Stage 2: Self-Verification Pass
    # ──────────────────────────────────────

    def self_verify(
        self,
        response: str,
        context_chunks: List[str],
        model=None,
        tokenizer=None,
    ) -> float:
        """
        LLM 자기 검증: 응답이 컨텍스트에 근거하는지 재질의.

        model/tokenizer가 없으면 규칙 기반 검증으로 폴백.

        Returns:
            verification_score (0.0 ~ 1.0)
        """
        if model is not None and tokenizer is not None:
            return self._llm_self_verify(response, context_chunks, model, tokenizer)

        return self._rule_based_verify(response, context_chunks)

    def _llm_self_verify(
        self, response: str, context_chunks: List[str], model, tokenizer
    ) -> float:
        """LLM 기반 자기 검증."""
        import torch

        context_text = "\n".join(context_chunks[:5])  # 상위 5개 청크
        prompt = (
            "<|im_start|>system\n"
            "You are a fact-checking assistant. Evaluate whether the response "
            "is fully grounded in the provided context. "
            "Reply with a JSON: {\"grounded\": true/false, \"score\": 0.0-1.0}\n"
            "<|im_end|>\n"
            f"<|im_start|>user\n"
            f"Context:\n{context_text[:2000]}\n\n"
            f"Response to verify:\n{response[:1000]}\n\n"
            f"Is every claim in the response grounded in the context?\n"
            f"<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        model.eval()
        with torch.no_grad():
            input_ids = tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=2048
            )["input_ids"].to(model.device)

            output_ids = model.generate(
                input_ids,
                max_new_tokens=100,
                do_sample=False,
                temperature=1.0,
            )
            gen_text = tokenizer.decode(
                output_ids[0][input_ids.shape[1]:], skip_special_tokens=True
            )

        # JSON 파싱 시도
        try:
            json_match = re.search(r'\{.*?\}', gen_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return float(result.get("score", 0.5))
        except (json.JSONDecodeError, ValueError):
            pass

        # 폴백: 키워드 기반
        if "grounded" in gen_text.lower() or "true" in gen_text.lower():
            return 0.8
        return 0.4

    def _rule_based_verify(self, response: str, context_chunks: List[str]) -> float:
        """규칙 기반 검증 (LLM 없이)."""
        if not context_chunks:
            return 0.0

        context_combined = " ".join(context_chunks).lower()
        response_lower = response.lower()

        # 응답의 핵심 용어가 컨텍스트에 존재하는지 확인
        # 영문/한글/일본어 용어 추출
        terms = set()
        # 영문 기술 용어 (2자 이상)
        terms.update(re.findall(r'[A-Z][A-Za-z0-9_]{1,}', response))
        # 한글 명사 패턴
        terms.update(re.findall(r'[가-힣]{2,}(?:서버|시스템|명령|설정|파일|모드|기능)', response))
        # 일본어 카타카나 용어
        terms.update(re.findall(r'[\u30A0-\u30FF]{2,}', response))

        if not terms:
            return 0.5

        grounded_count = sum(1 for t in terms if t.lower() in context_combined)
        return grounded_count / len(terms)

    # ──────────────────────────────────────
    # Stage 3: Fabrication Detection
    # ──────────────────────────────────────

    def detect_fabrications(
        self,
        response: str,
        context_chunks: List[str],
    ) -> Tuple[float, List[str]]:
        """
        응답에서 날조된 엔티티 탐지.

        Returns:
            (fabrication_score, list_of_fabricated_entities)
        """
        # 응답에서 엔티티 추출
        response_entities = self._extract_entities(response)
        if not response_entities:
            return 0.0, []

        context_combined = " ".join(context_chunks).lower()

        fabricated = []
        for entity in response_entities:
            entity_lower = entity.lower()
            # 알려진 엔티티에 있으면 OK
            if entity_lower in self.known_entities:
                continue
            # 컨텍스트에 있으면 OK
            if entity_lower in context_combined:
                continue
            # 일반 용어 제외 (너무 짧거나 일반적인 것)
            if len(entity) < 3:
                continue
            fabricated.append(entity)

        score = len(fabricated) / len(response_entities) if response_entities else 0.0
        return score, fabricated

    def _extract_entities(self, text: str) -> List[str]:
        """텍스트에서 고유명사/기술 용어 엔티티 추출."""
        entities = []

        # 대문자 약어 (TJES, OSC, TACF 등)
        entities.extend(re.findall(r'\b[A-Z]{2,}[A-Z0-9]*\b', text))
        # CamelCase (tjesmgr, hidbmgr 등)
        entities.extend(re.findall(r'\b[a-z]+[A-Z][a-zA-Z]*\b', text))
        # 소문자 mgr 명령어
        entities.extend(re.findall(r'\b[a-z]+mgr\b', text))
        # 파일명 패턴
        entities.extend(re.findall(r'\b\w+\.(conf|cfg|xml|properties|pdf)\b', text))
        # 에러 코드
        entities.extend(re.findall(r'-\d{4,5}\b', text))

        return list(set(entities))

    # ──────────────────────────────────────
    # Unified Evaluation
    # ──────────────────────────────────────

    def evaluate(
        self,
        response: str,
        context_chunks: List[str],
        model=None,
        tokenizer=None,
    ) -> HallucinationResult:
        """
        3단계 통합 환각 검사.

        Args:
            response: 모델 생성 응답
            context_chunks: 검색된 컨텍스트 청크들
            model: (선택) 자기 검증용 LLM
            tokenizer: (선택) 토크나이저
        """
        # Stage 1: Citation check
        missing, total, citation_ratio = self.check_citations(response)

        # Stage 2: Self-verification
        self_score = self.self_verify(response, context_chunks, model, tokenizer)

        # Stage 3: Fabrication detection
        fab_score, fab_entities = self.detect_fabrications(response, context_chunks)

        # 종합 신뢰도 계산
        confidence = (
            0.3 * citation_ratio
            + 0.4 * self_score
            + 0.3 * (1.0 - fab_score)
        )

        grounded = (
            citation_ratio >= self.min_citation_ratio
            and fab_score <= self.max_fabrication_score
            and confidence >= self.confidence_threshold
        )

        return HallucinationResult(
            grounded=grounded,
            missing_citations=missing,
            total_claims=total,
            citation_ratio=citation_ratio,
            fabrication_score=fab_score,
            fabricated_entities=fab_entities,
            self_verification_score=self_score,
            confidence=confidence,
        )

    def evaluate_product(
        self,
        product_id: str,
        responses: List[str],
        context_chunks_list: List[List[str]],
        model=None,
        tokenizer=None,
    ) -> ProductHallucinationReport:
        """
        제품 단위 환각 검사 및 리포트 생성.

        Args:
            product_id: 제품 ID
            responses: 해당 제품의 응답 리스트
            context_chunks_list: 각 응답에 대한 컨텍스트 청크 리스트
        """
        results = []
        grounded_count = 0
        hallucination_count = 0
        worst_cases = []

        for i, (response, chunks) in enumerate(zip(responses, context_chunks_list)):
            result = self.evaluate(response, chunks, model, tokenizer)
            results.append(result)

            if result.grounded:
                grounded_count += 1
            else:
                hallucination_count += 1
                worst_cases.append({
                    "index": i,
                    "confidence": result.confidence,
                    "fabrication_score": result.fabrication_score,
                    "fabricated_entities": result.fabricated_entities[:5],
                    "response_preview": response[:200],
                })

        total = len(results)
        hallucination_rate = hallucination_count / total if total > 0 else 0
        avg_citation = sum(r.citation_ratio for r in results) / total if total > 0 else 0
        avg_fab = sum(r.fabrication_score for r in results) / total if total > 0 else 0
        avg_conf = sum(r.confidence for r in results) / total if total > 0 else 0

        fail_reasons = []
        if hallucination_rate > self.max_hallucination_rate:
            fail_reasons.append(
                f"Hallucination rate {hallucination_rate:.1%} > {self.max_hallucination_rate:.1%}"
            )
        if avg_citation < self.min_citation_ratio:
            fail_reasons.append(
                f"Avg citation ratio {avg_citation:.1%} < {self.min_citation_ratio:.1%}"
            )

        # 최악 케이스 상위 5개
        worst_cases.sort(key=lambda x: x["confidence"])

        return ProductHallucinationReport(
            product_id=product_id,
            total_responses=total,
            grounded_count=grounded_count,
            hallucination_count=hallucination_count,
            hallucination_rate=hallucination_rate,
            avg_citation_ratio=avg_citation,
            avg_fabrication_score=avg_fab,
            avg_confidence=avg_conf,
            worst_cases=worst_cases[:5],
            passed=len(fail_reasons) == 0,
            fail_reasons=fail_reasons,
        )
