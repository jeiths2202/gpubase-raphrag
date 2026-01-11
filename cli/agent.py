#!/usr/bin/env python3
"""
KMS AI Agent CLI Client

A command-line interface for interacting with the KMS AI Agent system.
Supports multiple agent types: auto, ims, rag, vision, code, planner

Usage:
    python -m cli.agent                    # Interactive mode
    python -m cli.agent -q "your question" # Single query mode
    python -m cli.agent --agent ims        # Use specific agent
"""

import argparse
import json
import os
import sys
import getpass
from typing import Optional, Generator
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install with: pip install httpx")
    sys.exit(1)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cli.terminal import (
    print_info, print_error, print_warning, print_success,
    print_agent_response, print_thinking, print_tool_call,
    print_banner, print_prompt, clear_line, Colors
)
from cli.auth import AuthManager
from cli.config import Config


class AgentClient:
    """CLI client for KMS AI Agent API"""

    AGENT_TYPES = ["auto", "ims", "rag", "vision", "code", "planner"]

    def __init__(self, config: Config, auth: AuthManager):
        self.config = config
        self.auth = auth
        self.conversation_id: Optional[str] = None
        self.current_agent: str = "auto"

    def stream_query(self, query: str, agent_type: Optional[str] = None) -> Generator[dict, None, None]:
        """Send query to agent and stream response"""
        agent = agent_type or self.current_agent
        url = f"{self.config.api_url}/agents/stream"

        headers = self.auth.get_headers()
        if not headers:
            print_error("Not authenticated. Please login first.")
            return

        payload = {
            "task": query,
            "agent_type": agent,
            "language": self.config.language
        }

        if self.conversation_id:
            payload["conversation_id"] = self.conversation_id

        try:
            with httpx.Client(timeout=120.0) as client:
                with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code == 401:
                        print_error("Session expired. Please login again.")
                        self.auth.clear_token()
                        return

                    if response.status_code != 200:
                        print_error(f"API error: {response.status_code}")
                        return

                    buffer = ""
                    for chunk in response.iter_text():
                        buffer += chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if line.startswith("data: "):
                                try:
                                    data = json.loads(line[6:])
                                    yield data
                                except json.JSONDecodeError:
                                    continue

        except httpx.ConnectError:
            print_error(f"Cannot connect to server at {self.config.api_url}")
        except httpx.TimeoutException:
            print_error("Request timed out")
        except Exception as e:
            print_error(f"Error: {e}")

    def query(self, query: str, agent_type: Optional[str] = None) -> str:
        """Send query and collect full response"""
        full_response = ""
        current_type = None

        for chunk in self.stream_query(query, agent_type):
            chunk_type = chunk.get("type", "")
            content = chunk.get("content", "")

            if chunk_type == "thinking":
                if current_type != "thinking":
                    print_thinking("Thinking...")
                    current_type = "thinking"

            elif chunk_type == "tool_call":
                tool_name = chunk.get("tool_name", "tool")
                print_tool_call(tool_name, content)
                current_type = "tool_call"

            elif chunk_type == "tool_result":
                print_info(f"Tool result received ({len(content)} chars)")
                current_type = "tool_result"

            elif chunk_type == "content":
                if current_type != "content":
                    print()  # New line before content
                    current_type = "content"
                print_agent_response(content, end="")
                full_response += content

            elif chunk_type == "done":
                if chunk.get("conversation_id"):
                    self.conversation_id = chunk["conversation_id"]
                print()  # Final newline

            elif chunk_type == "error":
                print_error(content)

        return full_response

    def set_agent(self, agent_type: str) -> bool:
        """Set current agent type"""
        if agent_type.lower() in self.AGENT_TYPES:
            self.current_agent = agent_type.lower()
            print_success(f"Agent switched to: {self.current_agent}")
            return True
        else:
            print_error(f"Invalid agent type. Available: {', '.join(self.AGENT_TYPES)}")
            return False

    def new_conversation(self):
        """Start a new conversation"""
        self.conversation_id = None
        print_success("New conversation started")


class CLI:
    """Interactive CLI for Agent"""

    COMMANDS = {
        "/help": "Show this help message",
        "/agent <type>": "Switch agent (auto, ims, rag, vision, code, planner)",
        "/new": "Start new conversation",
        "/status": "Show current status",
        "/clear": "Clear screen",
        "/exit": "Exit CLI",
        "/quit": "Exit CLI",
    }

    def __init__(self, config: Config):
        self.config = config
        self.auth = AuthManager(config)
        self.client = AgentClient(config, self.auth)
        self.running = False

    def show_help(self):
        """Display help information"""
        print(f"\n{Colors.CYAN}Available Commands:{Colors.RESET}")
        for cmd, desc in self.COMMANDS.items():
            print(f"  {Colors.YELLOW}{cmd:<20}{Colors.RESET} {desc}")
        print(f"\n{Colors.CYAN}Agent Types:{Colors.RESET}")
        for agent in AgentClient.AGENT_TYPES:
            marker = "→" if agent == self.client.current_agent else " "
            print(f"  {marker} {agent}")
        print()

    def show_status(self):
        """Display current status"""
        print(f"\n{Colors.CYAN}=== Status ==={Colors.RESET}")
        print(f"  Server:       {self.config.api_url}")
        print(f"  Agent:        {self.client.current_agent}")
        print(f"  Language:     {self.config.language}")
        print(f"  Logged in:    {'Yes' if self.auth.is_authenticated() else 'No'}")
        print(f"  Conversation: {self.client.conversation_id or 'None'}")
        print()

    def handle_command(self, cmd: str) -> bool:
        """Handle CLI command. Returns True if should continue."""
        parts = cmd.strip().split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command in ("/exit", "/quit"):
            print_info("Goodbye!")
            return False

        elif command == "/help":
            self.show_help()

        elif command == "/agent":
            if args:
                self.client.set_agent(args)
            else:
                print_info(f"Current agent: {self.client.current_agent}")
                print_info(f"Available: {', '.join(AgentClient.AGENT_TYPES)}")

        elif command == "/new":
            self.client.new_conversation()

        elif command == "/status":
            self.show_status()

        elif command == "/clear":
            os.system('cls' if os.name == 'nt' else 'clear')
            print_banner()

        else:
            print_warning(f"Unknown command: {command}. Type /help for available commands.")

        return True

    def login(self) -> bool:
        """Handle login flow"""
        if self.auth.is_authenticated():
            if self.auth.refresh_token():
                print_success("Session restored")
                return True

        print(f"\n{Colors.CYAN}=== Login ==={Colors.RESET}")

        # Try default admin credentials first for development
        if self.config.is_dev_mode():
            print_info("Development mode: trying default credentials...")
            if self.auth.login("admin", "admin123"):
                print_success("Logged in as admin")
                return True

        # Manual login
        for attempt in range(3):
            username = input(f"{Colors.CYAN}Username: {Colors.RESET}").strip()
            password = getpass.getpass(f"{Colors.CYAN}Password: {Colors.RESET}")

            if self.auth.login(username, password):
                print_success(f"Logged in as {username}")
                return True
            else:
                remaining = 2 - attempt
                if remaining > 0:
                    print_warning(f"Login failed. {remaining} attempts remaining.")

        print_error("Login failed. Please check your credentials.")
        return False

    def run_interactive(self):
        """Run interactive REPL mode"""
        print_banner()

        if not self.login():
            return

        self.show_status()
        print_info("Type /help for available commands, or enter your query.\n")

        self.running = True
        while self.running:
            try:
                user_input = print_prompt(self.client.current_agent)

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    self.running = self.handle_command(user_input)
                else:
                    self.client.query(user_input)
                    print()  # Extra line after response

            except KeyboardInterrupt:
                print("\n")
                print_info("Use /exit to quit or press Ctrl+C again")
                try:
                    input()
                except KeyboardInterrupt:
                    print_info("\nGoodbye!")
                    break

            except EOFError:
                print_info("\nGoodbye!")
                break

    def run_single_query(self, query: str, agent_type: Optional[str] = None):
        """Run single query mode"""
        if not self.login():
            return

        if agent_type:
            self.client.set_agent(agent_type)

        self.client.query(query)


def main():
    parser = argparse.ArgumentParser(
        description="KMS AI Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cli.agent                         # Interactive mode
  python -m cli.agent -q "search DFSRRC00"    # Single query
  python -m cli.agent --agent ims -q "list issues"  # IMS agent query
  python -m cli.agent --server http://localhost:9000  # Custom server
        """
    )

    parser.add_argument(
        "-q", "--query",
        help="Single query to execute (non-interactive mode)"
    )
    parser.add_argument(
        "-a", "--agent",
        choices=AgentClient.AGENT_TYPES,
        default="auto",
        help="Agent type to use (default: auto)"
    )
    parser.add_argument(
        "-s", "--server",
        default=os.environ.get("KMS_API_URL", "http://localhost:9000"),
        help="API server URL (default: http://localhost:9000)"
    )
    parser.add_argument(
        "-l", "--language",
        choices=["ko", "en", "ja"],
        default="ko",
        help="Response language (default: ko)"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )

    args = parser.parse_args()

    # Initialize config
    config = Config(
        api_url=args.server,
        language=args.language,
        use_color=not args.no_color
    )

    # Apply color settings
    if args.no_color:
        Colors.disable()

    # Create CLI and run
    cli = CLI(config)

    if args.query:
        cli.run_single_query(args.query, args.agent)
    else:
        cli.run_interactive()


if __name__ == "__main__":
    main()
