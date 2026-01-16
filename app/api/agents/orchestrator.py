"""
Agent Orchestrator
Manages agent selection and execution flow.
Supports both simple single-agent and enterprise multi-agent orchestration.
"""
from typing import Any, Dict, List, Optional, AsyncGenerator
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
from .adapters.integration import get_deep_agent
from .intent import IntentClassifier, get_intent_classifier, IntentResult
from .dag import DAGBuilder, get_dag_builder
from .parallel_executor import ParallelExecutor, get_parallel_executor
from .evaluator import ResultEvaluator, SynthesisEvaluator, get_evaluator, get_synthesis_evaluator
from .master_system_constraint import (
    get_constraint_enforcer,
    log_compliance_violation,
    ComplianceViolationType,
    validate_constraint_present,
    build_constrained_system_prompt
)

# Deep Agents integration
try:
    from .adapters.deep_agent_adapter import (
        DeepAgentAdapter,
        create_rag_deep_agent,
        create_code_deep_agent,
        create_planner_deep_agent,
    )
    DEEP_AGENTS_AVAILABLE = True
except ImportError as e:
    DEEP_AGENTS_AVAILABLE = False
    import logging
    logging.getLogger(__name__).warning(f"Deep Agents import failed: {e}")

# Import query log writer for logging all agent queries
from ..infrastructure.services.query_log_writer import get_query_log_writer

# Import web content service for URL fetching
from ..services.web_content_service import get_web_content_service

# Import UI context models for context-aware AI
from ..models.ui_context import (
    UIContext,
    filter_ui_context_by_role,
    build_context_prompt_section,
)

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
        # Deep Agents cache (lazy-initialized)
        self._deep_agents: Dict[AgentType, Any] = {}

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

    def get_deep_agent(self, agent_type: AgentType) -> Optional['DeepAgentAdapter']:
        """
        Get or create a Deep Agent for the specified type.

        Args:
            agent_type: The agent type to get Deep Agent for

        Returns:
            DeepAgentAdapter instance or None if Deep Agents not available
        """
        if not DEEP_AGENTS_AVAILABLE:
            logger.warning("[Orchestrator] Deep Agents not available")
            return None

        if agent_type not in self._deep_agents:
            # Create appropriate Deep Agent based on type
            if agent_type == AgentType.RAG:
                self._deep_agents[agent_type] = create_rag_deep_agent()
            elif agent_type == AgentType.CODE:
                self._deep_agents[agent_type] = create_code_deep_agent()
            elif agent_type == AgentType.PLANNER:
                self._deep_agents[agent_type] = create_planner_deep_agent()
            else:
                # For other types, create a generic Deep Agent with RAG tools
                from .middleware import get_rag_tools
                self._deep_agents[agent_type] = DeepAgentAdapter(
                    name=f"DeepAgent-{agent_type.value}",
                    agent_type=agent_type,
                    description=f"Deep Agent for {agent_type.value} tasks",
                    tools=get_rag_tools(),
                )
            logger.info(f"[Orchestrator] Created Deep Agent for {agent_type.value}")

        return self._deep_agents[agent_type]

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
            url_source=url_source,
            use_deep_agent=getattr(request, 'use_deep_agent', False)
        )

        # Select agent type
        if request.agent_type:
            agent_type = request.agent_type
        else:
            agent_type = await self.classify_task(request.task)

        # Check environment variable for global Deep Agent setting
        # ENABLE_DEEP_AGENT=true/false overrides request.use_deep_agent
        import os
        env_deep_agent = os.getenv("ENABLE_DEEP_AGENT", "").lower()
        if env_deep_agent in ("true", "1", "yes"):
            use_deep_agent = True
        elif env_deep_agent in ("false", "0", "no"):
            use_deep_agent = False
        else:
            use_deep_agent = request.use_deep_agent

        logger.info(f"[Orchestrator] use_deep_agent={use_deep_agent} (env={env_deep_agent or 'not set'})")

        # Route to Deep Agent if requested
        if use_deep_agent:
            return await self._execute_deep_agent(request, context, agent_type, user_id, start_time)

        # Classify intent and attach to context
        intent_result = await self.intent_classifier.classify(
            request.task,
            agent_type=agent_type.value
        )
        context.intent = intent_result
        logger.info(f"[Orchestrator] Intent: {intent_result.intent.value} "
                   f"(confidence={intent_result.confidence:.2f}, method={intent_result.method})")

        # Get agent - use regular agent since use_deep_agent is False here
        agent = self.agent_registry.get(agent_type)
        logger.info(f"[Orchestrator] Using regular agent: {agent.name}")

        # ========================================================================
        # ORCHESTRATOR-LEVEL CONSTRAINT VALIDATION
        # Verify agent system prompt includes master constraint before execution
        # ========================================================================
        constrained_prompt = build_constrained_system_prompt(agent.system_prompt)
        if not validate_constraint_present(constrained_prompt):
            log_compliance_violation(
                ComplianceViolationType.CONSTRAINT_MISSING,
                agent_type.value,
                user_id=user_id,
                session_id=request.session_id,
                details={"step": "orchestrator_pre_execute"}
            )
            logger.critical(f"[Orchestrator] CRITICAL: Master constraint not present for {agent_type.value} agent")
        else:
            logger.info(f"[Orchestrator] Master constraint validated for {agent_type.value} agent")

        # Execute
        result = await agent.execute(request.task, context)

        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)

        # Estimate tokens
        input_tokens = len(request.task) // 4
        output_tokens = len(result.answer) // 4 if result.answer else 0

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
            response_summary=result.answer[:500] if result.answer else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens
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
            url_source=url_source,
            use_deep_agent=getattr(request, 'use_deep_agent', False)
        )

        # Process UI context if provided
        ui_context_prompt = None
        if request.ui_context:
            ui_context_prompt = await self._process_ui_context(
                request.ui_context,
                user_id
            )
            if ui_context_prompt:
                context.metadata['ui_context_prompt'] = ui_context_prompt
                logger.info(f"[Orchestrator] UI context processed: page={request.ui_context.get('current_page')}")

        if request.agent_type:
            agent_type = request.agent_type
        else:
            agent_type = await self.classify_task(request.task)

        # Check environment variable for global Deep Agent setting
        # ENABLE_DEEP_AGENT=true/false overrides request.use_deep_agent
        import os
        env_deep_agent = os.getenv("ENABLE_DEEP_AGENT", "").lower()
        if env_deep_agent in ("true", "1", "yes"):
            use_deep_agent = True
        elif env_deep_agent in ("false", "0", "no"):
            use_deep_agent = False
        else:
            use_deep_agent = request.use_deep_agent

        # Debug: Log use_deep_agent value
        print(f"[Orchestrator] use_deep_agent={use_deep_agent} (env={env_deep_agent or 'not set'})", flush=True)

        # Route to Deep Agent streaming if requested
        if use_deep_agent:
            async for chunk in self._stream_deep_agent(request, context, agent_type, user_id, start_time):
                yield chunk
            return

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

        # Get agent - use Deep Agent if enabled (use env-modified value, not request value)
        if use_deep_agent:
            try:
                agent = get_deep_agent(agent_type)
                print(f"[Orchestrator] Using Deep Agent: {agent.name}", flush=True)
            except Exception as e:
                logger.warning(f"[Orchestrator] Failed to create Deep Agent, falling back: {e}")
                agent = self.agent_registry.get(agent_type)
                print(f"[Orchestrator] Fallback to regular agent: {agent.name}", flush=True)
        else:
            agent = self.agent_registry.get(agent_type)
            print(f"[Orchestrator] Using regular agent: {agent.name}", flush=True)

        # ========================================================================
        # ORCHESTRATOR-LEVEL CONSTRAINT VALIDATION (Stream)
        # Verify agent system prompt includes master constraint before execution
        # ========================================================================
        constrained_prompt = build_constrained_system_prompt(agent.system_prompt)
        if not validate_constraint_present(constrained_prompt):
            log_compliance_violation(
                ComplianceViolationType.CONSTRAINT_MISSING,
                agent_type.value,
                user_id=user_id,
                session_id=request.session_id,
                details={"step": "orchestrator_pre_stream"}
            )
            print(f"[Orchestrator] CRITICAL: Master constraint not present for {agent_type.value} agent", flush=True)
        else:
            print(f"[Orchestrator] Master constraint validated for {agent_type.value} agent", flush=True)

        # Collect response text for logging
        response_text_parts = []
        success = True
        has_sent_content = False

        # State-based thinking tag filter for streaming
        # Nemotron model outputs thinking without <think> but with </think> at end
        inside_thinking = False
        waiting_for_think_end = False  # For cases without <think> but with </think>
        text_buffer = ""

        try:
            async for chunk in agent.stream(request.task, context):
                logger.debug(f"[Orchestrator] chunk={chunk.chunk_type}")
                # Filter thinking tags from text content (state-based for streaming)
                if chunk.chunk_type == "text" and chunk.content:
                    text_buffer += chunk.content

                    # Detect thinking start pattern (model outputs thinking without <think> tag)
                    if not inside_thinking and not waiting_for_think_end and not has_sent_content:
                        thinking_patterns = [
                            "Okay, let's", "Okay let's", "Let me ", "I need to ",
                            "First, ", "The user ", "Looking at ", "I should ",
                        ]
                        if any(text_buffer.strip().startswith(p) for p in thinking_patterns):
                            waiting_for_think_end = True
                            logger.debug("[Orchestrator] Detected thinking pattern, waiting for </think>")

                    # Check for <think> tag to enter thinking mode
                    if "<think>" in text_buffer and not inside_thinking:
                        inside_thinking = True
                        waiting_for_think_end = False
                        # Keep content before <think>
                        before_think = text_buffer.split("<think>")[0]
                        if before_think.strip():
                            has_sent_content = True
                            response_text_parts.append(before_think)
                            yield AgentStreamChunk(chunk_type="text", content=before_think)
                        text_buffer = "<think>" + text_buffer.split("<think>", 1)[1]

                    # Check for </think> tag to exit thinking mode
                    if "</think>" in text_buffer:
                        inside_thinking = False
                        waiting_for_think_end = False
                        # Get content after </think>
                        after_think = text_buffer.split("</think>", 1)[1].lstrip()
                        text_buffer = ""
                        if after_think.strip():
                            has_sent_content = True
                            response_text_parts.append(after_think)
                            yield AgentStreamChunk(chunk_type="text", content=after_think)
                        continue

                    # If inside thinking or waiting for </think>, skip this chunk
                    if inside_thinking or waiting_for_think_end:
                        continue

                    # If not inside thinking, apply regular filtering and yield
                    filtered_content = self._strip_thinking_tags(text_buffer)
                    text_buffer = ""  # Clear buffer after processing
                    if filtered_content:
                        has_sent_content = True
                        response_text_parts.append(filtered_content)
                        chunk = AgentStreamChunk(
                            chunk_type=chunk.chunk_type,
                            content=filtered_content,
                            metadata=chunk.metadata
                        )
                    else:
                        continue  # Skip empty chunks after filtering
                elif chunk.chunk_type == "error":
                    success = False
                elif chunk.chunk_type == "done" and not has_sent_content:
                    # 응답이 전부 필터링됨 - 기본 메시지 전송
                    default_msg = "죄송합니다. 해당 질문에 대한 관련 정보를 지식 베이스에서 찾을 수 없습니다. 다른 키워드로 검색하거나 질문을 더 구체적으로 해주세요."
                    yield AgentStreamChunk(chunk_type="text", content=default_msg)
                    response_text_parts.append(default_msg)

                # Stream figure reference images before done chunk
                if chunk.chunk_type == "done":
                    full_response_for_images = ''.join(response_text_parts)
                    # Debug: Log context.metadata for image lookup
                    print(f"[Orchestrator] Before image lookup - metadata keys: {list(context.metadata.keys()) if context.metadata else 'None'}", flush=True)
                    if context.metadata and 'sources' in context.metadata:
                        sources = context.metadata['sources']
                        print(f"[Orchestrator] Sources count: {len(sources)}", flush=True)
                        for s in sources[:3]:
                            print(f"[Orchestrator] Source: doc_id={s.get('doc_id')}, page={s.get('page_number')}", flush=True)
                    if full_response_for_images:
                        async for img_chunk in self._stream_figure_images(
                            full_response_for_images, context
                        ):
                            yield img_chunk

                yield chunk
        except Exception as e:
            logger.error(f"[Orchestrator] ERROR: {e}")
            success = False
            raise
        finally:
            # Log query after stream completes (in finally to ensure logging even on error)
            execution_time_ms = int((time.time() - start_time) * 1000)
            full_response = ''.join(response_text_parts)
            response_summary = full_response[:500] if full_response else None

            # Estimate tokens (approximately 4 chars per token)
            input_tokens = len(request.task) // 4
            output_tokens = len(full_response) // 4

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
                response_summary=response_summary,
                input_tokens=input_tokens,
                output_tokens=output_tokens
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
            url_source=url_source,
            use_deep_agent=getattr(request, 'use_deep_agent', False)
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

        # Estimate tokens
        input_tokens = len(request.task) // 4
        output_tokens = len(synthesized_answer) // 4 if synthesized_answer else 0

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
            response_summary=synthesized_answer[:500] if synthesized_answer else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens
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
            url_source=url_source,
            use_deep_agent=getattr(request, 'use_deep_agent', False)
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

        # Debug: Log enable_multi_agent and use_deep_agent values
        print(f"[stream_enterprise] enable_multi_agent={request.enable_multi_agent}, use_deep_agent={request.use_deep_agent}", flush=True)

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
                url_context=request.url_context,
                use_deep_agent=request.use_deep_agent  # Pass Deep Agent flag
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

        # Build trace data for UI visualization
        dag_tasks_for_ui = [
            {
                "task_id": t.task_id,
                "description": t.description[:200],
                "agent_type": t.agent_type.value,
                "status": t.status.value,
                "dependencies": t.dependencies
            }
            for t in dag.tasks.values()
        ]

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
            },
            trace_data={
                "trace_id": str(trace.trace_id),
                "dag": {
                    "tasks": dag_tasks_for_ui,
                    "execution_batches": dag.execution_batches,
                    "parallelism_type": dag.parallelism_type.value
                },
                "timeline": []
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
                content=self._strip_thinking_tags(synthesized_answer),
                metadata={"is_final": True}
            )
        elif successful_results:
            single_result = list(successful_results.values())[0]
            yield ParallelStreamChunk(
                chunk_type="synthesis",
                content=self._strip_thinking_tags(single_result.answer),
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

        # Estimate tokens from streamed results
        input_tokens = len(request.task) // 4
        output_tokens = sum(len(r.answer) // 4 for r in successful_results.values() if r.answer) if successful_results else 0

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
            response_summary=None,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )

        yield ParallelStreamChunk(
            chunk_type="done",
            metadata={
                "execution_time": execution_time,
                "successful_tasks": len(successful_results),
                "total_tasks": len(dag.tasks)
            }
        )

    # =========================================================================
    # Deep Agent Execution Methods
    # =========================================================================

    async def _execute_deep_agent(
        self,
        request: AgentRequest,
        context: AgentContext,
        agent_type: AgentType,
        user_id: Optional[str],
        start_time: float
    ) -> AgentResponse:
        """
        Execute request using Deep Agents framework.

        Args:
            request: The agent request
            context: Agent execution context
            agent_type: Classified agent type
            user_id: Optional user ID
            start_time: Execution start time

        Returns:
            AgentResponse with answer and metadata
        """
        logger.info(f"[Orchestrator] Executing with Deep Agent: type={agent_type.value}")

        deep_agent = self.get_deep_agent(agent_type)
        if deep_agent is None:
            # Fallback to regular execution if Deep Agents not available
            logger.warning("[Orchestrator] Deep Agents not available, falling back to regular execution")
            # Create a new request without use_deep_agent to avoid infinite loop
            fallback_request = AgentRequest(
                task=request.task,
                agent_type=request.agent_type,
                session_id=request.session_id,
                language=request.language,
                max_steps=request.max_steps,
                include_sources=request.include_sources,
                stream=False,
                file_context=request.file_context,
                url_context=request.url_context,
                ui_context=request.ui_context,
                use_deep_agent=False
            )
            return await self.execute(fallback_request, user_id)

        try:
            # Execute via Deep Agent
            result = await deep_agent.execute(request.task, context)

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Estimate tokens
            input_tokens = len(request.task) // 4
            output_tokens = len(result.answer) // 4 if result.answer else 0

            # Log query
            await self._log_query(
                query_text=request.task,
                user_id=user_id,
                session_id=request.session_id,
                agent_type=f"deep_{agent_type.value}",
                intent_type=None,
                category=None,
                language=request.language,
                execution_time_ms=execution_time_ms,
                success=result.success,
                response_summary=result.answer[:500] if result.answer else None,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )

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

        except Exception as e:
            logger.error(f"[Orchestrator] Deep Agent execution failed: {e}")
            execution_time = time.time() - start_time
            return AgentResponse(
                answer=f"Deep Agent 실행 중 오류가 발생했습니다: {str(e)}",
                agent_type=agent_type,
                session_id=context.session_id,
                steps=0,
                sources=[],
                execution_time=execution_time,
                success=False,
                error=str(e)
            )

    async def _stream_deep_agent(
        self,
        request: AgentRequest,
        context: AgentContext,
        agent_type: AgentType,
        user_id: Optional[str],
        start_time: float
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        Stream execution using Deep Agents framework.

        Args:
            request: The agent request
            context: Agent execution context
            agent_type: Classified agent type
            user_id: Optional user ID
            start_time: Execution start time

        Yields:
            AgentStreamChunk with incremental results
        """
        print(f"[_stream_deep_agent] Starting Deep Agent streaming: type={agent_type.value}", flush=True)

        deep_agent = self.get_deep_agent(agent_type)
        print(f"[_stream_deep_agent] deep_agent={deep_agent}", flush=True)
        if deep_agent is None:
            yield AgentStreamChunk(
                chunk_type="error",
                content="Deep Agents가 설치되지 않았습니다. pip install deepagents langchain-openai를 실행하세요."
            )
            return

        response_text_parts = []
        success = True

        has_sent_content = False
        try:
            async for chunk in deep_agent.stream(request.task, context):
                # Filter thinking tags from text content
                if chunk.chunk_type == "text" and chunk.content:
                    filtered_content = self._strip_thinking_tags(chunk.content)
                    if filtered_content:
                        has_sent_content = True
                        response_text_parts.append(filtered_content)
                        chunk = AgentStreamChunk(
                            chunk_type=chunk.chunk_type,
                            content=filtered_content,
                            metadata=chunk.metadata
                        )
                    else:
                        continue  # Skip empty chunks after filtering
                elif chunk.chunk_type == "error":
                    success = False
                elif chunk.chunk_type == "done" and not has_sent_content:
                    # 응답이 전부 필터링됨 - 기본 메시지 전송
                    default_msg = "죄송합니다. 해당 질문에 대한 관련 정보를 지식 베이스에서 찾을 수 없습니다. 다른 키워드로 검색하거나 질문을 더 구체적으로 해주세요."
                    yield AgentStreamChunk(chunk_type="text", content=default_msg)
                    response_text_parts.append(default_msg)
                yield chunk

        except Exception as e:
            logger.error(f"[Orchestrator] Deep Agent streaming failed: {e}")
            success = False
            yield AgentStreamChunk(
                chunk_type="error",
                content=str(e)
            )
        finally:
            # Log query after stream completes
            execution_time_ms = int((time.time() - start_time) * 1000)
            full_response = ''.join(response_text_parts)
            response_summary = full_response[:500] if full_response else None

            input_tokens = len(request.task) // 4
            output_tokens = len(full_response) // 4

            await self._log_query(
                query_text=request.task,
                user_id=user_id,
                session_id=request.session_id,
                agent_type=f"deep_{agent_type.value}",
                intent_type=None,
                category=None,
                language=request.language,
                execution_time_ms=execution_time_ms,
                success=success,
                response_summary=response_summary,
                input_tokens=input_tokens,
                output_tokens=output_tokens
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
        response_summary: Optional[str],
        input_tokens: int = 0,
        output_tokens: int = 0
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
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
            })
            logger.debug(f"[Orchestrator] Query logged: agent={agent_type}, intent={intent_type}, tokens={input_tokens}+{output_tokens}")
        except Exception as e:
            # Non-blocking - log error but don't fail the request
            logger.warning(f"[Orchestrator] Failed to log query: {e}")

    async def _process_ui_context(
        self,
        ui_context_data: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Process UI context for context-aware AI responses.

        Validates the incoming context, applies role-based filtering,
        and builds a prompt section for the LLM.

        Args:
            ui_context_data: Raw UI context dictionary from frontend
            user_id: User ID for additional role verification

        Returns:
            Formatted context prompt section, or None if processing fails
        """
        try:
            # Parse and validate UI context
            ui_context = UIContext(**ui_context_data)

            # Get user role from context (frontend sends this)
            # For security, in production you might want to verify this
            # against the actual user role from user_id lookup
            user_role = ui_context.user_permission_scope

            # Apply role-based filtering
            filtered_context = filter_ui_context_by_role(ui_context, user_role)

            # Build prompt section for LLM
            prompt_section = build_context_prompt_section(filtered_context)

            logger.debug(f"[Orchestrator] UI context processed: "
                        f"page={ui_context.current_page}, "
                        f"role={user_role}, "
                        f"has_selected_item={ui_context.selected_item is not None}")

            return prompt_section

        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to process UI context: {e}")
            return None

    def _strip_thinking_tags(self, text: str) -> str:
        """
        LLM 응답에서 thinking 관련 콘텐츠 제거
        - <think>...</think> 태그
        - 내부 추론 과정 전체
        """
        if not text:
            return text

        # <think>...</think> 태그와 그 내용 제거 (멀티라인 지원)
        cleaned = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)

        # 내부 추론 패턴 (응답 전체가 이런 패턴이면 무시)
        internal_reasoning_patterns = [
            r'This will help me',
            r'I (?:need to|should|will|\'ll) (?:search|check|look|find|use|try)',
            r'(?:Let me|I\'m going to) (?:search|check|look|find|use|try)',
            r'using the available tools',
            r'(?:First|Next),? I (?:need to|should|will)',
            r'The (?:user|question) (?:is asking|wants|asked)',
            r'I don\'t have (?:enough|any) information',
            r'(?:Maybe|Perhaps) (?:I should|using)',
        ]

        # 응답이 내부 추론인지 확인
        is_internal_reasoning = any(
            re.search(pattern, cleaned, re.IGNORECASE)
            for pattern in internal_reasoning_patterns
        )

        if is_internal_reasoning:
            # 전체 응답이 추론이면 빈 문자열 반환
            return ""

        # 응답이 내부 추론으로 시작하는지 확인
        thinking_start_patterns = [
            r'^Okay,?\s+(?:so\s+)?(?:the user|I)',
            r'^(?:First|Let me|I need to|I should|I\'ll|I will)\s+',
            r'^(?:Hmm|Well|Alright|The user)',
            r'^(?:Since|Looking at|Based on)\s+(?:the|this|my)',
        ]

        is_thinking_response = any(
            re.match(pattern, cleaned, re.IGNORECASE)
            for pattern in thinking_start_patterns
        )

        if is_thinking_response:
            # 마지막 문단에서 실제 답변 찾기
            paragraphs = cleaned.split('\n\n')
            for para in reversed(paragraphs):
                para = para.strip()
                if para and not any(
                    re.match(p, para, re.IGNORECASE)
                    for p in thinking_start_patterns
                ) and not any(
                    re.search(p, para, re.IGNORECASE)
                    for p in internal_reasoning_patterns
                ):
                    return para

        return cleaned.strip()

    async def _stream_figure_images(
        self,
        response_text: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        Detect figure references in response and stream matching images.

        Args:
            response_text: Full response text to search for figure references
            context: Agent context with session info

        Yields:
            AgentStreamChunk with image data for detected figure references
        """
        try:
            from ..services.figure_reference_extractor import get_figure_detector
            from ..services.figure_image_service import FigureImageService
            from ..core.deps import get_image_repository

            detector = get_figure_detector()

            # Detect figure references in response (optional - images can be fetched by page numbers too)
            figure_refs = detector.detect_references(response_text)
            if figure_refs:
                logger.info(f"[Orchestrator] Detected figure references: {figure_refs}")

            # Get document IDs from context metadata
            document_ids = []
            if context.metadata:
                doc_ids = context.metadata.get('document_ids', [])
                if isinstance(doc_ids, list):
                    document_ids = doc_ids
                elif isinstance(doc_ids, str):
                    document_ids = [doc_ids]

            # Collect sources with page numbers for page-based image lookup
            sources = context.metadata.get('sources', []) if context.metadata else []
            doc_pages: dict[str, set] = {}  # {doc_id: {page_numbers}}

            for source in sources:
                if isinstance(source, dict):
                    doc_id = source.get('document_id') or source.get('doc_id')
                    page_num = source.get('page_number') or source.get('page')

                    if doc_id:
                        if doc_id not in document_ids:
                            document_ids.append(doc_id)
                        # Collect page numbers for each document
                        if page_num is not None:
                            if doc_id not in doc_pages:
                                doc_pages[doc_id] = set()
                            doc_pages[doc_id].add(page_num)

            # Check if we have anything to look up (either figure_refs or page_numbers)
            has_page_numbers = any(pages for pages in doc_pages.values())
            print(f"[Orchestrator] Image lookup: doc_ids={document_ids}, figure_refs={figure_refs}, has_pages={has_page_numbers}, doc_pages={dict(doc_pages)}", flush=True)
            if not document_ids or (not figure_refs and not has_page_numbers):
                print("[Orchestrator] No document IDs or page numbers for image lookup - skipping", flush=True)
                return

            # Get image repository
            try:
                image_repo = await get_image_repository()
            except Exception as e:
                logger.warning(f"[Orchestrator] Could not get image repository: {e}")
                return

            # Fetch images using page-based lookup (primary method)
            all_images = []
            for doc_id in document_ids:
                try:
                    page_nums = list(doc_pages.get(doc_id, set()))
                    if page_nums:
                        # Use page-based lookup
                        images = await image_repo.get_by_page_numbers(
                            document_id=doc_id,
                            page_numbers=page_nums,
                            include_data=True
                        )
                        all_images.extend(images)
                        logger.info(f"[Orchestrator] Found {len(images)} images for doc {doc_id} pages {page_nums}")
                    elif figure_refs:
                        # Fallback to figure reference lookup
                        images = await image_repo.get_by_figure_references(
                            document_id=doc_id,
                            figure_references=figure_refs,
                            include_data=True
                        )
                        all_images.extend(images)
                except Exception as e:
                    logger.warning(f"[Orchestrator] Error fetching images for doc {doc_id}: {e}")

            if not all_images:
                logger.debug(f"[Orchestrator] No matching images found for refs: {figure_refs}")
                return

            # Format and yield image chunks
            import base64
            for img in all_images:
                if img.image_data:
                    try:
                        b64_data = base64.b64encode(img.image_data).decode('utf-8')
                        image_chunk = AgentStreamChunk(
                            chunk_type="image",
                            content="",
                            metadata={
                                "image_id": img.image_id,
                                "document_id": img.document_id,
                                "figure_reference": img.figure_reference,
                                "figure_caption": img.figure_caption or img.description or "",
                                "page_number": img.page_number,
                                "width": img.width,
                                "height": img.height,
                                "mime_type": img.mime_type,
                                "data": f"data:{img.mime_type};base64,{b64_data}"
                            }
                        )
                        logger.info(f"[Orchestrator] Streaming image: {img.figure_reference}")
                        yield image_chunk
                    except Exception as e:
                        logger.warning(f"[Orchestrator] Error encoding image {img.image_id}: {e}")

        except ImportError as e:
            logger.debug(f"[Orchestrator] Figure image service not available: {e}")
        except Exception as e:
            logger.error(f"[Orchestrator] Error streaming figure images: {e}")

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
