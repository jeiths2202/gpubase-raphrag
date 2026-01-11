"""
Task DAG Builder
Decomposes complex tasks into execution DAGs using hybrid approach:
- Rule-based detection for common patterns (fast)
- LLM-based decomposition for complex tasks (accurate)
"""
from typing import List, Optional, Dict, Any, Tuple
import logging
import re
import json
import uuid

from .types import (
    AgentType, TaskDAG, SubTask, TaskStatus, ParallelismType
)

logger = logging.getLogger(__name__)


# Rule-based patterns for detecting parallelism (multilingual)
PARALLEL_PATTERNS = {
    ParallelismType.FULL: [
        # English
        r"(?:compare|contrast)\s+.+\s+(?:and|with|vs\.?|versus)\s+",
        r"both\s+.+\s+and\s+",
        r"(?:search|find|get|retrieve)\s+.+\s+(?:and\s+also|as\s+well\s+as)\s+",
        r"analyze\s+.+\s+and\s+.+\s+(?:separately|independently)",
        # Korean
        r"(.+)\s*(?:와|과|랑)\s*(.+)\s*(?:비교|대조)",
        r"각각\s*.+\s*(?:대해|관해)",
        r"(.+)\s*(?:도|또한)\s*.+\s*(?:찾아|검색)",
        # Japanese
        r"(.+)と(.+)を(?:比較|対比)",
        r"それぞれ.+について",
        r"(.+)も(.+)も",
    ],
    ParallelismType.PIPELINE: [
        # English
        r"first\s+.+\s+then\s+",
        r"after\s+.+\s+do\s+",
        r"once\s+.+\s+(?:is\s+)?done,?\s+",
        r"step\s*1.+step\s*2",
        # Korean
        r"먼저\s*.+\s*(?:그\s*다음|그리고|후에)",
        r"(.+)\s*한\s*후에?\s*(.+)",
        # Japanese
        r"まず.+(?:次に|その後)",
        r"(.+)した後で(.+)",
    ],
}

# Patterns to detect single-agent tasks (no decomposition needed)
SINGLE_AGENT_PATTERNS = [
    r"^(?:what|how|why|when|where|who)\s+",  # Simple questions
    r"^(?:find|search|get|show)\s+\w+\s+(?:about|for|of)\s+",  # Simple search
    r"^(?:뭐|무엇|어떻게|왜)\s*",  # Korean simple questions
    r"^(?:何|どう|なぜ)\s*",  # Japanese simple questions
]


class DAGBuilder:
    """
    Builds execution DAGs from complex tasks.
    Uses hybrid approach: rules first, LLM for complex cases.
    """

    def __init__(self, llm_adapter=None):
        """
        Initialize DAG builder.

        Args:
            llm_adapter: LLM adapter for complex task decomposition
        """
        self.llm_adapter = llm_adapter
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for efficiency"""
        self._parallel_patterns = {
            ptype: [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]
            for ptype, patterns in PARALLEL_PATTERNS.items()
        }
        self._single_agent_patterns = [
            re.compile(p, re.IGNORECASE | re.UNICODE)
            for p in SINGLE_AGENT_PATTERNS
        ]

    def _is_single_agent_task(self, task: str) -> bool:
        """Check if task is simple enough for single agent"""
        task_clean = task.strip()
        for pattern in self._single_agent_patterns:
            if pattern.match(task_clean):
                return True
        # Also check length - very short tasks are usually single-agent
        if len(task_clean.split()) <= 10:
            return True
        return False

    def _detect_parallelism_type(self, task: str) -> Tuple[ParallelismType, float]:
        """
        Detect parallelism type using rule-based patterns.

        Returns:
            Tuple of (ParallelismType, confidence score)
        """
        task_lower = task.lower()
        best_type = ParallelismType.NONE
        best_confidence = 0.0

        for ptype, patterns in self._parallel_patterns.items():
            for pattern in patterns:
                if pattern.search(task_lower):
                    # Multiple matches increase confidence
                    confidence = 0.7
                    if best_confidence < confidence:
                        best_type = ptype
                        best_confidence = confidence
                    break

        return best_type, best_confidence

    async def build_dag(
        self,
        task: str,
        agent_type: Optional[AgentType] = None,
        language: str = "auto",
        use_llm: bool = True
    ) -> TaskDAG:
        """
        Build execution DAG from task description.

        Args:
            task: User's task description
            agent_type: Optional hint for primary agent type
            language: Response language preference
            use_llm: Whether to use LLM for complex decomposition

        Returns:
            TaskDAG with execution plan
        """
        # 1. Check if task is simple (single agent)
        if self._is_single_agent_task(task):
            logger.info("[DAGBuilder] Simple task detected, creating single-agent DAG")
            return self._create_single_task_dag(task, agent_type)

        # 2. Try rule-based parallelism detection
        parallelism_type, confidence = self._detect_parallelism_type(task)

        if confidence >= 0.7:
            logger.info(f"[DAGBuilder] Rule-based detection: {parallelism_type.value} (confidence={confidence:.2f})")
            return await self._build_rule_based_dag(task, parallelism_type, agent_type, language)

        # 3. Use LLM for complex decomposition
        if use_llm and self.llm_adapter:
            logger.info("[DAGBuilder] Using LLM-based decomposition")
            try:
                return await self._build_llm_dag(task, agent_type, language)
            except Exception as e:
                logger.warning(f"[DAGBuilder] LLM decomposition failed: {e}, falling back to single task")

        # 4. Fallback: single-task DAG
        logger.info("[DAGBuilder] Fallback to single-task DAG")
        return self._create_single_task_dag(task, agent_type)

    def _create_single_task_dag(
        self,
        task: str,
        agent_type: Optional[AgentType] = None
    ) -> TaskDAG:
        """Create a single-node DAG (backward compatible)"""
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        subtask = SubTask(
            task_id=task_id,
            description=task,
            agent_type=agent_type or AgentType.RAG,
            dependencies=[],
            status=TaskStatus.PENDING
        )

        dag = TaskDAG(
            tasks={task_id: subtask},
            root_task=task,
            execution_batches=[[task_id]],
            parallelism_type=ParallelismType.NONE
        )

        return dag

    async def _build_rule_based_dag(
        self,
        task: str,
        parallelism_type: ParallelismType,
        agent_type: Optional[AgentType],
        language: str
    ) -> TaskDAG:
        """Build DAG using rule-based decomposition"""
        # For rule-based, we still use LLM to extract the subtasks,
        # but with simpler prompting since we know the parallelism type
        if self.llm_adapter:
            return await self._build_llm_dag(
                task, agent_type, language,
                hint_parallelism=parallelism_type
            )

        # Without LLM, create basic 2-task parallel DAG for compare patterns
        if parallelism_type == ParallelismType.FULL:
            return self._create_basic_parallel_dag(task, agent_type)

        # Default to single task
        return self._create_single_task_dag(task, agent_type)

    def _create_basic_parallel_dag(
        self,
        task: str,
        agent_type: Optional[AgentType]
    ) -> TaskDAG:
        """Create basic 2-task parallel DAG for compare-style tasks"""
        # Extract parts from task using simple heuristics
        parts = re.split(r'\s+(?:and|vs\.?|versus|와|과|と)\s+', task, maxsplit=1, flags=re.IGNORECASE)

        if len(parts) < 2:
            return self._create_single_task_dag(task, agent_type)

        task1_id = f"task_{uuid.uuid4().hex[:8]}"
        task2_id = f"task_{uuid.uuid4().hex[:8]}"
        synthesis_id = f"synthesis_{uuid.uuid4().hex[:8]}"

        subtask1 = SubTask(
            task_id=task1_id,
            description=parts[0].strip(),
            agent_type=agent_type or AgentType.RAG,
            dependencies=[],
            status=TaskStatus.PENDING
        )

        subtask2 = SubTask(
            task_id=task2_id,
            description=parts[1].strip(),
            agent_type=agent_type or AgentType.RAG,
            dependencies=[],
            status=TaskStatus.PENDING
        )

        # Synthesis task depends on both
        synthesis = SubTask(
            task_id=synthesis_id,
            description=f"Synthesize results: {task}",
            agent_type=AgentType.RAG,
            dependencies=[task1_id, task2_id],
            status=TaskStatus.PENDING,
            metadata={"is_synthesis": True}
        )

        dag = TaskDAG(
            tasks={task1_id: subtask1, task2_id: subtask2, synthesis_id: synthesis},
            root_task=task,
            execution_batches=[[task1_id, task2_id], [synthesis_id]],
            parallelism_type=ParallelismType.FULL
        )

        return dag

    async def _build_llm_dag(
        self,
        task: str,
        agent_type: Optional[AgentType],
        language: str,
        hint_parallelism: Optional[ParallelismType] = None
    ) -> TaskDAG:
        """Build DAG using LLM decomposition"""
        parallelism_hint = ""
        if hint_parallelism:
            parallelism_hint = f"\nNote: This task appears to be {hint_parallelism.value} parallelizable."

        prompt = f"""Decompose this complex task into subtasks for a multi-agent system.

Task: {task}

Available agent types:
- rag: Knowledge base queries, document search, general information
- ims: Issue tracking, bug reports, technical problems (IMS system)
- vision: Image analysis, charts, diagrams
- code: Code generation, review, debugging
- planner: Complex task planning (use sparingly)

{parallelism_hint}

Return a JSON object with this exact structure:
{{
  "subtasks": [
    {{
      "id": "unique_id",
      "description": "What this subtask should accomplish",
      "agent_type": "rag|ims|vision|code|planner",
      "dependencies": ["id_of_task_that_must_complete_first"]
    }}
  ],
  "parallelism": "none|full|partial|pipeline"
}}

Guidelines:
1. Break into 2-5 subtasks maximum (prefer fewer)
2. Identify dependencies (which tasks need results from others)
3. Tasks with no dependencies can run in parallel
4. Use appropriate agent types
5. Keep subtask descriptions actionable and specific

Respond with ONLY the JSON object, no explanation."""

        try:
            response = await self.llm_adapter.generate([
                {"role": "user", "content": prompt}
            ])

            content = response.get("content", "")
            dag_data = self._parse_llm_response(content)
            return self._build_dag_from_llm_response(dag_data, task, agent_type)

        except Exception as e:
            logger.error(f"[DAGBuilder] LLM DAG generation failed: {e}")
            raise

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM response to extract JSON"""
        # Remove markdown code blocks if present
        content = content.strip()
        if content.startswith("```"):
            # Remove opening ```json or ```
            content = re.sub(r'^```(?:json)?\s*', '', content)
            # Remove closing ```
            content = re.sub(r'\s*```$', '', content)

        # Try to find JSON object
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in LLM response")

        return json.loads(json_match.group())

    def _build_dag_from_llm_response(
        self,
        dag_data: Dict[str, Any],
        original_task: str,
        default_agent_type: Optional[AgentType]
    ) -> TaskDAG:
        """Build TaskDAG from parsed LLM response"""
        subtasks_data = dag_data.get("subtasks", [])
        parallelism_str = dag_data.get("parallelism", "none")

        # Map parallelism string to enum
        parallelism_map = {
            "none": ParallelismType.NONE,
            "full": ParallelismType.FULL,
            "partial": ParallelismType.PARTIAL,
            "pipeline": ParallelismType.PIPELINE
        }
        parallelism_type = parallelism_map.get(parallelism_str, ParallelismType.NONE)

        # Build subtasks
        tasks: Dict[str, SubTask] = {}
        for st_data in subtasks_data:
            task_id = st_data.get("id", f"task_{uuid.uuid4().hex[:8]}")

            # Parse agent type
            agent_type_str = st_data.get("agent_type", "rag").lower()
            agent_type_map = {
                "rag": AgentType.RAG,
                "ims": AgentType.IMS,
                "vision": AgentType.VISION,
                "code": AgentType.CODE,
                "planner": AgentType.PLANNER
            }
            agent_type = agent_type_map.get(agent_type_str, default_agent_type or AgentType.RAG)

            subtask = SubTask(
                task_id=task_id,
                description=st_data.get("description", ""),
                agent_type=agent_type,
                dependencies=st_data.get("dependencies", []),
                status=TaskStatus.PENDING
            )
            tasks[task_id] = subtask

        # Validate dependencies exist
        all_task_ids = set(tasks.keys())
        for subtask in tasks.values():
            subtask.dependencies = [dep for dep in subtask.dependencies if dep in all_task_ids]

        # Compute execution batches (topological sort with level detection)
        execution_batches = self._compute_execution_batches(tasks)

        dag = TaskDAG(
            tasks=tasks,
            root_task=original_task,
            execution_batches=execution_batches,
            parallelism_type=parallelism_type
        )

        logger.info(f"[DAGBuilder] Created DAG with {len(tasks)} tasks, "
                   f"{len(execution_batches)} batches, parallelism={parallelism_type.value}")

        return dag

    def _compute_execution_batches(self, tasks: Dict[str, SubTask]) -> List[List[str]]:
        """
        Compute execution batches using topological sort with level detection.
        Tasks in the same batch can run in parallel.
        """
        if not tasks:
            return []

        # Compute in-degree for each task
        in_degree = {task_id: len(task.dependencies) for task_id, task in tasks.items()}

        # Group by dependency level
        batches = []
        remaining = set(tasks.keys())

        while remaining:
            # Find all tasks with no remaining dependencies (in_degree = 0)
            batch = [
                task_id for task_id in remaining
                if in_degree[task_id] == 0
            ]

            if not batch:
                # Cycle detected or error - break and add remaining
                logger.warning("[DAGBuilder] Possible cycle in DAG, adding remaining tasks")
                batch = list(remaining)

            batches.append(batch)

            # Remove processed tasks and update in-degrees
            for task_id in batch:
                remaining.discard(task_id)
                # Decrease in-degree for tasks that depend on this one
                for other_id in remaining:
                    if task_id in tasks[other_id].dependencies:
                        in_degree[other_id] -= 1

        return batches

    def validate_dag(self, dag: TaskDAG) -> Tuple[bool, Optional[str]]:
        """
        Validate a DAG for correctness.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not dag.tasks:
            return False, "DAG has no tasks"

        # Check for cycles
        visited = set()
        rec_stack = set()

        def has_cycle(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            task = dag.tasks.get(task_id)
            if task:
                for dep in task.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.discard(task_id)
            return False

        for task_id in dag.tasks:
            if task_id not in visited:
                if has_cycle(task_id):
                    return False, f"Cycle detected involving task {task_id}"

        # Check all dependencies exist
        for task_id, task in dag.tasks.items():
            for dep in task.dependencies:
                if dep not in dag.tasks:
                    return False, f"Task {task_id} has unknown dependency {dep}"

        # Check execution batches cover all tasks
        batched_tasks = set()
        for batch in dag.execution_batches:
            batched_tasks.update(batch)

        if batched_tasks != set(dag.tasks.keys()):
            return False, "Execution batches don't cover all tasks"

        return True, None


# Singleton instance
_dag_builder_instance: Optional[DAGBuilder] = None


def get_dag_builder(llm_adapter=None) -> DAGBuilder:
    """Get or create the DAG builder instance"""
    global _dag_builder_instance
    if _dag_builder_instance is None:
        _dag_builder_instance = DAGBuilder(llm_adapter)
    elif llm_adapter and _dag_builder_instance.llm_adapter is None:
        _dag_builder_instance.llm_adapter = llm_adapter
    return _dag_builder_instance
