#!/usr/bin/env python3
"""
Create v8 Final Dataset - PDCA Iteration 2
Addresses critical gaps G9 (NDB Q-A mismatch) and G10 (ofasm diversity)

Key changes:
1. Remove openframe_ndb_v2 entirely (unusable Q-A pairs)
2. Filter ofasm_v2 to keep only valid Q-A pairs
3. Apply stricter Q-A relevance filtering
4. Regenerate train_all.json and eval_all.json
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Set
import logging
import shutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Known bad answer patterns (Q-A mismatch indicators)
BAD_ANSWER_PATTERNS = [
    # NDB boilerplate
    r'STURNG RANGE',
    r'TEARNG RANGE',
    r'以下は、.*RANGEにデータを作成する',
    # Generic placeholder
    r'^以下は、.*の例です。$',
    # Truncated answers (answer starts with continuation)
    r'^在するUninstall',
    r'^照してください',
    r'^ことをお勧めします',
]

# Known bad Q-A patterns (question doesn't match answer topic)
QA_MISMATCH_PATTERNS = [
    # Question about concept X, answer about unrelated Y
    (r'階層型データベース', r'RANGE.*データを作成'),
    (r'ネットワークデータベース', r'RANGE.*データを作成'),
    (r'トラブルシューティング', r'RANGE.*データを作成'),
    (r'機能について', r'RANGE.*データを作成'),
    (r'設定方法', r'RANGE.*データを作成'),
]

# Products to completely remove (unusable data)
PRODUCTS_TO_REMOVE = [
    'openframe_ndb_v2',  # Critical Q-A mismatch
    'ofasm_v2',          # Insufficient quality data, mostly duplicates and Korean labels
]

# Products requiring strict filtering
PRODUCTS_STRICT_FILTER = [
    'ofasm_v2',  # Needs Q-A relevance check
]


class FinalDatasetCreator:
    """Create v8 final dataset with strict quality filters"""

    def __init__(self, input_dir: Path, output_dir: Path):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.stats = {
            'products_processed': 0,
            'products_removed': 0,
            'records_input': 0,
            'records_output': 0,
            'records_filtered': defaultdict(int),
        }

    def extract_qa(self, text: str) -> Tuple[str, str]:
        """Extract question and answer from ChatML format"""
        question = ""
        answer = ""

        user_match = re.search(r'<\|im_start\|>user\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if user_match:
            question = user_match.group(1).strip()

        assistant_match = re.search(r'<\|im_start\|>assistant\n(.*?)<\|im_end\|>', text, re.DOTALL)
        if assistant_match:
            answer = assistant_match.group(1).strip()

        return question, answer

    def is_bad_answer(self, answer: str) -> bool:
        """Check if answer matches known bad patterns"""
        for pattern in BAD_ANSWER_PATTERNS:
            if re.search(pattern, answer, re.IGNORECASE):
                return True
        return False

    def is_qa_mismatch(self, question: str, answer: str) -> bool:
        """Check if Q-A pair has topic mismatch"""
        for q_pattern, a_pattern in QA_MISMATCH_PATTERNS:
            if re.search(q_pattern, question, re.IGNORECASE) and re.search(a_pattern, answer, re.IGNORECASE):
                return True
        return False

    def has_language_mismatch(self, question: str, answer: str) -> bool:
        """Check for language inconsistency (Japanese question, Korean answer)"""
        # Japanese hiragana/katakana
        jp_pattern = re.compile(r'[\u3040-\u309f\u30a0-\u30ff]')
        # Korean hangul
        ko_pattern = re.compile(r'[\uac00-\ud7a3]')

        q_has_jp = bool(jp_pattern.search(question))
        a_has_ko = bool(ko_pattern.search(answer))

        # If question is in Japanese but answer is primarily Korean
        if q_has_jp:
            jp_count = len(jp_pattern.findall(answer))
            ko_count = len(ko_pattern.findall(answer))
            # More than 50% Korean in answer is problematic
            if ko_count > 0 and ko_count > jp_count * 2:
                return True

        return False

    def filter_records(self, records: List[dict], product: str) -> List[dict]:
        """Filter records based on quality criteria"""
        filtered = []

        for record in records:
            text = record.get('text', '')
            question, answer = self.extract_qa(text)

            # Check for bad answer patterns
            if self.is_bad_answer(answer):
                self.stats['records_filtered']['bad_answer'] += 1
                continue

            # Check for Q-A mismatch
            if self.is_qa_mismatch(question, answer):
                self.stats['records_filtered']['qa_mismatch'] += 1
                continue

            # Strict filtering for specific products
            if product in PRODUCTS_STRICT_FILTER:
                # Check language mismatch
                if self.has_language_mismatch(question, answer):
                    self.stats['records_filtered']['language_mismatch'] += 1
                    continue

                # Check answer length (too short = likely truncated)
                if len(answer) < 50:
                    self.stats['records_filtered']['too_short'] += 1
                    continue

            filtered.append(record)

        return filtered

    def process_product(self, product_dir: Path) -> Tuple[List[dict], List[dict]]:
        """Process a single product directory"""
        product = product_dir.name

        # Skip products to remove
        if product in PRODUCTS_TO_REMOVE:
            logger.info(f"  [SKIP] {product} - marked for removal")
            self.stats['products_removed'] += 1
            return [], []

        train_path = product_dir / 'train.json'
        eval_path = product_dir / 'eval.json'

        train_data = []
        eval_data = []

        if train_path.exists():
            with open(train_path, 'r', encoding='utf-8') as f:
                train_data = json.load(f)
                self.stats['records_input'] += len(train_data)

        if eval_path.exists():
            with open(eval_path, 'r', encoding='utf-8') as f:
                eval_data = json.load(f)
                self.stats['records_input'] += len(eval_data)

        # Apply filtering
        filtered_train = self.filter_records(train_data, product)
        filtered_eval = self.filter_records(eval_data, product)

        logger.info(f"  {product}: train {len(train_data)}→{len(filtered_train)}, eval {len(eval_data)}→{len(filtered_eval)}")

        return filtered_train, filtered_eval

    def create_dataset(self):
        """Create the v8 final dataset"""
        logger.info(f"\n{'='*60}")
        logger.info(f"Creating v8 Final Dataset")
        logger.info(f"Input: {self.input_dir}")
        logger.info(f"Output: {self.output_dir}")
        logger.info(f"{'='*60}\n")

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        train_all = []
        eval_all = []
        product_stats = {}

        # Process each product
        for product_dir in sorted(self.input_dir.iterdir()):
            if not product_dir.is_dir():
                continue
            if product_dir.name.endswith('.json'):
                continue

            self.stats['products_processed'] += 1
            train, eval_data = self.process_product(product_dir)

            if train or eval_data:
                # Save product-level files
                product_output = self.output_dir / product_dir.name
                product_output.mkdir(exist_ok=True)

                with open(product_output / 'train.json', 'w', encoding='utf-8') as f:
                    json.dump(train, f, ensure_ascii=False, indent=2)

                with open(product_output / 'eval.json', 'w', encoding='utf-8') as f:
                    json.dump(eval_data, f, ensure_ascii=False, indent=2)

                # Track stats
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

        self.stats['records_output'] = len(train_all) + len(eval_all)

        # Generate report
        report = {
            'summary': {
                'products_processed': self.stats['products_processed'],
                'products_removed': self.stats['products_removed'],
                'products_kept': self.stats['products_processed'] - self.stats['products_removed'],
                'records_input': self.stats['records_input'],
                'records_output': self.stats['records_output'],
                'records_filtered': sum(self.stats['records_filtered'].values()),
                'filter_breakdown': dict(self.stats['records_filtered']),
                'train_total': len(train_all),
                'eval_total': len(eval_all),
            },
            'products': product_stats,
            'removed_products': PRODUCTS_TO_REMOVE,
        }

        with open(self.output_dir / 'v8_creation_report.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Print summary
        logger.info(f"\n{'='*60}")
        logger.info(f"v8 Final Dataset Created")
        logger.info(f"{'='*60}")
        logger.info(f"Products processed: {self.stats['products_processed']}")
        logger.info(f"Products removed: {self.stats['products_removed']}")
        logger.info(f"Records input: {self.stats['records_input']:,}")
        logger.info(f"Records output: {self.stats['records_output']:,}")
        logger.info(f"Records filtered: {sum(self.stats['records_filtered'].values()):,}")
        logger.info(f"  - bad_answer: {self.stats['records_filtered']['bad_answer']}")
        logger.info(f"  - qa_mismatch: {self.stats['records_filtered']['qa_mismatch']}")
        logger.info(f"  - language_mismatch: {self.stats['records_filtered']['language_mismatch']}")
        logger.info(f"  - too_short: {self.stats['records_filtered']['too_short']}")
        logger.info(f"\nTrain: {len(train_all):,} | Eval: {len(eval_all):,}")
        logger.info(f"Output: {self.output_dir}")

        return report


def main():
    # Use v7_augmented_v2 as input (latest dataset)
    input_dir = Path('uploads/summaries/multi_lora_v7_augmented_v2')
    output_dir = Path('uploads/summaries/multi_lora_v8_final')

    creator = FinalDatasetCreator(input_dir, output_dir)
    report = creator.create_dataset()

    print(f"\n[DONE] v8 Final Dataset created at: {output_dir}")
    print(f"       Report: {output_dir / 'v8_creation_report.json'}")


if __name__ == '__main__':
    main()
