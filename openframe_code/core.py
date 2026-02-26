#!/usr/bin/env python3
"""OpenFrame Code - CLI coding assistant powered by local LLM.

Interactive CLI with OpenFrame 7 codebase expertise.
Connects to vLLM via OpenAI-compatible API.

Usage:
    ofcode                              # General mode
    ofcode --openframe                  # OpenFrame expert mode
    ofcode --server http://host:port/v1 # Custom server
"""

# ═══════════════════════════════════════════════════════════════
# Section 1: Imports & Configuration
# ═══════════════════════════════════════════════════════════════

import argparse
import fnmatch
import glob as glob_module
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
import uuid
from pathlib import Path

from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.theme import Theme
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import HTML

# Fix Windows encoding for Unicode output (Korean, Japanese, etc.)
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_SERVER = "http://192.168.8.11:12810/v1"
DEFAULT_OFCODE_SERVER = "http://192.168.8.11:12820"
DEFAULT_MODEL = None  # auto-detect from server
DEFAULT_CONTEXT_LENGTH = 8192
HISTORY_FILE = os.path.expanduser("~/.local_coder_history")
MAX_OUTPUT_LINES = 200
MAX_AGENT_ITERATIONS = 25
TOKEN_BUFFER = 500  # safety margin for token estimation inaccuracy
MIN_OUTPUT_TOKENS = 256  # minimum tokens reserved for response
RECENT_MESSAGES_TO_KEEP = 4  # keep last N messages when compressing
TOOL_RESULT_TRUNCATE_LINES = 5  # max lines to keep per tool result during compression

SYSTEM_PROMPT = """\
You are a coding assistant with direct access to the user's filesystem and shell.

Available tools: read_file, write_file, edit_file, bash, grep_search, glob_search, list_directory

Guidelines:
- Always read a file before editing it to understand context.
- Use edit_file for targeted changes, write_file for new files or complete rewrites.
- Be concise and focused on the task.
- Explain what shell commands do before running them.
- Working directory: {cwd}
"""

OPENFRAME_SYSTEM_PROMPT = """\
You are an OpenFrame 7 codebase expert assistant with filesystem and code analysis tools.

OpenFrame Architecture (6 layers, top to bottom):
1. Entry: COBOL programs, JCL scripts, CICS transactions, IMS DLI calls, SQL, TSO commands
2. Parser: JCL parser(Yacc/Lex), COBOL85 parser(cob85p), MVS/MSP/VOS3/XSP dialect handlers
3. Server/Runtime: cmsvr(connection), dmsvr(data), sasvr(security), uisvr(UI), smlog, oscmgr, osiofmgr
4. Data Access: dsalc(dataset alloc), dsio(dataset I/O), dbio(database I/O), mqnio(MQ I/O), volm, sms, VSAM/SAM/tsam
5. Common Services: memm(memory), ofcom(logging/config), saf(security auth), spinlock, ttree, smf(monitoring)
6. DB Backend: tdbconnsw(driver switch) -> PostgreSQL(ODBC), Tibero(ODBC/OCI/native), Oracle(OCI)

Modules:
- base/ (27 subdirs): Core runtime - include(98 headers), parser, ds(dbio/dsio/dsalc), server, fh(file handlers), common, tdbconnsw
- batch/ (19 subdirs): Batch processing - tjes(scheduler), tso(emulation), output management, JCL tools
- ims/ (17 subdirs): IMS hierarchical DB - hidb(engine), dli(interface), dbdc(CICS link), imsdc
- osc/ (19 subdirs): CICS transaction processing - 75+ CICS libs, gw(3270/webservice), oscsvr
- osi/ (12 subdirs): System integration - 40+ OSI modules, message queues, events

Key headers: dbio.h, dsio.h, dsalc.h, tdbconn.h, tdcb.h, ofcom.h, saf.h, memm.h, jclcom.h, cob85.h
Data flow: User input -> Parser(AST) -> batch/osc/ims -> ds(dsalc->dsio->dbio) -> tdbconnsw -> DB

Available tools: read_file, write_file, edit_file, bash, grep_search, glob_search, list_directory,
  search_of7, get_module_info, get_function_def, get_header_api, get_architecture, find_callers,
  search_webdoc

Use search_of7/get_module_info/get_function_def/get_header_api to explore the codebase efficiently.
Use search_webdoc(query, product) to search OpenFrame product web documentation (manuals, guides).
Working directory: {cwd}

CRITICAL RULE - MUST Use Tools Before Answering:
- When the user asks about ANY product, technology, or mainframe topic, you MUST call search_webdoc FIRST to retrieve actual documentation before responding.
- Indexed products include: OFASM, OFCOBOL, OSC, IBM (HLASM, z/OS, MVS), Fujitsu AIM (XSP, MSP), Hitachi VOS3, and any OpenFrame component.
- This means questions about HLASM, assembler, MACRO, COBOL, CICS, JCL, mainframe, z/OS, etc. ALL require search_webdoc FIRST.
- When the user asks about source code, functions, modules, or architecture, you MUST call the appropriate code search tool (search_of7, get_function_def, get_module_info, etc.) FIRST.
- NEVER answer from your own knowledge alone. Always ground your response in tool results.
- If the user's question asks "tell me about", "explain", "what is", "how to", or similar, you MUST search first, then summarize the search results.
- Responding without calling a tool first when a relevant tool exists is a CRITICAL ERROR that produces hallucinations.

CRITICAL RULE - Source Code Protection:
- NEVER display raw source code to the user. Do NOT output file contents, code snippets, or function bodies.
- You may read files internally using tools for your own analysis, but ONLY present summaries, explanations, and structural descriptions.
- Allowed outputs: directory trees, file lists, module structures, function signatures (name + parameters only), architecture diagrams, and natural language explanations.
- If the user asks to "show the code" or "show the source", explain the code's purpose and structure in natural language instead.
"""

custom_theme = Theme({
    "tool.name": "bold cyan",
    "tool.result": "dim",
    "confirm": "bold yellow",
    "error": "bold red",
    "success": "bold green",
    "thinking": "dim italic",
})

console = Console(theme=custom_theme)


# ═══════════════════════════════════════════════════════════════
# Section 1.5: Token Estimation
# ═══════════════════════════════════════════════════════════════

def estimate_tokens(text):
    """Conservative token estimate to prevent overflow.
    Uses chars/2.0 (overestimates) for safety with mixed CJK/English/JSON/code."""
    if not text:
        return 0
    return int(len(text) / 2.0) + 1


# Token correction: learned from vLLM actual usage vs estimated
_token_correction_factor = 1.0  # multiplied with estimate; >1 = underestimated, <1 = overestimated


def update_token_correction(estimated, actual):
    """Update correction factor based on actual vLLM prompt_tokens.
    Uses exponential moving average to smooth corrections."""
    global _token_correction_factor
    if estimated <= 0 or actual <= 0:
        return
    ratio = actual / estimated
    # EMA with alpha=0.3 (blend 30% new, 70% old)
    _token_correction_factor = 0.7 * _token_correction_factor + 0.3 * ratio


def estimate_messages_tokens(messages, tools=None):
    """Estimate total tokens for a messages array + tool definitions.
    Applies learned correction factor from vLLM actual usage."""
    total = 0
    for msg in messages:
        # Role overhead (~4 tokens)
        total += 4
        if msg.get("content"):
            total += estimate_tokens(msg["content"])
        # Tool calls in assistant messages
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                total += estimate_tokens(tc.get("function", {}).get("name", ""))
                total += estimate_tokens(tc.get("function", {}).get("arguments", ""))
                total += 10  # overhead per tool call
    # Tool definitions overhead
    if tools:
        total += estimate_tokens(json.dumps(tools))
    # Apply correction factor
    total = int(total * _token_correction_factor)
    return total


# ═══════════════════════════════════════════════════════════════
# Section 2: Tool Definitions (OpenAI Function Calling Schema)
# ═══════════════════════════════════════════════════════════════

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "offset": {"type": "integer", "description": "Start line (1-based)"},
                    "limit": {"type": "integer", "description": "Max lines"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace unique string in file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "old_string": {"type": "string", "description": "String to find (must be unique)"},
                    "new_string": {"type": "string", "description": "Replacement"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run"},
                    "timeout": {"type": "integer", "description": "Timeout seconds (default:30)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Regex search in files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern"},
                    "path": {"type": "string", "description": "Search path"},
                    "include": {"type": "string", "description": "File glob filter (e.g. *.py)"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_search",
            "description": "Find files by glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g. **/*.py)"},
                    "path": {"type": "string", "description": "Base directory"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List directory contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path"},
                },
                "required": [],
            },
        },
    },
]

OPENFRAME_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_of7",
            "description": "Search of7 C/H files by regex.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Regex pattern"},
                    "module": {"type": "string", "description": "Filter: base/batch/ims/osc/osi"},
                    "file_type": {"type": "string", "description": "c, h, or both"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_module_info",
            "description": "Get of7 module info (subdirs, files).",
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "e.g. base, base/ds, batch"},
                },
                "required": ["module"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_function_def",
            "description": "Find C function definition with source.",
            "parameters": {
                "type": "object",
                "properties": {
                    "function_name": {"type": "string", "description": "Function name (exact or partial)"},
                },
                "required": ["function_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_header_api",
            "description": "Get header API (functions, structs, defines).",
            "parameters": {
                "type": "object",
                "properties": {
                    "header_name": {"type": "string", "description": "e.g. dbio.h, dsio.h"},
                },
                "required": ["header_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_architecture",
            "description": "Show of7 6-layer architecture diagram.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_callers",
            "description": "Find callers of a function in of7.",
            "parameters": {
                "type": "object",
                "properties": {
                    "function_name": {"type": "string", "description": "Function name"},
                    "module": {"type": "string", "description": "Filter: base/batch/ims/osc/osi"},
                },
                "required": ["function_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_webdoc",
            "description": "Search OpenFrame product web documentation (manuals, guides). Returns matching pages with titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g. 'OFASM analyze', 'dataset allocation')"},
                    "product": {"type": "string", "description": "Filter by product: OFASM, OFCOBOL, OSC, etc. (optional)"},
                },
                "required": ["query"],
            },
        },
    },
]

CONFIRM_REQUIRED = {"write_file", "edit_file", "bash"}


# ═══════════════════════════════════════════════════════════════
# Section 3: Tool Implementations
# ═══════════════════════════════════════════════════════════════

def _format_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _truncate(text, max_lines=MAX_OUTPUT_LINES):
    lines = text.split("\n")
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + f"\n\n... (truncated, {len(lines)} total lines)"
    return text


def tool_read_file(path, offset=None, limit=None):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"Error: File not found: {path}"
    if os.path.isdir(path):
        return f"Error: {path} is a directory, not a file. Use list_directory instead."
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error reading file: {e}"

    total = len(lines)
    start = max(0, (offset or 1) - 1)
    end = start + limit if limit else total
    selected = lines[start:end]

    result = []
    for i, line in enumerate(selected, start=start + 1):
        result.append(f"{i:>6}\t{line.rstrip()}")

    output = "\n".join(result)
    return _truncate(output)


def tool_write_file(path, content):
    path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        lines = content.count("\n") + 1
        return f"Successfully wrote {lines} lines to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def tool_edit_file(path, old_string, new_string):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"Error: File not found: {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"Error reading file: {e}"

    count = content.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {path}"
    if count > 1:
        return f"Error: old_string found {count} times in {path}. Must be unique. Provide more surrounding context."

    new_content = content.replace(old_string, new_string, 1)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_content)
        return f"Successfully edited {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def tool_bash(command, timeout=30):
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        if result.returncode != 0:
            output += f"\n[Exit code: {result.returncode}]"
        return _truncate(output) if output else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def tool_grep_search(pattern, path=".", include=""):
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: Invalid regex pattern: {e}"

    search_path = Path(path).expanduser()
    if not search_path.exists():
        return f"Error: Path not found: {path}"

    skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", ".tox", "dist", "build"}
    results = []

    if search_path.is_file():
        files_to_search = [search_path]
    else:
        files_to_search = []
        for root, dirs, filenames in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for fname in filenames:
                if include and not fnmatch.fnmatch(fname, include):
                    continue
                files_to_search.append(Path(root) / fname)
            if len(files_to_search) > 500:
                break

    for fpath in files_to_search:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    if regex.search(line):
                        results.append(f"{fpath}:{lineno}: {line.rstrip()}")
                        if len(results) >= 50:
                            results.append("... (truncated at 50 matches)")
                            return "\n".join(results)
        except (OSError, UnicodeDecodeError):
            continue

    return "\n".join(results) if results else "No matches found."


def tool_glob_search(pattern, path="."):
    search_path = os.path.expanduser(path)
    full_pattern = os.path.join(search_path, pattern)
    try:
        matches = sorted(glob_module.glob(full_pattern, recursive=True))[:50]
    except Exception as e:
        return f"Error: {e}"

    if not matches:
        return "No files matched the pattern."

    result = "\n".join(matches)
    if len(matches) == 50:
        result += "\n... (showing first 50 matches)"
    return result


def tool_list_directory(path="."):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"Error: Directory not found: {path}"
    if not os.path.isdir(path):
        return f"Error: {path} is a file, not a directory."
    try:
        entries = sorted(os.listdir(path))
    except Exception as e:
        return f"Error: {e}"

    result = []
    for entry in entries:
        full = os.path.join(path, entry)
        if os.path.isdir(full):
            result.append(f"  {entry}/")
        else:
            try:
                size = os.path.getsize(full)
                result.append(f"  {entry}  ({_format_size(size)})")
            except OSError:
                result.append(f"  {entry}")

    return "\n".join(result) if result else "(empty directory)"


# ═══════════════════════════════════════════════════════════════
# Section 3.5: OpenFrame Tools - Remote API Client
# ═══════════════════════════════════════════════════════════════

# ofcode-server URL (set during init via --ofcode-server)
_ofcode_server_url = None


def _ofcode_api(endpoint, payload=None):
    """Call ofcode-server REST API. Returns parsed JSON or error string."""
    url = f"{_ofcode_server_url}{endpoint}"
    try:
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.readable() else ""
        return f"Error: API {endpoint} returned {e.code}: {body}"
    except urllib.error.URLError as e:
        return f"Error: Cannot connect to ofcode-server ({_ofcode_server_url}): {e.reason}"
    except Exception as e:
        return f"Error: API call failed: {e}"


def _check_ofcode_server():
    """Check if ofcode-server is reachable and index is loaded."""
    result = _ofcode_api("/health")
    if isinstance(result, str):
        return False, result
    if not result.get("index_loaded"):
        return False, "ofcode-server index not loaded. Call /api/rebuild-index on server."
    return True, result


def tool_search_of7(query, module="", file_type="both"):
    """Search of7 codebase via remote ofcode-server."""
    result = _ofcode_api("/api/search", {"query": query, "module": module, "file_type": file_type, "max_results": 30})
    if isinstance(result, str):
        return result
    entries = result.get("results", [])
    if not entries:
        return "No matches found."
    lines = [f"{r['file']}:{r['line']}: {r['content']}" for r in entries]
    if result.get("truncated"):
        lines.append("... (max results reached)")
    return "\n".join(lines)


def tool_get_module_info(module):
    """Get module info via remote ofcode-server."""
    result = _ofcode_api("/api/module", {"module": module})
    if isinstance(result, str):
        return result
    lines = [f"Module: {result['module']}/"]
    lines.append(f"Description: {result.get('description', 'N/A')}")
    lines.append(f"Files: {result.get('c_files', 0)} .c + {result.get('h_files', 0)} .h = {result.get('total_files', 0)} total")
    subdirs = result.get("subdirs", [])
    subdirs_desc = result.get("subdirs_desc", {})
    lines.append(f"Subdirectories ({len(subdirs)}):")
    for sd in subdirs:
        desc = subdirs_desc.get(sd, "")
        if desc:
            lines.append(f"  {sd}/ - {desc}")
        else:
            lines.append(f"  {sd}/")
    detail = result.get("subdir_detail")
    if detail:
        lines.append(f"\nSubdir detail: {detail['name']}/")
        lines.append(f"  C files: {detail.get('c_files', 0)}, H files: {detail.get('h_files', 0)}")
        if detail.get("subdirs"):
            lines.append(f"  Sub-subdirs: {', '.join(detail['subdirs'])}")
    return "\n".join(lines)


def tool_get_function_def(function_name):
    """Find function definition via remote ofcode-server."""
    result = _ofcode_api("/api/function", {"function_name": function_name})
    if isinstance(result, str):
        return result
    if not result.get("found"):
        matches = result.get("matches", [])
        if matches:
            lines = [result.get("message", f"Multiple matches for '{function_name}':")]
            for m in matches:
                lines.append(f"  {m['name']}  ({m['file']}:{m['line']})")
            return "\n".join(lines)
        return result.get("message", f"Function '{function_name}' not found.")
    code_entries = result.get("code", [])
    code_lines = []
    for c in code_entries:
        marker = ">>>" if c.get("is_def") else "   "
        code_lines.append(f"{marker} {c['num']:>5}: {c['text']}")
    return (
        f"Function: {result['name']}\n"
        f"File: {result['file']}:{result['line']}\n"
        f"Module: {result.get('module', 'unknown')}\n"
        f"---\n"
        + "\n".join(code_lines)
    )


def tool_get_header_api(header_name):
    """Get header API summary via remote ofcode-server."""
    result = _ofcode_api("/api/header", {"header_name": header_name})
    if isinstance(result, str):
        return result
    if not result.get("found"):
        suggestions = result.get("suggestions", [])
        if suggestions:
            return f"Header '{header_name}' not found. Did you mean:\n" + "\n".join(suggestions)
        return f"Header '{header_name}' not found."
    lines = [f"Header: {result['header']}"]
    lines.append(f"Path: {result.get('path', '')}")
    lines.append(f"Module: {result.get('module', 'unknown')}")
    funcs = result.get("functions", [])
    if funcs:
        lines.append(f"\nFunction declarations ({len(funcs)}):")
        for f in funcs[:30]:
            lines.append(f"  {f}()")
    structs = result.get("structs", [])
    if structs:
        lines.append(f"\nStruct/type definitions ({len(structs)}):")
        for s in structs[:20]:
            lines.append(f"  struct {s}")
    defines = result.get("defines", [])
    if defines:
        lines.append(f"\nKey defines ({len(defines)}):")
        for d in defines[:20]:
            lines.append(f"  #define {d}")
    return "\n".join(lines)


def tool_get_architecture():
    """Get architecture diagram via remote ofcode-server."""
    result = _ofcode_api("/api/architecture")
    if isinstance(result, str):
        return result
    return result.get("diagram", "Architecture diagram not available.")


def tool_find_callers(function_name, module=""):
    """Find callers of a function via remote ofcode-server."""
    result = _ofcode_api("/api/callers", {"function_name": function_name, "module": module})
    if isinstance(result, str):
        return result
    entries = result.get("results", [])
    if not entries:
        return f"No callers of '{function_name}' found."
    lines = [f"{r['file']}:{r['line']}: {r['content']}" for r in entries]
    if result.get("truncated"):
        lines.append("... (max results reached)")
    return "\n".join(lines)


def _format_rag_entries(entries):
    """Format Neo4j RAG search result entries into display lines."""
    lines = []
    for r in entries:
        doc = r.get("doc_name", "")
        # Extract short filename from path
        short_name = doc.split("/")[-1] if "/" in doc else doc
        page = r.get("page_number", "")
        score = r.get("score", 0)
        lines.append(f"[{short_name} p.{page}] (score: {score})")
        content = r.get("content", "").strip()
        if content:
            lines.append(f"  {content}")
        lines.append("")
    return lines


def _format_webdoc_entries(entries):
    """Format webdoc search result entries into display lines."""
    lines = []
    for r in entries:
        lines.append(f"[{r.get('product', '')}] {r['title']} (score: {r['score']})")
        lines.append(f"  URL: {r['url']}")
        if r.get('headings'):
            lines.append(f"  Sections: {', '.join(r['headings'][:3])}")
        if r.get('snippet'):
            lines.append(f"  Preview: {r['snippet'][:150]}...")
        lines.append("")
    return lines


def _format_of7_entries(of7_result):
    """Format of7 search result entries into display lines."""
    lines = []
    for r in of7_result.get("results", []):
        lines.append(f"  {r['file']}:{r['line']}: {r['content']}")
    if of7_result.get("truncated"):
        lines.append("  ... (more results available via search_of7)")
    return lines


# Product name → of7 module directory mapping
_PRODUCT_TO_MODULE = {
    "ofasm": "ofasm",
    "ofcobol": "ofcobol",
    "osc": "osc",
    "osi": "osi",
    "ims": "ims",
    "batch": "batch",
    "base": "base",
}


# ── Auto-RAG: product detection & context injection ──

# Keywords that indicate an OpenFrame product question
_PRODUCT_KEYWORDS = {
    "ofasm": "ofasm",
    "ofcobol": "ofcobol",
    "osc": "osc",
    "cics": "osc",
    "batch": "batch",
    "tjes": "batch",
    "ims": "ims",
    "hidb": "ims",
    "base": "base",
    "tacf": "tacf",
    "prosort": "prosort",
    "jeus": "jeus",
    "tibero": "tibero",
    "openframe": "",
    "of7": "",
}

# Broader topic keywords that should trigger RAG even without product name
_TOPIC_KEYWORDS = [
    "컴파일", "compile", "어셈블", "assemble", "assembler",
    "cobol", "jcl", "매크로", "macro", "hlasm",
    "설정", "config", "옵션", "option", "파라미터", "parameter",
    "설치", "install", "마이그레이션", "migration",
    "ofasm", "ofcobol", "osc", "cics", "batch", "ims",
    "데이터셋", "dataset", "vsam", "tsam",
    "ofld", "링크", "link", "로드", "load",
    "에러", "error", "오류", "abend",
    "mainframe", "메인프레임", "z/os", "msp", "xsp", "vos3",
]


def _detect_product_from_query(text):
    """Detect OpenFrame product name from user query text.

    Returns (product, is_openframe_question) tuple.
    product: specific product name or "" for general OpenFrame.
    is_openframe_question: True if we should inject RAG context.
    """
    text_lower = text.lower()

    # Check product keywords
    for keyword, product in _PRODUCT_KEYWORDS.items():
        if keyword in text_lower:
            return product, True

    # Check topic keywords
    for keyword in _TOPIC_KEYWORDS:
        if keyword.lower() in text_lower:
            return "", True

    return "", False


def _auto_rag_context(query, product=""):
    """Fetch RAG context from Neo4j and format as injectable text.

    Returns formatted context string, or "" if no results.
    """
    rag_result = _ofcode_api("/api/rag/search", {
        "query": query, "product": product, "top_k": 5,
    })
    if isinstance(rag_result, str):
        return ""

    entries = rag_result.get("results", [])
    if not entries:
        return ""

    lines = ["", "[Reference Documentation from Official Manuals]"]
    for r in entries:
        doc = r.get("doc_name", "")
        short_name = doc.split("/")[-1] if "/" in doc else doc
        page = r.get("page_number", "")
        score = r.get("score", 0)
        content = r.get("content", "").strip()
        if content:
            lines.append(f"--- {short_name} (p.{page}, relevance: {score}) ---")
            lines.append(content)
            lines.append("")

    lines.append("[End of Reference Documentation]")
    lines.append("IMPORTANT: Base your answer ONLY on the reference documentation above. "
                 "Do NOT fabricate options, commands, or parameters that are not mentioned in the documentation.")
    return "\n".join(lines)


def tool_search_webdoc(query, product=""):
    """Search OpenFrame documentation across all sources.

    Runs all applicable steps and combines results:
      0) Neo4j RAG — full manual vector search (most accurate)
      1) Web docs — product-filtered
      2) Web docs — all products
      3) of7 source code — product module only  (e.g. of7/ofasm)
      4) of7 source code — all modules
    """
    lines = []
    module = _PRODUCT_TO_MODULE.get(product.lower(), "") if product else ""

    # ── Step 0: Neo4j RAG — full manual vector search ──
    rag_result = _ofcode_api("/api/rag/search", {
        "query": query, "product": product, "top_k": 3,
    })
    if not isinstance(rag_result, str):
        rag_entries = rag_result.get("results", [])
        if rag_entries:
            header = f"Manual RAG ({product})" if product else "Manual RAG"
            lines.append(f"── {header} ──")
            lines.extend(_format_rag_entries(rag_entries))

    # ── Step 1: Web docs — product-filtered ──
    if product:
        result = _ofcode_api("/api/webdoc/search", {"query": query, "top_k": 3, "product": product})
        if not isinstance(result, str):
            entries = result.get("results", [])
            if entries:
                lines.append(f"── Web docs ({product}) ──")
                lines.extend(_format_webdoc_entries(entries))

    # ── Step 2: Web docs — all products ──
    result = _ofcode_api("/api/webdoc/search", {"query": query, "top_k": 3})
    if not isinstance(result, str):
        entries = result.get("results", [])
        if entries:
            # Skip duplicates already shown in Step 1
            step1_urls = {l.split("URL: ")[-1].strip() for l in lines if "URL: " in l}
            new_entries = [e for e in entries if e.get("url") not in step1_urls]
            if new_entries:
                lines.append(f"── Web docs (all products) ──")
                lines.extend(_format_webdoc_entries(new_entries))

    # ── Step 3: of7 source code — product module ──
    if module:
        of7_result = _ofcode_api("/api/search", {"query": query, "module": module, "file_type": "both", "max_results": 10})
        if not isinstance(of7_result, str):
            of7_entries = of7_result.get("results", [])
            if of7_entries:
                lines.append(f"── of7 source code ({module}/) ──")
                lines.extend(_format_of7_entries(of7_result))

    # ── Step 4: of7 source code — all modules ──
    of7_result = _ofcode_api("/api/search", {"query": query, "module": "", "file_type": "both", "max_results": 10})
    if not isinstance(of7_result, str):
        of7_entries = of7_result.get("results", [])
        if of7_entries:
            # Skip duplicates already shown in Step 3
            step3_files = {l.strip().split(":")[0] for l in lines if "── of7" not in l and ":" in l and "/" in l}
            new_of7 = [r for r in of7_entries if r["file"] not in step3_files]
            if new_of7:
                lines.append(f"── of7 source code (all modules) ──")
                for r in new_of7:
                    lines.append(f"  {r['file']}:{r['line']}: {r['content']}")

    if not lines:
        return f"No results found for '{query}' in web docs or of7 source code."
    return "\n".join(lines)


TOOL_DISPATCH = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "bash": tool_bash,
    "grep_search": tool_grep_search,
    "glob_search": tool_glob_search,
    "list_directory": tool_list_directory,
}

OPENFRAME_TOOL_DISPATCH = {
    "search_of7": tool_search_of7,
    "get_module_info": tool_get_module_info,
    "get_function_def": tool_get_function_def,
    "get_header_api": tool_get_header_api,
    "get_architecture": tool_get_architecture,
    "find_callers": tool_find_callers,
    "search_webdoc": tool_search_webdoc,
}


# ═══════════════════════════════════════════════════════════════
# Section 4: Think Tag Filter (for Qwen3 <think> blocks)
# ═══════════════════════════════════════════════════════════════

class ThinkFilter:
    """Filters <think>...</think> blocks from streaming text."""

    def __init__(self, show_thinking=False):
        self.in_think = False
        self.buffer = ""
        self.show_thinking = show_thinking
        self.think_content = ""

    def feed(self, text):
        """Feed text chunk, return (display_text, thinking_text)."""
        self.buffer += text
        display = ""
        thinking = ""

        while self.buffer:
            if self.in_think:
                end_idx = self.buffer.find("</think>")
                if end_idx != -1:
                    thinking += self.buffer[:end_idx]
                    self.in_think = False
                    self.buffer = self.buffer[end_idx + 8:]
                else:
                    if len(self.buffer) > 8:
                        thinking += self.buffer[:-8]
                        self.buffer = self.buffer[-8:]
                    break
            else:
                start_idx = self.buffer.find("<think>")
                if start_idx != -1:
                    display += self.buffer[:start_idx]
                    self.in_think = True
                    self.buffer = self.buffer[start_idx + 7:]
                else:
                    safe_end = len(self.buffer)
                    for i in range(1, min(8, len(self.buffer) + 1)):
                        if self.buffer[-i:] == "<think>"[:i]:
                            safe_end = len(self.buffer) - i
                            break
                    display += self.buffer[:safe_end]
                    self.buffer = self.buffer[safe_end:]
                    if safe_end == 0:
                        break

        self.think_content += thinking
        return display, thinking

    def flush(self):
        """Flush remaining buffer."""
        remaining = self.buffer
        self.buffer = ""
        if self.in_think:
            return "", remaining
        return remaining, ""


# ═══════════════════════════════════════════════════════════════
# Section 5: Hermes Tool Call Fallback Parser
# ═══════════════════════════════════════════════════════════════

def parse_hermes_tool_calls(text):
    """Parse Hermes-style <tool_call> blocks from text content as fallback."""
    pattern = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"
    matches = re.findall(pattern, text, re.DOTALL)
    tool_calls = []
    for match in matches:
        try:
            data = json.loads(match)
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "name": data.get("name", ""),
                "arguments": json.dumps(data.get("arguments", {})),
            })
        except json.JSONDecodeError:
            continue
    return tool_calls


# ═══════════════════════════════════════════════════════════════
# Section 6: Display Helpers
# ═══════════════════════════════════════════════════════════════

def show_tool_call(name, args_dict):
    args_lines = []
    for k, v in args_dict.items():
        val = repr(v) if isinstance(v, str) and len(str(v)) > 80 else str(v)
        if isinstance(v, str) and len(v) > 200:
            val = repr(v[:200] + "...")
        args_lines.append(f"  {k}: {val}")
    body = "\n".join(args_lines)
    console.print(Panel(body, title=f"[tool.name]{name}[/tool.name]", border_style="cyan", padding=(0, 1)))


def show_tool_result(name, result, is_error=False):
    style = "red" if is_error else "dim"
    truncated = _truncate(result, 30)
    console.print(Panel(
        truncated,
        title=f"[{style}]Result: {name}[/{style}]",
        border_style=style,
        padding=(0, 1),
    ))


def show_welcome(model_name, server, context_limit, openframe=False):
    console.print()
    if openframe:
        console.print(Panel(
            f"[bold magenta]OpenFrame Code[/bold magenta] - OpenFrame 7 Expert CLI\n\n"
            f"Type [bold]/help[/bold] for commands, [bold]/exit[/bold] to quit.",
            border_style="magenta",
            padding=(1, 2),
        ))
    else:
        console.print(Panel(
            f"[bold]Local Coder[/bold] - Interactive CLI Coding Assistant\n\n"
            f"Type [bold]/help[/bold] for commands, [bold]/exit[/bold] to quit.",
            border_style="green",
            padding=(1, 2),
        ))
    console.print()


def show_help(openframe=False):
    base_help = (
        "[bold]Commands:[/bold]\n"
        "  /help       Show this help message\n"
        "  /exit       Exit the program\n"
        "  /clear      Clear conversation history\n"
        "  /model      Show current model info\n"
        "  /tokens     Show token usage and context window status\n"
        "  /history    Show conversation message count\n"
        "  /compact    Compact history (keep last N exchanges)\n"
        "  Ctrl+C      Interrupt current response\n"
    )
    if openframe:
        base_help += (
            "\n[bold]OpenFrame Commands:[/bold]\n"
            "  /reindex       Rebuild server index (after source changes)\n"
            "  /crawl-webdoc [product]  Crawl web docs (all or specific product)\n"
            "\n[bold]OpenFrame Tools:[/bold]\n"
            "  search_of7(query)          Search C/H files in of7/\n"
            "  get_module_info(module)    Module description and structure\n"
            "  get_function_def(func)     Find function definition + code\n"
            "  get_header_api(header)     Header API summary\n"
            "  get_architecture()         Architecture diagram\n"
            "  find_callers(func)         Who calls this function?\n"
            "  search_webdoc(query)       Search product web documentation\n"
        )
    base_help += (
        "\n[bold]Tips:[/bold]\n"
        "  - Paste multi-line text directly\n"
        "  - Destructive operations require confirmation\n"
        "  - Use --no-confirm to skip confirmations"
    )
    console.print(Panel(
        base_help,
        title="[bold]Help[/bold]",
        border_style="blue",
        padding=(0, 1),
    ))


# ═══════════════════════════════════════════════════════════════
# Section 7: Local Coder - Main Agent Class
# ═══════════════════════════════════════════════════════════════

class LocalCoder:
    def __init__(self, server, model=None, no_confirm=False, show_thinking=False,
                 temperature=0.7, max_tokens=4096, context_length=None,
                 openframe=False, ofcode_server=None):
        self.server = server
        self.no_confirm = no_confirm
        self.show_thinking = show_thinking
        self.temperature = temperature
        self.requested_max_tokens = max_tokens
        self.openframe = openframe

        self.client = OpenAI(base_url=server, api_key="not-needed")
        model_id, detected_ctx = self._detect_model_and_context()
        self.model = model or model_id
        self.context_limit = context_length or detected_ctx or DEFAULT_CONTEXT_LENGTH

        # Setup tools and system prompt based on mode
        if openframe:
            global _ofcode_server_url
            _ofcode_server_url = (ofcode_server or DEFAULT_OFCODE_SERVER).rstrip("/")
            # Verify ofcode-server connection
            ok, info = _check_ofcode_server()
            if ok:
                console.print(f"  [dim]ofcode-server: {_ofcode_server_url} (connected)[/dim]")
            else:
                console.print(f"[yellow]Warning: ofcode-server at {_ofcode_server_url}: {info}[/yellow]")
            self.tools = TOOLS + OPENFRAME_TOOLS
            self.tool_dispatch = {**TOOL_DISPATCH, **OPENFRAME_TOOL_DISPATCH}
            prompt = OPENFRAME_SYSTEM_PROMPT.format(cwd=os.getcwd())
        else:
            self.tools = TOOLS
            self.tool_dispatch = TOOL_DISPATCH
            prompt = SYSTEM_PROMPT.format(cwd=os.getcwd())

        self.messages = [{"role": "system", "content": prompt}]

    def _detect_model_and_context(self):
        """Detect model name and context length from vLLM /v1/models API."""
        try:
            models = self.client.models.list()
            if models.data:
                m = models.data[0]
                model_id = m.id
                ctx_len = getattr(m, "max_model_len", None)
                console.print(f"  [dim]Auto-detected model: {model_id}[/dim]")
                if ctx_len:
                    console.print(f"  [dim]Context length: {ctx_len} tokens[/dim]")
                return model_id, ctx_len
        except Exception as e:
            console.print(f"[error]Failed to connect to {self.server}: {e}[/error]")
            sys.exit(1)
        console.print("[error]No models available on server[/error]")
        sys.exit(1)

    def get_token_usage(self):
        """Return (estimated_input_tokens, available_output_tokens)."""
        input_tokens = estimate_messages_tokens(self.messages, self.tools)
        available = self.context_limit - input_tokens - TOKEN_BUFFER
        return input_tokens, max(0, available)

    def calculate_max_tokens(self):
        """Proactive budget system: calculate safe max_tokens BEFORE sending.
        Runs progressive compression if budget is insufficient.
        Returns safe max_tokens value that will not cause 400 errors."""
        input_tokens, available = self.get_token_usage()

        # Happy path: enough budget
        if available >= MIN_OUTPUT_TOKENS:
            return min(self.requested_max_tokens, available)

        # Budget insufficient - run progressive compression
        console.print(
            f"  [yellow]Context budget: ~{input_tokens} input, "
            f"~{available} available (need {MIN_OUTPUT_TOKENS}+). Compressing...[/yellow]"
        )
        self.progressive_compress()

        # Recalculate after compression
        input_tokens, available = self.get_token_usage()
        return max(MIN_OUTPUT_TOKENS, min(self.requested_max_tokens, available))

    def progressive_compress(self):
        """Progressive 4-step compression to fit within context budget.
        Steps 1-3 are local (no LLM call). Step 4 uses LLM as last resort.
        Returns True if compression was performed."""
        target = self.context_limit - MIN_OUTPUT_TOKENS - TOKEN_BUFFER
        compressed = False

        # Step 1: Truncate tool results (biggest token consumers)
        for msg in self.messages[1:]:
            if msg.get("role") == "tool":
                content = msg.get("content") or ""
                lines = content.split("\n")
                if len(lines) > TOOL_RESULT_TRUNCATE_LINES:
                    msg["content"] = "\n".join(lines[:TOOL_RESULT_TRUNCATE_LINES]) + f"\n...(truncated {len(lines)} lines)"
                    compressed = True
            # Also truncate very long assistant content
            elif msg.get("role") == "assistant":
                content = msg.get("content") or ""
                if len(content) > 800:
                    msg["content"] = content[:800] + "\n...(truncated)"
                    compressed = True

        if estimate_messages_tokens(self.messages, self.tools) <= target:
            if compressed:
                console.print("  [dim]Step 1: Tool results truncated.[/dim]")
            return compressed

        # Step 2: Drop old messages, keep system + last N
        if len(self.messages) > 1 + RECENT_MESSAGES_TO_KEEP:
            system_msg = self.messages[0]
            recent = self.messages[-RECENT_MESSAGES_TO_KEEP:]
            old_count = len(self.messages) - 1 - RECENT_MESSAGES_TO_KEEP
            self.messages = [system_msg] + recent
            console.print(f"  [dim]Step 2: Dropped {old_count} old messages.[/dim]")
            compressed = True

        if estimate_messages_tokens(self.messages, self.tools) <= target:
            return compressed

        # Step 3: Aggressive content truncation on remaining messages
        max_chars = 300
        for msg in self.messages[1:]:
            content = msg.get("content") or ""
            if len(content) > max_chars:
                msg["content"] = content[:max_chars] + "\n...(truncated)"
                compressed = True

        if estimate_messages_tokens(self.messages, self.tools) <= target:
            console.print("  [dim]Step 3: Messages truncated aggressively.[/dim]")
            return compressed

        # Step 4: LLM-based summarization of remaining old context
        if len(self.messages) > 2:
            system_msg = self.messages[0]
            old_msgs = self.messages[1:-2] if len(self.messages) > 3 else []
            keep_msgs = self.messages[-2:] if len(self.messages) > 2 else self.messages[1:]

            if old_msgs:
                old_text_parts = []
                for msg in old_msgs:
                    role = msg.get("role", "?")
                    content = msg.get("content", "")
                    if content:
                        if len(content) > 300:
                            content = content[:300] + "..."
                        old_text_parts.append(f"[{role}] {content}")
                old_text = "\n".join(old_text_parts)
                if len(old_text) > 1500:
                    old_text = old_text[:1500] + "\n..."

                try:
                    summary_max = min(200, self.context_limit - estimate_tokens(old_text) - 150)
                    if summary_max >= 50:
                        resp = self.client.chat.completions.create(
                            model=self.model,
                            messages=[{
                                "role": "user",
                                "content": (
                                    "/no_think\n"
                                    "Summarize in 2 sentences. Focus on tasks done and current state.\n\n"
                                    f"{old_text}"
                                ),
                            }],
                            max_tokens=summary_max,
                            temperature=0.3,
                        )
                        summary = resp.choices[0].message.content or ""
                        summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL).strip()
                        if summary:
                            summary_msg = {"role": "user", "content": f"[Context: {summary}]"}
                            self.messages = [system_msg, summary_msg] + keep_msgs
                            console.print(f"  [success]Step 4: LLM summarized {len(old_msgs)} messages.[/success]")
                            return True
                except Exception as e:
                    console.print(f"  [dim]Step 4 summarization failed: {e}[/dim]")

        # Final fallback: drop everything except system + last message
        if len(self.messages) > 2:
            self.messages = [self.messages[0], self.messages[-1]]
            console.print("  [yellow]Emergency: kept only last message.[/yellow]")
            compressed = True

        return compressed

    def confirm(self, description):
        if self.no_confirm:
            return True
        console.print(f"  [confirm]> {description}[/confirm]")
        try:
            response = console.input("  [bold]Allow? (y/N):[/bold] ")
            return response.strip().lower() in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def execute_tool(self, name, arguments_str):
        """Execute a tool and return the result string."""
        func = self.tool_dispatch.get(name)
        if not func:
            return f"Error: Unknown tool: {name}"

        try:
            args = json.loads(arguments_str) if arguments_str else {}
        except json.JSONDecodeError as e:
            return f"Error: Invalid tool arguments JSON: {e}\nRaw: {arguments_str}"

        # Show what we're about to do
        show_tool_call(name, args)

        # Confirm destructive operations
        if name in CONFIRM_REQUIRED and not self.no_confirm:
            if name == "bash":
                desc = f"Run command: {args.get('command', '?')}"
            elif name == "write_file":
                desc = f"Write to: {args.get('path', '?')}"
            elif name == "edit_file":
                desc = f"Edit: {args.get('path', '?')}"
            else:
                desc = f"Execute: {name}"

            if not self.confirm(desc):
                return "Action denied by user."

        try:
            result = func(**args)
        except TypeError as e:
            return f"Error: Invalid arguments for {name}: {e}"
        except Exception as e:
            return f"Error executing {name}: {e}"

        is_error = result.startswith("Error:") if result else False
        show_tool_result(name, result, is_error)
        return result

    def _parse_token_count_from_error(self, error_msg):
        """Parse actual input token count from vLLM 400 error message.
        Example: '...your request has 4126 input tokens...' -> 4126"""
        match = re.search(r"your request has (\d+) input tokens", str(error_msg))
        if match:
            return int(match.group(1))
        return None

    def _create_stream(self, max_tokens):
        """Create a streaming completion with proactive overflow prevention.
        If vLLM still returns 400 (estimation was off), learns correction factor
        and retries with progressive compression."""
        try:
            return self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.tools,
                stream=True,
                temperature=self.temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            error_msg = str(e)
            if "400" not in error_msg:
                raise

            # Parse actual token count from vLLM error to learn correction
            actual_input = self._parse_token_count_from_error(error_msg)
            if actual_input:
                estimated = estimate_messages_tokens(self.messages, self.tools)
                update_token_correction(estimated, actual_input)
                console.print(
                    f"  [yellow]Token mismatch: estimated {estimated}, actual {actual_input}. "
                    f"Correction factor updated.[/yellow]"
                )

                # Try simple max_tokens reduction first
                available = self.context_limit - actual_input - 50
                if available >= MIN_OUTPUT_TOKENS:
                    console.print(f"  [yellow]Retrying with max_tokens={available}...[/yellow]")
                    return self.client.chat.completions.create(
                        model=self.model,
                        messages=self.messages,
                        tools=self.tools,
                        stream=True,
                        temperature=self.temperature,
                        max_tokens=available,
                    )

            # Not enough room - compress and retry
            console.print("  [yellow]Context full. Running progressive compression...[/yellow]")
            self.progressive_compress()
            new_max = self.calculate_max_tokens()
            return self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.tools,
                stream=True,
                temperature=self.temperature,
                max_tokens=new_max,
            )

    def stream_response(self):
        """Send messages to LLM and stream the response.

        Returns (content_text, tool_calls_list) where tool_calls_list
        is a list of dicts with keys: id, name, arguments.
        """
        accumulated_content = ""
        display_content = ""
        tool_calls_data = {}
        think_filter = ThinkFilter(self.show_thinking)
        usage_info = None  # capture from last chunk for correction learning

        try:
            # Proactive budget check before sending
            estimated_input = estimate_messages_tokens(self.messages, self.tools)
            effective_max_tokens = self.calculate_max_tokens()
            stream = self._create_stream(effective_max_tokens)

            console.print()  # blank line before response

            for chunk in stream:
                # Capture usage info from stream (vLLM sends it in final chunk)
                if hasattr(chunk, "usage") and chunk.usage:
                    usage_info = chunk.usage

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                # Accumulate text content
                if delta and delta.content:
                    accumulated_content += delta.content
                    display_text, thinking_text = think_filter.feed(delta.content)

                    if display_text:
                        display_content += display_text
                        sys.stdout.write(display_text)
                        sys.stdout.flush()

                    if thinking_text and self.show_thinking:
                        console.print(f"[thinking]{thinking_text}[/thinking]", end="")

                # Accumulate tool calls
                if delta and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_delta.id:
                            tool_calls_data[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_calls_data[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_calls_data[idx]["arguments"] += tc_delta.function.arguments

        except KeyboardInterrupt:
            console.print("\n[yellow]Response interrupted.[/yellow]")
            return display_content, []
        except Exception as e:
            console.print(f"\n[error]Stream error: {e}[/error]")
            return None, []

        # Learn from actual usage to improve future estimates
        if usage_info and hasattr(usage_info, "prompt_tokens") and usage_info.prompt_tokens:
            update_token_correction(estimated_input, usage_info.prompt_tokens)

        # Flush think filter
        remaining_display, remaining_think = think_filter.flush()
        if remaining_display:
            display_content += remaining_display
            sys.stdout.write(remaining_display)
            sys.stdout.flush()

        if accumulated_content or display_content:
            sys.stdout.write("\n")
            sys.stdout.flush()

        # Build tool calls list
        tool_calls_list = []
        for idx in sorted(tool_calls_data.keys()):
            tc = tool_calls_data[idx]
            if not tc["id"]:
                tc["id"] = f"call_{uuid.uuid4().hex[:8]}"
            tool_calls_list.append(tc)

        # Fallback: check for Hermes-style tool calls in text
        if not tool_calls_list and accumulated_content and "<tool_call>" in accumulated_content:
            tool_calls_list = parse_hermes_tool_calls(accumulated_content)
            if tool_calls_list:
                console.print("[dim](parsed tool calls from text)[/dim]")

        # Add assistant message to history
        assistant_msg = {"role": "assistant", "content": display_content or None}
        if tool_calls_list:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls_list
            ]
        self.messages.append(assistant_msg)

        return display_content, tool_calls_list

    def agent_loop(self):
        """Run the agent loop: stream response, execute tools, repeat."""
        for iteration in range(MAX_AGENT_ITERATIONS):
            content, tool_calls = self.stream_response()

            if content is None:
                break  # error occurred

            if not tool_calls:
                break  # no tools to execute, done

            # Execute each tool call and feed results back
            for tc in tool_calls:
                result = self.execute_tool(tc["name"], tc["arguments"])
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

            if iteration == MAX_AGENT_ITERATIONS - 1:
                console.print(f"[yellow]Reached max iterations ({MAX_AGENT_ITERATIONS}). Stopping.[/yellow]")

    def process(self, user_input):
        """Process user input: handle commands or send to LLM."""
        text = user_input.strip()
        if not text:
            return

        # Special commands
        if text.startswith("/"):
            cmd = text.split()[0].lower()
            if cmd in ("/exit", "/quit", "/q"):
                console.print("[dim]Goodbye![/dim]")
                sys.exit(0)
            elif cmd == "/clear":
                if self.openframe:
                    prompt = OPENFRAME_SYSTEM_PROMPT.format(cwd=os.getcwd())
                else:
                    prompt = SYSTEM_PROMPT.format(cwd=os.getcwd())
                self.messages = [{"role": "system", "content": prompt}]
                console.print("[success]Conversation cleared.[/success]")
                return
            elif cmd == "/help":
                show_help(openframe=self.openframe)
                return
            elif cmd == "/model":
                console.print(f"  Model: [cyan]{self.model}[/cyan]")
                console.print(f"  Server: [dim]{self.server}[/dim]")
                console.print(f"  Context limit: {self.context_limit} tokens")
                console.print(f"  Max tokens (requested): {self.requested_max_tokens}")
                console.print(f"  Temperature: {self.temperature}")
                return
            elif cmd == "/tokens":
                input_tokens, available = self.get_token_usage()
                pct = int(input_tokens / self.context_limit * 100)
                bar_len = 30
                filled = int(bar_len * pct / 100)
                bar = "#" * filled + "-" * (bar_len - filled)
                console.print(f"  Context: [{bar}] {pct}%")
                console.print(f"  Input: ~{input_tokens} / {self.context_limit} tokens")
                console.print(f"  Available for output: ~{available} tokens")
                console.print(f"  Messages: {len(self.messages)}")
                return
            elif cmd == "/history":
                n = len(self.messages)
                console.print(f"  Messages in history: [cyan]{n}[/cyan]")
                return
            elif cmd == "/compact":
                # Keep system + last 10 messages
                if len(self.messages) > 11:
                    self.messages = [self.messages[0]] + self.messages[-10:]
                    console.print("[success]History compacted to last 10 messages.[/success]")
                else:
                    console.print("[dim]History is already small.[/dim]")
                return
            elif cmd == "/reindex":
                if not self.openframe:
                    console.print("[dim]Only available in OpenFrame mode (--openframe).[/dim]")
                    return
                console.print("  [dim]Rebuilding index on ofcode-server...[/dim]")
                result = _ofcode_api("/api/rebuild-index", {})
                if isinstance(result, dict) and result.get("status") == "ok":
                    console.print(
                        f"[success]Index rebuilt: "
                        f"{result.get('functions', 0)} functions, "
                        f"{result.get('structs', 0)} structs, "
                        f"{result.get('headers', 0)} headers[/success]"
                    )
                else:
                    console.print(f"[error]Rebuild failed: {result}[/error]")
                return
            elif cmd == "/crawl-webdoc":
                if not self.openframe:
                    console.print("[dim]Only available in OpenFrame mode (--openframe).[/dim]")
                    return
                # Parse optional product argument: /crawl-webdoc [product]
                parts = text.split(None, 1)
                crawl_product = parts[1].strip() if len(parts) > 1 else ""
                body = {"product": crawl_product} if crawl_product else {}
                if crawl_product:
                    console.print(f"  [dim]Crawling web docs for '{crawl_product}'...[/dim]")
                else:
                    console.print("  [dim]Crawling all web documentation...[/dim]")
                result = _ofcode_api("/api/webdoc/crawl", body)
                if isinstance(result, dict) and result.get("status") == "ok":
                    console.print(
                        f"[success]Web docs crawled: "
                        f"{result.get('total_pages', 0)} pages, "
                        f"products: {', '.join(result.get('products', []))}[/success]"
                    )
                else:
                    console.print(f"[error]Crawl failed: {result}[/error]")
                return
            else:
                console.print(f"[dim]Unknown command: {cmd}. Type /help for available commands.[/dim]")
                return

        # Auto-RAG: inject documentation context before LLM responds
        rag_context = ""
        if self.openframe:
            product, is_of_question = _detect_product_from_query(text)
            if is_of_question:
                rag_context = _auto_rag_context(text, product)
                if rag_context:
                    console.print(f"[dim]  (Auto-RAG: injected documentation context)[/dim]")

        # Add user message (with RAG context if available)
        if rag_context:
            augmented = text + "\n" + rag_context
            self.messages.append({"role": "user", "content": augmented})
        else:
            self.messages.append({"role": "user", "content": text})
        self.agent_loop()


# ═══════════════════════════════════════════════════════════════
# Section 8: Main Entry Point & REPL
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="OpenFrame Code - CLI coding assistant powered by local LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--server", default=DEFAULT_SERVER,
        help=f"vLLM server URL (default: {DEFAULT_SERVER})",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help="Model name (auto-detected if not specified)",
    )
    parser.add_argument(
        "--no-confirm", action="store_true",
        help="Skip confirmation prompts for destructive operations",
    )
    parser.add_argument(
        "--show-thinking", action="store_true",
        help="Show Qwen3 <think> blocks instead of hiding them",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.7,
        help="Sampling temperature (default: 0.7)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=4096,
        help="Max response tokens (default: 4096)",
    )
    parser.add_argument(
        "--context-length", type=int, default=None,
        help="Model context length override (auto-detected if not specified)",
    )
    parser.add_argument(
        "--openframe", action="store_true",
        help="Enable OpenFrame Code mode with of7 codebase knowledge and tools",
    )
    parser.add_argument(
        "--ofcode-server", default=None,
        help=f"ofcode-server URL for OpenFrame mode (default: {DEFAULT_OFCODE_SERVER})",
    )
    args = parser.parse_args()

    # Initialize the coder
    coder = LocalCoder(
        server=args.server,
        model=args.model,
        no_confirm=args.no_confirm,
        show_thinking=args.show_thinking,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        context_length=args.context_length,
        openframe=args.openframe,
        ofcode_server=args.ofcode_server,
    )

    show_welcome(coder.model, coder.server, coder.context_limit,
                 openframe=args.openframe)

    # Setup prompt - try prompt_toolkit first, fall back to basic input
    use_prompt_toolkit = True
    session = None
    try:
        session = PromptSession(history=FileHistory(HISTORY_FILE))
        # Test that it can actually create output (fails in Git Bash on Windows)
        session.app
    except Exception:
        use_prompt_toolkit = False
        console.print("  [dim]Note: Using basic input (prompt_toolkit unavailable in this terminal)[/dim]")

    def get_input():
        if use_prompt_toolkit and session:
            return session.prompt(HTML("<ansigreen><b>You &gt; </b></ansigreen>"))
        else:
            try:
                console.print("[green bold]You > [/green bold]", end="")
                return input()
            except UnicodeDecodeError:
                return input("You > ")

    # REPL loop
    while True:
        try:
            user_input = get_input()
            coder.process(user_input)
        except KeyboardInterrupt:
            console.print()  # newline after ^C
            continue
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            break


if __name__ == "__main__":
    main()
