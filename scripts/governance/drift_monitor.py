#!/usr/bin/env python3
"""
Drift Detection & Dashboard Monitor.

Tracks model quality drift over time using:
- KL divergence trend
- Hallucination rate trend
- Token entropy shift
- Embedding cosine similarity shift

Detection methods:
- Z-score deviation (> 2σ warning, > 3σ critical)
- Moving average anomaly
- Trend regression

Exports Grafana-compatible JSON dashboard config and metrics endpoint.

Usage:
    from scripts.governance.drift_monitor import DriftMonitor
    monitor = DriftMonitor(config)
    monitor.record_metrics(run_id, product_id, metrics)
    alert = monitor.check_drift(product_id)
"""

import json
import math
import sqlite3
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from scripts.governance.governance_config import (
    GovernanceConfig,
    DriftLevel,
    DriftThresholds,
    ALL_PRODUCT_IDS,
)

logger = logging.getLogger(__name__)


@dataclass
class DriftMetricPoint:
    """단일 시점의 drift 메트릭."""
    timestamp: str
    run_id: str
    product_id: str
    kl_divergence: float
    hallucination_rate: float
    token_entropy: float
    embedding_cosine_shift: float
    perplexity: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DriftAlert:
    """Drift 탐지 알림."""
    product_id: str
    metric_name: str
    current_value: float
    mean_value: float
    std_value: float
    z_score: float
    drift_level: str
    moving_avg: float
    trend_direction: str    # "increasing", "decreasing", "stable"
    message: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ProductDriftReport:
    """제품별 drift 분석 결과."""
    product_id: str
    overall_drift_level: str
    alerts: List[Dict]
    metric_trends: Dict[str, Dict]   # {metric_name: {trend, z_score, ...}}
    history_length: int
    recommendation: str

    def to_dict(self) -> Dict:
        return asdict(self)


class DriftMonitor:
    """Drift 탐지 및 모니터링 시스템."""

    METRIC_NAMES = [
        "kl_divergence",
        "hallucination_rate",
        "token_entropy",
        "embedding_cosine_shift",
        "perplexity",
    ]

    def __init__(self, config: Optional[GovernanceConfig] = None):
        self.config = config or GovernanceConfig()
        self.thresholds = self.config.quality_gate.drift
        self._db_initialized = False

    # ──────────────────────────────────────
    # Data Recording
    # ──────────────────────────────────────

    def record_metrics(self, point: DriftMetricPoint):
        """메트릭 포인트를 DB에 기록."""
        self._init_db()
        conn = sqlite3.connect(str(self.config.metrics_db_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO drift_metrics
            (timestamp, run_id, product_id, kl_divergence,
             hallucination_rate, token_entropy, embedding_cosine_shift, perplexity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            point.timestamp, point.run_id, point.product_id,
            point.kl_divergence, point.hallucination_rate,
            point.token_entropy, point.embedding_cosine_shift,
            point.perplexity,
        ))

        conn.commit()
        conn.close()

    def get_history(
        self, product_id: str, limit: int = 100
    ) -> List[DriftMetricPoint]:
        """제품별 메트릭 이력 조회."""
        self._init_db()
        conn = sqlite3.connect(str(self.config.metrics_db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM drift_metrics
            WHERE product_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
        """, (product_id, limit))

        points = [
            DriftMetricPoint(**{k: row[k] for k in DriftMetricPoint.__dataclass_fields__})
            for row in cursor.fetchall()
        ]
        conn.close()
        return points

    # ──────────────────────────────────────
    # Drift Detection
    # ──────────────────────────────────────

    def check_drift(self, product_id: str) -> ProductDriftReport:
        """
        특정 제품의 drift 상태 분석.

        Returns:
            ProductDriftReport
        """
        history = self.get_history(product_id)

        if len(history) < self.thresholds.min_history_points:
            return ProductDriftReport(
                product_id=product_id,
                overall_drift_level=DriftLevel.NONE.value,
                alerts=[],
                metric_trends={},
                history_length=len(history),
                recommendation=f"Insufficient data ({len(history)} points, "
                               f"need {self.thresholds.min_history_points})",
            )

        alerts = []
        metric_trends = {}
        max_drift_level = DriftLevel.NONE

        for metric_name in self.METRIC_NAMES:
            values = [getattr(p, metric_name) for p in history]

            # Z-score 분석
            z_result = self._compute_z_score(values)
            # Moving average
            ma = self._compute_moving_average(
                values, self.thresholds.moving_avg_window
            )
            # Trend
            trend = self._detect_trend(values)

            metric_trends[metric_name] = {
                "current": values[-1] if values else 0,
                "mean": z_result["mean"],
                "std": z_result["std"],
                "z_score": z_result["z_score"],
                "moving_avg": ma[-1] if ma else 0,
                "trend": trend,
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
            }

            # 알림 판정
            drift_level = self._classify_drift(z_result["z_score"])

            if drift_level.value in (DriftLevel.MEDIUM.value,
                                      DriftLevel.HIGH.value,
                                      DriftLevel.CRITICAL.value):
                alert = DriftAlert(
                    product_id=product_id,
                    metric_name=metric_name,
                    current_value=values[-1],
                    mean_value=z_result["mean"],
                    std_value=z_result["std"],
                    z_score=z_result["z_score"],
                    drift_level=drift_level.value,
                    moving_avg=ma[-1] if ma else 0,
                    trend_direction=trend,
                    message=self._format_alert_message(
                        product_id, metric_name, z_result["z_score"], drift_level
                    ),
                )
                alerts.append(alert.to_dict())

            # 최고 drift level 추적
            drift_order = [
                DriftLevel.NONE, DriftLevel.LOW, DriftLevel.MEDIUM,
                DriftLevel.HIGH, DriftLevel.CRITICAL,
            ]
            if drift_order.index(drift_level) > drift_order.index(max_drift_level):
                max_drift_level = drift_level

        recommendation = self._generate_recommendation(max_drift_level, alerts)

        return ProductDriftReport(
            product_id=product_id,
            overall_drift_level=max_drift_level.value,
            alerts=alerts,
            metric_trends=metric_trends,
            history_length=len(history),
            recommendation=recommendation,
        )

    def check_all_products(self) -> Dict[str, ProductDriftReport]:
        """전체 22개 제품 drift 분석."""
        results = {}
        for product_id in ALL_PRODUCT_IDS:
            results[product_id] = self.check_drift(product_id)
        return results

    # ──────────────────────────────────────
    # Statistical Methods
    # ──────────────────────────────────────

    def _compute_z_score(self, values: List[float]) -> Dict:
        """최근 값의 z-score 계산."""
        if len(values) < 2:
            return {"z_score": 0.0, "mean": values[0] if values else 0, "std": 0.0}

        # 최근 값 제외한 historical 통계
        historical = values[:-1]
        mean = sum(historical) / len(historical)
        variance = sum((x - mean) ** 2 for x in historical) / len(historical)
        std = math.sqrt(variance) if variance > 0 else 1e-8

        current = values[-1]
        z_score = abs(current - mean) / std

        return {"z_score": z_score, "mean": mean, "std": std}

    def _compute_moving_average(
        self, values: List[float], window: int
    ) -> List[float]:
        """이동 평균 계산."""
        if len(values) < window:
            window = len(values)
        if window == 0:
            return []

        result = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            chunk = values[start:i + 1]
            result.append(sum(chunk) / len(chunk))
        return result

    def _detect_trend(self, values: List[float]) -> str:
        """단순 선형 회귀로 추세 탐지."""
        if len(values) < 3:
            return "stable"

        n = len(values)
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n

        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return "stable"

        slope = numerator / denominator

        # 상대적 기울기로 판단
        relative_slope = slope / (y_mean + 1e-8)

        if relative_slope > 0.05:
            return "increasing"
        elif relative_slope < -0.05:
            return "decreasing"
        return "stable"

    def _classify_drift(self, z_score: float) -> DriftLevel:
        """Z-score 기반 drift 수준 분류."""
        if z_score >= self.thresholds.z_score_critical:
            return DriftLevel.CRITICAL
        elif z_score >= self.thresholds.z_score_warn + 0.5:
            return DriftLevel.HIGH
        elif z_score >= self.thresholds.z_score_warn:
            return DriftLevel.MEDIUM
        elif z_score >= 1.0:
            return DriftLevel.LOW
        return DriftLevel.NONE

    def _format_alert_message(
        self, product_id: str, metric: str, z_score: float, level: DriftLevel
    ) -> str:
        return (
            f"[{level.value.upper()}] {product_id}/{metric}: "
            f"z-score={z_score:.2f} exceeds threshold"
        )

    def _generate_recommendation(
        self, level: DriftLevel, alerts: List[Dict]
    ) -> str:
        if level == DriftLevel.CRITICAL:
            return "CRITICAL drift detected. Halt deployment and retrain immediately."
        elif level == DriftLevel.HIGH:
            return "High drift detected. Review adapter and consider retraining."
        elif level == DriftLevel.MEDIUM:
            return "Moderate drift detected. Monitor closely and schedule review."
        elif level == DriftLevel.LOW:
            return "Minor drift within acceptable range. Continue monitoring."
        return "No significant drift detected."

    # ──────────────────────────────────────
    # Dashboard Export
    # ──────────────────────────────────────

    def export_dashboard_json(self, output_path: str):
        """Grafana 호환 대시보드 JSON 내보내기."""
        panels = []
        panel_id = 1

        for metric in self.METRIC_NAMES:
            panels.append({
                "id": panel_id,
                "type": "timeseries",
                "title": f"{metric.replace('_', ' ').title()} Over Time",
                "datasource": "SQLite",
                "targets": [{
                    "rawSql": (
                        f"SELECT timestamp as time, {metric} as value, product_id "
                        f"FROM drift_metrics "
                        f"ORDER BY timestamp ASC"
                    ),
                    "format": "time_series",
                }],
                "fieldConfig": {
                    "defaults": {
                        "thresholds": {
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "yellow", "value": self.thresholds.z_score_warn},
                                {"color": "red", "value": self.thresholds.z_score_critical},
                            ]
                        }
                    }
                },
                "gridPos": {"h": 8, "w": 12, "x": 0 if panel_id % 2 == 1 else 12, "y": ((panel_id - 1) // 2) * 8},
            })
            panel_id += 1

        # Alert Overview Panel
        panels.append({
            "id": panel_id,
            "type": "table",
            "title": "Active Drift Alerts",
            "datasource": "SQLite",
            "targets": [{
                "rawSql": (
                    "SELECT product_id, kl_divergence, hallucination_rate, "
                    "token_entropy, embedding_cosine_shift, timestamp "
                    "FROM drift_metrics "
                    "ORDER BY timestamp DESC LIMIT 22"
                ),
                "format": "table",
            }],
            "gridPos": {"h": 10, "w": 24, "x": 0, "y": ((panel_id - 1) // 2) * 8},
        })

        dashboard = {
            "dashboard": {
                "id": None,
                "uid": "lora-governance-drift",
                "title": "LoRA Governance - Drift Dashboard",
                "tags": ["governance", "drift", "lora"],
                "timezone": "utc",
                "refresh": "5m",
                "panels": panels,
                "time": {"from": "now-30d", "to": "now"},
                "version": 1,
            },
            "overwrite": True,
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(dashboard, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"Dashboard config exported to {output_path}")

    def export_metrics_json(self, output_path: str):
        """전체 제품 drift 상태를 JSON으로 내보내기 (API 엔드포인트용)."""
        reports = self.check_all_products()
        export_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "products": {pid: r.to_dict() for pid, r in reports.items()},
            "summary": {
                "total_products": len(reports),
                "critical": sum(
                    1 for r in reports.values()
                    if r.overall_drift_level == DriftLevel.CRITICAL.value
                ),
                "high": sum(
                    1 for r in reports.values()
                    if r.overall_drift_level == DriftLevel.HIGH.value
                ),
                "medium": sum(
                    1 for r in reports.values()
                    if r.overall_drift_level == DriftLevel.MEDIUM.value
                ),
                "stable": sum(
                    1 for r in reports.values()
                    if r.overall_drift_level in (
                        DriftLevel.NONE.value, DriftLevel.LOW.value
                    )
                ),
            },
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(export_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ──────────────────────────────────────
    # DB Setup
    # ──────────────────────────────────────

    def _init_db(self):
        if self._db_initialized:
            return

        db_path = Path(self.config.metrics_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drift_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                run_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                kl_divergence REAL,
                hallucination_rate REAL,
                token_entropy REAL,
                embedding_cosine_shift REAL,
                perplexity REAL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_drift_product_time
            ON drift_metrics(product_id, timestamp)
        """)

        conn.commit()
        conn.close()
        self._db_initialized = True
