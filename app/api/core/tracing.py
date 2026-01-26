"""
Tracing Decorators and Helpers

Provides decorators and utility functions for E2E message tracing.
"""
from functools import wraps
from typing import Optional, Dict, Any
from .logging_framework import AppLogger, LogCategory
from .trace_context import TraceContext, SpanType


def trace_request(func):
    """
    Decorator to trace API request handlers.

    Captures request parameters and response data from the decorated function,
    storing them in the trace context for later persistence.

    Usage:
        @router.post("/query")
        @trace_request
        async def query_endpoint(request: QueryRequest):
            ...

    Args:
        func: The async function to decorate

    Returns:
        Wrapped function that captures trace data
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Get trace context from RequestContext
        logger = AppLogger()
        ctx = logger.get_request_context()

        if not hasattr(ctx, 'trace_context') or ctx.trace_context is None:
            # No trace context, continue without tracing
            return await func(*args, **kwargs)

        trace_ctx: TraceContext = ctx.trace_context

        # Capture request parameters (from kwargs)
        request_data = {
            'question': kwargs.get('question'),
            'strategy': kwargs.get('strategy', 'auto'),
            'language': kwargs.get('language', 'auto')
        }

        # Execute request
        result = await func(*args, **kwargs)

        # Capture response data
        response_data = {
            'answer': result.get('answer', ''),
            'confidence': result.get('confidence', 0.0),
            'sources': len(result.get('sources', []))
        }

        # Store in trace context for later persistence
        if not hasattr(trace_ctx, 'request_data'):
            trace_ctx.request_data = request_data
        if not hasattr(trace_ctx, 'response_data'):
            trace_ctx.response_data = response_data

        return result

    return wrapper


def detect_response_quality(
    response: str,
    rag_confidence: Optional[float] = None,
    user_feedback: Optional[int] = None
) -> str:
    """
    Detect response quality flag based on priority rules.

    Priority order:
    1. User feedback (thumbs down) - highest priority
    2. Empty/short response - medium priority
    3. Low RAG confidence - lowest priority
    4. Default to NORMAL if none apply

    Args:
        response: The response text to evaluate
        rag_confidence: RAG confidence score (0-1)
        user_feedback: User feedback score (1-5, where <= 2 is negative)

    Returns:
        Quality flag string: "USER_NEGATIVE" | "EMPTY" | "LOW_CONFIDENCE" | "NORMAL"

    Examples:
        >>> detect_response_quality("", None, None)
        'EMPTY'
        >>> detect_response_quality("Good answer", 0.3, None)
        'LOW_CONFIDENCE'
        >>> detect_response_quality("Good answer", 0.8, 1)
        'USER_NEGATIVE'
        >>> detect_response_quality("Good answer", 0.8, 4)
        'NORMAL'
    """
    # Priority 1: User feedback
    if user_feedback is not None and user_feedback <= 2:
        return "USER_NEGATIVE"

    # Priority 2: Empty or short response
    if not response or len(response.strip()) < 50:
        return "EMPTY"

    # Priority 3: Low RAG confidence
    if rag_confidence is not None and rag_confidence < 0.5:
        return "LOW_CONFIDENCE"

    # Default
    return "NORMAL"


def should_sample_trace(mode_manager, is_error: bool = False) -> bool:
    """
    Determine if trace should be sampled based on mode.

    DEVELOP mode: 100% sampling (all requests traced)
    PRODUCT mode: 10% for successful requests, 100% for errors

    Args:
        mode_manager: The AppMode manager instance
        is_error: Whether this request resulted in an error

    Returns:
        bool: True if trace should be persisted, False if should be dropped

    Examples:
        # DEVELOP mode - always trace
        >>> should_sample_trace(mode_manager_develop, False)
        True
        >>> should_sample_trace(mode_manager_develop, True)
        True

        # PRODUCT mode - selective sampling
        >>> should_sample_trace(mode_manager_product, True)  # Errors always traced
        True
        >>> should_sample_trace(mode_manager_product, False)  # Success: 10% sampling
        <depends on random>
    """
    # DEVELOP mode: trace everything
    if mode_manager.is_develop:
        return True

    # PRODUCT mode: always trace errors
    if is_error:
        return True

    # PRODUCT mode: 10% sampling for successful requests
    import random
    return random.random() < 0.1


def get_trace_context_from_request() -> Optional[TraceContext]:
    """
    Get trace context from current request context.

    Returns:
        TraceContext if available, None otherwise
    """
    try:
        logger = AppLogger()
        ctx = logger.get_request_context()
        if hasattr(ctx, 'trace_context'):
            return ctx.trace_context
        return None
    except Exception:
        return None
