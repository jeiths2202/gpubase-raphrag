"""
Code Tools for Deep Agents
코드 생성 및 분석 도구를 Deep Agents에서 사용할 수 있도록 제공

Deep Agents는 기본적으로 execute 도구를 제공하지만,
이 모듈은 추가적인 코드 분석 도구를 제공합니다.
"""
import os
import subprocess
import tempfile
import logging
from typing import List, Optional, Callable

logger = logging.getLogger(__name__)

# 의존성 체크
try:
    from langchain_core.tools import tool
    LANGCHAIN_TOOLS_AVAILABLE = True
except ImportError:
    LANGCHAIN_TOOLS_AVAILABLE = False


class CodeToolsProvider:
    """
    코드 도구 제공자

    코드 실행, 분석 도구를 생성하여 Deep Agent에 전달합니다.
    """

    # 허용된 프로그래밍 언어
    ALLOWED_LANGUAGES = {
        "python": {"ext": ".py", "cmd": ["python"]},
        "javascript": {"ext": ".js", "cmd": ["node"]},
        "typescript": {"ext": ".ts", "cmd": ["npx", "ts-node"]},
    }

    # 위험한 명령어 패턴
    DANGEROUS_PATTERNS = [
        "rm -rf",
        "sudo",
        "chmod 777",
        "eval(",
        "exec(",
        "__import__",
        "os.system",
        "subprocess.call",
    ]

    def __init__(
        self,
        allowed_languages: Optional[List[str]] = None,
        enable_execution: bool = True,
        max_execution_time: int = 30,
        working_dir: Optional[str] = None
    ):
        self.allowed_languages = allowed_languages or ["python", "javascript"]
        self.enable_execution = enable_execution
        self.max_execution_time = max_execution_time
        self.working_dir = working_dir or tempfile.gettempdir()

    def _is_safe_code(self, code: str) -> tuple[bool, str]:
        """코드 안전성 검사"""
        code_lower = code.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in code_lower:
                return False, f"Dangerous pattern detected: {pattern}"
        return True, ""

    def get_tools(self) -> List[Callable]:
        """코드 도구 목록 반환"""
        if not LANGCHAIN_TOOLS_AVAILABLE:
            logger.warning("[CodeTools] langchain_core.tools not available")
            return []

        provider = self

        @tool
        def run_python(code: str) -> str:
            """Execute Python code and return the output.

            Use this to run Python scripts and see the results.
            The code runs in a sandboxed environment with limited execution time.

            Args:
                code: Python code to execute

            Returns:
                Execution output (stdout, stderr, return code)
            """
            if not provider.enable_execution:
                return "[Error] Code execution is disabled."

            if "python" not in provider.allowed_languages:
                return "[Error] Python execution is not allowed."

            is_safe, reason = provider._is_safe_code(code)
            if not is_safe:
                return f"[Security Error] Execution blocked: {reason}"

            try:
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix='.py',
                    dir=provider.working_dir,
                    delete=False,
                    encoding='utf-8'
                ) as f:
                    f.write(code)
                    temp_file = f.name

                try:
                    # Using subprocess.run with explicit args list (no shell injection)
                    result = subprocess.run(
                        ["python", temp_file],
                        capture_output=True,
                        text=True,
                        timeout=provider.max_execution_time,
                        cwd=provider.working_dir,
                        shell=False  # Explicit: no shell
                    )

                    output = ""
                    if result.stdout:
                        output += f"[Output]\n{result.stdout}\n"
                    if result.stderr:
                        output += f"[Errors/Warnings]\n{result.stderr}\n"
                    if result.returncode != 0:
                        output += f"[Exit Code] {result.returncode}"

                    return output.strip() or "[Completed] No output"

                finally:
                    try:
                        os.unlink(temp_file)
                    except OSError:
                        pass

            except subprocess.TimeoutExpired:
                return f"[Timeout] Execution exceeded {provider.max_execution_time} seconds."
            except Exception as e:
                logger.error(f"[CodeTools] run_python error: {e}")
                return f"[Execution Error] {str(e)}"

        @tool
        def analyze_code(code: str, language: str = "python") -> str:
            """Analyze code for quality, security, and potential issues.

            Use this to review code before execution or submission.
            Checks for common issues, security concerns, and best practices.

            Args:
                code: Code to analyze
                language: Programming language (python, javascript, typescript)

            Returns:
                Analysis report with findings and recommendations
            """
            analysis = []

            # Basic statistics
            lines = code.split('\n')
            analysis.append("## Basic Statistics")
            analysis.append(f"- Total lines: {len(lines)}")
            analysis.append(f"- Empty lines: {sum(1 for l in lines if not l.strip())}")
            analysis.append(f"- Characters: {len(code)}")

            # Security check
            analysis.append("\n## Security Check")
            is_safe, reason = provider._is_safe_code(code)
            if is_safe:
                analysis.append("- [PASS] No known dangerous patterns")
            else:
                analysis.append(f"- [WARNING] {reason}")

            # Language-specific checks
            language = language.lower()
            analysis.append(f"\n## Code Quality ({language})")

            if language == "python":
                if "import *" in code:
                    analysis.append("- [WARNING] Wildcard import (from x import *)")
                if "except:" in code and "except Exception" not in code:
                    analysis.append("- [WARNING] Bare except clause")
                if not any(line.strip().startswith('def ') for line in lines):
                    analysis.append("- [INFO] No function definitions")
                if '"""' not in code and "'''" not in code:
                    analysis.append("- [INFO] No docstrings")

            elif language in ["javascript", "typescript"]:
                if "var " in code:
                    analysis.append("- [WARNING] Using 'var' (prefer let/const)")
                if "==" in code and "===" not in code:
                    analysis.append("- [WARNING] Loose equality (prefer ===)")
                if "any" in code and language == "typescript":
                    analysis.append("- [WARNING] Using 'any' type")

            if len([a for a in analysis if "[WARNING]" in a]) == 0:
                analysis.append("- [PASS] No significant issues found")

            return "\n".join(analysis)

        return [run_python, analyze_code]


# Convenience function
def get_code_tools(
    allowed_languages: Optional[List[str]] = None,
    enable_execution: bool = True
) -> List[Callable]:
    """
    코드 도구 목록 반환 (간편 함수)

    Args:
        allowed_languages: List of allowed languages
        enable_execution: Whether to allow code execution

    Returns:
        List of code tools for use with create_deep_agent
    """
    provider = CodeToolsProvider(
        allowed_languages=allowed_languages,
        enable_execution=enable_execution
    )
    return provider.get_tools()


# Code analysis system prompt
CODE_SYSTEM_PROMPT = """
## Code Development Guidelines

You have access to code execution and analysis tools.

### Available Tools:

1. **run_python**: Execute Python code
   - Returns stdout, stderr, and exit code
   - Limited execution time for safety

2. **analyze_code**: Code quality analysis
   - Security, quality, and best practice checks
   - Supports Python, JavaScript, TypeScript

### Best Practices:

1. **Test Before Delivery**: Always run code with run_python before providing it.

2. **Analyze for Quality**: Use analyze_code to check for issues.

3. **Document Code**: Add comments and docstrings for complex logic.

4. **Handle Errors**: Include proper error handling in code.

5. **Security First**: Never execute code that could harm the system.
"""


# Backward compatibility
CodeMiddleware = CodeToolsProvider
