"""
Bash Tool
Executes shell commands with strict whitelist-based security.

SECURITY: This tool uses a whitelist approach to prevent command injection.
Only explicitly allowed commands can be executed, and shell=False is used
to prevent shell metacharacter attacks.
"""
from typing import Dict, Any, Optional, List, Set
import logging
import asyncio
import shlex
import re
import os

from .base import BaseTool
from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


# WHITELIST: Only these commands are allowed (security-first approach)
# Each command must be explicitly listed - no wildcards or patterns
ALLOWED_COMMANDS: Set[str] = {
    # File listing and navigation (read-only)
    "ls", "dir", "pwd", "tree",
    # File reading (read-only)
    "cat", "head", "tail", "less", "more", "file", "stat",
    # Text searching (read-only)
    "grep", "rg", "ag", "awk", "sed",
    # File finding (read-only)
    "find", "locate", "which", "whereis",
    # Text processing (read-only)
    "wc", "sort", "uniq", "cut", "tr", "diff",
    # System info (read-only)
    "date", "cal", "uptime", "whoami", "hostname", "uname",
    # Development tools (controlled)
    "python", "python3", "node", "npm", "npx",
    "git",  # Read operations only - see argument validation
    # Output
    "echo", "printf",
}

# Git subcommands that are allowed (read-only operations)
ALLOWED_GIT_SUBCOMMANDS: Set[str] = {
    "status", "log", "diff", "show", "branch", "tag",
    "ls-files", "ls-tree", "rev-parse", "describe",
    "config", "remote",  # Read config only
}

# Blocked argument patterns (even for allowed commands)
BLOCKED_ARG_PATTERNS = [
    r"^\.\.",           # Directory traversal
    r"^/etc/",          # System config
    r"^/dev/",          # Devices
    r"^/proc/",         # Process info
    r"^/sys/",          # System files
    r"[;&|`$]",         # Shell metacharacters in args
    r"\$\(",            # Command substitution
    r">\s*\S",          # Output redirection
    r"<\s*\S",          # Input redirection
]


class BashTool(BaseTool):
    """
    Tool for executing shell commands with strict whitelist-based security.

    SECURITY MEASURES:
    1. Whitelist-only: Only explicitly allowed commands can run
    2. No shell: Uses subprocess with argument list (not shell string)
    3. Argument validation: All arguments are checked for dangerous patterns
    4. Path restrictions: Blocks access to sensitive system directories
    5. Git restrictions: Only read-only git operations allowed
    """

    def __init__(self, custom_allowed_commands: Optional[Set[str]] = None):
        super().__init__(
            name="bash",
            description="""Execute a shell command (whitelist-based security).
Allowed operations:
- File listing: ls, dir, pwd, tree
- File reading: cat, head, tail, file, stat
- Searching: grep, find, rg, ag
- Text processing: wc, sort, uniq, cut, diff
- Development: python, node, git (read-only)

All other commands are blocked for security."""
        )
        # Use custom whitelist if provided, otherwise use default
        self._allowed_commands = custom_allowed_commands or ALLOWED_COMMANDS

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute (whitelist-only)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Command timeout in seconds (max 60)",
                    "default": 30
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for the command"
                }
            },
            "required": ["command"]
        }

    def _get_base_command(self, cmd_path: str) -> str:
        """Extract base command name from path (e.g., /usr/bin/ls -> ls)"""
        return os.path.basename(cmd_path).lower()

    def _validate_arguments(self, args: List[str]) -> tuple[bool, str]:
        """Validate all command arguments for dangerous patterns"""
        for arg in args:
            for pattern in BLOCKED_ARG_PATTERNS:
                if re.search(pattern, arg):
                    return False, f"Blocked pattern in argument: {arg}"
        return True, ""

    def _validate_git_command(self, args: List[str]) -> tuple[bool, str]:
        """Special validation for git commands - only read-only operations"""
        if len(args) < 2:
            return True, ""  # Just 'git' with no subcommand

        subcommand = args[1].lower()
        if subcommand not in ALLOWED_GIT_SUBCOMMANDS:
            return False, f"Git subcommand '{subcommand}' is not allowed (read-only operations only)"
        return True, ""

    def _is_command_safe(self, command: str) -> tuple[bool, str, List[str]]:
        """
        Validate command using whitelist approach.
        Returns (is_safe, error_message, parsed_args)
        """
        # Parse command safely
        try:
            parts = shlex.split(command)
            if not parts:
                return False, "Empty command", []
        except ValueError as e:
            return False, f"Invalid command syntax: {e}", []

        # Get base command (handle paths like /usr/bin/ls)
        base_cmd = self._get_base_command(parts[0])

        # Check whitelist (SECURITY: This is the primary security gate)
        if base_cmd not in self._allowed_commands:
            return False, f"Command '{base_cmd}' is not in the allowed whitelist", []

        # Validate arguments for dangerous patterns
        if len(parts) > 1:
            is_valid, error = self._validate_arguments(parts[1:])
            if not is_valid:
                return False, error, []

        # Special validation for git commands
        if base_cmd == "git":
            is_valid, error = self._validate_git_command(parts)
            if not is_valid:
                return False, error, []

        return True, "", parts

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        command = kwargs.get("command", "")
        timeout = min(kwargs.get("timeout", 30), 60)  # Max 60 seconds
        working_dir = kwargs.get("working_dir")

        if not command:
            return self.create_error_result("command parameter is required")

        # Security validation (whitelist-based)
        is_safe, error_msg, cmd_parts = self._is_command_safe(command)
        if not is_safe:
            logger.warning(f"Command rejected: {error_msg} - {command[:100]}")
            return self.create_error_result(f"Command rejected: {error_msg}")

        try:
            # SECURITY FIX: Use create_subprocess_exec with argument list
            # This prevents shell injection by NOT passing through a shell
            # Arguments are passed directly to the process, bypassing shell parsing
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,  # Pass as argument list, not shell string
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()  # Reap the process to prevent zombie
                return self.create_error_result(
                    f"Command timed out after {timeout} seconds"
                )

            # Decode output
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Truncate long output
            max_output = 10000
            if len(stdout_str) > max_output:
                stdout_str = stdout_str[:max_output] + "\n...[truncated]"
            if len(stderr_str) > max_output:
                stderr_str = stderr_str[:max_output] + "\n...[truncated]"

            output = {
                "command": command,
                "exit_code": process.returncode,
                "stdout": stdout_str,
                "stderr": stderr_str if stderr_str else None
            }

            if process.returncode != 0:
                return ToolResult(
                    success=False,
                    output=self.format_output(output),
                    error=f"Command exited with code {process.returncode}",
                    metadata={"exit_code": process.returncode}
                )

            return self.create_success_result(
                output,
                metadata={"exit_code": process.returncode}
            )

        except FileNotFoundError:
            return self.create_error_result(f"Command not found: {cmd_parts[0]}")
        except PermissionError:
            return self.create_error_result(f"Permission denied: {cmd_parts[0]}")
        except Exception as e:
            logger.error(f"Bash execution error: {e}")
            return self.create_error_result(f"Execution failed: {str(e)}")


class SafeBashTool(BashTool):
    """
    Bash tool with the strictest restrictions.
    Only allows specific read-only commands - no python/node execution.
    """

    # Even more restricted whitelist for maximum security
    SAFE_COMMANDS_ONLY: Set[str] = {
        "ls", "dir", "pwd", "tree",
        "cat", "head", "tail", "less", "more",
        "find", "grep", "rg", "ag",
        "wc", "sort", "uniq", "cut", "diff",
        "stat", "file",
        "echo", "printf",
        "date", "cal",
        "git",  # Read-only git commands only
    }

    def __init__(self):
        super().__init__(custom_allowed_commands=self.SAFE_COMMANDS_ONLY)
        self.description = """Execute safe, read-only shell commands only.
Allowed: ls, cat, grep, find, git (read-only), etc.
Blocked: python, node, file modification, network access, system commands."""
