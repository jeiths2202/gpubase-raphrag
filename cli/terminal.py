"""
Terminal formatting utilities for CLI Agent

Provides colored output and formatting for terminal display.
"""

import sys
import os


class Colors:
    """ANSI color codes for terminal output"""

    _enabled = True

    # Basic colors
    BLACK = "\033[0;30m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    MAGENTA = "\033[0;35m"
    CYAN = "\033[0;36m"
    WHITE = "\033[0;37m"

    # Bright colors
    BRIGHT_BLACK = "\033[0;90m"
    BRIGHT_RED = "\033[0;91m"
    BRIGHT_GREEN = "\033[0;92m"
    BRIGHT_YELLOW = "\033[0;93m"
    BRIGHT_BLUE = "\033[0;94m"
    BRIGHT_MAGENTA = "\033[0;95m"
    BRIGHT_CYAN = "\033[0;96m"
    BRIGHT_WHITE = "\033[0;97m"

    # Text styles
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Reset
    RESET = "\033[0m"

    @classmethod
    def disable(cls):
        """Disable all colors"""
        cls._enabled = False
        for attr in dir(cls):
            if attr.isupper() and not attr.startswith('_'):
                setattr(cls, attr, "")

    @classmethod
    def enable(cls):
        """Re-enable colors (reinitialize)"""
        cls._enabled = True
        cls.BLACK = "\033[0;30m"
        cls.RED = "\033[0;31m"
        cls.GREEN = "\033[0;32m"
        cls.YELLOW = "\033[0;33m"
        cls.BLUE = "\033[0;34m"
        cls.MAGENTA = "\033[0;35m"
        cls.CYAN = "\033[0;36m"
        cls.WHITE = "\033[0;37m"
        cls.BRIGHT_BLACK = "\033[0;90m"
        cls.BRIGHT_RED = "\033[0;91m"
        cls.BRIGHT_GREEN = "\033[0;92m"
        cls.BRIGHT_YELLOW = "\033[0;93m"
        cls.BRIGHT_BLUE = "\033[0;94m"
        cls.BRIGHT_MAGENTA = "\033[0;95m"
        cls.BRIGHT_CYAN = "\033[0;96m"
        cls.BRIGHT_WHITE = "\033[0;97m"
        cls.BOLD = "\033[1m"
        cls.DIM = "\033[2m"
        cls.ITALIC = "\033[3m"
        cls.UNDERLINE = "\033[4m"
        cls.RESET = "\033[0m"


# Enable Windows ANSI support
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        # Fallback: disable colors on Windows if ANSI not supported
        if os.environ.get("TERM") != "xterm":
            Colors.disable()


# Agent type colors
AGENT_COLORS = {
    "auto": Colors.BRIGHT_CYAN,
    "ims": Colors.BRIGHT_YELLOW,
    "rag": Colors.BRIGHT_GREEN,
    "vision": Colors.BRIGHT_MAGENTA,
    "code": Colors.BRIGHT_BLUE,
    "planner": Colors.BRIGHT_WHITE,
}


def print_banner():
    """Print CLI banner"""
    banner = f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   {Colors.BRIGHT_CYAN}KMS AI Agent CLI{Colors.CYAN}                                      ║
║   {Colors.DIM}HybridRAG Knowledge Management System{Colors.RESET}{Colors.CYAN}                ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝{Colors.RESET}
"""
    print(banner)


def print_prompt(agent_type: str = "auto") -> str:
    """Print input prompt and get user input"""
    color = AGENT_COLORS.get(agent_type, Colors.CYAN)
    prompt = f"{color}[{agent_type}]{Colors.RESET} {Colors.BRIGHT_WHITE}>{Colors.RESET} "

    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise


def print_info(message: str):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ{Colors.RESET} {message}")


def print_success(message: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓{Colors.RESET} {message}")


def print_warning(message: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {message}")


def print_error(message: str):
    """Print error message"""
    print(f"{Colors.RED}✗{Colors.RESET} {message}")


def print_thinking(message: str = "Thinking..."):
    """Print thinking indicator"""
    print(f"{Colors.DIM}💭 {message}{Colors.RESET}", end="\r")


def print_tool_call(tool_name: str, description: str = ""):
    """Print tool call indicator"""
    desc = f" - {description}" if description else ""
    print(f"{Colors.MAGENTA}🔧 [{tool_name}]{Colors.RESET}{Colors.DIM}{desc}{Colors.RESET}")


def print_agent_response(text: str, end: str = "\n"):
    """Print agent response with formatting"""
    # Simple markdown-like formatting
    formatted = text

    # Bold: **text** or __text__
    # We'll keep it simple for terminal

    print(f"{Colors.WHITE}{formatted}{Colors.RESET}", end=end, flush=True)


def clear_line():
    """Clear current line"""
    print("\r" + " " * 80 + "\r", end="")


def print_table(headers: list, rows: list):
    """Print formatted table"""
    if not rows:
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Print header
    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    separator = "-+-".join("-" * w for w in widths)

    print(f"{Colors.CYAN}{header_line}{Colors.RESET}")
    print(f"{Colors.DIM}{separator}{Colors.RESET}")

    # Print rows
    for row in rows:
        row_line = " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
        print(row_line)


def print_markdown_simple(text: str):
    """Simple markdown rendering for terminal"""
    lines = text.split("\n")

    for line in lines:
        # Headers
        if line.startswith("### "):
            print(f"{Colors.BOLD}{Colors.CYAN}{line[4:]}{Colors.RESET}")
        elif line.startswith("## "):
            print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}{line[3:]}{Colors.RESET}")
        elif line.startswith("# "):
            print(f"{Colors.BOLD}{Colors.BRIGHT_WHITE}{line[2:]}{Colors.RESET}")
        # Code blocks
        elif line.startswith("```"):
            print(f"{Colors.DIM}{line}{Colors.RESET}")
        # Lists
        elif line.startswith("- ") or line.startswith("* "):
            print(f"  {Colors.YELLOW}•{Colors.RESET} {line[2:]}")
        elif line.startswith("  - ") or line.startswith("  * "):
            print(f"    {Colors.DIM}◦{Colors.RESET} {line[4:]}")
        # Normal text
        else:
            print(line)
