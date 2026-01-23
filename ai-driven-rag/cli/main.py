#!/usr/bin/env python3
"""CLI interface for AI Driven RAG System."""
import argparse
import asyncio
import sys
import getpass
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import AIAgent


def setup_ims_credentials(username: str = None, password: str = None, prompt: bool = False) -> bool:
    """Setup IMS credentials from arguments or prompt."""
    from tools.ims_search import _get_ims_crawler

    crawler = _get_ims_crawler()

    # If already has credentials, skip
    if crawler.has_credentials():
        return True

    # Use provided credentials
    if username and password:
        crawler.set_credentials(username, password)
        return True

    # Prompt for credentials if requested
    if prompt:
        print("\n[IMS 로그인 필요]")
        try:
            ims_user = input("IMS ID: ").strip()
            ims_pass = getpass.getpass("IMS Password: ").strip()
            if ims_user and ims_pass:
                crawler.set_credentials(ims_user, ims_pass)
                print("IMS credentials set.\n")
                return True
        except (EOFError, KeyboardInterrupt):
            print("\nIMS login skipped.\n")

    return False


def print_header():
    """Print CLI header."""
    print("\n" + "=" * 60)
    print("  AI Driven RAG System")
    print("  No rules, just AI decisions")
    print("=" * 60 + "\n")


def print_response(response):
    """Print agent response with formatting."""
    print("\n" + "-" * 40)
    print("Answer:")
    print("-" * 40)
    print(response.answer)

    if response.tool_calls_made:
        print("\n" + "-" * 40)
        print(f"Tool calls made: {len(response.tool_calls_made)}")
        print("-" * 40)
        for i, tc in enumerate(response.tool_calls_made, 1):
            print(f"  {i}. {tc['tool']}({tc['arguments']}) → {tc['result_summary']}")

    if response.sources:
        print("\n" + "-" * 40)
        print("Sources:")
        print("-" * 40)
        for source in response.sources:
            print(f"  - {source}")

    print()


async def run_single_query(query: str, stream: bool = False, ims_user: str = None, ims_pass: str = None):
    """Run a single query."""
    # Setup IMS credentials if provided
    if ims_user and ims_pass:
        setup_ims_credentials(ims_user, ims_pass)

    agent = AIAgent()

    try:
        if stream:
            print("\nAnswer: ", end="", flush=True)
            async for chunk in agent.run_stream(query):
                print(chunk, end="", flush=True)
            print("\n")
        else:
            response = await agent.run(query)

            # Check if IMS login is required and prompt for credentials
            if _needs_ims_login(response):
                print("\n[IMS 로그인이 필요합니다]")
                if setup_ims_credentials(prompt=True):
                    # Retry the query with credentials
                    response = await agent.run(query)

            print_response(response)
    finally:
        await agent.close()


def _needs_ims_login(response) -> bool:
    """Check if response indicates IMS login is required."""
    for tc in response.tool_calls_made:
        result_summary = tc.get("result_summary", "")
        if "login" in result_summary.lower() or "로그인" in result_summary:
            return True
    return "로그인이 필요" in response.answer or "login_required" in response.answer


async def run_interactive(ims_user: str = None, ims_pass: str = None):
    """Run interactive REPL mode."""
    # Setup IMS credentials if provided
    if ims_user and ims_pass:
        setup_ims_credentials(ims_user, ims_pass)

    print_header()
    print("Type your questions. Commands:")
    print("  /quit, /exit - Exit the program")
    print("  /clear       - Clear conversation history")
    print("  /stream      - Toggle streaming mode")
    print("  /ims-login   - Login to IMS")
    print("  /ims-logout  - Logout from IMS")
    print()

    agent = AIAgent()
    conversation_history = []
    stream_mode = False

    try:
        while True:
            try:
                query = input("You: ").strip()
            except EOFError:
                break

            if not query:
                continue

            # Handle commands
            if query.lower() in ["/quit", "/exit", "quit", "exit"]:
                print("Goodbye!")
                break

            if query.lower() == "/clear":
                conversation_history = []
                print("Conversation history cleared.\n")
                continue

            if query.lower() == "/stream":
                stream_mode = not stream_mode
                print(f"Streaming mode: {'ON' if stream_mode else 'OFF'}\n")
                continue

            if query.lower() == "/ims-login":
                setup_ims_credentials(prompt=True)
                continue

            if query.lower() == "/ims-logout":
                from tools.ims_search import _get_ims_crawler
                _get_ims_crawler().clear_credentials()
                print("IMS logged out.\n")
                continue

            # Run query
            try:
                if stream_mode:
                    print("\nAssistant: ", end="", flush=True)
                    async for chunk in agent.run_stream(query, conversation_history):
                        print(chunk, end="", flush=True)
                    print("\n")
                else:
                    response = await agent.run(query, conversation_history)

                    # Check if IMS login is required
                    if _needs_ims_login(response):
                        print("\n[IMS 로그인이 필요합니다]")
                        if setup_ims_credentials(prompt=True):
                            # Retry the query
                            response = await agent.run(query, conversation_history)

                    print_response(response)

                    # Add to conversation history
                    conversation_history.append({"role": "user", "content": query})
                    conversation_history.append({"role": "assistant", "content": response.answer})

            except Exception as e:
                print(f"\nError: {e}\n")

    finally:
        await agent.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI Driven RAG System - CLI Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single query
  python -m cli.main "에러 코드 E001에 대해 알려줘"

  # Interactive mode
  python -m cli.main

  # Stream mode
  python -m cli.main --stream "검색어"

  # With IMS credentials
  python -m cli.main --ims-user hong --ims-password 1234 "DFSORT 이슈"

  # Using environment variables
  IMS_USERNAME=hong IMS_PASSWORD=1234 python -m cli.main "DFSORT 이슈"
        """,
    )

    parser.add_argument(
        "query",
        nargs="?",
        help="Query to run (if not provided, starts interactive mode)",
    )
    parser.add_argument(
        "--stream", "-s",
        action="store_true",
        help="Enable streaming output",
    )
    parser.add_argument(
        "--ims-user",
        help="IMS username for authentication",
    )
    parser.add_argument(
        "--ims-password",
        help="IMS password for authentication",
    )

    args = parser.parse_args()

    if args.query:
        asyncio.run(run_single_query(args.query, args.stream, args.ims_user, args.ims_password))
    else:
        asyncio.run(run_interactive(args.ims_user, args.ims_password))


if __name__ == "__main__":
    main()
