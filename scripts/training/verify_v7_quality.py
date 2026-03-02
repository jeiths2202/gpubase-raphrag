#!/usr/bin/env python3
"""
V7 Clean Dataset Quality Verification
클린 데이터셋 품질 샘플 검증

검증 항목:
1. Q&A 완전성 (질문/답변 모두 존재)
2. 질문 품질 (의미있는 질문인지)
3. 답변 품질 (충분한 정보 제공)
4. 제품 관련성 (올바른 제품 정보)
5. 언어 일관성 (JA/KO/EN 일관)
"""

import json
import re
import random
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
V7_DIR = BASE_DIR / "uploads" / "summaries" / "multi_lora_v7_augmented_v2"

# 샘플 수
SAMPLES_PER_PRODUCT = 5


@dataclass
class QualityMetrics:
    """품질 메트릭"""
    product: str
    total_sampled: int = 0
    complete_qa: int = 0          # Q&A 모두 존재
    meaningful_question: int = 0   # 의미있는 질문
    sufficient_answer: int = 0     # 충분한 답변
    product_relevant: int = 0      # 제품 관련
    language_consistent: int = 0   # 언어 일관

    @property
    def quality_score(self) -> float:
        if self.total_sampled == 0:
            return 0.0
        scores = [
            self.complete_qa,
            self.meaningful_question,
            self.sufficient_answer,
            self.product_relevant,
            self.language_consistent
        ]
        return sum(scores) / (self.total_sampled * 5) * 100

    def to_dict(self) -> dict:
        return {
            "total_sampled": self.total_sampled,
            "complete_qa": f"{self.complete_qa}/{self.total_sampled}",
            "meaningful_question": f"{self.meaningful_question}/{self.total_sampled}",
            "sufficient_answer": f"{self.sufficient_answer}/{self.total_sampled}",
            "product_relevant": f"{self.product_relevant}/{self.total_sampled}",
            "language_consistent": f"{self.language_consistent}/{self.total_sampled}",
            "quality_score": f"{self.quality_score:.1f}%"
        }


class QualityVerifier:
    """품질 검증기"""

    # 언어 패턴
    JA_PATTERN = re.compile(r'[\u3040-\u309f\u30a0-\u30ff]')
    KO_PATTERN = re.compile(r'[\uac00-\ud7a3]')

    # 의미없는 질문 패턴
    MEANINGLESS_Q_PATTERNS = [
        r'^\d+\s',                    # 숫자로 시작
        r'^[a-zA-Z]:\\',              # 경로
        r'^\w+\.\w+$',                # 파일명만
        r'^[\w_]+\s*>\s*',            # 명령어 조각
    ]

    # 불충분한 답변 패턴
    INSUFFICIENT_A_PATTERNS = [
        r'^第\d+章',                   # 장 번호만
        r'^Appendix',                 # 부록 참조만
        r'^以下は',                    # 서두만
        r'を参照(して)?ください。?$',   # 참조만
    ]

    def __init__(self):
        self.metrics: Dict[str, QualityMetrics] = {}

    def extract_qa(self, text: str) -> Tuple[str, str, str]:
        """ChatML에서 추출"""
        system = question = answer = ""

        sys_m = re.search(r'<\|im_start\|>system\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if sys_m:
            system = sys_m.group(1).strip()

        user_m = re.search(r'<\|im_start\|>user\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if user_m:
            question = user_m.group(1).strip()

        asst_m = re.search(r'<\|im_start\|>assistant\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if asst_m:
            answer = asst_m.group(1).strip()

        return system, question, answer

    def detect_language(self, text: str) -> str:
        """언어 감지"""
        ja_count = len(self.JA_PATTERN.findall(text))
        ko_count = len(self.KO_PATTERN.findall(text))

        if ja_count > ko_count:
            return "ja"
        elif ko_count > ja_count:
            return "ko"
        return "en"

    def is_meaningful_question(self, question: str) -> bool:
        """의미있는 질문인지"""
        if len(question) < 10:
            return False

        for pattern in self.MEANINGLESS_Q_PATTERNS:
            if re.match(pattern, question):
                return False

        # 질문 형식 확인 (?, 。, ください 등)
        has_question_form = any(q in question for q in ['?', '？', 'ください', '教えて', '説明', '알려', '무엇'])
        return has_question_form or len(question) > 20

    def is_sufficient_answer(self, answer: str) -> bool:
        """충분한 답변인지"""
        # 메타데이터 제거
        clean_answer = re.sub(r'\n\n\*\*製品.*$', '', answer, flags=re.DOTALL)
        clean_answer = re.sub(r'\n\n\*\*出典.*$', '', clean_answer, flags=re.DOTALL)

        if len(clean_answer) < 30:
            return False

        for pattern in self.INSUFFICIENT_A_PATTERNS:
            if re.match(pattern, clean_answer):
                return False

        # 실질적 내용 있는지 (문장 2개 이상)
        sentences = re.split(r'[。．.!?！？]', clean_answer)
        meaningful_sentences = [s for s in sentences if len(s.strip()) > 10]
        return len(meaningful_sentences) >= 1

    def is_product_relevant(self, text: str, product: str) -> bool:
        """제품 관련성"""
        product_keywords = {
            "jeus": ["JEUS", "jeus", "WAS", "서버"],
            "tibero": ["Tibero", "tibero", "데이터베이스", "DB"],
            "ofasm": ["OFASM", "ASM", "아셈블러", "アセンブラ"],
            "ofpli": ["OFPLI", "PL/I", "PLI"],
            "ofcobol": ["OFCOBOL", "COBOL", "コボル"],
            "openframe": ["OpenFrame", "오픈프레임", "TJES", "OSC", "TACF"],
        }

        product_base = product.replace("_v2", "").lower()

        # 매칭되는 키워드 그룹 찾기
        for key, keywords in product_keywords.items():
            if key in product_base or product_base in key:
                return any(kw.lower() in text.lower() for kw in keywords)

        # OpenFrame 계열
        if "openframe" in product_base:
            return any(kw.lower() in text.lower() for kw in product_keywords["openframe"])

        return True  # 기본적으로 통과

    def is_language_consistent(self, system: str, question: str, answer: str) -> bool:
        """언어 일관성"""
        sys_lang = self.detect_language(system)
        q_lang = self.detect_language(question)
        a_lang = self.detect_language(answer)

        # 시스템과 질문/답변 언어가 다르면 불일치
        if sys_lang == "ko" and a_lang == "ja":
            return False
        if sys_lang == "ja" and a_lang == "ko":
            return False

        return True

    def verify_sample(self, text: str, product: str) -> Dict[str, bool]:
        """단일 샘플 검증"""
        system, question, answer = self.extract_qa(text)

        results = {
            "complete_qa": bool(question and answer),
            "meaningful_question": self.is_meaningful_question(question) if question else False,
            "sufficient_answer": self.is_sufficient_answer(answer) if answer else False,
            "product_relevant": self.is_product_relevant(text, product),
            "language_consistent": self.is_language_consistent(system, question, answer),
        }

        return results

    def verify_product(self, product: str, samples: List[dict]) -> QualityMetrics:
        """제품 검증"""
        metrics = QualityMetrics(product=product)
        metrics.total_sampled = len(samples)

        for sample in samples:
            text = sample.get("text", "")
            results = self.verify_sample(text, product)

            if results["complete_qa"]:
                metrics.complete_qa += 1
            if results["meaningful_question"]:
                metrics.meaningful_question += 1
            if results["sufficient_answer"]:
                metrics.sufficient_answer += 1
            if results["product_relevant"]:
                metrics.product_relevant += 1
            if results["language_consistent"]:
                metrics.language_consistent += 1

        return metrics

    def verify_all(self) -> Dict[str, QualityMetrics]:
        """전체 검증"""
        print("\n" + "=" * 80)
        print("  V7 CLEAN DATASET QUALITY VERIFICATION")
        print("=" * 80)

        all_samples = []

        for product_dir in sorted(V7_DIR.iterdir()):
            if not product_dir.is_dir():
                continue

            product = product_dir.name
            train_file = product_dir / "train.json"

            if not train_file.exists():
                continue

            with open(train_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 랜덤 샘플링
            sample_size = min(SAMPLES_PER_PRODUCT, len(data))
            samples = random.sample(data, sample_size) if len(data) > sample_size else data

            metrics = self.verify_product(product, samples)
            self.metrics[product] = metrics
            all_samples.extend(samples)

        # 결과 출력
        print(f"\n{'Product':<25} | {'Samples':>7} | {'Q Score':>7} | {'A Score':>7} | {'Total':>7}")
        print("-" * 80)

        total_score = 0
        for product, m in sorted(self.metrics.items()):
            q_score = m.meaningful_question / max(1, m.total_sampled) * 100
            a_score = m.sufficient_answer / max(1, m.total_sampled) * 100
            total_score += m.quality_score

            print(f"{product:<25} | {m.total_sampled:>7} | {q_score:>6.1f}% | {a_score:>6.1f}% | {m.quality_score:>6.1f}%")

        avg_score = total_score / len(self.metrics) if self.metrics else 0
        print("-" * 80)
        print(f"{'AVERAGE':<25} | {'':<7} | {'':<7} | {'':<7} | {avg_score:>6.1f}%")
        print("=" * 80)

        return self.metrics

    def generate_report(self) -> dict:
        """리포트 생성"""
        report = {
            "summary": {
                "total_products": len(self.metrics),
                "total_samples": sum(m.total_sampled for m in self.metrics.values()),
                "average_quality_score": sum(m.quality_score for m in self.metrics.values()) / max(1, len(self.metrics)),
            },
            "products": {p: m.to_dict() for p, m in self.metrics.items()},
            "quality_issues": []
        }

        # 품질 이슈 식별
        for product, m in self.metrics.items():
            if m.quality_score < 70:
                report["quality_issues"].append({
                    "product": product,
                    "score": m.quality_score,
                    "issues": []
                })

                if m.meaningful_question < m.total_sampled * 0.7:
                    report["quality_issues"][-1]["issues"].append("Low question quality")
                if m.sufficient_answer < m.total_sampled * 0.7:
                    report["quality_issues"][-1]["issues"].append("Insufficient answers")

        return report

    def show_problem_samples(self, limit: int = 5):
        """문제 샘플 표시"""
        print("\n" + "=" * 80)
        print("  PROBLEM SAMPLES (Low Quality)")
        print("=" * 80)

        count = 0
        for product_dir in sorted(V7_DIR.iterdir()):
            if not product_dir.is_dir() or count >= limit:
                break

            product = product_dir.name
            train_file = product_dir / "train.json"

            if not train_file.exists():
                continue

            with open(train_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for item in data[:3]:  # 각 제품에서 최대 3개
                text = item.get("text", "")
                results = self.verify_sample(text, product)

                # 문제 있는 샘플만 표시
                if not all(results.values()):
                    system, question, answer = self.extract_qa(text)
                    issues = [k for k, v in results.items() if not v]

                    print(f"\n[{product}] Issues: {', '.join(issues)}")
                    print(f"  Q: {question[:80]}...")
                    print(f"  A: {answer[:100]}...")
                    count += 1

                    if count >= limit:
                        break


def main():
    random.seed(42)  # 재현성

    verifier = QualityVerifier()
    verifier.verify_all()

    # 리포트 저장
    report = verifier.generate_report()
    report_path = V7_DIR / "quality_verification_report.json"

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n[REPORT] Saved to: {report_path}")

    # 문제 샘플 표시
    verifier.show_problem_samples(limit=10)

    print("\n[DONE] Quality verification complete!")


if __name__ == "__main__":
    main()
