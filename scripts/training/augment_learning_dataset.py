#!/usr/bin/env python3
"""
Learning Dataset Augmentation Script (v5 -> v5_augmented)

Augments insufficient products with additional Q&A pairs from:
1. Glossary terms
2. Commands documentation
3. Error codes
4. Configuration parameters

Target: Products with < 100 records after semantic cleaning
"""

import json
import re
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import hashlib

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
SUMMARIES_DIR = BASE_DIR / "uploads" / "summaries"
V5_FINAL_DIR = SUMMARIES_DIR / "multi_lora_v5_final"
OUTPUT_DIR = SUMMARIES_DIR / "multi_lora_v5_augmented"

# Product mapping from folder names to dataset product names
PRODUCT_MAPPING = {
    # Direct mappings
    "jeus": "jeus_v2",
    "tibero": "tibero7_v2",
    "tmax": "tmax_v2",
    "webtob": "webtob_v2",
    # OpenFrame products
    "openframe_base": "openframe_base_v2",
    "openframe_batch": "openframe_batch_v2",
    "openframe_common": "openframe_common_v2",
    "openframe_osc": "openframe_osc_v2",
    "openframe_osi": "openframe_osi_v2",
    "openframe_tacf": "openframe_tacf_v2",
    "openframe_aim": "openframe_aim_v2",
    "openframe_gateway": "openframe_gateway_v2",
    "openframe_hidb": "openframe_hidb_v2",
    "openframe_ndb": "openframe_ndb_v2",
    "openframe_vos3": "openframe_vos3_v2",
    # Tools
    "ofasm": "ofasm_v2",
    "ofcobol": "ofcobol_v2",
    "ofpli": "ofpli_v2",
    "ofmanager": "ofmanager_v2",
    "ofminer": "ofminer_v2",
    "ofstudio": "ofstudio_v2",
    "prosort": "prosort_v2",
    "prosync": "prosync_v2",
    "protrieve": "protrieve_v2",
}

# Reverse mapping
DATASET_TO_PRODUCT = {v: k for k, v in PRODUCT_MAPPING.items()}

# Target products for augmentation (P0: <50, P1: <100)
P0_PRODUCTS = [
    "openframe_ndb_v2",  # 11
    "prosync_v2",        # 16
    "prosort_v2",        # 17
    "ofasm_v2",          # 28
    "openframe_hidb_v2", # 30
    "ofpli_v2",          # 35
    "ofcobol_v2",        # 38
    "protrieve_v2",      # 49
]

P1_PRODUCTS = [
    "ofminer_v2",        # 54
    "ofstudio_v2",       # 60
    "openframe_tacf_v2", # 75
    "ofmanager_v2",      # 93
    "openframe_osi_v2",  # 97
    "openframe_aim_v2",  # 108
]

# Question templates (Japanese)
QUESTION_TEMPLATES = {
    "what_is": [
        "{term}とは何ですか？",
        "{term}について説明してください。",
        "{term}の概念を教えてください。",
    ],
    "how_to": [
        "{term}の使い方を教えてください。",
        "{term}のやり方を説明してください。",
        "{term}の手順を教えてください。",
    ],
    "error": [
        "エラーコード{code}の原因と対処方法を教えてください。",
        "{code}エラーが発生しました。どうすればよいですか？",
        "エラー{code}の解決方法を教えてください。",
    ],
    "command": [
        "{cmd}コマンドの使い方を教えてください。",
        "{cmd}コマンドについて説明してください。",
        "{cmd}の構文とオプションを教えてください。",
    ],
    "config": [
        "{param}パラメータの設定方法を教えてください。",
        "{param}の設定について説明してください。",
        "{param}の値と意味を教えてください。",
    ],
}


def generate_hash(text: str) -> str:
    """Generate short hash for deduplication."""
    return hashlib.md5(text.encode()).hexdigest()[:8]


def detect_product_from_content(content: str, filename: str) -> Optional[str]:
    """Detect product name from content or filename."""
    content_lower = content.lower()
    filename_lower = filename.lower()

    # Check filename first
    for key, product in PRODUCT_MAPPING.items():
        if key.replace("_", "") in filename_lower.replace("_", ""):
            return product

    # Check content for product mentions
    product_patterns = [
        (r"openframe\s*ndb|ndb\s*manager|ndbmgr", "openframe_ndb_v2"),
        (r"openframe\s*hidb|hidb\s*manager|hidbmgr", "openframe_hidb_v2"),
        (r"prosync|pro\s*sync", "prosync_v2"),
        (r"prosort|pro\s*sort", "prosort_v2"),
        (r"protrieve|pro\s*trieve", "protrieve_v2"),
        (r"ofasm|of\s*asm|assembler", "ofasm_v2"),
        (r"ofcobol|of\s*cobol|cobol", "ofcobol_v2"),
        (r"ofpli|of\s*pli|pli", "ofpli_v2"),
        (r"ofmanager|of\s*manager", "ofmanager_v2"),
        (r"ofminer|of\s*miner", "ofminer_v2"),
        (r"ofstudio|of\s*studio", "ofstudio_v2"),
        (r"openframe\s*tacf|tacfmgr", "openframe_tacf_v2"),
        (r"openframe\s*osc|oscmgr", "openframe_osc_v2"),
        (r"openframe\s*osi|osimgr", "openframe_osi_v2"),
        (r"openframe\s*aim", "openframe_aim_v2"),
        (r"openframe\s*gateway|ofgw", "openframe_gateway_v2"),
        (r"openframe\s*batch|tjclrun", "openframe_batch_v2"),
        (r"openframe\s*base", "openframe_base_v2"),
        (r"openframe\s*common", "openframe_common_v2"),
        (r"openframe\s*vos3|vos3", "openframe_vos3_v2"),
        (r"\btmax\b(?!\s*japan)", "tmax_v2"),
        (r"\bjeus\b", "jeus_v2"),
        (r"\btibero\b", "tibero7_v2"),
        (r"\bwebtob\b", "webtob_v2"),
    ]

    for pattern, product in product_patterns:
        if re.search(pattern, content_lower):
            return product

    return None


def parse_glossary_file(filepath: Path) -> List[Dict]:
    """Parse glossary markdown file and extract terms."""
    items = []
    content = filepath.read_text(encoding="utf-8")

    # Pattern: ## Term Name\n\nDefinition...
    term_pattern = r"##\s+([^\n]+)\n+([^#]+?)(?=\n##|\Z)"
    matches = re.findall(term_pattern, content, re.DOTALL)

    for term, definition in matches:
        term = term.strip()
        definition = definition.strip()

        if len(definition) < 30:
            continue

        product = detect_product_from_content(definition, filepath.name)
        if product:
            items.append({
                "type": "glossary",
                "term": term,
                "definition": definition,
                "product": product,
                "source": filepath.name,
            })

    return items


def parse_command_file(filepath: Path) -> List[Dict]:
    """Parse command documentation and extract commands."""
    items = []
    content = filepath.read_text(encoding="utf-8")

    # Detect product from filename
    product = detect_product_from_content(content, filepath.name)
    if not product:
        return items

    # Pattern: ### Command Name or ## Command Name
    cmd_pattern = r"###+\s+([^\n]+)\n+([^#]+?)(?=\n##|\Z)"
    matches = re.findall(cmd_pattern, content, re.DOTALL)

    for cmd_name, description in matches:
        cmd_name = cmd_name.strip()
        description = description.strip()

        if len(description) < 30:
            continue

        # Skip index entries
        if cmd_name.lower() in ["index", "contents", "overview"]:
            continue

        items.append({
            "type": "command",
            "command": cmd_name,
            "description": description,
            "product": product,
            "source": filepath.name,
        })

    return items


def parse_error_code_file(filepath: Path) -> List[Dict]:
    """Parse error code documentation."""
    items = []
    content = filepath.read_text(encoding="utf-8")

    product = detect_product_from_content(content, filepath.name)
    if not product:
        return items

    # Pattern: ### Error Code or Error -NNNN
    error_pattern = r"###?\s*([-\d]+|[A-Z]+[-_]?\d+)\s*[:\n]\s*([^\n]+)\n+([^#]+?)(?=\n##|\Z)"
    matches = re.findall(error_pattern, content, re.DOTALL)

    for code, name, description in matches:
        code = code.strip()
        name = name.strip()
        description = description.strip()

        if len(description) < 30:
            continue

        items.append({
            "type": "error",
            "code": code,
            "name": name,
            "description": description,
            "product": product,
            "source": filepath.name,
        })

    return items


def parse_config_file(filepath: Path) -> List[Dict]:
    """Parse configuration parameter documentation."""
    items = []
    content = filepath.read_text(encoding="utf-8")

    product = detect_product_from_content(content, filepath.name)
    if not product:
        return items

    # Pattern for config parameters
    config_pattern = r"###?\s+([A-Z_]+[A-Za-z_0-9]*)\s*\n+([^#]+?)(?=\n##|\Z)"
    matches = re.findall(config_pattern, content, re.DOTALL)

    for param, description in matches:
        param = param.strip()
        description = description.strip()

        if len(description) < 30:
            continue

        items.append({
            "type": "config",
            "parameter": param,
            "description": description,
            "product": product,
            "source": filepath.name,
        })

    return items


def generate_qa_from_item(item: Dict, idx: int = 0) -> Dict:
    """Generate Q&A pair from parsed item."""
    item_type = item["type"]

    if item_type == "glossary":
        templates = QUESTION_TEMPLATES["what_is"]
        question = templates[idx % len(templates)].format(term=item["term"])
        answer = f"{item['term']}は、{item['definition']}"

    elif item_type == "command":
        templates = QUESTION_TEMPLATES["command"]
        question = templates[idx % len(templates)].format(cmd=item["command"])
        answer = f"{item['command']}コマンドについて説明します。\n\n{item['description']}"

    elif item_type == "error":
        templates = QUESTION_TEMPLATES["error"]
        question = templates[idx % len(templates)].format(code=item["code"])
        answer = f"エラーコード{item['code']} ({item['name']})について説明します。\n\n{item['description']}"

    elif item_type == "config":
        templates = QUESTION_TEMPLATES["config"]
        question = templates[idx % len(templates)].format(param=item["parameter"])
        answer = f"{item['parameter']}パラメータについて説明します。\n\n{item['description']}"

    else:
        return None

    # Clean up answer
    answer = re.sub(r'\n{3,}', '\n\n', answer)
    answer = answer.strip()

    # Minimum answer length check
    if len(answer) < 50:
        return None

    return {
        "question": question,
        "answer": answer,
        "product": item["product"],
        "source": item.get("source", "augmented"),
        "type": item_type,
    }


def format_chatml(question: str, answer: str, product: str) -> str:
    """Format as ChatML for training."""
    system_prompt = f"あなたは{product.replace('_v2', '').replace('_', ' ').upper()}製品の専門家アシスタントです。正確で詳細な技術情報を提供してください。"

    return f"""<|im_start|>system
{system_prompt}<|im_end|>
<|im_start|>user
{question}<|im_end|>
<|im_start|>assistant
{answer}<|im_end|>"""


def load_existing_v5_data() -> Tuple[Dict[str, List], Dict[str, int]]:
    """Load existing v5_final data and count by product."""
    data_by_product = defaultdict(list)
    counts = {}

    for product_dir in V5_FINAL_DIR.iterdir():
        if not product_dir.is_dir():
            continue

        train_file = product_dir / "train.json"
        if train_file.exists():
            with open(train_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                product = product_dir.name
                data_by_product[product] = data
                counts[product] = len(data)

    return data_by_product, counts


def collect_augmentation_sources() -> Dict[str, List[Dict]]:
    """Collect all augmentation sources."""
    sources_by_product = defaultdict(list)

    # 1. Glossary
    glossary_dir = SUMMARIES_DIR / "glossary"
    if glossary_dir.exists():
        for f in glossary_dir.glob("*.md"):
            if f.name == "index.md":
                continue
            items = parse_glossary_file(f)
            for item in items:
                sources_by_product[item["product"]].append(item)

    # 2. Commands
    commands_dir = SUMMARIES_DIR / "commands"
    if commands_dir.exists():
        for f in commands_dir.glob("*.md"):
            if f.name == "index.md":
                continue
            items = parse_command_file(f)
            for item in items:
                sources_by_product[item["product"]].append(item)

    # 3. Error codes
    error_dir = SUMMARIES_DIR / "error-codes"
    if error_dir.exists():
        for f in error_dir.glob("*.md"):
            if f.name == "index.md":
                continue
            items = parse_error_code_file(f)
            for item in items:
                sources_by_product[item["product"]].append(item)

    # 4. Configs
    config_dir = SUMMARIES_DIR / "configs"
    if config_dir.exists():
        for f in config_dir.glob("*.md"):
            if f.name == "index.md":
                continue
            items = parse_config_file(f)
            for item in items:
                sources_by_product[item["product"]].append(item)

    return sources_by_product


def augment_product(
    product: str,
    existing_data: List[Dict],
    sources: List[Dict],
    target_count: int = 100
) -> Tuple[List[Dict], int]:
    """Augment a single product to reach target count."""
    current_count = len(existing_data)
    needed = max(0, target_count - current_count)

    if needed == 0:
        return existing_data, 0

    # Extract existing questions for deduplication
    existing_questions = set()
    for item in existing_data:
        text = item.get("text", "")
        # Extract question from ChatML
        match = re.search(r"<\|im_start\|>user\n(.+?)<\|im_end\|>", text, re.DOTALL)
        if match:
            existing_questions.add(match.group(1).strip())

    # Generate new Q&A pairs
    new_items = []
    for idx, source_item in enumerate(sources):
        if len(new_items) >= needed:
            break

        qa = generate_qa_from_item(source_item, idx)
        if qa and qa["question"] not in existing_questions:
            chatml = format_chatml(qa["question"], qa["answer"], product)
            new_items.append({"text": chatml})
            existing_questions.add(qa["question"])

    augmented_data = existing_data + new_items
    return augmented_data, len(new_items)


def main():
    print("[START] Learning Dataset Augmentation")
    print("=" * 60)

    # Load existing data
    print("\n[INFO] Loading existing v5_final data...")
    existing_data, counts = load_existing_v5_data()

    print(f"[INFO] Found {len(counts)} products")
    for product, count in sorted(counts.items(), key=lambda x: x[1]):
        status = "[P0]" if product in P0_PRODUCTS else "[P1]" if product in P1_PRODUCTS else "    "
        print(f"  {status} {product}: {count}")

    # Collect augmentation sources
    print("\n[INFO] Collecting augmentation sources...")
    sources = collect_augmentation_sources()

    for product, items in sources.items():
        print(f"  {product}: {len(items)} items available")

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Augment each target product
    print("\n[INFO] Augmenting products...")
    augmentation_stats = {}
    total_original = 0
    total_augmented = 0

    all_products = set(list(counts.keys()) + list(sources.keys()))

    for product in sorted(all_products):
        existing = existing_data.get(product, [])
        product_sources = sources.get(product, [])

        # Determine target count
        if product in P0_PRODUCTS:
            target = 100
        elif product in P1_PRODUCTS:
            target = 150
        else:
            target = len(existing)  # No augmentation needed

        augmented, added = augment_product(product, existing, product_sources, target)

        # Save augmented data
        product_dir = OUTPUT_DIR / product
        product_dir.mkdir(parents=True, exist_ok=True)

        with open(product_dir / "train.json", "w", encoding="utf-8") as f:
            json.dump(augmented, f, ensure_ascii=False, indent=2)

        total_original += len(existing)
        total_augmented += len(augmented)

        if added > 0:
            print(f"  [DONE] {product}: {len(existing)} -> {len(augmented)} (+{added})")
            augmentation_stats[product] = {
                "original": len(existing),
                "augmented": len(augmented),
                "added": added,
            }
        else:
            # Just copy the data
            augmentation_stats[product] = {
                "original": len(existing),
                "augmented": len(augmented),
                "added": 0,
            }

    # Save augmentation report
    report = {
        "summary": {
            "total_original": total_original,
            "total_augmented": total_augmented,
            "total_added": total_augmented - total_original,
            "products_augmented": sum(1 for s in augmentation_stats.values() if s["added"] > 0),
        },
        "products": augmentation_stats,
    }

    with open(OUTPUT_DIR / "augmentation_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("[REPORT] Augmentation Summary")
    print("=" * 60)
    print(f"Total Original: {total_original}")
    print(f"Total Augmented: {total_augmented}")
    print(f"Total Added: {total_augmented - total_original}")
    print(f"\nOutput: {OUTPUT_DIR}")
    print("[DONE] Augmentation complete!")


if __name__ == "__main__":
    main()
