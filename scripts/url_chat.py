#!/usr/bin/env python3
"""
URL Chat CLI - Interactive RAG conversation with URL context

Usage:
    python scripts/url_chat.py <URL>
    python scripts/url_chat.py https://docs.python.org/3/library/asyncio.html

Commands during chat:
    /url <new_url>  - Change URL context
    /clear          - Clear URL context
    /quit           - Exit
"""

import sys
import requests

API_URL = "http://localhost:9000/api/v1"
USERNAME = "admin"
PASSWORD = "SecureAdm1nP@ss2024!"


def login():
    """Login and return access token."""
    resp = requests.post(f"{API_URL}/auth/login", json={
        "username": USERNAME,
        "password": PASSWORD
    })
    if resp.status_code == 200 and resp.json().get("success"):
        return resp.json()["data"]["access_token"]
    else:
        print(f"Login failed: {resp.text}")
        sys.exit(1)


def chat(token, question, url_context=None):
    """Send question to RAG agent with optional URL context."""
    payload = {
        "task": question,
        "agent_type": "rag",
        "language": "en"
    }
    if url_context:
        payload["url_context"] = url_context

    resp = requests.post(
        f"{API_URL}/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=120
    )

    if resp.status_code == 200:
        return resp.json().get("answer", "No response")
    else:
        return f"Error: {resp.text}"


def main():
    # Get initial URL from command line
    url_context = None
    if len(sys.argv) > 1:
        url_context = sys.argv[1]

    print("=" * 60)
    print("URL Chat CLI - RAG with URL Context")
    print("=" * 60)
    print("Commands: /url <url>, /clear, /quit")
    print("=" * 60)

    # Login
    print("\nLogging in...", end=" ")
    token = login()
    print("OK\n")

    if url_context:
        print(f"URL Context: {url_context}\n")
    else:
        print("No URL context. Use /url <url> to set one.\n")

    # Interactive loop
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()

            if cmd == "/quit":
                print("Bye!")
                break
            elif cmd == "/clear":
                url_context = None
                print("URL context cleared.\n")
                continue
            elif cmd == "/url":
                if len(parts) > 1:
                    url_context = parts[1]
                    print(f"URL context set: {url_context}\n")
                else:
                    print("Usage: /url <url>\n")
                continue
            else:
                print(f"Unknown command: {cmd}\n")
                continue

        # Send question
        print("\nAssistant: ", end="", flush=True)
        response = chat(token, user_input, url_context)
        print(response)
        print()


if __name__ == "__main__":
    main()
