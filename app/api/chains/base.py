"""
Base Chain Infrastructure
Abstract chain classes for composable AI pipelines.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    Dict, Any, Optional, List, TypeVar, Generic,
    Callable, Awaitable, Union
)
from enum import Enum
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

TInput = TypeVar('TInput')
TOutput = TypeVar('TOutput')


class ChainStatus(str, Enum):
    """Status of chain execution"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ChainConfig:
    """Base configuration for chains"""
    timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_delay: float = 1.0
    enable_logging: bool = True
    enable_metrics: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    """Result from a single chain step"""
    step_name: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainResult(Generic[TOutput]):
    """
    Result of chain execution.

    Contains output, status, timing, and step details.
    """
    status: ChainStatus
    output: Optional[TOutput] = None
    error: Optional[str] = None
    steps: List[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == ChainStatus.SUCCESS

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def get_step(self, name: str) -> Optional[StepResult]:
        """Get step result by name"""
        for step in self.steps:
            if step.step_name == name:
                return step
        return None

    def add_step(self, step: StepResult) -> None:
        """Add step result"""
        self.steps.append(step)
        self.total_duration_ms += step.duration_ms


class ChainStep(ABC, Generic[TInput, TOutput]):
    """
    A single step in a chain.

    Steps are composable units that transform input to output.
    They can be combined to form complex pipelines.

    Example:
        class EmbedStep(ChainStep[str, List[float]]):
            def __init__(self, embedder: EmbeddingPort):
                self.embedder = embedder

            async def execute(self, input: str, context: Dict) -> List[float]:
                return await self.embedder.embed(input)
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def execute(
        self,
        input: TInput,
        context: Dict[str, Any]
    ) -> TOutput:
        """
        Execute this step.

        Args:
            input: Input from previous step
            context: Shared context across steps

        Returns:
            Output for next step
        """
        pass

    async def validate_input(self, input: TInput) -> bool:
        """Validate input before execution"""
        return True

    async def on_error(
        self,
        error: Exception,
        input: TInput,
        context: Dict[str, Any]
    ) -> Optional[TOutput]:
        """Handle error, optionally return fallback"""
        return None


class Chain(ABC, Generic[TInput, TOutput]):
    """
    Abstract base class for chains.

    A chain is a sequence of steps that process input
    and produce output. Chains handle:
    - Step orchestration
    - Error handling and retries
    - Logging and metrics
    - Context management

    Example:
        class MyChain(Chain[str, str]):
            def __init__(self, llm: LLMPort):
                super().__init__("my_chain")
                self.llm = llm
                self._steps = [
                    PrepareStep(),
                    GenerateStep(llm),
                    FormatStep()
                ]

            def get_steps(self) -> List[ChainStep]:
                return self._steps
    """

    def __init__(
        self,
        name: str,
        config: Optional[ChainConfig] = None
    ):
        self.name = name
        self.config = config or ChainConfig()
        self._hooks: Dict[str, List[Callable]] = {
            "before_chain": [],
            "after_chain": [],
            "before_step": [],
            "after_step": [],
            "on_error": []
        }

    @abstractmethod
    def get_steps(self) -> List[ChainStep]:
        """Return ordered list of steps"""
        pass

    async def run(
        self,
        input: TInput,
        context: Optional[Dict[str, Any]] = None
    ) -> ChainResult[TOutput]:
        """
        Execute the chain.

        Args:
            input: Initial input
            context: Optional shared context

        Returns:
            ChainResult with output and metadata
        """
        context = context or {}
        context["chain_name"] = self.name
        context["start_time"] = datetime.now()

        result = ChainResult[TOutput](status=ChainStatus.SUCCESS)
        start_time = time.time()

        try:
            # Run before_chain hooks
            await self._run_hooks("before_chain", input, context)

            # Execute steps
            current_output = input
            steps = self.get_steps()

            for step in steps:
                step_result = await self._execute_step(
                    step, current_output, context
                )
                result.add_step(step_result)

                if not step_result.success:
                    result.status = ChainStatus.FAILED
                    result.error = step_result.error
                    break

                current_output = step_result.output

            if result.status == ChainStatus.SUCCESS:
                result.output = current_output

            # Run after_chain hooks
            await self._run_hooks("after_chain", result, context)

        except Exception as e:
            result.status = ChainStatus.FAILED
            result.error = str(e)
            logger.error(f"Chain {self.name} failed: {e}")

            # Run error hooks
            await self._run_hooks("on_error", e, context)

        finally:
            result.total_duration_ms = (time.time() - start_time) * 1000

            if self.config.enable_logging:
                self._log_result(result)

        return result

    async def _execute_step(
        self,
        step: ChainStep,
        input: Any,
        context: Dict[str, Any]
    ) -> StepResult:
        """Execute a single step with error handling"""
        start_time = time.time()

        try:
            # Validate input
            if not await step.validate_input(input):
                return StepResult(
                    step_name=step.name,
                    success=False,
                    error="Input validation failed"
                )

            # Run before_step hooks
            await self._run_hooks("before_step", step, context)

            # Execute step with retries
            output = await self._execute_with_retry(step, input, context)

            duration = (time.time() - start_time) * 1000

            # Run after_step hooks
            await self._run_hooks("after_step", step, context)

            return StepResult(
                step_name=step.name,
                success=True,
                output=output,
                duration_ms=duration
            )

        except Exception as e:
            duration = (time.time() - start_time) * 1000

            # Try error handler
            fallback = await step.on_error(e, input, context)
            if fallback is not None:
                return StepResult(
                    step_name=step.name,
                    success=True,
                    output=fallback,
                    duration_ms=duration,
                    metadata={"used_fallback": True}
                )

            return StepResult(
                step_name=step.name,
                success=False,
                error=str(e),
                duration_ms=duration
            )

    async def _execute_with_retry(
        self,
        step: ChainStep,
        input: Any,
        context: Dict[str, Any]
    ) -> Any:
        """Execute step with retry logic"""
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                return await step.execute(input, context)
            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    await self._wait(self.config.retry_delay * (attempt + 1))
                    logger.warning(
                        f"Retrying step {step.name}, attempt {attempt + 2}"
                    )

        raise last_error

    async def _wait(self, seconds: float) -> None:
        """Async wait"""
        import asyncio
        await asyncio.sleep(seconds)

    async def _run_hooks(
        self,
        hook_type: str,
        data: Any,
        context: Dict[str, Any]
    ) -> None:
        """Run registered hooks"""
        for hook in self._hooks.get(hook_type, []):
            try:
                result = hook(data, context)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.warning(f"Hook {hook_type} failed: {e}")

    def add_hook(
        self,
        hook_type: str,
        hook: Callable
    ) -> None:
        """Register a hook"""
        if hook_type in self._hooks:
            self._hooks[hook_type].append(hook)

    def _log_result(self, result: ChainResult) -> None:
        """Log chain execution result"""
        status = "SUCCESS" if result.is_success else "FAILED"
        logger.info(
            f"Chain {self.name} {status} in {result.total_duration_ms:.2f}ms "
            f"({result.step_count} steps)"
        )


class CompositeChain(Chain[TInput, TOutput]):
    """
    Chain composed of other chains.

    Allows building complex pipelines from simpler chains.

    Example:
        composite = CompositeChain("full_rag", [
            RetrievalChain(retriever),
            GenerationChain(llm)
        ])
    """

    def __init__(
        self,
        name: str,
        chains: List[Chain],
        config: Optional[ChainConfig] = None
    ):
        super().__init__(name, config)
        self._chains = chains

    def get_steps(self) -> List[ChainStep]:
        """Not used for composite chains"""
        return []

    async def run(
        self,
        input: TInput,
        context: Optional[Dict[str, Any]] = None
    ) -> ChainResult[TOutput]:
        """Execute all sub-chains in sequence"""
        context = context or {}
        result = ChainResult[TOutput](status=ChainStatus.SUCCESS)
        start_time = time.time()

        current_output = input

        for chain in self._chains:
            chain_result = await chain.run(current_output, context)

            # Merge step results
            for step in chain_result.steps:
                result.add_step(step)

            if not chain_result.is_success:
                result.status = ChainStatus.FAILED
                result.error = chain_result.error
                break

            current_output = chain_result.output

        if result.status == ChainStatus.SUCCESS:
            result.output = current_output

        result.total_duration_ms = (time.time() - start_time) * 1000
        return result
