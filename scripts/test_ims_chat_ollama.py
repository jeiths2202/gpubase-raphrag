"""
Test IMS Chat with Ollama (Gemma3:1b)

This script tests the IMS Chat API using a local Ollama model.
Run this script to verify the IMS chat functionality before deploying to GPU-based LLM.

Usage:
    python scripts/test_ims_chat_ollama.py

Prerequisites:
    - Ollama must be running: ollama serve
    - Gemma3:1b model must be installed: ollama pull gemma3:1b
    - API server must be running with USE_OLLAMA=true
"""

import asyncio
import aiohttp
import json
import os
import sys
import io

# Fix Windows console encoding for UTF-8
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_ollama_connection():
    """Test if Ollama is running and gemma3:1b is available."""
    print("=" * 60)
    print("[1] Testing Ollama connection...")
    print("=" * 60)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:11434/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    print(f"[OK] Ollama is running")
                    print(f"  Available models: {models}")

                    if any("gemma3:1b" in m for m in models):
                        print(f"[OK] gemma3:1b is available")
                        return True
                    else:
                        print(f"[FAIL] gemma3:1b not found. Run: ollama pull gemma3:1b")
                        return False
                else:
                    print(f"[FAIL] Ollama returned status {resp.status}")
                    return False
    except Exception as e:
        print(f"[FAIL] Failed to connect to Ollama: {e}")
        print("  Make sure Ollama is running: ollama serve")
        return False


async def test_ollama_adapter():
    """Test the Ollama LLM adapter directly."""
    print("\n" + "=" * 60)
    print("[2] Testing Ollama LLM Adapter...")
    print("=" * 60)

    try:
        from app.api.adapters.ollama import OllamaLLMAdapter
        from app.api.ports.llm_port import LLMMessage, LLMRole

        adapter = OllamaLLMAdapter(model="gemma3:1b")

        # Test health check
        is_healthy = await adapter.health_check()
        print(f"[OK] Health check: {'passed' if is_healthy else 'failed'}")

        # Test simple generation
        messages = [
            LLMMessage(role=LLMRole.USER, content="Hello, what is 2+2?")
        ]

        print("  Sending test message: 'Hello, what is 2+2?'")
        response = await adapter.generate(messages)
        print(f"[OK] Response received ({response.usage.total_tokens} tokens)")
        print(f"  Content: {response.content[:200]}...")

        return True

    except Exception as e:
        print(f"[FAIL] Adapter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ims_chat_service():
    """Test the IMS Chat service with mock issues."""
    print("\n" + "=" * 60)
    print("[3] Testing IMS RAG Integration Service...")
    print("=" * 60)

    # Set environment variable to use Ollama
    os.environ["USE_OLLAMA"] = "true"
    os.environ["OLLAMA_MODEL"] = "gemma3:1b"

    try:
        from app.api.services.ims_rag_integration import (
            IMSRAGIntegrationService,
            reset_ims_rag_service
        )
        from app.api.adapters.ollama import OllamaLLMAdapter
        from app.api.ims_crawler.domain.entities import Issue, IssueStatus, IssuePriority
        from app.api.models.ims_chat import IMSChatRequest
        from uuid import uuid4
        from datetime import datetime

        # Reset singleton to use Ollama
        reset_ims_rag_service()

        # Create mock issue repository
        class MockIssueRepository:
            def __init__(self):
                self.issues = [
                    Issue(
                        id=uuid4(),
                        ims_id="IMS-12345",
                        user_id=uuid4(),
                        title="MSCASMC 토큰 인증 오류",
                        description="MSCASMC 서비스 접속 시 토큰 인증 실패 오류 발생",
                        status=IssueStatus.IN_PROGRESS,
                        priority=IssuePriority.HIGH,
                        status_raw="In Progress",
                        priority_raw="High",
                        product="OpenFrame",
                        version="7.0",
                        module="MSCASMC",
                        customer="삼성전자",
                        reporter="김철수",
                        issue_details="토큰 발급 후 1시간 이내에 토큰이 만료됨. 환경변수 TOKEN_TIMEOUT 설정 확인 필요.",
                        action_no="1. 환경변수 확인\n2. 토큰 재발급\n3. 서비스 재시작",
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    ),
                    Issue(
                        id=uuid4(),
                        ims_id="IMS-12346",
                        user_id=uuid4(),
                        title="ProSort 메모리 부족 오류",
                        description="대용량 데이터 정렬 시 메모리 부족 오류 발생",
                        status=IssueStatus.OPEN,
                        priority=IssuePriority.CRITICAL,
                        status_raw="Open",
                        priority_raw="Critical",
                        product="ProSort",
                        version="3.0",
                        module="Sort Engine",
                        customer="LG전자",
                        reporter="이영희",
                        issue_details="10GB 이상의 파일 정렬 시 OutOfMemory 오류. SORT_MEMORY 파라미터 조정 필요.",
                        action_no="1. SORT_MEMORY 값 증가\n2. 임시 디렉토리 공간 확보\n3. 청크 단위 처리 적용",
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                ]

            async def find_by_ids_with_details(self, issue_ids, user_id):
                return self.issues

        # Create service with mock repository
        llm = OllamaLLMAdapter(model="gemma3:1b")
        mock_repo = MockIssueRepository()

        service = IMSRAGIntegrationService(llm=llm, issue_repository=mock_repo)

        # Test chat request
        request = IMSChatRequest(
            question="MSCASMC 토큰 오류 해결 방법을 알려주세요",
            issue_ids=[issue.id for issue in mock_repo.issues],
            stream=False,
            max_context_issues=10
        )

        print("  Question: 'MSCASMC 토큰 오류 해결 방법을 알려주세요'")
        print("  Context: 2 mock IMS issues")
        print("  Generating response...")

        # Call chat
        response = await service.chat(request, mock_repo.issues[0].user_id)

        print(f"[OK] Response generated!")
        print(f"  Tokens: {response.total_tokens} (input: {response.input_tokens}, output: {response.output_tokens})")
        print(f"\n  AI Response:\n  {'-' * 50}")
        print(f"  {response.content}")
        print(f"  {'-' * 50}")

        return True

    except Exception as e:
        print(f"[FAIL] Service test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_streaming():
    """Test streaming response."""
    print("\n" + "=" * 60)
    print("[4] Testing Streaming Response...")
    print("=" * 60)

    os.environ["USE_OLLAMA"] = "true"
    os.environ["OLLAMA_MODEL"] = "gemma3:1b"

    try:
        from app.api.services.ims_rag_integration import IMSRAGIntegrationService
        from app.api.adapters.ollama import OllamaLLMAdapter
        from app.api.ims_crawler.domain.entities import Issue, IssueStatus, IssuePriority
        from app.api.models.ims_chat import IMSChatRequest
        from uuid import uuid4
        from datetime import datetime

        # Create mock issue repository (same as above)
        class MockIssueRepository:
            def __init__(self):
                self.issues = [
                    Issue(
                        id=uuid4(),
                        ims_id="IMS-12345",
                        user_id=uuid4(),
                        title="MSCASMC 토큰 인증 오류",
                        description="MSCASMC 서비스 접속 시 토큰 인증 실패 오류 발생",
                        status=IssueStatus.IN_PROGRESS,
                        priority=IssuePriority.HIGH,
                        status_raw="In Progress",
                        priority_raw="High",
                        product="OpenFrame",
                        version="7.0",
                        module="MSCASMC",
                        customer="삼성전자",
                        reporter="김철수",
                        issue_details="토큰 발급 후 1시간 이내에 토큰이 만료됨.",
                        action_no="1. 환경변수 확인\n2. 토큰 재발급",
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                ]

            async def find_by_ids_with_details(self, issue_ids, user_id):
                return self.issues

        llm = OllamaLLMAdapter(model="gemma3:1b")
        mock_repo = MockIssueRepository()
        service = IMSRAGIntegrationService(llm=llm, issue_repository=mock_repo)

        request = IMSChatRequest(
            question="이 이슈에 대해 간단히 설명해주세요",
            issue_ids=[issue.id for issue in mock_repo.issues],
            stream=True,
            max_context_issues=10
        )

        print("  Question: '이 이슈에 대해 간단히 설명해주세요'")
        print("  Streaming response:")
        print("  " + "-" * 50)

        # Stream response
        full_response = ""
        async for event in service.chat_stream(request, mock_repo.issues[0].user_id):
            if event.event == "token":
                content = event.data.get("content", "")
                print(content, end="", flush=True)
                full_response += content
            elif event.event == "done":
                print(f"\n  {'-' * 50}")
                print(f"[OK] Streaming completed!")

        return True

    except Exception as e:
        print(f"[FAIL] Streaming test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("IMS Chat with Ollama (Gemma3:1b) - Test Suite")
    print("=" * 60 + "\n")

    results = []

    # Test 1: Ollama connection
    results.append(("Ollama Connection", await test_ollama_connection()))

    if not results[0][1]:
        print("\n[FAIL] Cannot proceed without Ollama. Please start Ollama first.")
        return

    # Test 2: Ollama adapter
    results.append(("Ollama Adapter", await test_ollama_adapter()))

    # Test 3: IMS Chat service
    results.append(("IMS Chat Service", await test_ims_chat_service()))

    # Test 4: Streaming
    results.append(("Streaming Response", await test_streaming()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "[OK] PASSED" if passed else "[FAIL] FAILED"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("All tests passed! IMS Chat is ready for testing.")
        print("\nTo start the API server with Ollama:")
        print("  set USE_OLLAMA=true && python -m app.api.main --mode develop")
    else:
        print("Some tests failed. Please check the errors above.")

    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
