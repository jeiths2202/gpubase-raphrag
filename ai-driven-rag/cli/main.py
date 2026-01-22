#!/usr/bin/env python3
"""CLI interface for AI Driven RAG System."""
import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import AIAgent


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


async def run_single_query(query: str, stream: bool = False):
    """Run a single query."""
    agent = AIAgent()

    try:
        if stream:
            print("\nAnswer: ", end="", flush=True)
            async for chunk in agent.run_stream(query):
                print(chunk, end="", flush=True)
            print("\n")
        else:
            response = await agent.run(query)
            print_response(response)
    finally:
        await agent.close()


async def run_interactive():
    """Run interactive REPL mode."""
    print_header()
    print("Type your questions. Commands:")
    print("  /quit, /exit - Exit the program")
    print("  /clear       - Clear conversation history")
    print("  /stream      - Toggle streaming mode")
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

            # Run query
            try:
                if stream_mode:
                    print("\nAssistant: ", end="", flush=True)
                    async for chunk in agent.run_stream(query, conversation_history):
                        print(chunk, end="", flush=True)
                    print("\n")
                else:
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

    args = parser.parse_args()

    if args.query:
        asyncio.run(run_single_query(args.query, args.stream))
    else:
        asyncio.run(run_interactive())


if __name__ == "__main__":
    main()
