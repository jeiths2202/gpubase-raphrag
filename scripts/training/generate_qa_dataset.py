#!/usr/bin/env python3
"""
Q&A Dataset Generator for Fine-tuning Learning LLM

Summaries 데이터(에러 코드, 명령어, 용어)에서 Q&A 학습 데이터를 자동 생성합니다.
생성된 데이터는 Qwen2.5-7B QLoRA 파인튜닝에 사용됩니다.

Usage:
    python generate_qa_dataset.py --output /opt/kms/data/training/summaries_qa.jsonl
    python generate_qa_dataset.py --output summaries_qa.jsonl --stats-only
"""
import os
import sys
import json
import re
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import random

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================
# Q&A Templates
# ============================================

ERROR_QUESTION_TEMPLATES = [
    "에러코드 {code}의 원인은 무엇인가요?",
    "에러 {code} 해결방법을 알려주세요",
    "{name} 에러가 발생했을 때 대처방법은?",
    "{code} 에러 원인과 해결책",
    "에러 {code}이(가) 발생했습니다. 어떻게 해야 하나요?",
    "{module}에서 {code} 에러가 발생하면?",
    "{code} 오류 설명",
    "에러코드 {code}에 대해 알려주세요",
]

ERROR_QUESTION_TEMPLATES_JA = [
    "エラーコード {code} の原因は何ですか？",
    "エラー {code} の解決方法を教えてください",
    "{code} エラーが発生した場合の対処方法は？",
    "エラーコード {code} について教えてください",
    "{module} で {code} エラーが発生しました",
]

COMMAND_QUESTION_TEMPLATES = [
    "{cmd} 명령어 사용법은?",
    "{cmd} 명령어의 구문과 옵션을 알려주세요",
    "{cmd} 실행 방법",
    "{product}에서 {cmd} 사용하는 방법",
    "{cmd} 명령어가 무엇인가요?",
    "{cmd}의 구문을 알려주세요",
    "{cmd} 명령어 설명",
    "어떻게 {cmd}을(를) 실행하나요?",
]

COMMAND_QUESTION_TEMPLATES_JA = [
    "{cmd} コマンドの使い方は？",
    "{cmd} コマンドの構文とオプションを教えてください",
    "{cmd} の実行方法",
    "{product} で {cmd} を使う方法",
    "{cmd} コマンドとは何ですか？",
]

GLOSSARY_QUESTION_TEMPLATES = [
    "{term}가 무엇인가요?",
    "{term}의 의미와 기능을 설명해주세요",
    "{term} 정의",
    "{term}이(가) 뭔가요?",
    "{term}의 의미는?",
    "{term}에 대해 설명해주세요",
]

GLOSSARY_QUESTION_TEMPLATES_JA = [
    "{term} とは何ですか？",
    "{term} の意味と機能を説明してください",
    "{term} の定義",
    "{term} について説明してください",
]

# Multi-product comparison question templates
MULTI_PRODUCT_QUESTION_TEMPLATES = [
    "{cmd}가 MVS와 MSP에서 어떻게 다른가요?",
    "{cmd} 명령어의 플랫폼별 차이점을 설명해주세요",
    "{platform}에서 {cmd} 명령어 사용법",
    "MVS와 MSP에서 {cmd} 차이점은?",
    "{cmd} 명령어가 플랫폼마다 다른가요?",
    "OpenFrame {platform}에서 {cmd} 사용방법",
    "{cmd}의 버전별 차이점을 알려주세요",
]

MULTI_PRODUCT_QUESTION_TEMPLATES_JA = [
    "MVS と MSP で {cmd} はどう違いますか？",
    "{cmd} コマンドのプラットフォーム別の違いを説明してください",
    "{platform} で {cmd} コマンドの使い方",
    "MVS と MSP での {cmd} の違いは何ですか？",
]


# ============================================
# Markdown Parsers
# ============================================

def parse_error_codes_md(content: str, source_file: str) -> List[Dict[str, Any]]:
    """
    Parse error codes from markdown content.

    Expected format:
    | 코드 | 설명 | 소스 |
    |------|------|------|
    | `-5212` | DATASET_NOT_FOUND | file.pdf:p40 |
    """
    errors = []

    # Try to extract module from header
    module_match = re.search(r'^#\s*(\w+)\s+에러\s*코드|Error\s*Code', content, re.MULTILINE | re.IGNORECASE)
    default_module = module_match.group(1) if module_match else "Unknown"

    # Parse table rows
    # Pattern for table row: | code | description | source |
    table_pattern = re.compile(
        r'\|\s*`?(-?\d+)`?\s*\|\s*([^|]+)\|\s*([^|]*)\|',
        re.MULTILINE
    )

    for match in table_pattern.finditer(content):
        code = match.group(1).strip()
        description = match.group(2).strip()
        source = match.group(3).strip()

        if code and description and not description.startswith('--'):
            # Extract page number from source
            page_match = re.search(r':p\.?(\d+)', source)
            page_num = page_match.group(1) if page_match else None

            errors.append({
                "code": code,
                "name": description[:100],  # Limit name length
                "description": description,
                "module": default_module,
                "source_file": source_file,
                "source_pdf": source.split(':')[0] if ':' in source else source,
                "page_number": page_num,
            })

    # Also try ## CODE section format
    section_pattern = re.compile(
        r'##\s*(-?\d+)\s*\n+([^#]+?)(?=\n##|\Z)',
        re.MULTILINE | re.DOTALL
    )

    for match in section_pattern.finditer(content):
        code = match.group(1).strip()
        section_content = match.group(2).strip()

        # Check if already parsed from table
        if any(e["code"] == code for e in errors):
            continue

        # Extract description (first line)
        lines = section_content.split('\n')
        description = lines[0].strip() if lines else ""

        # Extract solution/cause if present
        solution = ""
        for line in lines:
            if '대처' in line or '해결' in line or '対処' in line:
                solution = line.split(':', 1)[-1].strip() if ':' in line else ""

        if code and description:
            errors.append({
                "code": code,
                "name": description[:100],
                "description": description,
                "solution": solution,
                "module": default_module,
                "source_file": source_file,
            })

    return errors


def parse_commands_md(content: str, source_file: str) -> List[Dict[str, Any]]:
    """
    Parse commands from markdown content.

    Expected format:
    ## COMMAND_NAME

    Description text

    **구문:**
    ```
    command syntax
    ```

    - 소스: file.pdf (p.XX)
    """
    commands = []

    # Extract product from filename
    product_match = re.search(r'OpenFrame_(\w+)_', source_file)
    default_product = product_match.group(1) if product_match else "OpenFrame"

    # Parse ## sections
    section_pattern = re.compile(
        r'##\s+([^\n]+)\n+([^#]+?)(?=\n##|\Z)',
        re.MULTILINE | re.DOTALL
    )

    for match in section_pattern.finditer(content):
        cmd_name = match.group(1).strip()
        section_content = match.group(2).strip()

        # Skip index/table of contents
        if cmd_name.lower() in ['목차', 'index', 'contents', '---']:
            continue

        # Extract description (first paragraph)
        desc_match = re.search(r'^([^*\n`]+)', section_content)
        description = desc_match.group(1).strip() if desc_match else ""

        # Extract syntax from code block
        syntax_match = re.search(r'```\s*\n?([^`]+)```', section_content)
        syntax = syntax_match.group(1).strip() if syntax_match else ""

        # Extract source info
        source_match = re.search(r'-\s*소스[:：]\s*([^\n]+)', section_content)
        source_info = source_match.group(1).strip() if source_match else ""

        # Extract page number
        page_match = re.search(r'\(p\.?(\d+)\)', source_info)
        page_num = page_match.group(1) if page_match else None

        if cmd_name and (description or syntax):
            commands.append({
                "name": cmd_name,
                "description": description,
                "syntax": syntax,
                "product": default_product,
                "source_file": source_file,
                "source_pdf": source_info.split('(')[0].strip() if '(' in source_info else source_info,
                "page_number": page_num,
            })

    return commands


def parse_glossary_md(content: str, source_file: str) -> List[Dict[str, Any]]:
    """
    Parse glossary terms from markdown content.

    Expected format:
    ## TERM_NAME

    Description text

    - 소스: file.pdf (p.XX)
    """
    terms = []

    # Parse ## sections
    section_pattern = re.compile(
        r'##\s+([^\n]+)\n+([^#]+?)(?=\n##|\Z)',
        re.MULTILINE | re.DOTALL
    )

    for match in section_pattern.finditer(content):
        term_name = match.group(1).strip()
        section_content = match.group(2).strip()

        # Skip headers/toc
        if term_name.lower() in ['목차', 'index', '---', '용어집']:
            continue

        # Extract description (first line/paragraph)
        lines = section_content.split('\n')
        description = ""
        for line in lines:
            line = line.strip()
            if line and not line.startswith('-') and not line.startswith('*'):
                description = line
                break

        # Extract source info
        source_match = re.search(r'-\s*소스[:：]\s*([^\n]+)', section_content)
        source_info = source_match.group(1).strip() if source_match else ""

        # Extract page number
        page_match = re.search(r'\(p\.?(\d+)\)', source_info)
        page_num = page_match.group(1) if page_match else None

        if term_name and description:
            terms.append({
                "name": term_name,
                "description": description,
                "source_file": source_file,
                "source_pdf": source_info.split('(')[0].strip() if source_info else "",
                "page_number": page_num,
            })

    return terms


# ============================================
# Q&A Generation
# ============================================

class QADatasetGenerator:
    """Summaries에서 Q&A 학습 데이터 자동 생성"""

    def __init__(self, summaries_dir: str = "uploads/summaries"):
        self.summaries_dir = Path(summaries_dir)
        self.error_codes: List[Dict] = []
        self.commands: List[Dict] = []
        self.glossary: List[Dict] = []

    def load_summaries(self) -> Tuple[int, int, int]:
        """Load and parse all summary files"""

        # Load error codes
        error_dir = self.summaries_dir / "error_codes"
        if error_dir.exists():
            for md_file in error_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding='utf-8')
                    errors = parse_error_codes_md(content, md_file.name)
                    self.error_codes.extend(errors)
                except Exception as e:
                    logger.warning(f"Failed to parse {md_file}: {e}")

        # Load commands
        commands_dir = self.summaries_dir / "commands"
        if commands_dir.exists():
            for md_file in commands_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding='utf-8')
                    cmds = parse_commands_md(content, md_file.name)
                    self.commands.extend(cmds)
                except Exception as e:
                    logger.warning(f"Failed to parse {md_file}: {e}")

        # Load glossary/terms
        for subdir in ["glossary", "terms"]:
            terms_dir = self.summaries_dir / subdir
            if terms_dir.exists():
                for md_file in terms_dir.glob("*.md"):
                    try:
                        content = md_file.read_text(encoding='utf-8')
                        terms = parse_glossary_md(content, md_file.name)
                        self.glossary.extend(terms)
                    except Exception as e:
                        logger.warning(f"Failed to parse {md_file}: {e}")

        logger.info(f"Loaded: {len(self.error_codes)} errors, {len(self.commands)} commands, {len(self.glossary)} terms")
        return len(self.error_codes), len(self.commands), len(self.glossary)

    def generate_error_code_qa(self) -> List[Dict[str, Any]]:
        """에러코드 Q&A 쌍 생성"""
        qa_pairs = []

        for error in self.error_codes:
            code = error.get("code", "")
            name = error.get("name", "")
            description = error.get("description", "")
            solution = error.get("solution", "")
            module = error.get("module", "")
            source_pdf = error.get("source_pdf", "")
            page_num = error.get("page_number", "")

            if not code or not description:
                continue

            # Build answer
            answer_parts = []
            answer_parts.append(f"에러 코드 {code} ({name}):\n")
            answer_parts.append(f"설명: {description}\n")
            if module and module != "Unknown":
                answer_parts.append(f"모듈: {module}\n")
            if solution:
                answer_parts.append(f"대처방법: {solution}\n")
            if source_pdf:
                source_ref = source_pdf
                if page_num:
                    source_ref += f" (p.{page_num})"
                answer_parts.append(f"\n출처: {source_ref}")

            answer = "".join(answer_parts)

            # Generate multiple Q&A pairs with different templates
            templates = ERROR_QUESTION_TEMPLATES + ERROR_QUESTION_TEMPLATES_JA

            # Select 2-4 templates randomly
            selected_templates = random.sample(templates, min(4, len(templates)))

            for template in selected_templates:
                try:
                    question = template.format(
                        code=code,
                        name=name,
                        module=module
                    )

                    qa_pairs.append({
                        "instruction": question,
                        "input": "",
                        "output": answer,
                        "metadata": {
                            "type": "error_code",
                            "code": code,
                            "module": module,
                            "source_pdf": source_pdf,
                            "page_number": page_num,
                        }
                    })
                except KeyError:
                    continue  # Skip templates that need missing fields

        logger.info(f"Generated {len(qa_pairs)} error code Q&A pairs")
        return qa_pairs

    def generate_command_qa(self) -> List[Dict[str, Any]]:
        """명령어 Q&A 쌍 생성"""
        qa_pairs = []

        for cmd in self.commands:
            name = cmd.get("name", "")
            description = cmd.get("description", "")
            syntax = cmd.get("syntax", "")
            product = cmd.get("product", "")
            source_pdf = cmd.get("source_pdf", "")
            page_num = cmd.get("page_number", "")

            if not name or not (description or syntax):
                continue

            # Build answer
            answer_parts = []
            answer_parts.append(f"{name} 명령어:\n")
            if description:
                answer_parts.append(f"설명: {description}\n")
            if syntax:
                answer_parts.append(f"구문:\n```\n{syntax}\n```\n")
            if product:
                answer_parts.append(f"제품: {product}\n")
            if source_pdf:
                source_ref = source_pdf
                if page_num:
                    source_ref += f" (p.{page_num})"
                answer_parts.append(f"\n출처: {source_ref}")

            answer = "".join(answer_parts)

            # Generate multiple Q&A pairs
            templates = COMMAND_QUESTION_TEMPLATES + COMMAND_QUESTION_TEMPLATES_JA
            selected_templates = random.sample(templates, min(4, len(templates)))

            for template in selected_templates:
                try:
                    question = template.format(
                        cmd=name,
                        product=product or "OpenFrame"
                    )

                    qa_pairs.append({
                        "instruction": question,
                        "input": "",
                        "output": answer,
                        "metadata": {
                            "type": "command",
                            "name": name,
                            "product": product,
                            "source_pdf": source_pdf,
                            "page_number": page_num,
                        }
                    })
                except KeyError:
                    continue

        logger.info(f"Generated {len(qa_pairs)} command Q&A pairs")
        return qa_pairs

    def generate_glossary_qa(self) -> List[Dict[str, Any]]:
        """용어 Q&A 쌍 생성"""
        qa_pairs = []

        for term in self.glossary:
            name = term.get("name", "")
            description = term.get("description", "")
            source_pdf = term.get("source_pdf", "")
            page_num = term.get("page_number", "")

            if not name or not description:
                continue

            # Skip very short or generic descriptions
            if len(description) < 10:
                continue

            # Build answer
            answer_parts = []
            answer_parts.append(f"{name}:\n")
            answer_parts.append(f"{description}\n")
            if source_pdf:
                source_ref = source_pdf
                if page_num:
                    source_ref += f" (p.{page_num})"
                answer_parts.append(f"\n출처: {source_ref}")

            answer = "".join(answer_parts)

            # Generate multiple Q&A pairs
            templates = GLOSSARY_QUESTION_TEMPLATES + GLOSSARY_QUESTION_TEMPLATES_JA
            selected_templates = random.sample(templates, min(3, len(templates)))

            for template in selected_templates:
                try:
                    question = template.format(term=name)

                    qa_pairs.append({
                        "instruction": question,
                        "input": "",
                        "output": answer,
                        "metadata": {
                            "type": "glossary",
                            "name": name,
                            "source_pdf": source_pdf,
                            "page_number": page_num,
                        }
                    })
                except KeyError:
                    continue

        logger.info(f"Generated {len(qa_pairs)} glossary Q&A pairs")
        return qa_pairs

    def generate_multi_product_qa(self) -> List[Dict[str, Any]]:
        """
        Generate Q&A pairs for multi-product comparisons.

        Groups commands that exist on multiple platforms (MVS, MSP, XSP, VOS3)
        and generates comparison questions.
        """
        qa_pairs = []

        # Group commands by name (case-insensitive)
        from collections import defaultdict
        by_name: Dict[str, List[Dict]] = defaultdict(list)

        for cmd in self.commands:
            name = cmd.get("name", "").lower()
            if name:
                by_name[name].append(cmd)

        # Extract platform from product field or source file
        def extract_platform(cmd: Dict) -> str:
            product = cmd.get("product", "")
            source = cmd.get("source_file", "")

            for platform in ["MVS", "MSP", "XSP", "VOS3"]:
                if platform in product.upper() or platform in source.upper():
                    return platform
            return "Common"

        # Generate comparison Q&A for commands on multiple platforms
        for name, cmd_variants in by_name.items():
            if len(cmd_variants) < 2:
                continue

            # Get unique platforms
            platforms = list(set(extract_platform(c) for c in cmd_variants))
            if len(platforms) < 2:
                continue

            # Sort by platform priority
            platform_order = {"MVS": 0, "MSP": 1, "XSP": 2, "VOS3": 3, "Common": 4}
            platforms.sort(key=lambda p: platform_order.get(p, 99))

            # Get the canonical name
            canonical_name = cmd_variants[0].get("name", name)

            # Build comparison answer
            answer_parts = [f"{canonical_name} 명령어의 플랫폼별 정보:\n"]

            for cmd in cmd_variants:
                platform = extract_platform(cmd)
                description = cmd.get("description", "")
                syntax = cmd.get("syntax", "")

                answer_parts.append(f"\n## {platform}\n")
                if description:
                    answer_parts.append(f"설명: {description}\n")
                if syntax:
                    answer_parts.append(f"구문: `{syntax}`\n")

                source_pdf = cmd.get("source_pdf", "")
                page_num = cmd.get("page_number", "")
                if source_pdf:
                    source_ref = source_pdf
                    if page_num:
                        source_ref += f" (p.{page_num})"
                    answer_parts.append(f"출처: {source_ref}\n")

            answer = "".join(answer_parts)

            # Check if descriptions differ (platform-specific behavior)
            descriptions = [c.get("description", "") for c in cmd_variants if c.get("description")]
            has_differences = len(set(descriptions)) > 1

            if has_differences:
                answer_parts.insert(1, "⚠️ 플랫폼별로 동작이 다를 수 있습니다.\n")
                answer = "".join(answer_parts)

            # Generate questions from templates
            templates = MULTI_PRODUCT_QUESTION_TEMPLATES + MULTI_PRODUCT_QUESTION_TEMPLATES_JA
            selected_templates = random.sample(templates, min(4, len(templates)))

            for template in selected_templates:
                try:
                    question = template.format(
                        cmd=canonical_name,
                        platform=platforms[0] if platforms else "MVS"
                    )

                    qa_pairs.append({
                        "instruction": question,
                        "input": "",
                        "output": answer,
                        "metadata": {
                            "type": "multi_product",
                            "name": canonical_name,
                            "platforms": platforms,
                            "has_differences": has_differences,
                        }
                    })
                except KeyError:
                    continue

        logger.info(f"Generated {len(qa_pairs)} multi-product comparison Q&A pairs")
        return qa_pairs

    def generate_all(self, include_multi_product: bool = True) -> List[Dict[str, Any]]:
        """Generate all Q&A pairs

        Args:
            include_multi_product: Include platform comparison Q&A (default True)
        """
        all_qa = []

        all_qa.extend(self.generate_error_code_qa())
        all_qa.extend(self.generate_command_qa())
        all_qa.extend(self.generate_glossary_qa())

        if include_multi_product:
            all_qa.extend(self.generate_multi_product_qa())

        # Shuffle for training
        random.shuffle(all_qa)

        return all_qa

    def save_dataset(
        self,
        output_path: str,
        qa_pairs: Optional[List[Dict[str, Any]]] = None
    ) -> int:
        """
        Save dataset to JSONL format.

        Args:
            output_path: Output file path
            qa_pairs: Q&A pairs (if None, generate all)

        Returns:
            Number of Q&A pairs saved
        """
        if qa_pairs is None:
            qa_pairs = self.generate_all()

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            for qa in qa_pairs:
                # Write in JSONL format (one JSON object per line)
                f.write(json.dumps(qa, ensure_ascii=False) + '\n')

        logger.info(f"Saved {len(qa_pairs)} Q&A pairs to {output_path}")
        return len(qa_pairs)

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the dataset"""
        return {
            "summaries_dir": str(self.summaries_dir),
            "error_codes_count": len(self.error_codes),
            "commands_count": len(self.commands),
            "glossary_count": len(self.glossary),
            "total_items": len(self.error_codes) + len(self.commands) + len(self.glossary),
            "estimated_qa_pairs": {
                "error_codes": len(self.error_codes) * 4,
                "commands": len(self.commands) * 4,
                "glossary": len(self.glossary) * 3,
                "total": len(self.error_codes) * 4 + len(self.commands) * 4 + len(self.glossary) * 3,
            },
            "timestamp": datetime.now().isoformat(),
        }


# ============================================
# Main
# ============================================

def main():
    parser = argparse.ArgumentParser(description="Generate Q&A dataset from summaries")
    parser.add_argument(
        "--output",
        type=str,
        default="/opt/kms/data/training/summaries_qa.jsonl",
        help="Output JSONL file path"
    )
    parser.add_argument(
        "--summaries-dir",
        type=str,
        default="uploads/summaries",
        help="Path to summaries directory"
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show statistics, don't generate dataset"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="If > 0, generate only N sample Q&A pairs"
    )
    parser.add_argument(
        "--include-multi-product",
        action="store_true",
        default=True,
        help="Include multi-product/platform comparison Q&A pairs (default: True)"
    )
    parser.add_argument(
        "--no-multi-product",
        action="store_true",
        help="Exclude multi-product/platform comparison Q&A pairs"
    )

    args = parser.parse_args()

    # Handle multi-product flag
    include_multi_product = args.include_multi_product and not args.no_multi_product

    # Initialize generator
    generator = QADatasetGenerator(summaries_dir=args.summaries_dir)

    # Load summaries
    generator.load_summaries()

    # Show statistics
    stats = generator.get_statistics()
    print("\n" + "="*60)
    print("Dataset Statistics")
    print("="*60)
    print(f"Summaries Directory: {stats['summaries_dir']}")
    print(f"Error Codes: {stats['error_codes_count']}")
    print(f"Commands: {stats['commands_count']}")
    print(f"Glossary Terms: {stats['glossary_count']}")
    print(f"Total Items: {stats['total_items']}")
    print("\nEstimated Q&A Pairs:")
    print(f"  Error Code Q&A: ~{stats['estimated_qa_pairs']['error_codes']}")
    print(f"  Command Q&A: ~{stats['estimated_qa_pairs']['commands']}")
    print(f"  Glossary Q&A: ~{stats['estimated_qa_pairs']['glossary']}")
    print(f"  Total: ~{stats['estimated_qa_pairs']['total']}")
    print("="*60 + "\n")

    if args.stats_only:
        return

    # Generate dataset
    qa_pairs = generator.generate_all(include_multi_product=include_multi_product)

    # Sample if requested
    if args.sample > 0 and len(qa_pairs) > args.sample:
        qa_pairs = random.sample(qa_pairs, args.sample)
        logger.info(f"Sampled {args.sample} Q&A pairs")

    # Save dataset
    count = generator.save_dataset(args.output, qa_pairs)

    # Save statistics alongside
    stats_path = Path(args.output).with_suffix('.stats.json')
    stats['actual_qa_pairs'] = count
    stats['output_file'] = args.output

    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\nGenerated {count} Q&A pairs")
    print(f"Output: {args.output}")
    print(f"Stats: {stats_path}")

    # Show samples
    print("\n" + "="*60)
    print("Sample Q&A Pairs")
    print("="*60)

    for i, qa in enumerate(qa_pairs[:3]):
        print(f"\n[Sample {i+1}] Type: {qa['metadata'].get('type', 'unknown')}")
        print(f"Q: {qa['instruction']}")
        print(f"A: {qa['output'][:300]}...")


if __name__ == "__main__":
    main()
