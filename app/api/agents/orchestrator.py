"""
Agent Orchestrator
Manages agent selection and execution flow.
Supports both simple single-agent and enterprise multi-agent orchestration.
"""
from typing import Dict, List, Optional, AsyncGenerator
import logging
import re
import time

from .types import (
    AgentType, AgentContext, AgentResult, AgentRequest, AgentResponse,
    AgentStreamChunk,
    # Enterprise orchestration types
    EnterpriseAgentRequest, EnterpriseAgentResponse,
    TaskDAG, ExecutionTrace, ParallelStreamChunk, TaskStatus
)
from .base import BaseAgent
from .registry import AgentRegistry, get_agent_registry
from .executor import AgentExecutor, get_executor
from .intent import IntentClassifier, get_intent_classifier, IntentResult
from .dag import DAGBuilder, get_dag_builder
from .parallel_executor import ParallelExecutor, get_parallel_executor
from .evaluator import ResultEvaluator, SynthesisEvaluator, get_evaluator, get_synthesis_evaluator

# Import query log writer for logging all agent queries
from ..infrastructure.services.query_log_writer import get_query_log_writer

# Import web content service for URL fetching
from ..services.web_content_service import get_web_content_service

logger = logging.getLogger(__name__)


# Keywords for agent type classification
AGENT_KEYWORDS = {
    AgentType.RAG: [
        "what", "how", "why", "explain", "describe", "tell me",
        "knowledge", "information", "document", "article",
        "뭐", "무엇", "어떻게", "왜", "설명", "알려",
        "何", "どう", "なぜ", "説明",
    ],
    AgentType.IMS: [
        "issue", "bug", "error", "problem", "ticket",
        "ims", "jira", "defect", "fix", "resolved",
        "이슈", "버그", "오류", "문제", "티켓",
        "バグ", "エラー", "問題", "チケット",
    ],
    AgentType.VISION: [
        "image", "picture", "photo", "chart", "graph",
        "diagram", "figure", "screenshot", "visual",
        "이미지", "사진", "차트", "그래프", "다이어그램",
        "画像", "写真", "チャート", "グラフ",
    ],
    AgentType.CODE: [
        "code", "program", "function", "class", "implement",
        "debug", "compile", "script", "algorithm",
        "코드", "프로그램", "함수", "클래스", "구현",
        "コード", "プログラム", "関数", "クラス",
    ],
    AgentType.PLANNER: [
        "plan", "strategy", "approach", "steps", "roadmap",
        "breakdown", "decompose", "organize", "schedule",
        "계획", "전략", "접근", "단계", "로드맵",
        "計画", "戦略", "アプローチ", "ステップ",
    ],
}


class AgentOrchestrator:
    """
    Orchestrates agent selection and execution.
    Singleton pattern with lazy initialization.
    """

    _instance: Optional['AgentOrchestrator'] = None

    def __init__(
        self,
        agent_registry: Optional[AgentRegistry] = None,
        executor: Optional[AgentExecutor] = None,
        intent_classifier: Optional[IntentClassifier] = None,
        dag_builder: Optional[DAGBuilder] = None,
        parallel_executor: Optional[ParallelExecutor] = None,
        evaluator: Optional[ResultEvaluator] = None,
        synthesis_evaluator: Optional[SynthesisEvaluator] = None
    ):
        self.agent_registry = agent_registry or get_agent_registry()
        self.executor = executor or get_executor()
        self.intent_classifier = intent_classifier or get_intent_classifier()
        # Enterprise orchestration components (lazy-initialized)
        self._dag_builder = dag_builder
        self._parallel_executor = parallel_executor
        self._evaluator = evaluator
        self._synthesis_evaluator = synthesis_evaluator

    @property
    def dag_builder(self) -> DAGBuilder:
        """Lazy-initialize DAG builder."""
        if self._dag_builder is None:
            llm_adapter = getattr(self.executor, 'llm_adapter', None)
            self._dag_builder = get_dag_builder(llm_adapter)
        return self._dag_builder

    @property
    def parallel_executor(self) -> ParallelExecutor:
        """Lazy-initialize parallel executor."""
        if self._parallel_executor is None:
            self._parallel_executor = get_parallel_executor(
                self.agent_registry,
                self.executor
            )
        return self._parallel_executor

    @property
    def evaluator(self) -> ResultEvaluator:
        """Lazy-initialize result evaluator."""
        if self._evaluator is None:
            llm_adapter = getattr(self.executor, 'llm_adapter', None)
            self._evaluator = get_evaluator(llm_adapter)
        return self._evaluator

    @property
    def synthesis_evaluator(self) -> SynthesisEvaluator:
        """Lazy-initialize synthesis evaluator."""
        if self._synthesis_evaluator is None:
            self._synthesis_evaluator = get_synthesis_evaluator()
        return self._synthesis_evaluator

    @classmethod
    def get_instance(cls) -> 'AgentOrchestrator':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def execute(
        self,
        request: AgentRequest,
        user_id: Optional[str] = None
    ) -> AgentResponse:
        """
        Execute an agent request.

        Args:
            request: The agent request
            user_id: Optional user ID for context

        Returns:
            AgentResponse with answer and metadata
        """
        start_time = time.time()

        # Fetch URL content if url_context is provided
        url_content = None
        url_source = None
        if request.url_context:
            url_content, url_source = await self._fetch_url_content(request.url_context)
            if url_content:
                logger.info(f"[Orchestrator] URL content fetched: {len(url_content)} chars from {url_source}")

        # Create context
        context = AgentContext(
            session_id=request.session_id or "",
            user_id=user_id,
            language=request.language,
            max_steps=request.max_steps,
            file_context=request.file_context,
            url_context=url_content,
            url_source=url_source
        )

        # Select agent
        if request.agent_type:
            agent_type = request.agent_type
        else:
            agent_type = await self.classify_task(request.task)

        # Classify intent and attach to context
        intent_result = await self.intent_classifier.classify(
            request.task,
            agent_type=agent_type.value
        )
        context.intent = intent_result
        logger.info(f"[Orchestrator] Intent: {intent_result.intent.value} "
                   f"(confidence={intent_result.confidence:.2f}, method={intent_result.method})")

        # Get agent
        agent = self.agent_registry.get(agent_type)

        # Execute
        result = await agent.execute(request.task, context)

        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)

        # Log query for FAQ system (non-blocking)
        await self._log_query(
            query_text=request.task,
            user_id=user_id,
            session_id=request.session_id,
            agent_type=result.agent_type.value,
            intent_type=intent_result.intent.value if intent_result else None,
            category=intent_result.extracted_params.get('product') if intent_result else None,
            language=request.language,
            execution_time_ms=execution_time_ms,
            success=result.success,
            response_summary=result.answer[:500] if result.answer else None
        )

        # Build response
        return AgentResponse(
            answer=result.answer,
            agent_type=result.agent_type,
            session_id=context.session_id,
            steps=result.steps,
            sources=result.sources if request.include_sources else [],
            execution_time=result.execution_time,
            success=result.success,
            error=result.error
        )

    async def stream(
        self,
        request: AgentRequest,
        user_id: Optional[str] = None
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        Stream agent execution.

        Args:
            request: The agent request
            user_id: Optional user ID for context

        Yields:
            AgentStreamChunk with incremental results
        """
        start_time = time.time()
        logger.info(f"[Orchestrator] stream called: task={request.task[:50]}...")

        # Fetch URL content if url_context is provided
        url_content = None
        url_source = None
        if request.url_context:
            url_content, url_source = await self._fetch_url_content(request.url_context)
            if url_content:
                logger.info(f"[Orchestrator] URL content fetched: {len(url_content)} chars from {url_source}")

        context = AgentContext(
            session_id=request.session_id or "",
            user_id=user_id,
            language=request.language,
            max_steps=request.max_steps,
            file_context=request.file_context,
            url_context=url_content,
            url_source=url_source
        )

        if request.agent_type:
            agent_type = request.agent_type
        else:
            agent_type = await self.classify_task(request.task)

        # Classify intent and attach to context
        intent_result = await self.intent_classifier.classify(
            request.task,
            agent_type=agent_type.value
        )
        context.intent = intent_result
        print(f"[Orchestrator] Intent: {intent_result.intent.value} "
              f"(confidence={intent_result.confidence:.2f}, method={intent_result.method}, "
              f"params={intent_result.extracted_params})", flush=True)

        print(f"[Orchestrator] agent_type={agent_type.value}", flush=True)

        agent = self.agent_registry.get(agent_type)
        print(f"[Orchestrator] agent={agent.name}", flush=True)

        # Collect response text for logging
        response_text_parts = []
        success = True

        try:
            async for chunk in agent.stream(request.task, context):
                logger.debug(f"[Orchestrator] chunk={chunk.chunk_type}")
                # Collect text chunks for summary
                if chunk.chunk_type == "text" and chunk.content:
                    response_text_parts.append(chunk.content)
                elif chunk.chunk_type == "error":
                    success = False
                yield chunk
        except Exception as e:
            logger.error(f"[Orchestrator] ERROR: {e}")
            success = False
            raise
        finally:
            # Log query after stream completes (in finally to ensure logging even on error)
            execution_time_ms = int((time.time() - start_time) * 1000)
            response_summary = ''.join(response_text_parts)[:500] if response_text_parts else None
            await self._log_query(
                query_text=request.task,
                user_id=user_id,
                session_id=request.session_id,
                agent_type=agent_type.value,
                intent_type=intent_result.intent.value if intent_result else None,
                category=intent_result.extracted_params.get('product') if intent_result else None,
                language=request.language,
                execution_time_ms=execution_time_ms,
                success=success,
                response_summary=response_summary
            )

    async def classify_task(self, task: str) -> AgentType:
        """
        Classify a task to determine the appropriate agent type.

        Uses keyword matching and optionally LLM classification.
        """
        task_lower = task.lower()

        # Score each agent type based on keyword matches
        scores: Dict[AgentType, int] = {at: 0 for at in AgentType}

        for agent_type, keywords in AGENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in task_lower:
                    scores[agent_type] += 1
                    logger.debug(f"[Classify] matched '{keyword}' -> {agent_type.value}")

        logger.debug(f"[Classify] scores={scores}")

        # Find best match
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # If no strong match, default to RAG
        if best_score == 0:
            logger.info("[Classify] no match, defaulting to RAG")
            return AgentType.RAG

        # If multiple high scores, prefer RAG as it's most general
        high_scores = [at for at, score in scores.items() if score == best_score]
        if len(high_scores) > 1 and AgentType.RAG in high_scores:
            logger.info(f"[Classify] multiple high scores {high_scores}, preferring RAG")
            return AgentType.RAG

        logger.info(f"[Classify] result={best_type.value}")
        return best_type

    async def classify_with_llm(self, task: str) -> AgentType:
        """
        Use LLM to classify the task (more accurate but slower).
        """
        try:
            if self.executor.llm_adapter is None:
                return await self.classify_task(task)

            prompt = f"""Classify this task into one of these categories:
- rag: General knowledge queries, questions about documents or information
- ims: Issue tracking, bug reports, technical problems
- vision: Image or visual content analysis
- code: Code generation, review, or debugging
- planner: Complex task planning or decomposition

Task: {task}

Respond with only the category name (rag, ims, vision, code, or planner):"""

            response = await self.executor.llm_adapter.generate([
                {"role": "user", "content": prompt}
            ])

            classification = response.get("content", "").strip().lower()

            type_map = {
                "rag": AgentType.RAG,
                "ims": AgentType.IMS,
                "vision": AgentType.VISION,
                "code": AgentType.CODE,
                "planner": AgentType.PLANNER,
            }

            return type_map.get(classification, AgentType.RAG)

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return await self.classify_task(task)

    def get_available_agents(self) -> List[Dict]:
        """Get information about available agents"""
        agents = []
        for agent_type in self.agent_registry.get_all_types():
            agent = self.agent_registry.get(agent_type)
            agents.append({
                "type": agent_type.value,
                "name": agent.name,
                "description": agent.description,
                "tools": agent.tools
            })
        return agents

    # =========================================================================
    # Enterprise Multi-Agent Orchestration Methods
    # =========================================================================

    async def execute_enterprise(
        self,
        request: EnterpriseAgentRequest,
        user_id: Optional[str] = None
    ) -> EnterpriseAgentResponse:
        """
        Execute an enterprise multi-agent request.

        Supports task decomposition, parallel execution, evaluation,
        retry logic, and result synthesis.

        Args:
            request: The enterprise agent request with orchestration config
            user_id: Optional user ID for context

        Returns:
            EnterpriseAgentResponse with synthesized answer and trace
        """
        start_time = time.time()
        trace = ExecutionTrace()
        trace.record("orchestration_start", data={"task": request.task[:200]})

        # Fetch URL content if provided
        url_content = None
        url_source = None
        if request.url_context:
            url_content, url_source = await self._fetch_url_content(request.url_context)
            if url_content:
                logger.info(f"[Enterprise] URL content fetched: {len(url_content)} chars")

        # Create base context
        context = AgentContext(
            session_id=request.session_id or "",
            user_id=user_id,
            language=request.language,
            max_steps=request.max_steps,
            file_context=request.file_context,
            url_context=url_content,
            url_source=url_source
        )

        # Classify primary agent type
        if request.agent_type:
            agent_type = request.agent_type
        else:
            agent_type = await self.classify_task(request.task)

        # Classify intent
        intent_result = await self.intent_classifier.classify(
            request.task,
            agent_type=agent_type.value
        )
        context.intent = intent_result
        logger.info(
            f"[Enterprise] Intent: {intent_result.intent.value} "
            f"(confidence={intent_result.confidence:.2f})"
        )

        # Check if multi-agent orchestration is needed
        if not request.enable_multi_agent:
            # Fall back to simple single-agent execution
            simple_request = AgentRequest(
                task=request.task,
                agent_type=request.agent_type,
                session_id=request.session_id,
                language=request.language,
                max_steps=request.max_steps,
                include_sources=request.include_sources,
                stream=False,
                file_context=request.file_context,
                url_context=request.url_context
            )
            simple_response = await self.execute(simple_request, user_id)
            return EnterpriseAgentResponse(
                answer=simple_response.answer,
                agent_type=simple_response.agent_type,
                session_id=simple_response.session_id,
                steps=simple_response.steps,
                sources=simple_response.sources,
                execution_time=simple_response.execution_time,
                success=simple_response.success,
                error=simple_response.error
            )

        # Build task DAG
        config = request.orchestration_config
        use_llm = config.enable_parallel  # Use LLM for complex decomposition
        dag = await self.dag_builder.build_dag(
            request.task,
            agent_type,
            request.language,
            use_llm=use_llm
        )
        trace.dag = dag
        trace.record(
            "dag_created",
            data={
                "task_count": len(dag.tasks),
                "parallelism": dag.parallelism_type.value,
                "batches": len(dag.execution_batches)
            }
        )
        logger.info(
            f"[Enterprise] DAG created: {len(dag.tasks)} tasks, "
            f"parallelism={dag.parallelism_type.value}"
        )

        # Execute DAG with parallel executor
        results = await self.parallel_executor.execute_dag(
            dag, context, config, trace
        )

        # Collect successful and failed results
        successful_results: Dict[str, AgentResult] = {}
        partial_failures: List[str] = []

        for task_id, result in results.items():
            if result.success:
                successful_results[task_id] = result
            else:
                partial_failures.append(task_id)

        # Evaluate and potentially retry failed tasks
        if config.enable_evaluation and config.enable_retry:
            for task_id in list(partial_failures):
                subtask = dag.tasks.get(task_id)
                if subtask and subtask.result:
                    evaluation = await self.evaluator.evaluate(
                        subtask.result,
                        subtask.description,
                        config.evaluation_criteria,
                        subtask
                    )
                    trace.evaluations[task_id] = evaluation

                    should_retry, delay = self.evaluator.should_retry(
                        evaluation,
                        subtask.retry_count,
                        config.retry_config
                    )

                    if should_retry:
                        trace.record("retry", task_id=task_id, data={"delay": delay})
                        # Note: Actual retry is handled in parallel_executor
                        # This is for additional retry logic if needed

        # Synthesize results
        if len(successful_results) > 1:
            synthesized_answer = await self._synthesize_results(
                request.task,
                successful_results,
                request.language,
                trace
            )
        elif successful_results:
            # Single result, use as-is
            single_result = list(successful_results.values())[0]
            synthesized_answer = single_result.answer
        else:
            # All failed
            synthesized_answer = "모든 작업이 실패했습니다. 나중에 다시 시도해주세요."
            if request.language == "en":
                synthesized_answer = "All tasks failed. Please try again later."
            elif request.language == "ja":
                synthesized_answer = "すべてのタスクが失敗しました。後でもう一度お試しください。"

        # Generate next-action recommendations
        next_actions: List[str] = []
        if config.enable_next_actions and successful_results:
            next_actions = await self._generate_next_actions(
                request.task,
                synthesized_answer,
                successful_results,
                request.language
            )
            trace.next_actions = next_actions

        # Calculate total execution time
        execution_time = time.time() - start_time
        trace.end_time = trace.start_time.__class__.utcnow()
        trace.total_time = execution_time
        trace.record("orchestration_complete", data={"total_time": execution_time})

        # Aggregate sources from all successful results
        all_sources = []
        for result in successful_results.values():
            all_sources.extend(result.sources)

        # Calculate total steps
        total_steps = sum(r.steps for r in successful_results.values())

        # Build subtask results for response
        subtask_results = {
            task_id: {
                "answer": result.answer[:500],
                "agent_type": result.agent_type.value,
                "success": result.success,
                "execution_time": result.execution_time
            }
            for task_id, result in results.items()
        }

        # Log query
        await self._log_query(
            query_text=request.task,
            user_id=user_id,
            session_id=request.session_id,
            agent_type=agent_type.value,
            intent_type=intent_result.intent.value if intent_result else None,
            category=intent_result.extracted_params.get('product') if intent_result else None,
            language=request.language,
            execution_time_ms=int(execution_time * 1000),
            success=len(successful_results) > 0,
            response_summary=synthesized_answer[:500] if synthesized_answer else None
        )

        return EnterpriseAgentResponse(
            answer=synthesized_answer,
            agent_type=agent_type,
            session_id=context.session_id,
            steps=total_steps,
            sources=all_sources if request.include_sources else [],
            execution_time=execution_time,
            success=len(successful_results) > 0,
            error=None if successful_results else "All subtasks failed",
            trace=self._serialize_trace(trace),
            subtask_results=subtask_results,
            next_actions=next_actions,
            partial_failures=partial_failures
        )

    async def stream_enterprise(
        self,
        request: EnterpriseAgentRequest,
        user_id: Optional[str] = None
    ) -> AsyncGenerator[ParallelStreamChunk, None]:
        """
        Stream enterprise multi-agent execution.

        Provides real-time updates from parallel agent execution
        with interleaved streaming.

        Args:
            request: The enterprise agent request
            user_id: Optional user ID for context

        Yields:
            ParallelStreamChunk with incremental results
        """
        start_time = time.time()
        trace = ExecutionTrace()

        # Emit start
        yield ParallelStreamChunk(
            chunk_type="orchestration_start",
            content=f"Starting enterprise orchestration: {request.task[:100]}...",
            metadata={"task": request.task}
        )

        # Fetch URL content if provided
        url_content = None
        url_source = None
        if request.url_context:
            url_content, url_source = await self._fetch_url_content(request.url_context)

        # Create context
        context = AgentContext(
            session_id=request.session_id or "",
            user_id=user_id,
            language=request.language,
            max_steps=request.max_steps,
            file_context=request.file_context,
            url_context=url_content,
            url_source=url_source
        )

        # Classify
        if request.agent_type:
            agent_type = request.agent_type
        else:
            agent_type = await self.classify_task(request.task)

        intent_result = await self.intent_classifier.classify(
            request.task,
            agent_type=agent_type.value
        )
        context.intent = intent_result

        # Check if multi-agent is needed
        if not request.enable_multi_agent:
            # Stream simple execution wrapped in parallel chunks
            simple_request = AgentRequest(
                task=request.task,
                agent_type=request.agent_type,
                session_id=request.session_id,
                language=request.language,
                max_steps=request.max_steps,
                include_sources=request.include_sources,
                stream=True,
                file_context=request.file_context,
                url_context=request.url_context
            )
            async for chunk in self.stream(simple_request, user_id):
                yield ParallelStreamChunk(
                    chunk_type="agent_chunk",
                    task_id="main",
                    agent_type=agent_type,
                    agent_chunk=chunk
                )
            yield ParallelStreamChunk(chunk_type="done")
            return

        # Build DAG
        config = request.orchestration_config
        dag = await self.dag_builder.build_dag(
            request.task,
            agent_type,
            request.language,
            use_llm=config.enable_parallel
        )
        trace.dag = dag

        yield ParallelStreamChunk(
            chunk_type="dag_created",
            content=f"Task decomposed into {len(dag.tasks)} subtasks",
            metadata={
                "task_count": len(dag.tasks),
                "parallelism": dag.parallelism_type.value,
                "tasks": [
                    {"id": t.task_id, "description": t.description[:100]}
                    for t in dag.tasks.values()
                ]
            }
        )

        # Stream DAG execution
        async for chunk in self.parallel_executor.stream_dag(dag, context, config, trace):
            yield chunk

        # Collect results for synthesis
        successful_results = {
            task_id: subtask.result
            for task_id, subtask in dag.tasks.items()
            if subtask.status == TaskStatus.COMPLETED and subtask.result
        }

        # Synthesize
        if len(successful_results) > 1:
            yield ParallelStreamChunk(
                chunk_type="synthesis",
                content="Synthesizing results from all agents..."
            )
            synthesized_answer = await self._synthesize_results(
                request.task,
                successful_results,
                request.language,
                trace
            )
            yield ParallelStreamChunk(
                chunk_type="synthesis",
                content=synthesized_answer,
                metadata={"is_final": True}
            )
        elif successful_results:
            single_result = list(successful_results.values())[0]
            yield ParallelStreamChunk(
                chunk_type="synthesis",
                content=single_result.answer,
                metadata={"is_final": True}
            )

        # Generate next actions
        if config.enable_next_actions and successful_results:
            next_actions = await self._generate_next_actions(
                request.task,
                "",  # Answer already streamed
                successful_results,
                request.language
            )
            if next_actions:
                yield ParallelStreamChunk(
                    chunk_type="next_actions",
                    content="\n".join(next_actions),
                    metadata={"actions": next_actions}
                )

        # Log query
        execution_time = time.time() - start_time
        await self._log_query(
            query_text=request.task,
            user_id=user_id,
            session_id=request.session_id,
            agent_type=agent_type.value,
            intent_type=intent_result.intent.value if intent_result else None,
            category=intent_result.extracted_params.get('product') if intent_result else None,
            language=request.language,
            execution_time_ms=int(execution_time * 1000),
            success=len(successful_results) > 0,
            response_summary=None
        )

        yield ParallelStreamChunk(
            chunk_type="done",
            metadata={
                "execution_time": execution_time,
                "successful_tasks": len(successful_results),
                "total_tasks": len(dag.tasks)
            }
        )

    async def _synthesize_results(
        self,
        original_task: str,
        results: Dict[str, AgentResult],
        language: str,
        trace: ExecutionTrace
    ) -> str:
        """
        Synthesize multiple agent results into a coherent answer.

        Uses LLM to merge and deduplicate information from multiple sources.
        """
        trace.record("synthesis_start", data={"result_count": len(results)})

        # Prepare result summaries
        result_texts = []
        for task_id, result in results.items():
            result_texts.append(f"[{task_id}]\n{result.answer}")

        combined = "\n\n---\n\n".join(result_texts)

        # Use LLM for synthesis if available
        llm_adapter = getattr(self.executor, 'llm_adapter', None)
        if llm_adapter is None:
            # Simple concatenation fallback
            return combined

        # Language-specific synthesis prompts
        synthesis_prompts = {
            "ko": "다음 여러 결과를 하나의 일관된 답변으로 통합하세요. 중복을 제거하고 정보를 논리적으로 구성하세요.",
            "ja": "以下の複数の結果を一つの一貫した回答に統合してください。重複を排除し、情報を論理的に整理してください。",
            "en": "Synthesize the following results into one coherent answer. Remove duplicates and organize information logically."
        }
        synthesis_instruction = synthesis_prompts.get(language, synthesis_prompts["en"])

        prompt = f"""{synthesis_instruction}

Original question: {original_task}

Results to synthesize:
{combined}

Provide a unified, well-structured answer:"""

        try:
            response = await llm_adapter.generate([
                {"role": "user", "content": prompt}
            ])
            synthesized = response.get("content", combined)
            trace.record("synthesis_complete", data={"length": len(synthesized)})
            trace.synthesis_metadata["method"] = "llm"
            return synthesized
        except Exception as e:
            logger.warning(f"[Enterprise] Synthesis failed: {e}, using concatenation")
            trace.synthesis_metadata["method"] = "concatenation"
            trace.synthesis_metadata["error"] = str(e)
            return combined

    async def _generate_next_actions(
        self,
        original_task: str,
        answer: str,
        results: Dict[str, AgentResult],
        language: str
    ) -> List[str]:
        """
        Generate recommended next actions based on results.

        Uses LLM to suggest follow-up questions or actions.
        """
        llm_adapter = getattr(self.executor, 'llm_adapter', None)
        if llm_adapter is None:
            return []

        # Language-specific prompts
        next_action_prompts = {
            "ko": "사용자가 다음에 할 수 있는 관련 질문이나 행동 2-3개를 제안하세요.",
            "ja": "ユーザーが次に行える関連する質問やアクションを2-3個提案してください。",
            "en": "Suggest 2-3 related questions or actions the user might want to take next."
        }
        instruction = next_action_prompts.get(language, next_action_prompts["en"])

        # Truncate answer for prompt
        answer_preview = answer[:1000] if answer else "Multiple results processed"

        prompt = f"""{instruction}

Original question: {original_task}

Answer provided: {answer_preview}

List each suggestion on a new line, starting with "- ":"""

        try:
            response = await llm_adapter.generate([
                {"role": "user", "content": prompt}
            ])
            content = response.get("content", "")

            # Parse suggestions
            suggestions = []
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    suggestions.append(line[2:])
                elif line.startswith("• "):
                    suggestions.append(line[2:])

            return suggestions[:3]  # Limit to 3 suggestions

        except Exception as e:
            logger.warning(f"[Enterprise] Next actions generation failed: {e}")
            return []

    def _serialize_trace(self, trace: ExecutionTrace) -> Dict:
        """Serialize execution trace for API response."""
        return {
            "trace_id": trace.trace_id,
            "start_time": trace.start_time.isoformat() if trace.start_time else None,
            "end_time": trace.end_time.isoformat() if trace.end_time else None,
            "total_time": trace.total_time,
            "events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "event_type": e.event_type,
                    "task_id": e.task_id,
                    "agent_type": e.agent_type.value if e.agent_type else None,
                    "data": e.data
                }
                for e in trace.events
            ],
            "dag": {
                "task_count": len(trace.dag.tasks) if trace.dag else 0,
                "parallelism": trace.dag.parallelism_type.value if trace.dag else None,
                "batches": trace.dag.execution_batches if trace.dag else []
            } if trace.dag else None,
            "evaluations": {
                task_id: {
                    "passed": e.passed,
                    "score": e.score,
                    "issues": e.issues
                }
                for task_id, e in trace.evaluations.items()
            },
            "synthesis": trace.synthesis_metadata,
            "next_actions": trace.next_actions
        }

    async def _log_query(
        self,
        query_text: str,
        user_id: Optional[str],
        session_id: Optional[str],
        agent_type: str,
        intent_type: Optional[str],
        category: Optional[str],
        language: str,
        execution_time_ms: int,
        success: bool,
        response_summary: Optional[str]
    ) -> None:
        """
        Log query to the background query log writer.

        Non-blocking operation - failures are logged but don't affect request.
        """
        try:
            query_log_writer = get_query_log_writer()
            if query_log_writer is None:
                logger.debug("[Orchestrator] QueryLogWriter not initialized, skipping log")
                return

            await query_log_writer.submit_query({
                'user_id': user_id,
                'session_id': session_id,
                'query_text': query_text,
                'agent_type': agent_type,
                'intent_type': intent_type,
                'category': category,
                'language': language,
                'execution_time_ms': execution_time_ms,
                'success': success,
                'response_summary': response_summary,
            })
            logger.debug(f"[Orchestrator] Query logged: agent={agent_type}, intent={intent_type}")
        except Exception as e:
            # Non-blocking - log error but don't fail the request
            logger.warning(f"[Orchestrator] Failed to log query: {e}")

    async def _fetch_url_content(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """
        Fetch content from a URL for RAG context.

        Args:
            url: The URL to fetch content from

        Returns:
            Tuple of (content, source_url) or (None, None) on failure
        """
        try:
            web_service = get_web_content_service()

            # Fetch HTML
            html_content, status_code, error = await web_service.fetch_url(url)
            if html_content is None:
                logger.warning(f"[Orchestrator] Failed to fetch URL {url}: {error}")
                return None, None

            # Extract text content
            extraction = await web_service.extractor.extract_with_trafilatura(html_content, url)
            if not extraction.success or not extraction.text_content:
                # Fallback to BeautifulSoup
                extraction = await web_service.extractor.extract_with_beautifulsoup(html_content, url)

            if extraction.success and extraction.text_content:
                # Truncate to reasonable size for context (max 10000 chars)
                content = extraction.text_content[:10000]
                if len(extraction.text_content) > 10000:
                    content += "\n\n[... content truncated ...]"
                return content, url

            logger.warning(f"[Orchestrator] Failed to extract content from URL {url}")
            return None, None

        except Exception as e:
            logger.error(f"[Orchestrator] Error fetching URL {url}: {e}")
            return None, None


# Convenience function
def get_orchestrator() -> AgentOrchestrator:
    """Get the global orchestrator instance"""
    return AgentOrchestrator.get_instance()
