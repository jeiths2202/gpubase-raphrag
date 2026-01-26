"""
Deep Agent Adapter Test Script
Minimal functionality test (using Ollama qwen2.5:3b)
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.agents.adapters import (
    DeepAgentAdapter,
    create_deep_agent_adapter,
    create_rag_deep_agent,
    register_deep_agent,
    enable_deep_agents,
    get_deep_agent,
)
from app.api.agents.types import AgentType, AgentContext
from app.api.agents.registry import AgentRegistry


async def test_basic():
    """Basic execution test"""
    print("=" * 50)
    print("Deep Agent Adapter Basic Test")
    print("=" * 50)

    # Create adapter
    adapter = create_deep_agent_adapter(
        name="TestDeepAgent",
        agent_type=AgentType.PLANNER,
        system_prompt="You are a helpful assistant. Answer concisely.",
    )

    # Create context
    context = AgentContext(
        session_id="test-session",
        user_id="test-user",
        language="en"
    )

    # Test question
    task = "What is the difference between a list and a tuple in Python? Explain briefly."

    print(f"\nQuestion: {task}\n")
    print("Executing...")

    # Execute
    result = await adapter.execute(task, context)

    print(f"\nResult:")
    print(f"  - Success: {result.success}")
    print(f"  - Steps: {result.steps}")
    print(f"  - Execution time: {result.execution_time:.2f}s")
    print(f"\nAnswer:\n{result.answer}")

    if result.error:
        print(f"\nError: {result.error}")

    return result.success


async def test_streaming():
    """Streaming test"""
    print("\n" + "=" * 50)
    print("Deep Agent Adapter Streaming Test")
    print("=" * 50)

    adapter = create_deep_agent_adapter(
        name="StreamingAgent",
        agent_type=AgentType.RAG,
    )

    context = AgentContext(session_id="test-stream")
    task = "Hello, what is 2 + 2?"

    print(f"\nQuestion: {task}\n")
    print("Streaming response:")

    async for chunk in adapter.stream(task, context):
        if chunk.chunk_type == "text":
            print(chunk.content, end="", flush=True)
        elif chunk.chunk_type == "done":
            exec_time = chunk.metadata.get('execution_time', 0) if chunk.metadata else 0
            print(f"\n\nDone (execution time: {exec_time:.2f}s)")
        elif chunk.chunk_type == "error":
            print(f"\nError: {chunk.content}")

    return True


async def test_rag_tools_creation():
    """RAG tools creation test"""
    print("\n" + "=" * 50)
    print("RAG Tools Creation Test")
    print("=" * 50)

    try:
        from app.api.agents.middleware import get_rag_tools

        tools = get_rag_tools()
        print(f"\nRAG tools created: {len(tools)}")

        for tool in tools:
            print(f"  - {tool.name}: {tool.description[:50]}...")

        return len(tools) > 0

    except Exception as e:
        print(f"\nError creating RAG tools: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_rag_deep_agent():
    """RAG Deep Agent creation test"""
    print("\n" + "=" * 50)
    print("RAG Deep Agent Creation Test")
    print("=" * 50)

    try:
        # Create RAG Deep Agent
        agent = create_rag_deep_agent(
            name="TestRAGAgent",
        )

        print(f"\nAgent created: {agent.name}")
        print(f"Agent type: {agent.agent_type}")
        print(f"Tools count: {len(agent._custom_tools)}")

        for tool in agent._custom_tools:
            print(f"  - {tool.name}")

        return True

    except Exception as e:
        print(f"\nError creating RAG Deep Agent: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_registry_integration():
    """Registry integration test"""
    print("\n" + "=" * 50)
    print("Registry Integration Test")
    print("=" * 50)

    try:
        # Create new registry for testing
        registry = AgentRegistry()

        # Register Deep Agent for RAG type
        success = register_deep_agent(
            agent_type=AgentType.RAG,
            registry=registry,
            name="IntegratedRAGAgent",
        )

        print(f"\nDeep Agent registered: {success}")

        if success:
            # Get agent from registry
            agent = registry.get(AgentType.RAG)
            print(f"Agent from registry: {agent.name}")
            print(f"Agent type: {agent.agent_type}")

            # Verify it's a DeepAgentAdapter
            is_deep = isinstance(agent, DeepAgentAdapter)
            print(f"Is DeepAgentAdapter: {is_deep}")

            return is_deep

        return False

    except Exception as e:
        print(f"\nError in registry integration: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_get_deep_agent():
    """Direct Deep Agent creation test"""
    print("\n" + "=" * 50)
    print("Direct Deep Agent Creation Test")
    print("=" * 50)

    try:
        # Get Deep Agent directly (bypass registry)
        agent = get_deep_agent(
            agent_type=AgentType.PLANNER,
            name="DirectPlannerAgent",
        )

        print(f"\nAgent created: {agent.name}")
        print(f"Agent type: {agent.agent_type}")

        # Test execution
        context = AgentContext(session_id="test-direct")
        result = await agent.execute("What is 1+1?", context)

        print(f"Execution success: {result.success}")
        print(f"Answer preview: {result.answer[:100]}...")

        return result.success

    except Exception as e:
        print(f"\nError in direct creation: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test runner"""
    print("\nDeep Agent Adapter Test Start\n")

    # Check Ollama connection
    from app.api.agents.adapters import get_ollama_adapter
    ollama = get_ollama_adapter()
    is_available = await ollama.health_check()

    if not is_available:
        print("Warning: Ollama is not running.")
        print("Start Ollama: ollama serve")
        print("Download model: ollama pull qwen2.5:3b")
        return

    print("Ollama connection confirmed\n")

    # Run tests
    try:
        success1 = await test_basic()
        success2 = await test_streaming()
        success3 = await test_rag_tools_creation()
        success4 = await test_rag_deep_agent()
        success5 = await test_registry_integration()
        success6 = await test_get_deep_agent()

        print("\n" + "=" * 50)
        print("Test Results")
        print("=" * 50)
        print(f"Basic test: {'PASS' if success1 else 'FAIL'}")
        print(f"Streaming test: {'PASS' if success2 else 'FAIL'}")
        print(f"RAG tools creation: {'PASS' if success3 else 'FAIL'}")
        print(f"RAG Deep Agent: {'PASS' if success4 else 'FAIL'}")
        print(f"Registry integration: {'PASS' if success5 else 'FAIL'}")
        print(f"Direct Deep Agent: {'PASS' if success6 else 'FAIL'}")

        all_pass = all([success1, success2, success3, success4, success5, success6])
        print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILED'}")

    except Exception as e:
        print(f"\nTest error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
