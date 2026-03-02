#!/usr/bin/env python3
"""
Semantic Clean Dataset - v4 -> v5 의미적 품질 개선
품질 리뷰에서 발견된 P0/P1 이슈 해결

Issues addressed:
- P0: 최소 답변 길이 미충족 (< 25자)
- P0: 잘린/불완전한 질문 패턴
- P0: 페이지 번호만 있는 답변
- P0: 함수명만 있는 답변 (설명 없음)
- P1: Q&A 정합성 검증 (질문 vs 답변 불일치)
"""

import json
import re
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import logging

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


class SemanticDatasetCleaner:
    """데이터셋 의미적 품질 클리너"""

    # 최소 답변 길이 (문자 수)
    MIN_ANSWER_LENGTH = 25

    # 잘린 질문 패턴 (의미 없는 질문)
    TRUNCATED_QUESTION_PATTERNS = [
        # 매우 짧은 맥락 + 질문 접미사 (일본어)
        r'^.{1,20}のやり方は？$',
        r'^.{1,20}とは何ですか？$',
        r'^.{1,18}について説明してください。$',
        r'^.{1,18}の概念を教えてください。$',
        r'^.{1,20}のステップを説明してください。$',
        r'^.{1,20}の手順を教えてください。$',

        # 문장 중간이 질문에 포함된 경우 (PDF 파싱 오류)
        r'^.+です。.{1,30}(について|とは|のやり方|の概念|のステップ|の手順)',
        r'^.+ます。.{1,30}(について|とは|のやり方|の概念|のステップ|の手順)',
        r'^.+した。.{1,30}(について|とは|のやり方|の概念|のステップ|の手順)',
        r'^.+します。.{1,30}(について|とは|のやり方|の概念|のステップ|の手順)',

        # 잘린 단어로 시작하는 질문
        r'^する.{1,30}の(やり方|手順|ステップ|概念)',
        r'^される.{1,30}の(やり方|手順|ステップ|概念)',
        r'^されて.{1,30}の(やり方|手順|ステップ|概念)',
        r'^して.{1,30}の(やり方|手順|ステップ|概念)',
        r'^中に.{1,25}の(やり方|手順|ステップ)',
        r'^後に.{1,25}の(やり方|手順|ステップ)',

        # 문장 끝에서 잘린 질문 (... の + 질문패턴)
        r'^.+[。、」]の(やり方|手順|ステップ|概念)',

        # 영어 잘린 패턴
        r'^What are the steps for .{1,30}\?$',
        r'^What is .{1,15}\?$',
        r'^How do I (use|perform) .{1,25}\?$',
        r'^Describe the concept of .{1,15}\.$',
        r'^How do I .{1,10} #\?$',  # "How do I perform ation #?"
    ]

    # 무의미한 답변 패턴
    MEANINGLESS_ANSWER_PATTERNS = [
        # 페이지/장 번호만 있는 답변
        r'^第\d+章[^\n]{0,40}$',
        r'^Chapter\s+\d+[^\n]{0,30}$',
        r'^Appendix\s+[A-Z][^\n]{0,30}$',
        r'^付録\s*[A-Z]?[^\n]{0,30}$',
        r'^\d+\s*$',  # 숫자만

        # 함수명/변수명만 있는 답변 (설명 없음)
        r'^[a-z_][a-z0-9_]*\(\)$',
        r'^,?\s*[a-z_][a-z0-9_]*\(\)$',
        r'^[a-z_][a-z0-9_]*\(\),\s*[a-z_][a-z0-9_]*\(\)$',
        r'^[a-z_][a-z0-9_]*\(\),\s*[a-z_][a-z0-9_]*\(\),\s*[a-z_][a-z0-9_]*\(\)$',

        # 코드 조각만 있는 답변 (설명 없음)
        r'^(if|for|while|char|int|void|return)\s*[\(\{][^가-힣ぁ-んァ-ンa-zA-Z]*$',
        r'^[\w\s\*]+\s*=\s*[^;]{0,30};?$',

        # 단순 참조만 있는 답변
        r'^.{0,15}を参照(して)?ください。?$',
        r'^See\s+.{1,30}\.$',
        r'^詳細は.{0,20}を参照$',

        # 구분선/기호만 있는 답변
        r'^[\-=\*_\.]+$',
        r'^●?[a-z_]+$',

        # 단일 단어/표현만
        r'^す。$',
        r'^です。$',
        r'^ます。$',
        r'^[ぁ-ん]{1,3}$',
    ]

    # Q&A 키워드 매핑 (질문 키워드 -> 답변에 있어야 할 키워드 중 하나)
    QA_KEYWORD_REQUIREMENTS = {
        # 일본어
        '引数と戻り値': ['引数', 'param', 'パラメータ', '戻り値', 'return', '返す'],
        '引数': ['引数', 'param', 'パラメータ', 'argument', '入力'],
        '戻り値': ['戻り値', 'return', '返す', '返り値', 'result', '出力'],
        '使用方法': ['使用', '方法', 'use', 'how', '例', 'example', '手順'],
        '使用例': ['例', 'example', 'サンプル', 'sample', '以下'],
        'APIの使用': ['API', '使用', '呼び出', 'call', '方法'],

        # 영어
        'parameters and return': ['param', 'argument', 'return', 'result', 'input', 'output'],
        'return value': ['return', 'result', 'output', '戻り値'],
        'example': ['example', '例', 'sample', 'following', '以下'],
        'how to use': ['use', 'usage', 'call', 'method', '使用', '方法'],
    }

    def __init__(self):
        self.stats: Dict[str, CleaningStats] = {}
        self.total_stats = CleaningStats()

    def extract_qa_from_text(self, text: str) -> Tuple[str, str, str]:
        """ChatML 포맷에서 system, question, answer 추출"""
        system = ""
        question = ""
        answer = ""

        # System prompt 추출
        system_match = re.search(r'<\|im_start\|>system\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if system_match:
            system = system_match.group(1).strip()

        # User question 추출
        user_match = re.search(r'<\|im_start\|>user\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if user_match:
            question = user_match.group(1).strip()

        # Assistant answer 추출
        assistant_match = re.search(r'<\|im_start\|>assistant\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if assistant_match:
            answer = assistant_match.group(1).strip()
            # 메타데이터 제거 (순수 답변만 추출)
            answer = re.sub(r'\n\n\*\*製品/Product\*\*:.*$', '', answer, flags=re.DOTALL)
            answer = re.sub(r'\n\n\*\*出典/Source\*\*:.*$', '', answer, flags=re.DOTALL)

        return system, question, answer

    def is_truncated_question(self, question: str) -> bool:
        """잘린 질문인지 확인"""
        # 1. 정규식 패턴 매칭
        for pattern in self.TRUNCATED_QUESTION_PATTERNS:
            if re.match(pattern, question, re.IGNORECASE):
                return True

        # 2. 조사/접속사로 시작하는 질문 (문장 중간에서 잘림)
        truncated_starters = [
            'する', 'される', 'されて', 'して', 'した',
            'ます', 'です', 'した。', 'ます。', 'です。',
            '中に', '後に', '時に', '際に',
            'および', 'および', 'また', 'そして',
            'ために', 'として', 'について', 'による',
        ]
        for starter in truncated_starters:
            if question.startswith(starter):
                return True

        # 3. 영어 잘린 패턴 추가 체크
        if question.startswith('ation ') or question.startswith('tion '):
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

    def check_qa_coherence(self, question: str, answer: str) -> bool:
        """Q&A 정합성 검증"""
        question_lower = question.lower()
        answer_lower = answer.lower()

        # 특정 키워드가 질문에 있으면 답변에도 관련 내용이 있어야 함
        for q_keywords, a_keywords in self.QA_KEYWORD_REQUIREMENTS.items():
            if q_keywords in question or q_keywords.lower() in question_lower:
                # 답변에 관련 키워드가 하나도 없으면 불일치
                has_match = any(
                    ak in answer or ak.lower() in answer_lower
                    for ak in a_keywords
                )
                if not has_match:
                    # 답변이 충분히 길면 OK (상세 설명으로 간주)
                    if len(answer) > 150:
                        return True
                    return False

        return True

    def classify_removal_reason(self, question: str, answer: str) -> str:
        """제거 사유 분류"""
        answer_clean = answer.strip()

        # 1. 답변 길이 체크
        if len(answer_clean) < self.MIN_ANSWER_LENGTH:
            return "too_short_answer"

        # 2. 잘린 질문 체크
        if self.is_truncated_question(question):
            return "truncated_question"

        # 3. 무의미한 답변 체크
        if self.is_meaningless_answer(answer):
            return "meaningless_answer"

        # 4. Q&A 정합성 체크
        if not self.check_qa_coherence(question, answer):
            return "qa_mismatch"

        return ""

    def should_remove(self, text: str) -> Tuple[bool, str]:
        """레코드 제거 여부 및 사유 반환"""
        system, question, answer = self.extract_qa_from_text(text)

        if not question or not answer:
            return True, "missing_qa"

        reason = self.classify_removal_reason(question, answer)
        return bool(reason), reason

    def clean_dataset(self, input_path: Path, output_path: Path) -> CleaningStats:
        """데이터셋 클리닝"""
        stats = CleaningStats()

        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        stats.original_count = len(data)
        cleaned_data = []

        for item in data:
            text = item.get('text', '')
            should_remove, reason = self.should_remove(text)

            if should_remove:
                stats.removed_by_type[reason] += 1
            else:
                cleaned_data.append(item)

        stats.cleaned_count = len(cleaned_data)

        # 출력 디렉토리 생성
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 클린 데이터 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=2)

        return stats

    def process_all_products(self, input_dir: Path, output_dir: Path) -> None:
        """모든 제품 데이터셋 처리"""
        products = [d.name for d in input_dir.iterdir() if d.is_dir()]

        print(f"\n[INFO] Semantic Cleaning: {len(products)} products")
        print("=" * 75)
        print(f"{'Product':<32} | {'Original':>7} | {'Cleaned':>7} | {'Removed':>7} | {'Rate':>6}")
        print("-" * 75)

        for product in sorted(products):
            product_input = input_dir / product
            product_output = output_dir / product

            # train.json 처리
            train_input = product_input / 'train.json'
            train_output = product_output / 'train.json'

            if not train_input.exists():
                continue

            train_stats = self.clean_dataset(train_input, train_output)

            # eval.json 처리
            eval_input = product_input / 'eval.json'
            eval_output = product_output / 'eval.json'

            eval_stats = CleaningStats()
            if eval_input.exists():
                eval_stats = self.clean_dataset(eval_input, eval_output)

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
            print(f"{product:<32} | {combined_stats.original_count:>7} | {combined_stats.cleaned_count:>7} | {removed:>7} | {rate:>5.1f}%")

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

        print("=" * 75)

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

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # 콘솔 출력
        print(f"\n[REPORT] Semantic Cleaning Summary")
        print("=" * 60)
        print(f"  Total Original: {self.total_stats.original_count:>10,}")
        print(f"  Total Cleaned:  {self.total_stats.cleaned_count:>10,}")
        print(f"  Total Removed:  {total_removed:>10,}")
        print(f"  Removal Rate:   {self.total_stats.removal_rate:>10.1f}%")
        print()
        print("  Removal by Type:")

        if total_removed > 0:
            for reason, count in sorted(self.total_stats.removed_by_type.items(), key=lambda x: -x[1]):
                pct = count / total_removed * 100
                print(f"    {reason:<25} {count:>6} ({pct:>5.1f}%)")

        return report


def main():
    parser = argparse.ArgumentParser(description='Semantic clean QLoRA dataset (v4 -> v5)')
    parser.add_argument('--input', '-i', type=Path,
                        default=Path('uploads/summaries/multi_lora_v4_cleaned'),
                        help='Input directory with v4 cleaned datasets')
    parser.add_argument('--output', '-o', type=Path,
                        default=Path('uploads/summaries/multi_lora_v5_semantic'),
                        help='Output directory for semantic cleaned datasets')

    args = parser.parse_args()

    print(f"\n[START] Semantic Dataset Cleaner")
    print(f"   Input:  {args.input}")
    print(f"   Output: {args.output}")

    cleaner = SemanticDatasetCleaner()
    cleaner.process_all_products(args.input, args.output)

    report_path = args.output / 'semantic_cleaning_report.json'
    cleaner.generate_report(report_path)

    print(f"\n[DONE] Semantic cleaning complete!")
    print(f"   Report: {report_path}")


if __name__ == '__main__':
    main()
