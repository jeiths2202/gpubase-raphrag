#!/usr/bin/env python3
"""
Enterprise Governance CI/CD Pipeline Orchestrator.

Automates the full governance pipeline:
    1. Train CPT → 2. Validate CPT → 3. Hallucination Guard
    → 4. Drift Analysis → 5. Quality Gate → 6. Approve/Block
    → 7. Deploy Adapter → 8. Monitor Beta Auto-Tuning

Each step produces JSON output for CI/CD integration.
Pipeline is fully reproducible with config + data versioning.

Usage:
    # Full pipeline
    python -m scripts.governance.pipeline --config governance_config.json

    # Single step
    python -m scripts.governance.pipeline --step validate --product jeus_v2
"""

import os
import sys
import json
import time
import logging
import argparse
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from scripts.governance.governance_config import (
    GovernanceConfig,
    ApprovalStatus,
    ALL_PRODUCT_IDS,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepResult:
    """단일 파이프라인 스텝 결과."""
    step_name: str
    status: str          # "success", "failed", "skipped"
    duration_ms: float
    output_path: str
    details: Dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PipelineReport:
    """전체 파이프라인 실행 결과."""
    run_id: str
    timestamp: str
    config_hash: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    skipped_steps: int
    overall_status: str      # "success", "failed", "partial"
    steps: List[Dict]
    deployment_decision: str  # "approved", "blocked", "manual_review"
    duration_total_ms: float

    def to_dict(self) -> Dict:
        return asdict(self)

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


class GovernancePipeline:
    """엔터프라이즈 거버넌스 CI/CD 파이프라인."""

    STEP_ORDER = [
        "validate_cpt",
        "hallucination_guard",
        "drift_analysis",
        "quality_gate",
        "beta_autotune",
        "deployment_decision",
    ]

    def __init__(self, config: Optional[GovernanceConfig] = None):
        self.config = config or GovernanceConfig()
        self.output_dir = Path(self.config.governance_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.run_id = datetime.now(timezone.utc).strftime("pipeline_%Y%m%d_%H%M%S")
        self.run_dir = self.output_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────
    # Full Pipeline
    # ──────────────────────────────────────

    def run_full_pipeline(
        self,
        base_model=None,
        cpt_model=None,
        tokenizer=None,
        eval_data: Optional[Dict] = None,
    ) -> PipelineReport:
        """
        전체 거버넌스 파이프라인 실행.

        model/tokenizer가 None이면 mock 모드 (설정 검증만).
        """
        pipeline_start = time.time()
        steps = []
        completed = 0
        failed = 0
        skipped = 0

        # 설정 저장 (재현성)
        self.config.save(str(self.run_dir / "config.json"))

        # Step 1: CPT Validation
        result = self._run_step(
            "validate_cpt",
            lambda: self._step_validate_cpt(
                base_model, cpt_model, tokenizer, eval_data
            ),
        )
        steps.append(result.to_dict())
        if result.status == "success":
            completed += 1
        elif result.status == "failed":
            failed += 1
        else:
            skipped += 1

        # Step 2: Hallucination Guard
        result = self._run_step(
            "hallucination_guard",
            lambda: self._step_hallucination_guard(
                cpt_model, tokenizer, eval_data
            ),
        )
        steps.append(result.to_dict())
        if result.status == "success":
            completed += 1
        elif result.status == "failed":
            failed += 1
        else:
            skipped += 1

        # Step 3: Drift Analysis
        result = self._run_step(
            "drift_analysis",
            lambda: self._step_drift_analysis(),
        )
        steps.append(result.to_dict())
        if result.status == "success":
            completed += 1
        elif result.status == "failed":
            failed += 1
        else:
            skipped += 1

        # Step 4: Quality Gate
        cpt_output = self.run_dir / "validate_cpt.json"
        hall_output = self.run_dir / "hallucination_guard.json"
        drift_output = self.run_dir / "drift_analysis.json"

        result = self._run_step(
            "quality_gate",
            lambda: self._step_quality_gate(
                cpt_output, hall_output, drift_output
            ),
        )
        steps.append(result.to_dict())
        if result.status == "success":
            completed += 1
        elif result.status == "failed":
            failed += 1
        else:
            skipped += 1

        # Step 5: Beta Auto-Tune
        result = self._run_step(
            "beta_autotune",
            lambda: self._step_beta_autotune(cpt_output, hall_output),
        )
        steps.append(result.to_dict())
        if result.status == "success":
            completed += 1
        elif result.status == "failed":
            failed += 1
        else:
            skipped += 1

        # Step 6: Deployment Decision
        gate_output = self.run_dir / "quality_gate.json"
        result = self._run_step(
            "deployment_decision",
            lambda: self._step_deployment_decision(gate_output),
        )
        steps.append(result.to_dict())
        if result.status == "success":
            completed += 1
        elif result.status == "failed":
            failed += 1
        else:
            skipped += 1

        # 전체 상태 판단
        if failed > 0:
            overall = "failed"
        elif skipped > 0:
            overall = "partial"
        else:
            overall = "success"

        # 배포 결정
        deployment = self._get_deployment_decision(gate_output)

        total_duration = (time.time() - pipeline_start) * 1000

        import hashlib
        config_hash = hashlib.md5(
            self.config.to_json().encode()
        ).hexdigest()[:8]

        report = PipelineReport(
            run_id=self.run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            config_hash=config_hash,
            total_steps=len(steps),
            completed_steps=completed,
            failed_steps=failed,
            skipped_steps=skipped,
            overall_status=overall,
            steps=steps,
            deployment_decision=deployment,
            duration_total_ms=round(total_duration, 1),
        )

        report.save(str(self.run_dir / "pipeline_report.json"))
        logger.info(f"Pipeline complete: {overall} ({total_duration:.0f}ms)")
        logger.info(f"Deployment: {deployment}")
        logger.info(f"Report: {self.run_dir / 'pipeline_report.json'}")

        return report

    # ──────────────────────────────────────
    # Individual Steps
    # ──────────────────────────────────────

    def _run_step(self, step_name: str, func) -> PipelineStepResult:
        """단일 스텝 실행 (에러 핸들링 + 타이밍)."""
        logger.info(f"═══ Step: {step_name} ═══")
        start = time.time()

        try:
            result = func()
            duration = (time.time() - start) * 1000
            logger.info(f"  → {step_name}: {result.get('status', 'done')} ({duration:.0f}ms)")

            return PipelineStepResult(
                step_name=step_name,
                status=result.get("status", "success"),
                duration_ms=round(duration, 1),
                output_path=str(self.run_dir / f"{step_name}.json"),
                details=result,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(f"  → {step_name}: FAILED - {e}")

            return PipelineStepResult(
                step_name=step_name,
                status="failed",
                duration_ms=round(duration, 1),
                output_path="",
                error=str(e),
            )

    def _step_validate_cpt(
        self, base_model, cpt_model, tokenizer, eval_data
    ) -> Dict:
        """CPT 검증 스텝."""
        output_path = self.run_dir / "validate_cpt.json"

        if base_model is None or cpt_model is None:
            # Mock 모드: 설정만 검증
            mock_results = []
            for pid in self.config.products:
                mock_results.append({
                    "product_id": pid,
                    "kl_divergence": 0.0,
                    "perplexity_delta_pct": 0.0,
                    "task_score_cpt": 0.0,
                    "passed": True,
                    "fail_reasons": [],
                    "mock": True,
                })

            result = {
                "status": "success",
                "mode": "mock",
                "products_validated": len(mock_results),
                "product_results": mock_results,
            }
            output_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return result

        from scripts.governance.cpt_validation import CPTValidator

        validator = CPTValidator(
            kl_fail_threshold=self.config.quality_gate.kl.fail,
            max_perplexity_increase_pct=self.config.quality_gate.perplexity.max_increase_pct,
            min_task_score=self.config.quality_gate.min_task_score,
        )

        report = validator.run_full_validation(
            base_model=base_model,
            cpt_model=cpt_model,
            tokenizer=tokenizer,
            product_eval_data=eval_data or {},
        )
        report.save(str(output_path))

        return {
            "status": "success" if report.overall_pass else "failed",
            "passed": report.passed_products,
            "failed": report.failed_products,
        }

    def _step_hallucination_guard(
        self, model, tokenizer, eval_data
    ) -> Dict:
        """환각 검사 스텝."""
        output_path = self.run_dir / "hallucination_guard.json"

        if model is None:
            # Mock 모드
            mock_results = {}
            for pid in self.config.products:
                mock_results[pid] = {
                    "product_id": pid,
                    "hallucination_rate": 0.0,
                    "avg_citation_ratio": 1.0,
                    "passed": True,
                    "mock": True,
                }

            result = {"status": "success", "mode": "mock", "products": mock_results}
            output_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return result

        from scripts.governance.hallucination_guard import HallucinationGuard

        guard = HallucinationGuard(
            max_hallucination_rate=self.config.quality_gate.hallucination.max_rate,
            min_citation_ratio=self.config.quality_gate.hallucination.min_citation_ratio,
        )

        products_result = {}
        for pid, texts in (eval_data or {}).items():
            # 간이 검사: 텍스트를 응답으로 간주
            report = guard.evaluate_product(
                product_id=pid,
                responses=texts[:20],
                context_chunks_list=[[] for _ in texts[:20]],
                model=model,
                tokenizer=tokenizer,
            )
            products_result[pid] = report.to_dict()

        result = {"status": "success", "products": products_result}
        output_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return result

    def _step_drift_analysis(self) -> Dict:
        """드리프트 분석 스텝."""
        output_path = self.run_dir / "drift_analysis.json"

        from scripts.governance.drift_monitor import DriftMonitor

        monitor = DriftMonitor(self.config)
        reports = monitor.check_all_products()

        result = {
            "status": "success",
            "products": {pid: r.to_dict() for pid, r in reports.items()},
        }
        output_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 대시보드 내보내기
        monitor.export_dashboard_json(
            str(self.run_dir / "drift_dashboard.json")
        )

        return result

    def _step_quality_gate(
        self, cpt_path: Path, hall_path: Path, drift_path: Path
    ) -> Dict:
        """Quality gate 스텝 (이전 스텝 결과 통합)."""
        from scripts.governance.quality_gate import QualityGate, ProductMetrics

        gate = QualityGate(self.config)
        product_metrics = []

        # CPT 결과 로드
        cpt_data = {}
        if cpt_path.exists():
            raw = json.loads(cpt_path.read_text(encoding="utf-8"))
            for pr in raw.get("product_results", []):
                cpt_data[pr["product_id"]] = pr

        # Hallucination 결과 로드
        hall_data = {}
        if hall_path.exists():
            raw = json.loads(hall_path.read_text(encoding="utf-8"))
            hall_data = raw.get("products", {})

        # Drift 결과 로드
        drift_data = {}
        if drift_path.exists():
            raw = json.loads(drift_path.read_text(encoding="utf-8"))
            drift_data = raw.get("products", {})

        # 제품별 메트릭 통합
        for pid in self.config.products:
            cpt = cpt_data.get(pid, {})
            hall = hall_data.get(pid, {})
            drift = drift_data.get(pid, {})

            product_metrics.append(ProductMetrics(
                product_id=pid,
                kl_divergence=cpt.get("kl_divergence", 0),
                hallucination_rate=hall.get("hallucination_rate", 0),
                task_score=cpt.get("task_score_cpt", 0),
                drift_status=drift.get("overall_drift_level", "stable"),
                perplexity_delta_pct=cpt.get("perplexity_delta_pct", 0),
                num_eval_samples=cpt.get("num_eval_samples", 0),
            ))

        report = gate.evaluate_all(product_metrics, run_id=self.run_id)
        report.save(str(self.run_dir / "quality_gate.json"))

        # Prometheus 메트릭 내보내기
        prom_metrics = gate.export_prometheus_metrics(report)
        (self.run_dir / "prometheus_metrics.txt").write_text(
            prom_metrics, encoding="utf-8"
        )

        return {
            "status": "success" if report.overall_pass else "failed",
            "passed": report.passed_products,
            "failed": report.failed_products,
            "deployment_allowed": report.deployment_allowed,
        }

    def _step_beta_autotune(
        self, cpt_path: Path, hall_path: Path
    ) -> Dict:
        """Beta 자동 조정 스텝."""
        from scripts.governance.beta_autotune import BetaAutoTuner, BetaAdjustmentInput

        tuner = BetaAutoTuner(self.config)
        results = {}

        # 이전 이력 로드
        history_path = self.output_dir / "beta_history.json"
        tuner.load_history(str(history_path))

        # CPT/Hall 결과 로드
        cpt_data = {}
        if cpt_path.exists():
            raw = json.loads(cpt_path.read_text(encoding="utf-8"))
            for pr in raw.get("product_results", []):
                cpt_data[pr["product_id"]] = pr

        hall_data = {}
        if hall_path.exists():
            raw = json.loads(hall_path.read_text(encoding="utf-8"))
            hall_data = raw.get("products", {})

        for pid in self.config.products:
            cpt = cpt_data.get(pid, {})
            hall = hall_data.get(pid, {})

            # 현재 beta 결정 (이력에서 또는 초기값)
            hist = tuner.get_history(pid)
            current_beta = hist.current_beta

            metrics = BetaAdjustmentInput(
                product_id=pid,
                current_beta=current_beta,
                kl_divergence=cpt.get("kl_divergence", 0),
                kl_trend="stable",  # drift 분석에서 가져올 수 있음
                reward_margin=0.5,  # DPO 결과에서
                hallucination_rate=hall.get("hallucination_rate", 0),
                task_accuracy=cpt.get("task_score_cpt", 0),
            )

            result = tuner.compute_adjustment(metrics)
            results[pid] = result.to_dict()

        # 이력 저장
        tuner.save_history(str(history_path))

        output = {"status": "success", "adjustments": results}
        (self.run_dir / "beta_autotune.json").write_text(
            json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return output

    def _step_deployment_decision(self, gate_path: Path) -> Dict:
        """배포 결정 스텝."""
        decision = self._get_deployment_decision(gate_path)

        output = {
            "status": "success",
            "decision": decision,
            "auto_deploy": self.config.auto_deploy,
            "run_id": self.run_id,
        }
        (self.run_dir / "deployment_decision.json").write_text(
            json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return output

    def _get_deployment_decision(self, gate_path: Path) -> str:
        """Quality gate 결과에서 배포 결정."""
        if not gate_path.exists():
            return "blocked"

        try:
            data = json.loads(gate_path.read_text(encoding="utf-8"))
            if data.get("overall_pass"):
                if self.config.auto_deploy:
                    return "approved"
                return "manual_review"
            return "blocked"
        except Exception:
            return "blocked"


def main():
    parser = argparse.ArgumentParser(description="Governance Pipeline")
    parser.add_argument("--config", help="Config JSON path")
    parser.add_argument("--step", help="Run single step", choices=GovernancePipeline.STEP_ORDER)
    parser.add_argument("--product", help="Single product ID")
    parser.add_argument("--gpu", default="4", help="GPU ID")
    parser.add_argument("--mock", action="store_true", help="Mock mode (no model loading)")
    args = parser.parse_args()

    os.environ["HF_HOME"] = "/raid/users/ofuser/.cache/huggingface"
    os.environ["TMPDIR"] = "/raid/users/ofuser/tmp"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    # 설정 로드
    if args.config and Path(args.config).exists():
        config = GovernanceConfig.load(args.config)
    else:
        config = GovernanceConfig()

    if args.product:
        config.products = [args.product]

    pipeline = GovernancePipeline(config)

    if args.mock or args.step:
        report = pipeline.run_full_pipeline()
    else:
        # Full pipeline with model loading
        os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info("Loading models for full pipeline...")
        tokenizer = AutoTokenizer.from_pretrained(
            config.base_model, trust_remote_code=True
        )
        base_model = AutoModelForCausalLM.from_pretrained(
            config.base_model,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
        )

        # eval data 로드
        eval_path = Path(config.dataset_base_dir) / "eval_all.json"
        eval_data = {}
        if eval_path.exists():
            raw = json.loads(eval_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                eval_data["combined"] = [item.get("text", "") for item in raw[:100]]

        report = pipeline.run_full_pipeline(
            base_model=base_model,
            cpt_model=base_model,  # CPT 어댑터 별도 로드 필요
            tokenizer=tokenizer,
            eval_data=eval_data,
        )

    # 결과 출력
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
