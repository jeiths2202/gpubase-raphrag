"""
Auto Planner Agent

Creates execution plans for the Auto Agent orchestrator.
Analyzes user tasks, decomposes into subtasks, and generates ExecutionPlan.
"""
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, AsyncGenerator

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk,
    ParallelismType
)
from .types import (
    ExecutionPlan, PlannedTask, EnhancedRetryConfig,
    AutoAgentMemoryContext, PlanStatus
)

logger = logging.getLogger(__name__)


# Agent type for internal use (not exposed in AgentType enum)
AUTO_PLANNER_TYPE = "auto_planner"


class AutoPlannerAgent(BaseAgent):
    """
    Planner Agent for the Auto Agent orchestration system.

    Responsibilities:
    - Analyze user intent with memory context
    - Decompose tasks into sub-tasks with dependencies
    - Detect parallelism opportunities
    - Estimate confidence per task
    - Define retry policy
    """

    def __init__(
        self,
        llm_adapter=None,
        name: str = "AutoPlannerAgent",
        description: str = "Plans and decomposes complex tasks for multi-agent execution"
    ):
        """
        Initialize the Auto Planner Agent.

        Args:
            llm_adapter: LLM adapter for generating plans
            name: Agent name
            description: Agent description
        """
        super().__init__(
            name=name,
            agent_type=AgentType.PLANNER,
            description=description,
            tools=[],  # Planner doesn't use tools directly
        )
        self._llm_adapter = llm_adapter
        self._system_prompt = self._load_planner_prompt()

    @property
    def llm_adapter(self):
        """Lazy load LLM adapter"""
        if self._llm_adapter is None:
            from ..adapters.ollama_adapter import get_llm_adapter
            self._llm_adapter = get_llm_adapter()
        return self._llm_adapter

    def _load_planner_prompt(self) -> str:
        """Load the planner system prompt"""
        prompt_file = Path(__file__).parent / "prompts" / "auto_planner.txt"
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """Fallback prompt if file not found"""
        return """You are an AI Planner Agent. Analyze tasks and create execution plans.

Return JSON with:
- decomposed_tasks: list of {task_id, description, agent_type, dependencies, priority, estimated_confidence}
- parallelism_strategy: none|full|partial|pipeline
- execution_batches: list of task_id lists
- estimated_total_confidence: float 0-1
- internal_reasoning: your analysis (hidden from user)
"""

    async def create_plan(
        self,
        task: str,
        memory_context: Optional[AutoAgentMemoryContext] = None,
        context: Optional[AgentContext] = None
    ) -> ExecutionPlan:
        """
        Create an execution plan for the given task.

        Args:
            task: User's task description
            memory_context: Memory context for informed planning
            context: Agent execution context

        Returns:
            ExecutionPlan with decomposed tasks and execution strategy
        """
        # Build the planning prompt
        planning_prompt = self._build_planning_prompt(task, memory_context, context)

        # Call LLM for plan generation
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": planning_prompt}
        ]

        try:
            response = await self.llm_adapter.generate(messages)
            plan_json = self._parse_plan_response(response.get("content", ""))
            plan = self._build_execution_plan(plan_json, task)

            logger.info(
                f"[AutoPlannerAgent] Created plan with {len(plan.decomposed_tasks)} tasks, "
                f"strategy={plan.parallelism_strategy.value}"
            )

            return plan

        except Exception as e:
            logger.error(f"[AutoPlannerAgent] Plan creation failed: {e}")
            # Return a fallback single-task plan
            return self._create_fallback_plan(task)

    def _build_planning_prompt(
        self,
        task: str,
        memory_context: Optional[AutoAgentMemoryContext],
        context: Optional[AgentContext]
    ) -> str:
        """Build the prompt for plan generation"""
        prompt_parts = [f"## User Task\n{task}"]

        # Add memory context if available
        if memory_context:
            context_parts = []

            if memory_context.user_memory:
                um = memory_context.user_memory
                if um.language_preference != "auto":
                    context_parts.append(f"- User language preference: {um.language_preference}")
                if um.domain_expertise:
                    context_parts.append(f"- User domains: {', '.join(um.domain_expertise[:5])}")

            if memory_context.system_memory:
                sm = memory_context.system_memory
                # Include agent success rates
                rates = [f"{k}: {v:.0%}" for k, v in list(sm.agent_success_rates.items())[:5]]
                if rates:
                    context_parts.append(f"- Agent success rates: {', '.join(rates)}")

            if memory_context.conversation_memory:
                cm = memory_context.conversation_memory
                if cm.conversation_summary:
                    context_parts.append(f"- Conversation context: {cm.conversation_summary[:200]}")
                if cm.key_topics:
                    context_parts.append(f"- Recent topics: {', '.join(cm.key_topics[:5])}")

            if context_parts:
                prompt_parts.append("\n## Memory Context")
                prompt_parts.extend(context_parts)

        # Add agent context if available
        if context:
            if context.language != "auto":
                prompt_parts.append(f"\n## Response Language: {context.language}")
            if context.file_context:
                prompt_parts.append("\n## Note: User has attached file context (prioritize in plan)")

        prompt_parts.append("\n## Instructions\nCreate an execution plan following the JSON format specified.")

        return "\n".join(prompt_parts)

    def _parse_plan_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM response to extract plan JSON"""
        content = content.strip()

        # Remove markdown code blocks
        if content.startswith("```"):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

        # Find JSON object
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in planner response")

        return json.loads(json_match.group())

    def _build_execution_plan(
        self,
        plan_json: Dict[str, Any],
        original_task: str
    ) -> ExecutionPlan:
        """Build ExecutionPlan from parsed JSON"""
        # Parse decomposed tasks
        decomposed_tasks: List[PlannedTask] = []
        for task_data in plan_json.get("decomposed_tasks", []):
            task_id = task_data.get("task_id", f"t{len(decomposed_tasks)+1:03d}")

            # Map agent type string to enum
            agent_type_str = task_data.get("agent_type", "rag").lower()
            agent_type = self._map_agent_type(agent_type_str)

            planned_task = PlannedTask(
                task_id=task_id,
                description=task_data.get("description", ""),
                agent_type=agent_type,
                dependencies=task_data.get("dependencies", []),
                priority=task_data.get("priority", 1),
                estimated_confidence=task_data.get("estimated_confidence", 0.8),
                timeout_override=task_data.get("timeout_override"),
                context_requirements=task_data.get("context_requirements", []),
                fallback_strategy=task_data.get("fallback_strategy"),
                internal_reasoning=task_data.get("internal_reasoning"),
                metadata=task_data.get("metadata", {})
            )
            decomposed_tasks.append(planned_task)

        # Parse parallelism strategy
        parallelism_str = plan_json.get("parallelism_strategy", "none").lower()
        parallelism_map = {
            "none": ParallelismType.NONE,
            "full": ParallelismType.FULL,
            "partial": ParallelismType.PARTIAL,
            "pipeline": ParallelismType.PIPELINE
        }
        parallelism_strategy = parallelism_map.get(parallelism_str, ParallelismType.NONE)

        # Parse or compute execution batches
        execution_batches = plan_json.get("execution_batches", [])
        if not execution_batches:
            execution_batches = self._compute_execution_batches(decomposed_tasks)

        # Parse retry policy
        retry_data = plan_json.get("retry_policy", {})
        retry_policy = EnhancedRetryConfig(
            max_retries=retry_data.get("max_retries", 2),
            max_replans=retry_data.get("max_replans", 1),
            retry_on_timeout=retry_data.get("retry_on_timeout", True),
            retry_on_empty=retry_data.get("retry_on_empty", True),
            retry_on_low_confidence=retry_data.get("retry_on_low_confidence", True),
            confidence_threshold=retry_data.get("confidence_threshold", 0.6)
        )

        # Create execution plan
        plan = ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            original_task=original_task,
            decomposed_tasks=decomposed_tasks,
            parallelism_strategy=parallelism_strategy,
            execution_batches=execution_batches,
            estimated_total_confidence=plan_json.get("estimated_total_confidence", 0.8),
            retry_policy=retry_policy,
            internal_reasoning=plan_json.get("internal_reasoning"),
            status=PlanStatus.CREATED
        )

        return plan

    def _map_agent_type(self, agent_type_str: str) -> AgentType:
        """Map agent type string to AgentType enum"""
        type_map = {
            "rag": AgentType.RAG,
            "ims": AgentType.IMS,
            "vision": AgentType.VISION,
            "code": AgentType.CODE,
            "planner": AgentType.PLANNER,
        }
        return type_map.get(agent_type_str, AgentType.RAG)

    def _compute_execution_batches(
        self,
        tasks: List[PlannedTask]
    ) -> List[List[str]]:
        """Compute execution batches using topological sort"""
        if not tasks:
            return []

        task_map = {t.task_id: t for t in tasks}
        in_degree = {t.task_id: len(t.dependencies) for t in tasks}

        batches = []
        remaining = set(task_map.keys())

        while remaining:
            # Find tasks with no remaining dependencies
            batch = [
                task_id for task_id in remaining
                if in_degree.get(task_id, 0) == 0
            ]

            if not batch:
                # Cycle detected - add remaining
                logger.warning("[AutoPlannerAgent] Possible cycle in task dependencies")
                batch = list(remaining)

            batches.append(batch)

            # Update in-degrees
            for task_id in batch:
                remaining.discard(task_id)
                for other_id in remaining:
                    if task_id in task_map[other_id].dependencies:
                        in_degree[other_id] -= 1

        return batches

    def _create_fallback_plan(self, task: str) -> ExecutionPlan:
        """Create a simple fallback plan when planning fails"""
        fallback_task = PlannedTask(
            task_id="fallback_001",
            description=task,
            agent_type=AgentType.RAG,
            dependencies=[],
            priority=1,
            estimated_confidence=0.6,
            fallback_strategy="Try alternative search strategies"
        )

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            original_task=task,
            decomposed_tasks=[fallback_task],
            parallelism_strategy=ParallelismType.NONE,
            execution_batches=[["fallback_001"]],
            estimated_total_confidence=0.6,
            retry_policy=EnhancedRetryConfig(),
            status=PlanStatus.CREATED,
            metadata={"is_fallback": True}
        )

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """
        Execute the planner agent (creates a plan).

        Note: This is primarily called internally by the orchestrator.
        The main entry point is create_plan().
        """
        import time
        start_time = time.time()

        try:
            plan = await self.create_plan(task, None, context)

            # Serialize plan to answer
            answer = json.dumps({
                "plan_id": plan.plan_id,
                "task_count": len(plan.decomposed_tasks),
                "parallelism_strategy": plan.parallelism_strategy.value,
                "estimated_confidence": plan.estimated_total_confidence
            }, ensure_ascii=False, indent=2)

            return AgentResult(
                answer=answer,
                agent_type=AgentType.PLANNER,
                steps=1,
                execution_time=time.time() - start_time,
                success=True,
                metadata={"plan": plan}
            )

        except Exception as e:
            logger.error(f"[AutoPlannerAgent] Execution failed: {e}")
            return AgentResult(
                answer=f"Planning failed: {str(e)}",
                agent_type=AgentType.PLANNER,
                steps=1,
                execution_time=time.time() - start_time,
                success=False,
                error=str(e)
            )

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution (planning phase updates)"""
        yield AgentStreamChunk(
            chunk_type="status",
            content="Creating execution plan...",
            metadata={"phase": "planning"}
        )

        result = await self.execute(task, context)

        if result.success:
            yield AgentStreamChunk(
                chunk_type="text",
                content=result.answer
            )
            yield AgentStreamChunk(
                chunk_type="done",
                metadata={"execution_time": result.execution_time}
            )
        else:
            yield AgentStreamChunk(
                chunk_type="error",
                content=result.error or "Planning failed"
            )


# Singleton instance
_planner_agent: Optional[AutoPlannerAgent] = None


def get_auto_planner_agent(llm_adapter=None) -> AutoPlannerAgent:
    """Get or create the Auto Planner Agent instance"""
    global _planner_agent
    if _planner_agent is None:
        _planner_agent = AutoPlannerAgent(llm_adapter=llm_adapter)
    elif llm_adapter and _planner_agent._llm_adapter is None:
        _planner_agent._llm_adapter = llm_adapter
    return _planner_agent
