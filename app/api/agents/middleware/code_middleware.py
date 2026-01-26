"""
Code Middleware and Tools for Deep Agents
Code (코드 생성/분석) 기능을 Deep Agents에서 사용할 수 있도록 제공

코드 생성, 코드 리뷰, 디버깅, 테스트 작성 등의 기능 제공
"""
import os
import logging
import subprocess
import tempfile
from typing import List, Optional, Any, Callable

logger = logging.getLogger(__name__)

# 의존성 체크
try:
    from langchain_core.tools import tool
    LANGCHAIN_TOOLS_AVAILABLE = True
except ImportError:
    LANGCHAIN_TOOLS_AVAILABLE = False


# 안전한 명령어 화이트리스트
SAFE_COMMANDS = {
    "python": ["python", "python3"],
    "node": ["node", "npm"],
    "java": ["java", "javac"],
    "go": ["go"],
    "rust": ["cargo", "rustc"],
}

# 위험한 패턴
DANGEROUS_PATTERNS = [
    "rm -rf", "del /f", "format", "mkfs",
    "dd if=", ":(){", "fork", "wget", "curl",
    "chmod 777", "sudo", "su -", "passwd",
]


class CodeToolsProvider:
    """
    Code 도구 제공자

    코드 실행, 분석, 테스트 등의 도구를 Deep Agent에 전달합니다.
    """

    def __init__(self):
        self._safe_mode = True  # 기본적으로 안전 모드

    def _is_safe_command(self, command: str) -> bool:
        """명령어 안전성 검사"""
        command_lower = command.lower()

        # 위험한 패턴 체크
        for pattern in DANGEROUS_PATTERNS:
            if pattern in command_lower:
                return False

        return True

    def _execute_code(self, code: str, language: str = "python") -> str:
        """코드 실행 (샌드박스 환경)"""
        if not self._safe_mode:
            return "Code execution disabled for security"

        try:
            # 임시 파일에 코드 저장
            extensions = {
                "python": ".py",
                "javascript": ".js",
                "typescript": ".ts",
                "java": ".java",
                "go": ".go",
                "rust": ".rs",
            }

            ext = extensions.get(language.lower(), ".txt")

            with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False) as f:
                f.write(code)
                temp_path = f.name

            try:
                # 언어별 실행 명령
                commands = {
                    "python": ["python", temp_path],
                    "javascript": ["node", temp_path],
                    "go": ["go", "run", temp_path],
                }

                cmd = commands.get(language.lower())
                if not cmd:
                    return f"Unsupported language: {language}"

                # 타임아웃 설정 (환경변수에서 로드)
                try:
                    from ...core.config import get_api_settings
                    timeout = get_api_settings().CODE_EXECUTION_TIMEOUT
                except Exception:
                    timeout = 30  # Fallback

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tempfile.gettempdir()
                )

                output = result.stdout
                if result.stderr:
                    output += f"\n[STDERR]\n{result.stderr}"

                return output if output else "(No output)"

            finally:
                # 임시 파일 삭제
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass  # Ignore file deletion errors (file may already be deleted)

        except subprocess.TimeoutExpired:
            return "Execution timed out (30 seconds limit)"
        except Exception as e:
            logger.error(f"[CodeTools] Execution error: {e}")
            return f"Execution error: {str(e)}"

    def _search_code_examples(self, query: str, top_k: int = 5) -> str:
        """Knowledge base에서 코드 예제 검색 (동기)"""
        try:
            from ..tools import VectorSearchTool
            from ..types import AgentContext

            vector_tool = VectorSearchTool()
            context = AgentContext()

            # "code example" 키워드 추가하여 검색
            enhanced_query = f"code example {query}"

            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            vector_tool.execute(context, query=enhanced_query, top_k=top_k)
                        )
                        result = future.result()
                else:
                    result = loop.run_until_complete(
                        vector_tool.execute(context, query=enhanced_query, top_k=top_k)
                    )
            except RuntimeError:
                result = asyncio.run(
                    vector_tool.execute(context, query=enhanced_query, top_k=top_k)
                )

            if result.get("success"):
                output = result.get("output", {})
                if isinstance(output, dict):
                    results = output.get("results", [])
                    if results:
                        formatted = []
                        for r in results[:top_k]:
                            formatted.append(f"- {r.get('content', '')[:500]}")
                        return "\n".join(formatted)
                return str(output)
            return "No code examples found"

        except Exception as e:
            logger.error(f"[CodeTools] Search error: {e}")
            return f"Search error: {str(e)}"

    def _run_shell_command(self, command: str) -> str:
        """안전한 쉘 명령 실행"""
        if not self._is_safe_command(command):
            return f"Command blocked for security: {command}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tempfile.gettempdir()
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]\n{result.stderr}"

            return output if output else "(No output)"

        except subprocess.TimeoutExpired:
            return "Command timed out (30 seconds limit)"
        except Exception as e:
            return f"Command error: {str(e)}"

    def get_tools(self) -> List[Callable]:
        """Code 도구 목록 반환"""
        if not LANGCHAIN_TOOLS_AVAILABLE:
            logger.warning("[CodeTools] langchain_core.tools not available")
            return []

        provider = self

        @tool
        def execute_code(code: str, language: str = "python") -> str:
            """Execute code in a sandboxed environment.

            Use this tool to run code snippets and verify they work correctly.
            Supported languages: python, javascript, go

            Args:
                code: The code to execute
                language: Programming language (python, javascript, go)

            Returns:
                Execution output or error message
            """
            try:
                result = provider._execute_code(code, language)
                return f"=== Execution Result ===\n{result}"
            except Exception as e:
                logger.error(f"[CodeTools] execute_code error: {e}")
                return f"Execution error: {str(e)}"

        @tool
        def search_code_examples(query: str, language: str = "", top_k: int = 5) -> str:
            """Search the knowledge base for code examples and documentation.

            Use this to find relevant code snippets, API documentation, or examples.

            Args:
                query: Search query (e.g., "python file handling", "API authentication")
                language: Optional language filter
                top_k: Number of results to return (default: 5)

            Returns:
                Relevant code examples and documentation from knowledge base
            """
            try:
                search_query = f"{language} {query}" if language else query
                result = provider._search_code_examples(search_query, top_k)
                return result
            except Exception as e:
                logger.error(f"[CodeTools] search error: {e}")
                return f"Search error: {str(e)}"

        @tool
        def run_shell_command(command: str) -> str:
            """Run a safe shell command.

            This tool has security restrictions and only allows safe commands.
            Dangerous commands like rm, del, format, sudo, etc. are blocked.

            Args:
                command: Shell command to execute

            Returns:
                Command output or error message
            """
            try:
                result = provider._run_shell_command(command)
                return f"=== Command Output ===\n{result}"
            except Exception as e:
                logger.error(f"[CodeTools] shell command error: {e}")
                return f"Command error: {str(e)}"

        return [execute_code, search_code_examples, run_shell_command]


def get_code_tools() -> List[Callable]:
    """
    Code 도구 목록 반환 (간편 함수)

    Returns:
        List of Code tools for use with create_deep_agent
    """
    provider = CodeToolsProvider()
    return provider.get_tools()


def _load_code_system_prompt() -> str:
    """Load Code system prompt from external file."""
    from pathlib import Path
    prompt_file = Path(__file__).parent.parent / "prompts" / "middleware" / "code_system.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    # Fallback prompt
    return """## Code Generation and Analysis Guidelines
Write clean code, test before submit, follow best practices."""


# Code 시스템 프롬프트
CODE_SYSTEM_PROMPT = _load_code_system_prompt()
