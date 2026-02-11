#!/usr/bin/env python3
"""
Model Evaluation Script - Perplexity + Cloze Test

각 학습 Phase 전후로 모델의 도메인 지식 수준을 평가합니다.

평가 항목:
1. Perplexity: holdout 도메인 텍스트에서 토큰 예측 정확도
2. Cloze Test: OpenFrame 도메인 용어 빈칸 채우기 (30개)

Usage:
    # 단일 모델 평가
    python scripts/training/evaluate_perplexity.py \
        --model Qwen/Qwen2.5-7B-Instruct \
        --test-data uploads/training_text/MVS_Openframe_7.1/corpus.txt

    # Cloze test 포함
    python scripts/training/evaluate_perplexity.py \
        --model models/qwen2.5-7b-openframe-cpt \
        --test-data uploads/training_text/MVS_Openframe_7.1/corpus.txt \
        --cloze

    # 두 모델 비교
    python scripts/training/evaluate_perplexity.py \
        --compare eval_base.json eval_cpt.json

Requirements:
    pip install transformers torch accelerate bitsandbytes
"""

import os
import sys
import json
import math
import logging
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================
# Cloze Test Templates
# ============================================

CLOZE_TEMPLATES = [
    # Commands → Product
    ("tjesmgrは___の管理コマンドです。", "TJES"),
    ("tacfmgrは___のセキュリティ管理ツールです。", "TACF"),
    ("hidbmgrは___データベースの管理コマンドです。", "HiDB"),
    ("oscmgrは___オンラインシステムの管理コマンドです。", "OSC"),
    ("osimgrは___オンラインシステムの管理コマンドです。", "OSI"),
    ("ndbmgrは___データベースの管理コマンドです。", "NDB"),

    # Acronyms
    ("TJESはTmax ___の略称です。", "Job Entry Subsystem"),
    ("TACFはTmax ___の略称です。", "Access Control Facility"),
    ("OSCはOpenFrame System ___です。", "Controller"),
    ("KSDSは___Sequenced Data Setの略です。", "Key"),
    ("ESDSは___Sequenced Data Setの略です。", "Entry"),
    ("GDGは___Data Groupの略です。", "Generation"),
    ("PDSは___Data Setの略です。", "Partitioned"),

    # Config files → Product
    ("tjes.confは___の設定ファイルです。", "TJES"),
    ("osc.confは___の設定ファイルです。", "OSC"),
    ("tacf.confは___の設定ファイルです。", "TACF"),

    # Error codes
    ("ABEND S0C7はデータ___エラーです。", "exception"),
    ("ABEND S0C4はプロテクション___エラーです。", "exception"),

    # Commands → Functions
    ("tmbootはシステムを___するコマンドです。", "起動"),
    ("tmdownはシステムを___するコマンドです。", "停止"),
    ("ofbootはOpenFrameを___するコマンドです。", "起動"),
    ("ofdownはOpenFrameを___するコマンドです。", "停止"),

    # Utilities
    ("idcamsは___データセットの管理ユーティリティです。", "VSAM"),
    ("iebgenerはデータセットの___ユーティリティです。", "コピー"),
    ("dfsortはデータの___ユーティリティです。", "ソート"),

    # JCL
    ("JCLの___ステートメントはジョブを定義します。", "JOB"),
    ("JCLの___ステートメントはプログラムを実行します。", "EXEC"),
    ("JCLのDDステートメントは___を定義します。", "データセット"),

    # Architecture
    ("OpenFrameは___のリホスティングプラットフォームです。", "メインフレーム"),
    ("tjclrunは___を実行するコマンドです。", "JCL"),
]


# ============================================
# Perplexity Evaluator
# ============================================

class PerplexityEvaluator:
    """도메인 텍스트에서 Perplexity 측정"""

    def __init__(self, model, tokenizer, max_seq_length: int = 4096):
        self.model = model
        self.tokenizer = tokenizer
        self.max_seq_length = max_seq_length
        self.device = model.device

    def compute(
        self,
        texts: List[str],
        stride: Optional[int] = None,
    ) -> Dict:
        """
        Perplexity 계산 (슬라이딩 윈도우).

        Perplexity = exp(평균 negative log-likelihood per token)
        """
        if stride is None:
            stride = self.max_seq_length // 2

        total_nll = 0.0
        total_tokens = 0

        self.model.eval()

        for i, text in enumerate(texts):
            encodings = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=False,
                add_special_tokens=False,
            )
            input_ids = encodings.input_ids[0]
            seq_len = len(input_ids)

            prev_end = 0
            for begin in range(0, seq_len, stride):
                end = min(begin + self.max_seq_length, seq_len)
                chunk = input_ids[begin:end].unsqueeze(0).to(self.device)

                target_len = end - prev_end
                labels = chunk.clone()
                labels[:, :-target_len] = -100

                with torch.no_grad():
                    outputs = self.model(chunk, labels=labels)
                    nll = outputs.loss.item() * target_len

                total_nll += nll
                total_tokens += target_len
                prev_end = end

                if end >= seq_len:
                    break

            if (i + 1) % 10 == 0:
                logger.info(f"  진행: {i + 1}/{len(texts)}")

        perplexity = math.exp(total_nll / total_tokens) if total_tokens > 0 else float("inf")

        return {
            "perplexity": perplexity,
            "avg_nll": total_nll / total_tokens if total_tokens > 0 else 0,
            "total_tokens": total_tokens,
            "num_texts": len(texts),
        }


# ============================================
# Cloze Test Evaluator
# ============================================

class ClozeTestEvaluator:
    """도메인 용어 Cloze (빈칸 채우기) 테스트"""

    def __init__(self, model, tokenizer):
        self.model = model
        self.tokenizer = tokenizer
        self.device = model.device

    def evaluate(
        self,
        templates: List[Tuple[str, str]] = None,
        max_new_tokens: int = 30,
    ) -> Dict:
        """Cloze test 실행"""
        if templates is None:
            templates = CLOZE_TEMPLATES

        self.model.eval()
        results = []
        correct = 0

        for template, expected in templates:
            # "___" 앞까지를 프롬프트로 사용
            prompt = template.split("___")[0]

            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)

            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    temperature=1.0,
                )

            generated = self.tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1]:],
                skip_special_tokens=True,
            ).strip()

            hit = expected.lower() in generated.lower()
            correct += int(hit)

            results.append({
                "template": template,
                "expected": expected,
                "generated": generated[:100],
                "correct": hit,
            })

        accuracy = correct / len(templates) if templates else 0

        return {
            "accuracy": accuracy,
            "correct": correct,
            "total": len(templates),
            "details": results,
        }


# ============================================
# Model Loading
# ============================================

def load_model(model_path: str, gpu: str = "0", use_4bit: bool = True):
    """모델 로드 (4-bit quantization)"""
    logger.info(f"모델 로드: {model_path}")

    kwargs = {
        "trust_remote_code": True,
        "device_map": {"": int(gpu)},
    }

    if use_4bit:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        kwargs["quantization_config"] = bnb_config
        kwargs["torch_dtype"] = torch.bfloat16
    else:
        kwargs["torch_dtype"] = torch.float16

    model = AutoModelForCausalLM.from_pretrained(model_path, **kwargs)
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

    return model, tokenizer


# ============================================
# Text Sampling
# ============================================

def sample_texts(
    text_path: str,
    num_samples: int = 50,
    min_length: int = 500,
    max_length: int = 5000,
    seed: int = 42,
) -> List[str]:
    """corpus에서 평가용 텍스트 샘플 추출"""
    import random
    random.seed(seed)

    path = Path(text_path)
    content = path.read_text(encoding="utf-8")

    # 문서 구분자로 분할
    doc_sep = "=" * 80
    documents = content.split(doc_sep)

    # "Document:" 라인 제거 및 빈 문서 제외
    valid_docs = []
    for doc in documents:
        doc = doc.strip()
        if doc.startswith("Document:"):
            doc = "\n".join(doc.split("\n")[1:]).strip()
        if len(doc) >= min_length:
            # 길이 제한
            if len(doc) > max_length:
                doc = doc[:max_length]
            valid_docs.append(doc)

    # 샘플 추출
    if len(valid_docs) <= num_samples:
        return valid_docs

    return random.sample(valid_docs, num_samples)


# ============================================
# Compare Results
# ============================================

def compare_results(result_files: List[str]):
    """여러 평가 결과 비교 출력"""
    results = []
    for f in result_files:
        path = Path(f)
        if not path.exists():
            logger.warning(f"결과 파일 없음: {f}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        results.append((path.stem, data))

    if not results:
        print("비교할 결과가 없습니다.")
        return

    print("\n" + "=" * 70)
    print("Model Evaluation Comparison")
    print("=" * 70)

    # Perplexity 비교
    print(f"\n{'Model':<30} {'Perplexity':>12} {'Avg NLL':>10} {'Tokens':>10}")
    print("-" * 65)
    for name, data in results:
        ppl = data.get("perplexity", {})
        if isinstance(ppl, dict):
            print(
                f"{name:<30} "
                f"{ppl.get('perplexity', 'N/A'):>12.2f} "
                f"{ppl.get('avg_nll', 'N/A'):>10.4f} "
                f"{ppl.get('total_tokens', 'N/A'):>10,}"
            )

    # Cloze test 비교
    has_cloze = any("cloze" in d for _, d in results)
    if has_cloze:
        print(f"\n{'Model':<30} {'Cloze Accuracy':>15} {'Correct':>10}")
        print("-" * 58)
        for name, data in results:
            cloze = data.get("cloze", {})
            if cloze:
                print(
                    f"{name:<30} "
                    f"{cloze.get('accuracy', 0):>14.1%} "
                    f"{cloze.get('correct', 0):>5}/{cloze.get('total', 0):<4}"
                )

    # 개선율
    if len(results) >= 2:
        base_ppl = results[0][1].get("perplexity", {}).get("perplexity", 0)
        for name, data in results[1:]:
            new_ppl = data.get("perplexity", {}).get("perplexity", 0)
            if base_ppl > 0 and new_ppl > 0:
                improvement = (base_ppl - new_ppl) / base_ppl * 100
                print(f"\n{name} vs {results[0][0]}: Perplexity {improvement:+.1f}%")

    print("=" * 70)


# ============================================
# CLI
# ============================================

def main():
    parser = argparse.ArgumentParser(
        description="Model Evaluation - Perplexity + Cloze Test",
    )

    subparsers = parser.add_subparsers(dest="command")

    # Evaluate command
    eval_parser = subparsers.add_parser("eval", help="단일 모델 평가")
    eval_parser.add_argument("--model", required=True, help="모델 경로")
    eval_parser.add_argument("--test-data", required=True, help="평가용 텍스트")
    eval_parser.add_argument("--output", "-o", help="결과 JSON 출력 경로")
    eval_parser.add_argument("--num-samples", type=int, default=50)
    eval_parser.add_argument("--max-seq-length", type=int, default=4096)
    eval_parser.add_argument("--cloze", action="store_true", help="Cloze test 포함")
    eval_parser.add_argument("--gpu", default="0")
    eval_parser.add_argument("--no-4bit", action="store_true")

    # Compare command
    cmp_parser = subparsers.add_parser("compare", help="결과 비교")
    cmp_parser.add_argument("files", nargs="+", help="결과 JSON 파일들")

    # 기본 동작 (subcommand 없이)
    parser.add_argument("--model", help="모델 경로")
    parser.add_argument("--test-data", help="평가용 텍스트")
    parser.add_argument("--output", "-o", help="결과 JSON 출력 경로")
    parser.add_argument("--num-samples", type=int, default=50)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--cloze", action="store_true")
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--no-4bit", action="store_true")
    parser.add_argument("--compare", nargs="+", help="비교할 결과 파일들")

    args = parser.parse_args()

    # Compare mode
    if args.command == "compare" or args.compare:
        files = getattr(args, "files", None) or args.compare
        compare_results(files)
        return

    # Eval mode
    model_path = getattr(args, "model", None)
    test_data = getattr(args, "test_data", None)

    if not model_path or not test_data:
        parser.print_help()
        return

    gpu = getattr(args, "gpu", "0")
    use_4bit = not getattr(args, "no_4bit", False)

    # 모델 로드
    model, tokenizer = load_model(model_path, gpu, use_4bit)

    result = {
        "model": model_path,
        "test_data": test_data,
        "evaluated_at": datetime.now().isoformat(),
    }

    # Perplexity
    logger.info("Perplexity 평가 시작...")
    texts = sample_texts(
        test_data,
        num_samples=getattr(args, "num_samples", 50),
    )
    evaluator = PerplexityEvaluator(
        model, tokenizer,
        max_seq_length=getattr(args, "max_seq_length", 4096),
    )
    ppl_result = evaluator.compute(texts)
    result["perplexity"] = ppl_result
    logger.info(f"Perplexity: {ppl_result['perplexity']:.2f}")

    # Cloze test
    if getattr(args, "cloze", False):
        logger.info("Cloze test 시작...")
        cloze_eval = ClozeTestEvaluator(model, tokenizer)
        cloze_result = cloze_eval.evaluate()
        result["cloze"] = cloze_result
        logger.info(
            f"Cloze Accuracy: {cloze_result['accuracy']:.1%} "
            f"({cloze_result['correct']}/{cloze_result['total']})"
        )

    # 결과 저장
    output_path = getattr(args, "output", None)
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"결과 저장: {output_path}")

    # 출력
    print(f"\n=== Evaluation Results ===")
    print(f"Model: {model_path}")
    print(f"Perplexity: {ppl_result['perplexity']:.2f}")
    print(f"Avg NLL: {ppl_result['avg_nll']:.4f}")
    print(f"Total tokens: {ppl_result['total_tokens']:,}")
    if "cloze" in result:
        c = result["cloze"]
        print(f"Cloze Accuracy: {c['accuracy']:.1%} ({c['correct']}/{c['total']})")


if __name__ == "__main__":
    main()
