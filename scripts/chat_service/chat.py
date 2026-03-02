#!/usr/bin/env python3
"""
OpenFrame CPT/DPO 학습 LLM 채팅 인터페이스

Usage:
    python3 scripts/chat_service/chat.py
    python3 scripts/chat_service/chat.py --model dpo_72b
    python3 scripts/chat_service/chat.py --url http://localhost:8800/v1
"""
import argparse
import sys
import json
import signal
from openai import OpenAI

# 기본 설정
DEFAULT_URL = "http://localhost:8800/v1"
DEFAULT_MODEL = "openframe-cpt-72b"
SYSTEM_PROMPT = (
    "You are an expert on TmaxSoft OpenFrame products. "
    "Answer questions about OpenFrame, TJES, TACF, HiDB, OSC, OSI, Batch, "
    "error codes, commands (tjesmgr, tacfmgr, etc.), and configuration. "
    "Respond in the same language as the user's question. "
    "한국어 질문에는 한국어로, 日本語の質問には日本語で답변하세요."
)


def create_client(base_url: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key="not-needed")


def list_models(client: OpenAI) -> list:
    """사용 가능한 모델/어댑터 목록"""
    try:
        models = client.models.list()
        return [m.id for m in models.data]
    except Exception as e:
        print(f"모델 목록 조회 실패: {e}")
        return []


def chat_stream(client: OpenAI, model: str, messages: list) -> str:
    """스트리밍 채팅 응답"""
    full_response = ""
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                print(token, end="", flush=True)
                full_response += token
        print()  # 줄바꿈
    except Exception as e:
        print(f"\n오류: {e}")
    return full_response


def print_help():
    print(
        """
명령어:
  /models    - 사용 가능한 모델(어댑터) 목록
  /model X   - 모델 전환 (예: /model dpo_72b)
  /system X  - 시스템 프롬프트 변경
  /clear     - 대화 기록 초기화
  /history   - 대화 기록 보기
  /help      - 도움말
  /quit      - 종료
"""
    )


def main():
    parser = argparse.ArgumentParser(description="OpenFrame LLM Chat")
    parser.add_argument("--url", default=DEFAULT_URL, help="vLLM server URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model/adapter name")
    parser.add_argument("--system", default=SYSTEM_PROMPT, help="System prompt")
    args = parser.parse_args()

    client = create_client(args.url)
    model = args.model
    system_prompt = args.system
    messages = [{"role": "system", "content": system_prompt}]

    # Ctrl+C 처리
    signal.signal(signal.SIGINT, lambda s, f: (print("\n종료합니다."), sys.exit(0)))

    # 서버 연결 확인
    print("=" * 50)
    print(" OpenFrame 학습 LLM 채팅")
    print("=" * 50)
    print(f"Server : {args.url}")

    available = list_models(client)
    if available:
        print(f"Models : {', '.join(available)}")
        # 요청 모델이 없으면 base model 사용
        if model not in available:
            if available:
                model = available[0]
                print(f"→ '{args.model}' 없음, '{model}' 사용")
    else:
        print("서버 연결 실패. 서버가 실행 중인지 확인하세요.")
        print(f"  docker logs vllm-chat-cpt")
        sys.exit(1)

    print(f"Active : {model}")
    print(f"Type '/help' for commands, '/quit' to exit")
    print("-" * 50)

    while True:
        try:
            user_input = input("\nYou> ").strip()
        except EOFError:
            break

        if not user_input:
            continue

        # 명령어 처리
        if user_input.startswith("/"):
            cmd = user_input.split(maxsplit=1)
            cmd_name = cmd[0].lower()

            if cmd_name in ("/quit", "/exit", "/q"):
                print("종료합니다.")
                break
            elif cmd_name == "/help":
                print_help()
            elif cmd_name == "/models":
                models = list_models(client)
                print(f"사용 가능: {', '.join(models) if models else '없음'}")
            elif cmd_name == "/model":
                if len(cmd) > 1:
                    model = cmd[1]
                    print(f"모델 전환: {model}")
                else:
                    print(f"현재 모델: {model}")
            elif cmd_name == "/system":
                if len(cmd) > 1:
                    system_prompt = cmd[1]
                    messages = [{"role": "system", "content": system_prompt}]
                    print("시스템 프롬프트 변경 및 대화 초기화됨")
                else:
                    print(f"현재: {system_prompt[:80]}...")
            elif cmd_name == "/clear":
                messages = [{"role": "system", "content": system_prompt}]
                print("대화 기록 초기화됨")
            elif cmd_name == "/history":
                for msg in messages[1:]:  # system 제외
                    role = "You" if msg["role"] == "user" else "AI"
                    content = msg["content"][:100]
                    print(f"  [{role}] {content}...")
                if len(messages) <= 1:
                    print("  (대화 기록 없음)")
            else:
                print(f"알 수 없는 명령어: {cmd_name}. /help 참조")
            continue

        # 채팅 메시지 추가
        messages.append({"role": "user", "content": user_input})

        # 스트리밍 응답
        print(f"\n[{model}]> ", end="", flush=True)
        response = chat_stream(client, model, messages)

        if response:
            messages.append({"role": "assistant", "content": response})

        # 컨텍스트 윈도우 관리 (최근 20턴 유지)
        if len(messages) > 41:  # system + 20 pairs
            messages = [messages[0]] + messages[-40:]


if __name__ == "__main__":
    main()
