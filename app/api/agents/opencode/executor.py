"""
OpenCode Pipeline Executor

Orchestrates the 5-step mandatory workflow with:
- Automatic hallucination detection
- Retry logic (max 3 attempts)
- Detailed progress streaming
- PostgreSQL execution logging
"""

import time
import logging
import asyncio
from typing import Optional, AsyncGenerator, List
from datetime import datetime

from .types import (
    OpenCodeContext,
    OpenCodeResult,
    StepResult,
    StepStatus,
    AnswerStatus,
    OpenCodeConfig,
)
from .steps import (
    KeywordExtractionStep,
    SummarySearchStep,
    PDFVerificationStep,
    ToolSelectionStep,
    AnswerGenerationStep,
    PIPELINE_STEPS,
)
from .hallucination_detector import HallucinationDetector, get_hallucination_detector

from ..types import AgentStreamChunk, AgentContext

logger = logging.getLogger(__name__)


class OpenCodeExecutor:
    """
    Executes the OpenCode 5-step mandatory workflow.

    Features:
    - Sequential step execution with progress streaming
    - Automatic hallucination detection after Step 5
    - Retry logic with max 3 attempts
    - Detailed execution logging for PostgreSQL
    """

    def __init__(
        self,
        config: Optional[OpenCodeConfig] = None,
        hallucination_detector: Optional[HallucinationDetector] = None,
    ):
        self.config = config or OpenCodeConfig()
        self.detector = hallucination_detector or get_hallucination_detector()

        # Initialize steps
        self.steps = [
            KeywordExtractionStep(),
            SummarySearchStep(),
            PDFVerificationStep(),
            ToolSelectionStep(),
            AnswerGenerationStep(),
        ]

    async def execute(
        self,
        query: str,
        agent_context: AgentContext,
    ) -> OpenCodeResult:
        """
        Execute the full 5-step pipeline with hallucination detection and retry.

        Args:
            query: User query
            agent_context: Agent execution context

        Returns:
            OpenCodeResult with answer, sources, and verification status
        """
        start_time = time.time()

        # Create OpenCode context
        context = OpenCodeContext(
            query=query,
            session_id=agent_context.session_id,
            user_id=agent_context.user_id,
            language=agent_context.language,
            config=self.config,
            file_context=agent_context.file_context,
            url_context=agent_context.url_context,
        )

        # Handle file_context priority (Session Context vs Database)
        if context.file_context:
            logger.info(f"[OpenCode] File context provided - will prioritize attached content")

        # Execute with retry logic
        result = await self._execute_with_retry(context)

        # Calculate total execution time
        result.execution_time_ms = (time.time() - start_time) * 1000

        # Log execution to PostgreSQL
        await self._log_execution(context, result)

        return result

    async def stream(
        self,
        query: str,
        agent_context: AgentContext,
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        Stream the 5-step pipeline execution with detailed progress.

        Yields AgentStreamChunk for each step and sub-step.
        """
        start_time = time.time()

        # Create OpenCode context
        context = OpenCodeContext(
            query=query,
            session_id=agent_context.session_id,
            user_id=agent_context.user_id,
            language=agent_context.language,
            config=self.config,
            file_context=agent_context.file_context,
            url_context=agent_context.url_context,
        )

        # Handle file_context priority
        if context.file_context:
            yield AgentStreamChunk(
                chunk_type="status",
                content="Processing attached file context...",
                metadata={"has_file_context": True}
            )

        attempt = 0
        max_attempts = context.config.max_retries + 1

        while attempt < max_attempts:
            attempt += 1
            context.retry_count = attempt - 1

            # Stream pipeline execution
            async for chunk in self._stream_pipeline(context, attempt, max_attempts):
                yield chunk

            # Check the final step result
            if context.step_history and context.step_history[-1].status == StepStatus.COMPLETED:
                step_output = context.step_history[-1].output
                if step_output and not step_output.get("blocked"):
                    answer = step_output.get("answer", "")
                    sources = step_output.get("sources", [])

                    # Hallucination check
                    yield AgentStreamChunk(
                        chunk_type="status",
                        content="Verifying answer grounding...",
                        metadata={"step": "hallucination_check", "attempt": attempt}
                    )

                    check_result = await self.detector.check(answer, context)
                    context.hallucination_check = check_result

                    if check_result.is_hallucination and check_result.retry_recommended:
                        yield AgentStreamChunk(
                            chunk_type="status",
                            content=f"Hallucination detected (attempt {attempt}/{max_attempts}). Retrying...",
                            metadata={
                                "hallucination_detected": True,
                                "reasons": check_result.reasons,
                                "attempt": attempt,
                                "max_attempts": max_attempts,
                            }
                        )
                        # Reset step history for retry
                        context.step_history = []
                        context.summary_searches = []
                        context.pdf_verifications = []
                        continue  # Retry

                    # No hallucination or max retries reached
                    # Stream the answer
                    yield AgentStreamChunk(
                        chunk_type="text",
                        content=answer,
                    )

                    # Stream sources
                    if sources:
                        yield AgentStreamChunk(
                            chunk_type="sources",
                            sources=sources[:10],
                        )

                    # Stream verification status
                    verification_passed = not check_result.is_hallucination
                    yield AgentStreamChunk(
                        chunk_type="status",
                        content=f"Verification: {'PASSED' if verification_passed else 'FAILED'}",
                        metadata={
                            "verification_status": "PASSED" if verification_passed else "FAILED",
                            "hallucination_check": check_result.to_dict(),
                        }
                    )

                    break  # Success, exit retry loop
                else:
                    # Answer blocked (no sources)
                    blocked_message = step_output.get("answer", "No information found.")
                    yield AgentStreamChunk(
                        chunk_type="text",
                        content=blocked_message,
                    )
                    break
            else:
                # Pipeline failed
                error = context.step_history[-1].error if context.step_history else "Unknown error"
                yield AgentStreamChunk(
                    chunk_type="error",
                    content=f"Pipeline failed: {error}",
                )
                break

        # Stream completion
        execution_time = (time.time() - start_time) * 1000
        yield AgentStreamChunk(
            chunk_type="done",
            metadata={
                "execution_time_ms": execution_time,
                "steps_executed": len(context.step_history),
                "retry_count": context.retry_count,
            }
        )

    async def _execute_with_retry(self, context: OpenCodeContext) -> OpenCodeResult:
        """Execute pipeline with automatic retry on hallucination detection"""
        max_attempts = context.config.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            context.retry_count = attempt - 1
            logger.info(f"[OpenCode] Attempt {attempt}/{max_attempts}")

            # Execute all 5 steps
            for step in self.steps:
                result = await step.execute(context)
                context.step_history.append(result)

                if result.status == StepStatus.FAILED:
                    logger.error(f"[OpenCode] Step {step.name} failed: {result.error}")
                    return self._create_failed_result(context, result.error)

            # Get answer from Step 5
            step5_output = context.step_history[-1].output
            if not step5_output or step5_output.get("blocked"):
                return self._create_blocked_result(context, step5_output)

            answer = step5_output.get("answer", "")
            sources = step5_output.get("sources", [])

            # Hallucination check
            check_result = await self.detector.check(answer, context)
            context.hallucination_check = check_result

            if check_result.is_hallucination:
                logger.warning(
                    f"[OpenCode] Hallucination detected (attempt {attempt}): {check_result.reasons}"
                )
                if attempt < max_attempts:
                    # Reset for retry
                    context.step_history = []
                    context.summary_searches = []
                    context.pdf_verifications = []
                    continue

            # Success or max retries reached
            return self._create_success_result(context, answer, sources, check_result)

        # Should not reach here, but just in case
        return self._create_failed_result(context, "Max retries exceeded")

    async def _stream_pipeline(
        self,
        context: OpenCodeContext,
        attempt: int,
        max_attempts: int,
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream individual step execution"""
        for step in self.steps:
            # Stream step start
            yield AgentStreamChunk(
                chunk_type="status",
                content=f"Step {step.step_number}/5: {step.display_names.get(context.language, step.name)}",
                metadata={
                    "step_number": step.step_number,
                    "step_name": step.name,
                    "status": "running",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                }
            )

            # Execute step
            result = await step.execute(context)
            context.step_history.append(result)

            # Stream step result
            yield AgentStreamChunk(
                chunk_type="status",
                content=f"Step {step.step_number}/5: {result.status.value}",
                metadata={
                    "step_number": step.step_number,
                    "step_name": step.name,
                    "status": result.status.value,
                    "latency_ms": result.latency_ms,
                    **result.metadata,
                }
            )

            if result.status == StepStatus.FAILED:
                yield AgentStreamChunk(
                    chunk_type="error",
                    content=f"Step {step.name} failed: {result.error}",
                )
                return

    def _create_success_result(
        self,
        context: OpenCodeContext,
        answer: str,
        sources: List[dict],
        check_result,
    ) -> OpenCodeResult:
        """Create successful result"""
        verification_passed = not check_result.is_hallucination

        return OpenCodeResult(
            answer=answer,
            sources=sources,
            status=AnswerStatus.SUCCESS,
            confidence=1.0 - check_result.confidence,
            steps_executed=len(context.step_history),
            retry_count=context.retry_count,
            hallucination_checked=True,
            vision_used=context.tool_selection and context.tool_selection.vision_required,
            verification_checklist={
                "all_keywords_extracted": context.keywords is not None,
                "all_summary_documents_searched": len(context.summary_searches) > 0,
                "all_relevant_pdfs_opened": len(context.pdf_verifications) > 0,
                "pages_verified": any(pdf.verified_chunks for pdf in context.pdf_verifications),
                "correct_tools_used": context.tool_selection is not None,
                "all_claims_sourced": len(sources) > 0,
                "no_hallucination_detected": verification_passed,
            },
            metadata={
                "run_id": context.run_id,
                "hallucination_check": check_result.to_dict(),
            }
        )

    def _create_blocked_result(
        self,
        context: OpenCodeContext,
        step_output: Optional[dict],
    ) -> OpenCodeResult:
        """Create blocked result (no sources found)"""
        answer = step_output.get("answer", "No information found.") if step_output else "No information found."

        return OpenCodeResult(
            answer=answer,
            sources=[],
            status=AnswerStatus.BLOCKED,
            confidence=0.0,
            steps_executed=len(context.step_history),
            retry_count=context.retry_count,
            hallucination_checked=False,
            failure_reason="No verified sources found",
            verification_checklist={
                "all_keywords_extracted": context.keywords is not None,
                "all_summary_documents_searched": len(context.summary_searches) > 0,
                "all_relevant_pdfs_opened": False,
                "pages_verified": False,
                "correct_tools_used": False,
                "all_claims_sourced": False,
                "no_hallucination_detected": False,
            },
            metadata={"run_id": context.run_id}
        )

    def _create_failed_result(
        self,
        context: OpenCodeContext,
        error: str,
    ) -> OpenCodeResult:
        """Create failed result"""
        return OpenCodeResult(
            answer="",
            sources=[],
            status=AnswerStatus.RETRY if context.retry_count < context.config.max_retries else AnswerStatus.BLOCKED,
            confidence=0.0,
            steps_executed=len(context.step_history),
            retry_count=context.retry_count,
            hallucination_checked=False,
            failure_reason=error,
            metadata={"run_id": context.run_id, "error": error}
        )

    async def _log_execution(self, context: OpenCodeContext, result: OpenCodeResult) -> None:
        """Log execution to PostgreSQL"""
        try:
            from ...infrastructure.postgres.opencode_execution_log_repository import (
                get_opencode_log_repository
            )
            repo = await get_opencode_log_repository()

            await repo.log_execution(
                run_id=context.run_id,
                user_id=context.user_id,
                session_id=context.session_id,
                query=context.query,
                language=context.language,
                status=result.status.value,
                answer=result.answer,
                sources=result.sources,
                steps_executed=result.steps_executed,
                retry_count=result.retry_count,
                hallucination_checked=result.hallucination_checked,
                vision_used=result.vision_used,
                execution_time_ms=result.execution_time_ms,
                verification_checklist=result.verification_checklist,
                step_history=[s.to_dict() for s in context.step_history],
                hallucination_check=context.hallucination_check.to_dict() if context.hallucination_check else None,
            )

            logger.info(f"[OpenCode] Execution logged: {context.run_id}")

        except Exception as e:
            # Non-blocking - log error but don't fail the request
            logger.warning(f"[OpenCode] Failed to log execution: {e}")


# Singleton instance
_opencode_executor: Optional[OpenCodeExecutor] = None


def get_opencode_executor(config: Optional[OpenCodeConfig] = None) -> OpenCodeExecutor:
    """Get or create the OpenCode executor singleton"""
    global _opencode_executor
    if _opencode_executor is None:
        _opencode_executor = OpenCodeExecutor(config=config)
    return _opencode_executor
