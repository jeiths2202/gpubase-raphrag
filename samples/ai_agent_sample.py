#!/usr/bin/env python3
"""
AI Agent 샘플 코드
==================

이 샘플은 Python에서 AI Agent를 생성하고 호출하는 방법을 보여줍니다.
3개의 Agent(Orchestra, Developer, Reviewer)를 사용하여
"HelloWorld"를 출력하는 C 소스코드를 생성하고 리뷰합니다.

실행 방법:
    python samples/ai_agent_sample.py

필요한 패키지:
    pip install openai httpx

작성자: AI Agent Sample
"""

import json
import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod


# =============================================================================
# 1. 기본 설정 및 상수 정의
# =============================================================================

# LLM API 엔드포인트 설정
# - 로컬 NVIDIA NIM 서버 또는 OpenAI API를 사용할 수 있습니다
LLM_API_URL = "http://localhost:12800/v1/chat/completions"  # Nemotron Nano
LLM_MODEL = "nvidia/llama-3.1-nemotron-nano-8b-v1"

# API 타임아웃 설정 (초)
API_TIMEOUT = 120.0


# =============================================================================
# 2. 에이전트 역할(Role) 정의
# =============================================================================

class AgentRole(Enum):
    """
    에이전트 역할 열거형

    각 에이전트는 고유한 역할을 가지며, 이 역할에 따라
    시스템 프롬프트와 행동 방식이 결정됩니다.
    """
    ORCHESTRA = "orchestra"      # 오케스트라: 전체 작업 흐름을 조율
    DEVELOPER = "developer"      # 개발자: 코드 작성 담당
    REVIEWER = "reviewer"        # 리뷰어: 코드 검토 및 피드백


# =============================================================================
# 3. 메시지 및 결과 데이터 클래스
# =============================================================================

@dataclass
class Message:
    """
    LLM과 주고받는 메시지를 표현하는 데이터 클래스

    Attributes:
        role: 메시지 발신자 역할 ("system", "user", "assistant")
        content: 메시지 내용
    """
    role: str       # "system", "user", "assistant" 중 하나
    content: str    # 실제 메시지 내용

    def to_dict(self) -> Dict[str, str]:
        """메시지를 딕셔너리로 변환 (API 호출용)"""
        return {"role": self.role, "content": self.content}


@dataclass
class AgentResult:
    """
    에이전트 실행 결과를 담는 데이터 클래스

    Attributes:
        success: 실행 성공 여부
        output: 에이전트 출력 결과
        error: 에러 메시지 (실패 시)
        metadata: 추가 메타데이터 (토큰 사용량 등)
    """
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# 4. LLM 클라이언트 클래스
# =============================================================================

class LLMClient:
    """
    LLM API와 통신하는 클라이언트 클래스

    이 클래스는 HTTP 요청을 통해 LLM에 프롬프트를 전송하고
    응답을 받아오는 역할을 합니다.

    사용 예시:
        client = LLMClient()
        response = client.chat([
            Message("system", "당신은 도움이 되는 AI입니다."),
            Message("user", "안녕하세요!")
        ])
    """

    def __init__(
        self,
        api_url: str = LLM_API_URL,
        model: str = LLM_MODEL,
        timeout: float = API_TIMEOUT
    ):
        """
        LLM 클라이언트 초기화

        Args:
            api_url: LLM API 엔드포인트 URL
            model: 사용할 모델 이름
            timeout: API 요청 타임아웃 (초)
        """
        self.api_url = api_url
        self.model = model
        self.timeout = timeout

        # HTTP 클라이언트 생성 (연결 재사용을 위해 세션 유지)
        self.http_client = httpx.Client(timeout=timeout)

    def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """
        LLM에 채팅 메시지를 전송하고 응답을 받습니다.

        Args:
            messages: 대화 메시지 리스트
            temperature: 생성 다양성 (0.0~1.0, 낮을수록 결정적)
            max_tokens: 최대 생성 토큰 수

        Returns:
            LLM의 응답 텍스트

        Raises:
            Exception: API 호출 실패 시
        """
        # 요청 페이로드 구성
        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            # POST 요청 전송
            response = self.http_client.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()

            # 응답 파싱
            result = response.json()

            # OpenAI 형식의 응답에서 텍스트 추출
            return result["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            raise Exception(f"LLM API 오류: HTTP {e.response.status_code}")
        except Exception as e:
            raise Exception(f"LLM 호출 실패: {str(e)}")

    def close(self):
        """HTTP 클라이언트 연결 종료"""
        self.http_client.close()


# =============================================================================
# 5. 기본 에이전트 추상 클래스
# =============================================================================

class BaseAgent(ABC):
    """
    모든 에이전트의 기본이 되는 추상 클래스

    이 클래스를 상속받아 각 역할에 맞는 에이전트를 구현합니다.
    Template Method 패턴을 사용하여 공통 로직을 제공합니다.

    상속 시 구현해야 할 메서드:
        - get_system_prompt(): 에이전트의 시스템 프롬프트 반환
        - process(): 실제 작업 수행 로직
    """

    def __init__(self, name: str, role: AgentRole, llm_client: LLMClient):
        """
        에이전트 초기화

        Args:
            name: 에이전트 이름 (로깅/디버깅용)
            role: 에이전트 역할
            llm_client: LLM 클라이언트 인스턴스
        """
        self.name = name
        self.role = role
        self.llm_client = llm_client

        # 대화 히스토리 저장 (컨텍스트 유지용)
        self.conversation_history: List[Message] = []

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        에이전트의 시스템 프롬프트를 반환합니다.

        시스템 프롬프트는 에이전트의 역할, 행동 방식,
        제약 조건 등을 정의합니다.

        Returns:
            시스템 프롬프트 문자열
        """
        pass

    @abstractmethod
    def process(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        주어진 작업을 처리합니다.

        Args:
            task: 수행할 작업 설명
            context: 추가 컨텍스트 정보 (이전 에이전트 결과 등)

        Returns:
            작업 수행 결과
        """
        pass

    def _call_llm(self, user_message: str) -> str:
        """
        LLM을 호출하는 내부 헬퍼 메서드

        시스템 프롬프트와 대화 히스토리를 포함하여 LLM을 호출합니다.

        Args:
            user_message: 사용자 메시지

        Returns:
            LLM 응답 텍스트
        """
        # 메시지 구성
        messages = [
            Message("system", self.get_system_prompt()),
            *self.conversation_history,
            Message("user", user_message)
        ]

        # LLM 호출
        response = self.llm_client.chat(messages)

        # 대화 히스토리 업데이트
        self.conversation_history.append(Message("user", user_message))
        self.conversation_history.append(Message("assistant", response))

        return response

    def reset_history(self):
        """대화 히스토리 초기화"""
        self.conversation_history = []


# =============================================================================
# 6. 오케스트라 에이전트 (Orchestra Agent)
# =============================================================================

class OrchestraAgent(BaseAgent):
    """
    오케스트라 에이전트

    전체 작업 흐름을 조율하고 다른 에이전트들에게
    작업을 분배하는 역할을 합니다.

    주요 기능:
        - 작업 분석 및 계획 수립
        - 하위 에이전트 호출 순서 결정
        - 최종 결과 취합 및 보고
    """

    def __init__(self, llm_client: LLMClient):
        super().__init__(
            name="OrchestraAgent",
            role=AgentRole.ORCHESTRA,
            llm_client=llm_client
        )

    def get_system_prompt(self) -> str:
        """오케스트라 에이전트의 시스템 프롬프트"""
        return """당신은 소프트웨어 개발 프로젝트의 오케스트라(조율자) 에이전트입니다.

역할:
- 사용자의 요구사항을 분석하고 작업 계획을 수립합니다.
- Developer 에이전트와 Reviewer 에이전트에게 작업을 할당합니다.
- 전체 프로세스를 조율하고 최종 결과를 보고합니다.

지침:
1. 요구사항을 명확하게 파악합니다.
2. 개발자 에이전트에게 전달할 구체적인 스펙을 작성합니다.
3. 리뷰어 에이전트의 피드백을 반영하여 품질을 보장합니다.
4. 모든 단계의 진행 상황을 명확하게 보고합니다.

응답 형식:
- 한국어로 응답합니다.
- 각 단계를 명확히 구분하여 설명합니다."""

    def process(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        작업을 분석하고 계획을 수립합니다.

        Args:
            task: 사용자 요구사항
            context: 추가 컨텍스트

        Returns:
            작업 계획 및 분석 결과
        """
        try:
            # 작업 분석 요청
            prompt = f"""다음 요구사항을 분석하고 작업 계획을 수립해주세요:

요구사항: {task}

다음 형식으로 응답해주세요:
1. 요구사항 분석
2. 개발자 에이전트에게 전달할 상세 스펙
3. 리뷰어 에이전트가 확인해야 할 항목
4. 예상 작업 흐름"""

            response = self._call_llm(prompt)

            return AgentResult(
                success=True,
                output=response,
                metadata={"agent": self.name, "role": self.role.value}
            )

        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e),
                metadata={"agent": self.name}
            )

    def summarize_results(
        self,
        dev_result: AgentResult,
        review_result: AgentResult
    ) -> AgentResult:
        """
        개발 및 리뷰 결과를 종합하여 최종 보고서를 생성합니다.

        Args:
            dev_result: 개발자 에이전트의 결과
            review_result: 리뷰어 에이전트의 결과

        Returns:
            최종 종합 보고서
        """
        try:
            prompt = f"""다음 개발 및 리뷰 결과를 종합하여 최종 보고서를 작성해주세요:

=== 개발 결과 ===
{dev_result.output}

=== 리뷰 결과 ===
{review_result.output}

다음 형식으로 최종 보고서를 작성해주세요:
1. 프로젝트 요약
2. 생성된 코드 (최종 버전)
3. 코드 품질 평가
4. 개선 권장사항 (있는 경우)
5. 결론"""

            response = self._call_llm(prompt)

            return AgentResult(
                success=True,
                output=response,
                metadata={"agent": self.name, "phase": "summary"}
            )

        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e)
            )


# =============================================================================
# 7. 개발자 에이전트 (Developer Agent)
# =============================================================================

class DeveloperAgent(BaseAgent):
    """
    개발자 에이전트

    코드 작성을 담당하는 에이전트입니다.
    주어진 스펙에 따라 코드를 생성합니다.

    주요 기능:
        - 요구사항에 맞는 코드 작성
        - 코드 주석 및 문서화
        - 리뷰 피드백 반영
    """

    def __init__(self, llm_client: LLMClient):
        super().__init__(
            name="DeveloperAgent",
            role=AgentRole.DEVELOPER,
            llm_client=llm_client
        )

    def get_system_prompt(self) -> str:
        """개발자 에이전트의 시스템 프롬프트"""
        return """당신은 숙련된 소프트웨어 개발자 에이전트입니다.

역할:
- 주어진 요구사항에 맞는 코드를 작성합니다.
- 깔끔하고 읽기 쉬운 코드를 작성합니다.
- 적절한 주석을 포함합니다.

코딩 규칙:
1. 코드는 항상 ```언어명 ... ``` 형식의 코드 블록으로 감쌉니다.
2. 변수명과 함수명은 명확하게 작성합니다.
3. 에러 처리를 고려합니다.
4. 코드 설명을 한국어로 제공합니다.

응답 형식:
- 먼저 코드의 설명을 제공합니다.
- 그 다음 코드를 작성합니다.
- 마지막으로 사용 방법을 설명합니다."""

    def process(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        요구사항에 맞는 코드를 작성합니다.

        Args:
            task: 코드 작성 요구사항
            context: 추가 컨텍스트 (오케스트라 에이전트의 스펙 등)

        Returns:
            생성된 코드와 설명
        """
        try:
            # 컨텍스트가 있으면 포함
            context_str = ""
            if context and context.get("spec"):
                context_str = f"\n\n추가 스펙:\n{context['spec']}"

            prompt = f"""다음 요구사항에 맞는 코드를 작성해주세요:

요구사항: {task}{context_str}

코드를 작성하고, 각 부분에 대한 설명을 포함해주세요."""

            response = self._call_llm(prompt)

            return AgentResult(
                success=True,
                output=response,
                metadata={"agent": self.name, "role": self.role.value}
            )

        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e),
                metadata={"agent": self.name}
            )

    def apply_feedback(self, original_code: str, feedback: str) -> AgentResult:
        """
        리뷰 피드백을 반영하여 코드를 수정합니다.

        Args:
            original_code: 원본 코드
            feedback: 리뷰어의 피드백

        Returns:
            수정된 코드
        """
        try:
            prompt = f"""다음 코드에 리뷰 피드백을 반영하여 수정해주세요:

=== 원본 코드 ===
{original_code}

=== 리뷰 피드백 ===
{feedback}

피드백을 반영하여 개선된 코드를 작성해주세요."""

            response = self._call_llm(prompt)

            return AgentResult(
                success=True,
                output=response,
                metadata={"agent": self.name, "phase": "revision"}
            )

        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e)
            )


# =============================================================================
# 8. 리뷰어 에이전트 (Reviewer Agent)
# =============================================================================

class ReviewerAgent(BaseAgent):
    """
    리뷰어 에이전트

    코드 리뷰를 담당하는 에이전트입니다.
    코드의 품질, 보안, 성능 등을 검토합니다.

    주요 기능:
        - 코드 품질 검토
        - 버그 및 취약점 탐지
        - 개선 사항 제안
        - 코딩 컨벤션 준수 여부 확인
    """

    def __init__(self, llm_client: LLMClient):
        super().__init__(
            name="ReviewerAgent",
            role=AgentRole.REVIEWER,
            llm_client=llm_client
        )

    def get_system_prompt(self) -> str:
        """리뷰어 에이전트의 시스템 프롬프트"""
        return """당신은 꼼꼼한 코드 리뷰어 에이전트입니다.

역할:
- 제출된 코드를 철저히 검토합니다.
- 버그, 보안 취약점, 성능 이슈를 찾아냅니다.
- 코드 품질 향상을 위한 피드백을 제공합니다.

리뷰 기준:
1. 정확성: 코드가 요구사항을 충족하는가?
2. 가독성: 코드가 이해하기 쉬운가?
3. 효율성: 불필요한 연산이나 메모리 사용이 없는가?
4. 보안성: 보안 취약점이 없는가?
5. 유지보수성: 코드 수정이 용이한가?

응답 형식:
- 한국어로 리뷰 결과를 작성합니다.
- 각 항목별로 점수(1-5)와 피드백을 제공합니다.
- 개선이 필요한 부분은 구체적인 수정 방안을 제시합니다."""

    def process(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        코드를 리뷰하고 피드백을 제공합니다.

        Args:
            task: 리뷰할 코드 또는 리뷰 요청
            context: 추가 컨텍스트 (원본 요구사항 등)

        Returns:
            리뷰 결과 및 피드백
        """
        try:
            # 컨텍스트에서 원본 요구사항 추출
            requirements = ""
            if context and context.get("requirements"):
                requirements = f"\n\n원본 요구사항:\n{context['requirements']}"

            prompt = f"""다음 코드를 리뷰해주세요:

{task}{requirements}

다음 항목을 기준으로 리뷰해주세요:
1. 정확성 (요구사항 충족 여부)
2. 가독성 (코드 스타일, 네이밍)
3. 효율성 (성능, 리소스 사용)
4. 보안성 (취약점 여부)
5. 유지보수성 (확장성, 수정 용이성)

각 항목별로 점수(1-5)와 상세 피드백을 제공해주세요."""

            response = self._call_llm(prompt)

            return AgentResult(
                success=True,
                output=response,
                metadata={"agent": self.name, "role": self.role.value}
            )

        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e),
                metadata={"agent": self.name}
            )


# =============================================================================
# 9. 에이전트 매니저 (Agent Manager)
# =============================================================================

class AgentManager:
    """
    에이전트 매니저

    여러 에이전트를 관리하고 작업 흐름을 조율합니다.
    Facade 패턴을 사용하여 복잡한 에이전트 상호작용을
    단순한 인터페이스로 제공합니다.

    사용 예시:
        manager = AgentManager()
        result = manager.execute_workflow("HelloWorld 출력 C 프로그램 작성")
        print(result)
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        에이전트 매니저 초기화

        Args:
            llm_client: LLM 클라이언트 (없으면 자동 생성)
        """
        # LLM 클라이언트 생성 또는 주입받기
        self.llm_client = llm_client or LLMClient()

        # 에이전트 인스턴스 생성
        self.orchestra = OrchestraAgent(self.llm_client)
        self.developer = DeveloperAgent(self.llm_client)
        self.reviewer = ReviewerAgent(self.llm_client)

        print("[AgentManager] 초기화 완료")
        print(f"  - Orchestra Agent: {self.orchestra.name}")
        print(f"  - Developer Agent: {self.developer.name}")
        print(f"  - Reviewer Agent: {self.reviewer.name}")

    def execute_workflow(self, user_request: str) -> str:
        """
        전체 워크플로우를 실행합니다.

        워크플로우 순서:
        1. Orchestra가 요구사항 분석 및 계획 수립
        2. Developer가 코드 작성
        3. Reviewer가 코드 리뷰
        4. Orchestra가 최종 결과 종합

        Args:
            user_request: 사용자의 요청사항

        Returns:
            최종 결과 보고서
        """
        print("\n" + "=" * 60)
        print("AI Agent 워크플로우 시작")
        print("=" * 60)
        print(f"요청: {user_request}")
        print("=" * 60 + "\n")

        # Step 1: 오케스트라 에이전트 - 요구사항 분석
        print("[Step 1] Orchestra Agent - 요구사항 분석 중...")
        print("-" * 40)

        orchestra_result = self.orchestra.process(user_request)

        if not orchestra_result.success:
            return f"오류: 요구사항 분석 실패 - {orchestra_result.error}"

        print(orchestra_result.output)
        print()

        # Step 2: 개발자 에이전트 - 코드 작성
        print("[Step 2] Developer Agent - 코드 작성 중...")
        print("-" * 40)

        dev_result = self.developer.process(
            task=user_request,
            context={"spec": orchestra_result.output}
        )

        if not dev_result.success:
            return f"오류: 코드 작성 실패 - {dev_result.error}"

        print(dev_result.output)
        print()

        # Step 3: 리뷰어 에이전트 - 코드 리뷰
        print("[Step 3] Reviewer Agent - 코드 리뷰 중...")
        print("-" * 40)

        review_result = self.reviewer.process(
            task=dev_result.output,
            context={"requirements": user_request}
        )

        if not review_result.success:
            return f"오류: 코드 리뷰 실패 - {review_result.error}"

        print(review_result.output)
        print()

        # Step 4: 오케스트라 에이전트 - 최종 결과 종합
        print("[Step 4] Orchestra Agent - 최종 결과 종합 중...")
        print("-" * 40)

        final_result = self.orchestra.summarize_results(dev_result, review_result)

        if not final_result.success:
            return f"오류: 결과 종합 실패 - {final_result.error}"

        print(final_result.output)

        print("\n" + "=" * 60)
        print("AI Agent 워크플로우 완료")
        print("=" * 60)

        return final_result.output

    def cleanup(self):
        """리소스 정리"""
        self.llm_client.close()
        print("[AgentManager] 리소스 정리 완료")


# =============================================================================
# 10. 메인 실행 코드
# =============================================================================

def main():
    """
    메인 함수

    HelloWorld를 출력하는 C 프로그램을 생성하고 리뷰하는
    전체 워크플로우를 실행합니다.
    """
    print("""
╔══════════════════════════════════════════════════════════════╗
║           AI Agent 샘플 - HelloWorld C 프로그램              ║
║                                                              ║
║  이 샘플은 3개의 AI 에이전트를 사용하여:                     ║
║  1. Orchestra: 작업 계획 수립                                ║
║  2. Developer: C 코드 작성                                   ║
║  3. Reviewer: 코드 리뷰                                      ║
║                                                              ║
║  "HelloWorld"를 출력하는 C 프로그램을 생성합니다.           ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # 사용자 요청 정의
    user_request = """
    "HelloWorld" 메시지를 출력하는 C 프로그램을 작성해주세요.

    요구사항:
    1. 표준 출력으로 "HelloWorld"를 출력합니다.
    2. 적절한 주석을 포함합니다.
    3. main 함수의 반환값은 0입니다.
    4. 코드는 ANSI C 표준을 준수합니다.
    """

    # 에이전트 매니저 생성 및 워크플로우 실행
    manager = None
    try:
        manager = AgentManager()
        result = manager.execute_workflow(user_request)

        # 최종 결과 출력
        print("\n" + "=" * 60)
        print("최종 결과")
        print("=" * 60)
        print(result)

    except Exception as e:
        print(f"\n오류 발생: {str(e)}")
        print("\n[TIP] LLM 서버가 실행 중인지 확인하세요.")
        print(f"      현재 설정된 URL: {LLM_API_URL}")

    finally:
        # 리소스 정리
        if manager:
            manager.cleanup()


# =============================================================================
# 11. Mock LLM 클라이언트 (테스트용)
# =============================================================================

class MockLLMClient(LLMClient):
    """
    테스트용 Mock LLM 클라이언트

    실제 LLM API 없이 에이전트 동작을 테스트할 수 있습니다.
    """

    def __init__(self):
        # 부모 클래스 초기화는 건너뜀
        self.call_count = 0

    def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """Mock 응답 반환"""
        self.call_count += 1

        # 시스템 프롬프트에서 에이전트 역할 파악
        system_msg = messages[0].content if messages else ""
        user_msg = messages[-1].content if messages else ""

        if "오케스트라" in system_msg or "조율자" in system_msg:
            if "종합" in user_msg or "개발 결과" in user_msg:
                return self._mock_summary_response()
            return self._mock_orchestra_response()
        elif "개발자" in system_msg:
            return self._mock_developer_response()
        elif "리뷰어" in system_msg:
            return self._mock_reviewer_response()

        return "Mock 응답입니다."

    def _mock_orchestra_response(self) -> str:
        return """## 요구사항 분석

1. **목표**: "HelloWorld" 메시지를 출력하는 C 프로그램 작성
2. **세부 요구사항**:
   - 표준 출력(stdout)으로 "HelloWorld" 출력
   - ANSI C 표준 준수
   - 적절한 주석 포함
   - main 함수 반환값 0

## 개발자 에이전트 스펙

- stdio.h 헤더 사용
- printf() 함수로 출력
- 한글 주석으로 코드 설명

## 리뷰어 확인 항목

- 컴파일 가능 여부
- 출력 결과 정확성
- 코딩 컨벤션 준수"""

    def _mock_developer_response(self) -> str:
        return """## 코드 설명

"HelloWorld"를 출력하는 간단한 C 프로그램입니다.
표준 입출력 헤더를 포함하고, printf 함수를 사용합니다.

## 코드

```c
/*
 * HelloWorld 프로그램
 *
 * 설명: 표준 출력으로 "HelloWorld" 메시지를 출력합니다.
 * 작성자: Developer Agent
 * 표준: ANSI C
 */

#include <stdio.h>

/*
 * 메인 함수
 * 프로그램의 진입점입니다.
 */
int main(void) {
    /* "HelloWorld" 메시지 출력 */
    printf("HelloWorld\\n");

    /* 정상 종료 */
    return 0;
}
```

## 컴파일 및 실행 방법

```bash
# 컴파일
gcc -o helloworld helloworld.c

# 실행
./helloworld
```

예상 출력:
```
HelloWorld
```"""

    def _mock_reviewer_response(self) -> str:
        return """## 코드 리뷰 결과

### 1. 정확성 (5/5)
- 요구사항을 완벽히 충족합니다.
- "HelloWorld" 메시지가 정확히 출력됩니다.

### 2. 가독성 (5/5)
- 코드가 간결하고 이해하기 쉽습니다.
- 주석이 적절히 포함되어 있습니다.
- 함수명과 구조가 명확합니다.

### 3. 효율성 (5/5)
- 단순한 프로그램으로 효율성 이슈 없음
- 불필요한 연산이나 메모리 사용 없음

### 4. 보안성 (5/5)
- 보안 취약점 없음
- 사용자 입력을 받지 않아 안전

### 5. 유지보수성 (5/5)
- 코드 구조가 표준적임
- 수정 및 확장이 용이함

### 총평
- **총점: 25/25 (우수)**
- 깔끔하고 표준적인 HelloWorld 프로그램입니다.
- 개선 사항 없음"""

    def _mock_summary_response(self) -> str:
        return """## 최종 보고서

### 1. 프로젝트 요약
"HelloWorld"를 출력하는 C 프로그램이 성공적으로 작성되었습니다.

### 2. 최종 코드

```c
#include <stdio.h>

int main(void) {
    printf("HelloWorld\\n");
    return 0;
}
```

### 3. 코드 품질 평가
- 총점: 25/25 (우수)
- 모든 요구사항 충족
- 코딩 표준 준수

### 4. 결론
프로젝트가 성공적으로 완료되었습니다."""

    def close(self):
        """Mock은 정리할 리소스 없음"""
        pass


def test_with_mock():
    """
    Mock LLM을 사용한 테스트

    실제 LLM 서버 없이 에이전트 동작을 확인합니다.
    """
    print("\n[테스트 모드] Mock LLM 사용")
    print("-" * 40)

    # Mock 클라이언트로 매니저 생성
    mock_client = MockLLMClient()
    manager = AgentManager(llm_client=mock_client)

    # 워크플로우 실행
    result = manager.execute_workflow("HelloWorld C 프로그램 작성")

    print(f"\n[테스트 완료] LLM 호출 횟수: {mock_client.call_count}")

    manager.cleanup()


# =============================================================================
# 실행
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # 테스트 모드: Mock LLM 사용
        test_with_mock()
    else:
        # 실제 모드: 실제 LLM 서버 사용
        main()
