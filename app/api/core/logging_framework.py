"""
Centralized Logging Framework
Mode-aware logging with support for token-level tracing and APM integration
"""
import sys
import json
import time
import random
import logging
import traceback
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager
from functools import wraps
from enum import Enum
import threading

from .app_mode import get_app_mode_manager, AppMode, ModeConfig


class LogCategory(str, Enum):
    """Log categories for filtering and routing"""
    REQUEST = "request"
    RESPONSE = "response"
    TOKEN = "token"
    LLM = "llm"
    EMBEDDING = "embedding"
    DATABASE = "database"
    EXTERNAL_API = "external_api"
    SECURITY = "security"
    PERFORMANCE = "performance"
    BUSINESS = "business"
    ERROR = "error"
    AUDIT = "audit"


@dataclass
class RequestContext:
    """Context information for a request"""
    request_id: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "endpoint": self.endpoint,
            "method": self.method,
            "ip_address": self.ip_address,
            "elapsed_ms": int((time.time() - self.start_time) * 1000)
        }


@dataclass
class TokenLogEntry:
    """Log entry for token-level processing"""
    request_id: str
    session_id: Optional[str]
    token_index: int
    token_content: Optional[str]
    processing_stage: str
    start_time_ms: float
    end_time_ms: float
    processing_time_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PerformanceMetrics:
    """Performance tracking metrics"""
    operation: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter for production"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # Add extra fields
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "session_id"):
            log_data["session_id"] = record.session_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "category"):
            log_data["category"] = record.category
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data

        # Add exception info if present
        if record.exc_info:
            mode_manager = get_app_mode_manager()
            if mode_manager.should_log_stack_trace():
                log_data["exception"] = {
                    "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                    "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                    "traceback": traceback.format_exception(*record.exc_info)
                }
            else:
                log_data["exception"] = {
                    "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                    "message": str(record.exc_info[1]) if record.exc_info[1] else None
                }

        return json.dumps(log_data, ensure_ascii=False, default=str)


class DevelopFormatter(logging.Formatter):
    """Human-readable formatter for development"""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m"
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]

        # Build base message
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        base = f"{color}[{timestamp}] {record.levelname:8}{reset} {record.name}: {record.getMessage()}"

        # Add context if available
        context_parts = []
        if hasattr(record, "request_id"):
            context_parts.append(f"req={record.request_id[:8]}")
        if hasattr(record, "session_id") and record.session_id:
            context_parts.append(f"sess={record.session_id[:8]}")
        if hasattr(record, "duration_ms"):
            context_parts.append(f"took={record.duration_ms}ms")

        if context_parts:
            base = f"{base} [{', '.join(context_parts)}]"

        # Add extra data
        if hasattr(record, "extra_data") and record.extra_data:
            base = f"{base}\n    {color}→{reset} {json.dumps(record.extra_data, ensure_ascii=False, default=str)}"

        # Add exception info
        if record.exc_info:
            exc_text = "".join(traceback.format_exception(*record.exc_info))
            base = f"{base}\n{color}{exc_text}{reset}"

        return base


class AppLogger:
    """
    Central application logger with mode-aware behavior.
    Provides consistent logging interface across the application.
    """

    _loggers: Dict[str, logging.Logger] = {}
    _context: threading.local = threading.local()

    def __init__(self, name: str = "kms"):
        self.name = name
        self._logger = self._get_or_create_logger(name)
        self._mode_manager = get_app_mode_manager()

    @classmethod
    def _get_or_create_logger(cls, name: str) -> logging.Logger:
        """Get or create a logger with proper configuration"""
        if name in cls._loggers:
            return cls._loggers[name]

        logger = logging.getLogger(name)
        mode_manager = get_app_mode_manager()

        # Set log level based on mode
        level = getattr(logging, mode_manager.get_log_level())
        logger.setLevel(level)

        # Remove existing handlers
        logger.handlers = []

        # Create handler with appropriate formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        if mode_manager.is_develop:
            handler.setFormatter(DevelopFormatter())
        else:
            handler.setFormatter(StructuredFormatter())

        logger.addHandler(handler)
        logger.propagate = False

        cls._loggers[name] = logger
        return logger

    @classmethod
    def set_request_context(cls, context: RequestContext):
        """Set request context for current thread"""
        cls._context.request_context = context

    @classmethod
    def get_request_context(cls) -> Optional[RequestContext]:
        """Get request context for current thread"""
        return getattr(cls._context, "request_context", None)

    @classmethod
    def clear_request_context(cls):
        """Clear request context for current thread"""
        if hasattr(cls._context, "request_context"):
            delattr(cls._context, "request_context")

    def _should_sample_log(self) -> bool:
        """Check if this log should be sampled (for production)"""
        config = self._mode_manager.config
        if config.log_sampling_rate >= 1.0:
            return True
        return random.random() < config.log_sampling_rate

    def _add_context_to_record(
        self,
        extra: Dict[str, Any],
        category: Optional[LogCategory] = None,
        duration_ms: Optional[float] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Add context information to log record"""
        ctx = self.get_request_context()

        result = {**extra}
        if ctx:
            result["request_id"] = ctx.request_id
            result["session_id"] = ctx.session_id
            result["user_id"] = ctx.user_id

        if category:
            result["category"] = category.value
        if duration_ms is not None:
            result["duration_ms"] = duration_ms
        if extra_data:
            result["extra_data"] = extra_data

        return result

    def debug(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Log debug message (develop mode only)"""
        if not self._mode_manager.config.enable_debug_logs:
            return

        extra = self._add_context_to_record({}, category, extra_data=extra_data)
        self._logger.debug(message, extra=extra, **kwargs)

    def info(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        duration_ms: Optional[float] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Log info message"""
        if not self._should_sample_log():
            return

        extra = self._add_context_to_record({}, category, duration_ms, extra_data)
        self._logger.info(message, extra=extra, **kwargs)

    def warning(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Log warning message"""
        extra = self._add_context_to_record({}, category, extra_data=extra_data)
        self._logger.warning(message, extra=extra, **kwargs)

    def error(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
        **kwargs
    ):
        """Log error message"""
        extra = self._add_context_to_record({}, category or LogCategory.ERROR, extra_data=extra_data)

        # Auto-include exception info in develop mode
        if self._mode_manager.is_develop and sys.exc_info()[0] is not None:
            exc_info = True

        self._logger.error(message, extra=extra, exc_info=exc_info, **kwargs)

    def critical(
        self,
        message: str,
        category: Optional[LogCategory] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        exc_info: bool = True,
        **kwargs
    ):
        """Log critical message"""
        extra = self._add_context_to_record({}, category or LogCategory.ERROR, extra_data=extra_data)
        self._logger.critical(message, extra=extra, exc_info=exc_info, **kwargs)

    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        extra_data: Optional[Dict[str, Any]] = None
    ):
        """Log HTTP request"""
        message = f"{method} {path} → {status_code}"

        level = logging.INFO
        if status_code >= 500:
            level = logging.ERROR
        elif status_code >= 400:
            level = logging.WARNING

        extra = self._add_context_to_record(
            {},
            LogCategory.REQUEST,
            duration_ms,
            {
                "method": method,
                "path": path,
                "status_code": status_code,
                **(extra_data or {})
            }
        )

        self._logger.log(level, message, extra=extra)

    def log_performance(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        extra_data: Optional[Dict[str, Any]] = None
    ):
        """Log performance metrics"""
        if not self._mode_manager.config.enable_performance_tracking:
            return

        threshold = self._mode_manager.config.slow_request_threshold_ms
        is_slow = duration_ms > threshold

        message = f"Performance: {operation}"
        if is_slow:
            message = f"SLOW {message}"

        level = logging.WARNING if is_slow else logging.DEBUG
        if not success:
            level = logging.ERROR

        extra = self._add_context_to_record(
            {},
            LogCategory.PERFORMANCE,
            duration_ms,
            {"operation": operation, "success": success, "slow": is_slow, **(extra_data or {})}
        )

        self._logger.log(level, message, extra=extra)


class TokenLogger:
    """
    Specialized logger for token-level processing.
    Only active in develop mode.
    """

    def __init__(self, logger: Optional[AppLogger] = None):
        self._logger = logger or AppLogger("kms.token")
        self._mode_manager = get_app_mode_manager()
        self._token_entries: List[TokenLogEntry] = []

    def is_enabled(self) -> bool:
        """Check if token logging is enabled"""
        return self._mode_manager.should_log_tokens()

    @contextmanager
    def track_token(
        self,
        token_index: int,
        token_content: Optional[str] = None,
        processing_stage: str = "process",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Context manager to track token processing time.

        Usage:
            with token_logger.track_token(0, "Hello", "embedding") as entry:
                # Process token
                pass
        """
        if not self.is_enabled():
            yield None
            return

        ctx = AppLogger.get_request_context()
        request_id = ctx.request_id if ctx else "unknown"
        session_id = ctx.session_id if ctx else None

        start_time = time.time() * 1000  # milliseconds

        entry = TokenLogEntry(
            request_id=request_id,
            session_id=session_id,
            token_index=token_index,
            token_content=token_content[:50] if token_content else None,
            processing_stage=processing_stage,
            start_time_ms=start_time,
            end_time_ms=0,
            processing_time_ms=0,
            metadata=metadata or {}
        )

        try:
            yield entry
        finally:
            end_time = time.time() * 1000
            entry.end_time_ms = end_time
            entry.processing_time_ms = round(end_time - start_time, 3)

            self._token_entries.append(entry)
            self._log_token_entry(entry)

    def _log_token_entry(self, entry: TokenLogEntry):
        """Log individual token entry"""
        self._logger.debug(
            f"Token[{entry.token_index}] {entry.processing_stage}: {entry.processing_time_ms}ms",
            category=LogCategory.TOKEN,
            extra_data={
                "token_index": entry.token_index,
                "token_content": entry.token_content,
                "stage": entry.processing_stage,
                "processing_time_ms": entry.processing_time_ms,
                **entry.metadata
            }
        )

    def log_batch(
        self,
        tokens: List[str],
        processing_stage: str,
        total_time_ms: float,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log batch token processing"""
        if not self.is_enabled():
            return

        avg_time = total_time_ms / len(tokens) if tokens else 0

        self._logger.debug(
            f"Token batch [{len(tokens)} tokens] {processing_stage}: {total_time_ms}ms (avg: {avg_time:.2f}ms)",
            category=LogCategory.TOKEN,
            extra_data={
                "token_count": len(tokens),
                "stage": processing_stage,
                "total_time_ms": total_time_ms,
                "avg_time_ms": avg_time,
                **(metadata or {})
            }
        )

    def get_entries(self) -> List[TokenLogEntry]:
        """Get all logged token entries"""
        return self._token_entries

    def clear_entries(self):
        """Clear logged entries"""
        self._token_entries = []

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of token processing"""
        if not self._token_entries:
            return {"total_tokens": 0, "total_time_ms": 0}

        total_time = sum(e.processing_time_ms for e in self._token_entries)
        by_stage: Dict[str, List[float]] = {}

        for entry in self._token_entries:
            if entry.processing_stage not in by_stage:
                by_stage[entry.processing_stage] = []
            by_stage[entry.processing_stage].append(entry.processing_time_ms)

        stage_summary = {
            stage: {
                "count": len(times),
                "total_ms": sum(times),
                "avg_ms": sum(times) / len(times),
                "max_ms": max(times),
                "min_ms": min(times)
            }
            for stage, times in by_stage.items()
        }

        return {
            "total_tokens": len(self._token_entries),
            "total_time_ms": total_time,
            "avg_time_per_token_ms": total_time / len(self._token_entries),
            "by_stage": stage_summary
        }


# Decorator for function timing
def log_execution(
    operation: Optional[str] = None,
    category: LogCategory = LogCategory.BUSINESS,
    log_args: bool = False
):
    """
    Decorator to log function execution with timing.

    Usage:
        @log_execution("process_query", category=LogCategory.LLM)
        async def process_query(query: str):
            ...
    """
    def decorator(func: Callable):
        op_name = operation or f"{func.__module__}.{func.__name__}"

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = AppLogger("kms.execution")

            extra = {}
            if log_args and get_app_mode_manager().is_develop:
                extra = {"args": str(args)[:200], "kwargs": str(kwargs)[:200]}

            logger.debug(f"→ Entering {op_name}", category=category, extra_data=extra)

            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start) * 1000

                logger.log_performance(op_name, duration, success=True)
                logger.debug(f"← Exiting {op_name}", category=category)

                return result
            except Exception as e:
                duration = (time.time() - start) * 1000
                logger.log_performance(op_name, duration, success=False)
                logger.error(
                    f"✗ Error in {op_name}: {str(e)}",
                    category=category,
                    exc_info=True
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = AppLogger("kms.execution")

            extra = {}
            if log_args and get_app_mode_manager().is_develop:
                extra = {"args": str(args)[:200], "kwargs": str(kwargs)[:200]}

            logger.debug(f"→ Entering {op_name}", category=category, extra_data=extra)

            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start) * 1000

                logger.log_performance(op_name, duration, success=True)
                logger.debug(f"← Exiting {op_name}", category=category)

                return result
            except Exception as e:
                duration = (time.time() - start) * 1000
                logger.log_performance(op_name, duration, success=False)
                logger.error(
                    f"✗ Error in {op_name}: {str(e)}",
                    category=category,
                    exc_info=True
                )
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Global logger instances
_main_logger: Optional[AppLogger] = None
_token_logger: Optional[TokenLogger] = None


def get_logger(name: str = "kms") -> AppLogger:
    """Get application logger"""
    global _main_logger
    if _main_logger is None or name != "kms":
        _main_logger = AppLogger(name)
    return _main_logger


def get_token_logger() -> TokenLogger:
    """Get token logger"""
    global _token_logger
    if _token_logger is None:
        _token_logger = TokenLogger()
    return _token_logger
