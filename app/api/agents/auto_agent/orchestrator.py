"""
Auto Agent Orchestrator

Enterprise-grade AI orchestration system implementing a Meta-Agent (Auto Agent)
that coordinates multiple sub-agents with mandatory Planner and Verifier agents.

Architecture:
    User Prompt → AutoAgentOrchestrator
        ↓
    Memory Manager → Load context
        ↓
    Planner Agent → Create ExecutionPlan (MANDATORY)
        ↓
    Parallel Executor → Execute sub-agents
        ↓
    Verifier Agent → Validate results (MANDATORY)
        ↓
    Answer Composer → Strip reasoning, format response
        ↓
    Final Response with Next Actions
"""
import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, AsyncGenerator

from ..types import (
    AgentType, AgentContext, AgentResult, SubTask, TaskDAG, TaskStatus,
    AgentStreamChunk
)
from ..registry import get_agent_registry
from ..parallel_executor import get_parallel_executor
from .types import (
    ExecutionPlan, PlannedTask, VerificationResult, VerificationDecision,
    AutoAgentMemoryContext, ComposedAnswer, AutoAgentStreamChunk,
    AutoAgentExecutionResult, PlanStatus, EnhancedRetryConfig,
    ClarificationRequest
)
from .planner_agent import get_auto_planner_agent
from .verifier_agent import get_verifier_agent
from .answer_composer import get_answer_composer
from .memory_manager import get_memory_manager
from .confidence_scorer import get_confidence_scorer

logger = logging.getLogger(__name__)


class AutoAgentOrchestrator:
    """
    Main orchestrator for the Auto Agent system.

    Coordinates:
    - Planner Agent (MANDATORY first)
    - Sub-agent execution (parallel when possible)
    - Verifier Agent (MANDATORY after execution)
    - Answer Composer (strips reasoning)
    - Memory integration
    """

    def __init__(
        self,
        llm_adapter=None,
        max_retries: int = 2,
        max_replans: int = 1
    ):
        """
        Initialize the Auto Agent Orchestrator.

        Args:
            llm_adapter: LLM adapter for agents
            max_retries: Maximum retry attempts per task
            max_replans: Maximum full replan attempts
        """
        self._llm_adapter = llm_adapter
        self.max_retries = max_retries
        self.max_replans = max_replans

        # Lazy-loaded components
        self._planner = None
        self._verifier = None
        self._composer = None
        self._memory_manager = None
        self._confidence_scorer = None
        self._parallel_executor = None

    @property
    def planner(self):
        if self._planner is None:
            self._planner = get_auto_planner_agent(self._llm_adapter)
        return self._planner

    @property
    def verifier(self):
        if self._verifier is None:
            self._verifier = get_verifier_agent(self._llm_adapter)
        return self._verifier

    @property
    def composer(self):
        if self._composer is None:
            self._composer = get_answer_composer(self._llm_adapter)
        return self._composer

    @property
    def memory_manager(self):
        if self._memory_manager is None:
            self._memory_manager = get_memory_manager()
        return self._memory_manager

    @property
    def confidence_scorer(self):
        if self._confidence_scorer is None:
            self._confidence_scorer = get_confidence_scorer()
        return self._confidence_scorer

    @property
    def parallel_executor(self):
        if self._parallel_executor is None:
            self._parallel_executor = get_parallel_executor()
        return self._parallel_executor

    async def execute(
        self,
        task: str,
        context: AgentContext,
        config: Optional[EnhancedRetryConfig] = None
    ) -> AutoAgentExecutionResult:
        """
        Execute the Auto Agent orchestration flow.

        Args:
            task: User's task/question
            context: Agent execution context
            config: Optional retry configuration

        Returns:
            AutoAgentExecutionResult with answer and metadata
        """
        start_time = time.time()
        execution_id = str(uuid.uuid4())

        result = AutoAgentExecutionResult(
            execution_id=execution_id,
            original_task=task,
            started_at=datetime.now(timezone.utc)
        )

        try:
            # 1. Load memory context
            logger.info(f"[AutoAgent] Starting execution {execution_id}")
            memory_ctx = await self.memory_manager.get_context_for_planner(
                user_id=context.user_id,
                session_id=context.session_id,
                task=task
            )

            # 2. MANDATORY: Run Planner Agent
            logger.info("[AutoAgent] Phase: Planning")
            plan = await self.planner.create_plan(task, memory_ctx, context)
            result.plan = plan

            # Use plan's retry policy or provided config
            retry_config = config or plan.retry_policy

            # 3. Execute sub-agents
            logger.info(f"[AutoAgent] Phase: Execution ({len(plan.decomposed_tasks)} tasks)")
            task_results = await self._execute_plan(plan, context)
            result.task_results = task_results

            # Collect sources for verification
            all_sources = self._collect_all_sources(task_results)

            # 4. MANDATORY: Run Verifier Agent
            logger.info("[AutoAgent] Phase: Verification")
            verification = await self.verifier.verify(
                original_task=task,
                aggregated_results=task_results,
                sources=all_sources,
                context=context
            )
            result.verification = verification

            # 5. Handle verification decision
            if verification.decision == VerificationDecision.PARTIAL_RETRY:
                logger.info("[AutoAgent] Verification: Partial retry needed")
                task_results, verification = await self._handle_partial_retry(
                    plan, task_results, verification, context, retry_config
                )
                result.task_results = task_results
                result.verification = verification
                result.retry_attempts += 1

            elif verification.decision == VerificationDecision.FULL_REPLAN:
                logger.info("[AutoAgent] Verification: Full replan needed")
                if result.replan_attempts < retry_config.max_replans:
                    task_results, plan, verification = await self._handle_full_replan(
                        task, memory_ctx, context, retry_config
                    )
                    result.plan = plan
                    result.task_results = task_results
                    result.verification = verification
                    result.replan_attempts += 1

            # 6. Compose final answer
            logger.info("[AutoAgent] Phase: Composition")
            answer = await self.composer.compose(
                plan=plan,
                task_results=task_results,
                verification=verification,
                context=context
            )
            result.answer = answer

            # 7. Store in memory for learning
            await self.memory_manager.store_execution_result(
                user_id=context.user_id,
                session_id=context.session_id,
                task=task,
                plan=plan,
                verification=verification,
                answer=answer
            )

            result.success = True
            result.total_execution_time = time.time() - start_time
            result.completed_at = datetime.now(timezone.utc)

            logger.info(
                f"[AutoAgent] Execution complete: {result.total_execution_time:.2f}s, "
                f"confidence={verification.overall_score:.0%}"
            )

            return result

        except Exception as e:
            logger.error(f"[AutoAgent] Execution failed: {e}", exc_info=True)
            result.success = False
            result.error = str(e)
            result.total_execution_time = time.time() - start_time
            result.completed_at = datetime.now(timezone.utc)

            # Create fallback answer
            result.answer = ComposedAnswer(
                content=f"처리 중 오류가 발생했습니다: {str(e)}",
                language=context.language,
                confidence=0.0
            )

            return result

    async def stream(
        self,
        task: str,
        context: AgentContext,
        config: Optional[EnhancedRetryConfig] = None,
        skip_clarification: bool = False
    ) -> AsyncGenerator[AutoAgentStreamChunk, None]:
        """
        Stream the Auto Agent orchestration flow.

        Args:
            task: User's task/question
            context: Agent execution context
            config: Optional retry configuration
            skip_clarification: If True, skip the clarification check

        Yields:
            AutoAgentStreamChunk with progress updates
        """
        start_time = time.time()
        execution_id = str(uuid.uuid4())

        try:
            # 0. Query Clarification Check (Human-in-the-loop)
            if not skip_clarification:
                clarification = await self.planner.check_query_clarity(task, context)

                if clarification:
                    logger.info(
                        f"[AutoAgent] Clarification needed: {clarification.ambiguity_type.value}"
                    )
                    yield AutoAgentStreamChunk(
                        chunk_type="clarification_needed",
                        phase="clarification",
                        content=clarification.clarification_question,
                        clarification_data=clarification.to_dict()
                    )
                    # Stop here and wait for user response
                    # The frontend will handle user selection and re-call with refined query
                    return

            # 1. Planning phase
            yield AutoAgentStreamChunk(
                chunk_type="planning_start",
                phase="planning",
                content="Creating execution plan..."
            )

            memory_ctx = await self.memory_manager.get_context_for_planner(
                user_id=context.user_id,
                session_id=context.session_id,
                task=task
            )

            plan = await self.planner.create_plan(task, memory_ctx, context)

            yield AutoAgentStreamChunk(
                chunk_type="planning_done",
                phase="planning",
                content=f"Plan created: {len(plan.decomposed_tasks)} tasks",
                plan_data={
                    "plan_id": plan.plan_id,
                    "task_count": len(plan.decomposed_tasks),
                    "parallelism": plan.parallelism_strategy.value,
                    "tasks": [
                        {"id": t.task_id, "description": t.description, "agent": t.agent_type.value}
                        for t in plan.decomposed_tasks
                    ]
                }
            )

            retry_config = config or plan.retry_policy

            # 2. Execution phase
            yield AutoAgentStreamChunk(
                chunk_type="execution_start",
                phase="execution",
                content="Executing tasks..."
            )

            task_results = {}
            total_tasks = len(plan.decomposed_tasks)
            completed = 0

            # Execute batch by batch
            for batch_idx, batch in enumerate(plan.execution_batches):
                yield AutoAgentStreamChunk(
                    chunk_type="batch_start",
                    phase="execution",
                    content=f"Batch {batch_idx + 1}/{len(plan.execution_batches)}",
                    metadata={"batch": batch_idx + 1, "tasks": batch}
                )

                # Execute batch
                batch_results = await self._execute_batch(batch, plan, context)
                task_results.update(batch_results)
                completed += len(batch)

                for task_id, result in batch_results.items():
                    yield AutoAgentStreamChunk(
                        chunk_type="agent_done",
                        phase="execution",
                        task_id=task_id,
                        agent_type=result.agent_type.value,
                        progress=completed / total_tasks,
                        content=f"Task {task_id} completed"
                    )

            # 3. Verification phase
            yield AutoAgentStreamChunk(
                chunk_type="verification_start",
                phase="verification",
                content="Verifying results..."
            )

            all_sources = self._collect_all_sources(task_results)
            verification = await self.verifier.verify(
                original_task=task,
                aggregated_results=task_results,
                sources=all_sources,
                context=context
            )

            yield AutoAgentStreamChunk(
                chunk_type="verification_done",
                phase="verification",
                content=f"Verification: {verification.decision.value}",
                verification_data={
                    "decision": verification.decision.value,
                    "score": verification.overall_score,
                    "issues": len(verification.issues)
                }
            )

            # 4. Handle retries if needed
            if verification.decision == VerificationDecision.PARTIAL_RETRY:
                yield AutoAgentStreamChunk(
                    chunk_type="retry_start",
                    phase="retry",
                    content=f"Retrying {len(verification.tasks_to_retry)} tasks..."
                )

                task_results, verification = await self._handle_partial_retry(
                    plan, task_results, verification, context, retry_config
                )

            # 5. Composition phase
            yield AutoAgentStreamChunk(
                chunk_type="composition_start",
                phase="composition",
                content="Composing answer..."
            )

            answer = await self.composer.compose(
                plan=plan,
                task_results=task_results,
                verification=verification,
                context=context
            )

            yield AutoAgentStreamChunk(
                chunk_type="composition_done",
                phase="composition",
                content=answer.content,
                sources=answer.sources
            )

            # 6. Next actions
            if answer.next_actions:
                yield AutoAgentStreamChunk(
                    chunk_type="next_actions",
                    phase="done",
                    next_actions=answer.next_actions
                )

            # 7. Done
            yield AutoAgentStreamChunk(
                chunk_type="done",
                phase="done",
                metadata={
                    "execution_time": time.time() - start_time,
                    "confidence": verification.overall_score,
                    "task_count": len(plan.decomposed_tasks)
                }
            )

            # Store for learning
            await self.memory_manager.store_execution_result(
                user_id=context.user_id,
                session_id=context.session_id,
                task=task,
                plan=plan,
                verification=verification,
                answer=answer
            )

        except Exception as e:
            logger.error(f"[AutoAgent] Stream failed: {e}", exc_info=True)
            yield AutoAgentStreamChunk(
                chunk_type="error",
                phase="error",
                error_message=str(e)
            )

    async def _execute_plan(
        self,
        plan: ExecutionPlan,
        context: AgentContext
    ) -> Dict[str, AgentResult]:
        """Execute all tasks in the plan"""
        task_results: Dict[str, AgentResult] = {}

        for batch in plan.execution_batches:
            batch_results = await self._execute_batch(batch, plan, context)
            task_results.update(batch_results)

        return task_results

    async def _execute_batch(
        self,
        batch: List[str],
        plan: ExecutionPlan,
        context: AgentContext
    ) -> Dict[str, AgentResult]:
        """Execute a batch of tasks in parallel"""
        batch_results: Dict[str, AgentResult] = {}

        # Create coroutines for parallel execution
        async def execute_task(task_id: str) -> tuple:
            planned_task = plan.get_task(task_id)
            if not planned_task:
                return task_id, AgentResult(
                    answer="",
                    agent_type=AgentType.RAG,
                    steps=0,
                    execution_time=0.0,
                    success=False,
                    error=f"Task {task_id} not found in plan"
                )

            try:
                # Get agent from registry
                registry = get_agent_registry()
                agent = registry.get(planned_task.agent_type)

                # Execute with timeout
                timeout = planned_task.timeout_override or context.timeout
                result = await asyncio.wait_for(
                    agent.execute(planned_task.description, context),
                    timeout=timeout
                )
                return task_id, result

            except asyncio.TimeoutError:
                return task_id, AgentResult(
                    answer="",
                    agent_type=planned_task.agent_type,
                    steps=0,
                    execution_time=timeout,
                    success=False,
                    error="Task execution timed out"
                )
            except Exception as e:
                return task_id, AgentResult(
                    answer="",
                    agent_type=planned_task.agent_type,
                    steps=0,
                    execution_time=0.0,
                    success=False,
                    error=str(e)
                )

        # Execute batch in parallel
        tasks = [execute_task(task_id) for task_id in batch]
        results = await asyncio.gather(*tasks)

        for task_id, result in results:
            batch_results[task_id] = result

        return batch_results

    async def _handle_partial_retry(
        self,
        plan: ExecutionPlan,
        task_results: Dict[str, AgentResult],
        verification: VerificationResult,
        context: AgentContext,
        config: EnhancedRetryConfig
    ) -> tuple:
        """Handle partial retry for failed tasks"""
        tasks_to_retry = verification.tasks_to_retry
        retry_count = 0

        while tasks_to_retry and retry_count < config.max_retries:
            retry_count += 1
            logger.info(f"[AutoAgent] Retry attempt {retry_count} for {len(tasks_to_retry)} tasks")

            # Apply backoff
            if retry_count > 1:
                delay = min(
                    config.initial_delay * (config.backoff_factor ** (retry_count - 1)),
                    config.max_delay
                )
                await asyncio.sleep(delay)

            # Retry failed tasks
            retry_results = await self._execute_batch(tasks_to_retry, plan, context)
            task_results.update(retry_results)

            # Re-verify
            all_sources = self._collect_all_sources(task_results)
            verification = await self.verifier.verify(
                original_task=plan.original_task,
                aggregated_results=task_results,
                sources=all_sources,
                context=context
            )

            if verification.decision == VerificationDecision.ACCEPT:
                break

            tasks_to_retry = verification.tasks_to_retry

        return task_results, verification

    async def _handle_full_replan(
        self,
        task: str,
        memory_ctx: AutoAgentMemoryContext,
        context: AgentContext,
        config: EnhancedRetryConfig
    ) -> tuple:
        """Handle full replan scenario"""
        logger.info("[AutoAgent] Creating new plan after failure")

        # Add failure context to memory
        memory_ctx.domain_context = (memory_ctx.domain_context or "") + \
            " [Previous plan failed, creating new approach]"

        # Create new plan
        plan = await self.planner.create_plan(task, memory_ctx, context)

        # Execute new plan
        task_results = await self._execute_plan(plan, context)

        # Verify new results
        all_sources = self._collect_all_sources(task_results)
        verification = await self.verifier.verify(
            original_task=task,
            aggregated_results=task_results,
            sources=all_sources,
            context=context
        )

        return task_results, plan, verification

    def _collect_all_sources(
        self,
        task_results: Dict[str, AgentResult]
    ) -> List[Dict[str, Any]]:
        """Collect all sources from task results"""
        all_sources = []
        for result in task_results.values():
            all_sources.extend(result.sources)
        return all_sources


# Singleton instance
_orchestrator: Optional[AutoAgentOrchestrator] = None


def get_auto_agent_orchestrator(llm_adapter=None) -> AutoAgentOrchestrator:
    """Get or create the Auto Agent Orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AutoAgentOrchestrator(llm_adapter=llm_adapter)
    elif llm_adapter and _orchestrator._llm_adapter is None:
        _orchestrator._llm_adapter = llm_adapter
    return _orchestrator
