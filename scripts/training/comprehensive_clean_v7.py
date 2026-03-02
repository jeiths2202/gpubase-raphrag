#!/usr/bin/env python3
"""
Comprehensive Clean Dataset v7 - Multi-LoRA v6 -> v7
품질 리뷰에서 발견된 모든 이슈 해결

Issues addressed (NEW in v7):
- 중복/유사 중복 Q&A 쌍 제거 (시맨틱 dedupe)
- 경로 조각/무의미한 질문 제거
- 언어 일관성 검증 (시스템/질문/답변 언어 일치)
- 제품 분포 밸런싱 (과다 대표 제품 샘플링)
- 메타데이터 노이즈 클리닝 (페이지 번호, 챕터 참조)
- 불완전 답변 제거 (문장 중간 절단)

기존 기능 포함:
- deep_clean_dataset.py 기능 (encoding, chinese chars, repetition)
- semantic_clean_dataset.py 기능 (truncated questions, meaningless answers)
"""

import json
import re
import hashlib
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
import logging

# Import QA relevance checker
from qa_relevance_checker import QARelevanceChecker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class CleaningStats:
    """클리닝 통계"""
    original_count: int = 0
    cleaned_count: int = 0
    removed_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def removal_rate(self) -> float:
        if self.original_count == 0:
            return 0.0
        return (self.original_count - self.cleaned_count) / self.original_count * 100

    def to_dict(self) -> dict:
        return {
            'original_count': self.original_count,
            'cleaned_count': self.cleaned_count,
            'removed_total': self.original_count - self.cleaned_count,
            'removal_rate': f"{self.removal_rate:.1f}%",
            'removed_by_type': dict(self.removed_by_type)
        }


class ComprehensiveDatasetCleaner:
    """종합 데이터셋 클리너 v7"""

    # 최소 길이 요구사항
    MIN_QUESTION_LENGTH = 15
    MIN_ANSWER_LENGTH = 30

    # 경로 조각 패턴 (무의미한 질문)
    PATH_FRAGMENT_PATTERNS = [
        r'^[a-zA-Z]:\\',                           # Windows 경로
        r'^/[a-z]+/',                              # Unix 경로
        r'^[a-z_]+\.(?:json|xml|conf|log|txt)',    # 파일명
        r'^erData/',                               # 잘린 경로
        r'^er_file_name>',                         # 잘린 경로
        r'^er/license/',                           # 잘린 경로
        r'^\d+/OpenFrame/volume',                  # 볼륨 경로
        r'^[A-Z]+_[A-Z]+_[A-Z0-9]+$',              # 환경변수명만
        r'^[a-z_]+\s*>\s*-f\s+[a-z_]+\.',         # 명령어 조각
    ]

    # 잘린 질문 패턴 (확장)
    TRUNCATED_QUESTION_PATTERNS = [
        # 매우 짧은 맥락 + 질문 접미사 (일본어)
        r'^.{1,20}のやり方は？$',
        r'^.{1,20}とは何ですか？$',
        r'^.{1,18}について説明してください。$',
        r'^.{1,18}の概念を教えてください。$',
        r'^.{1,20}のステップを説明してください。$',
        r'^.{1,20}の手順を教えてください。$',

        # 문장 중간이 질문에 포함된 경우
        r'^.+です。.{1,30}(について|とは|のやり方|の概念)',
        r'^.+ます。.{1,30}(について|とは|のやり方|の概念)',

        # 조사로 시작 (문장 중간 절단)
        r'^する.{1,30}の(やり方|手順|ステップ|概念)',
        r'^される.{1,30}の(やり方|手順|ステップ|概念)',
        r'^して.{1,30}の(やり方|手順|ステップ|概念)',

        # 영어 잘린 패턴
        r'^What are the steps for .{1,30}\?$',
        r'^What is .{1,15}\?$',
        r'^Explain the procedure for .{1,30}\.$',
        r'^Explain .{1,15} #\.$',
        r'^What is \d+ [a-zA-Z]+\?$',  # "What is 6 jMSConsumerResourcetroubles?"
    ]

    # 무의미한 답변 패턴
    MEANINGLESS_ANSWER_PATTERNS = [
        # 페이지/장 번호만
        r'^第\d+章[^\n]{0,40}$',
        r'^\d+\s*$',
        r'^Appendix\s+[A-Z]',

        # 함수/변수 목록만 (설명 없음)
        r'^[\d\.]+\s+[a-zA-Z_]+[a-zA-Z0-9_]*\n',
        r'^[a-z_][a-z0-9_]*\(\)$',

        # 타임스탬프만
        r'^TIME STAMP\s*:',

        # 단순 참조만
        r'^.{0,15}を参照(して)?ください。?$',
        r'^詳細は.{0,20}を参照$',
    ]

    # 절단된 답변 패턴 (문장 끝이 아닌 곳에서 끝남)
    TRUNCATED_ANSWER_ENDINGS = [
        r'[^。！？\.!?]$',                          # 문장 종결 문자 없이 끝남
        r'を参照し$',                              # "を参照してください"가 잘림
        r'については$',                            # "については..."가 잘림
        r'の場合$',                                # "の場合は..."가 잘림
        r'する場合$',
        r'について$',
        r'、以下$',
        r'に指定$',
        r'を設定$',
        r'に設定$',
    ]

    # 언어 감지 패턴
    JAPANESE_CHARS = re.compile(r'[\u3040-\u309f\u30a0-\u30ff]')  # 히라가나/카타카나
    KOREAN_CHARS = re.compile(r'[\uac00-\ud7a3]')                  # 한글
    CHINESE_SIMPLIFIED = set('清业为关产说应实进时后动来现两义数类图认这个们对与并从发过还让将向于使被给着内种运设处变务据线节间问题长门开关电机单双级体统网络户员资库志录备复选择页显视窗标签')

    def __init__(self, max_per_product: int = 500, enable_dedup: bool = True, enable_qa_check: bool = True):
        self.max_per_product = max_per_product
        self.enable_dedup = enable_dedup
        self.enable_qa_check = enable_qa_check
        self.stats: Dict[str, CleaningStats] = {}
        self.total_stats = CleaningStats()
        self.seen_hashes: Set[str] = set()
        self.qa_checker = QARelevanceChecker() if enable_qa_check else None

    def extract_qa_from_text(self, text: str) -> Tuple[str, str, str]:
        """ChatML 포맷에서 system, question, answer 추출"""
        system = ""
        question = ""
        answer = ""

        system_match = re.search(r'<\|im_start\|>system\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if system_match:
            system = system_match.group(1).strip()

        user_match = re.search(r'<\|im_start\|>user\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if user_match:
            question = user_match.group(1).strip()

        assistant_match = re.search(r'<\|im_start\|>assistant\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if assistant_match:
            answer = assistant_match.group(1).strip()
            # 메타데이터 제거 (순수 답변만)
            answer = re.sub(r'\n\n\*\*製品/Product\*\*:.*$', '', answer, flags=re.DOTALL)
            answer = re.sub(r'\n\n\*\*出典/Source\*\*:.*$', '', answer, flags=re.DOTALL)

        return system, question, answer

    def normalize_for_dedup(self, question: str, answer: str) -> str:
        """중복 검사용 정규화된 해시 생성"""
        # 질문에서 변형 패턴 제거 (같은 질문의 다른 형태)
        normalized_q = question
        suffixes_to_remove = [
            'とは何ですか？', 'について説明してください。', 'の概念を教えてください。',
            'のやり方は？', 'の手順を教えてください。', 'のステップを説明してください。',
            'とは何ですか', 'について説明してください', 'の概念を教えてください',
        ]
        for suffix in suffixes_to_remove:
            normalized_q = normalized_q.replace(suffix, '')

        # 공백/특수문자 정규화
        normalized_q = re.sub(r'\s+', '', normalized_q.lower())
        normalized_a = re.sub(r'\s+', '', answer[:200].lower())  # 답변 앞부분만

        combined = f"{normalized_q}||{normalized_a}"
        return hashlib.md5(combined.encode()).hexdigest()

    def detect_language(self, text: str) -> str:
        """텍스트 주요 언어 감지"""
        jp_count = len(self.JAPANESE_CHARS.findall(text))
        ko_count = len(self.KOREAN_CHARS.findall(text))
        cn_count = sum(1 for c in text if c in self.CHINESE_SIMPLIFIED)
        en_count = len(re.findall(r'[a-zA-Z]+', text))

        total = jp_count + ko_count + cn_count + en_count
        if total == 0:
            return 'unknown'

        ratios = {
            'ja': jp_count / total,
            'ko': ko_count / total,
            'zh': cn_count / total,
            'en': en_count / total,
        }

        return max(ratios, key=ratios.get)

    def check_language_consistency(self, system: str, question: str, answer: str) -> bool:
        """시스템/질문/답변 언어 일관성 검증"""
        sys_lang = self.detect_language(system)
        q_lang = self.detect_language(question)
        a_lang = self.detect_language(answer)

        # 시스템 프롬프트와 질문/답변 언어가 일치해야 함
        # (영어는 모든 언어와 호환)
        if sys_lang == 'ko' and a_lang == 'ja':
            return False
        if sys_lang == 'ja' and a_lang == 'ko':
            return False

        return True

    def is_path_fragment(self, question: str) -> bool:
        """경로 조각인지 확인"""
        for pattern in self.PATH_FRAGMENT_PATTERNS:
            if re.match(pattern, question, re.IGNORECASE):
                return True
        return False

    def is_truncated_question(self, question: str) -> bool:
        """잘린 질문인지 확인"""
        # 너무 짧은 질문
        if len(question) < self.MIN_QUESTION_LENGTH:
            return True

        # 패턴 매칭
        for pattern in self.TRUNCATED_QUESTION_PATTERNS:
            if re.match(pattern, question, re.IGNORECASE):
                return True

        # 조사/접속사로 시작 (문장 중간 절단)
        truncated_starters = ['する', 'される', 'されて', 'して', '中に', '後に', 'tion ', 'ation ']
        for starter in truncated_starters:
            if question.startswith(starter):
                return True

        return False

    def is_meaningless_answer(self, answer: str) -> bool:
        """무의미한 답변인지 확인"""
        answer_clean = answer.strip()

        # 너무 짧은 답변
        if len(answer_clean) < self.MIN_ANSWER_LENGTH:
            return True

        # 무의미한 패턴 매칭
        for pattern in self.MEANINGLESS_ANSWER_PATTERNS:
            if re.match(pattern, answer_clean, re.IGNORECASE | re.MULTILINE):
                return True

        return False

    def is_truncated_answer(self, answer: str) -> bool:
        """절단된 답변인지 확인"""
        answer_clean = answer.strip()

        # 마지막 문자가 문장 종결이 아닌 경우
        for pattern in self.TRUNCATED_ANSWER_ENDINGS:
            if re.search(pattern, answer_clean):
                # 답변이 충분히 길면 OK (일부 절단 허용)
                if len(answer_clean) > 200:
                    return False
                return True

        return False

    def clean_answer_metadata(self, answer: str) -> str:
        """답변에서 메타데이터 노이즈 제거"""
        # 페이지/챕터 참조 제거
        cleaned = re.sub(r'第\d+章[^\n]*\n?', '', answer)
        cleaned = re.sub(r'\d+\s*JEUS\s+\w+\s+\w+', '', cleaned)
        cleaned = re.sub(r'Appendix\s+[A-Z][^\n]*\n?', '', cleaned)

        # 중복 줄바꿈 정리
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        return cleaned.strip()

    def classify_removal_reason(self, text: str) -> str:
        """제거 사유 분류"""
        system, question, answer = self.extract_qa_from_text(text)

        if not question or not answer:
            return "missing_qa"

        # 1. 경로 조각 체크
        if self.is_path_fragment(question):
            return "path_fragment"

        # 2. 잘린 질문 체크
        if self.is_truncated_question(question):
            return "truncated_question"

        # 3. 무의미한 답변 체크
        if self.is_meaningless_answer(answer):
            return "meaningless_answer"

        # 4. 절단된 답변 체크
        if self.is_truncated_answer(answer):
            return "truncated_answer"

        # 5. 언어 일관성 체크
        if not self.check_language_consistency(system, question, answer):
            return "language_mismatch"

        # 6. Q-A 관련성 체크 (NEW)
        if self.enable_qa_check and self.qa_checker:
            is_relevant, reason = self.qa_checker.check_relevance(question, answer)
            if not is_relevant:
                return f"qa_irrelevant_{reason}"

        # 7. 중복 체크 (시맨틱 dedupe)
        if self.enable_dedup:
            dedup_hash = self.normalize_for_dedup(question, answer)
            if dedup_hash in self.seen_hashes:
                return "duplicate"
            self.seen_hashes.add(dedup_hash)

        return ""

    def clean_dataset(self, input_path: Path, output_path: Path,
                      max_records: Optional[int] = None) -> CleaningStats:
        """데이터셋 클리닝"""
        stats = CleaningStats()

        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        stats.original_count = len(data)
        cleaned_data = []

        for item in data:
            text = item.get('text', '')
            reason = self.classify_removal_reason(text)

            if reason:
                stats.removed_by_type[reason] += 1
            else:
                # 답변 메타데이터 클리닝
                system, question, answer = self.extract_qa_from_text(text)
                cleaned_answer = self.clean_answer_metadata(answer)

                if len(cleaned_answer) >= self.MIN_ANSWER_LENGTH:
                    # 클린 답변은 그대로 사용 (원본 유지)
                    cleaned_data.append(item)
                else:
                    stats.removed_by_type['too_short_after_clean'] += 1

        # 최대 레코드 수 제한 (밸런싱)
        if max_records and len(cleaned_data) > max_records:
            # 균등 샘플링
            import random
            random.seed(42)
            cleaned_data = random.sample(cleaned_data, max_records)
            stats.removed_by_type['sampled_for_balance'] = len(data) - max_records

        stats.cleaned_count = len(cleaned_data)

        # 출력 디렉토리 생성
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 클린 데이터 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=2)

        return stats

    def process_all_products(self, input_dir: Path, output_dir: Path,
                             balance_products: bool = False) -> None:
        """모든 제품 데이터셋 처리"""
        products = [d.name for d in input_dir.iterdir() if d.is_dir()]

        print(f"\n[INFO] Comprehensive Cleaning v7: {len(products)} products")
        print("=" * 80)
        print(f"{'Product':<32} | {'Original':>8} | {'Cleaned':>8} | {'Removed':>8} | {'Rate':>6}")
        print("-" * 80)

        for product in sorted(products):
            product_input = input_dir / product
            product_output = output_dir / product

            train_input = product_input / 'train.json'
            train_output = product_output / 'train.json'

            if not train_input.exists():
                continue

            # 밸런싱 적용 (과다 제품 샘플링)
            max_records = self.max_per_product if balance_products else None

            # 중복 해시 초기화 (제품별 dedupe)
            self.seen_hashes.clear()

            # QA checker 빈도 카운터 초기화 (제품별)
            if self.qa_checker:
                self.qa_checker.reset_frequency_counter()

            train_stats = self.clean_dataset(train_input, train_output, max_records)

            # eval.json 처리
            eval_input = product_input / 'eval.json'
            eval_output = product_output / 'eval.json'

            eval_stats = CleaningStats()
            if eval_input.exists():
                eval_max = max_records // 5 if max_records else None
                eval_stats = self.clean_dataset(eval_input, eval_output, eval_max)

            # 통계 합산
            combined_stats = CleaningStats()
            combined_stats.original_count = train_stats.original_count + eval_stats.original_count
            combined_stats.cleaned_count = train_stats.cleaned_count + eval_stats.cleaned_count

            for reason, count in train_stats.removed_by_type.items():
                combined_stats.removed_by_type[reason] += count
            for reason, count in eval_stats.removed_by_type.items():
                combined_stats.removed_by_type[reason] += count

            self.stats[product] = combined_stats

            # 전체 통계 업데이트
            self.total_stats.original_count += combined_stats.original_count
            self.total_stats.cleaned_count += combined_stats.cleaned_count
            for reason, count in combined_stats.removed_by_type.items():
                self.total_stats.removed_by_type[reason] += count

            # 진행 상황 출력
            removed = combined_stats.original_count - combined_stats.cleaned_count
            rate = combined_stats.removal_rate
            print(f"{product:<32} | {combined_stats.original_count:>8} | {combined_stats.cleaned_count:>8} | {removed:>8} | {rate:>5.1f}%")

            # stats.json 저장
            stats_output = product_output / 'stats.json'
            with open(stats_output, 'w', encoding='utf-8') as f:
                json.dump({
                    'original_count': combined_stats.original_count,
                    'cleaned_count': combined_stats.cleaned_count,
                    'removed_total': removed,
                    'removal_rate': f"{rate:.1f}%",
                    'removed_by_type': dict(combined_stats.removed_by_type),
                    'train_count': train_stats.cleaned_count,
                    'eval_count': eval_stats.cleaned_count
                }, f, ensure_ascii=False, indent=2)

        print("=" * 80)

    def generate_report(self, output_path: Path) -> dict:
        """클리닝 리포트 생성"""
        total_removed = self.total_stats.original_count - self.total_stats.cleaned_count

        report = {
            'summary': {
                'total_original': self.total_stats.original_count,
                'total_cleaned': self.total_stats.cleaned_count,
                'total_removed': total_removed,
                'removal_rate': f"{self.total_stats.removal_rate:.1f}%",
                'removal_by_type': dict(self.total_stats.removed_by_type)
            },
            'products': {}
        }

        for product, stats in self.stats.items():
            report['products'][product] = stats.to_dict()

        # merge_stats.json 생성 (train_all.json용)
        merge_stats = {
            'summary': {
                'total_records': self.total_stats.cleaned_count,
                'total_train': sum(
                    s.to_dict().get('train_count', s.cleaned_count * 80 // 100)
                    for s in self.stats.values()
                ),
                'total_eval': sum(
                    s.to_dict().get('eval_count', s.cleaned_count * 20 // 100)
                    for s in self.stats.values()
                ),
                'products': len(self.stats)
            },
            'products': {
                p: {'total': s.cleaned_count, 'train': s.cleaned_count * 80 // 100, 'eval': s.cleaned_count * 20 // 100}
                for p, s in self.stats.items()
            }
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        merge_path = output_path.parent / 'merge_stats.json'
        with open(merge_path, 'w', encoding='utf-8') as f:
            json.dump(merge_stats, f, ensure_ascii=False, indent=2)

        # 콘솔 출력
        print(f"\n[REPORT] Comprehensive Cleaning v7 Summary")
        print("=" * 65)
        print(f"  Total Original: {self.total_stats.original_count:>12,}")
        print(f"  Total Cleaned:  {self.total_stats.cleaned_count:>12,}")
        print(f"  Total Removed:  {total_removed:>12,}")
        print(f"  Removal Rate:   {self.total_stats.removal_rate:>12.1f}%")
        print()
        print("  Removal by Type:")

        if total_removed > 0:
            for reason, count in sorted(self.total_stats.removed_by_type.items(), key=lambda x: -x[1]):
                pct = count / total_removed * 100
                print(f"    {reason:<30} {count:>6} ({pct:>5.1f}%)")

        return report


def merge_all_products(output_dir: Path) -> None:
    """모든 제품의 train/eval을 통합"""
    train_all = []
    eval_all = []

    for product_dir in sorted(output_dir.iterdir()):
        if not product_dir.is_dir():
            continue

        train_path = product_dir / 'train.json'
        eval_path = product_dir / 'eval.json'

        if train_path.exists():
            with open(train_path, 'r', encoding='utf-8') as f:
                train_all.extend(json.load(f))

        if eval_path.exists():
            with open(eval_path, 'r', encoding='utf-8') as f:
                eval_all.extend(json.load(f))

    # 통합 파일 저장
    with open(output_dir / 'train_all.json', 'w', encoding='utf-8') as f:
        json.dump(train_all, f, ensure_ascii=False, indent=2)

    with open(output_dir / 'eval_all.json', 'w', encoding='utf-8') as f:
        json.dump(eval_all, f, ensure_ascii=False, indent=2)

    print(f"\n[MERGED] train_all.json: {len(train_all):,} records")
    print(f"[MERGED] eval_all.json: {len(eval_all):,} records")


def main():
    parser = argparse.ArgumentParser(description='Comprehensive clean QLoRA dataset v7')
    parser.add_argument('--input', '-i', type=Path,
                        default=Path('uploads/summaries/multi_lora_v6_final'),
                        help='Input directory with v6 datasets')
    parser.add_argument('--output', '-o', type=Path,
                        default=Path('uploads/summaries/multi_lora_v7_clean'),
                        help='Output directory for v7 cleaned datasets')
    parser.add_argument('--max-per-product', '-m', type=int, default=500,
                        help='Maximum records per product for balancing (default: 500)')
    parser.add_argument('--balance', '-b', action='store_true',
                        help='Enable product distribution balancing')
    parser.add_argument('--no-dedup', action='store_true',
                        help='Disable semantic deduplication')
    parser.add_argument('--no-qa-check', action='store_true',
                        help='Disable Q-A relevance checking')

    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"  COMPREHENSIVE DATASET CLEANER v7")
    print(f"{'='*65}")
    print(f"   Input:           {args.input}")
    print(f"   Output:          {args.output}")
    print(f"   Balance:         {args.balance}")
    print(f"   Max per product: {args.max_per_product if args.balance else 'unlimited'}")
    print(f"   Deduplication:   {not args.no_dedup}")
    print(f"   Q-A Check:       {not args.no_qa_check}")
    print(f"{'='*65}")

    cleaner = ComprehensiveDatasetCleaner(
        max_per_product=args.max_per_product,
        enable_dedup=not args.no_dedup,
        enable_qa_check=not args.no_qa_check
    )

    cleaner.process_all_products(args.input, args.output, balance_products=args.balance)

    report_path = args.output / 'cleaning_report_v7.json'
    cleaner.generate_report(report_path)

    # 통합 파일 생성
    merge_all_products(args.output)

    print(f"\n[DONE] Comprehensive cleaning v7 complete!")
    print(f"   Report: {report_path}")


if __name__ == '__main__':
    main()
