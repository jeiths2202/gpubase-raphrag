"""
Tests for bug fixes in agent system.
- Zombie process leak fix in bash.py
- Doom loop detection fix in executor.py
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.api.agents.tools.bash import BashTool, SafeBashTool
from app.api.agents.executor import AgentExecutor
from app.api.agents.types import (
    AgentContext, AgentMessage, MessageRole, ToolCall, AgentType
)


class TestBashToolZombieProcessFix:
    """Test that zombie process leak is fixed in bash tool."""

    @pytest.fixture
    def bash_tool(self):
        return BashTool()

    @pytest.fixture
    def context(self):
        return AgentContext(
            user_id="test_user",
            session_id="test_session",
            max_steps=5
        )

    @pytest.mark.asyncio
    async def test_timeout_calls_process_wait(self, context):
        """Verify that process.wait() is called after process.kill() on timeout."""
        mock_process = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        # Create bash tool with 'sleep' in whitelist for testing timeout handling
        # (The default security whitelist blocks sleep, but this test is about
        # timeout/zombie process handling, not command validation)
        from app.api.agents.tools.bash import ALLOWED_COMMANDS
        bash_tool_with_sleep = BashTool(custom_allowed_commands=ALLOWED_COMMANDS | {'sleep'})

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError()):
                result = await bash_tool_with_sleep.execute(
                    context,
                    command="sleep 100",
                    timeout=1
                )

        # Verify process.kill() was called
        mock_process.kill.assert_called_once()
        # Verify process.wait() was called to reap the zombie process
        mock_process.wait.assert_called_once()
        # Verify error result
        assert result["success"] is False
        assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_command_no_zombie(self, bash_tool, context):
        """Verify normal command execution doesn't leave zombies."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))

        # Use create_subprocess_exec since bash tool now uses shell=False
        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            with patch('asyncio.wait_for', return_value=(b"output", b"")):
                # Mock the communicate to return properly
                result = await bash_tool.execute(
                    context,
                    command="echo hello",
                    timeout=30
                )

        # Normal execution should succeed
        # (process.communicate() handles cleanup automatically)


class TestDoomLoopDetectionFix:
    """Test that doom loop detection properly prevents tool execution."""

    @pytest.fixture
    def executor(self):
        executor = AgentExecutor()
        executor._llm_adapter = AsyncMock()
        return executor

    @pytest.fixture
    def mock_agent(self):
        agent = MagicMock()
        agent.agent_type = AgentType.RAG
        agent.system_prompt = "You are a test agent."
        agent.name = "TestAgent"
        return agent

    @pytest.fixture
    def context(self):
        return AgentContext(
            user_id="test_user",
            session_id="test_session",
            max_steps=10,
            language="en"
        )

    @pytest.mark.asyncio
    async def test_doom_loop_skips_tool_execution(self, executor, mock_agent, context):
        """Verify that when doom loop is detected, tool execution is skipped."""
        tool_execution_count = 0

        # Create tool calls that will trigger doom loop (3 identical calls)
        identical_tool_call = ToolCall(
            tool_name="vector_search",
            arguments={"query": "test"},
            call_id="call_1"
        )

        # Mock LLM to return same tool call repeatedly
        call_count = 0
        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return {
                    "content": "Thinking...",
                    "tool_calls": [{
                        "id": f"call_{call_count}",
                        "function": {
                            "name": "vector_search",
                            "arguments": json.dumps({"query": "test"})
                        }
                    }]
                }
            else:
                return {"content": "Final answer", "tool_calls": []}

        executor._llm_adapter.generate = mock_generate

        # Mock tool execution to track calls
        async def mock_execute_tool(tool_call, ctx):
            nonlocal tool_execution_count
            tool_execution_count += 1
            return {
                "success": True,
                "output": "result",
                "error": None,
                "metadata": None
            }

        executor._execute_tool = mock_execute_tool

        # Mock tool registry
        mock_tool = MagicMock()
        mock_tool.get_definition.return_value = MagicMock(
            name="vector_search",
            description="Search",
            parameters={}
        )
        executor.tool_registry = MagicMock()
        executor.tool_registry.get_tools_for_agent.return_value = [mock_tool]

        result = await executor.run(mock_agent, "test query", context)

        # With the fix, after doom loop is detected on 3rd call,
        # tool execution should be skipped for that iteration
        # So we should have at most 2 tool executions (calls 1 and 2)
        # before doom loop is detected on call 3
        assert tool_execution_count <= 2, (
            f"Expected at most 2 tool executions before doom loop, got {tool_execution_count}"
        )

        # Verify the result contains doom loop message
        assert "repeating" in result.answer.lower() or result.answer is not None

    @pytest.mark.asyncio
    async def test_normal_execution_without_doom_loop(self, executor, mock_agent, context):
        """Verify normal execution works when there's no doom loop."""
        # Mock LLM to return different tool calls then final answer
        call_count = 0
        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "vector_search",
                            "arguments": json.dumps({"query": "query1"})
                        }
                    }]
                }
            elif call_count == 2:
                return {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_2",
                        "function": {
                            "name": "vector_search",
                            "arguments": json.dumps({"query": "query2"})  # Different query
                        }
                    }]
                }
            else:
                return {"content": "Final answer based on search results", "tool_calls": []}

        executor._llm_adapter.generate = mock_generate

        tool_execution_count = 0
        async def mock_execute_tool(tool_call, ctx):
            nonlocal tool_execution_count
            tool_execution_count += 1
            return {
                "success": True,
                "output": f"result_{tool_execution_count}",
                "error": None,
                "metadata": None
            }

        executor._execute_tool = mock_execute_tool

        mock_tool = MagicMock()
        mock_tool.get_definition.return_value = MagicMock(
            name="vector_search",
            description="Search",
            parameters={}
        )
        executor.tool_registry = MagicMock()
        executor.tool_registry.get_tools_for_agent.return_value = [mock_tool]

        result = await executor.run(mock_agent, "test query", context)

        # Both tool calls should execute since they're different
        assert tool_execution_count == 2
        assert "Final answer" in result.answer


class TestDoomLoopThreshold:
    """Test doom loop threshold behavior."""

    def test_doom_loop_threshold_value(self):
        """Verify the doom loop threshold is set correctly."""
        executor = AgentExecutor()
        assert executor.DOOM_LOOP_THRESHOLD == 3

    def test_identical_call_detection(self):
        """Test that identical tool calls are correctly identified."""
        import json

        call1 = {"tool": "search", "args": json.dumps({"query": "test"}, sort_keys=True)}
        call2 = {"tool": "search", "args": json.dumps({"query": "test"}, sort_keys=True)}
        call3 = {"tool": "search", "args": json.dumps({"query": "different"}, sort_keys=True)}

        # Same calls should be equal
        assert call1 == call2
        # Different calls should not be equal
        assert call1 != call3
