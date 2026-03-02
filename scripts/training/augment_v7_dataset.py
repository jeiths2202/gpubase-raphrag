#!/usr/bin/env python3
"""
Data Augmentation for v7 Clean Dataset
데이터 부족 제품(ofasm, ofpli, ofcobol 등)에 대한 품질 기반 증강

Strategy:
1. v6 원본에서 클리닝 기준 완화로 추가 복구
2. 용어/명령어 요약본에서 새 Q&A 생성
3. 품질 검증 통과 데이터만 추가
"""

import json
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
SUMMARIES_DIR = BASE_DIR / "uploads" / "summaries"
V6_DIR = SUMMARIES_DIR / "multi_lora_v6_final"
V7_DIR = SUMMARIES_DIR / "multi_lora_v7_clean_v2"
OUTPUT_DIR = SUMMARIES_DIR / "multi_lora_v7_augmented_v2"

# 데이터 부족 제품 (클리닝 후 30건 미만)
LOW_DATA_PRODUCTS = {
    "ofasm_v2": 0,
    "ofstudio_v2": 4,
    "ofpli_v2": 6,
    "openframe_ndb_v2": 7,
    "openframe_tacf_v2": 9,
    "openframe_gateway_v2": 12,
    "ofmanager_v2": 15,
    "ofcobol_v2": 16,
    "openframe_vos3_v2": 18,
    "prosort_v2": 18,
    "openframe_base_v2": 19,
    "protrieve_v2": 21,
    "openframe_aim_v2": 25,
    "openframe_hidb_v2": 25,
    "prosync_v2": 25,
}

# 시스템 프롬프트 템플릿
SYSTEM_PROMPTS = {
    "ofasm_v2": "あなたはOFASM専門のテクニカルアシスタントです。OFASMに関する質問に正確に回答してください。",
    "ofpli_v2": "あなたはOFPLI専門のテクニカルアシスタントです。OFPLIに関する質問に正確に回答してください。",
    "ofcobol_v2": "あなたはOFCOBOL専門のテクニカルアシスタントです。OFCOBOLに関する質問に正確に回答してください。",
    "ofmanager_v2": "あなたはOFManager専門のテクニカルアシスタントです。OFManagerに関する質問に正確に回答してください。",
    "openframe_gateway_v2": "あなたはOpenFrame Gateway専門のテクニカルアシスタントです。OpenFrame Gatewayに関する質問に正確に回答してください。",
    "ofstudio_v2": "あなたはOFStudio専門のテクニカルアシスタントです。OFStudioに関する質問に正確に回答してください。",
}

# 제품별 키워드 매핑
PRODUCT_KEYWORDS = {
    "ofasm_v2": ["OFASM", "OFAsm", "アセンブラ", "Assembler", "ASM", "マクロ", "macro"],
    "ofpli_v2": ["OFPLI", "OFPli", "PL/I", "PLI"],
    "ofcobol_v2": ["OFCOBOL", "OFCobol", "COBOL", "コボル"],
    "ofmanager_v2": ["OFManager", "OFMANAGER", "Manager"],
    "openframe_gateway_v2": ["Gateway", "ゲートウェイ", "OFGW"],
    "ofstudio_v2": ["OFStudio", "OFSTUDIO", "Studio"],
}

# 질문 템플릿
QUESTION_TEMPLATES_JP = [
    "{topic}とは何ですか？",
    "{topic}について説明してください。",
    "{topic}の機能について教えてください。",
    "{topic}の使用方法を説明してください。",
    "{topic}の設定方法を教えてください。",
]


@dataclass
class AugmentationStats:
    """증강 통계"""
    product: str
    original_count: int = 0
    recovered_count: int = 0
    generated_count: int = 0
    final_count: int = 0

    def to_dict(self) -> dict:
        return {
            "product": self.product,
            "original_count": self.original_count,
            "recovered_count": self.recovered_count,
            "generated_count": self.generated_count,
            "final_count": self.final_count,
            "augmentation_rate": f"{(self.final_count - self.original_count) / max(1, self.original_count) * 100:.1f}%"
        }


class QualityChecker:
    """품질 검사기 (완화된 기준)"""

    MIN_QUESTION_LENGTH = 10  # 15 → 10으로 완화
    MIN_ANSWER_LENGTH = 25    # 30 → 25로 완화

    # 무효 질문 패턴 (엄격)
    INVALID_QUESTION_PATTERNS = [
        r'^[a-zA-Z]:\\',           # Windows path
        r'^/[a-z]+/',              # Unix path
        r'^\d+\s*$',               # Only numbers
        r'^erData/',               # Truncated path
        r'^er_file_name>',         # Truncated path
    ]

    # 무효 답변 패턴 (엄격)
    INVALID_ANSWER_PATTERNS = [
        r'^第\d+章\s*$',            # Only chapter number
        r'^\d+\s*$',               # Only numbers
        r'^Appendix\s+[A-Z]\s*$',  # Only appendix
    ]

    def __init__(self, product: str):
        self.product = product
        self.keywords = PRODUCT_KEYWORDS.get(product, [])

    def extract_qa(self, text: str) -> Tuple[str, str, str]:
        """ChatML에서 system, question, answer 추출"""
        system = ""
        question = ""
        answer = ""

        sys_match = re.search(r'<\|im_start\|>system\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if sys_match:
            system = sys_match.group(1).strip()

        user_match = re.search(r'<\|im_start\|>user\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if user_match:
            question = user_match.group(1).strip()

        asst_match = re.search(r'<\|im_start\|>assistant\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if asst_match:
            answer = asst_match.group(1).strip()
            # 메타데이터 제거
            answer = re.sub(r'\n\n\*\*製品/Product\*\*:.*$', '', answer, flags=re.DOTALL)
            answer = re.sub(r'\n\n\*\*出典/Source\*\*:.*$', '', answer, flags=re.DOTALL)

        return system, question, answer

    def is_valid_question(self, question: str) -> bool:
        """질문 유효성 검사 (완화)"""
        if len(question) < self.MIN_QUESTION_LENGTH:
            return False

        for pattern in self.INVALID_QUESTION_PATTERNS:
            if re.match(pattern, question):
                return False

        return True

    def is_valid_answer(self, answer: str) -> bool:
        """답변 유효성 검사 (완화)"""
        if len(answer) < self.MIN_ANSWER_LENGTH:
            return False

        for pattern in self.INVALID_ANSWER_PATTERNS:
            if re.match(pattern, answer):
                return False

        return True

    def is_product_relevant(self, text: str) -> bool:
        """제품 관련성 검사"""
        if not self.keywords:
            return True

        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in self.keywords)

    def check_quality(self, text: str) -> Tuple[bool, str]:
        """종합 품질 검사"""
        system, question, answer = self.extract_qa(text)

        if not question or not answer:
            return False, "missing_qa"

        if not self.is_valid_question(question):
            return False, "invalid_question"

        if not self.is_valid_answer(answer):
            return False, "invalid_answer"

        # 제품 관련성 - 답변에서 확인
        if not self.is_product_relevant(answer):
            return False, "not_relevant"

        return True, "ok"


class DataAugmenter:
    """데이터 증강기"""

    def __init__(self):
        self.stats: Dict[str, AugmentationStats] = {}
        self.seen_hashes: Dict[str, Set[str]] = defaultdict(set)

    def get_hash(self, question: str, answer: str) -> str:
        """중복 확인용 해시"""
        normalized_q = re.sub(r'\s+', '', question.lower())
        normalized_a = re.sub(r'\s+', '', answer[:100].lower())
        return hashlib.md5(f"{normalized_q}||{normalized_a}".encode()).hexdigest()

    def recover_from_v6(self, product: str) -> List[dict]:
        """v6에서 완화된 기준으로 데이터 복구"""
        recovered = []
        checker = QualityChecker(product)

        v6_train = V6_DIR / product / "train.json"
        v7_train = V7_DIR / product / "train.json"

        if not v6_train.exists():
            return recovered

        # v7에 이미 있는 데이터 해시 수집
        if v7_train.exists():
            with open(v7_train, 'r', encoding='utf-8') as f:
                v7_data = json.load(f)
                for item in v7_data:
                    text = item.get('text', '')
                    _, q, a = checker.extract_qa(text)
                    self.seen_hashes[product].add(self.get_hash(q, a))

        # v6에서 복구 시도
        with open(v6_train, 'r', encoding='utf-8') as f:
            v6_data = json.load(f)

        for item in v6_data:
            text = item.get('text', '')
            is_valid, reason = checker.check_quality(text)

            if is_valid:
                _, q, a = checker.extract_qa(text)
                item_hash = self.get_hash(q, a)

                if item_hash not in self.seen_hashes[product]:
                    recovered.append(item)
                    self.seen_hashes[product].add(item_hash)

        return recovered

    def generate_from_summaries(self, product: str) -> List[dict]:
        """요약본에서 새 Q&A 생성"""
        generated = []
        checker = QualityChecker(product)
        system_prompt = SYSTEM_PROMPTS.get(product, "あなたは製品専門のテクニカルアシスタントです。")

        # 명령어/용어 요약본 검색
        commands_dir = SUMMARIES_DIR / "commands"
        glossary_dir = SUMMARIES_DIR / "glossary"

        product_base = product.replace("_v2", "").upper()

        # 명령어 요약본에서 생성
        if commands_dir.exists():
            for md_file in commands_dir.glob("*.md"):
                if product_base in md_file.name.upper() or "OPENFRAME" in md_file.name.upper():
                    generated.extend(
                        self._generate_from_markdown(md_file, product, system_prompt, checker)
                    )

        return generated[:30]  # 최대 30개

    def _generate_from_markdown(self, md_file: Path, product: str,
                                 system_prompt: str, checker: QualityChecker) -> List[dict]:
        """마크다운 파일에서 Q&A 생성"""
        generated = []

        try:
            content = md_file.read_text(encoding='utf-8')
        except Exception:
            return generated

        # 섹션 추출 (## 헤딩 기준)
        sections = re.split(r'\n##\s+', content)

        for section in sections[1:]:  # 첫 번째는 헤더이므로 제외
            lines = section.strip().split('\n')
            if not lines:
                continue

            title = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()

            if len(title) < 3 or len(body) < 30:
                continue

            # 제품 관련성 확인
            if not checker.is_product_relevant(body):
                continue

            # Q&A 생성
            for template in QUESTION_TEMPLATES_JP[:2]:  # 2개 템플릿만 사용
                question = template.format(topic=title)
                answer = body[:500]  # 최대 500자

                # 중복 확인
                item_hash = self.get_hash(question, answer)
                if item_hash in self.seen_hashes[product]:
                    continue

                # ChatML 형식 생성
                text = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                text += f"<|im_start|>user\n{question}<|im_end|>\n"
                text += f"<|im_start|>assistant\n{answer}\n\n**製品/Product**: {product.replace('_v2', '').upper()}<|im_end|>"

                # 최종 품질 검사
                is_valid, _ = checker.check_quality(text)
                if is_valid:
                    generated.append({"text": text})
                    self.seen_hashes[product].add(item_hash)

        return generated

    def augment_product(self, product: str) -> AugmentationStats:
        """단일 제품 증강"""
        stats = AugmentationStats(product=product)

        # 현재 v7 데이터 로드
        v7_train = V7_DIR / product / "train.json"
        current_data = []

        if v7_train.exists():
            with open(v7_train, 'r', encoding='utf-8') as f:
                current_data = json.load(f)

        stats.original_count = len(current_data)

        # 1. v6에서 복구
        recovered = self.recover_from_v6(product)
        stats.recovered_count = len(recovered)

        # 2. 요약본에서 생성
        generated = self.generate_from_summaries(product)
        stats.generated_count = len(generated)

        # 3. 병합
        augmented_data = current_data + recovered + generated
        stats.final_count = len(augmented_data)

        # 4. 저장
        output_dir = OUTPUT_DIR / product
        output_dir.mkdir(parents=True, exist_ok=True)

        # train/eval 분리 (80/20)
        train_count = int(len(augmented_data) * 0.8)
        train_data = augmented_data[:train_count]
        eval_data = augmented_data[train_count:]

        with open(output_dir / "train.json", 'w', encoding='utf-8') as f:
            json.dump(train_data, f, ensure_ascii=False, indent=2)

        with open(output_dir / "eval.json", 'w', encoding='utf-8') as f:
            json.dump(eval_data, f, ensure_ascii=False, indent=2)

        self.stats[product] = stats
        return stats

    def augment_all(self):
        """모든 부족 제품 증강"""
        print("\n" + "=" * 70)
        print("  DATA AUGMENTATION FOR V7 CLEAN DATASET")
        print("=" * 70)
        print(f"{'Product':<25} | {'Original':>8} | {'Recovered':>9} | {'Generated':>9} | {'Final':>7}")
        print("-" * 70)

        for product in LOW_DATA_PRODUCTS:
            stats = self.augment_product(product)
            print(f"{product:<25} | {stats.original_count:>8} | {stats.recovered_count:>9} | {stats.generated_count:>9} | {stats.final_count:>7}")

        print("-" * 70)

        # 나머지 제품은 v7에서 복사
        self._copy_other_products()

        # 통합 파일 생성
        self._merge_all()

        # 리포트 저장
        self._save_report()

    def _copy_other_products(self):
        """증강 대상이 아닌 제품은 v7에서 그대로 복사"""
        for product_dir in V7_DIR.iterdir():
            if not product_dir.is_dir():
                continue

            product = product_dir.name
            if product in LOW_DATA_PRODUCTS:
                continue  # 이미 증강됨

            output_dir = OUTPUT_DIR / product
            output_dir.mkdir(parents=True, exist_ok=True)

            for json_file in product_dir.glob("*.json"):
                content = json_file.read_text(encoding='utf-8')
                (output_dir / json_file.name).write_text(content, encoding='utf-8')

    def _merge_all(self):
        """모든 제품 통합"""
        train_all = []
        eval_all = []

        for product_dir in sorted(OUTPUT_DIR.iterdir()):
            if not product_dir.is_dir():
                continue

            train_path = product_dir / "train.json"
            eval_path = product_dir / "eval.json"

            if train_path.exists():
                with open(train_path, 'r', encoding='utf-8') as f:
                    train_all.extend(json.load(f))

            if eval_path.exists():
                with open(eval_path, 'r', encoding='utf-8') as f:
                    eval_all.extend(json.load(f))

        with open(OUTPUT_DIR / "train_all.json", 'w', encoding='utf-8') as f:
            json.dump(train_all, f, ensure_ascii=False, indent=2)

        with open(OUTPUT_DIR / "eval_all.json", 'w', encoding='utf-8') as f:
            json.dump(eval_all, f, ensure_ascii=False, indent=2)

        print(f"\n[MERGED] train_all.json: {len(train_all):,} records")
        print(f"[MERGED] eval_all.json: {len(eval_all):,} records")

    def _save_report(self):
        """증강 리포트 저장"""
        report = {
            "summary": {
                "augmented_products": len(self.stats),
                "total_original": sum(s.original_count for s in self.stats.values()),
                "total_recovered": sum(s.recovered_count for s in self.stats.values()),
                "total_generated": sum(s.generated_count for s in self.stats.values()),
                "total_final": sum(s.final_count for s in self.stats.values()),
            },
            "products": {p: s.to_dict() for p, s in self.stats.items()}
        }

        with open(OUTPUT_DIR / "augmentation_report.json", 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n[REPORT] Saved to: {OUTPUT_DIR / 'augmentation_report.json'}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    augmenter = DataAugmenter()
    augmenter.augment_all()

    print("\n[DONE] Data augmentation complete!")


if __name__ == "__main__":
    main()
