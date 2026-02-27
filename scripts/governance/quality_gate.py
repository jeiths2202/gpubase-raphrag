#!/usr/bin/env python3
"""
22-Product Unified Quality Gate.

Aggregates all governance metrics and enforces pass/fail for each product.
Stores results in SQLite (local) and exports Prometheus-compatible metrics.

Gate conditions per product:
    - KL divergence < threshold
    - Hallucination rate < 5%
    - Task score >= baseline
    - Drift score = stable

Usage:
    from scripts.governance.quality_gate import QualityGate
    gate = QualityGate(config)
    report = gate.evaluate_all(product_metrics)
"""

import json
import sqlite3
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from scripts.governance.governance_config import (
    GovernanceConfig,
    ApprovalStatus,
    StabilityStatus,
    ALL_PRODUCT_IDS,
)

logger = logging.getLogger(__name__)


@dataclass
class ProductGateResult:
    """단일 제품 quality gate 결과."""
    product_id: str
    # 입력 메트릭
    kl_divergence: float
    hallucination_rate: float
    task_score: float
    drift_status: str
    perplexity_delta_pct: float
    # 게이트 판정
    kl_pass: bool
    hallucination_pass: bool
    task_score_pass: bool
    drift_pass: bool
    perplexity_pass: bool
    # 종합
    overall_pass: bool
    approval_status: str
    fail_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class QualityGateReport:
    """전체 quality gate 리포트."""
    timestamp: str
    run_id: str
    total_products: int
    passed_products: int
    failed_products: int
    blocked_products: int
    overall_pass: bool
    product_results: List[Dict]
    summary_metrics: Dict
    deployment_allowed: bool

    def to_dict(self) -> Dict:
        return asdict(self)

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


@dataclass
class ProductMetrics:
    """Quality gate 입력용 제품 메트릭."""
    product_id: str
    kl_divergence: float = 0.0
    kl_std: float = 0.0
    hallucination_rate: float = 0.0
    task_score: float = 0.0
    drift_status: str = "stable"
    perplexity_delta_pct: float = 0.0
    num_eval_samples: int = 0


class QualityGate:
    """22개 제품 통합 Quality Gate."""

    def __init__(self, config: Optional[GovernanceConfig] = None):
        self.config = config or GovernanceConfig()
        self.qg = self.config.quality_gate
        self._db_initialized = False

    # ──────────────────────────────────────
    # Gate Evaluation
    # ──────────────────────────────────────

    def evaluate_product(self, metrics: ProductMetrics) -> ProductGateResult:
        """단일 제품 quality gate 평가."""
        fail_reasons = []
        warnings = []

        # 1. KL Divergence Gate
        kl_pass = metrics.kl_divergence < self.qg.kl.fail
        if not kl_pass:
            fail_reasons.append(
                f"KL={metrics.kl_divergence:.4f} >= {self.qg.kl.fail}"
            )
        elif metrics.kl_divergence > self.qg.kl.warn:
            warnings.append(
                f"KL={metrics.kl_divergence:.4f} approaching threshold"
            )

        # 2. Hallucination Gate
        hallucination_pass = metrics.hallucination_rate <= self.qg.hallucination.max_rate
        if not hallucination_pass:
            fail_reasons.append(
                f"Hallucination={metrics.hallucination_rate:.1%} > {self.qg.hallucination.max_rate:.1%}"
            )

        # 3. Task Score Gate
        task_pass = metrics.task_score >= self.qg.min_task_score
        if not task_pass:
            fail_reasons.append(
                f"Task score={metrics.task_score:.3f} < {self.qg.min_task_score}"
            )

        # 4. Drift Gate
        drift_pass = metrics.drift_status in ("stable", "none")
        if not drift_pass:
            fail_reasons.append(f"Drift status={metrics.drift_status}")

        # 5. Perplexity Gate
        ppl_pass = metrics.perplexity_delta_pct <= self.qg.perplexity.max_increase_pct
        if not ppl_pass:
            fail_reasons.append(
                f"Perplexity increased {metrics.perplexity_delta_pct:.1f}%"
            )
        elif metrics.perplexity_delta_pct > self.qg.perplexity.warn_increase_pct:
            warnings.append(f"Perplexity increased {metrics.perplexity_delta_pct:.1f}%")

        overall = kl_pass and hallucination_pass and task_pass and drift_pass and ppl_pass

        # 최소 평가 샘플 체크
        if metrics.num_eval_samples < self.qg.min_eval_samples:
            overall = False
            fail_reasons.append(
                f"Insufficient eval samples: {metrics.num_eval_samples} < {self.qg.min_eval_samples}"
            )

        approval = ApprovalStatus.APPROVED if overall else ApprovalStatus.BLOCKED

        return ProductGateResult(
            product_id=metrics.product_id,
            kl_divergence=metrics.kl_divergence,
            hallucination_rate=metrics.hallucination_rate,
            task_score=metrics.task_score,
            drift_status=metrics.drift_status,
            perplexity_delta_pct=metrics.perplexity_delta_pct,
            kl_pass=kl_pass,
            hallucination_pass=hallucination_pass,
            task_score_pass=task_pass,
            drift_pass=drift_pass,
            perplexity_pass=ppl_pass,
            overall_pass=overall,
            approval_status=approval.value,
            fail_reasons=fail_reasons,
            warnings=warnings,
        )

    def evaluate_all(
        self,
        product_metrics: List[ProductMetrics],
        run_id: Optional[str] = None,
    ) -> QualityGateReport:
        """
        전체 22개 제품에 대한 quality gate 평가.

        Args:
            product_metrics: 각 제품의 메트릭 리스트
            run_id: 실행 ID (CI/CD 연동용)
        """
        if run_id is None:
            run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")

        results = []
        passed = 0
        failed = 0
        blocked = 0

        # 누락된 제품 체크
        submitted_ids = {m.product_id for m in product_metrics}
        missing_ids = set(ALL_PRODUCT_IDS) - submitted_ids

        for metrics in product_metrics:
            result = self.evaluate_product(metrics)
            results.append(result.to_dict())

            if result.overall_pass:
                passed += 1
            else:
                failed += 1
                if result.approval_status == ApprovalStatus.BLOCKED.value:
                    blocked += 1

            logger.info(
                f"{'✓' if result.overall_pass else '✗'} "
                f"{metrics.product_id}: "
                f"KL={metrics.kl_divergence:.4f} "
                f"Hall={metrics.hallucination_rate:.1%} "
                f"Task={metrics.task_score:.3f} "
                f"Drift={metrics.drift_status}"
            )

        # 누락 제품 처리
        for pid in missing_ids:
            results.append(ProductGateResult(
                product_id=pid,
                kl_divergence=0, hallucination_rate=0, task_score=0,
                drift_status="unknown", perplexity_delta_pct=0,
                kl_pass=False, hallucination_pass=False,
                task_score_pass=False, drift_pass=False, perplexity_pass=False,
                overall_pass=False,
                approval_status=ApprovalStatus.BLOCKED.value,
                fail_reasons=["Product not evaluated"],
            ).to_dict())
            failed += 1
            blocked += 1

        total = passed + failed

        # 전체 통과 조건
        if self.config.quality_gate.require_all_products_pass:
            overall_pass = failed == 0
        else:
            overall_pass = passed / total >= 0.8 if total > 0 else False

        deployment_allowed = overall_pass and not self.config.auto_deploy

        # 요약 메트릭
        all_kl = [m.kl_divergence for m in product_metrics]
        all_hall = [m.hallucination_rate for m in product_metrics]
        all_task = [m.task_score for m in product_metrics]

        summary = {
            "pass_rate": passed / total if total > 0 else 0,
            "avg_kl": sum(all_kl) / len(all_kl) if all_kl else 0,
            "max_kl": max(all_kl) if all_kl else 0,
            "avg_hallucination_rate": sum(all_hall) / len(all_hall) if all_hall else 0,
            "avg_task_score": sum(all_task) / len(all_task) if all_task else 0,
            "missing_products": list(missing_ids),
        }

        report = QualityGateReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=run_id,
            total_products=total,
            passed_products=passed,
            failed_products=failed,
            blocked_products=blocked,
            overall_pass=overall_pass,
            product_results=results,
            summary_metrics=summary,
            deployment_allowed=deployment_allowed,
        )

        # DB 저장
        self._store_to_db(report)

        return report

    # ──────────────────────────────────────
    # Database Storage
    # ──────────────────────────────────────

    def _init_db(self):
        """SQLite DB 초기화."""
        if self._db_initialized:
            return

        db_path = Path(self.config.metrics_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quality_gate_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                total_products INTEGER,
                passed_products INTEGER,
                failed_products INTEGER,
                overall_pass BOOLEAN,
                deployment_allowed BOOLEAN,
                summary_json TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_gate_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                kl_divergence REAL,
                hallucination_rate REAL,
                task_score REAL,
                drift_status TEXT,
                perplexity_delta_pct REAL,
                overall_pass BOOLEAN,
                approval_status TEXT,
                fail_reasons_json TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES quality_gate_runs(run_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_product_results_run
            ON product_gate_results(run_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_product_results_product
            ON product_gate_results(product_id)
        """)

        conn.commit()
        conn.close()
        self._db_initialized = True

    def _store_to_db(self, report: QualityGateReport):
        """리포트를 DB에 저장."""
        try:
            self._init_db()
            conn = sqlite3.connect(str(self.config.metrics_db_path))
            cursor = conn.cursor()

            # 실행 기록
            cursor.execute("""
                INSERT OR REPLACE INTO quality_gate_runs
                (run_id, timestamp, total_products, passed_products,
                 failed_products, overall_pass, deployment_allowed, summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report.run_id,
                report.timestamp,
                report.total_products,
                report.passed_products,
                report.failed_products,
                report.overall_pass,
                report.deployment_allowed,
                json.dumps(report.summary_metrics, ensure_ascii=False),
            ))

            # 제품별 결과
            for pr in report.product_results:
                cursor.execute("""
                    INSERT INTO product_gate_results
                    (run_id, product_id, kl_divergence, hallucination_rate,
                     task_score, drift_status, perplexity_delta_pct,
                     overall_pass, approval_status, fail_reasons_json, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    report.run_id,
                    pr["product_id"],
                    pr["kl_divergence"],
                    pr["hallucination_rate"],
                    pr["task_score"],
                    pr["drift_status"],
                    pr["perplexity_delta_pct"],
                    pr["overall_pass"],
                    pr["approval_status"],
                    json.dumps(pr.get("fail_reasons", []), ensure_ascii=False),
                    report.timestamp,
                ))

            conn.commit()
            conn.close()
            logger.info(f"Quality gate results stored to DB (run_id={report.run_id})")
        except Exception as e:
            logger.error(f"Failed to store to DB: {e}")

    # ──────────────────────────────────────
    # Prometheus Metrics Export
    # ──────────────────────────────────────

    def export_prometheus_metrics(self, report: QualityGateReport) -> str:
        """Prometheus exposition format으로 메트릭 내보내기."""
        lines = [
            "# HELP governance_quality_gate_pass Quality gate pass status (1=pass, 0=fail)",
            "# TYPE governance_quality_gate_pass gauge",
            f'governance_quality_gate_pass{{run_id="{report.run_id}"}} '
            f'{1 if report.overall_pass else 0}',
            "",
            "# HELP governance_products_passed Number of products that passed quality gate",
            "# TYPE governance_products_passed gauge",
            f'governance_products_passed{{run_id="{report.run_id}"}} {report.passed_products}',
            "",
            "# HELP governance_products_failed Number of products that failed quality gate",
            "# TYPE governance_products_failed gauge",
            f'governance_products_failed{{run_id="{report.run_id}"}} {report.failed_products}',
            "",
            "# HELP governance_kl_divergence KL divergence per product",
            "# TYPE governance_kl_divergence gauge",
        ]

        for pr in report.product_results:
            pid = pr["product_id"]
            lines.append(
                f'governance_kl_divergence{{product="{pid}",run_id="{report.run_id}"}} '
                f'{pr["kl_divergence"]:.6f}'
            )

        lines.extend([
            "",
            "# HELP governance_hallucination_rate Hallucination rate per product",
            "# TYPE governance_hallucination_rate gauge",
        ])

        for pr in report.product_results:
            pid = pr["product_id"]
            lines.append(
                f'governance_hallucination_rate{{product="{pid}",run_id="{report.run_id}"}} '
                f'{pr["hallucination_rate"]:.6f}'
            )

        lines.extend([
            "",
            "# HELP governance_task_score Task score per product",
            "# TYPE governance_task_score gauge",
        ])

        for pr in report.product_results:
            pid = pr["product_id"]
            lines.append(
                f'governance_task_score{{product="{pid}",run_id="{report.run_id}"}} '
                f'{pr["task_score"]:.6f}'
            )

        return "\n".join(lines) + "\n"

    # ──────────────────────────────────────
    # History Query
    # ──────────────────────────────────────

    def get_history(
        self, product_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict]:
        """DB에서 이력 조회."""
        try:
            self._init_db()
            conn = sqlite3.connect(str(self.config.metrics_db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if product_id:
                cursor.execute("""
                    SELECT * FROM product_gate_results
                    WHERE product_id = ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (product_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM quality_gate_runs
                    ORDER BY timestamp DESC LIMIT ?
                """, (limit,))

            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.error(f"Failed to query history: {e}")
            return []
