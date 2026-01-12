#!/usr/bin/env python3
"""
Deep Agents 통합 샘플 코드
==========================

이 샘플은 LangChain의 Deep Agents 프레임워크를 HybridRAG KMS 프로젝트에
통합하는 방법을 보여줍니다.

주요 내용:
1. Deep Agents 기본 사용법
2. NVIDIA NIM LLM과 통합
3. 커스텀 미들웨어 작성
4. SubAgent 패턴 활용
5. 기존 WebUI Agent와의 통합 방안

실행 방법:
    python samples/deep_agents_sample.py
    python samples/deep_agents_sample.py --with-llm  # 실제 LLM 사용

필요 패키지:
    pip install deepagents langchain-openai

작성자: Deep Agents Integration Sample
"""

import asyncio
import sys
import io
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

# Windows 콘솔 UTF-8 인코딩 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# =============================================================================
# Deep Agents 임포트
# =============================================================================

try:
    from deepagents import create_deep_agent
    from deepagents.middleware import (
        AgentMiddleware,
        TodoListMiddleware,
        FilesystemMiddleware,
        SubAgentMiddleware,
    )
    from langchain_core.tools import tool
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    DEEPAGENTS_AVAILABLE = True
except ImportError as e:
    print(f"[경고] Deep Agents를 불러올 수 없습니다: {e}")
    print("       pip install deepagents langchain-openai 를 실행하세요.")
    DEEPAGENTS_AVAILABLE = False

try:
    from langchain_openai import ChatOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# =============================================================================
# 1. 기본 Deep Agent 생성 예제
# =============================================================================

def example_basic_deep_agent():
    """
    기본 Deep Agent 생성 예제

    Deep Agents는 create_deep_agent() 함수로 쉽게 생성할 수 있습니다.
    기본적으로 TodoListMiddleware, FilesystemMiddleware, SubAgentMiddleware가
    자동으로 포함됩니다.
    """
    print("\n" + "=" * 60)
    print("1. 기본 Deep Agent 생성 예제")
    print("=" * 60)

    if not DEEPAGENTS_AVAILABLE:
        print("[SKIP] deepagents 패키지가 설치되지 않았습니다.")
        return

    print("""
Deep Agent 생성 코드:

```python
from deepagents import create_deep_agent

# 기본 Deep Agent 생성
agent = create_deep_agent(
    model="claude-3-5-sonnet-20241022",  # 또는 다른 모델
    system_prompt="You are a helpful assistant.",
)

# 기본 미들웨어가 자동 포함됨:
# - TodoListMiddleware: write_todos, read_todos 도구
# - FilesystemMiddleware: ls, read_file, write_file, edit_file, glob, grep, execute
# - SubAgentMiddleware: task 도구 (SubAgent 생성)
```

주요 특징:
- 미들웨어 스택으로 기능 확장
- 자동 Context 관리 (170K 토큰 초과 시 요약)
- 대용량 결과 파일 오프로드 (20K 토큰 초과 시)
- SubAgent로 복잡한 작업 분리
""")


# =============================================================================
# 2. NVIDIA NIM LLM과 통합
# =============================================================================

def example_nvidia_nim_integration():
    """
    NVIDIA NIM LLM과 Deep Agents 통합 예제

    Deep Agents는 OpenAI 호환 API를 사용하므로,
    NVIDIA NIM의 OpenAI 호환 엔드포인트를 사용할 수 있습니다.
    """
    print("\n" + "=" * 60)
    print("2. NVIDIA NIM LLM 통합 예제")
    print("=" * 60)

    print("""
NVIDIA NIM과 Deep Agents 통합:

```python
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

# NVIDIA NIM을 OpenAI 호환 모드로 사용
nim_llm = ChatOpenAI(
    model="nvidia/llama-3.1-nemotron-nano-8b-v1",
    base_url="http://localhost:12800/v1",
    api_key="not-needed",  # NIM은 API 키 불필요
    temperature=0.7,
    max_tokens=4096,
)

# Deep Agent 생성 (NVIDIA NIM 사용)
agent = create_deep_agent(
    model=nim_llm,
    system_prompt=\"\"\"당신은 HybridRAG KMS의 AI 어시스턴트입니다.

역할:
- 사용자 질문에 지식베이스를 검색하여 답변
- 코드 생성 및 분석
- 복잡한 작업은 SubAgent로 분리

언어: 한국어로 응답\"\"\"
)
```

포트 설정:
- 12800: Nemotron Nano 9B (RAG 쿼리)
- 12802: Mistral NeMo 12B (코드 생성)
""")


# =============================================================================
# 3. 커스텀 미들웨어 작성
# =============================================================================

def example_custom_middleware():
    """
    커스텀 미들웨어 작성 예제

    Deep Agents의 핵심은 미들웨어 패턴입니다.
    커스텀 미들웨어를 작성하여 기능을 확장할 수 있습니다.
    """
    print("\n" + "=" * 60)
    print("3. 커스텀 미들웨어 작성 예제")
    print("=" * 60)

    print("""
커스텀 미들웨어 구현:

```python
from deepagents.middleware import AgentMiddleware
from langchain_core.tools import tool
from typing import Any, Dict, List

class RAGMiddleware(AgentMiddleware):
    \"\"\"
    RAG (Retrieval-Augmented Generation) 미들웨어

    지식베이스 검색 도구를 에이전트에 주입합니다.
    \"\"\"

    def __init__(self, vector_store, graph_store=None):
        self.vector_store = vector_store
        self.graph_store = graph_store

    def get_tools(self) -> List:
        \"\"\"미들웨어가 제공하는 도구 목록\"\"\"

        @tool
        def vector_search(query: str, top_k: int = 5) -> str:
            \"\"\"지식베이스에서 관련 문서를 벡터 검색합니다.\"\"\"
            results = self.vector_store.similarity_search(query, k=top_k)
            return "\\n\\n".join([doc.page_content for doc in results])

        @tool
        def graph_query(cypher: str) -> str:
            \"\"\"Neo4j 그래프 데이터베이스에 Cypher 쿼리를 실행합니다.\"\"\"
            if self.graph_store:
                return self.graph_store.query(cypher)
            return "Graph store not configured"

        return [vector_search, graph_query]

    def get_system_prompt_addition(self) -> str:
        \"\"\"시스템 프롬프트에 추가할 내용\"\"\"
        return \"\"\"
RAG 도구 사용 지침:
1. 사용자 질문에 답하기 전에 항상 vector_search로 관련 문서를 검색하세요.
2. 복잡한 관계 쿼리는 graph_query를 사용하세요.
3. 검색 결과가 없으면 "지식베이스에서 관련 정보를 찾을 수 없습니다"라고 답하세요.
\"\"\"


# 미들웨어 사용
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="claude-3-5-sonnet",
    middleware=[
        RAGMiddleware(vector_store=my_vector_store),
        TodoListMiddleware(),
        FilesystemMiddleware(),
    ]
)
```
""")


# =============================================================================
# 4. SubAgent 패턴 활용
# =============================================================================

def example_subagent_pattern():
    """
    SubAgent 패턴 활용 예제

    SubAgent는 복잡한 작업을 분리하여 처리하는 패턴입니다.
    Context 격리로 메인 에이전트의 컨텍스트를 깨끗하게 유지합니다.
    """
    print("\n" + "=" * 60)
    print("4. SubAgent 패턴 활용 예제")
    print("=" * 60)

    print("""
SubAgent 패턴:

```python
from deepagents import create_deep_agent
from deepagents.middleware import SubAgentMiddleware

# SubAgent 정의
subagents = {
    "researcher": {
        "description": "웹에서 정보를 조사하는 전문가",
        "instructions": \"\"\"
            당신은 리서치 전문가입니다.
            웹 검색을 통해 최신 정보를 수집하고 요약합니다.
        \"\"\",
        "model": "gpt-4o-mini",  # 가벼운 모델 사용
    },
    "coder": {
        "description": "코드 작성 및 분석 전문가",
        "instructions": \"\"\"
            당신은 소프트웨어 개발자입니다.
            깔끔하고 효율적인 코드를 작성합니다.
        \"\"\",
        "model": "claude-3-5-sonnet",
    },
    "reviewer": {
        "description": "코드 리뷰 전문가",
        "instructions": \"\"\"
            당신은 시니어 코드 리뷰어입니다.
            코드의 품질, 보안, 성능을 검토합니다.
        \"\"\",
        "model": "claude-3-5-sonnet",
    }
}

# SubAgentMiddleware 설정
subagent_middleware = SubAgentMiddleware(
    subagents=subagents,
    default_model="claude-3-5-sonnet",
)

# 메인 에이전트 생성
agent = create_deep_agent(
    model="claude-3-5-sonnet",
    middleware=[subagent_middleware],
    system_prompt=\"\"\"
당신은 프로젝트 매니저입니다.
복잡한 작업은 적절한 SubAgent에게 위임하세요:
- researcher: 조사 작업
- coder: 코드 작성
- reviewer: 코드 리뷰

task 도구를 사용하여 SubAgent를 호출합니다.
\"\"\"
)

# 사용 예시
# 에이전트가 task 도구를 호출하면 SubAgent가 실행됨
# {"tool": "task", "arguments": {"agent": "coder", "task": "HelloWorld C 프로그램 작성"}}
```

SubAgent의 장점:
1. Context 격리: SubAgent는 별도의 컨텍스트에서 실행
2. 전문화: 각 SubAgent는 특정 도메인에 특화
3. 비용 최적화: 간단한 작업에는 가벼운 모델 사용
4. 재사용성: SubAgent를 여러 메인 에이전트에서 공유
""")


# =============================================================================
# 5. 기존 WebUI Agent와 통합 방안
# =============================================================================

def example_webui_integration():
    """
    기존 WebUI Agent와 Deep Agents 통합 방안

    기존 WebUI Agent 시스템에 Deep Agents의 장점을 도입하는 방법입니다.
    """
    print("\n" + "=" * 60)
    print("5. 기존 WebUI Agent 통합 방안")
    print("=" * 60)

    print("""
통합 전략:

1. **점진적 마이그레이션**
   - 기존 WebUI Agent를 유지하면서 Deep Agents를 병행 사용
   - 새로운 기능은 Deep Agents로 구현
   - 기존 기능은 필요시 점진적으로 마이그레이션

2. **미들웨어 브릿지**
   - 기존 Tool을 Deep Agents 미들웨어로 래핑

```python
# 기존 WebUI Tool을 Deep Agents 미들웨어로 변환

from deepagents.middleware import AgentMiddleware
from langchain_core.tools import tool

class WebUIToolBridge(AgentMiddleware):
    \"\"\"기존 WebUI Tool을 Deep Agents로 브릿지\"\"\"

    def __init__(self, webui_tool_registry):
        self.registry = webui_tool_registry

    def get_tools(self):
        tools = []
        for webui_tool in self.registry.get_all():
            # WebUI Tool을 LangChain tool로 변환
            @tool(name=webui_tool.name, description=webui_tool.description)
            async def wrapped_tool(**kwargs):
                return await webui_tool.execute(kwargs, context=None)
            tools.append(wrapped_tool)
        return tools
```

3. **Orchestrator 확장**
   - AgentOrchestrator에 Deep Agent 지원 추가

```python
# app/api/agents/orchestrator.py 확장

class AgentOrchestrator:
    def __init__(self, ...):
        # 기존 코드
        self.agent_registry = get_agent_registry()

        # Deep Agents 지원 추가
        self.deep_agent = self._create_deep_agent()

    def _create_deep_agent(self):
        \"\"\"Deep Agent 인스턴스 생성\"\"\"
        from deepagents import create_deep_agent

        return create_deep_agent(
            model=self._get_nim_llm(),
            middleware=[
                RAGMiddleware(self.vector_store),
                SubAgentMiddleware(subagents={
                    "code": {...},
                    "research": {...},
                }),
            ]
        )

    async def execute(self, request, user_id):
        # 복잡한 작업은 Deep Agent로 라우팅
        if self._is_complex_task(request.task):
            return await self._execute_with_deep_agent(request)

        # 단순 작업은 기존 Agent 사용
        return await self._execute_with_webui_agent(request)
```

4. **API 엔드포인트 추가**

```python
# app/api/routers/agents.py

@router.post("/deep/execute")
async def execute_deep_agent(
    request: AgentRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    \"\"\"Deep Agent로 작업 실행\"\"\"
    return await orchestrator.execute_with_deep_agent(request)

@router.post("/deep/stream")
async def stream_deep_agent(request: AgentRequest):
    \"\"\"Deep Agent 스트리밍 실행\"\"\"
    async def generate():
        async for chunk in orchestrator.stream_deep_agent(request):
            yield f"data: {json.dumps(chunk)}\\n\\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```
""")


# =============================================================================
# 6. 실제 동작 예제 (Mock)
# =============================================================================

async def example_mock_execution():
    """
    Deep Agents Mock 실행 예제

    실제 LLM 없이 Deep Agents의 동작 흐름을 보여줍니다.
    """
    print("\n" + "=" * 60)
    print("6. Deep Agents 동작 흐름 (Mock)")
    print("=" * 60)

    print("""
Deep Agents 실행 흐름:

1. 사용자 요청: "HelloWorld C 프로그램을 작성하고 리뷰해주세요"

2. 메인 에이전트 분석:
   - 복잡한 작업으로 판단
   - SubAgent 활용 결정

3. TodoList 작성 (TodoListMiddleware):
   ```
   [write_todos]
   - [ ] C 코드 작성 (coder SubAgent에게 위임)
   - [ ] 코드 리뷰 (reviewer SubAgent에게 위임)
   - [ ] 최종 결과 정리
   ```

4. SubAgent 호출 - Coder:
   ```
   [task] agent="coder", task="HelloWorld C 프로그램 작성"

   Coder SubAgent 실행:
   - 별도 컨텍스트에서 실행
   - C 코드 생성
   - 결과 반환
   ```

5. SubAgent 호출 - Reviewer:
   ```
   [task] agent="reviewer", task="다음 코드 리뷰: ..."

   Reviewer SubAgent 실행:
   - 코드 품질 검토
   - 점수 및 피드백 반환
   ```

6. 최종 결과 합성:
   - Coder 결과 + Reviewer 피드백 통합
   - 사용자에게 최종 응답 반환

실행 결과:
""")

    # Mock 실행 결과
    print("""
============================================================
[메인 에이전트] 작업 시작: HelloWorld C 프로그램 작성 및 리뷰
============================================================

[TodoList] 작업 계획 수립:
  1. [ ] C 코드 작성
  2. [ ] 코드 리뷰
  3. [ ] 결과 정리

[SubAgent:Coder] 호출 중...
------------------------------------------------------------
## 코드 작성 완료

```c
#include <stdio.h>

int main(void) {
    printf("HelloWorld\\n");
    return 0;
}
```
------------------------------------------------------------

[TodoList] 업데이트:
  1. [x] C 코드 작성
  2. [ ] 코드 리뷰
  3. [ ] 결과 정리

[SubAgent:Reviewer] 호출 중...
------------------------------------------------------------
## 코드 리뷰 결과

- 정확성: 5/5
- 가독성: 5/5
- 효율성: 5/5
- 보안성: 5/5
- 유지보수성: 5/5

총점: 25/25 (우수)
------------------------------------------------------------

[TodoList] 업데이트:
  1. [x] C 코드 작성
  2. [x] 코드 리뷰
  3. [x] 결과 정리

============================================================
[메인 에이전트] 작업 완료
============================================================
""")


# =============================================================================
# 7. 실제 LLM 연동 예제
# =============================================================================

async def example_real_execution():
    """
    실제 LLM과 Deep Agents 연동 예제
    """
    print("\n" + "=" * 60)
    print("7. 실제 LLM 연동 (NVIDIA NIM)")
    print("=" * 60)

    if not DEEPAGENTS_AVAILABLE:
        print("[SKIP] deepagents 패키지가 설치되지 않았습니다.")
        return

    if not OPENAI_AVAILABLE:
        print("[SKIP] langchain-openai 패키지가 설치되지 않았습니다.")
        print("       pip install langchain-openai 를 실행하세요.")
        return

    try:
        # NVIDIA NIM LLM 설정
        nim_llm = ChatOpenAI(
            model="nvidia/llama-3.1-nemotron-nano-8b-v1",
            base_url="http://localhost:12800/v1",
            api_key="not-needed",
            temperature=0.7,
            max_tokens=2048,
        )

        # 간단한 테스트
        print("\n[테스트] NVIDIA NIM 연결 확인...")
        response = await nim_llm.ainvoke([
            HumanMessage(content="Hello, respond with 'OK' if you can hear me.")
        ])
        print(f"[성공] NIM 응답: {response.content[:100]}...")

        # Deep Agent 생성
        print("\n[생성] Deep Agent 생성 중...")

        # 간단한 도구 정의
        @tool
        def get_current_time() -> str:
            """현재 시간을 반환합니다."""
            from datetime import datetime
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Deep Agent 생성 (미들웨어 최소화)
        agent = create_deep_agent(
            model=nim_llm,
            tools=[get_current_time],
            system_prompt="당신은 도움이 되는 AI 어시스턴트입니다. 한국어로 응답하세요.",
        )

        print("[성공] Deep Agent 생성 완료")

        # 실행
        print("\n[실행] Deep Agent 테스트...")
        result = await agent.ainvoke({
            "messages": [HumanMessage(content="현재 시간이 몇 시인가요?")]
        })

        print(f"\n[결과] {result}")

    except Exception as e:
        print(f"\n[오류] {type(e).__name__}: {e}")
        print("\n[TIP] NVIDIA NIM 서버가 실행 중인지 확인하세요:")
        print("      http://localhost:12800/v1/chat/completions")


# =============================================================================
# 메인 실행
# =============================================================================

async def main():
    """메인 함수"""
    print("""
+==============================================================+
|           Deep Agents 통합 샘플                              |
|                                                              |
|  이 샘플은 LangChain Deep Agents를 HybridRAG KMS에           |
|  통합하는 방법을 보여줍니다.                                 |
|                                                              |
|  주요 내용:                                                  |
|  1. 기본 Deep Agent 생성                                     |
|  2. NVIDIA NIM LLM 통합                                      |
|  3. 커스텀 미들웨어 작성                                     |
|  4. SubAgent 패턴 활용                                       |
|  5. 기존 WebUI Agent 통합                                    |
|  6. Mock 실행 예제                                           |
|  7. 실제 LLM 연동 (선택)                                     |
+==============================================================+
    """)

    # 예제 실행
    example_basic_deep_agent()
    example_nvidia_nim_integration()
    example_custom_middleware()
    example_subagent_pattern()
    example_webui_integration()
    await example_mock_execution()

    # 실제 LLM 연동 (옵션)
    if len(sys.argv) > 1 and sys.argv[1] == "--with-llm":
        await example_real_execution()
    else:
        print("\n" + "=" * 60)
        print("[INFO] 실제 LLM 연동 테스트를 실행하려면:")
        print("       python samples/deep_agents_sample.py --with-llm")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
