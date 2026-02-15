#!/usr/bin/env python3
"""
DPO Beta Auto-Tuning Algorithm.

Dynamically adjusts DPO beta parameter to prevent:
- Over-alignment (too high beta → diversity collapse)
- Under-alignment (too low beta → hallucination)
- KL explosion

Inputs:
    - KL divergence trend
    - Reward margin
    - Hallucination rate
    - Task accuracy

Logic:
    - KL rising    → decrease beta (loosen constraint)
    - KL too low   → increase beta (tighten alignment)
    - Hallucination rises → decrease beta
    - Task accuracy drops → increase beta carefully

Usage:
    from scripts.governance.beta_autotune import BetaAutoTuner
    tuner = BetaAutoTuner(config)
    result = tuner.compute_adjustment(current_metrics, history)
"""

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from scripts.governance.governance_config import GovernanceConfig, BetaTuningConfig

logger = logging.getLogger(__name__)


@dataclass
class BetaAdjustmentInput:
    """Beta 조정을 위한 입력 메트릭."""
    product_id: str
    current_beta: float
    kl_divergence: float
    kl_trend: str           # "increasing", "decreasing", "stable"
    reward_margin: float
    hallucination_rate: float
    task_accuracy: float
    epoch: int = 0


@dataclass
class BetaAdjustmentResult:
    """Beta 조정 결과."""
    product_id: str
    beta_old: float
    beta_new: float
    adjustment: float       # delta (양수 = 증가, 음수 = 감소)
    reason: str
    signals: Dict           # 각 신호의 기여도
    confidence: float       # 조정 신뢰도 (0~1)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class BetaTuningHistory:
    """Beta 조정 이력."""
    product_id: str
    adjustments: List[Dict]
    current_beta: float
    total_adjustments: int
    avg_adjustment: float
    trend: str

    def to_dict(self) -> Dict:
        return asdict(self)


class BetaAutoTuner:
    """DPO Beta 자동 조정 엔진."""

    def __init__(self, config: Optional[GovernanceConfig] = None):
        self.config = config or GovernanceConfig()
        self.bt = self.config.quality_gate.beta_tuning
        self._history: Dict[str, List[BetaAdjustmentResult]] = {}

    def compute_adjustment(
        self, metrics: BetaAdjustmentInput
    ) -> BetaAdjustmentResult:
        """
        현재 메트릭 기반 beta 조정값 계산.

        조정 로직:
        1. KL Signal: KL > target → beta 감소, KL < target*0.5 → beta 증가
        2. Hallucination Signal: rate 상승 → beta 감소
        3. Reward Signal: margin 부족 → beta 증가
        4. Task Signal: accuracy 하락 → beta 소폭 증가
        """
        signals = {}
        adjustments = []

        # ── Signal 1: KL Divergence ──
        kl_signal = self._kl_signal(
            metrics.kl_divergence, metrics.kl_trend
        )
        signals["kl"] = {"value": kl_signal, "input": metrics.kl_divergence}
        adjustments.append(kl_signal)

        # ── Signal 2: Hallucination Rate ──
        hall_signal = self._hallucination_signal(metrics.hallucination_rate)
        signals["hallucination"] = {"value": hall_signal, "input": metrics.hallucination_rate}
        adjustments.append(hall_signal)

        # ── Signal 3: Reward Margin ──
        reward_signal = self._reward_signal(metrics.reward_margin)
        signals["reward_margin"] = {"value": reward_signal, "input": metrics.reward_margin}
        adjustments.append(reward_signal)

        # ── Signal 4: Task Accuracy ──
        task_signal = self._task_accuracy_signal(metrics.task_accuracy)
        signals["task_accuracy"] = {"value": task_signal, "input": metrics.task_accuracy}
        adjustments.append(task_signal)

        # 가중 평균 조정값 (KL이 가장 중요)
        weights = [0.4, 0.25, 0.2, 0.15]
        weighted_adjustment = sum(a * w for a, w in zip(adjustments, weights))

        # 스텝 크기 제한
        clamped = max(-self.bt.adjustment_step, min(self.bt.adjustment_step, weighted_adjustment))

        # 새 beta 범위 제한
        new_beta = max(
            self.bt.min_beta,
            min(self.bt.max_beta, metrics.current_beta + clamped),
        )

        # 조정 이유 생성
        reason = self._generate_reason(signals, clamped)

        # 신뢰도 계산 (신호 일치도 기반)
        sign_agreement = sum(
            1 for a in adjustments if (a > 0) == (weighted_adjustment > 0)
        )
        confidence = sign_agreement / len(adjustments) if adjustments else 0.5

        result = BetaAdjustmentResult(
            product_id=metrics.product_id,
            beta_old=metrics.current_beta,
            beta_new=round(new_beta, 4),
            adjustment=round(new_beta - metrics.current_beta, 4),
            reason=reason,
            signals=signals,
            confidence=confidence,
        )

        # 이력 저장
        self._history.setdefault(metrics.product_id, []).append(result)

        return result

    # ──────────────────────────────────────
    # Signal Functions
    # ──────────────────────────────────────

    def _kl_signal(self, kl: float, trend: str) -> float:
        """
        KL 기반 신호.
        - KL 상승 → beta 감소 (제약 완화하여 KL 하강 유도)
        - KL 과도하게 낮음 → beta 증가 (정렬 강화)
        """
        target = self.bt.kl_target
        step = self.bt.adjustment_step

        if kl > target * 1.5:
            # KL 폭주 → 강하게 감소
            signal = -step * 1.5
        elif kl > target:
            # KL 초과 → 감소
            overshoot = (kl - target) / target
            signal = -step * min(1.0, overshoot)
        elif kl < target * 0.3:
            # KL 과도하게 낮음 → 증가 (정렬 부족)
            signal = step * 0.5
        else:
            signal = 0.0

        # 추세 가중
        if trend == "increasing" and signal <= 0:
            signal *= 1.3  # 증가 추세에서 감소 강화
        elif trend == "decreasing" and signal >= 0:
            signal *= 0.7  # 감소 추세에서 증가 약화

        return signal

    def _hallucination_signal(self, rate: float) -> float:
        """
        환각률 기반 신호.
        - 환각 증가 → beta 감소 (KL 제약 완화 → 모델이 더 보수적)
        """
        max_rate = self.config.quality_gate.hallucination.max_rate
        step = self.bt.adjustment_step

        if rate > max_rate * 2:
            return -step * 1.5
        elif rate > max_rate:
            excess = (rate - max_rate) / max_rate
            return -step * min(1.0, excess)
        elif rate < max_rate * 0.5:
            # 매우 낮은 환각률 → beta 소폭 증가 가능
            return step * 0.2
        return 0.0

    def _reward_signal(self, margin: float) -> float:
        """
        보상 마진 기반 신호.
        - 마진 부족 → beta 증가 (선호 학습 강화)
        """
        min_margin = self.bt.reward_margin_min
        step = self.bt.adjustment_step

        if margin < min_margin * 0.5:
            return step * 1.0
        elif margin < min_margin:
            deficit = (min_margin - margin) / min_margin
            return step * min(1.0, deficit)
        return 0.0

    def _task_accuracy_signal(self, accuracy: float) -> float:
        """
        태스크 정확도 기반 신호.
        - 정확도 하락 → beta 소폭 증가
        """
        min_score = self.config.quality_gate.min_task_score
        step = self.bt.adjustment_step

        if accuracy < min_score:
            deficit = (min_score - accuracy) / min_score
            return step * min(0.5, deficit)
        return 0.0

    # ──────────────────────────────────────
    # Reason & History
    # ──────────────────────────────────────

    def _generate_reason(self, signals: Dict, adjustment: float) -> str:
        """조정 이유 문자열 생성."""
        dominant = max(signals.items(), key=lambda x: abs(x[1]["value"]))
        direction = "increased" if adjustment > 0 else "decreased"

        reasons = []
        if abs(signals["kl"]["value"]) > 0.001:
            kl_val = signals["kl"]["input"]
            reasons.append(f"KL={kl_val:.3f}")
        if abs(signals["hallucination"]["value"]) > 0.001:
            reasons.append(f"Hallucination={signals['hallucination']['input']:.1%}")
        if abs(signals["reward_margin"]["value"]) > 0.001:
            reasons.append(f"Reward margin={signals['reward_margin']['input']:.3f}")
        if abs(signals["task_accuracy"]["value"]) > 0.001:
            reasons.append(f"Task accuracy={signals['task_accuracy']['input']:.3f}")

        reason_str = ", ".join(reasons) if reasons else "No significant signals"
        return f"Beta {direction} (dominant: {dominant[0]}). Signals: {reason_str}"

    def get_history(self, product_id: str) -> BetaTuningHistory:
        """제품별 beta 조정 이력 조회."""
        history = self._history.get(product_id, [])

        if not history:
            return BetaTuningHistory(
                product_id=product_id,
                adjustments=[],
                current_beta=self.bt.initial_beta,
                total_adjustments=0,
                avg_adjustment=0.0,
                trend="stable",
            )

        adjustments_list = [r.to_dict() for r in history]
        adj_values = [r.adjustment for r in history]
        avg_adj = sum(adj_values) / len(adj_values)

        # 추세 판단
        if len(adj_values) >= 3:
            recent = adj_values[-3:]
            if all(a > 0 for a in recent):
                trend = "increasing"
            elif all(a < 0 for a in recent):
                trend = "decreasing"
            else:
                trend = "oscillating"
        else:
            trend = "stable"

        return BetaTuningHistory(
            product_id=product_id,
            adjustments=adjustments_list,
            current_beta=history[-1].beta_new,
            total_adjustments=len(history),
            avg_adjustment=avg_adj,
            trend=trend,
        )

    def save_history(self, output_path: str):
        """전체 조정 이력을 JSON으로 저장."""
        data = {}
        for product_id in self._history:
            data[product_id] = self.get_history(product_id).to_dict()

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_history(self, input_path: str):
        """이전 세션의 이력 로드."""
        path = Path(input_path)
        if not path.exists():
            return

        data = json.loads(path.read_text(encoding="utf-8"))
        for product_id, hist in data.items():
            for adj in hist.get("adjustments", []):
                result = BetaAdjustmentResult(**{
                    k: v for k, v in adj.items()
                    if k in BetaAdjustmentResult.__dataclass_fields__
                })
                self._history.setdefault(product_id, []).append(result)
