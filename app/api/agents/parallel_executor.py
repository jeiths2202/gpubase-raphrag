"""
Parallel Agent Executor
Executes multiple agents concurrently using asyncio with:
- Fan-out/fan-in pattern for parallel execution
- Timeout management per agent type
- Partial result collection on failure
- Interleaved streaming from parallel agents
"""
from typing import Dict, List, Optional, Any, AsyncGenerator, Tuple
import asyncio
import logging
import time
from datetime import datetime

from .types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk,
    TaskDAG, SubTask, TaskStatus, OrchestrationConfig,
    ParallelStreamChunk, ExecutionTrace
)
from .base import BaseAgent
from .registry import AgentRegistry, get_agent_registry
from .executor import AgentExecutor, get_executor

logger = logging.getLogger(__name__)


# Default timeout per agent type (seconds)
DEFAULT_AGENT_TIMEOUTS = {
    AgentType.RAG: 120.0,
    AgentType.IMS: 180.0,    # IMS crawler can be slow
    AgentType.VISION: 90.0,
    AgentType.CODE: 180.0,
    AgentType.PLANNER: 60.0,
}
DEFAULT_TIMEOUT = 300.0  # 5 minutes fallback


class ParallelExecutor:
    """
    Executes multiple agents in parallel with timeout and failure handling.
    """

    def __init__(
        self,
        agent_registry: Optional[AgentRegistry] = None,
        executor: Optional[AgentExecutor] = None,
        timeout_config: Optional[Dict[AgentType, float]] = None
    ):
        """
        Initialize parallel executor.

        Args:
            agent_registry: Registry to get agent instances
            executor: Executor for running agents
            timeout_config: Per-agent timeout overrides
        """
        self.agent_registry = agent_registry or get_agent_registry()
        self.executor = executor or get_executor()
        self.timeout_config = {**DEFAULT_AGENT_TIMEOUTS, **(timeout_config or {})}

    def _get_timeout(
        self,
        subtask: SubTask,
        config: Optional[OrchestrationConfig]
    ) -> float:
        """Get timeout for a subtask with priority: subtask > config > default"""
        # Priority 1: Subtask-specific override
        if subtask.timeout_override:
            return subtask.timeout_override

        # Priority 2: Config-level override
        if config and config.timeout_overrides:
            agent_key = subtask.agent_type.value
            if agent_key in config.timeout_overrides:
                return config.timeout_overrides[agent_key]

        # Priority 3: Default per agent type
        return self.timeout_config.get(subtask.agent_type, DEFAULT_TIMEOUT)

    async def execute_dag(
        self,
        dag: TaskDAG,
        context: AgentContext,
        config: Optional[OrchestrationConfig] = None,
        trace: Optional[ExecutionTrace] = None
    ) -> Dict[str, AgentResult]:
        """
        Execute all tasks in a DAG respecting dependencies.

        Args:
            dag: The task DAG to execute
            context: Base context for all agents
            config: Orchestration configuration
            trace: Execution trace to record events

        Returns:
            Dict mapping task_id to AgentResult
        """
        config = config or OrchestrationConfig()
        results: Dict[str, AgentResult] = {}

        # Execute batch by batch
        for batch_idx, batch in enumerate(dag.execution_batches):
            logger.info(f"[ParallelExecutor] Executing batch {batch_idx + 1}/{len(dag.execution_batches)} "
                       f"with {len(batch)} tasks")

            if trace:
                trace.record("batch_start", batch_idx=batch_idx, task_ids=batch)

            if len(batch) == 1 or not config.enable_parallel:
                # Sequential execution
                batch_results = await self._execute_sequential(
                    batch, dag, context, config, results, trace
                )
            else:
                # Parallel execution
                batch_results = await self._execute_parallel(
                    batch, dag, context, config, results, trace
                )

            results.update(batch_results)

            if trace:
                trace.record("batch_complete", batch_idx=batch_idx,
                            success_count=sum(1 for r in batch_results.values() if r.success),
                            fail_count=sum(1 for r in batch_results.values() if not r.success))

            # Check if we should continue after failures
            failed_tasks = [tid for tid, r in batch_results.items() if not r.success]
            if failed_tasks and not config.continue_on_failure:
                logger.warning(f"[ParallelExecutor] Stopping due to failures: {failed_tasks}")
                break

        return results

    async def _execute_sequential(
        self,
        task_ids: List[str],
        dag: TaskDAG,
        context: AgentContext,
        config: OrchestrationConfig,
        previous_results: Dict[str, AgentResult],
        trace: Optional[ExecutionTrace]
    ) -> Dict[str, AgentResult]:
        """Execute tasks sequentially"""
        results = {}

        for task_id in task_ids:
            subtask = dag.tasks.get(task_id)
            if not subtask:
                continue

            result = await self._execute_single_task(
                subtask, context, config, previous_results, trace
            )
            results[task_id] = result

            # Update DAG state
            if result.success:
                dag.mark_completed(task_id, result)
            else:
                dag.mark_failed(task_id, result.error or "Unknown error")

        return results

    async def _execute_parallel(
        self,
        task_ids: List[str],
        dag: TaskDAG,
        context: AgentContext,
        config: OrchestrationConfig,
        previous_results: Dict[str, AgentResult],
        trace: Optional[ExecutionTrace]
    ) -> Dict[str, AgentResult]:
        """Execute tasks in parallel using asyncio.gather"""
        tasks = []
        task_id_map = []

        for task_id in task_ids:
            subtask = dag.tasks.get(task_id)
            if not subtask:
                continue

            # Mark as running
            dag.mark_running(task_id)

            # Create coroutine
            coro = self._execute_single_task(
                subtask, context, config, previous_results, trace
            )
            tasks.append(coro)
            task_id_map.append(task_id)

        # Execute in parallel, capturing exceptions
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Map results back to task IDs
        results = {}
        for task_id, result in zip(task_id_map, results_list):
            if isinstance(result, Exception):
                # Convert exception to failed AgentResult
                error_result = AgentResult(
                    answer="",
                    agent_type=dag.tasks[task_id].agent_type,
                    steps=0,
                    success=False,
                    error=f"Execution error: {str(result)}",
                    execution_time=0.0
                )
                results[task_id] = error_result
                dag.mark_failed(task_id, str(result))

                if trace:
                    trace.record("task_error", task_id=task_id, error=str(result))
            else:
                results[task_id] = result
                if result.success:
                    dag.mark_completed(task_id, result)
                else:
                    dag.mark_failed(task_id, result.error or "Unknown error")

        return results

    async def _execute_single_task(
        self,
        subtask: SubTask,
        base_context: AgentContext,
        config: OrchestrationConfig,
        previous_results: Dict[str, AgentResult],
        trace: Optional[ExecutionTrace]
    ) -> AgentResult:
        """Execute a single task with timeout"""
        start_time = time.time()
        timeout = self._get_timeout(subtask, config)

        if trace:
            trace.record("task_start", task_id=subtask.task_id,
                        agent_type=subtask.agent_type,
                        description=subtask.description[:100])

        logger.info(f"[ParallelExecutor] Starting task {subtask.task_id} "
                   f"(agent={subtask.agent_type.value}, timeout={timeout}s)")

        # Build context with dependency results if needed
        task_context = self._build_task_context(subtask, base_context, previous_results)

        try:
            # Get agent from registry
            agent = self.agent_registry.get(subtask.agent_type)

            # Execute with timeout
            result = await asyncio.wait_for(
                self.executor.run(agent, subtask.description, task_context),
                timeout=timeout
            )

            execution_time = time.time() - start_time

            if trace:
                trace.record("task_complete", task_id=subtask.task_id,
                            success=result.success,
                            execution_time=execution_time,
                            steps=result.steps)

            logger.info(f"[ParallelExecutor] Task {subtask.task_id} completed "
                       f"(success={result.success}, time={execution_time:.2f}s)")

            return result

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            error_msg = f"Task timed out after {timeout}s"

            if trace:
                trace.record("task_timeout", task_id=subtask.task_id,
                            timeout=timeout, execution_time=execution_time)

            logger.warning(f"[ParallelExecutor] Task {subtask.task_id} timed out")

            return AgentResult(
                answer="",
                agent_type=subtask.agent_type,
                steps=0,
                success=False,
                error=error_msg,
                execution_time=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Execution failed: {str(e)}"

            if trace:
                trace.record("task_error", task_id=subtask.task_id,
                            error=str(e), execution_time=execution_time)

            logger.error(f"[ParallelExecutor] Task {subtask.task_id} failed: {e}")

            return AgentResult(
                answer="",
                agent_type=subtask.agent_type,
                steps=0,
                success=False,
                error=error_msg,
                execution_time=execution_time
            )

    def _build_task_context(
        self,
        subtask: SubTask,
        base_context: AgentContext,
        previous_results: Dict[str, AgentResult]
    ) -> AgentContext:
        """Build context for a task, including results from dependencies"""
        # Create new context based on base
        context = AgentContext(
            session_id=base_context.session_id,
            user_id=base_context.user_id,
            conversation_history=base_context.conversation_history.copy(),
            language=base_context.language,
            max_steps=base_context.max_steps,
            timeout=base_context.timeout,
            metadata=base_context.metadata.copy(),
            uploaded_documents=base_context.uploaded_documents.copy(),
            external_resources=base_context.external_resources.copy(),
            file_context=base_context.file_context,
            url_context=base_context.url_context,
            url_source=base_context.url_source,
            intent=base_context.intent
        )

        # Add dependency results to context if any
        if subtask.dependencies and previous_results:
            dep_context_parts = []
            for dep_id in subtask.dependencies:
                if dep_id in previous_results:
                    dep_result = previous_results[dep_id]
                    if dep_result.success and dep_result.answer:
                        dep_context_parts.append(
                            f"[Result from previous task {dep_id}]\n{dep_result.answer[:2000]}"
                        )

            if dep_context_parts:
                # Prepend dependency context to file_context
                dep_context = "\n\n".join(dep_context_parts)
                if context.file_context:
                    context.file_context = f"{dep_context}\n\n{context.file_context}"
                else:
                    context.file_context = dep_context

        return context

    async def stream_dag(
        self,
        dag: TaskDAG,
        context: AgentContext,
        config: Optional[OrchestrationConfig] = None,
        trace: Optional[ExecutionTrace] = None
    ) -> AsyncGenerator[ParallelStreamChunk, None]:
        """
        Stream execution of a DAG with interleaved parallel agent outputs.

        Args:
            dag: The task DAG to execute
            context: Base context for all agents
            config: Orchestration configuration
            trace: Execution trace to record events

        Yields:
            ParallelStreamChunk with execution events
        """
        config = config or OrchestrationConfig()
        results: Dict[str, AgentResult] = {}

        yield ParallelStreamChunk(
            chunk_type="orchestration_start",
            content=f"Starting orchestration with {len(dag.tasks)} tasks",
            metadata={
                "task_count": len(dag.tasks),
                "batch_count": len(dag.execution_batches),
                "parallelism": dag.parallelism_type.value
            }
        )

        # Execute batch by batch
        for batch_idx, batch in enumerate(dag.execution_batches):
            yield ParallelStreamChunk(
                chunk_type="batch_start",
                content=f"Starting batch {batch_idx + 1}/{len(dag.execution_batches)}",
                metadata={"batch_idx": batch_idx, "task_ids": batch}
            )

            if len(batch) == 1 or not config.enable_parallel:
                # Stream sequential execution
                async for chunk in self._stream_sequential(
                    batch, dag, context, config, results, trace
                ):
                    yield chunk
            else:
                # Stream parallel execution (interleaved)
                async for chunk in self._stream_parallel(
                    batch, dag, context, config, results, trace
                ):
                    yield chunk

            yield ParallelStreamChunk(
                chunk_type="batch_done",
                metadata={"batch_idx": batch_idx}
            )

            # Check if we should continue after failures
            failed_tasks = [tid for tid in batch
                          if tid in results and not results[tid].success]
            if failed_tasks and not config.continue_on_failure:
                yield ParallelStreamChunk(
                    chunk_type="error",
                    content=f"Stopping due to failures in tasks: {failed_tasks}"
                )
                break

    async def _stream_sequential(
        self,
        task_ids: List[str],
        dag: TaskDAG,
        context: AgentContext,
        config: OrchestrationConfig,
        results: Dict[str, AgentResult],
        trace: Optional[ExecutionTrace]
    ) -> AsyncGenerator[ParallelStreamChunk, None]:
        """Stream sequential task execution"""
        for task_id in task_ids:
            subtask = dag.tasks.get(task_id)
            if not subtask:
                continue

            async for chunk in self._stream_single_task(
                subtask, context, config, results, trace
            ):
                yield chunk

            # Update results from trace or stored result
            if task_id in results:
                if results[task_id].success:
                    dag.mark_completed(task_id, results[task_id])
                else:
                    dag.mark_failed(task_id, results[task_id].error or "Unknown error")

    async def _stream_parallel(
        self,
        task_ids: List[str],
        dag: TaskDAG,
        context: AgentContext,
        config: OrchestrationConfig,
        results: Dict[str, AgentResult],
        trace: Optional[ExecutionTrace]
    ) -> AsyncGenerator[ParallelStreamChunk, None]:
        """Stream parallel task execution with interleaved output"""
        # Create streams for each task
        streams: Dict[str, AsyncGenerator] = {}
        active_streams: Dict[str, bool] = {}

        for task_id in task_ids:
            subtask = dag.tasks.get(task_id)
            if not subtask:
                continue

            dag.mark_running(task_id)
            streams[task_id] = self._stream_single_task(
                subtask, context, config, results, trace
            )
            active_streams[task_id] = True

        # Use asyncio.Queue to interleave streams
        queue: asyncio.Queue[Tuple[str, Optional[ParallelStreamChunk]]] = asyncio.Queue()

        async def consume_stream(task_id: str, stream: AsyncGenerator):
            """Consume a single stream and put chunks in queue"""
            try:
                async for chunk in stream:
                    await queue.put((task_id, chunk))
            except Exception as e:
                logger.error(f"[ParallelExecutor] Stream error for {task_id}: {e}")
                await queue.put((task_id, ParallelStreamChunk(
                    chunk_type="error",
                    task_id=task_id,
                    content=f"Stream error: {str(e)}"
                )))
            finally:
                await queue.put((task_id, None))  # Signal stream complete

        # Start all stream consumers
        consumers = [
            asyncio.create_task(consume_stream(tid, stream))
            for tid, stream in streams.items()
        ]

        # Yield interleaved chunks
        completed_count = 0
        total_streams = len(streams)

        while completed_count < total_streams:
            try:
                task_id, chunk = await asyncio.wait_for(queue.get(), timeout=300.0)

                if chunk is None:
                    # Stream completed
                    completed_count += 1
                    active_streams[task_id] = False
                    continue

                # Tag chunk with task_id
                chunk.task_id = task_id
                yield chunk

            except asyncio.TimeoutError:
                logger.warning("[ParallelExecutor] Queue timeout waiting for chunks")
                break

        # Wait for all consumers to finish
        await asyncio.gather(*consumers, return_exceptions=True)

        # Update DAG state from results
        for task_id in task_ids:
            if task_id in results:
                if results[task_id].success:
                    dag.mark_completed(task_id, results[task_id])
                else:
                    dag.mark_failed(task_id, results[task_id].error or "Unknown error")

    async def _stream_single_task(
        self,
        subtask: SubTask,
        base_context: AgentContext,
        config: OrchestrationConfig,
        results: Dict[str, AgentResult],
        trace: Optional[ExecutionTrace]
    ) -> AsyncGenerator[ParallelStreamChunk, None]:
        """Stream a single task execution"""
        start_time = time.time()
        timeout = self._get_timeout(subtask, config)

        yield ParallelStreamChunk(
            chunk_type="agent_start",
            task_id=subtask.task_id,
            agent_type=subtask.agent_type,
            content=subtask.description[:100],
            metadata={"timeout": timeout}
        )

        if trace:
            trace.record("task_start", task_id=subtask.task_id,
                        agent_type=subtask.agent_type)

        # Build context
        task_context = self._build_task_context(subtask, base_context, results)

        try:
            agent = self.agent_registry.get(subtask.agent_type)

            # Collect answer parts for final result
            answer_parts = []
            sources = []
            steps = 0

            # Stream with timeout
            stream_task = agent.stream(subtask.description, task_context)
            async for chunk in self._timeout_stream(stream_task, timeout):
                # Wrap agent chunk in parallel chunk
                yield ParallelStreamChunk(
                    chunk_type="agent_chunk",
                    task_id=subtask.task_id,
                    agent_type=subtask.agent_type,
                    agent_chunk=chunk
                )

                # Collect for result
                if chunk.chunk_type == "text" and chunk.content:
                    answer_parts.append(chunk.content)
                elif chunk.chunk_type == "sources" and chunk.sources:
                    sources.extend(chunk.sources)
                elif chunk.chunk_type == "done" and chunk.metadata:
                    steps = chunk.metadata.get("steps", 0)

            execution_time = time.time() - start_time

            # Build result
            result = AgentResult(
                answer="".join(answer_parts),
                agent_type=subtask.agent_type,
                steps=steps,
                sources=sources,
                success=True,
                execution_time=execution_time
            )
            results[subtask.task_id] = result

            yield ParallelStreamChunk(
                chunk_type="agent_done",
                task_id=subtask.task_id,
                agent_type=subtask.agent_type,
                metadata={
                    "success": True,
                    "execution_time": execution_time,
                    "answer_length": len(result.answer)
                }
            )

            if trace:
                trace.record("task_complete", task_id=subtask.task_id,
                            success=True, execution_time=execution_time)

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            error_msg = f"Task timed out after {timeout}s"

            result = AgentResult(
                answer="",
                agent_type=subtask.agent_type,
                steps=0,
                success=False,
                error=error_msg,
                execution_time=execution_time
            )
            results[subtask.task_id] = result

            yield ParallelStreamChunk(
                chunk_type="agent_done",
                task_id=subtask.task_id,
                agent_type=subtask.agent_type,
                content=error_msg,
                metadata={"success": False, "timeout": True}
            )

            if trace:
                trace.record("task_timeout", task_id=subtask.task_id, timeout=timeout)

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Execution failed: {str(e)}"

            result = AgentResult(
                answer="",
                agent_type=subtask.agent_type,
                steps=0,
                success=False,
                error=error_msg,
                execution_time=execution_time
            )
            results[subtask.task_id] = result

            yield ParallelStreamChunk(
                chunk_type="agent_done",
                task_id=subtask.task_id,
                agent_type=subtask.agent_type,
                content=error_msg,
                metadata={"success": False, "error": str(e)}
            )

            if trace:
                trace.record("task_error", task_id=subtask.task_id, error=str(e))

    async def _timeout_stream(
        self,
        stream: AsyncGenerator[AgentStreamChunk, None],
        timeout: float
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Wrap a stream with timeout"""
        deadline = time.time() + timeout

        async for chunk in stream:
            if time.time() > deadline:
                raise asyncio.TimeoutError()
            yield chunk


# Singleton instance
_parallel_executor_instance: Optional[ParallelExecutor] = None


def get_parallel_executor(
    agent_registry: Optional[AgentRegistry] = None,
    executor: Optional[AgentExecutor] = None
) -> ParallelExecutor:
    """Get the global parallel executor instance.

    Args:
        agent_registry: Optional registry override (used on first call)
        executor: Optional executor override (used on first call)

    Returns:
        ParallelExecutor singleton instance
    """
    global _parallel_executor_instance
    if _parallel_executor_instance is None:
        _parallel_executor_instance = ParallelExecutor(
            agent_registry=agent_registry,
            executor=executor
        )
    return _parallel_executor_instance
