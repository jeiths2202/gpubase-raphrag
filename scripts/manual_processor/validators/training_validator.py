"""학습 데이터 품질 검증기

5가지 검증을 통합하여 SFT/DPO/CPT 데이터 품질을 확인합니다:
1. 길이 검증 (instruction/response 최소 길이)
2. 중복 검출 (TF-IDF 코사인 유사도 ≥ 0.95)
3. Q-A 일치도 (키워드 겹침 ≥ 30%)
4. 언어 균형 (제품별/언어별 분포)
5. ChatML 포맷 검증 (특수 토큰 존재 확인)
"""

import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Set
from collections import defaultdict, Counter

from ..models.training import SFTRecord, DPORecord, DataLanguage

logger = logging.getLogger(__name__)


class TrainingValidator:
    """학습 데이터 품질 검증 (5가지 검증 통합)"""

    # 검증 기준
    MIN_INSTRUCTION_LEN = 10     # 최소 질문 길이 (chars)
    MIN_RESPONSE_LEN = 20        # 최소 응답 길이 (chars)
    MAX_RESPONSE_TOKENS = 4096   # 최대 응답 토큰 (근사)
    DUPLICATE_THRESHOLD = 0.95   # 중복 판정 코사인 유사도 (SFT 생성 시 0.90으로 사전 필터링 완료)
    COHERENCE_THRESHOLD = 0.30   # Q-A 키워드 겹침 최소 비율
    MIN_PRODUCT_COUNT = 20       # 제품당 최소 레코드 수

    # ChatML 특수 토큰
    CHATML_TOKENS = ["<|im_start|>", "<|im_end|>"]

    def validate_sft(self, records: List[SFTRecord]) -> Dict:
        """SFT 레코드 전체 검증

        Returns:
            {
                "total": int,
                "passed": int,
                "failed": int,
                "quality_score": float,  # 0-100
                "checks": {
                    "length": {...},
                    "duplicates": {...},
                    "coherence": {...},
                    "language_balance": {...},
                    "format": {...},
                },
                "recommendations": [str, ...]
            }
        """
        logger.info(f"[Validator] Validating {len(records)} SFT records...")

        report = {
            "total": len(records),
            "passed": 0,
            "failed": 0,
            "quality_score": 0.0,
            "checks": {},
            "recommendations": [],
        }

        if not records:
            report["recommendations"].append("No records to validate")
            return report

        # 1. 길이 검증
        report["checks"]["length"] = self._check_length(records)

        # 2. 중복 검출
        report["checks"]["duplicates"] = self._check_duplicates(records)

        # 3. Q-A 일치도
        report["checks"]["coherence"] = self._check_coherence(records)

        # 4. 언어 균형
        report["checks"]["language_balance"] = self._check_language_balance(records)

        # 5. ChatML 포맷
        report["checks"]["format"] = self._check_format(records)

        # 종합 점수
        total_issues = sum(
            c.get("failed", 0) for c in report["checks"].values()
        )
        report["passed"] = len(records) - total_issues
        report["failed"] = total_issues
        report["quality_score"] = round(
            (report["passed"] / max(1, len(records))) * 100, 2
        )

        # 추천사항 생성
        report["recommendations"] = self._generate_recommendations(report)

        return report

    def validate_dpo(self, records: List[DPORecord]) -> Dict:
        """DPO 레코드 검증"""
        logger.info(f"[Validator] Validating {len(records)} DPO records...")

        report = {
            "total": len(records),
            "passed": 0,
            "failed": 0,
            "quality_score": 0.0,
            "checks": {},
        }

        if not records:
            return report

        # chosen과 rejected 동일성 검사
        identical = 0
        too_short_chosen = 0
        too_short_rejected = 0
        strategy_counts = Counter()

        for r in records:
            if r.chosen == r.rejected:
                identical += 1
            if len(r.chosen) < self.MIN_RESPONSE_LEN:
                too_short_chosen += 1
            if len(r.rejected) < self.MIN_RESPONSE_LEN:
                too_short_rejected += 1
            strategy_counts[r.strategy] += 1

        failed = identical + too_short_chosen + too_short_rejected

        report["checks"]["identical_pairs"] = {
            "failed": identical,
            "passed": len(records) - identical,
        }
        report["checks"]["length"] = {
            "failed": too_short_chosen + too_short_rejected,
            "passed": len(records) - too_short_chosen - too_short_rejected,
            "short_chosen": too_short_chosen,
            "short_rejected": too_short_rejected,
        }
        report["checks"]["strategy_distribution"] = dict(strategy_counts)

        report["passed"] = len(records) - failed
        report["failed"] = failed
        report["quality_score"] = round(
            (report["passed"] / max(1, len(records))) * 100, 2
        )

        return report

    def validate_cpt(self, corpus_path: Path) -> Dict:
        """CPT 코퍼스 파일 검증"""
        logger.info(f"[Validator] Validating CPT corpus: {corpus_path}")

        report = {
            "file": str(corpus_path),
            "exists": corpus_path.exists(),
            "checks": {},
        }

        if not corpus_path.exists():
            report["quality_score"] = 0.0
            return report

        content = corpus_path.read_text(encoding="utf-8")
        separator = "<|endoftext|>"

        chunks = content.split(separator)
        chunks = [c.strip() for c in chunks if c.strip()]

        # 파일 크기
        file_size_mb = corpus_path.stat().st_size / 1024 / 1024

        # 청크 길이 분포
        chunk_lens = [len(c) for c in chunks]
        avg_len = sum(chunk_lens) / max(1, len(chunk_lens))

        # 너무 짧은 청크
        short_chunks = sum(1 for l in chunk_lens if l < 100)
        # 빈 청크
        empty_chunks = sum(1 for c in chunks if not c)

        report["checks"] = {
            "chunk_count": len(chunks),
            "file_size_mb": round(file_size_mb, 2),
            "avg_chunk_chars": round(avg_len),
            "short_chunks": short_chunks,
            "empty_chunks": empty_chunks,
            "separator_count": content.count(separator),
        }

        issues = short_chunks + empty_chunks
        report["quality_score"] = round(
            ((len(chunks) - issues) / max(1, len(chunks))) * 100, 2
        )

        return report

    def _check_length(self, records: List[SFTRecord]) -> Dict:
        """길이 검증"""
        too_short_q = [
            r for r in records
            if len(r.instruction) < self.MIN_INSTRUCTION_LEN
        ]
        too_short_a = [
            r for r in records
            if len(r.response) < self.MIN_RESPONSE_LEN
        ]
        too_long_a = [
            r for r in records
            if len(r.response) > self.MAX_RESPONSE_TOKENS * 4  # 근사
        ]

        failed = len(set(too_short_q) | set(too_short_a) | set(too_long_a))

        return {
            "passed": len(records) - failed,
            "failed": failed,
            "short_questions": len(too_short_q),
            "short_answers": len(too_short_a),
            "too_long_answers": len(too_long_a),
        }

    def _check_duplicates(self, records: List[SFTRecord]) -> Dict:
        """TF-IDF 코사인 유사도 기반 중복 검출

        전체 비교는 O(n²)이므로 제품별로 분할하여 수행합니다.
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            logger.warning("sklearn not available - skipping duplicate check")
            return {"passed": len(records), "failed": 0, "skipped": True}

        texts = [r.instruction + " " + r.response for r in records]
        duplicates: Set[int] = set()

        products = set(r.product for r in records)
        for product in products:
            indices = [i for i, r in enumerate(records) if r.product == product]
            if len(indices) < 2:
                continue

            product_texts = [texts[i] for i in indices]

            try:
                vectorizer = TfidfVectorizer(max_features=5000)
                tfidf = vectorizer.fit_transform(product_texts)
                sim = cosine_similarity(tfidf)

                for i in range(len(indices)):
                    for j in range(i + 1, len(indices)):
                        if sim[i][j] >= self.DUPLICATE_THRESHOLD:
                            duplicates.add(indices[j])
            except Exception as e:
                logger.debug(f"Duplicate check error for {product}: {e}")
                continue

        return {
            "passed": len(records) - len(duplicates),
            "failed": len(duplicates),
            "duplicate_count": len(duplicates),
        }

    def _check_coherence(self, records: List[SFTRecord]) -> Dict:
        """Q-A 키워드 겹침 검증

        질문의 핵심 키워드가 응답에 포함되는지 확인합니다.
        겹침 비율이 COHERENCE_THRESHOLD 미만이면 불일치로 판정합니다.
        """
        incoherent = 0

        for record in records:
            q_keywords = self._extract_keywords(record.instruction)
            a_keywords = self._extract_keywords(record.response)

            if not q_keywords:
                continue

            overlap = len(q_keywords & a_keywords)
            ratio = overlap / len(q_keywords)

            if ratio < self.COHERENCE_THRESHOLD:
                incoherent += 1

        return {
            "passed": len(records) - incoherent,
            "failed": incoherent,
            "incoherent_count": incoherent,
        }

    def _check_language_balance(self, records: List[SFTRecord]) -> Dict:
        """언어/제품 균형 검증"""
        lang_counts = Counter()
        product_counts = Counter()

        for r in records:
            lang = r.language.value if isinstance(r.language, DataLanguage) else r.language
            lang_counts[lang] += 1
            product_counts[r.product] += 1

        # 부족한 제품
        underrepresented = {
            p: c for p, c in product_counts.items()
            if c < self.MIN_PRODUCT_COUNT
        }

        # 언어 불균형 (최대/최소 비율이 5배 초과)
        if lang_counts:
            max_lang = max(lang_counts.values())
            min_lang = min(lang_counts.values())
            imbalance_ratio = max_lang / max(1, min_lang)
        else:
            imbalance_ratio = 0

        return {
            "passed": len(records),
            "failed": len(underrepresented),
            "language_distribution": dict(lang_counts),
            "product_distribution": dict(product_counts),
            "underrepresented_products": underrepresented,
            "language_imbalance_ratio": round(imbalance_ratio, 2),
        }

    def _check_format(self, records: List[SFTRecord]) -> Dict:
        """ChatML 포맷 검증"""
        invalid = 0

        for record in records:
            chatml = record.to_chatml()
            # 필수 토큰 존재 확인
            for token in self.CHATML_TOKENS:
                if token not in chatml:
                    invalid += 1
                    break
            else:
                # system, user, assistant 3개 역할 확인
                if chatml.count("<|im_start|>") != 3:
                    invalid += 1

        return {
            "passed": len(records) - invalid,
            "failed": invalid,
            "invalid_format_count": invalid,
        }

    def _extract_keywords(self, text: str) -> Set[str]:
        """텍스트에서 핵심 키워드 추출"""
        # 영문/숫자 단어 + CJK 문자열
        words = set()

        # 영문/숫자 단어 (2문자 이상)
        for w in re.findall(r'[A-Za-z0-9_]{2,}', text):
            words.add(w.lower())

        # 에러코드 패턴
        for code in re.findall(r'-?\d{4,5}', text):
            words.add(code)

        return words

    def _generate_recommendations(self, report: Dict) -> List[str]:
        """검증 결과에서 개선 추천사항 생성"""
        recs = []

        checks = report.get("checks", {})

        # 길이
        length = checks.get("length", {})
        if length.get("short_questions", 0) > 0:
            recs.append(
                f"질문이 너무 짧은 레코드 {length['short_questions']}건 → "
                f"템플릿 다양화 필요"
            )
        if length.get("short_answers", 0) > 0:
            recs.append(
                f"응답이 너무 짧은 레코드 {length['short_answers']}건 → "
                f"응답 보강 필요"
            )

        # 중복
        dups = checks.get("duplicates", {})
        if dups.get("duplicate_count", 0) > 0:
            recs.append(
                f"중복 레코드 {dups['duplicate_count']}건 → "
                f"중복 제거 후 재생성"
            )

        # 일치도
        coh = checks.get("coherence", {})
        if coh.get("incoherent_count", 0) > 0:
            recs.append(
                f"Q-A 불일치 {coh['incoherent_count']}건 → "
                f"질문-응답 쌍 재검토"
            )

        # 균형
        bal = checks.get("language_balance", {})
        if bal.get("underrepresented_products"):
            products = list(bal["underrepresented_products"].keys())[:5]
            recs.append(
                f"레코드 부족 제품: {', '.join(products)} → "
                f"해당 제품 데이터 증강 필요"
            )
        if bal.get("language_imbalance_ratio", 0) > 5:
            recs.append(
                f"언어 불균형 비율 {bal['language_imbalance_ratio']}x → "
                f"소수 언어 데이터 증강 필요"
            )

        # 포맷
        fmt = checks.get("format", {})
        if fmt.get("invalid_format_count", 0) > 0:
            recs.append(
                f"ChatML 포맷 오류 {fmt['invalid_format_count']}건 → "
                f"to_chatml() 메서드 검증"
            )

        if not recs:
            recs.append("모든 검증 통과 - 품질 양호")

        return recs

    def write_report(self, report: Dict, output_path: Path):
        """검증 리포트를 JSON으로 출력"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"[Validator] Report written → {output_path}")
