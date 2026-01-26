#!/usr/bin/env python3
"""
Deep Agents Integration Test Script

This script tests that the Deep Agents integration is working correctly.

Run:
    python scripts/test_deep_agents.py
    python scripts/test_deep_agents.py --with-llm  # Test with actual LLM

Required packages:
    pip install deepagents langchain-openai
"""
import sys
import os
import io
import asyncio
import argparse

# Windows console UTF-8 encoding fix
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_header(text: str):
    """헤더 출력"""
    print("\n" + "=" * 60)
    print(f" {text}")
    print("=" * 60)


def print_result(name: str, success: bool, message: str = ""):
    """결과 출력"""
    status = "[PASS]" if success else "[FAIL]"
    print(f"  {status} {name}")
    if message:
        print(f"        {message}")


def test_imports():
    """임포트 테스트"""
    print_header("1. 임포트 테스트")
    results = []

    # Deep Agents 패키지
    try:
        from deepagents import create_deep_agent
        results.append(("deepagents.create_deep_agent", True, ""))
    except ImportError as e:
        results.append(("deepagents.create_deep_agent", False, str(e)))

    try:
        from deepagents.middleware import (
            FilesystemMiddleware,
            SubAgentMiddleware,
            SubAgent,
        )
        results.append(("deepagents.middleware", True, ""))
    except ImportError as e:
        results.append(("deepagents.middleware", False, str(e)))

    # LangChain
    try:
        from langchain_openai import ChatOpenAI
        results.append(("langchain_openai.ChatOpenAI", True, ""))
    except ImportError as e:
        results.append(("langchain_openai.ChatOpenAI", False, str(e)))

    try:
        from langchain_core.tools import tool
        results.append(("langchain_core.tools", True, ""))
    except ImportError as e:
        results.append(("langchain_core.tools", False, str(e)))

    # 프로젝트 모듈
    try:
        from app.api.agents.adapters.deep_agent_adapter import (
            DeepAgentAdapter,
            create_rag_deep_agent,
            create_code_deep_agent,
            create_project_deep_agent,
        )
        results.append(("DeepAgentAdapter", True, ""))
    except ImportError as e:
        results.append(("DeepAgentAdapter", False, str(e)))

    try:
        from app.api.agents.middleware import RAGMiddleware, CodeMiddleware
        results.append(("Custom Middleware", True, ""))
    except ImportError as e:
        results.append(("Custom Middleware", False, str(e)))

    # 결과 출력
    for name, success, message in results:
        print_result(name, success, message)

    passed = sum(1 for _, s, _ in results if s)
    total = len(results)
    print(f"\n  Import Tests: {passed}/{total} passed")

    return all(s for _, s, _ in results)


def test_middleware_creation():
    """미들웨어/도구 생성 테스트"""
    print_header("2. 도구 제공자 테스트")
    results = []

    try:
        from app.api.agents.middleware.rag_middleware import RAGToolsProvider
        rag = RAGToolsProvider()
        tools = rag.get_tools()
        results.append(("RAGToolsProvider", True, f"{len(tools)} tools"))
    except Exception as e:
        results.append(("RAGToolsProvider", False, str(e)))

    try:
        from app.api.agents.middleware.code_middleware import CodeToolsProvider
        code = CodeToolsProvider()
        tools = code.get_tools()
        results.append(("CodeToolsProvider", True, f"{len(tools)} tools"))
    except Exception as e:
        results.append(("CodeToolsProvider", False, str(e)))

    try:
        from app.api.agents.middleware import get_rag_tools, get_code_tools
        rag_tools = get_rag_tools()
        code_tools = get_code_tools()
        results.append(("Convenience functions", True, f"rag={len(rag_tools)}, code={len(code_tools)}"))
    except Exception as e:
        results.append(("Convenience functions", False, str(e)))

    for name, success, message in results:
        print_result(name, success, message)

    passed = sum(1 for _, s, _ in results if s)
    print(f"\n  Tools Tests: {passed}/{len(results)} passed")

    return all(s for _, s, _ in results)


def test_adapter_creation():
    """어댑터 생성 테스트"""
    print_header("3. DeepAgentAdapter 생성 테스트")
    results = []

    try:
        from app.api.agents.adapters.deep_agent_adapter import DeepAgentAdapter
        from app.api.agents.types import AgentType

        adapter = DeepAgentAdapter(
            name="TestAgent",
            agent_type=AgentType.PLANNER,
            description="Test Agent",
            tools=[],
            subagents=[],
        )
        results.append(("Basic DeepAgentAdapter", True, f"name={adapter.name}"))
    except Exception as e:
        results.append(("Basic DeepAgentAdapter", False, str(e)))

    try:
        from app.api.agents.adapters.deep_agent_adapter import create_rag_deep_agent
        agent = create_rag_deep_agent()
        results.append(("create_rag_deep_agent", True, f"name={agent.name}"))
    except Exception as e:
        results.append(("create_rag_deep_agent", False, str(e)))

    try:
        from app.api.agents.adapters.deep_agent_adapter import create_code_deep_agent
        agent = create_code_deep_agent()
        results.append(("create_code_deep_agent", True, f"name={agent.name}"))
    except Exception as e:
        results.append(("create_code_deep_agent", False, str(e)))

    try:
        from app.api.agents.adapters.deep_agent_adapter import create_project_deep_agent
        agent = create_project_deep_agent()
        results.append(("create_project_deep_agent", True, f"name={agent.name}"))
    except Exception as e:
        results.append(("create_project_deep_agent", False, str(e)))

    for name, success, message in results:
        print_result(name, success, message)

    passed = sum(1 for _, s, _ in results if s)
    print(f"\n  Adapter Tests: {passed}/{len(results)} passed")

    return all(s for _, s, _ in results)


async def test_execution_mock():
    """Mock 실행 테스트"""
    print_header("4. Mock 실행 테스트")
    results = []

    try:
        from app.api.agents.adapters.deep_agent_adapter import DeepAgentAdapter
        from app.api.agents.types import AgentType, AgentContext

        # Deep Agents 없이 테스트
        adapter = DeepAgentAdapter(
            name="MockTestAgent",
            agent_type=AgentType.RAG,
            tools=[],
            subagents=[],
        )

        context = AgentContext(
            session_id="test-session",
            user_id="test-user",
            language="ko",
        )

        # 실행 (Deep Agents 없으면 에러 메시지 반환)
        result = await adapter.execute("Test question", context)

        # Deep Agents 설치 여부에 따라 결과 다름
        if result.success:
            results.append(("Mock Execution", True, f"answer_len={len(result.answer)}"))
        else:
            error_str = str(result.error) if result.error else result.answer
            # 예상되는 에러들 (LLM 서버 미실행 또는 패키지 미설치)
            expected_errors = [
                "not installed",
                "deepagents",
                "connection error",
                "connection refused",
                "connect",
            ]
            if any(err in error_str.lower() for err in expected_errors):
                results.append(("Mock Execution (no LLM)", True, "Expected: LLM not available"))
            else:
                results.append(("Mock Execution", False, f"error: {error_str[:100]}"))

    except Exception as e:
        import traceback
        results.append(("Mock Execution", False, f"{type(e).__name__}: {str(e)[:100]}"))

    for name, success, message in results:
        print_result(name, success, message)

    return all(s for _, s, _ in results)


async def test_execution_real():
    """실제 LLM 실행 테스트"""
    print_header("5. 실제 LLM 실행 테스트")

    try:
        from deepagents import create_deep_agent
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
    except ImportError as e:
        print_result("Dependencies", False, f"Required packages not installed: {e}")
        return False

    results = []

    # NIM 연결 테스트
    try:
        llm = ChatOpenAI(
            model="nvidia/llama-3.1-nemotron-nano-8b-v1",
            base_url="http://localhost:12800/v1",
            api_key="not-needed",
            temperature=0.7,
            max_tokens=256,
        )

        response = await llm.ainvoke([
            HumanMessage(content="Say 'OK' if you can hear me.")
        ])

        if response.content:
            results.append(("NIM Connection", True, f"response_len={len(response.content)}"))
        else:
            results.append(("NIM Connection", False, "Empty response"))

    except Exception as e:
        results.append(("NIM Connection", False, str(e)))
        print_result("NIM Connection", False, str(e))
        print("\n  [TIP] NVIDIA NIM 서버가 실행 중인지 확인하세요:")
        print("        http://localhost:12800/v1/chat/completions")
        return False

    # DeepAgentAdapter 실행 테스트
    try:
        from app.api.agents.adapters.deep_agent_adapter import DeepAgentAdapter
        from app.api.agents.types import AgentType, AgentContext

        adapter = DeepAgentAdapter(
            name="RealTestAgent",
            agent_type=AgentType.RAG,
            enable_subagents=False,
            enable_filesystem=False,
            enable_todolist=False,
        )

        context = AgentContext(
            session_id="test-session",
            user_id="test-user",
            language="ko",
        )

        result = await adapter.execute("안녕하세요! 간단히 자기소개 해주세요.", context)

        if result.success:
            results.append(("DeepAgent Execution", True, f"time={result.execution_time:.2f}s"))
            print(f"\n  [응답 미리보기]\n  {result.answer[:200]}...")
        else:
            results.append(("DeepAgent Execution", False, result.error))

    except Exception as e:
        results.append(("DeepAgent Execution", False, str(e)))

    for name, success, message in results:
        print_result(name, success, message)

    return all(s for _, s, _ in results)


async def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="Deep Agents 통합 테스트")
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="실제 LLM 연동 테스트 실행"
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("       Deep Agents 통합 테스트")
    print("=" * 60)

    all_passed = True

    # 기본 테스트
    all_passed &= test_imports()
    all_passed &= test_middleware_creation()
    all_passed &= test_adapter_creation()
    all_passed &= await test_execution_mock()

    # 실제 LLM 테스트 (선택)
    if args.with_llm:
        all_passed &= await test_execution_real()
    else:
        print("\n" + "-" * 60)
        print("  [INFO] 실제 LLM 테스트를 실행하려면:")
        print("         python scripts/test_deep_agents.py --with-llm")
        print("-" * 60)

    # 최종 결과
    print("\n" + "=" * 60)
    if all_passed:
        print("  [SUCCESS] 모든 테스트 통과!")
    else:
        print("  [FAILED] 일부 테스트 실패")
    print("=" * 60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
