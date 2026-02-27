#!/usr/bin/env python3
"""
DPO Preference Pair Generator

E2E 테스트 패턴, 요약본, SFT 데이터에서 DPO (Direct Preference Optimization)
학습용 preference pair (prompt, chosen, rejected)를 생성합니다.

3가지 생성 전략:
1. E2E Cross-Product: notExpected 키워드를 활용한 교차 제품 오답 생성
2. Factual Mutation: 정확한 답변에 에러 코드/파라미터/제품명 변경
3. Summary Cross-Match: SFT 데이터에서 교차 제품 오답 매칭

Usage:
    python scripts/training/generate_dpo_data.py \
        --output uploads/training_text/dpo_pairs.json

    # 최소 pair 수 지정
    python scripts/training/generate_dpo_data.py \
        --output uploads/training_text/dpo_pairs.json --min-pairs 500

    # 특정 전략만 사용
    python scripts/training/generate_dpo_data.py \
        --strategies e2e,factual --output uploads/training_text/dpo_pairs.json
"""

import os
import sys
import re
import json
import random
import logging
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class DPOConfig:
    """DPO 데이터 생성 설정"""

    # E2E 테스트 소스
    e2e_test_file: str = "e2e/e2e_sentence_test.js"

    # 요약본 디렉토리
    summaries_dir: str = "uploads/summaries"

    # SFT 데이터 디렉토리
    sft_data_dir: str = "uploads/summaries/multi_lora_v9_improved"

    # 출력
    output_path: str = "uploads/training_text/dpo_pairs.json"

    # 전략
    strategies: List[str] = field(
        default_factory=lambda: ["e2e", "factual", "cross_match"]
    )

    # 최소/최대 pair 수
    min_pairs: int = 300
    max_pairs: int = 2000

    seed: int = 42


# ============================================
# E2E Test Case Parser
# ============================================

def parse_e2e_test_cases(js_file: str) -> List[Dict]:
    """e2e_sentence_test.js에서 TEST_CASES와 STRICT_MATCH_TESTS 파싱"""
    path = Path(js_file)
    if not path.exists():
        logger.warning(f"E2E 테스트 파일 없음: {js_file}")
        return []

    content = path.read_text(encoding="utf-8")

    tests = []

    # { keyword: '...', query: '...', expected: [...], notExpected: [...] } 패턴 파싱
    pattern = re.compile(
        r"\{\s*"
        r"keyword:\s*'([^']+)'\s*,\s*"
        r"query:\s*'([^']+)'\s*,\s*"
        r"lang:\s*'([^']+)'\s*,\s*"
        r"expected:\s*\[([^\]]*)\]\s*,\s*"
        r"(?:notExpected|strictNotExpected):\s*\[([^\]]*)\]",
        re.DOTALL,
    )

    for m in pattern.finditer(content):
        keyword = m.group(1)
        query = m.group(2)
        lang = m.group(3)
        expected = [s.strip().strip("'\"") for s in m.group(4).split(",") if s.strip()]
        not_expected = [
            s.strip().strip("'\"") for s in m.group(5).split(",") if s.strip()
        ]

        tests.append({
            "keyword": keyword,
            "query": query,
            "lang": lang,
            "expected": expected,
            "notExpected": not_expected,
        })

    logger.info(f"E2E 테스트 케이스 파싱: {len(tests)}개")
    return tests


# ============================================
# Summary Data Loader
# ============================================

class SummaryLoader:
    """요약본 데이터 로더"""

    def __init__(self, summaries_dir: str):
        self.base = Path(summaries_dir)

    def load_commands(self) -> Dict[str, Dict[str, str]]:
        """명령어 요약본 로드 → {keyword: {name, syntax, description}}"""
        commands = {}
        cmd_dir = self.base / "commands"
        if not cmd_dir.exists():
            return commands

        for md_file in cmd_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            current_cmd = None

            for line in content.split("\n"):
                # ## COMMAND_NAME 패턴
                if line.startswith("## ") and not line.startswith("## #"):
                    current_cmd = line[3:].strip()
                    commands[current_cmd] = {
                        "name": current_cmd,
                        "description": "",
                        "syntax": "",
                        "source_file": md_file.name,
                    }
                elif current_cmd:
                    if line.startswith("```") and commands[current_cmd]["syntax"] == "":
                        continue
                    elif commands[current_cmd]["syntax"] == "" and line.strip().startswith(("$", current_cmd)):
                        commands[current_cmd]["syntax"] = line.strip()
                    elif commands[current_cmd]["description"] == "" and line.strip() and not line.startswith(("**", "```", "- ", "---")):
                        commands[current_cmd]["description"] = line.strip()

        logger.info(f"명령어 로드: {len(commands)}개")
        return commands

    def load_error_codes(self) -> Dict[str, Dict]:
        """에러 코드 요약본 로드"""
        errors = {}
        err_dir = self.base / "error-codes"
        if not err_dir.exists():
            return errors

        for md_file in err_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            # 테이블 패턴: | -5212 | NAME | Desc | Solution |
            for line in content.split("\n"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3 and re.match(r"-?\d{3,5}", parts[0]):
                    code = parts[0]
                    name = parts[1] if len(parts) > 1 else ""
                    desc = parts[2] if len(parts) > 2 else ""
                    solution = parts[3] if len(parts) > 3 else ""
                    errors[code] = {
                        "code": code,
                        "name": name,
                        "description": desc,
                        "solution": solution,
                        "source_file": md_file.name,
                    }

        logger.info(f"에러 코드 로드: {len(errors)}개")
        return errors

    def load_glossary_terms(self) -> Dict[str, str]:
        """용어 사전 로드"""
        terms = {}
        gls_dir = self.base / "glossary"
        if not gls_dir.exists():
            return terms

        for md_file in gls_dir.glob("*.md"):
            if md_file.name in ("index.md",):
                continue
            content = md_file.read_text(encoding="utf-8")
            current_term = None
            for line in content.split("\n"):
                if line.startswith("## "):
                    current_term = line[3:].strip()
                elif current_term and line.strip() and not line.startswith(("**", "---", "#")):
                    terms[current_term] = line.strip()
                    current_term = None

        logger.info(f"용어 로드: {len(terms)}개")
        return terms


# ============================================
# SFT Data Loader
# ============================================

def load_sft_data(sft_dir: str) -> Dict[str, List[Dict]]:
    """SFT v9 데이터를 제품별로 로드"""
    base = Path(sft_dir)
    if not base.exists():
        return {}

    product_data = {}
    for product_dir in base.iterdir():
        if not product_dir.is_dir():
            continue
        train_file = product_dir / "train.json"
        if not train_file.exists():
            continue

        data = json.loads(train_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            product_data[product_dir.name] = data
        elif isinstance(data, dict) and "data" in data:
            product_data[product_dir.name] = data["data"]

    logger.info(f"SFT 데이터 로드: {len(product_data)} 제품")
    return product_data


def extract_qa_from_chatml(text: str) -> Tuple[str, str]:
    """ChatML 텍스트에서 user/assistant 추출"""
    user_match = re.search(
        r"<\|im_start\|>user\n(.*?)<\|im_end\|>", text, re.DOTALL
    )
    asst_match = re.search(
        r"<\|im_start\|>assistant\n(.*?)<\|im_end\|>", text, re.DOTALL
    )
    user = user_match.group(1).strip() if user_match else ""
    asst = asst_match.group(1).strip() if asst_match else ""
    return user, asst


# ============================================
# Strategy 1: E2E Cross-Product Pairs
# ============================================

class E2ECrossProductGenerator:
    """E2E 테스트의 notExpected를 활용한 교차 제품 오답 생성"""

    def __init__(self, commands: Dict, errors: Dict, terms: Dict):
        self.commands = commands
        self.errors = errors
        self.terms = terms

    def _find_answer_for_keyword(self, keyword: str) -> str:
        """키워드에 대한 올바른 답변 검색"""
        # 명령어 검색
        if keyword in self.commands:
            cmd = self.commands[keyword]
            parts = [f"{keyword}は、{cmd['description']}"]
            if cmd["syntax"]:
                parts.append(f"\n構文: {cmd['syntax']}")
            return "".join(parts)

        # 대소문자 무관 명령어 검색
        for k, v in self.commands.items():
            if k.lower() == keyword.lower():
                parts = [f"{k}は、{v['description']}"]
                if v["syntax"]:
                    parts.append(f"\n構文: {v['syntax']}")
                return "".join(parts)

        # 에러 코드 검색
        code = keyword.replace("ABEND ", "").replace("エラーコード ", "")
        if code in self.errors:
            err = self.errors[code]
            return (
                f"エラーコード {code} ({err['name']}): {err['description']}。"
                f"\n対処方法: {err['solution']}"
            )

        # 용어 검색
        if keyword in self.terms:
            return f"{keyword}とは、{self.terms[keyword]}"

        # 부분 매칭
        for k, v in self.terms.items():
            if keyword.lower() in k.lower():
                return f"{k}とは、{v}"

        return ""

    def generate(self, test_cases: List[Dict]) -> List[Dict]:
        """E2E 테스트에서 preference pair 생성"""
        pairs = []

        for test in test_cases:
            not_expected = test.get("notExpected", [])
            if not not_expected:
                continue

            prompt = test["query"]
            keyword = test["keyword"]

            # Chosen: 올바른 답변
            chosen = self._find_answer_for_keyword(keyword)
            if not chosen:
                continue

            # Rejected: 잘못된 제품/명령어 답변
            for wrong_kw in not_expected:
                wrong_answer = self._find_answer_for_keyword(wrong_kw)
                if not wrong_answer:
                    # 오답 합성: chosen 답변에서 키워드를 교체
                    wrong_answer = chosen.replace(keyword, wrong_kw)
                    if wrong_answer == chosen:
                        continue

                pairs.append({
                    "prompt": prompt,
                    "chosen": chosen,
                    "rejected": wrong_answer,
                    "source": "e2e_cross_product",
                    "metadata": {
                        "keyword": keyword,
                        "wrong_keyword": wrong_kw,
                        "lang": test.get("lang", "ja"),
                    },
                })

        logger.info(f"E2E Cross-Product pairs: {len(pairs)}")
        return pairs


# ============================================
# Strategy 2: Factual Mutation Pairs
# ============================================

class FactualMutationGenerator:
    """정확한 답변에 사실적 오류를 도입하여 rejected 생성"""

    PRODUCT_NAMES = [
        "TJES", "TACF", "OSC", "OSI", "Base", "HiDB", "NDB",
        "OpenFrame", "Batch", "Gateway",
    ]

    def __init__(self, commands: Dict, errors: Dict, terms: Dict):
        self.commands = commands
        self.errors = errors
        self.terms = terms
        self.rng = random.Random(42)

    def _swap_product(self, text: str, original: str) -> str:
        """제품명 교체"""
        candidates = [p for p in self.PRODUCT_NAMES if p != original]
        if not candidates:
            return text
        replacement = self.rng.choice(candidates)
        return text.replace(original, replacement)

    def _mutate_error_code(self, code: str) -> str:
        """에러 코드 번호 변경"""
        numeric = re.search(r"(\d+)", code)
        if numeric:
            num = int(numeric.group(1))
            offset = self.rng.choice([1, -1, 10, -10, 100, -100])
            new_num = abs(num + offset)
            return code.replace(numeric.group(1), str(new_num))
        return code

    def generate_from_commands(self, commands: Dict) -> List[Dict]:
        """명령어 기반 mutation pairs"""
        pairs = []
        cmd_list = list(commands.items())

        for cmd_name, cmd_info in cmd_list:
            if not cmd_info["description"]:
                continue

            prompt = f"{cmd_name}コマンドについて説明してください。"
            chosen = f"{cmd_name}は、{cmd_info['description']}"
            if cmd_info["syntax"]:
                chosen += f"\n構文: {cmd_info['syntax']}"

            # Mutation 1: 제품명 교체
            for product in self.PRODUCT_NAMES:
                if product.lower() in cmd_info.get("source_file", "").lower():
                    rejected = self._swap_product(chosen, cmd_name)
                    if rejected != chosen:
                        pairs.append({
                            "prompt": prompt,
                            "chosen": chosen,
                            "rejected": rejected,
                            "source": "factual_product_swap",
                        })
                    break

            # Mutation 2: 다른 명령어의 설명으로 교체
            if len(cmd_list) > 1:
                other_cmd, other_info = self.rng.choice(cmd_list)
                while other_cmd == cmd_name and len(cmd_list) > 1:
                    other_cmd, other_info = self.rng.choice(cmd_list)
                if other_info["description"] and other_cmd != cmd_name:
                    rejected = f"{cmd_name}は、{other_info['description']}"
                    pairs.append({
                        "prompt": prompt,
                        "chosen": chosen,
                        "rejected": rejected,
                        "source": "factual_desc_swap",
                    })

        return pairs

    def generate_from_errors(self, errors: Dict) -> List[Dict]:
        """에러 코드 기반 mutation pairs"""
        pairs = []
        error_list = list(errors.items())

        for code, info in error_list:
            if not info["description"]:
                continue

            prompt = f"エラーコード {code} の原因を教えてください。"
            chosen = (
                f"エラーコード {code} ({info['name']}): {info['description']}。"
            )
            if info["solution"]:
                chosen += f"\n対処方法: {info['solution']}"

            # Mutation: 에러 코드 번호 변경
            wrong_code = self._mutate_error_code(code)
            wrong_info = errors.get(wrong_code)
            if wrong_info and wrong_code != code:
                rejected = (
                    f"エラーコード {code} ({wrong_info['name']}): "
                    f"{wrong_info['description']}。"
                )
                pairs.append({
                    "prompt": prompt,
                    "chosen": chosen,
                    "rejected": rejected,
                    "source": "factual_error_swap",
                })

            # Mutation: 다른 에러의 설명으로 교체
            if len(error_list) > 1:
                other_code, other_info = self.rng.choice(error_list)
                if other_code != code and other_info["description"]:
                    rejected = (
                        f"エラーコード {code} ({other_info['name']}): "
                        f"{other_info['description']}。"
                    )
                    pairs.append({
                        "prompt": prompt,
                        "chosen": chosen,
                        "rejected": rejected,
                        "source": "factual_error_desc_swap",
                    })

        return pairs

    def generate(self) -> List[Dict]:
        """전체 factual mutation pairs 생성"""
        pairs = []
        pairs.extend(self.generate_from_commands(self.commands))
        pairs.extend(self.generate_from_errors(self.errors))
        logger.info(f"Factual Mutation pairs: {len(pairs)}")
        return pairs


# ============================================
# Strategy 3: SFT Cross-Match Pairs
# ============================================

class SFTCrossMatchGenerator:
    """SFT 데이터에서 교차 제품 오답 매칭"""

    def __init__(self, sft_data: Dict[str, List[Dict]]):
        self.sft_data = sft_data
        self.rng = random.Random(42)

    def generate(self, max_per_product: int = 20) -> List[Dict]:
        """제품 간 교차 오답 pair 생성"""
        pairs = []
        products = list(self.sft_data.keys())

        if len(products) < 2:
            logger.warning("SFT 데이터에 제품이 2개 미만, cross-match 생략")
            return pairs

        for product_name, data_list in self.sft_data.items():
            # 다른 제품 선택
            other_products = [p for p in products if p != product_name]
            if not other_products:
                continue

            count = 0
            for item in data_list:
                if count >= max_per_product:
                    break

                text = item.get("text", "")
                if not text:
                    continue

                user_q, correct_a = extract_qa_from_chatml(text)
                if not user_q or not correct_a or len(correct_a) < 50:
                    continue

                # 다른 제품에서 유사한 길이의 답변 찾기
                other_product = self.rng.choice(other_products)
                other_data = self.sft_data[other_product]
                if not other_data:
                    continue

                other_item = self.rng.choice(other_data)
                other_text = other_item.get("text", "")
                _, wrong_a = extract_qa_from_chatml(other_text)

                if not wrong_a or wrong_a == correct_a:
                    continue

                pairs.append({
                    "prompt": user_q,
                    "chosen": correct_a,
                    "rejected": wrong_a,
                    "source": "sft_cross_match",
                    "metadata": {
                        "correct_product": product_name,
                        "wrong_product": other_product,
                    },
                })
                count += 1

        logger.info(f"SFT Cross-Match pairs: {len(pairs)}")
        return pairs


# ============================================
# Main Generator
# ============================================

def generate_dpo_pairs(config: DPOConfig) -> List[Dict]:
    """전체 DPO preference pair 생성"""
    random.seed(config.seed)

    all_pairs = []

    # 데이터 로드
    summary_loader = SummaryLoader(config.summaries_dir)
    commands = summary_loader.load_commands()
    errors = summary_loader.load_error_codes()
    terms = summary_loader.load_glossary_terms()

    # Strategy 1: E2E Cross-Product
    if "e2e" in config.strategies:
        test_cases = parse_e2e_test_cases(config.e2e_test_file)
        gen = E2ECrossProductGenerator(commands, errors, terms)
        all_pairs.extend(gen.generate(test_cases))

    # Strategy 2: Factual Mutation
    if "factual" in config.strategies:
        gen = FactualMutationGenerator(commands, errors, terms)
        all_pairs.extend(gen.generate())

    # Strategy 3: SFT Cross-Match
    if "cross_match" in config.strategies:
        sft_data = load_sft_data(config.sft_data_dir)
        gen = SFTCrossMatchGenerator(sft_data)
        all_pairs.extend(gen.generate())

    # 중복 제거 (prompt+chosen 기준)
    seen = set()
    unique_pairs = []
    for pair in all_pairs:
        key = (pair["prompt"], pair["chosen"][:100])
        if key not in seen:
            seen.add(key)
            unique_pairs.append(pair)

    # 셔플
    random.shuffle(unique_pairs)

    # 최대 수 제한
    if len(unique_pairs) > config.max_pairs:
        unique_pairs = unique_pairs[: config.max_pairs]

    logger.info(
        f"총 DPO pairs: {len(unique_pairs)} "
        f"(원본 {len(all_pairs)}, 중복 제거 후)"
    )

    if len(unique_pairs) < config.min_pairs:
        logger.warning(
            f"최소 pair 수 미달: {len(unique_pairs)} < {config.min_pairs}. "
            f"더 많은 소스 데이터가 필요합니다."
        )

    return unique_pairs


def main():
    parser = argparse.ArgumentParser(
        description="DPO Preference Pair Generator",
    )
    parser.add_argument(
        "--output", "-o",
        default="uploads/training_text/dpo_pairs.json",
        help="출력 파일 경로",
    )
    parser.add_argument(
        "--e2e-test-file",
        default="e2e/e2e_sentence_test.js",
        help="E2E 테스트 JS 파일 경로",
    )
    parser.add_argument(
        "--summaries-dir",
        default="uploads/summaries",
        help="요약본 디렉토리",
    )
    parser.add_argument(
        "--sft-data-dir",
        default="uploads/summaries/multi_lora_v9_improved",
        help="SFT v9 데이터 디렉토리",
    )
    parser.add_argument(
        "--strategies",
        default="e2e,factual,cross_match",
        help="생성 전략 (쉼표 구분: e2e,factual,cross_match)",
    )
    parser.add_argument("--min-pairs", type=int, default=300)
    parser.add_argument("--max-pairs", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    config = DPOConfig(
        e2e_test_file=args.e2e_test_file,
        summaries_dir=args.summaries_dir,
        sft_data_dir=args.sft_data_dir,
        output_path=args.output,
        strategies=args.strategies.split(","),
        min_pairs=args.min_pairs,
        max_pairs=args.max_pairs,
        seed=args.seed,
    )

    pairs = generate_dpo_pairs(config)

    if args.dry_run:
        print(f"\n=== DPO Data Generation (Dry Run) ===")
        print(f"Total pairs: {len(pairs)}")
        sources = {}
        for p in pairs:
            src = p.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1
        for src, cnt in sorted(sources.items()):
            print(f"  {src}: {cnt}")
        if pairs:
            print(f"\nSample pair:")
            sample = pairs[0]
            print(f"  Prompt: {sample['prompt'][:80]}...")
            print(f"  Chosen: {sample['chosen'][:80]}...")
            print(f"  Rejected: {sample['rejected'][:80]}...")
        return

    # 저장
    output_path = Path(config.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(pairs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 통계 저장
    sources = {}
    for p in pairs:
        src = p.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1

    stats = {
        "total_pairs": len(pairs),
        "sources": sources,
        "strategies": config.strategies,
        "generated_at": datetime.now().isoformat(),
    }
    stats_path = output_path.with_suffix(".stats.json")
    stats_path.write_text(
        json.dumps(stats, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n=== DPO Data Generated ===")
    print(f"Total pairs: {len(pairs)}")
    for src, cnt in sorted(sources.items()):
        print(f"  {src}: {cnt}")
    print(f"Output: {output_path}")
    print(f"Stats: {stats_path}")


if __name__ == "__main__":
    main()
