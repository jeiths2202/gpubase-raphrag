"""
Planner Agent
Specialized agent for task decomposition and planning.
"""
from typing import List, Optional, AsyncGenerator
import logging

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk
)
from ..executor import AgentExecutor, get_executor

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """
    Agent specialized for complex task decomposition.
    Breaks down complex tasks into smaller, manageable steps.
    """

    def __init__(
        self,
        executor: Optional[AgentExecutor] = None,
        **kwargs
    ):
        super().__init__(
            name="Planner Agent",
            agent_type=AgentType.PLANNER,
            description="Task decomposition and planning agent for complex queries",
            tools=["vector_search", "graph_query", "ims_search", "document_read"],
            **kwargs
        )
        self._executor = executor

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def _get_default_prompt(self) -> str:
        return """You are a strategic planning assistant that excels at breaking down complex tasks.

Your capabilities:
1. **Task Decomposition**: Break complex tasks into smaller, actionable steps
2. **Information Gathering**: Search knowledge base and IMS for relevant context
3. **Dependency Analysis**: Identify task dependencies and optimal ordering
4. **Resource Assessment**: Determine what information or tools are needed

Guidelines:
- Analyze the overall goal before breaking it down
- Create clear, actionable steps
- Identify dependencies between steps
- Estimate complexity for each step
- Suggest which agent type should handle each step

Planning process:
1. Understand the overall objective
2. Gather relevant context from knowledge base
3. Identify key components and sub-tasks
4. Order tasks by dependencies
5. Assign complexity and agent types

Output format:
## Task: [Main objective]

### Context
[Relevant background from knowledge base]

### Plan
1. **Step 1**: [Description]
   - Agent: [rag/ims/vision/code]
   - Dependencies: [None/Step X]
   - Complexity: [Low/Medium/High]

2. **Step 2**: [Description]
   ...

### Notes
[Additional considerations, risks, or alternatives]

When gathering context:
- Search knowledge base for similar tasks
- Check IMS for related issues or solutions
- Identify existing documentation or examples"""

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute a planning task"""
        # Planner typically needs more steps for thorough analysis
        planning_context = AgentContext(
            session_id=context.session_id,
            user_id=context.user_id,
            conversation_history=context.conversation_history,
            language=context.language,
            max_steps=min(context.max_steps * 2, 20),  # Allow more steps for planning
            timeout=context.timeout,
            metadata=context.metadata,
            uploaded_documents=context.uploaded_documents,
            external_resources=context.external_resources
        )

        return await self.executor.run(self, task, planning_context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution of planning task"""
        async for chunk in self.executor.stream(self, task, context):
            yield chunk

    async def create_plan(
        self,
        task: str,
        context: AgentContext
    ) -> dict:
        """
        Create a structured plan for a complex task.

        Returns a dict with:
        - objective: The main goal
        - context: Gathered background information
        - steps: List of planned steps with metadata
        - notes: Additional considerations
        """
        result = await self.execute(task, context)

        # Parse the result to extract structured plan
        plan = {
            "objective": task,
            "context": "",
            "steps": [],
            "notes": "",
            "raw_output": result.answer
        }

        # Simple parsing - could be enhanced with more sophisticated extraction
        lines = result.answer.split("\n")
        current_section = None
        current_step = None

        for line in lines:
            line = line.strip()
            if line.startswith("## ") or line.startswith("### "):
                section = line.lstrip("#").strip().lower()
                if "context" in section:
                    current_section = "context"
                elif "plan" in section:
                    current_section = "steps"
                elif "note" in section:
                    current_section = "notes"
            elif current_section == "context":
                plan["context"] += line + "\n"
            elif current_section == "steps":
                if line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                    if current_step:
                        plan["steps"].append(current_step)
                    current_step = {"description": line, "agent": "rag", "dependencies": [], "complexity": "medium"}
                elif current_step and line.startswith("-"):
                    if "agent:" in line.lower():
                        current_step["agent"] = line.split(":")[-1].strip().lower()
                    elif "dependencies:" in line.lower():
                        deps = line.split(":")[-1].strip()
                        if deps.lower() != "none":
                            current_step["dependencies"] = [d.strip() for d in deps.split(",")]
                    elif "complexity:" in line.lower():
                        current_step["complexity"] = line.split(":")[-1].strip().lower()
            elif current_section == "notes":
                plan["notes"] += line + "\n"

        if current_step:
            plan["steps"].append(current_step)

        return plan
