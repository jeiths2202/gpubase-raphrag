#!/usr/bin/env python3
"""
CPT Automated Validation Pipeline.

Compares Base model vs CPT-trained model across multiple metrics:
- KL divergence
- Perplexity delta
- Task score delta (cloze test)
- Response length delta
- Token distribution shift

Usage:
    python -m scripts.governance.cpt_validation \
        --base-model Qwen/Qwen2.5-7B-Instruct \
        --cpt-adapter /raid/users/ofuser/qlora/outputs/cpt_adapter \
        --eval-data uploads/summaries/multi_lora_v9/eval_all.json \
        --output /raid/users/ofuser/qlora/governance/cpt_validation.json \
        --gpu 4
"""

import os
import sys
import json
import math
import logging
import argparse
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CPTValidationResult:
    """Single product CPT validation result."""
    product_id: str
    kl_divergence: float
    kl_std: float
    perplexity_base: float
    perplexity_cpt: float
    perplexity_delta: float       # 음수 = 개선
    perplexity_delta_pct: float
    task_score_base: float
    task_score_cpt: float
    task_score_delta: float       # 양수 = 개선
    length_mean_base: float
    length_mean_cpt: float
    length_delta: float
    length_delta_pct: float
    token_distribution_shift: float   # JS divergence
    num_eval_samples: int
    passed: bool
    fail_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CPTValidationReport:
    """Aggregated CPT validation report for all products."""
    timestamp: str
    base_model: str
    cpt_adapter: str
    total_products: int
    passed_products: int
    failed_products: int
    overall_pass: bool
    product_results: List[Dict]
    aggregate_metrics: Dict
    config_used: Dict

    def to_dict(self) -> Dict:
        return asdict(self)

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


class CPTValidator:
    """CPT validation pipeline."""

    def __init__(
        self,
        kl_fail_threshold: float = 10.0,
        kl_warn_threshold: float = 5.0,
        max_perplexity_increase_pct: float = 10.0,
        min_task_score: float = 0.7,
        max_length_increase_pct: float = 50.0,
        max_token_shift: float = 0.3,
        max_length: int = 1024,
        batch_size: int = 2,
    ):
        self.kl_fail_threshold = kl_fail_threshold
        self.kl_warn_threshold = kl_warn_threshold
        self.max_perplexity_increase_pct = max_perplexity_increase_pct
        self.min_task_score = min_task_score
        self.max_length_increase_pct = max_length_increase_pct
        self.max_token_shift = max_token_shift
        self.max_length = max_length
        self.batch_size = batch_size

    def validate_product(
        self,
        product_id: str,
        base_model,
        cpt_model,
        tokenizer,
        eval_texts: List[str],
        cloze_templates: Optional[List] = None,
    ) -> CPTValidationResult:
        """
        단일 제품에 대한 CPT 검증 수행.

        Args:
            product_id: 제품 ID
            base_model: 베이스 모델
            cpt_model: CPT 학습된 모델
            tokenizer: 토크나이저
            eval_texts: 평가 텍스트 리스트
            cloze_templates: Cloze 테스트 템플릿 [(context, expected_token), ...]
        """
        import torch
        from scripts.governance.kl_metrics import KLMetricsCalculator

        fail_reasons = []

        # 1. KL Divergence
        kl_calc = KLMetricsCalculator(
            device=str(base_model.device),
            max_length=self.max_length,
            batch_size=self.batch_size,
        )
        kl_result = kl_calc.compute_from_models(
            cpt_model, base_model, tokenizer, eval_texts
        )
        if kl_result.mean_kl > self.kl_fail_threshold:
            fail_reasons.append(
                f"KL divergence {kl_result.mean_kl:.4f} > threshold {self.kl_fail_threshold}"
            )

        # 2. Perplexity
        ppl_base = self._compute_perplexity(base_model, tokenizer, eval_texts)
        ppl_cpt = self._compute_perplexity(cpt_model, tokenizer, eval_texts)
        ppl_delta = ppl_cpt - ppl_base
        ppl_delta_pct = (ppl_delta / ppl_base * 100) if ppl_base > 0 else 0
        if ppl_delta_pct > self.max_perplexity_increase_pct:
            fail_reasons.append(
                f"Perplexity increased by {ppl_delta_pct:.1f}% "
                f"(max allowed: {self.max_perplexity_increase_pct}%)"
            )

        # 3. Task Score (Cloze Test)
        task_score_base = 0.0
        task_score_cpt = 0.0
        if cloze_templates:
            task_score_base = self._run_cloze_test(base_model, tokenizer, cloze_templates)
            task_score_cpt = self._run_cloze_test(cpt_model, tokenizer, cloze_templates)
            if task_score_cpt < self.min_task_score:
                fail_reasons.append(
                    f"Task score {task_score_cpt:.3f} < minimum {self.min_task_score}"
                )
            if task_score_cpt < task_score_base * 0.9:  # 10% 이상 하락
                fail_reasons.append(
                    f"Task score dropped: {task_score_base:.3f} → {task_score_cpt:.3f}"
                )

        # 4. Response Length
        lengths_base = self._measure_response_lengths(base_model, tokenizer, eval_texts[:20])
        lengths_cpt = self._measure_response_lengths(cpt_model, tokenizer, eval_texts[:20])
        len_mean_base = sum(lengths_base) / len(lengths_base) if lengths_base else 0
        len_mean_cpt = sum(lengths_cpt) / len(lengths_cpt) if lengths_cpt else 0
        len_delta = len_mean_cpt - len_mean_base
        len_delta_pct = (len_delta / len_mean_base * 100) if len_mean_base > 0 else 0
        if abs(len_delta_pct) > self.max_length_increase_pct:
            fail_reasons.append(
                f"Response length changed by {len_delta_pct:.1f}% "
                f"(max allowed: ±{self.max_length_increase_pct}%)"
            )

        # 5. Token Distribution Shift (Jensen-Shannon divergence)
        token_shift = self._compute_token_distribution_shift(
            base_model, cpt_model, tokenizer, eval_texts[:20]
        )
        if token_shift > self.max_token_shift:
            fail_reasons.append(
                f"Token distribution shift {token_shift:.4f} > threshold {self.max_token_shift}"
            )

        return CPTValidationResult(
            product_id=product_id,
            kl_divergence=kl_result.mean_kl,
            kl_std=kl_result.std_kl,
            perplexity_base=ppl_base,
            perplexity_cpt=ppl_cpt,
            perplexity_delta=ppl_delta,
            perplexity_delta_pct=ppl_delta_pct,
            task_score_base=task_score_base,
            task_score_cpt=task_score_cpt,
            task_score_delta=task_score_cpt - task_score_base,
            length_mean_base=len_mean_base,
            length_mean_cpt=len_mean_cpt,
            length_delta=len_delta,
            length_delta_pct=len_delta_pct,
            token_distribution_shift=token_shift,
            num_eval_samples=len(eval_texts),
            passed=len(fail_reasons) == 0,
            fail_reasons=fail_reasons,
        )

    def _compute_perplexity(self, model, tokenizer, texts: List[str]) -> float:
        """모델의 perplexity 계산."""
        import torch

        model.eval()
        total_loss = 0.0
        total_tokens = 0

        with torch.no_grad():
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                encodings = tokenizer(
                    batch,
                    return_tensors="pt",
                    truncation=True,
                    max_length=self.max_length,
                    padding=True,
                )
                input_ids = encodings["input_ids"].to(model.device)
                attention_mask = encodings["attention_mask"].to(model.device)

                labels = input_ids.clone()
                labels[attention_mask == 0] = -100

                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=labels,
                )
                valid_tokens = (labels != -100).sum().item()
                total_loss += outputs.loss.item() * valid_tokens
                total_tokens += valid_tokens

        if total_tokens == 0:
            return float("inf")
        return math.exp(total_loss / total_tokens)

    def _run_cloze_test(self, model, tokenizer, templates: List) -> float:
        """Cloze 테스트로 도메인 지식 평가."""
        import torch

        model.eval()
        correct = 0
        total = 0

        with torch.no_grad():
            for context, expected in templates:
                input_ids = tokenizer(
                    context, return_tensors="pt", truncation=True, max_length=512
                )["input_ids"].to(model.device)

                outputs = model(input_ids=input_ids)
                next_token_logits = outputs.logits[0, -1, :]
                predicted_id = next_token_logits.argmax().item()
                predicted = tokenizer.decode([predicted_id]).strip().lower()

                if expected.strip().lower() in predicted:
                    correct += 1
                total += 1

        return correct / total if total > 0 else 0.0

    def _measure_response_lengths(
        self, model, tokenizer, texts: List[str], max_new_tokens: int = 128
    ) -> List[int]:
        """생성된 응답의 토큰 길이 측정."""
        import torch

        model.eval()
        lengths = []

        with torch.no_grad():
            for text in texts:
                prompt = f"<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n"
                input_ids = tokenizer(
                    prompt, return_tensors="pt", truncation=True, max_length=512
                )["input_ids"].to(model.device)

                output_ids = model.generate(
                    input_ids,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    temperature=1.0,
                )
                gen_length = output_ids.shape[1] - input_ids.shape[1]
                lengths.append(gen_length)

        return lengths

    def _compute_token_distribution_shift(
        self, base_model, cpt_model, tokenizer, texts: List[str]
    ) -> float:
        """Jensen-Shannon divergence로 토큰 분포 변화 측정."""
        import torch
        import torch.nn.functional as F

        base_model.eval()
        cpt_model.eval()
        js_values = []

        with torch.no_grad():
            for text in texts:
                encodings = tokenizer(
                    text, return_tensors="pt",
                    truncation=True, max_length=self.max_length,
                )
                input_ids = encodings["input_ids"]

                base_logits = base_model(
                    input_ids=input_ids.to(base_model.device)
                ).logits[0, -1, :]
                cpt_logits = cpt_model(
                    input_ids=input_ids.to(cpt_model.device)
                ).logits[0, -1, :]

                # 같은 디바이스로
                if base_logits.device != cpt_logits.device:
                    cpt_logits = cpt_logits.to(base_logits.device)

                p = F.softmax(base_logits, dim=-1)
                q = F.softmax(cpt_logits, dim=-1)
                m = 0.5 * (p + q)

                # JS = 0.5 * KL(P||M) + 0.5 * KL(Q||M)
                kl_pm = F.kl_div(m.log(), p, reduction="sum").item()
                kl_qm = F.kl_div(m.log(), q, reduction="sum").item()
                js = 0.5 * kl_pm + 0.5 * kl_qm
                js_values.append(max(0, js))  # 수치 안정성

        return float(sum(js_values) / len(js_values)) if js_values else 0.0

    def run_full_validation(
        self,
        base_model,
        cpt_model,
        tokenizer,
        product_eval_data: Dict[str, List[str]],
        cloze_templates: Optional[Dict[str, List]] = None,
        config: Optional[Dict] = None,
    ) -> CPTValidationReport:
        """
        전체 22개 제품에 대한 CPT 검증 실행.

        Args:
            product_eval_data: {product_id: [eval_texts]}
            cloze_templates: {product_id: [(context, expected), ...]}
            config: 사용된 설정 (기록용)
        """
        results = []
        passed = 0
        failed = 0

        for product_id, texts in product_eval_data.items():
            logger.info(f"Validating product: {product_id} ({len(texts)} samples)")

            templates = None
            if cloze_templates and product_id in cloze_templates:
                templates = cloze_templates[product_id]

            result = self.validate_product(
                product_id=product_id,
                base_model=base_model,
                cpt_model=cpt_model,
                tokenizer=tokenizer,
                eval_texts=texts,
                cloze_templates=templates,
            )
            results.append(result.to_dict())

            if result.passed:
                passed += 1
                logger.info(f"  ✓ {product_id}: PASSED (KL={result.kl_divergence:.4f})")
            else:
                failed += 1
                logger.warning(
                    f"  ✗ {product_id}: FAILED - {', '.join(result.fail_reasons)}"
                )

        # 집계 메트릭
        all_kl = [r["kl_divergence"] for r in results]
        all_ppl_delta = [r["perplexity_delta_pct"] for r in results]

        aggregate = {
            "kl_mean": float(sum(all_kl) / len(all_kl)) if all_kl else 0,
            "kl_max": float(max(all_kl)) if all_kl else 0,
            "ppl_delta_mean": float(sum(all_ppl_delta) / len(all_ppl_delta)) if all_ppl_delta else 0,
            "pass_rate": passed / (passed + failed) if (passed + failed) > 0 else 0,
        }

        return CPTValidationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            base_model=str(getattr(base_model, "name_or_path", "unknown")),
            cpt_adapter=str(getattr(cpt_model, "name_or_path", "unknown")),
            total_products=passed + failed,
            passed_products=passed,
            failed_products=failed,
            overall_pass=failed == 0,
            product_results=results,
            aggregate_metrics=aggregate,
            config_used=config or {},
        )


def main():
    parser = argparse.ArgumentParser(description="CPT Automated Validation")
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--cpt-adapter", required=True, help="CPT adapter path")
    parser.add_argument("--eval-data", required=True, help="Eval data JSON path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--gpu", default="4", help="GPU ID")
    parser.add_argument("--max-samples", type=int, default=50, help="Max samples per product")
    args = parser.parse_args()

    # GPU 설정 (torch import 전에)
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
    os.environ["HF_HOME"] = "/raid/users/ofuser/.cache/huggingface"
    os.environ["TMPDIR"] = "/raid/users/ofuser/tmp"

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logger.info("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)

    logger.info("Loading base model...")
    base_model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    logger.info("Loading CPT adapter...")
    cpt_model = PeftModel.from_pretrained(base_model, args.cpt_adapter)

    # 평가 데이터 로드
    logger.info(f"Loading eval data from {args.eval_data}")
    eval_data_raw = json.loads(Path(args.eval_data).read_text(encoding="utf-8"))

    # product별 분류
    product_eval_data = {}
    if isinstance(eval_data_raw, list):
        # 단일 파일: text 필드에서 추출
        for item in eval_data_raw[:args.max_samples]:
            text = item.get("text", "")
            product_eval_data.setdefault("combined", []).append(text)
    elif isinstance(eval_data_raw, dict):
        product_eval_data = {
            k: v[:args.max_samples] for k, v in eval_data_raw.items()
        }

    validator = CPTValidator()
    report = validator.run_full_validation(
        base_model=base_model,
        cpt_model=cpt_model,
        tokenizer=tokenizer,
        product_eval_data=product_eval_data,
    )
    report.save(args.output)
    logger.info(f"Validation report saved to {args.output}")
    logger.info(f"Overall: {'PASSED' if report.overall_pass else 'FAILED'}")
    logger.info(
        f"Products: {report.passed_products}/{report.total_products} passed"
    )


if __name__ == "__main__":
    main()
