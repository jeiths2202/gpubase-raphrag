"""
Enterprise-grade Terminal UI for KMS AI Agent CLI

Provides rich, cross-platform terminal interface similar to Claude Code CLI.
Uses the 'rich' library for advanced formatting.
"""

import sys
import os
import locale
from typing import Optional, List, Dict, Any
from datetime import datetime


def _setup_windows_utf8():
    """Setup UTF-8 encoding for Windows console"""
    if sys.platform == "win32":
        try:
            # Set console code page to UTF-8
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)

            # Set environment variable for Python
            os.environ["PYTHONIOENCODING"] = "utf-8"

            # Reconfigure stdout/stderr with UTF-8 encoding
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')

            return True
        except Exception:
            return False
    return True


# Setup UTF-8 on Windows before anything else
_setup_windows_utf8()


# Check if terminal supports Unicode
def _supports_unicode() -> bool:
    """Check if the terminal supports Unicode output"""
    if sys.platform == "win32":
        # Check Windows console encoding
        try:
            encoding = sys.stdout.encoding or locale.getpreferredencoding()
            return encoding.lower() in ('utf-8', 'utf8', 'utf-16', 'utf16')
        except Exception:
            return False
    return True

UNICODE_SUPPORT = _supports_unicode()

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.prompt import Prompt
    from rich.theme import Theme
    from rich.box import ROUNDED, HEAVY, DOUBLE, ASCII
    from rich.align import Align
    from rich.columns import Columns
    from rich.rule import Rule
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


# Custom theme for KMS CLI
KMS_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
    "success": "green",
    "agent.auto": "bright_cyan",
    "agent.ims": "bright_yellow",
    "agent.rag": "bright_green",
    "agent.vision": "bright_magenta",
    "agent.code": "bright_blue",
    "agent.planner": "bright_white",
    "thinking": "dim italic",
    "tool": "magenta",
    "prompt": "bold cyan",
    "response": "white",
    "header": "bold bright_white on blue",
})


class EnterpriseUI:
    """Enterprise-grade terminal UI"""

    # Unicode icons (for terminals with Unicode support)
    AGENT_ICONS_UNICODE = {
        "auto": "🤖",
        "ims": "🔍",
        "rag": "📚",
        "vision": "👁",
        "code": "💻",
        "planner": "📋",
    }

    # ASCII icons (for terminals without Unicode support)
    AGENT_ICONS_ASCII = {
        "auto": "[A]",
        "ims": "[I]",
        "rag": "[R]",
        "vision": "[V]",
        "code": "[C]",
        "planner": "[P]",
    }

    # Status icons
    ICONS_UNICODE = {
        "info": "ℹ",
        "success": "✓",
        "warning": "⚠",
        "error": "✗",
        "tool": "🔧",
        "thinking": "...",
        "connected": "●",
        "disconnected": "○",
        "arrow": "→",
        "wave": "👋",
    }

    ICONS_ASCII = {
        "info": "[i]",
        "success": "[+]",
        "warning": "[!]",
        "error": "[x]",
        "tool": "[T]",
        "thinking": "...",
        "connected": "*",
        "disconnected": "o",
        "arrow": "->",
        "wave": "",
    }

    AGENT_COLORS = {
        "auto": "bright_cyan",
        "ims": "bright_yellow",
        "rag": "bright_green",
        "vision": "bright_magenta",
        "code": "bright_blue",
        "planner": "bright_white",
    }

    def __init__(self, use_color: bool = True):
        self.use_color = use_color
        self.unicode = UNICODE_SUPPORT

        # Select icon set based on Unicode support
        self.AGENT_ICONS = self.AGENT_ICONS_UNICODE if self.unicode else self.AGENT_ICONS_ASCII
        self.ICONS = self.ICONS_UNICODE if self.unicode else self.ICONS_ASCII

        # Select box style based on Unicode support
        self.box_style = ROUNDED if self.unicode else ASCII
        self.double_box = DOUBLE if self.unicode else ASCII

        if HAS_RICH and use_color:
            self.console = Console(theme=KMS_THEME, force_terminal=True)
            self.rich_mode = True
        else:
            self.console = Console(force_terminal=True, no_color=not use_color)
            self.rich_mode = HAS_RICH

        self._live: Optional[Live] = None
        self._current_response = ""

    def print_banner(self):
        """Print enterprise-grade banner"""
        if self.rich_mode:
            banner_text = Text()
            banner_text.append("KMS AI Agent", style="bold bright_white")
            banner_text.append(" CLI", style="bold cyan")

            subtitle = Text("HybridRAG Knowledge Management System", style="dim")
            version = Text("v1.0.0", style="dim cyan")

            panel = Panel(
                Align.center(
                    Text.assemble(
                        banner_text, "\n",
                        subtitle, "  ", version
                    )
                ),
                box=self.double_box,
                border_style="cyan",
                padding=(1, 2),
            )
            self.console.print()
            self.console.print(panel)
            self.console.print()
        else:
            self.console.print("\n" + "=" * 60)
            self.console.print("  KMS AI Agent CLI")
            self.console.print("  HybridRAG Knowledge Management System  v1.0.0")
            self.console.print("=" * 60 + "\n")

    def print_status(self, server: str, agent: str, language: str,
                     logged_in: bool, user: str, session_id: Optional[str],
                     ims_connected: bool = False):
        """Print status panel"""
        if self.rich_mode:
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("Key", style="dim")
            table.add_column("Value", style="bright_white")

            table.add_row("Server", server)

            agent_icon = self.AGENT_ICONS.get(agent, "[A]")
            agent_color = self.AGENT_COLORS.get(agent, "white")
            table.add_row("Agent", Text(f"{agent_icon} {agent}", style=agent_color))

            table.add_row("Language", language.upper())

            conn_icon = self.ICONS["connected"] if logged_in else self.ICONS["disconnected"]
            status_style = "green" if logged_in else "red"
            status_label = "Connected" if logged_in else "Disconnected"
            status_text = Text(f"{conn_icon} {status_label}", style=status_style)
            table.add_row("Status", status_text)

            if logged_in:
                table.add_row("User", user)

            # IMS Status
            ims_icon = self.ICONS["connected"] if ims_connected else self.ICONS["disconnected"]
            ims_style = "green" if ims_connected else "dim"
            ims_label = "Connected" if ims_connected else "Not connected"
            ims_text = Text(f"{ims_icon} {ims_label}", style=ims_style)
            table.add_row("IMS", ims_text)

            if session_id:
                table.add_row("Session", session_id[:8] + "...")

            panel = Panel(table, title="[bold]Status[/bold]", border_style="dim", box=self.box_style)
            self.console.print(panel)
        else:
            self.console.print("\n--- Status ---")
            self.console.print(f"  Server:   {server}")
            self.console.print(f"  Agent:    {agent}")
            self.console.print(f"  Language: {language}")
            self.console.print(f"  Status:   {'Connected' if logged_in else 'Disconnected'}")
            self.console.print(f"  IMS:      {'Connected' if ims_connected else 'Not connected'}")
            if session_id:
                self.console.print(f"  Session:  {session_id[:8]}...")
            self.console.print()

    def print_help(self, commands: Dict[str, str], agents: List[str], current_agent: str):
        """Print help panel"""
        if self.rich_mode:
            # Commands table
            cmd_table = Table(show_header=True, box=self.box_style, header_style="bold cyan")
            cmd_table.add_column("Command", style="yellow")
            cmd_table.add_column("Description", style="white")

            for cmd, desc in commands.items():
                cmd_table.add_row(cmd, desc)

            # Agents table
            agent_table = Table(show_header=True, box=self.box_style, header_style="bold cyan")
            agent_table.add_column("", width=3)
            agent_table.add_column("Agent", style="white")
            agent_table.add_column("Icon", justify="center")

            arrow = self.ICONS["arrow"]
            for agent in agents:
                marker = arrow if agent == current_agent else ""
                icon = self.AGENT_ICONS.get(agent, "")
                color = self.AGENT_COLORS.get(agent, "white")
                agent_table.add_row(
                    Text(marker, style="green bold"),
                    Text(agent, style=color),
                    icon
                )

            self.console.print()
            self.console.print(Panel(cmd_table, title="[bold]Commands[/bold]", border_style="cyan", box=self.box_style))
            self.console.print(Panel(agent_table, title="[bold]Agents[/bold]", border_style="cyan", box=self.box_style))
            self.console.print()
        else:
            self.console.print("\n--- Commands ---")
            for cmd, desc in commands.items():
                self.console.print(f"  {cmd:<20} {desc}")
            self.console.print("\n--- Agents ---")
            for agent in agents:
                marker = self.ICONS["arrow"] if agent == current_agent else " "
                self.console.print(f"  {marker} {agent}")
            self.console.print()

    def get_prompt(self, agent: str) -> str:
        """Get user input with styled prompt"""
        if self.rich_mode:
            icon = self.AGENT_ICONS.get(agent, "🤖")
            color = self.AGENT_COLORS.get(agent, "cyan")
            prompt_text = f"[{color}]{icon} {agent}[/{color}] [bold]>[/bold] "
            try:
                return Prompt.ask(prompt_text, console=self.console).strip()
            except (EOFError, KeyboardInterrupt):
                raise
        else:
            try:
                return input(f"[{agent}] > ").strip()
            except (EOFError, KeyboardInterrupt):
                raise

    def print_info(self, message: str):
        """Print info message"""
        icon = self.ICONS["info"]
        if self.rich_mode:
            self.console.print(f"[info]{icon}[/info] {message}")
        else:
            self.console.print(f"{icon} {message}")

    def print_success(self, message: str):
        """Print success message"""
        icon = self.ICONS["success"]
        if self.rich_mode:
            self.console.print(f"[success]{icon}[/success] {message}")
        else:
            self.console.print(f"{icon} {message}")

    def print_warning(self, message: str):
        """Print warning message"""
        icon = self.ICONS["warning"]
        if self.rich_mode:
            self.console.print(f"[warning]{icon}[/warning] {message}")
        else:
            self.console.print(f"{icon} {message}")

    def print_error(self, message: str):
        """Print error message"""
        icon = self.ICONS["error"]
        if self.rich_mode:
            self.console.print(f"[error]{icon}[/error] {message}")
        else:
            self.console.print(f"{icon} {message}")

    def start_thinking(self, message: str = "Thinking..."):
        """Start thinking indicator"""
        if self.rich_mode and self.unicode:
            # Only use spinner animation if Unicode is supported
            self._live = Live(
                Spinner("dots", text=Text(message, style="thinking")),
                console=self.console,
                refresh_per_second=10,
                transient=True
            )
            try:
                self._live.start()
            except UnicodeEncodeError:
                # Fallback to simple text if spinner fails
                self._live = None
                self.console.print(f"[...] {message}", end="")
        else:
            # Simple ASCII indicator for non-Unicode terminals
            self.console.print(f"[...] {message}", end="")

    def update_thinking(self, message: str):
        """Update thinking message"""
        if self._live:
            try:
                self._live.update(Spinner("dots", text=Text(message, style="thinking")))
            except UnicodeEncodeError:
                pass

    def stop_thinking(self):
        """Stop thinking indicator"""
        if self._live:
            try:
                self._live.stop()
            except UnicodeEncodeError:
                pass
            self._live = None
        # Clear the line for non-spinner mode
        print("\r" + " " * 60 + "\r", end="")

    def print_tool_call(self, tool_name: str, description: str = ""):
        """Print tool call indicator"""
        self.stop_thinking()
        icon = self.ICONS["tool"]
        if self.rich_mode:
            tool_text = Text()
            tool_text.append(f"{icon} ", style="tool")
            tool_text.append(f"[{tool_name}]", style="tool bold")
            if description:
                tool_text.append(f" {description}", style="dim")
            self.console.print(tool_text)
        else:
            desc = f" - {description}" if description else ""
            self.console.print(f"{icon} [{tool_name}]{desc}")

    def print_tool_result(self, result_size: int):
        """Print tool result info"""
        branch = "`-" if not self.unicode else "└─"
        if self.rich_mode:
            self.console.print(f"  [dim]{branch} Result: {result_size} chars[/dim]")
        else:
            self.console.print(f"  {branch} Tool result: {result_size} chars")

    def start_response(self):
        """Start streaming response"""
        self.stop_thinking()
        self._current_response = ""
        if self.rich_mode:
            self.console.print()

    def stream_response(self, chunk: str):
        """Stream response chunk"""
        self._current_response += chunk
        if self.rich_mode:
            self.console.print(chunk, end="", markup=False)
        else:
            print(chunk, end="", flush=True)

    def end_response(self):
        """End streaming response"""
        if self.rich_mode:
            self.console.print()
        else:
            print()

    def print_response(self, text: str):
        """Print complete response with markdown formatting"""
        if self.rich_mode:
            # Try to render as markdown
            try:
                md = Markdown(text)
                self.console.print(md)
            except Exception:
                self.console.print(text)
        else:
            self.console.print(text)

    def print_sources(self, sources: List[Dict[str, Any]]):
        """Print sources panel"""
        if not sources:
            return

        if self.rich_mode:
            table = Table(show_header=True, box=self.box_style, header_style="bold")
            table.add_column("#", style="dim", width=3)
            table.add_column("Source", style="cyan")
            table.add_column("Score", style="green", width=8)

            for i, source in enumerate(sources[:5], 1):
                name = source.get("name", source.get("title", "Unknown"))
                score = source.get("score", source.get("similarity", 0))
                table.add_row(str(i), name, f"{score:.2f}")

            self.console.print(Panel(table, title="[bold]Sources[/bold]", border_style="dim", box=self.box_style))
        else:
            self.console.print("\n--- Sources ---")
            for i, source in enumerate(sources[:5], 1):
                name = source.get("name", source.get("title", "Unknown"))
                self.console.print(f"  {i}. {name}")

    def print_login_panel(self):
        """Print login panel"""
        if self.rich_mode:
            self.console.print()
            self.console.print(Rule("Login", style="cyan"))
        else:
            self.console.print("\n=== Login ===")

    def get_username(self) -> str:
        """Get username input"""
        if self.rich_mode:
            return Prompt.ask("[cyan]Username[/cyan]", console=self.console).strip()
        else:
            return input("Username: ").strip()

    def get_password(self, prompt: str = "Password") -> str:
        """Get password input (hidden)"""
        import getpass
        if self.rich_mode:
            return Prompt.ask(f"[cyan]{prompt}[/cyan]", password=True, console=self.console)
        else:
            return getpass.getpass(f"{prompt}: ")

    def get_input(self, prompt: str, default: str = "") -> str:
        """Get user input with optional default value"""
        if self.rich_mode:
            if default:
                return Prompt.ask(f"[cyan]{prompt}[/cyan]", default=default, console=self.console).strip()
            else:
                return Prompt.ask(f"[cyan]{prompt}[/cyan]", console=self.console).strip()
        else:
            if default:
                value = input(f"{prompt} [{default}]: ").strip()
                return value if value else default
            else:
                return input(f"{prompt}: ").strip()

    def clear(self):
        """Clear screen"""
        self.console.clear()

    def print_goodbye(self):
        """Print goodbye message"""
        wave = self.ICONS["wave"]
        goodbye_text = f"Goodbye! {wave}" if wave else "Goodbye!"
        if self.rich_mode:
            self.console.print()
            self.console.print(Panel(
                Align.center(Text(goodbye_text, style="bold cyan")),
                box=self.box_style,
                border_style="dim"
            ))
        else:
            self.console.print(f"\n{goodbye_text}")

    def print_divider(self, title: str = ""):
        """Print divider line"""
        if self.rich_mode:
            self.console.print(Rule(title, style="dim"))
        else:
            if title:
                self.console.print(f"\n--- {title} ---")
            else:
                self.console.print("-" * 40)

    def print_agent_switch(self, old_agent: str, new_agent: str):
        """Print agent switch notification"""
        success_icon = self.ICONS["success"]
        arrow = self.ICONS["arrow"]
        old_icon = self.AGENT_ICONS.get(old_agent, "")
        new_icon = self.AGENT_ICONS.get(new_agent, "")
        new_color = self.AGENT_COLORS.get(new_agent, "white")
        if self.rich_mode:
            self.console.print(
                f"[success]{success_icon}[/success] Agent: {old_icon} {old_agent} {arrow} [{new_color}]{new_icon} {new_agent}[/{new_color}]"
            )
        else:
            self.console.print(f"{success_icon} Agent switched: {old_agent} {arrow} {new_agent}")

    def print_session_info(self, session_id: str, steps: int, time_ms: float):
        """Print session execution info"""
        divider = "-" * 40 if not self.unicode else "─" * 40
        if self.rich_mode:
            info = Text()
            info.append("\n")
            info.append(divider, style="dim")
            info.append(f"\n  Session: ", style="dim")
            info.append(session_id[:12], style="cyan")
            info.append(f"  Steps: ", style="dim")
            info.append(str(steps), style="green")
            info.append(f"  Time: ", style="dim")
            info.append(f"{time_ms:.1f}ms", style="yellow")
            info.append("\n")
            self.console.print(info)
        else:
            self.console.print(f"\n  [Session: {session_id[:12]} | Steps: {steps} | Time: {time_ms:.1f}ms]")

    def print_llm_status(self, llm_data: Dict[str, Any], current_agent: str):
        """Print LLM status panel"""
        if not llm_data:
            self.print_error("Failed to get LLM status")
            return

        # Map agents to their primary LLM
        agent_llm_map = {
            "auto": "nemotron_llm",
            "rag": "nemotron_llm",
            "ims": "nemotron_llm",
            "vision": "nemotron_llm",
            "planner": "nemotron_llm",
            "code": "ollama_qwen",  # Local Qwen 2.5 3B via Ollama
        }
        current_llm = agent_llm_map.get(current_agent, "nemotron_llm")

        if self.rich_mode:
            table = Table(show_header=True, box=self.box_style, header_style="bold cyan")
            table.add_column("", width=3)
            table.add_column("Model", style="white")
            table.add_column("Purpose", style="dim")
            table.add_column("Status", justify="center")
            table.add_column("Response", justify="right")
            table.add_column("GPU", justify="center")

            arrow = self.ICONS["arrow"]
            for key, info in llm_data.items():
                is_current = key == current_llm
                marker = arrow if is_current else ""

                # Status indicator
                status = info.get("status", "unknown")
                if status == "healthy":
                    status_text = Text("Online", style="green")
                elif status == "unhealthy":
                    status_text = Text("Offline", style="red")
                else:
                    status_text = Text("Unknown", style="yellow")

                # Response time
                resp_time = info.get("response_time_ms")
                resp_text = f"{resp_time:.0f}ms" if resp_time else "-"

                # GPU
                gpu = info.get("gpu", "-") or "-"

                # Name with current indicator
                name_style = "bold cyan" if is_current else "white"
                name = info.get("name", key)

                table.add_row(
                    Text(marker, style="green bold"),
                    Text(name, style=name_style),
                    info.get("purpose", ""),
                    status_text,
                    resp_text,
                    str(gpu)
                )

            panel = Panel(table, title="[bold]Available LLMs[/bold]", border_style="cyan", box=self.box_style)
            self.console.print()
            self.console.print(panel)

            # Show current agent's LLM
            current_info = llm_data.get(current_llm, {})
            self.console.print(f"  Current agent [{current_agent}] uses: [cyan]{current_info.get('name', 'Unknown')}[/cyan]")
            self.console.print()
        else:
            self.console.print("\n=== Available LLMs ===")
            for key, info in llm_data.items():
                is_current = key == current_llm
                marker = self.ICONS["arrow"] if is_current else " "
                status = info.get("status", "unknown")
                name = info.get("name", key)
                purpose = info.get("purpose", "")
                self.console.print(f"  {marker} {name:<25} {purpose:<20} [{status}]")
            self.console.print(f"\n  Current agent [{current_agent}] uses: {llm_data.get(current_llm, {}).get('name', 'Unknown')}")
            self.console.print()


def get_ui(use_color: bool = True) -> EnterpriseUI:
    """Factory function to get UI instance"""
    return EnterpriseUI(use_color=use_color)
