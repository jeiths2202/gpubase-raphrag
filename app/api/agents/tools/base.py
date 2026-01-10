"""
Base Tool Abstract Class
Defines the interface for all agent tools.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import logging
import json
from pydantic import ValidationError

from ..types import ToolResult, ToolDefinition, AgentContext

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """
    Abstract base class for all agent tools.

    Each tool has:
    - A unique name
    - A description for the LLM
    - Parameter schema (JSON Schema format)
    - An execute method that performs the action
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.description = description
        self._parameters = parameters or self._get_default_parameters()

    @property
    def parameters(self) -> Dict[str, Any]:
        """Get parameter schema (JSON Schema format)"""
        return self._parameters

    @abstractmethod
    def _get_default_parameters(self) -> Dict[str, Any]:
        """Get default parameter schema"""
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    @abstractmethod
    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        """
        Execute the tool with given arguments.

        Args:
            context: Agent execution context
            **kwargs: Tool-specific arguments

        Returns:
            ToolResult with success status and output
        """
        pass

    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate parameters against schema.

        Args:
            params: Parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        schema = self.parameters
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        # Check required parameters
        for req in required:
            if req not in params:
                return False, f"Missing required parameter: {req}"

        # Check parameter types
        for key, value in params.items():
            if key in properties:
                prop_schema = properties[key]
                expected_type = prop_schema.get("type")

                # Skip type check for None values on non-required parameters
                if value is None and key not in required:
                    continue

                if expected_type:
                    if not self._check_type(value, expected_type):
                        return False, f"Parameter '{key}' should be {expected_type}, got {type(value).__name__}"

        return True, None

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected JSON Schema type"""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None)
        }

        expected = type_map.get(expected_type)
        if expected is None:
            return True  # Unknown type, allow

        return isinstance(value, expected)

    def get_definition(self) -> ToolDefinition:
        """Get tool definition for LLM function calling"""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            required=self.parameters.get("required", [])
        )

    def format_output(self, output: Any) -> str:
        """Format output for returning to agent"""
        if isinstance(output, str):
            return output
        if isinstance(output, (dict, list)):
            return json.dumps(output, ensure_ascii=False, indent=2)
        return str(output)

    def create_success_result(
        self,
        output: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Create a successful tool result"""
        return ToolResult(
            success=True,
            output=self.format_output(output),
            error=None,
            metadata=metadata
        )

    def create_error_result(
        self,
        error: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Create an error tool result"""
        return ToolResult(
            success=False,
            output="",
            error=error,
            metadata=metadata
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"


class MockTool(BaseTool):
    """Mock tool for testing"""

    def __init__(self):
        super().__init__(
            name="mock_tool",
            description="A mock tool for testing purposes"
        )

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Input to echo back"
                }
            },
            "required": ["input"]
        }

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        input_value = kwargs.get("input", "")
        return self.create_success_result(
            f"Mock tool received: {input_value}",
            metadata={"tool": "mock"}
        )
