#!/usr/bin/env python3
"""
Deep Clean Dataset - Multi-LoRA v3 Training Data Quality Fix
Addresses all identified issues from DATA_QUALITY_REPORT_COMPLETE.md

Issues targeted:
1. Broken encoding (26.3%): "syste)m", "説明清めます"
2. Chinese simplified characters (20.5%): "业务" instead of "業務"
3. Excessive repetition (14.2%): Same word >10% of content
4. Incomplete sentences (7.3%): Starts mid-context

Priority 1 Products (>60% error rate):
- tmax_v2 (81.1%), tibero7_v2 (63.3%), openframe_batch_v2 (63.5%)
- protrieve_v2 (63.5%), ofpli_v2 (62.9%), prosort_v2 (61.4%), ofcobol_v2 (60.1%)
"""

import json
import re
import argparse
from pathlib import Path
from collections import Counter
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from concurrent.futures import ProcessPoolExecutor, as_completed
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class CleaningStats:
    """Statistics for cleaning process"""
    original_count: int = 0
    cleaned_count: int = 0
    removed_broken_encoding: int = 0
    removed_chinese_chars: int = 0
    removed_repetition: int = 0
    removed_incomplete: int = 0
    removed_too_short: int = 0
    removed_nonsense: int = 0
    fixed_minor_issues: int = 0

    def to_dict(self) -> dict:
        return {
            'original_count': self.original_count,
            'cleaned_count': self.cleaned_count,
            'removed_total': self.original_count - self.cleaned_count,
            'removal_rate': f"{((self.original_count - self.cleaned_count) / max(self.original_count, 1)) * 100:.1f}%",
            'removed_by_type': {
                'broken_encoding': self.removed_broken_encoding,
                'chinese_simplified': self.removed_chinese_chars,
                'excessive_repetition': self.removed_repetition,
                'incomplete_sentence': self.removed_incomplete,
                'too_short': self.removed_too_short,
                'nonsense_content': self.removed_nonsense,
            },
            'fixed_minor_issues': self.fixed_minor_issues
        }


# Chinese Simplified characters commonly found in training data (should be Japanese)
CHINESE_SIMPLIFIED_CHARS = set([
    # Common simplified chars that appear instead of Japanese
    '清', '业', '为', '关', '产', '说', '应', '实', '进', '时',
    '后', '动', '来', '现', '两', '义', '数', '类', '图', '认',
    '这', '个', '们', '对', '与', '并', '从', '发', '过', '还',
    '让', '将', '向', '于', '使', '被', '给', '着', '内', '种',
    '运', '设', '处', '变', '务', '据', '线', '节', '间', '问',
    '题', '长', '门', '开', '关', '电', '机', '单', '双', '级',
    '体', '统', '网', '络', '户', '员', '资', '库', '志', '录',
    '备', '复', '选', '择', '页', '显', '视', '窗', '标', '签',
    # Additional simplified chars
    '连', '断', '转', '输', '队', '组', '调', '试', '检', '验',
    '确', '认', '证', '码', '钥', '锁', '盘', '键', '鼠', '标',
])

# Broken encoding patterns
BROKEN_ENCODING_PATTERNS = [
    r'[�]+',                          # Replacement characters
    r'\w+\s*\)\s*\w+',                # "syste)m" pattern
    r'[a-zA-Z]{2,}\s*[）】]',          # English + Japanese closing bracket
    r'説明清め',                       # Known broken pattern
    r'[\x00-\x08\x0b\x0c\x0e-\x1f]',  # Control characters
    r'(?<=[a-z])\s+(?=[a-z]{2})',     # Broken word spacing
    r'[ァ-ン]{1}$',                    # Ends with single katakana (truncation)
    r'^[ぁ-ん]{1,2}$',                 # Only 1-2 hiragana (meaningless)
]

# Nonsense/hallucinated patterns
NONSENSE_PATTERNS = [
    r'SOFO\s*\(',                      # Non-existent acronym
    r'Single\s+Day\s+Fault',          # Hallucinated term
    r'singleton\s+method',            # Wrong context
    r'\.{5,}',                        # Excessive dots
    r'_{5,}',                         # Excessive underscores
    r'={5,}',                         # Excessive equals
    r'(\w+)\s+\1\s+\1\s+\1',          # Same word 4+ times in a row
]

# Incomplete sentence starters (Japanese)
INCOMPLETE_STARTERS = [
    r'^[でにをがはもへと]',            # Particle-only start
    r'^[ぁ-ん]で[すま]',               # "です/ます" only
    r'^構成されて',                    # "構成されて" alone
    r'^設定されて',                    # "設定されて" alone
    r'^定義されて',                    # "定義されて" alone
]


def has_chinese_simplified(text: str, threshold: int = 2) -> bool:
    """
    Check if text contains Chinese simplified characters

    Args:
        text: Text to check
        threshold: Minimum number of chars to trigger (default 2)

    Returns:
        True if simplified Chinese chars found above threshold
    """
    count = sum(1 for char in text if char in CHINESE_SIMPLIFIED_CHARS)
    return count >= threshold


def has_broken_encoding(text: str) -> bool:
    """Check for encoding errors and PDF parsing issues"""
    for pattern in BROKEN_ENCODING_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def has_excessive_repetition(text: str, threshold: float = 0.15) -> bool:
    """
    Check for excessive word repetition

    Args:
        text: Text to check
        threshold: Max ratio of most common word (default 15%)
    """
    # Split into words/tokens
    words = re.findall(r'[\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+', text)
    if len(words) < 10:
        return False

    # Count occurrences
    counter = Counter(words)
    most_common_word, most_common_count = counter.most_common(1)[0]

    # Check ratio
    ratio = most_common_count / len(words)
    return ratio > threshold


def is_incomplete_sentence(text: str) -> bool:
    """Check if text starts with incomplete sentence fragment"""
    text = text.strip()
    for pattern in INCOMPLETE_STARTERS:
        if re.match(pattern, text):
            return True
    return False


def has_nonsense_content(text: str) -> bool:
    """Check for hallucinated or nonsense content"""
    for pattern in NONSENSE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def is_too_short(text: str, min_chars: int = 50) -> bool:
    """Check if response is too short to be useful"""
    # Remove whitespace and count
    clean_text = re.sub(r'\s+', '', text)
    return len(clean_text) < min_chars


def fix_minor_issues(text: str) -> Tuple[str, bool]:
    """
    Fix minor issues that don't require removal

    Returns:
        Tuple of (fixed_text, was_fixed)
    """
    original = text

    # Fix double spaces
    text = re.sub(r'  +', ' ', text)

    # Fix Japanese punctuation spacing
    text = re.sub(r'\s+([。、）」』])', r'\1', text)
    text = re.sub(r'([（「『])\s+', r'\1', text)

    # Remove trailing incomplete markers
    text = re.sub(r'[・…]+$', '', text)

    # Fix common OCR errors
    text = text.replace('syste m', 'system')
    text = text.replace('data base', 'database')

    return text, text != original


def extract_assistant_content(item: dict) -> Optional[str]:
    """Extract assistant response from training item"""
    text = item.get('text', '')

    try:
        # Format: <|im_start|>system...<|im_end|>...<|im_start|>assistant\n{content}<|im_end|>
        if '<|im_start|>assistant' in text:
            assistant_part = text.split('<|im_start|>assistant')[-1]
            content = assistant_part.split('<|im_end|>')[0].strip()
            return content
    except Exception:
        pass

    return None


def clean_single_item(item: dict) -> Tuple[Optional[dict], str]:
    """
    Clean a single training item

    Returns:
        Tuple of (cleaned_item or None, removal_reason or 'kept')
    """
    content = extract_assistant_content(item)

    if content is None:
        return None, 'invalid_format'

    # Check for issues (order matters - most severe first)
    if has_broken_encoding(content):
        return None, 'broken_encoding'

    if has_chinese_simplified(content):
        return None, 'chinese_simplified'

    if has_nonsense_content(content):
        return None, 'nonsense_content'

    if has_excessive_repetition(content):
        return None, 'excessive_repetition'

    if is_incomplete_sentence(content):
        return None, 'incomplete_sentence'

    if is_too_short(content):
        return None, 'too_short'

    # Try to fix minor issues
    fixed_content, was_fixed = fix_minor_issues(content)

    if was_fixed:
        # Update the item with fixed content
        text = item['text']
        # Replace the assistant content
        parts = text.split('<|im_start|>assistant')
        if len(parts) == 2:
            prefix = parts[0] + '<|im_start|>assistant\n'
            suffix_parts = parts[1].split('<|im_end|>')
            if len(suffix_parts) >= 2:
                suffix = '<|im_end|>' + '<|im_end|>'.join(suffix_parts[1:])
                item = item.copy()
                item['text'] = prefix + fixed_content + suffix
                return item, 'fixed'

    return item, 'kept'


def clean_dataset(input_path: Path, output_path: Path) -> CleaningStats:
    """
    Clean a single product's training dataset

    Args:
        input_path: Path to train.json
        output_path: Path to save cleaned train.json
    """
    stats = CleaningStats()

    # Load data
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stats.original_count = len(data)
    cleaned_data = []

    for item in data:
        cleaned_item, reason = clean_single_item(item)

        if reason == 'broken_encoding':
            stats.removed_broken_encoding += 1
        elif reason == 'chinese_simplified':
            stats.removed_chinese_chars += 1
        elif reason == 'excessive_repetition':
            stats.removed_repetition += 1
        elif reason == 'incomplete_sentence':
            stats.removed_incomplete += 1
        elif reason == 'too_short':
            stats.removed_too_short += 1
        elif reason == 'nonsense_content':
            stats.removed_nonsense += 1
        elif reason == 'fixed':
            stats.fixed_minor_issues += 1
            cleaned_data.append(cleaned_item)
        elif reason == 'kept':
            cleaned_data.append(cleaned_item)

    stats.cleaned_count = len(cleaned_data)

    # Save cleaned data
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, ensure_ascii=False, indent=2)

    return stats


def process_product(args: Tuple[str, Path, Path]) -> Tuple[str, CleaningStats]:
    """Process a single product (for parallel execution)"""
    product_name, input_dir, output_dir = args

    input_path = input_dir / product_name / 'train.json'
    output_path = output_dir / product_name / 'train.json'

    if not input_path.exists():
        logger.warning(f"Skipping {product_name}: train.json not found")
        return product_name, CleaningStats()

    logger.info(f"Processing {product_name}...")
    stats = clean_dataset(input_path, output_path)

    # Copy eval.json and stats.json if they exist
    for filename in ['eval.json', 'stats.json']:
        src = input_dir / product_name / filename
        dst = output_dir / product_name / filename
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(src, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(dst, 'w', encoding='utf-8') as f:
                f.write(content)

    return product_name, stats


def main():
    parser = argparse.ArgumentParser(description='Deep clean Multi-LoRA v3 training data')
    parser.add_argument('--input', '-i', type=Path,
                        default=Path('uploads/summaries/multi_lora_v3'),
                        help='Input directory containing product folders')
    parser.add_argument('--output', '-o', type=Path,
                        default=Path('uploads/summaries/multi_lora_v4_cleaned'),
                        help='Output directory for cleaned data')
    parser.add_argument('--products', '-p', type=str, default='all',
                        help='Comma-separated product names or "all" or "priority1"')
    parser.add_argument('--workers', '-w', type=int, default=4,
                        help='Number of parallel workers')
    parser.add_argument('--dry-run', action='store_true',
                        help='Analyze without saving')

    args = parser.parse_args()

    # Determine products to process
    if args.products == 'all':
        products = [d.name for d in args.input.iterdir() if d.is_dir()]
    elif args.products == 'priority1':
        # Priority 1: >60% error rate
        products = [
            'tmax_v2', 'tibero7_v2', 'openframe_batch_v2',
            'protrieve_v2', 'ofpli_v2', 'prosort_v2', 'ofcobol_v2'
        ]
    else:
        products = [p.strip() for p in args.products.split(',')]

    logger.info(f"Processing {len(products)} products...")
    logger.info(f"Input: {args.input}")
    logger.info(f"Output: {args.output}")

    # Process products
    all_stats = {}
    total_original = 0
    total_cleaned = 0

    # Prepare arguments for parallel processing
    process_args = [(p, args.input, args.output) for p in products]

    # Process (parallel or sequential based on dry-run)
    if args.dry_run:
        # Sequential for dry-run
        for p_args in process_args:
            product_name, stats = process_product(p_args)
            all_stats[product_name] = stats.to_dict()
            total_original += stats.original_count
            total_cleaned += stats.cleaned_count
    else:
        # Parallel processing
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_product, p_args): p_args[0]
                      for p_args in process_args}

            for future in as_completed(futures):
                product_name, stats = future.result()
                all_stats[product_name] = stats.to_dict()
                total_original += stats.original_count
                total_cleaned += stats.cleaned_count

                # Log progress
                removed = stats.original_count - stats.cleaned_count
                rate = (removed / max(stats.original_count, 1)) * 100
                logger.info(f"  {product_name}: {stats.original_count} → {stats.cleaned_count} ({rate:.1f}% removed)")

    # Summary
    print("\n" + "="*60)
    print("DEEP CLEANING SUMMARY")
    print("="*60)
    print(f"Total Original: {total_original:,}")
    print(f"Total Cleaned:  {total_cleaned:,}")
    print(f"Total Removed:  {total_original - total_cleaned:,} ({((total_original - total_cleaned) / max(total_original, 1)) * 100:.1f}%)")
    print("="*60)

    # Aggregate removal reasons
    removal_totals = {
        'broken_encoding': 0,
        'chinese_simplified': 0,
        'excessive_repetition': 0,
        'incomplete_sentence': 0,
        'too_short': 0,
        'nonsense_content': 0,
    }

    for product, stats in all_stats.items():
        for reason, count in stats.get('removed_by_type', {}).items():
            removal_totals[reason] += count

    print("\nRemoval by Type:")
    for reason, count in sorted(removal_totals.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count:,}")

    # Save report
    if not args.dry_run:
        report_path = args.output / 'cleaning_report.json'
        report = {
            'summary': {
                'total_original': total_original,
                'total_cleaned': total_cleaned,
                'total_removed': total_original - total_cleaned,
                'removal_rate': f"{((total_original - total_cleaned) / max(total_original, 1)) * 100:.1f}%",
                'removal_by_type': removal_totals
            },
            'products': all_stats
        }
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nReport saved to: {report_path}")

    print("\n[OK] Deep cleaning complete!")
    if args.dry_run:
        print("(Dry run - no files were saved)")


if __name__ == '__main__':
    main()
