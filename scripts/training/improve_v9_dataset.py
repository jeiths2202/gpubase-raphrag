#!/usr/bin/env python3
"""
Improve v9 Dataset - Quality Enhancement
Addresses quality review recommendations:

P1: 짧은 답변 보완 - Enhance short answers (under 50 chars)
P2: 문맥 의존적 질문 수정 - Fix context-dependent questions
P3: 데이터 균형화 - Balance data for small products

Input: multi_lora_v8_final
Output: multi_lora_v9_improved
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Minimum answer length (characters)
MIN_ANSWER_LENGTH = 50

# Patterns for context-dependent questions (need fixing)
CONTEXT_DEPENDENT_PATTERNS = [
    # Pattern: starts with continuation markers
    (r'^(の|を|は|に|が|で|と|から|まで|より)(概念|説明|方法|手順)', 'prefix_particle'),
    # Pattern: starts with "...について" without subject
    (r'^について(説明|教えて)', 'about_without_subject'),
    # Pattern: truncated start with ellipsis-like content
    (r'^(。|、|し|て|た|る)(ください|います|ます)', 'truncated_start'),
    # Pattern: starts with verb continuation
    (r'^(いる|ある|する|できる)(と|場合|とき)', 'verb_continuation'),
]

# Question type patterns for reconstruction
QUESTION_TYPES = {
    'explain': (r'(説明|について|とは|教えて|概念)', '{}について説明してください。'),
    'howto': (r'(方法|手順|やり方|使い方)', '{}の方法を教えてください。'),
    'what': (r'(とは何|何ですか)', '{}とは何ですか？'),
    'concept': (r'(概念を)', '{}の概念を教えてください。'),
}

# Small products that need augmentation (threshold: < 50 records)
SMALL_PRODUCT_THRESHOLD = 50

# System prompts by product
SYSTEM_PROMPTS = {
    'jeus': {
        'ko': '당신은 JEUS 전문 기술 어시스턴트입니다. JEUS에 관한 질문에 정확하게 답변해주세요.',
        'ja': 'あなたはJEUS専門のテクニカルアシスタントです。JEUSに関する質問に正確に回答してください。',
        'en': 'You are a JEUS technical expert assistant. Answer questions about JEUS accurately.'
    },
    'tibero': {
        'ko': '당신은 Tibero 전문 기술 어시스턴트입니다. Tibero에 관한 질문에 정확하게 답변해주세요.',
        'ja': 'あなたはTibero専門のテクニカルアシスタントです。Tiberoに関する質問に正確に回答してください。',
        'en': 'You are a Tibero technical expert assistant. Answer questions about Tibero accurately.'
    },
    'openframe': {
        'ko': '당신은 OpenFrame 전문 기술 어시스턴트입니다. OpenFrame에 관한 질문에 정확하게 답변해주세요.',
        'ja': 'あなたはOpenFrame専門のテクニカルアシスタントです。OpenFrameに関する質問に正確に回答してください。',
        'en': 'You are an OpenFrame technical expert assistant. Answer questions about OpenFrame accurately.'
    },
}


class DatasetImprover:
    """Improve dataset quality based on review recommendations"""

    def __init__(self, input_dir: Path, output_dir: Path):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.stats = {
            'total_processed': 0,
            'short_answers_found': 0,
            'short_answers_removed': 0,
            'context_questions_found': 0,
            'context_questions_fixed': 0,
            'context_questions_removed': 0,
            'products_augmented': 0,
            'records_augmented': 0,
        }
        self.improvement_log = []

    def extract_qa_parts(self, text: str) -> Tuple[str, str, str]:
        """Extract system prompt, question, and answer from ChatML format"""
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

        return system, question, answer

    def format_chatml(self, system: str, question: str, answer: str) -> str:
        """Format as ChatML"""
        return f"""<|im_start|>system
{system}<|im_end|>
<|im_start|>user
{question}<|im_end|>
<|im_start|>assistant
{answer}<|im_end|>"""

    def is_short_answer(self, answer: str) -> bool:
        """Check if answer is too short"""
        # Remove metadata lines from count
        clean_answer = re.sub(r'\*\*製品/Product\*\*:.*', '', answer)
        clean_answer = re.sub(r'\*\*出典/Source\*\*:.*', '', clean_answer)
        clean_answer = clean_answer.strip()
        return len(clean_answer) < MIN_ANSWER_LENGTH

    def is_context_dependent_question(self, question: str) -> Tuple[bool, str]:
        """Check if question is context-dependent (incomplete)"""
        for pattern, pattern_type in CONTEXT_DEPENDENT_PATTERNS:
            if re.match(pattern, question):
                return True, pattern_type
        return False, ""

    def extract_subject_from_answer(self, answer: str) -> Optional[str]:
        """Try to extract subject/topic from answer text"""
        # Look for patterns like "XXXは..." or "XXXとは..."
        patterns = [
            r'^([A-Za-z0-9_\-]+)は、',
            r'^([A-Za-z0-9_\-]+)とは',
            r'^「([^」]+)」は',
            r'^●\s*([^\n]+)',
            r'^([A-Z][A-Za-z0-9_]+)\s+(?:は|を|が)',
        ]

        for pattern in patterns:
            match = re.search(pattern, answer)
            if match:
                subject = match.group(1).strip()
                # Filter out generic words
                if len(subject) > 2 and subject not in ['以下', '本節', '上記', '詳細']:
                    return subject
        return None

    def fix_context_dependent_question(self, question: str, answer: str) -> Optional[str]:
        """Attempt to fix context-dependent question using answer context"""
        # Try to extract subject from answer
        subject = self.extract_subject_from_answer(answer)

        if not subject:
            return None

        # Determine question type
        for qtype, (pattern, template) in QUESTION_TYPES.items():
            if re.search(pattern, question):
                return template.format(subject)

        # Default: explain type
        return f'{subject}について説明してください。'

    def improve_record(self, record: dict, product: str) -> Optional[dict]:
        """Improve a single record"""
        text = record.get('text', '')
        system, question, answer = self.extract_qa_parts(text)

        self.stats['total_processed'] += 1
        improved = False

        # P1: Check for short answers
        if self.is_short_answer(answer):
            self.stats['short_answers_found'] += 1
            # Remove short answers - they don't provide value
            self.stats['short_answers_removed'] += 1
            self.improvement_log.append({
                'type': 'removed_short_answer',
                'product': product,
                'question': question[:50],
                'answer_length': len(answer)
            })
            return None

        # P2: Check for context-dependent questions
        is_context_dep, pattern_type = self.is_context_dependent_question(question)
        if is_context_dep:
            self.stats['context_questions_found'] += 1

            # Try to fix the question
            fixed_question = self.fix_context_dependent_question(question, answer)

            if fixed_question:
                self.stats['context_questions_fixed'] += 1
                question = fixed_question
                improved = True
                self.improvement_log.append({
                    'type': 'fixed_context_question',
                    'product': product,
                    'original': question[:50],
                    'fixed': fixed_question[:50],
                    'pattern': pattern_type
                })
            else:
                # Cannot fix - remove the record
                self.stats['context_questions_removed'] += 1
                self.improvement_log.append({
                    'type': 'removed_context_question',
                    'product': product,
                    'question': question[:50],
                    'pattern': pattern_type
                })
                return None

        # Return improved or original record
        if improved:
            return {'text': self.format_chatml(system, question, answer)}
        return record

    def generate_augmented_qa(self, existing_records: List[dict], product: str, target_count: int) -> List[dict]:
        """Generate augmented Q&A pairs for small products"""
        augmented = []

        # For now, we'll use paraphrase-style augmentation
        # This is a placeholder - in production, use LLM for better augmentation

        variation_templates = [
            ('{question}', '{answer}'),  # Original
            ('「{subject}」の詳細を教えてください。', '{answer}'),
            ('{subject}について詳しく説明してください。', '{answer}'),
        ]

        for record in existing_records:
            if len(augmented) >= target_count:
                break

            text = record.get('text', '')
            system, question, answer = self.extract_qa_parts(text)

            # Extract subject for variations
            subject = self.extract_subject_from_answer(answer)
            if not subject:
                continue

            # Generate variations (skip first as it's original)
            for template_q, template_a in variation_templates[1:]:
                if len(augmented) >= target_count:
                    break

                new_question = template_q.format(question=question, subject=subject)
                new_answer = template_a.format(answer=answer)

                augmented.append({
                    'text': self.format_chatml(system, new_question, new_answer)
                })
                self.stats['records_augmented'] += 1

        return augmented

    def process_product(self, product_dir: Path) -> Tuple[List[dict], List[dict]]:
        """Process a single product directory"""
        product = product_dir.name
        logger.info(f"  Processing {product}...")

        train_path = product_dir / 'train.json'
        eval_path = product_dir / 'eval.json'

        train_data = []
        eval_data = []

        if train_path.exists():
            with open(train_path, 'r', encoding='utf-8') as f:
                train_data = json.load(f)

        if eval_path.exists():
            with open(eval_path, 'r', encoding='utf-8') as f:
                eval_data = json.load(f)

        original_count = len(train_data) + len(eval_data)

        # Improve records
        improved_train = []
        for record in train_data:
            result = self.improve_record(record, product)
            if result:
                improved_train.append(result)

        improved_eval = []
        for record in eval_data:
            result = self.improve_record(record, product)
            if result:
                improved_eval.append(result)

        # P3: Augment small products
        total_improved = len(improved_train) + len(improved_eval)
        if total_improved < SMALL_PRODUCT_THRESHOLD and total_improved > 0:
            needed = SMALL_PRODUCT_THRESHOLD - total_improved
            logger.info(f"    Augmenting {product}: {total_improved} -> {SMALL_PRODUCT_THRESHOLD} (need {needed})")

            augmented = self.generate_augmented_qa(
                improved_train + improved_eval,
                product,
                min(needed, total_improved)  # Don't augment more than original
            )
            improved_train.extend(augmented)
            self.stats['products_augmented'] += 1

        improved_count = len(improved_train) + len(improved_eval)
        logger.info(f"    {product}: {original_count} -> {improved_count}")

        return improved_train, improved_eval

    def process_all(self):
        """Process all products"""
        logger.info(f"\n{'='*60}")
        logger.info(f"Dataset Quality Improvement (v8 -> v9)")
        logger.info(f"Input: {self.input_dir}")
        logger.info(f"Output: {self.output_dir}")
        logger.info(f"{'='*60}\n")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        train_all = []
        eval_all = []
        product_stats = {}

        for product_dir in sorted(self.input_dir.iterdir()):
            if not product_dir.is_dir():
                continue

            train, eval_data = self.process_product(product_dir)

            if train or eval_data:
                # Save product files
                product_output = self.output_dir / product_dir.name
                product_output.mkdir(exist_ok=True)

                with open(product_output / 'train.json', 'w', encoding='utf-8') as f:
                    json.dump(train, f, ensure_ascii=False, indent=2)

                with open(product_output / 'eval.json', 'w', encoding='utf-8') as f:
                    json.dump(eval_data, f, ensure_ascii=False, indent=2)

                product_stats[product_dir.name] = {
                    'train': len(train),
                    'eval': len(eval_data),
                    'total': len(train) + len(eval_data)
                }

                train_all.extend(train)
                eval_all.extend(eval_data)

        # Save combined files
        with open(self.output_dir / 'train_all.json', 'w', encoding='utf-8') as f:
            json.dump(train_all, f, ensure_ascii=False, indent=2)

        with open(self.output_dir / 'eval_all.json', 'w', encoding='utf-8') as f:
            json.dump(eval_all, f, ensure_ascii=False, indent=2)

        # Generate report
        report = {
            'summary': {
                'total_processed': self.stats['total_processed'],
                'final_train': len(train_all),
                'final_eval': len(eval_all),
                'final_total': len(train_all) + len(eval_all),
                'improvements': {
                    'short_answers_found': self.stats['short_answers_found'],
                    'short_answers_removed': self.stats['short_answers_removed'],
                    'context_questions_found': self.stats['context_questions_found'],
                    'context_questions_fixed': self.stats['context_questions_fixed'],
                    'context_questions_removed': self.stats['context_questions_removed'],
                    'products_augmented': self.stats['products_augmented'],
                    'records_augmented': self.stats['records_augmented'],
                }
            },
            'products': product_stats,
            'improvement_samples': self.improvement_log[:50]  # First 50 improvements
        }

        with open(self.output_dir / 'v9_improvement_report.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Print summary
        logger.info(f"\n{'='*60}")
        logger.info(f"v9 Dataset Improvement Complete")
        logger.info(f"{'='*60}")
        logger.info(f"Total processed: {self.stats['total_processed']:,}")
        logger.info(f"Short answers removed: {self.stats['short_answers_removed']:,}")
        logger.info(f"Context questions fixed: {self.stats['context_questions_fixed']:,}")
        logger.info(f"Context questions removed: {self.stats['context_questions_removed']:,}")
        logger.info(f"Products augmented: {self.stats['products_augmented']}")
        logger.info(f"Records augmented: {self.stats['records_augmented']:,}")
        logger.info(f"\nFinal: Train {len(train_all):,} | Eval {len(eval_all):,} | Total {len(train_all)+len(eval_all):,}")
        logger.info(f"Output: {self.output_dir}")

        return report


def main():
    input_dir = Path('uploads/summaries/multi_lora_v8_final')
    output_dir = Path('uploads/summaries/multi_lora_v9_improved')

    improver = DatasetImprover(input_dir, output_dir)
    report = improver.process_all()

    print(f"\n[DONE] v9 Improved Dataset created at: {output_dir}")
    print(f"       Report: {output_dir / 'v9_improvement_report.json'}")


if __name__ == '__main__':
    main()
