"""
Artifact Detector
Detects and extracts artifacts (code blocks, long text) from LLM responses.

Features:
- Detects fenced code blocks with language tags
- Detects long text blocks (20+ lines)
- Generates unique artifact IDs
- Creates artifact chunks for streaming
"""
import re
import uuid
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class DetectedArtifact:
    """Represents a detected artifact from content"""
    id: str
    type: str  # code, text, markdown, etc.
    title: str
    content: str
    language: Optional[str] = None
    line_count: int = 0
    char_count: int = 0


class ArtifactDetector:
    """
    Detects artifacts in LLM response content.

    Rules:
    - All fenced code blocks (```) become code artifacts
    - Text blocks with 20+ lines become text artifacts
    - Explicit <artifact> tags are supported (future)
    """

    # Regex for fenced code blocks with optional language
    CODE_BLOCK_PATTERN = re.compile(
        r'```(\w+)?\s*\n(.*?)```',
        re.DOTALL
    )

    # Minimum lines for long text artifact
    MIN_TEXT_LINES = 20

    # Maximum artifact size (1MB)
    MAX_ARTIFACT_SIZE = 1024 * 1024

    # Language mapping for common aliases
    LANGUAGE_ALIASES = {
        'py': 'python',
        'js': 'javascript',
        'ts': 'typescript',
        'rb': 'ruby',
        'sh': 'bash',
        'shell': 'bash',
        'zsh': 'bash',
        'yml': 'yaml',
        'dockerfile': 'docker',
        'bat': 'batch',
        'cmd': 'batch',
        'ps1': 'powershell',
        'psm1': 'powershell',
        'md': 'markdown',
    }

    # Supported languages for syntax highlighting
    SUPPORTED_LANGUAGES = {
        'python', 'javascript', 'typescript', 'java', 'go', 'rust',
        'c', 'cpp', 'csharp', 'ruby', 'php', 'swift', 'kotlin',
        'sql', 'bash', 'powershell', 'batch',
        'html', 'css', 'scss', 'less',
        'json', 'yaml', 'xml', 'toml',
        'markdown', 'text', 'plaintext',
        'docker', 'dockerfile',
        'diff', 'patch',
    }

    @classmethod
    def detect(cls, content: str) -> List[DetectedArtifact]:
        """
        Detect all artifacts in content.

        Args:
            content: The LLM response content to analyze

        Returns:
            List of DetectedArtifact objects
        """
        if not content or len(content) > cls.MAX_ARTIFACT_SIZE:
            return []

        artifacts: List[DetectedArtifact] = []

        # 1. Detect code blocks
        code_artifacts = cls._detect_code_blocks(content)
        artifacts.extend(code_artifacts)

        # 2. Detect long text (after removing code blocks)
        text_without_code = cls.CODE_BLOCK_PATTERN.sub('', content)
        text_artifacts = cls._detect_long_text(text_without_code)
        artifacts.extend(text_artifacts)

        return artifacts

    @classmethod
    def _detect_code_blocks(cls, content: str) -> List[DetectedArtifact]:
        """Detect fenced code blocks"""
        artifacts = []

        for match in cls.CODE_BLOCK_PATTERN.finditer(content):
            language_raw = match.group(1) or 'text'
            code_content = match.group(2).strip()

            if not code_content:
                continue

            # Normalize language
            language = cls._normalize_language(language_raw)

            # Generate title
            title = cls._generate_code_title(code_content, language)

            # Calculate metrics
            line_count = code_content.count('\n') + 1
            char_count = len(code_content)

            artifacts.append(DetectedArtifact(
                id=str(uuid.uuid4()),
                type='code',
                title=title,
                content=code_content,
                language=language,
                line_count=line_count,
                char_count=char_count,
            ))

        return artifacts

    @classmethod
    def _detect_long_text(cls, content: str) -> List[DetectedArtifact]:
        """Detect long text blocks (20+ lines)"""
        artifacts = []

        # Split by double newlines to find separate blocks
        blocks = re.split(r'\n\s*\n', content)

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            line_count = block.count('\n') + 1

            if line_count >= cls.MIN_TEXT_LINES:
                # Generate title from first line
                title = cls._generate_text_title(block)

                artifacts.append(DetectedArtifact(
                    id=str(uuid.uuid4()),
                    type='text',
                    title=title,
                    content=block,
                    language='text',
                    line_count=line_count,
                    char_count=len(block),
                ))

        return artifacts

    @classmethod
    def _normalize_language(cls, language: str) -> str:
        """Normalize language identifier"""
        lang_lower = language.lower().strip()

        # Apply alias mapping
        if lang_lower in cls.LANGUAGE_ALIASES:
            lang_lower = cls.LANGUAGE_ALIASES[lang_lower]

        # Check if supported
        if lang_lower in cls.SUPPORTED_LANGUAGES:
            return lang_lower

        return 'text'

    @classmethod
    def _generate_code_title(cls, code: str, language: str) -> str:
        """Generate a descriptive title for code artifact"""
        first_lines = code.split('\n')[:10]

        # Try to extract meaningful name from code
        for line in first_lines:
            line = line.strip()

            # Python function/class
            if language == 'python':
                if match := re.search(r'^(?:async\s+)?def\s+(\w+)', line):
                    return f"{match.group(1)}() - Python"
                if match := re.search(r'^class\s+(\w+)', line):
                    return f"{match.group(1)} - Python"

            # JavaScript/TypeScript function/class
            elif language in ('javascript', 'typescript'):
                if match := re.search(r'(?:function|const|let|var)\s+(\w+)', line):
                    return f"{match.group(1)} - {language.title()}"
                if match := re.search(r'^(?:export\s+)?class\s+(\w+)', line):
                    return f"{match.group(1)} - {language.title()}"

            # SQL
            elif language == 'sql':
                if match := re.search(r'^(?:CREATE|ALTER|SELECT)\s+(?:TABLE|VIEW|FUNCTION|PROCEDURE)?\s*(\w+)?', line, re.IGNORECASE):
                    return f"SQL: {match.group(0)[:30]}"

            # Shell script
            elif language in ('bash', 'sh'):
                if line.startswith('#!'):
                    continue
                if line.startswith('#'):
                    comment = line.lstrip('#').strip()[:30]
                    if comment:
                        return f"Script: {comment}"

        # Default title
        return f"Code ({language})"

    @classmethod
    def _generate_text_title(cls, text: str) -> str:
        """Generate title from text content"""
        first_line = text.split('\n')[0].strip()

        # Remove markdown headers
        first_line = re.sub(r'^#+\s*', '', first_line)

        if first_line:
            if len(first_line) > 50:
                return first_line[:50] + "..."
            return first_line

        return "Text Document"

    @classmethod
    def has_code_blocks(cls, content: str) -> bool:
        """Quick check if content has any code blocks"""
        return bool(cls.CODE_BLOCK_PATTERN.search(content))

    @classmethod
    def count_lines(cls, content: str) -> int:
        """Count total lines in content"""
        return content.count('\n') + 1 if content else 0


# Convenience function
def detect_artifacts(content: str) -> List[DetectedArtifact]:
    """Detect artifacts in content"""
    return ArtifactDetector.detect(content)
