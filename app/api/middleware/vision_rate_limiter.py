"""
Vision Rate Limiter Middleware

Rate limiting for Vision LLM API endpoints with:
- Per-user request limits
- Token-based limits
- Cost-based limits
- Sliding window algorithm
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import threading

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    # Request limits
    requests_per_minute: int = 20
    requests_per_hour: int = 200
    requests_per_day: int = 1000

    # Token limits (estimated)
    tokens_per_minute: int = 100000
    tokens_per_hour: int = 500000

    # Cost limits (USD)
    cost_per_hour: float = 10.0
    cost_per_day: float = 50.0

    # Image limits
    images_per_request: int = 10
    images_per_hour: int = 100

    # Burst allowance
    burst_multiplier: float = 1.5

    # Retry-After header (seconds)
    retry_after_seconds: int = 60


@dataclass
class UserRateState:
    """Rate limiting state for a single user"""
    # Request tracking (timestamps)
    minute_requests: List[float] = field(default_factory=list)
    hour_requests: List[float] = field(default_factory=list)
    day_requests: List[float] = field(default_factory=list)

    # Token tracking
    minute_tokens: List[Tuple[float, int]] = field(default_factory=list)
    hour_tokens: List[Tuple[float, int]] = field(default_factory=list)

    # Cost tracking
    hour_costs: List[Tuple[float, float]] = field(default_factory=list)
    day_costs: List[Tuple[float, float]] = field(default_factory=list)

    # Image tracking
    hour_images: List[Tuple[float, int]] = field(default_factory=list)

    # Lock for thread safety
    lock: threading.Lock = field(default_factory=threading.Lock)


class VisionRateLimiter:
    """
    Rate limiter for Vision API endpoints.

    Uses sliding window algorithm for accurate rate limiting.

    Usage:
        limiter = VisionRateLimiter()

        # Check if request is allowed
        allowed, reason = limiter.check_rate_limit(user_id, estimated_tokens=5000)
        if not allowed:
            raise HTTPException(429, detail=reason)

        # Record after request
        limiter.record_request(user_id, tokens=5000, cost=0.02, images=2)
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """Initialize rate limiter with configuration."""
        self.config = config or RateLimitConfig()
        self._user_states: Dict[str, UserRateState] = defaultdict(UserRateState)
        self._global_lock = threading.Lock()

    def check_rate_limit(
        self,
        user_id: str,
        estimated_tokens: int = 0,
        estimated_cost: float = 0.0,
        image_count: int = 0,
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Check if request is allowed within rate limits.

        Args:
            user_id: User identifier
            estimated_tokens: Estimated tokens for this request
            estimated_cost: Estimated cost for this request
            image_count: Number of images in request

        Returns:
            Tuple of (allowed, reason if denied, retry_after seconds)
        """
        state = self._get_user_state(user_id)
        now = time.time()

        with state.lock:
            # Clean old entries
            self._cleanup_old_entries(state, now)

            # Check per-request image limit
            if image_count > self.config.images_per_request:
                return (
                    False,
                    f"Too many images: {image_count} (max {self.config.images_per_request})",
                    None,
                )

            # Check request rate limits
            minute_count = len(state.minute_requests)
            if minute_count >= self.config.requests_per_minute * self.config.burst_multiplier:
                return (
                    False,
                    f"Rate limit exceeded: {minute_count} requests/minute (max {self.config.requests_per_minute})",
                    self.config.retry_after_seconds,
                )

            hour_count = len(state.hour_requests)
            if hour_count >= self.config.requests_per_hour:
                return (
                    False,
                    f"Hourly rate limit exceeded: {hour_count} requests/hour (max {self.config.requests_per_hour})",
                    3600 - int(now - state.hour_requests[0]) if state.hour_requests else 3600,
                )

            day_count = len(state.day_requests)
            if day_count >= self.config.requests_per_day:
                return (
                    False,
                    f"Daily rate limit exceeded: {day_count} requests/day (max {self.config.requests_per_day})",
                    86400 - int(now - state.day_requests[0]) if state.day_requests else 86400,
                )

            # Check token limits
            minute_tokens = sum(t[1] for t in state.minute_tokens)
            if minute_tokens + estimated_tokens > self.config.tokens_per_minute:
                return (
                    False,
                    f"Token limit exceeded: {minute_tokens + estimated_tokens} tokens/minute "
                    f"(max {self.config.tokens_per_minute})",
                    self.config.retry_after_seconds,
                )

            hour_tokens = sum(t[1] for t in state.hour_tokens)
            if hour_tokens + estimated_tokens > self.config.tokens_per_hour:
                return (
                    False,
                    f"Hourly token limit exceeded",
                    3600,
                )

            # Check cost limits
            hour_cost = sum(c[1] for c in state.hour_costs)
            if hour_cost + estimated_cost > self.config.cost_per_hour:
                return (
                    False,
                    f"Hourly cost limit exceeded: ${hour_cost + estimated_cost:.2f} "
                    f"(max ${self.config.cost_per_hour:.2f})",
                    3600,
                )

            day_cost = sum(c[1] for c in state.day_costs)
            if day_cost + estimated_cost > self.config.cost_per_day:
                return (
                    False,
                    f"Daily cost limit exceeded: ${day_cost + estimated_cost:.2f} "
                    f"(max ${self.config.cost_per_day:.2f})",
                    86400,
                )

            # Check image limits
            hour_images = sum(i[1] for i in state.hour_images)
            if hour_images + image_count > self.config.images_per_hour:
                return (
                    False,
                    f"Hourly image limit exceeded: {hour_images + image_count} images "
                    f"(max {self.config.images_per_hour})",
                    3600,
                )

        return True, None, None

    def record_request(
        self,
        user_id: str,
        tokens: int = 0,
        cost: float = 0.0,
        images: int = 0,
    ) -> None:
        """
        Record a completed request for rate limiting.

        Args:
            user_id: User identifier
            tokens: Actual tokens used
            cost: Actual cost
            images: Number of images processed
        """
        state = self._get_user_state(user_id)
        now = time.time()

        with state.lock:
            # Record request timestamp
            state.minute_requests.append(now)
            state.hour_requests.append(now)
            state.day_requests.append(now)

            # Record tokens
            if tokens > 0:
                state.minute_tokens.append((now, tokens))
                state.hour_tokens.append((now, tokens))

            # Record cost
            if cost > 0:
                state.hour_costs.append((now, cost))
                state.day_costs.append((now, cost))

            # Record images
            if images > 0:
                state.hour_images.append((now, images))

    def get_rate_limit_status(self, user_id: str) -> Dict[str, Any]:
        """Get current rate limit status for a user."""
        state = self._get_user_state(user_id)
        now = time.time()

        with state.lock:
            self._cleanup_old_entries(state, now)

            minute_requests = len(state.minute_requests)
            hour_requests = len(state.hour_requests)
            day_requests = len(state.day_requests)

            minute_tokens = sum(t[1] for t in state.minute_tokens)
            hour_tokens = sum(t[1] for t in state.hour_tokens)

            hour_cost = sum(c[1] for c in state.hour_costs)
            day_cost = sum(c[1] for c in state.day_costs)

            hour_images = sum(i[1] for i in state.hour_images)

        return {
            "requests": {
                "minute": {"used": minute_requests, "limit": self.config.requests_per_minute},
                "hour": {"used": hour_requests, "limit": self.config.requests_per_hour},
                "day": {"used": day_requests, "limit": self.config.requests_per_day},
            },
            "tokens": {
                "minute": {"used": minute_tokens, "limit": self.config.tokens_per_minute},
                "hour": {"used": hour_tokens, "limit": self.config.tokens_per_hour},
            },
            "cost": {
                "hour": {"used": hour_cost, "limit": self.config.cost_per_hour},
                "day": {"used": day_cost, "limit": self.config.cost_per_day},
            },
            "images": {
                "hour": {"used": hour_images, "limit": self.config.images_per_hour},
            },
        }

    def _get_user_state(self, user_id: str) -> UserRateState:
        """Get or create rate limit state for a user."""
        with self._global_lock:
            if user_id not in self._user_states:
                self._user_states[user_id] = UserRateState()
            return self._user_states[user_id]

    def _cleanup_old_entries(self, state: UserRateState, now: float) -> None:
        """Remove expired entries from rate limit state."""
        minute_ago = now - 60
        hour_ago = now - 3600
        day_ago = now - 86400

        # Clean request timestamps
        state.minute_requests = [t for t in state.minute_requests if t > minute_ago]
        state.hour_requests = [t for t in state.hour_requests if t > hour_ago]
        state.day_requests = [t for t in state.day_requests if t > day_ago]

        # Clean token records
        state.minute_tokens = [(t, v) for t, v in state.minute_tokens if t > minute_ago]
        state.hour_tokens = [(t, v) for t, v in state.hour_tokens if t > hour_ago]

        # Clean cost records
        state.hour_costs = [(t, v) for t, v in state.hour_costs if t > hour_ago]
        state.day_costs = [(t, v) for t, v in state.day_costs if t > day_ago]

        # Clean image records
        state.hour_images = [(t, v) for t, v in state.hour_images if t > hour_ago]

    def reset_user(self, user_id: str) -> None:
        """Reset rate limit state for a user."""
        with self._global_lock:
            if user_id in self._user_states:
                del self._user_states[user_id]

    def get_all_users_status(self) -> Dict[str, Dict[str, Any]]:
        """Get rate limit status for all users (admin use)."""
        with self._global_lock:
            user_ids = list(self._user_states.keys())

        return {uid: self.get_rate_limit_status(uid) for uid in user_ids}


class VisionRateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for Vision API rate limiting.

    Applies rate limits to /api/v1/vision/* endpoints.
    """

    def __init__(self, app, limiter: Optional[VisionRateLimiter] = None):
        super().__init__(app)
        self.limiter = limiter or VisionRateLimiter()
        self.vision_paths = ["/api/v1/vision/"]

    async def dispatch(self, request: Request, call_next):
        """Process request through rate limiter."""
        # Only apply to vision endpoints
        if not any(request.url.path.startswith(p) for p in self.vision_paths):
            return await call_next(request)

        # Get user ID from request
        user_id = self._get_user_id(request)

        # Estimate request size
        estimated_tokens = self._estimate_tokens(request)
        image_count = self._count_images(request)

        # Check rate limit
        allowed, reason, retry_after = self.limiter.check_rate_limit(
            user_id=user_id,
            estimated_tokens=estimated_tokens,
            image_count=image_count,
        )

        if not allowed:
            headers = {}
            if retry_after:
                headers["Retry-After"] = str(retry_after)

            # Add rate limit headers
            status = self.limiter.get_rate_limit_status(user_id)
            headers["X-RateLimit-Limit"] = str(self.limiter.config.requests_per_minute)
            headers["X-RateLimit-Remaining"] = str(
                max(0, self.limiter.config.requests_per_minute - status["requests"]["minute"]["used"])
            )

            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": reason,
                    "retry_after": retry_after,
                },
                headers=headers,
            )

        # Process request
        start_time = time.time()
        response = await call_next(request)
        latency = time.time() - start_time

        # Record successful request
        if response.status_code < 400:
            self.limiter.record_request(
                user_id=user_id,
                tokens=estimated_tokens,
                images=image_count,
            )

        # Add rate limit headers to response
        status = self.limiter.get_rate_limit_status(user_id)
        response.headers["X-RateLimit-Limit"] = str(self.limiter.config.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, self.limiter.config.requests_per_minute - status["requests"]["minute"]["used"])
        )
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)

        return response

    def _get_user_id(self, request: Request) -> str:
        """Extract user ID from request."""
        # Try to get from state (set by auth middleware)
        if hasattr(request.state, "user"):
            return request.state.user.get("id", "anonymous")

        # Try to get from header
        user_id = request.headers.get("X-User-ID")
        if user_id:
            return user_id

        # Fallback to IP-based limiting
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        return request.client.host if request.client else "anonymous"

    def _estimate_tokens(self, request: Request) -> int:
        """Estimate tokens for the request."""
        # Default estimate for vision requests
        return 5000

    def _count_images(self, request: Request) -> int:
        """Count images in the request."""
        # Would need to inspect multipart form data
        # For now, return 0 (actual count done after parsing)
        return 0


# Singleton instance
_limiter: Optional[VisionRateLimiter] = None


def get_vision_rate_limiter() -> VisionRateLimiter:
    """Get global rate limiter instance."""
    global _limiter
    if _limiter is None:
        _limiter = VisionRateLimiter()
    return _limiter


def create_rate_limit_middleware(app) -> VisionRateLimitMiddleware:
    """Create rate limit middleware for the app."""
    return VisionRateLimitMiddleware(app, get_vision_rate_limiter())
