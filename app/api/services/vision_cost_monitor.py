"""
Vision Cost Monitor

Tracks and monitors Vision LLM API costs with budget alerts,
usage analytics, and cost optimization recommendations.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


class CostAlertLevel(str, Enum):
    """Cost alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass
class TokenUsage:
    """Token usage for a single request"""
    input_tokens: int = 0
    output_tokens: int = 0
    image_tokens: int = 0  # Estimated tokens for images
    total_tokens: int = 0

    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens + self.image_tokens


@dataclass
class CostRecord:
    """Record of a single API call cost"""
    timestamp: datetime
    provider: str
    model: str
    token_usage: TokenUsage
    estimated_cost: float
    request_type: str  # query, analyze, batch
    user_id: Optional[str] = None
    document_id: Optional[str] = None
    success: bool = True
    latency_ms: float = 0.0


@dataclass
class BudgetConfig:
    """Budget configuration"""
    monthly_budget: float = 1000.0  # USD
    daily_budget: Optional[float] = None  # Auto-calculated if None
    hourly_budget: Optional[float] = None
    warning_threshold: float = 0.8  # 80% of budget
    critical_threshold: float = 0.95  # 95% of budget
    per_user_daily_limit: Optional[float] = None
    per_request_max: float = 5.0  # Max cost per single request

    def __post_init__(self):
        if self.daily_budget is None:
            self.daily_budget = self.monthly_budget / 30
        if self.hourly_budget is None:
            self.hourly_budget = self.daily_budget / 24


@dataclass
class UsageStats:
    """Usage statistics for a time period"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_cost: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_image_tokens: int = 0
    avg_latency_ms: float = 0.0
    by_provider: Dict[str, float] = field(default_factory=dict)
    by_model: Dict[str, float] = field(default_factory=dict)
    by_user: Dict[str, float] = field(default_factory=dict)


class VisionCostMonitor:
    """
    Monitors Vision LLM API costs and usage.

    Features:
    1. Real-time cost tracking per provider/model
    2. Budget alerts and enforcement
    3. Usage analytics and reporting
    4. Cost optimization recommendations
    5. Per-user usage limits

    Pricing (as of 2024):
    - GPT-4o: $2.50/1M input, $10.00/1M output
    - GPT-4o-mini: $0.15/1M input, $0.60/1M output
    - Claude 3.5 Sonnet: $3.00/1M input, $15.00/1M output
    - Claude 3 Haiku: $0.25/1M input, $1.25/1M output

    Usage:
        monitor = VisionCostMonitor(monthly_budget=500.0)

        # Record usage
        monitor.record_usage(
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            image_tokens=2000,
        )

        # Check budget
        status = monitor.get_budget_status()
        if status.alert_level == CostAlertLevel.WARNING:
            print("Budget warning!")
    """

    # Pricing per 1M tokens (USD)
    PRICING = {
        "openai": {
            "gpt-4o": {"input": 2.50, "output": 10.00, "image_base": 0.00255},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60, "image_base": 0.0001275},
            "gpt-4-turbo": {"input": 10.00, "output": 30.00, "image_base": 0.00765},
        },
        "anthropic": {
            "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00, "image_base": 0.0048},
            "claude-3-opus-20240229": {"input": 15.00, "output": 75.00, "image_base": 0.024},
            "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25, "image_base": 0.0004},
        },
    }

    # Image token estimation (approximate)
    IMAGE_TOKENS_PER_TILE = 170  # OpenAI tiles
    TILE_SIZE = 512  # pixels

    def __init__(
        self,
        budget_config: Optional[BudgetConfig] = None,
        enable_alerts: bool = True,
        alert_callback: Optional[callable] = None,
    ):
        """
        Initialize cost monitor.

        Args:
            budget_config: Budget configuration
            enable_alerts: Enable budget alerts
            alert_callback: Callback function for alerts
        """
        self.config = budget_config or BudgetConfig()
        self.enable_alerts = enable_alerts
        self.alert_callback = alert_callback

        # Storage
        self._records: List[CostRecord] = []
        self._lock = threading.Lock()

        # Caches for quick lookups
        self._hourly_costs: Dict[str, float] = defaultdict(float)
        self._daily_costs: Dict[str, float] = defaultdict(float)
        self._monthly_costs: Dict[str, float] = defaultdict(float)
        self._user_daily_costs: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

        # Alert tracking
        self._last_alert_level = CostAlertLevel.INFO
        self._alerts_sent: Dict[str, datetime] = {}

    def record_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        image_count: int = 0,
        image_dimensions: Optional[List[Tuple[int, int]]] = None,
        request_type: str = "query",
        user_id: Optional[str] = None,
        document_id: Optional[str] = None,
        success: bool = True,
        latency_ms: float = 0.0,
    ) -> CostRecord:
        """
        Record API usage and calculate cost.

        Args:
            provider: API provider (openai, anthropic)
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count
            image_count: Number of images processed
            image_dimensions: List of (width, height) for each image
            request_type: Type of request
            user_id: User identifier
            document_id: Document identifier
            success: Whether request succeeded
            latency_ms: Request latency

        Returns:
            CostRecord with calculated cost
        """
        # Estimate image tokens
        image_tokens = self._estimate_image_tokens(
            provider, image_count, image_dimensions
        )

        # Calculate token usage
        token_usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            image_tokens=image_tokens,
        )

        # Calculate cost
        estimated_cost = self._calculate_cost(
            provider, model, token_usage
        )

        # Create record
        now = datetime.now(timezone.utc)
        record = CostRecord(
            timestamp=now,
            provider=provider,
            model=model,
            token_usage=token_usage,
            estimated_cost=estimated_cost,
            request_type=request_type,
            user_id=user_id,
            document_id=document_id,
            success=success,
            latency_ms=latency_ms,
        )

        # Store record
        with self._lock:
            self._records.append(record)
            self._update_caches(record)

        # Check budget and send alerts
        if self.enable_alerts:
            self._check_and_alert()

        return record

    def estimate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        image_count: int = 0,
        image_dimensions: Optional[List[Tuple[int, int]]] = None,
    ) -> float:
        """
        Estimate cost before making a request.

        Useful for pre-flight cost checks.
        """
        image_tokens = self._estimate_image_tokens(
            provider, image_count, image_dimensions
        )

        token_usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            image_tokens=image_tokens,
        )

        return self._calculate_cost(provider, model, token_usage)

    def check_budget(
        self,
        estimated_cost: float,
        user_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a request can proceed within budget.

        Args:
            estimated_cost: Estimated cost of the request
            user_id: User making the request

        Returns:
            Tuple of (allowed, reason if denied)
        """
        # Check per-request limit
        if estimated_cost > self.config.per_request_max:
            return False, f"Request cost ${estimated_cost:.4f} exceeds per-request limit ${self.config.per_request_max:.2f}"

        # Check hourly budget
        hour_key = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
        current_hourly = self._hourly_costs.get(hour_key, 0.0)
        if current_hourly + estimated_cost > self.config.hourly_budget:
            return False, f"Hourly budget exceeded (${current_hourly:.2f}/${self.config.hourly_budget:.2f})"

        # Check daily budget
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current_daily = self._daily_costs.get(day_key, 0.0)
        if current_daily + estimated_cost > self.config.daily_budget:
            return False, f"Daily budget exceeded (${current_daily:.2f}/${self.config.daily_budget:.2f})"

        # Check monthly budget
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        current_monthly = self._monthly_costs.get(month_key, 0.0)
        if current_monthly + estimated_cost > self.config.monthly_budget:
            return False, f"Monthly budget exceeded (${current_monthly:.2f}/${self.config.monthly_budget:.2f})"

        # Check per-user limit
        if user_id and self.config.per_user_daily_limit:
            user_daily = self._user_daily_costs.get(user_id, {}).get(day_key, 0.0)
            if user_daily + estimated_cost > self.config.per_user_daily_limit:
                return False, f"User daily limit exceeded (${user_daily:.2f}/${self.config.per_user_daily_limit:.2f})"

        return True, None

    def get_budget_status(self) -> Dict[str, Any]:
        """Get current budget status."""
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%d-%H")
        day_key = now.strftime("%Y-%m-%d")
        month_key = now.strftime("%Y-%m")

        hourly_spent = self._hourly_costs.get(hour_key, 0.0)
        daily_spent = self._daily_costs.get(day_key, 0.0)
        monthly_spent = self._monthly_costs.get(month_key, 0.0)

        # Determine alert level
        monthly_ratio = monthly_spent / self.config.monthly_budget if self.config.monthly_budget > 0 else 0

        if monthly_ratio >= 1.0:
            alert_level = CostAlertLevel.BUDGET_EXCEEDED
        elif monthly_ratio >= self.config.critical_threshold:
            alert_level = CostAlertLevel.CRITICAL
        elif monthly_ratio >= self.config.warning_threshold:
            alert_level = CostAlertLevel.WARNING
        else:
            alert_level = CostAlertLevel.INFO

        return {
            "alert_level": alert_level.value,
            "hourly": {
                "spent": hourly_spent,
                "budget": self.config.hourly_budget,
                "remaining": max(0, self.config.hourly_budget - hourly_spent),
                "percentage": (hourly_spent / self.config.hourly_budget * 100) if self.config.hourly_budget > 0 else 0,
            },
            "daily": {
                "spent": daily_spent,
                "budget": self.config.daily_budget,
                "remaining": max(0, self.config.daily_budget - daily_spent),
                "percentage": (daily_spent / self.config.daily_budget * 100) if self.config.daily_budget > 0 else 0,
            },
            "monthly": {
                "spent": monthly_spent,
                "budget": self.config.monthly_budget,
                "remaining": max(0, self.config.monthly_budget - monthly_spent),
                "percentage": monthly_ratio * 100,
            },
            "thresholds": {
                "warning": self.config.warning_threshold * 100,
                "critical": self.config.critical_threshold * 100,
            },
        }

    def get_usage_stats(
        self,
        period: str = "day",  # hour, day, week, month
        user_id: Optional[str] = None,
    ) -> UsageStats:
        """Get usage statistics for a time period."""
        now = datetime.now(timezone.utc)

        if period == "hour":
            start_time = now - timedelta(hours=1)
        elif period == "day":
            start_time = now - timedelta(days=1)
        elif period == "week":
            start_time = now - timedelta(weeks=1)
        elif period == "month":
            start_time = now - timedelta(days=30)
        else:
            start_time = now - timedelta(days=1)

        # Filter records
        with self._lock:
            filtered = [
                r for r in self._records
                if r.timestamp >= start_time
                and (user_id is None or r.user_id == user_id)
            ]

        if not filtered:
            return UsageStats()

        # Calculate stats
        stats = UsageStats()
        stats.total_requests = len(filtered)
        stats.successful_requests = sum(1 for r in filtered if r.success)
        stats.failed_requests = stats.total_requests - stats.successful_requests
        stats.total_cost = sum(r.estimated_cost for r in filtered)
        stats.total_input_tokens = sum(r.token_usage.input_tokens for r in filtered)
        stats.total_output_tokens = sum(r.token_usage.output_tokens for r in filtered)
        stats.total_image_tokens = sum(r.token_usage.image_tokens for r in filtered)

        latencies = [r.latency_ms for r in filtered if r.latency_ms > 0]
        stats.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0

        # Group by provider/model/user
        for r in filtered:
            stats.by_provider[r.provider] = stats.by_provider.get(r.provider, 0) + r.estimated_cost
            stats.by_model[r.model] = stats.by_model.get(r.model, 0) + r.estimated_cost
            if r.user_id:
                stats.by_user[r.user_id] = stats.by_user.get(r.user_id, 0) + r.estimated_cost

        return stats

    def get_cost_breakdown(self, days: int = 7) -> Dict[str, Any]:
        """Get daily cost breakdown for the past N days."""
        now = datetime.now(timezone.utc)
        breakdown = {}

        for i in range(days):
            day = now - timedelta(days=i)
            day_key = day.strftime("%Y-%m-%d")
            breakdown[day_key] = self._daily_costs.get(day_key, 0.0)

        return {
            "daily_costs": breakdown,
            "total": sum(breakdown.values()),
            "average": sum(breakdown.values()) / days if days > 0 else 0,
        }

    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Get cost optimization recommendations."""
        recommendations = []
        stats = self.get_usage_stats(period="week")

        # Check model usage
        if stats.by_model:
            expensive_models = ["gpt-4o", "claude-3-opus-20240229", "gpt-4-turbo"]
            for model in expensive_models:
                if model in stats.by_model and stats.by_model[model] > stats.total_cost * 0.3:
                    recommendations.append({
                        "type": "model_optimization",
                        "priority": "high",
                        "message": f"Consider using cheaper models for simple queries. "
                                   f"{model} accounts for {stats.by_model[model]/stats.total_cost*100:.1f}% of costs.",
                        "potential_savings": f"${stats.by_model[model] * 0.5:.2f}/week",
                    })

        # Check image usage
        if stats.total_image_tokens > stats.total_input_tokens * 0.5:
            recommendations.append({
                "type": "image_optimization",
                "priority": "medium",
                "message": "High image token usage. Consider resizing images before processing.",
                "potential_savings": "20-40% reduction possible",
            })

        # Check failed requests
        if stats.failed_requests > stats.total_requests * 0.1:
            recommendations.append({
                "type": "reliability",
                "priority": "high",
                "message": f"High failure rate ({stats.failed_requests}/{stats.total_requests}). "
                           "Failed requests still incur costs.",
                "action": "Investigate and fix error causes",
            })

        return recommendations

    def _estimate_image_tokens(
        self,
        provider: str,
        image_count: int,
        image_dimensions: Optional[List[Tuple[int, int]]],
    ) -> int:
        """Estimate token count for images."""
        if image_count == 0:
            return 0

        if image_dimensions:
            total_tokens = 0
            for width, height in image_dimensions:
                # Calculate tiles (OpenAI method)
                tiles_w = (width + self.TILE_SIZE - 1) // self.TILE_SIZE
                tiles_h = (height + self.TILE_SIZE - 1) // self.TILE_SIZE
                tiles = tiles_w * tiles_h
                total_tokens += tiles * self.IMAGE_TOKENS_PER_TILE + 85  # Base tokens
            return total_tokens
        else:
            # Default estimate: 1 tile per image
            return image_count * (self.IMAGE_TOKENS_PER_TILE + 85)

    def _calculate_cost(
        self,
        provider: str,
        model: str,
        token_usage: TokenUsage,
    ) -> float:
        """Calculate cost from token usage."""
        pricing = self.PRICING.get(provider, {}).get(model)

        if not pricing:
            # Fallback to GPT-4o pricing
            pricing = self.PRICING["openai"]["gpt-4o"]
            logger.warning(f"Unknown pricing for {provider}/{model}, using GPT-4o rates")

        input_cost = (token_usage.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (token_usage.output_tokens / 1_000_000) * pricing["output"]
        image_cost = (token_usage.image_tokens / 1_000_000) * pricing.get("input", 2.50)

        return input_cost + output_cost + image_cost

    def _update_caches(self, record: CostRecord) -> None:
        """Update cost caches with new record."""
        hour_key = record.timestamp.strftime("%Y-%m-%d-%H")
        day_key = record.timestamp.strftime("%Y-%m-%d")
        month_key = record.timestamp.strftime("%Y-%m")

        self._hourly_costs[hour_key] += record.estimated_cost
        self._daily_costs[day_key] += record.estimated_cost
        self._monthly_costs[month_key] += record.estimated_cost

        if record.user_id:
            self._user_daily_costs[record.user_id][day_key] += record.estimated_cost

    def _check_and_alert(self) -> None:
        """Check budget status and send alerts if needed."""
        status = self.get_budget_status()
        current_level = CostAlertLevel(status["alert_level"])

        # Only alert on level changes or first critical/exceeded
        if current_level != self._last_alert_level:
            if current_level in [CostAlertLevel.WARNING, CostAlertLevel.CRITICAL, CostAlertLevel.BUDGET_EXCEEDED]:
                self._send_alert(current_level, status)
            self._last_alert_level = current_level

    def _send_alert(self, level: CostAlertLevel, status: Dict[str, Any]) -> None:
        """Send budget alert."""
        alert_key = f"{level.value}-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

        # Rate limit alerts (once per day per level)
        if alert_key in self._alerts_sent:
            return

        self._alerts_sent[alert_key] = datetime.now(timezone.utc)

        message = (
            f"Vision LLM Budget Alert: {level.value.upper()}\n"
            f"Monthly: ${status['monthly']['spent']:.2f}/${status['monthly']['budget']:.2f} "
            f"({status['monthly']['percentage']:.1f}%)"
        )

        logger.warning(message)

        if self.alert_callback:
            try:
                self.alert_callback(level, status, message)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

    def cleanup_old_records(self, days: int = 90) -> int:
        """Remove records older than N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        with self._lock:
            original_count = len(self._records)
            self._records = [r for r in self._records if r.timestamp >= cutoff]
            removed = original_count - len(self._records)

        logger.info(f"Cleaned up {removed} old cost records")
        return removed


# Singleton instance
_monitor: Optional[VisionCostMonitor] = None


def get_vision_cost_monitor() -> VisionCostMonitor:
    """Get global cost monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = VisionCostMonitor()
    return _monitor


def create_vision_cost_monitor(
    monthly_budget: float = 1000.0,
    enable_alerts: bool = True,
) -> VisionCostMonitor:
    """Create new cost monitor with custom configuration."""
    config = BudgetConfig(monthly_budget=monthly_budget)
    return VisionCostMonitor(budget_config=config, enable_alerts=enable_alerts)
