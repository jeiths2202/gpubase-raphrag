# Python AI Agent 개발 가이드

## 개요

이 문서는 Python에서 AI Agent를 생성하고 사용하는 방법을 상세히 설명합니다.
예제로 **Orchestra**, **Developer**, **Reviewer** 3개의 에이전트를 사용하여
"HelloWorld"를 출력하는 C 프로그램을 생성하고 리뷰하는 시스템을 구현합니다.

---

## 목차

1. [AI Agent란?](#1-ai-agent란)
2. [아키텍처 설계](#2-아키텍처-설계)
3. [핵심 컴포넌트](#3-핵심-컴포넌트)
4. [에이전트 구현](#4-에이전트-구현)
5. [워크플로우](#5-워크플로우)
6. [실행 방법](#6-실행-방법)
7. [확장 가이드](#7-확장-가이드)
8. [베스트 프랙티스](#8-베스트-프랙티스)

---

## 1. AI Agent란?

### 1.1 정의

AI Agent는 특정 목표를 달성하기 위해 **자율적으로 행동**하는 소프트웨어 엔티티입니다.
LLM(Large Language Model)을 기반으로 하여 자연어를 이해하고,
주어진 작업을 수행하며, 다른 에이전트나 시스템과 상호작용합니다.

### 1.2 주요 특성

| 특성 | 설명 |
|------|------|
| **자율성** | 사용자 개입 없이 독립적으로 작업 수행 |
| **반응성** | 환경 변화에 적절히 반응 |
| **목표 지향** | 명확한 목표를 향해 행동 |
| **사회성** | 다른 에이전트와 협력 가능 |

### 1.3 에이전트 vs 챗봇

```
┌─────────────────────────────────────────────────────────────┐
│                        챗봇 (Chatbot)                        │
├─────────────────────────────────────────────────────────────┤
│  • 단일 턴 대화 위주                                         │
│  • 질문-응답 형식                                            │
│  • 제한된 컨텍스트                                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      AI Agent                                │
├─────────────────────────────────────────────────────────────┤
│  • 복잡한 다단계 작업 수행                                   │
│  • 자율적 의사결정                                           │
│  • 도구 사용 및 외부 시스템 연동                             │
│  • 다른 에이전트와 협업                                      │
│  • 지속적인 컨텍스트 유지                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 아키텍처 설계

### 2.1 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                       Agent Manager                              │
│                    (Facade Pattern)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Orchestra   │  │  Developer   │  │   Reviewer   │          │
│  │    Agent     │  │    Agent     │  │    Agent     │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         └────────────┬────┴────────────────┘                   │
│                      │                                          │
│              ┌───────▼───────┐                                  │
│              │  Base Agent   │                                  │
│              │ (Template     │                                  │
│              │  Pattern)     │                                  │
│              └───────┬───────┘                                  │
│                      │                                          │
│              ┌───────▼───────┐                                  │
│              │  LLM Client   │                                  │
│              └───────┬───────┘                                  │
│                      │                                          │
└──────────────────────┼──────────────────────────────────────────┘
                       │
               ┌───────▼───────┐
               │   LLM API     │
               │ (OpenAI/NIM)  │
               └───────────────┘
```

### 2.2 사용된 디자인 패턴

| 패턴 | 적용 위치 | 목적 |
|------|-----------|------|
| **Template Method** | BaseAgent | 공통 로직 캡슐화, 확장 포인트 제공 |
| **Facade** | AgentManager | 복잡한 에이전트 상호작용 단순화 |
| **Strategy** | 각 Agent | 역할별 다른 행동 방식 |
| **Factory** | AgentManager | 에이전트 인스턴스 생성 관리 |

---

## 3. 핵심 컴포넌트

### 3.1 데이터 클래스

#### Message (메시지)

```python
@dataclass
class Message:
    """LLM과 주고받는 메시지"""
    role: str       # "system", "user", "assistant"
    content: str    # 메시지 내용

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}
```

**역할(role) 설명:**
- `system`: 에이전트의 행동 방식과 제약 조건 정의
- `user`: 사용자 또는 다른 에이전트의 요청
- `assistant`: LLM의 응답

#### AgentResult (실행 결과)

```python
@dataclass
class AgentResult:
    """에이전트 실행 결과"""
    success: bool                           # 성공 여부
    output: str                             # 출력 결과
    error: Optional[str] = None             # 에러 메시지
    metadata: Dict[str, Any] = field(default_factory=dict)  # 메타데이터
```

### 3.2 LLM 클라이언트

LLM API와 통신하는 클라이언트 클래스입니다.

```python
class LLMClient:
    def __init__(self, api_url: str, model: str, timeout: float):
        self.api_url = api_url
        self.model = model
        self.http_client = httpx.Client(timeout=timeout)

    def chat(self, messages: List[Message], temperature: float = 0.7) -> str:
        """LLM에 메시지 전송 후 응답 반환"""
        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": temperature
        }
        response = self.http_client.post(self.api_url, json=payload)
        return response.json()["choices"][0]["message"]["content"]
```

**주요 파라미터:**

| 파라미터 | 설명 | 권장값 |
|----------|------|--------|
| `temperature` | 응답의 다양성 (0.0~1.0) | 코드: 0.3, 대화: 0.7 |
| `max_tokens` | 최대 생성 토큰 수 | 2048~4096 |
| `timeout` | API 타임아웃 (초) | 60~120 |

---

## 4. 에이전트 구현

### 4.1 기본 에이전트 (BaseAgent)

모든 에이전트의 부모 클래스로, Template Method 패턴을 적용합니다.

```python
class BaseAgent(ABC):
    def __init__(self, name: str, role: AgentRole, llm_client: LLMClient):
        self.name = name
        self.role = role
        self.llm_client = llm_client
        self.conversation_history: List[Message] = []

    @abstractmethod
    def get_system_prompt(self) -> str:
        """시스템 프롬프트 반환 (하위 클래스에서 구현)"""
        pass

    @abstractmethod
    def process(self, task: str, context: Optional[Dict] = None) -> AgentResult:
        """작업 처리 (하위 클래스에서 구현)"""
        pass

    def _call_llm(self, user_message: str) -> str:
        """LLM 호출 (공통 로직)"""
        messages = [
            Message("system", self.get_system_prompt()),
            *self.conversation_history,
            Message("user", user_message)
        ]
        response = self.llm_client.chat(messages)

        # 대화 히스토리 업데이트
        self.conversation_history.append(Message("user", user_message))
        self.conversation_history.append(Message("assistant", response))

        return response
```

### 4.2 Orchestra Agent (오케스트라 에이전트)

전체 작업 흐름을 조율하는 에이전트입니다.

```python
class OrchestraAgent(BaseAgent):
    def get_system_prompt(self) -> str:
        return """당신은 소프트웨어 개발 프로젝트의 오케스트라(조율자) 에이전트입니다.

역할:
- 사용자의 요구사항을 분석하고 작업 계획을 수립합니다.
- Developer 에이전트와 Reviewer 에이전트에게 작업을 할당합니다.
- 전체 프로세스를 조율하고 최종 결과를 보고합니다.

지침:
1. 요구사항을 명확하게 파악합니다.
2. 개발자 에이전트에게 전달할 구체적인 스펙을 작성합니다.
3. 리뷰어 에이전트의 피드백을 반영하여 품질을 보장합니다."""

    def process(self, task: str, context: Optional[Dict] = None) -> AgentResult:
        prompt = f"다음 요구사항을 분석하고 작업 계획을 수립해주세요: {task}"
        response = self._call_llm(prompt)
        return AgentResult(success=True, output=response)
```

**주요 책임:**
- 요구사항 분석
- 작업 분배
- 결과 종합

### 4.3 Developer Agent (개발자 에이전트)

코드 작성을 담당하는 에이전트입니다.

```python
class DeveloperAgent(BaseAgent):
    def get_system_prompt(self) -> str:
        return """당신은 숙련된 소프트웨어 개발자 에이전트입니다.

역할:
- 주어진 요구사항에 맞는 코드를 작성합니다.
- 깔끔하고 읽기 쉬운 코드를 작성합니다.
- 적절한 주석을 포함합니다.

코딩 규칙:
1. 코드는 항상 ```언어명 ... ``` 형식의 코드 블록으로 감쌉니다.
2. 변수명과 함수명은 명확하게 작성합니다.
3. 에러 처리를 고려합니다."""

    def process(self, task: str, context: Optional[Dict] = None) -> AgentResult:
        spec = context.get("spec", "") if context else ""
        prompt = f"다음 요구사항에 맞는 코드를 작성해주세요:\n{task}\n\n스펙:\n{spec}"
        response = self._call_llm(prompt)
        return AgentResult(success=True, output=response)
```

**주요 책임:**
- 코드 생성
- 문서화
- 피드백 반영

### 4.4 Reviewer Agent (리뷰어 에이전트)

코드 리뷰를 담당하는 에이전트입니다.

```python
class ReviewerAgent(BaseAgent):
    def get_system_prompt(self) -> str:
        return """당신은 꼼꼼한 코드 리뷰어 에이전트입니다.

리뷰 기준:
1. 정확성: 코드가 요구사항을 충족하는가?
2. 가독성: 코드가 이해하기 쉬운가?
3. 효율성: 불필요한 연산이나 메모리 사용이 없는가?
4. 보안성: 보안 취약점이 없는가?
5. 유지보수성: 코드 수정이 용이한가?

응답 형식:
- 각 항목별로 점수(1-5)와 피드백을 제공합니다."""

    def process(self, task: str, context: Optional[Dict] = None) -> AgentResult:
        requirements = context.get("requirements", "") if context else ""
        prompt = f"다음 코드를 리뷰해주세요:\n{task}\n\n원본 요구사항:\n{requirements}"
        response = self._call_llm(prompt)
        return AgentResult(success=True, output=response)
```

**리뷰 기준:**

| 항목 | 점수 | 확인 사항 |
|------|------|-----------|
| 정확성 | 1-5 | 요구사항 충족 여부 |
| 가독성 | 1-5 | 코드 스타일, 네이밍 |
| 효율성 | 1-5 | 성능, 리소스 사용 |
| 보안성 | 1-5 | 취약점 여부 |
| 유지보수성 | 1-5 | 확장성, 수정 용이성 |

---

## 5. 워크플로우

### 5.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                    사용자 요청                               │
│         "HelloWorld 출력 C 프로그램 작성"                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Orchestra Agent - 요구사항 분석                     │
│                                                              │
│  • 요구사항 파악                                             │
│  • 작업 계획 수립                                            │
│  • Developer 에이전트 스펙 작성                              │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Developer Agent - 코드 작성                         │
│                                                              │
│  • Orchestra의 스펙 기반 코드 생성                           │
│  • 주석 및 문서화                                            │
│  • 컴파일/실행 방법 안내                                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Reviewer Agent - 코드 리뷰                          │
│                                                              │
│  • 코드 품질 검토                                            │
│  • 5가지 기준 평가                                           │
│  • 개선 사항 제안                                            │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: Orchestra Agent - 결과 종합                         │
│                                                              │
│  • 개발/리뷰 결과 통합                                       │
│  • 최종 보고서 작성                                          │
│  • 결론 및 권장사항                                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     최종 결과물                               │
│                                                              │
│  • HelloWorld C 프로그램                                     │
│  • 코드 리뷰 결과                                            │
│  • 품질 평가 보고서                                          │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Agent Manager 구현

```python
class AgentManager:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
        self.orchestra = OrchestraAgent(self.llm_client)
        self.developer = DeveloperAgent(self.llm_client)
        self.reviewer = ReviewerAgent(self.llm_client)

    def execute_workflow(self, user_request: str) -> str:
        # Step 1: 요구사항 분석
        orchestra_result = self.orchestra.process(user_request)

        # Step 2: 코드 작성
        dev_result = self.developer.process(
            task=user_request,
            context={"spec": orchestra_result.output}
        )

        # Step 3: 코드 리뷰
        review_result = self.reviewer.process(
            task=dev_result.output,
            context={"requirements": user_request}
        )

        # Step 4: 결과 종합
        final_result = self.orchestra.summarize_results(dev_result, review_result)

        return final_result.output
```

---

## 6. 실행 방법

### 6.1 필수 패키지 설치

```bash
pip install httpx
```

### 6.2 실제 LLM 서버로 실행

```bash
# LLM 서버가 localhost:12800에서 실행 중인 경우
python samples/ai_agent_sample.py
```

### 6.3 테스트 모드 (Mock LLM)

```bash
# 실제 LLM 없이 테스트
python samples/ai_agent_sample.py --test
```

### 6.4 예상 출력

```
╔══════════════════════════════════════════════════════════════╗
║           AI Agent 샘플 - HelloWorld C 프로그램              ║
╚══════════════════════════════════════════════════════════════╝

[Step 1] Orchestra Agent - 요구사항 분석 중...
------------------------------------------
## 요구사항 분석
1. 목표: "HelloWorld" 메시지 출력
...

[Step 2] Developer Agent - 코드 작성 중...
------------------------------------------
## 코드

```c
#include <stdio.h>

int main(void) {
    printf("HelloWorld\n");
    return 0;
}
```

[Step 3] Reviewer Agent - 코드 리뷰 중...
------------------------------------------
### 1. 정확성 (5/5)
- 요구사항을 완벽히 충족합니다.
...

[Step 4] Orchestra Agent - 최종 결과 종합 중...
------------------------------------------
## 최종 보고서
프로젝트가 성공적으로 완료되었습니다.
```

---

## 7. 확장 가이드

### 7.1 새로운 에이전트 추가

```python
class TesterAgent(BaseAgent):
    """테스트 에이전트 - 테스트 코드 작성"""

    def __init__(self, llm_client: LLMClient):
        super().__init__(
            name="TesterAgent",
            role=AgentRole.TESTER,  # 새 역할 추가 필요
            llm_client=llm_client
        )

    def get_system_prompt(self) -> str:
        return """당신은 테스트 전문가 에이전트입니다.

역할:
- 주어진 코드에 대한 테스트 케이스를 작성합니다.
- 유닛 테스트, 통합 테스트를 고려합니다.
- 엣지 케이스를 포함합니다."""

    def process(self, task: str, context: Optional[Dict] = None) -> AgentResult:
        prompt = f"다음 코드에 대한 테스트 케이스를 작성해주세요:\n{task}"
        response = self._call_llm(prompt)
        return AgentResult(success=True, output=response)
```

### 7.2 도구(Tool) 연동

```python
class DeveloperAgentWithTools(DeveloperAgent):
    """도구를 사용할 수 있는 개발자 에이전트"""

    def __init__(self, llm_client: LLMClient):
        super().__init__(llm_client)
        self.tools = {
            "compile": self._compile_code,
            "run": self._run_code,
            "lint": self._lint_code
        }

    def _compile_code(self, code: str, language: str) -> str:
        """코드 컴파일"""
        import subprocess
        # 실제 구현...
        pass

    def _run_code(self, executable: str) -> str:
        """코드 실행"""
        pass

    def _lint_code(self, code: str) -> str:
        """코드 린트 검사"""
        pass
```

### 7.3 에이전트 체이닝

```python
def advanced_workflow(manager: AgentManager, request: str):
    """고급 워크플로우 - 피드백 루프 포함"""

    # 1. 요구사항 분석
    plan = manager.orchestra.process(request)

    # 2. 코드 작성
    code = manager.developer.process(request, {"spec": plan.output})

    # 3. 리뷰 및 피드백 루프
    max_iterations = 3
    for i in range(max_iterations):
        review = manager.reviewer.process(code.output)

        # 점수가 충분히 높으면 종료
        if "25/25" in review.output or "우수" in review.output:
            break

        # 피드백 반영하여 코드 수정
        code = manager.developer.apply_feedback(code.output, review.output)

    # 4. 최종 결과
    return manager.orchestra.summarize_results(code, review)
```

---

## 8. 베스트 프랙티스

### 8.1 시스템 프롬프트 작성 팁

1. **명확한 역할 정의**
   ```
   당신은 [역할]입니다.
   ```

2. **구체적인 지침 제공**
   ```
   다음 규칙을 따르세요:
   1. ...
   2. ...
   ```

3. **출력 형식 지정**
   ```
   다음 형식으로 응답하세요:
   - ...
   - ...
   ```

4. **제약 조건 명시**
   ```
   주의사항:
   - 하지 말아야 할 것...
   - 반드시 해야 할 것...
   ```

### 8.2 에러 처리

```python
def safe_process(agent: BaseAgent, task: str) -> AgentResult:
    """안전한 에이전트 실행"""
    try:
        return agent.process(task)
    except httpx.TimeoutException:
        return AgentResult(
            success=False,
            output="",
            error="LLM 응답 시간 초과"
        )
    except httpx.HTTPStatusError as e:
        return AgentResult(
            success=False,
            output="",
            error=f"HTTP 오류: {e.response.status_code}"
        )
    except Exception as e:
        return AgentResult(
            success=False,
            output="",
            error=f"예상치 못한 오류: {str(e)}"
        )
```

### 8.3 로깅

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    def _call_llm(self, user_message: str) -> str:
        logger.info(f"[{self.name}] LLM 호출 시작")
        logger.debug(f"프롬프트: {user_message[:100]}...")

        response = self.llm_client.chat(messages)

        logger.info(f"[{self.name}] LLM 호출 완료")
        logger.debug(f"응답: {response[:100]}...")

        return response
```

### 8.4 테스트

```python
import pytest

def test_orchestra_agent():
    """오케스트라 에이전트 테스트"""
    mock_client = MockLLMClient()
    agent = OrchestraAgent(mock_client)

    result = agent.process("HelloWorld 프로그램 작성")

    assert result.success
    assert "요구사항" in result.output or "분석" in result.output

def test_developer_agent():
    """개발자 에이전트 테스트"""
    mock_client = MockLLMClient()
    agent = DeveloperAgent(mock_client)

    result = agent.process("C로 HelloWorld 작성")

    assert result.success
    assert "```c" in result.output or "#include" in result.output
```

---

## 부록

### A. 용어 정리

| 용어 | 설명 |
|------|------|
| **Agent** | 자율적으로 작업을 수행하는 소프트웨어 엔티티 |
| **LLM** | Large Language Model, 대규모 언어 모델 |
| **System Prompt** | 에이전트의 역할과 행동을 정의하는 프롬프트 |
| **Context** | 에이전트 간 전달되는 추가 정보 |
| **Workflow** | 에이전트들의 작업 수행 순서 |

### B. 참고 자료

- [OpenAI API 문서](https://platform.openai.com/docs)
- [LangChain Agent 가이드](https://python.langchain.com/docs/modules/agents/)
- [NVIDIA NIM 문서](https://developer.nvidia.com/nim)

### C. 파일 구조

```
samples/
├── ai_agent_sample.py     # 메인 샘플 코드
└── AI_AGENT_GUIDE.md      # 이 문서
```

---

*이 문서는 AI Agent 개발의 기초를 다루며, 실제 프로덕션 환경에서는 추가적인 보안, 성능 최적화, 에러 처리가 필요할 수 있습니다.*
