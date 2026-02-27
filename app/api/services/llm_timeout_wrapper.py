"""
LLM Timeout Wrapper - Timeout and retry handling for LLM calls
타임아웃, 재시도, 폴백 메커니즘 제공

Phase 1 - H2: LLM 타임아웃 처리
"""
import asyncio
import logging
from typing import Callable, TypeVar, Optional, Any, Tuple
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import threading

logger = logging.getLogger(__name__)

T = TypeVar('T')


class LLMTimeoutError(Exception):
    """LLM 타임아웃 예외"""

    def __init__(self, timeout_seconds: float, operation: str = "LLM call", attempt: int = 1):
        self.timeout_seconds = timeout_seconds
        self.operation = operation
        self.attempt = attempt
        super().__init__(f"{operation} timed out after {timeout_seconds}s (attempt {attempt})")


class LLMError(Exception):
    """LLM 일반 오류"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.original_error = original_error
        super().__init__(message)


class LLMTimeoutWrapper:
    """
    LLM 호출 타임아웃 관리자

    기능:
    - 동기/비동기 함수에 타임아웃 적용
    - 재시도 로직 (지수 백오프)
    - 폴백 함수 지원

    사용 예:
        wrapper = LLMTimeoutWrapper(timeout=30, max_retries=2, fallback_fn=my_fallback)
        result = wrapper.execute_sync(llm.invoke, prompt)
    """

    DEFAULT_TIMEOUT = 30  # 기본 30초
    MAX_RETRIES = 2       # 최대 재시도 2회

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        fallback_fn: Optional[Callable[..., T]] = None,
        backoff_base: float = 1.0
    ):
        """
        Args:
            timeout: 타임아웃 시간 (초)
            max_retries: 최대 재시도 횟수
            fallback_fn: 모든 시도 실패 시 호출할 폴백 함수
            backoff_base: 재시도 간 대기 시간 기본값 (지수 백오프)
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.fallback_fn = fallback_fn
        self.backoff_base = backoff_base
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm_timeout")

    def execute_sync(
        self,
        func: Callable[..., T],
        *args,
        fallback_args: Optional[tuple] = None,
        **kwargs
    ) -> T:
        """
        동기 함수에 타임아웃 적용하여 실행

        Args:
            func: 실행할 함수
            *args: 함수 인자
            fallback_args: 폴백 함수에 전달할 인자 (없으면 args 사용)
            **kwargs: 함수 키워드 인자

        Returns:
            함수 실행 결과 또는 폴백 결과

        Raises:
            LLMTimeoutError: 모든 재시도 실패 및 폴백 없음
            LLMError: 기타 오류
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                # ThreadPoolExecutor를 사용한 타임아웃 적용
                future = self._executor.submit(func, *args, **kwargs)
                result = future.result(timeout=self.timeout)
                return result

            except FuturesTimeoutError:
                last_error = LLMTimeoutError(self.timeout, "LLM call", attempt + 1)
                logger.warning(
                    f"LLM timeout on attempt {attempt + 1}/{self.max_retries + 1} "
                    f"(timeout={self.timeout}s)"
                )

                if attempt < self.max_retries:
                    # 지수 백오프 대기
                    wait_time = self.backoff_base * (2 ** attempt)
                    logger.info(f"Retrying in {wait_time}s...")
                    import time
                    time.sleep(wait_time)

            except Exception as e:
                last_error = LLMError(f"LLM error: {e}", e)
                logger.error(f"LLM error on attempt {attempt + 1}: {e}")

                # 특정 오류는 재시도하지 않음
                if self._is_non_retryable_error(e):
                    break

                if attempt < self.max_retries:
                    wait_time = self.backoff_base * (2 ** attempt)
                    import time
                    time.sleep(wait_time)

        # 모든 재시도 실패 → 폴백 실행
        if self.fallback_fn is not None:
            logger.info("All attempts failed. Executing fallback function...")
            try:
                fallback_input = fallback_args if fallback_args is not None else args
                return self.fallback_fn(*fallback_input)
            except Exception as e:
                logger.error(f"Fallback function also failed: {e}")
                raise LLMError(f"Fallback failed: {e}", e)

        # 폴백 없으면 마지막 오류 발생
        if last_error:
            raise last_error
        raise LLMTimeoutError(self.timeout)

    async def execute_async(
        self,
        coro_fn: Callable[..., T],
        *args,
        fallback_args: Optional[tuple] = None,
        **kwargs
    ) -> T:
        """
        비동기 코루틴에 타임아웃 적용하여 실행

        Args:
            coro_fn: 실행할 비동기 함수
            *args: 함수 인자
            fallback_args: 폴백 함수에 전달할 인자
            **kwargs: 함수 키워드 인자

        Returns:
            함수 실행 결과 또는 폴백 결과
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                async with asyncio.timeout(self.timeout):
                    return await coro_fn(*args, **kwargs)

            except asyncio.TimeoutError:
                last_error = LLMTimeoutError(self.timeout, "async LLM call", attempt + 1)
                logger.warning(
                    f"Async LLM timeout on attempt {attempt + 1}/{self.max_retries + 1}"
                )

                if attempt < self.max_retries:
                    wait_time = self.backoff_base * (2 ** attempt)
                    await asyncio.sleep(wait_time)

            except Exception as e:
                last_error = LLMError(f"Async LLM error: {e}", e)
                logger.error(f"Async LLM error on attempt {attempt + 1}: {e}")

                if self._is_non_retryable_error(e):
                    break

                if attempt < self.max_retries:
                    wait_time = self.backoff_base * (2 ** attempt)
                    await asyncio.sleep(wait_time)

        # 폴백 실행
        if self.fallback_fn is not None:
            logger.info("All async attempts failed. Executing fallback...")
            try:
                fallback_input = fallback_args if fallback_args is not None else args
                result = self.fallback_fn(*fallback_input)
                # 폴백이 코루틴이면 await
                if asyncio.iscoroutine(result):
                    return await result
                return result
            except Exception as e:
                logger.error(f"Fallback failed: {e}")
                raise LLMError(f"Fallback failed: {e}", e)

        if last_error:
            raise last_error
        raise LLMTimeoutError(self.timeout)

    def _is_non_retryable_error(self, error: Exception) -> bool:
        """재시도할 수 없는 오류인지 확인"""
        non_retryable_messages = [
            "invalid api key",
            "authentication failed",
            "model not found",
            "rate limit exceeded",  # Rate limit은 백오프 필요하지만 다른 전략 필요
        ]

        error_str = str(error).lower()
        return any(msg in error_str for msg in non_retryable_messages)

    def close(self):
        """리소스 정리"""
        self._executor.shutdown(wait=False)


def with_timeout(
    timeout: float = LLMTimeoutWrapper.DEFAULT_TIMEOUT,
    max_retries: int = LLMTimeoutWrapper.MAX_RETRIES,
    fallback: Optional[Callable] = None
):
    """
    타임아웃 데코레이터 (동기 함수용)

    Usage:
        @with_timeout(30, fallback=my_fallback_fn)
        def my_llm_call(prompt):
            return llm.invoke(prompt)
    """
    def decorator(func):
        wrapper_instance = LLMTimeoutWrapper(
            timeout=timeout,
            max_retries=max_retries,
            fallback_fn=fallback
        )

        @wraps(func)
        def wrapper(*args, **kwargs):
            return wrapper_instance.execute_sync(func, *args, **kwargs)

        return wrapper
    return decorator


def with_async_timeout(
    timeout: float = LLMTimeoutWrapper.DEFAULT_TIMEOUT,
    max_retries: int = LLMTimeoutWrapper.MAX_RETRIES,
    fallback: Optional[Callable] = None
):
    """
    타임아웃 데코레이터 (비동기 함수용)

    Usage:
        @with_async_timeout(30, fallback=my_fallback_fn)
        async def my_async_llm_call(prompt):
            return await llm.ainvoke(prompt)
    """
    def decorator(func):
        wrapper_instance = LLMTimeoutWrapper(
            timeout=timeout,
            max_retries=max_retries,
            fallback_fn=fallback
        )

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await wrapper_instance.execute_async(func, *args, **kwargs)

        return wrapper
    return decorator


# 편의를 위한 기본 인스턴스
_default_wrapper: Optional[LLMTimeoutWrapper] = None


def get_default_wrapper(
    timeout: float = 30,
    max_retries: int = 2
) -> LLMTimeoutWrapper:
    """기본 래퍼 인스턴스 반환 (싱글톤)"""
    global _default_wrapper
    if _default_wrapper is None:
        _default_wrapper = LLMTimeoutWrapper(timeout=timeout, max_retries=max_retries)
    return _default_wrapper
