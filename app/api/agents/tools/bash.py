"""
Bash Tool
Executes shell commands with restrictions.
"""
from typing import Dict, Any, Optional, List
import logging
import asyncio
import shlex
import re

from .base import BaseTool
from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


# Dangerous commands that are always blocked
BLOCKED_COMMANDS = {
    "rm", "rmdir", "del", "format", "mkfs",
    "dd", "shutdown", "reboot", "halt", "poweroff",
    "kill", "killall", "pkill",
    "chmod", "chown", "chgrp",
    "sudo", "su", "doas",
    "passwd", "useradd", "userdel", "usermod",
    "mount", "umount",
    "fdisk", "parted",
    "systemctl", "service",
    "iptables", "firewall-cmd",
    "curl", "wget",  # Network access restricted separately
}

# Patterns that indicate dangerous operations
DANGEROUS_PATTERNS = [
    r">\s*/dev/",  # Writing to devices
    r">\s*/etc/",  # Writing to system config
    r">\s*/bin/",  # Writing to binaries
    r">\s*/usr/",  # Writing to system
    r"\|.*bash",   # Piping to bash
    r"\|.*sh",     # Piping to shell
    r"&{2,}",      # Background execution chains
    r";\s*rm\s",   # rm after semicolon
    r"\$\(",       # Command substitution (could hide commands)
    r"`",          # Backtick command substitution
]


class BashTool(BaseTool):
    """
    Tool for executing shell commands.
    Restricted to safe operations only.
    """

    def __init__(self, allowed_commands: Optional[List[str]] = None):
        super().__init__(
            name="bash",
            description="""Execute a shell command.
Restricted to safe, read-only operations like:
- Listing files (ls, dir)
- Reading file info (stat, file)
- Searching files (find, grep)
- Code operations (python, node for testing)

Dangerous operations like rm, sudo, and system modifications are blocked."""
        )
        # If specified, only these commands are allowed
        self.allowed_commands = allowed_commands

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Command timeout in seconds",
                    "default": 30
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for the command"
                }
            },
            "required": ["command"]
        }

    def _is_command_safe(self, command: str) -> tuple[bool, str]:
        """Check if command is safe to execute"""
        # Parse command to get base command
        try:
            parts = shlex.split(command)
            if not parts:
                return False, "Empty command"
            base_cmd = parts[0].lower()
        except ValueError:
            return False, "Invalid command syntax"

        # Check if base command is blocked
        if base_cmd in BLOCKED_COMMANDS:
            return False, f"Command '{base_cmd}' is not allowed"

        # Check for dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return False, f"Dangerous pattern detected in command"

        # If allowed_commands is specified, check whitelist
        if self.allowed_commands is not None:
            if base_cmd not in self.allowed_commands:
                return False, f"Command '{base_cmd}' is not in allowed list"

        return True, ""

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

        # Security check
        is_safe, error_msg = self._is_command_safe(command)
        if not is_safe:
            return self.create_error_result(f"Command rejected: {error_msg}")

        try:
            # Execute command
            process = await asyncio.create_subprocess_shell(
                command,
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

        except Exception as e:
            logger.error(f"Bash execution error: {e}")
            return self.create_error_result(f"Execution failed: {str(e)}")


class SafeBashTool(BashTool):
    """
    Bash tool with stricter restrictions.
    Only allows specific read-only commands.
    """

    def __init__(self):
        super().__init__(allowed_commands=[
            "ls", "dir", "pwd", "cd",
            "cat", "head", "tail", "less", "more",
            "find", "grep", "rg", "ag",
            "wc", "sort", "uniq",
            "stat", "file", "type",
            "echo", "printf",
            "date", "cal",
            "python", "python3", "node", "npm", "npx",
            "git", "diff",
        ])
        self.description = """Execute safe, read-only shell commands.
Only allows: ls, cat, grep, find, git status, python (for testing), etc.
No file modification, network access, or system commands."""
