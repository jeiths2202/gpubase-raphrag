#!/usr/bin/env python3
"""
학습 데이터셋 품질 분석 스크립트

중복 검사, 품질 검사, 분포 분석을 수행합니다.
"""
import os
import sys
import json
import re
from collections import Counter, defaultdict
from typing import Dict, List, Any, Set, Tuple
from pathlib import Path

def load_json(path: str) -> Any:
    """JSON 파일 로드"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_qa_from_chatml(text: str) -> Tuple[str, str]:
    """ChatML 형식에서 질문과 답변 추출"""
    q_match = re.search(r'<\|im_start\|>user\n(.+?)<\|im_end\|>', text, re.DOTALL)
    a_match = re.search(r'<\|im_start\|>assistant\n(.+?)<\|im_end\|>', text, re.DOTALL)

    question = q_match.group(1).strip() if q_match else ""
    answer = a_match.group(1).strip() if a_match else ""
    return question, answer

def analyze_train_json(path: str) -> Dict[str, Any]:
    """train.json 분석"""
    print(f"\n{'='*60}")
    print(f"Analyzing: {path}")
    print(f"{'='*60}")

    data = load_json(path)
    total = len(data)
    print(f"Total samples: {total:,}")

    # 중복 분석
    seen_questions = {}
    seen_answers = {}
    exact_duplicates = []
    question_duplicates = defaultdict(list)
    answer_duplicates = defaultdict(list)

    # 품질 문제
    low_quality = []
    empty_answers = []
    placeholder_answers = []
    language_mixed = []

    # 통계
    answer_lengths = []
    question_keywords = Counter()
    product_mentions = Counter()

    for i, item in enumerate(data):
        text = item.get("text", "")
        q, a = extract_qa_from_chatml(text)

        if not q or not a:
            empty_answers.append(i)
            continue

        # 중복 검사
        if q in seen_questions:
            question_duplicates[q].append(i)
            if not question_duplicates[q]:
                question_duplicates[q].append(seen_questions[q])
        seen_questions[q] = i

        if a in seen_answers:
            answer_duplicates[a].append(i)
        seen_answers[a] = i

        # 품질 검사
        answer_lengths.append(len(a))

        # 플레이스홀더 답변 감지
        placeholder_patterns = [
            r'^.+はOpenFrameシステムの(concept|api|command|config|error)です。$',
            r'^.+はOpenFrameシステムの.+です。$',
            r'^Unknown$',
            r'^\s*$'
        ]
        for pattern in placeholder_patterns:
            if re.match(pattern, a):
                placeholder_answers.append((i, q, a))
                break

        # 언어 혼합 감지 (일본어 질문 + 한국어/중국어 답변)
        ja_pattern = r'[\u3040-\u309F\u30A0-\u30FF]'
        ko_pattern = r'[\uAC00-\uD7AF]'
        zh_pattern = r'[\u4E00-\u9FFF]'

        has_ja_in_q = bool(re.search(ja_pattern, q))
        has_ko_in_a = bool(re.search(ko_pattern, a))
        has_zh_in_a = bool(re.search(zh_pattern, a))

        if has_ja_in_q and (has_ko_in_a or has_zh_in_a) and not bool(re.search(ja_pattern, a)):
            language_mixed.append((i, q[:50], a[:100]))

        # 제품 추출
        product_match = re.search(r'\*\*製品/Product\*\*:\s*(\S+)', a)
        if product_match:
            product_mentions[product_match.group(1)] += 1

    # 결과 출력
    print(f"\n--- Duplication Analysis ---")
    q_dup_count = sum(len(v) for v in question_duplicates.values() if len(v) > 0)
    a_dup_count = sum(len(v) for v in answer_duplicates.values() if len(v) > 0)
    print(f"Unique questions: {len(seen_questions):,}")
    print(f"Duplicate questions: {q_dup_count:,} ({q_dup_count/total*100:.2f}%)")
    print(f"Unique answers: {len(seen_answers):,}")
    print(f"Duplicate answers: {a_dup_count:,} ({a_dup_count/total*100:.2f}%)")

    print(f"\n--- Quality Issues ---")
    print(f"Empty Q/A pairs: {len(empty_answers):,}")
    print(f"Placeholder answers: {len(placeholder_answers):,} ({len(placeholder_answers)/total*100:.2f}%)")
    print(f"Language mixed (JA question, KO/ZH answer): {len(language_mixed):,}")

    if placeholder_answers:
        print(f"\n  Sample placeholder answers:")
        for i, q, a in placeholder_answers[:5]:
            print(f"    [{i}] Q: {q[:40]}... → A: {a}")

    if language_mixed:
        print(f"\n  Sample language mixed:")
        for i, q, a in language_mixed[:3]:
            print(f"    [{i}] Q: {q}... → A: {a}...")

    print(f"\n--- Answer Length Distribution ---")
    if answer_lengths:
        avg_len = sum(answer_lengths) / len(answer_lengths)
        sorted_lens = sorted(answer_lengths)
        print(f"Average: {avg_len:.1f} chars")
        print(f"Min: {min(answer_lengths)}")
        print(f"Max: {max(answer_lengths)}")
        print(f"Median: {sorted_lens[len(sorted_lens)//2]}")

        # 짧은 답변 비율
        short_answers = sum(1 for l in answer_lengths if l < 50)
        print(f"Very short (<50 chars): {short_answers:,} ({short_answers/total*100:.2f}%)")

    print(f"\n--- Top 10 Products ---")
    for product, count in product_mentions.most_common(10):
        print(f"  {product}: {count:,} ({count/total*100:.2f}%)")

    return {
        "total": total,
        "unique_questions": len(seen_questions),
        "duplicate_questions": q_dup_count,
        "unique_answers": len(seen_answers),
        "duplicate_answers": a_dup_count,
        "placeholder_answers": len(placeholder_answers),
        "language_mixed": len(language_mixed),
        "empty_answers": len(empty_answers),
        "avg_answer_length": sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0,
        "short_answers": sum(1 for l in answer_lengths if l < 50),
        "products": dict(product_mentions.most_common(20)),
        "sample_placeholders": [(i, q, a) for i, q, a in placeholder_answers[:10]]
    }

def analyze_learning_dataset(path: str) -> Dict[str, Any]:
    """learning_dataset.json 분석"""
    print(f"\n{'='*60}")
    print(f"Analyzing: {path}")
    print(f"{'='*60}")

    data = load_json(path)
    items = data.get("items", []) if isinstance(data, dict) else data
    total = len(items)
    print(f"Total items: {total:,}")

    # 중복 분석
    seen_names = {}
    name_duplicates = defaultdict(list)

    # 분포 분석
    type_dist = Counter()
    product_dist = Counter()
    source_dist = Counter()
    strategy_dist = Counter()

    # 품질 분석
    missing_description = []
    short_description = []

    for i, item in enumerate(items):
        name = item.get("name", "")
        item_type = item.get("type", "unknown")
        product = item.get("product", "Unknown")
        source = item.get("source_file", "Unknown")
        strategy = item.get("strategy_id", "Unknown")
        description = item.get("description", "")

        # 중복
        if name in seen_names:
            name_duplicates[name].append(i)
            if not name_duplicates[name]:
                name_duplicates[name].append(seen_names[name])
        seen_names[name] = i

        # 분포
        type_dist[item_type] += 1
        product_dist[product] += 1
        source_dist[source] += 1
        strategy_dist[strategy] += 1

        # 품질
        if not description:
            missing_description.append((i, name))
        elif len(description) < 20:
            short_description.append((i, name, description))

    # 결과 출력
    name_dup_count = sum(len(v) for v in name_duplicates.values() if len(v) > 0)
    print(f"\n--- Duplication ---")
    print(f"Unique names: {len(seen_names):,}")
    print(f"Duplicate names: {name_dup_count:,} ({name_dup_count/total*100:.2f}%)")

    if name_duplicates:
        print(f"\n  Sample duplicate names:")
        for name, indices in list(name_duplicates.items())[:5]:
            if len(indices) > 0:
                print(f"    '{name}': appears at indices {indices[:3]}...")

    print(f"\n--- Type Distribution ---")
    for t, c in type_dist.most_common():
        print(f"  {t}: {c:,} ({c/total*100:.2f}%)")

    print(f"\n--- Top 10 Products ---")
    for p, c in product_dist.most_common(10):
        print(f"  {p}: {c:,} ({c/total*100:.2f}%)")

    print(f"\n--- Quality Issues ---")
    print(f"Missing description: {len(missing_description):,}")
    print(f"Very short description (<20 chars): {len(short_description):,}")

    if short_description:
        print(f"\n  Sample short descriptions:")
        for i, name, desc in short_description[:5]:
            print(f"    [{i}] {name}: '{desc}'")

    return {
        "total": total,
        "unique_names": len(seen_names),
        "duplicate_names": name_dup_count,
        "type_distribution": dict(type_dist),
        "product_distribution": dict(product_dist.most_common(20)),
        "missing_description": len(missing_description),
        "short_description": len(short_description)
    }

def main():
    # Set stdout encoding for Windows
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    base_path = Path(__file__).parent.parent.parent / "uploads" / "summaries"

    results = {}

    # train.json 분석
    train_path = base_path / "train.json"
    if train_path.exists():
        results["train"] = analyze_train_json(str(train_path))

    # learning_dataset.json 분석
    learning_path = base_path / "learning_dataset.json"
    if learning_path.exists():
        results["learning_dataset"] = analyze_learning_dataset(str(learning_path))

    # restructured_learning_dataset.json 분석
    restructured_path = base_path / "restructured_learning_dataset.json"
    if restructured_path.exists():
        results["restructured_learning_dataset"] = analyze_learning_dataset(str(restructured_path))

    # 결과 저장
    output_path = base_path / "dataset_quality_analysis.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"Analysis saved to: {output_path}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
