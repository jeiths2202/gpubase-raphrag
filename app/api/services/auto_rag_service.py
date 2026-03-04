"""
Auto-RAG Service

Agent Loop + Tool Calling 기반 자율 RAG 서비스.
CLI(openframe_code/core.py)의 Auto-RAG 로직을 웹 UI용으로 **정확히** 포팅.

CLI와의 일치 사항:
- OpenAI SDK 사용 (CLI와 동일한 호출 방식)
- ThinkFilter: <think>...</think> 블록 스트리밍 필터
- Hermes fallback: <tool_call>{JSON}</tool_call> XML 파싱
- 토큰 예산 관리: estimate → proactive budget → progressive compression
- 모델 자동 감지: /v1/models API
- tool_choice 미전송 (CLI와 동일: vLLM이 자율 결정)
- chat_template_kwargs 미전송
- max_tokens=4096 (CLI default) + budget-aware reduction
- 14개 도구 (7 base + 7 OpenFrame) — rag_search 별도 도구 없음
"""
import json
import logging
import os
import re
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import aiohttp

from ..core.config import get_api_settings
from ..core.logging_framework import get_logger
from ..adapters.learning_llm.vllm_adapter import MULTI_LORA_PRODUCT_MAPPING

logger = get_logger("kms.auto_rag")

# ─── Constants (CLI core.py와 동일) ────────────────────────────

MAX_AGENT_ITERATIONS = 25
MAX_TOOL_RESULT_LEN = 4000
SSE_RESULT_PREVIEW_LEN = 200
TOKEN_BUFFER = 500
MIN_OUTPUT_TOKENS = 256
RECENT_MESSAGES_TO_KEEP = 4
TOOL_RESULT_TRUNCATE_LINES = 5
DEFAULT_MAX_TOKENS = 4096
DEFAULT_CONTEXT_LENGTH = 8192


# ═══════════════════════════════════════════════════════════════
# ThinkFilter: <think>...</think> 스트리밍 필터 (CLI Section 4)
# ═══════════════════════════════════════════════════════════════

class ThinkFilter:
    """Filters <think>...</think> blocks from streaming text.
    Exact port from CLI core.py Section 4."""

    def __init__(self):
        self.in_think = False
        self.buffer = ""
        self.think_content = ""

    def feed(self, text: str) -> tuple[str, str]:
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

    def flush(self) -> tuple[str, str]:
        """Flush remaining buffer."""
        remaining = self.buffer
        self.buffer = ""
        if self.in_think:
            return "", remaining
        return remaining, ""


# ═══════════════════════════════════════════════════════════════
# Hermes Tool Call Fallback (CLI Section 5)
# ═══════════════════════════════════════════════════════════════

def parse_hermes_tool_calls(text: str) -> list[dict]:
    """Parse Hermes-style <tool_call> blocks from text content as fallback.
    Exact port from CLI core.py Section 5."""
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
# Token Estimation (CLI Section 1.5)
# ═══════════════════════════════════════════════════════════════

_token_correction_factor = 1.0


def estimate_tokens(text: str) -> int:
    """Conservative token estimate (chars/2.0) — CLI와 동일."""
    if not text:
        return 0
    return int(len(text) / 2.0) + 1


def update_token_correction(estimated: int, actual: int):
    """EMA 기반 보정계수 업데이트 — CLI와 동일."""
    global _token_correction_factor
    if estimated <= 0 or actual <= 0:
        return
    ratio = actual / estimated
    _token_correction_factor = 0.7 * _token_correction_factor + 0.3 * ratio


def estimate_messages_tokens(messages: list, tools: Optional[list] = None) -> int:
    """메시지 배열 + 도구 정의의 토큰 추정 — CLI와 동일."""
    total = 0
    for msg in messages:
        total += 4  # role overhead
        if msg.get("content"):
            total += estimate_tokens(msg["content"])
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                total += estimate_tokens(tc.get("function", {}).get("name", ""))
                total += estimate_tokens(tc.get("function", {}).get("arguments", ""))
                total += 10
    if tools:
        total += estimate_tokens(json.dumps(tools))
    total = int(total * _token_correction_factor)
    return total


# ═══════════════════════════════════════════════════════════════
# OpenFrame System Prompt (CLI와 완전 동일)
# ═══════════════════════════════════════════════════════════════

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


# ─── Tool Definitions (CLI TOOLS + OPENFRAME_TOOLS — 14 tools) ──────────

# CLI의 7개 base tools (웹 UI에서는 실행 불가이므로 stub 처리하지만,
# vLLM에 전달하는 도구 정의는 CLI와 동일해야 함)
BASE_TOOLS = [
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

# CLI와 동일: TOOLS + OPENFRAME_TOOLS = 14 tools
AUTO_RAG_TOOLS = BASE_TOOLS + OPENFRAME_TOOLS


# ─── Product Detection Keywords (CLI와 동일) ────────────────

_PRODUCT_KEYWORDS: Dict[str, str] = {
    # OpenFrame 핵심 제품
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
    # OpenFrame 유틸리티/도구
    "ofgw": "ofgw",
    "ofmanager": "ofmanager",
    "ofminer": "ofminer",
    "ofstudio": "ofstudio",
    "ofpli": "ofpli",
    "prosort": "prosort",
    "protrieve": "protrieve",
    "prosync": "prosync",
    # OpenFrame 메인프레임 호환
    "mvs": "mvs",
    "msp": "msp",
    "xsp": "xsp",
    "vos3": "vos3",
    # TmaxSoft 독립 제품
    "jeus": "jeus",
    "webtob": "webtob",
    "tibero": "tibero",
    "tmax": "tmax",
    # 일반
    "openframe": "",
    "of7": "",
    # OpenFrame Base C API 라이브러리
    "tdcb": "base",
    "tcfh": "base",
    "dsalc": "base",
    "dsio": "base",
    "dbio": "base",
    "tdbconn": "base",
}

_TOPIC_KEYWORDS: List[str] = [
    "컴파일", "compile", "어셈블", "assemble", "assembler",
    "cobol", "jcl", "매크로", "macro", "hlasm",
    "설정", "config", "옵션", "option", "파라미터", "parameter",
    "설치", "install", "마이그레이션", "migration",
    "ofasm", "ofcobol", "osc", "cics", "batch", "ims",
    "ofgw", "ofmanager", "ofminer", "ofstudio", "ofpli",
    "prosort", "protrieve", "prosync",
    "jeus", "webtob", "tibero", "tmax",
    "mvs", "msp", "xsp", "vos3",
    "데이터셋", "dataset", "vsam", "tsam",
    "ofld", "링크", "link", "로드", "load",
    "에러", "error", "오류", "abend",
    "mainframe", "メインフレーム", "z/os", "msp", "xsp", "vos3",
]

_PRODUCT_TO_MODULE: Dict[str, str] = {
    "ofasm": "ofasm",
    "ofcobol": "ofcobol",
    "osc": "osc",
    "osi": "osi",
    "ims": "ims",
    "batch": "batch",
    "base": "base",
}

# ─── Utility Product → Neo4j 검색 제품 매핑 ──────────────────
# 유틸리티 제품은 독립 청크가 없어 부모 제품 문서에서 검색해야 함
_UTILITY_SEARCH_PRODUCTS: Dict[str, List[str]] = {
    "protrieve": ["common", "batch"],   # CA-Easytrieve Plus → Common Utility Reference
    "prosort": ["common", "batch"],     # Sort utility → Common/Batch docs
    "prosync": ["common"],              # Data sync → Common docs
    "ofgw": ["base"],                   # OpenFrame Gateway
    "ofmanager": ["base"],              # OpenFrame Manager
    "ofminer": ["base"],               # OpenFrame Miner
    "ofstudio": ["base"],              # OpenFrame Studio
    "ofpli": ["common"],              # OpenFrame PL/I
}

# 유틸리티 제품의 벡터 검색 쿼리 보강 키워드
# 일본어/한국어 쿼리가 영문 기술 용어와 임베딩 매칭이 안 될 때 보완
_UTILITY_QUERY_ENRICHMENT: Dict[str, str] = {
    "protrieve": "ProTrieve CA-Easytrieve Plus EZTPA00",
    "prosort": "ProSort DFSORT SORT MERGE",
    "prosync": "ProSync synchronization replication",
    "ofgw": "OFGW OpenFrame Gateway",
    "ofmanager": "OFManager OpenFrame Manager",
    "ofminer": "OFMiner OpenFrame Miner",
    "ofstudio": "OFStudio OpenFrame Studio",
    "ofpli": "OFPLI PL/I OpenFrame",
}


def _expand_search_product(product: str) -> List[str]:
    """유틸리티 제품을 Neo4j 검색 가능한 부모 제품으로 확장.

    예: 'protrieve' → ['common', 'batch']
    'osc' → ['osc']  (변경 없음)
    """
    if product in _UTILITY_SEARCH_PRODUCTS:
        return _UTILITY_SEARCH_PRODUCTS[product]
    return [product] if product else [""]


# ─── Slash Commands ──────────────────────────────────────────

HELP_TEXT = """**Auto-RAG Commands:**
| Command | Description |
|---------|-------------|
| `/help` | Show this help |
| `/clear` | Clear conversation history |
| `/model` | Show current vLLM model info |
| `/tokens` | Show token usage |
| `/reindex` | Rebuild ofcode-server search index |
| `/crawl-webdoc <product>` | Crawl web docs for a product |
| `/analyze <path>` | Analyze legacy mainframe assets (COBOL, ASM, JCL, etc.) |
"""


# =============================================================================
# OfcodeClient: ofcode-server HTTP client (CLI Section 3.5)
# =============================================================================

class OfcodeClient:
    """ofcode-server (port 12820) async HTTP client."""

    def __init__(self, base_url: Optional[str] = None):
        settings = get_api_settings()
        self.base_url = base_url or settings.OFCODE_SERVER_URL

    async def _call(self, endpoint: str, payload: Optional[dict] = None, timeout: int = 30) -> Any:
        url = f"{self.base_url}{endpoint}"
        try:
            async with aiohttp.ClientSession() as session:
                if payload is not None:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            return f"Error: {endpoint} returned {resp.status}: {text[:200]}"
                        return await resp.json()
                else:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            return f"Error: {endpoint} returned {resp.status}: {text[:200]}"
                        return await resp.json()
        except aiohttp.ClientError as e:
            return f"Error: Cannot connect to ofcode-server ({self.base_url}): {e}"
        except Exception as e:
            return f"Error: API call failed: {e}"

    async def rag_search(self, query: str, product: str = "", top_k: int = 5) -> Any:
        return await self._call("/api/rag/search", {"query": query, "product": product, "top_k": top_k})

    async def webdoc_search(self, query: str, product: str = "", top_k: int = 5) -> Any:
        return await self._call("/api/webdoc/search", {"query": query, "product": product, "top_k": top_k})

    async def search_of7(self, query: str, module: str = "", file_type: str = "both") -> Any:
        return await self._call("/api/search", {"query": query, "module": module, "file_type": file_type, "max_results": 30})

    async def get_function_def(self, name: str) -> Any:
        return await self._call("/api/function", {"function_name": name})

    async def get_module_info(self, module: str) -> Any:
        return await self._call("/api/module", {"module": module})

    async def get_header_api(self, name: str) -> Any:
        return await self._call("/api/header", {"header_name": name})

    async def get_architecture(self) -> Any:
        return await self._call("/api/architecture")

    async def find_callers(self, name: str, module: str = "") -> Any:
        return await self._call("/api/callers", {"function_name": name, "module": module})

    async def rebuild_index(self) -> Any:
        return await self._call("/api/rebuild-index", {})

    async def crawl_webdoc(self, product: str = "") -> Any:
        return await self._call("/api/webdoc/crawl", {"product": product}, timeout=120)


_ofcode_client: Optional[OfcodeClient] = None


def get_ofcode_client() -> OfcodeClient:
    global _ofcode_client
    if _ofcode_client is None:
        _ofcode_client = OfcodeClient()
    return _ofcode_client


# =============================================================================
# Product Detection + Auto-RAG Context Injection (CLI와 동일)
# =============================================================================

def detect_product_from_query(text: str) -> tuple[str, bool]:
    text_lower = text.lower()
    for keyword, product in _PRODUCT_KEYWORDS.items():
        if keyword in text_lower:
            return product, True
    for keyword in _TOPIC_KEYWORDS:
        if keyword.lower() in text_lower:
            return "", True
    return "", False


async def _fetch_summary_context(query: str) -> str:
    """요약본(commands, error-codes, glossary 등)에서 관련 컨텍스트를 검색.

    agentic_rag_service._search_summaries()와 동일 로직의 경량 버전.
    BM25 전체 검색 1회 + 키워드별 dict 직접 조회만 사용 (<100ms).
    """
    try:
        from .summary_bm25_service import get_summary_bm25_service
        from .summary_search_service import get_summary_search_service

        bm25 = get_summary_bm25_service()
        summary_svc = get_summary_search_service()

        results: list[str] = []
        seen: set = set()

        def _add(source: str, content: str):
            key = f"{source}:{content[:80]}"
            if key not in seen and content.strip():
                seen.add(key)
                results.append(f"[{source}] {content}")

        # Phase 1: 키워드 추출 (대문자 약어 + 소문자 명령어)
        keywords = re.findall(r"([A-Za-z][A-Za-z0-9_]{2,})", query)
        keywords = list(dict.fromkeys(keywords))[:8]

        # Phase 2a: O(1) 직접 인덱스 조회
        for kw in keywords:
            # Glossary
            try:
                g = await summary_svc.search_glossary(kw)
                if g:
                    full = g.get("full_name", "")
                    desc = g.get("description", "")
                    _add(f"glossary/{kw}", f"{kw} ({full}): {desc[:400]}" if full else f"{kw}: {desc[:400]}")
            except Exception:
                pass

            # Command 인덱스 직접 조회
            kw_lower = kw.lower()
            if hasattr(bm25, '_command_index'):
                cmd_docs = bm25._command_index.get(kw_lower, [])
                for doc in cmd_docs[:2]:
                    if doc and doc.content:
                        _add(doc.source_file or f"commands/{kw}", doc.content[:500])

            # Error code 인덱스 직접 조회
            if hasattr(bm25, '_error_code_index'):
                err_doc = bm25._error_code_index.get(kw.upper()) or bm25._error_code_index.get(kw)
                if err_doc and err_doc.content:
                    _add(err_doc.source_file or f"errors/{kw}", err_doc.content[:400])

        # Phase 2b: BM25 get_scores() (search() 우회 — 경량 검색)
        try:
            import numpy as np
            if bm25._initialized and bm25._bm25 is not None:
                tokens = bm25._tokenize(query)
                scores = bm25._bm25.get_scores(tokens)
                top_indices = np.argsort(scores)[::-1][:10]
                for idx in top_indices:
                    if scores[idx] <= 0:
                        break
                    doc = bm25._documents[idx]
                    if doc and doc.content:
                        _add(doc.source_file or "bm25", doc.content[:500])
        except Exception as e:
            logger.warning(f"Auto-RAG summary BM25 error: {e}")

        # Phase 2c: enrich_query (에러코드 + 용어 보강)
        try:
            enriched = await summary_svc.enrich_query(query)
            if enriched and enriched != query:
                _add("Enriched", enriched[len(query):])
        except Exception:
            pass

        return "\n\n".join(results) if results else ""

    except Exception as e:
        logger.warning(f"Auto-RAG summary search error: {e}")
        return ""


# 컨텍스트 크기 제한: context_limit=8192에서 2회차 iteration 출력 예산 확보
# system(~1700tok) + user+ctx + tool_result → iteration 2 output ≥ 2000tok 보장
_MAX_SUMMARY_CONTEXT_CHARS = 1200   # summary: ~600 tokens
_MAX_VECTOR_CONTEXT_CHARS = 1500    # vector: ~750 tokens
_MAX_TOTAL_CONTEXT_CHARS = 2500     # combined hard cap


async def auto_rag_context(query: str, product: str = "") -> str:
    """CLI의 _auto_rag_context() + 요약본 검색 통합.

    1단계: 요약본(commands/error-codes/glossary) 검색 (<100ms)
    2단계: ofcode-server vector search (기존)
    두 결과를 합산하여 LLM 컨텍스트로 주입.

    주의: context_limit=8192에서 2회차 iteration(tool_call 후)의 출력 예산을
    확보하기 위해, 총 컨텍스트 크기를 _MAX_TOTAL_CONTEXT_CHARS로 제한.
    """
    parts: list[str] = []
    total_chars = 0

    # 1단계: 요약본 검색 (빠름, 로컬)
    t0 = time.time()
    summary_ctx = await _fetch_summary_context(query)
    t_summary = (time.time() - t0) * 1000
    if summary_ctx:
        if len(summary_ctx) > _MAX_SUMMARY_CONTEXT_CHARS:
            summary_ctx = summary_ctx[:_MAX_SUMMARY_CONTEXT_CHARS] + "\n...(truncated)"
        parts.append("")
        parts.append("[Summary Reference (commands, error-codes, glossary)]")
        parts.append(summary_ctx)
        parts.append("[End of Summary Reference]")
        total_chars += len(summary_ctx)
        logger.info(f"Auto-RAG summary context injected: {len(summary_ctx)} chars, {t_summary:.0f}ms")

    # 2단계: Vector search (유틸리티 제품은 부모 제품으로 확장 검색 + 쿼리 보강)
    client = get_ofcode_client()
    search_products = _expand_search_product(product)
    all_entries: list[dict] = []
    seen_docs: set[str] = set()

    # 유틸리티 제품은 쿼리에 관련 기술 용어 추가 (임베딩 매칭 향상)
    # 단, 긴 쿼리(코드/구문 포함)에는 적용하지 않음 — 노이즈 유발
    enriched_query = query
    is_short_query = len(query) < 80
    if product in _UTILITY_QUERY_ENRICHMENT and is_short_query:
        enriched_query = f"{query} {_UTILITY_QUERY_ENRICHMENT[product]}"
        logger.info(f"Auto-RAG query enriched: '{query}' → '{enriched_query}'")

    for sp in search_products:
        rag_result = await client.rag_search(enriched_query, sp, top_k=5)
        if not isinstance(rag_result, str):
            for r in rag_result.get("results", []):
                doc_key = f"{r.get('doc_name', '')}:{r.get('page_number', '')}"
                if doc_key not in seen_docs:
                    seen_docs.add(doc_key)
                    all_entries.append(r)
        else:
            logger.warning(f"Auto-RAG vector search failed (product={sp}): {rag_result}")

    # 원래 제품으로도 검색 (부모 검색과 중복 방지)
    # 유틸리티 제품은 부모 검색으로 충분 → 추가 검색 시 IMS 이슈 등 무관한 결과가 오염됨
    if product and product not in search_products and product not in _UTILITY_SEARCH_PRODUCTS:
        rag_result = await client.rag_search(query, product, top_k=3)
        if not isinstance(rag_result, str):
            for r in rag_result.get("results", []):
                doc_key = f"{r.get('doc_name', '')}:{r.get('page_number', '')}"
                if doc_key not in seen_docs:
                    seen_docs.add(doc_key)
                    all_entries.append(r)

    # score 내림차순 정렬
    all_entries.sort(key=lambda x: x.get("score", 0), reverse=True)

    if all_entries:
        doc_lines: list[str] = []
        ims_lines: list[str] = []
        vec_chars = 0
        for r in all_entries:
            doc = r.get("doc_name", "")
            short_name = doc.split("/")[-1] if "/" in doc else doc
            page = r.get("page_number", "")
            score = r.get("score", 0)
            content = r.get("content", "").strip()
            if content:
                entry = f"--- {short_name} (p.{page}, relevance: {score}) ---\n{content}"
                if vec_chars + len(entry) > _MAX_VECTOR_CONTEXT_CHARS:
                    break
                if "ims" in doc.lower() or "issue" in doc.lower():
                    ims_lines.append(entry)
                else:
                    doc_lines.append(entry)
                vec_chars += len(entry)
        # 문서 컨텍스트 우선, IMS 이슈는 보조
        # 유틸리티 제품(protrieve, prosort 등)은 IMS 이슈 제외 (무관한 결과 오염 방지)
        if doc_lines:
            parts.append("")
            parts.append("[Reference Documentation from Official Manuals]")
            parts.extend(doc_lines)
            parts.append("[End of Reference Documentation]")
        if ims_lines and product not in _UTILITY_SEARCH_PRODUCTS:
            parts.append("")
            parts.append("[Related IMS Issues]")
            parts.extend(ims_lines)
            parts.append("[End of IMS Issues]")
        total_chars += vec_chars
        if product in _UTILITY_SEARCH_PRODUCTS:
            logger.info(
                f"Auto-RAG utility expansion: {product} → {search_products}, "
                f"docs={len(doc_lines)}, ims={len(ims_lines)}"
            )

    if not parts:
        return ""

    # Hard cap: 총 컨텍스트 제한
    result = "\n".join(parts)
    if len(result) > _MAX_TOTAL_CONTEXT_CHARS:
        result = result[:_MAX_TOTAL_CONTEXT_CHARS] + "\n...(context truncated for output budget)"

    # 코드/구문 분석 요청 감지: 해석, 분석, 해줘 + 긴 쿼리
    _code_analysis_patterns = ["해석", "해줘", "분석", "説明", "解析", "analyze", "explain", "parse"]
    is_code_analysis = len(query) > 80 and any(p in query for p in _code_analysis_patterns)

    if is_code_analysis:
        result += (
            "\nNOTE: The user is asking you to ANALYZE or EXPLAIN code/syntax. "
            "Use the reference context above if relevant, but you MAY also use your "
            "general knowledge of the programming language (CA-Easytrieve Plus, ProTrieve, "
            "JCL, COBOL, etc.) to interpret the code. "
            "Always provide a detailed, structured explanation of each statement."
        )
    else:
        result += (
            "\nNOTE: This is preliminary context from summary + vector search. "
            "If the user's specific question is NOT directly answered above, "
            "you MUST call search_webdoc to find more relevant documentation. "
            "Do NOT fabricate information that is not found in tool results."
        )
    logger.info(f"Auto-RAG total context: {len(result)} chars")
    return result


# =============================================================================
# Tool Dispatch (CLI와 동일 포맷)
# =============================================================================

def _parse_sources_from_tool_result(result: str) -> list[dict]:
    """search_webdoc 결과 텍스트 및 pre-injected 컨텍스트에서 소스 참조 정보를 추출."""
    sources: list[dict] = []
    seen: set[str] = set()

    # Pre-injected context: --- doc_name (p.page, relevance: score) ---
    for m in re.finditer(
        r'---\s+(.+?)\s+\(p\.(\S+?),\s*relevance:\s*([\d.]+)\)\s*---', result
    ):
        doc_name, page, score = m.group(1), m.group(2), float(m.group(3))
        key = f"rag:{doc_name}:{page}"
        if key not in seen:
            seen.add(key)
            sources.append({
                "doc_name": doc_name,
                "source_page": page,
                "score": score,
                "domain": "manual_rag",
            })

    # Manual RAG: [doc_name p.page] (score: X.XX)
    for m in re.finditer(
        r'\[([^\]]+?)\s+p\.(\S+)\]\s*\(score:\s*([\d.]+)\)', result
    ):
        doc_name, page, score = m.group(1), m.group(2), float(m.group(3))
        key = f"rag:{doc_name}:{page}"
        if key not in seen:
            seen.add(key)
            sources.append({
                "doc_name": doc_name,
                "source_page": page,
                "score": score,
                "domain": "manual_rag",
            })

    # Web docs: [product] title (score: X.XX) + URL: url
    lines = result.split("\n")
    for i, line in enumerate(lines):
        wm = re.match(r'\[([^\]]+)\]\s+(.+?)\s+\(score:\s*([\d.]+)\)', line)
        if wm:
            product, title, score = wm.group(1), wm.group(2), float(wm.group(3))
            url = ""
            if i + 1 < len(lines):
                um = re.match(r'\s+URL:\s+(https?://\S+)', lines[i + 1])
                if um:
                    url = um.group(1)
            key = f"web:{url or title}"
            if key not in seen:
                seen.add(key)
                sources.append({
                    "doc_name": title,
                    "source_page": url,
                    "score": score,
                    "domain": "web_doc",
                    "product": product,
                    "url": url,
                })

    return sources


def _format_rag_entries(entries: list) -> list[str]:
    lines = []
    for r in entries:
        doc = r.get("doc_name", "")
        short_name = doc.split("/")[-1] if "/" in doc else doc
        page = r.get("page_number", "")
        score = r.get("score", 0)
        lines.append(f"[{short_name} p.{page}] (score: {score})")
        content = r.get("content", "").strip()
        if content:
            lines.append(f"  {content}")
        lines.append("")
    return lines


def _format_webdoc_entries(entries: list) -> list[str]:
    lines = []
    for r in entries:
        lines.append(f"[{r.get('product', '')}] {r['title']} (score: {r['score']})")
        lines.append(f"  URL: {r['url']}")
        if r.get("headings"):
            lines.append(f"  Sections: {', '.join(r['headings'][:3])}")
        if r.get("snippet"):
            lines.append(f"  Preview: {r['snippet'][:150]}...")
        lines.append("")
    return lines


async def dispatch_tool(name: str, args: dict) -> str:
    """도구 이름 + 인자 → ofcode-server 호출 → 결과 문자열.
    base tools (read_file 등)은 웹 UI에서 실행 불가 → 안내 메시지."""
    client = get_ofcode_client()

    # Base tools — 웹 UI에서는 실행 불가, 안내 메시지 반환
    if name in ("read_file", "write_file", "edit_file", "bash",
                "grep_search", "glob_search", "list_directory"):
        return (
            f"Tool '{name}' is not available in web UI mode. "
            "Use search_webdoc, search_of7, or other OpenFrame tools instead."
        )

    if name == "search_webdoc":
        return await _tool_search_webdoc(client, args.get("query", ""), args.get("product", ""))
    elif name == "search_of7":
        result = await client.search_of7(args.get("query", ""), args.get("module", ""), args.get("file_type", "both"))
        if isinstance(result, str):
            return result
        entries = result.get("results", [])
        if not entries:
            return "No matches found."
        lines = [f"{r['file']}:{r['line']}: {r['content']}" for r in entries]
        if result.get("truncated"):
            lines.append("... (max results reached)")
        return "\n".join(lines)
    elif name == "get_module_info":
        result = await client.get_module_info(args.get("module", ""))
        if isinstance(result, str):
            return result
        lines = [f"Module: {result.get('module', '')}/"]
        lines.append(f"Description: {result.get('description', 'N/A')}")
        lines.append(f"Files: {result.get('c_files', 0)} .c + {result.get('h_files', 0)} .h = {result.get('total_files', 0)} total")
        subdirs = result.get("subdirs", [])
        subdirs_desc = result.get("subdirs_desc", {})
        lines.append(f"Subdirectories ({len(subdirs)}):")
        for sd in subdirs:
            desc = subdirs_desc.get(sd, "")
            lines.append(f"  {sd}/ - {desc}" if desc else f"  {sd}/")
        return "\n".join(lines)
    elif name == "get_function_def":
        result = await client.get_function_def(args.get("function_name", ""))
        if isinstance(result, str):
            return result
        if not result.get("found"):
            matches = result.get("matches", [])
            if matches:
                lines = [result.get("message", f"Multiple matches:")]
                for m in matches:
                    lines.append(f"  {m['name']}  ({m['file']}:{m['line']})")
                return "\n".join(lines)
            return result.get("message", "Function not found.")
        return f"Function: {result.get('name', '')} in {result.get('file', '')}:{result.get('line', '')}"
    elif name == "get_header_api":
        result = await client.get_header_api(args.get("header_name", ""))
        if isinstance(result, str):
            return result
        if not result.get("found"):
            suggestions = result.get("suggestions", [])
            if suggestions:
                return f"Header not found. Did you mean:\n" + "\n".join(suggestions)
            return "Header not found."
        lines = [f"Header: {result.get('header', '')}"]
        lines.append(f"Path: {result.get('path', '')}")
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
    elif name == "get_architecture":
        result = await client.get_architecture()
        if isinstance(result, str):
            return result
        return result.get("diagram", "Architecture diagram not available.")
    elif name == "find_callers":
        result = await client.find_callers(args.get("function_name", ""), args.get("module", ""))
        if isinstance(result, str):
            return result
        entries = result.get("results", [])
        if not entries:
            return f"No callers found."
        lines = [f"{r['file']}:{r['line']}: {r['content']}" for r in entries]
        if result.get("truncated"):
            lines.append("... (max results reached)")
        return "\n".join(lines)
    else:
        return f"Unknown tool: {name}"


def _all_webdoc_scores_low(lines: list, threshold: float = 0.3) -> bool:
    """web doc 결과 라인에서 score 추출하여 모두 threshold 미만인지 확인."""
    import re
    scores = []
    for line in lines:
        m = re.search(r'\(score:\s*([\d.]+)\)', line)
        if m:
            scores.append(float(m.group(1)))
    return bool(scores) and all(s < threshold for s in scores)


async def _tool_search_webdoc(client: OfcodeClient, query: str, product: str = "") -> str:
    """search_webdoc: 5-step 통합 검색 (CLI tool_search_webdoc과 동일)."""
    lines: list[str] = []
    module = _PRODUCT_TO_MODULE.get(product.lower(), "") if product else ""

    # Step 0: Neo4j RAG (유틸리티 제품은 부모 제품으로 확장 검색 + 쿼리 보강)
    search_products = _expand_search_product(product)
    seen_rag: set[str] = set()
    all_rag_entries: list[dict] = []

    enriched_query = query
    if product in _UTILITY_QUERY_ENRICHMENT and len(query) < 80:
        enriched_query = f"{query} {_UTILITY_QUERY_ENRICHMENT[product]}"

    for sp in search_products:
        rag_result = await client.rag_search(enriched_query, sp, top_k=3)
        if not isinstance(rag_result, str):
            for r in rag_result.get("results", []):
                key = f"{r.get('doc_name', '')}:{r.get('page_number', '')}"
                if key not in seen_rag:
                    seen_rag.add(key)
                    all_rag_entries.append(r)

    # 원래 제품으로도 검색 (IMS 이슈 등)
    if product and product not in search_products:
        rag_result = await client.rag_search(query, product, top_k=3)
        if not isinstance(rag_result, str):
            for r in rag_result.get("results", []):
                key = f"{r.get('doc_name', '')}:{r.get('page_number', '')}"
                if key not in seen_rag:
                    seen_rag.add(key)
                    all_rag_entries.append(r)

    all_rag_entries.sort(key=lambda x: x.get("score", 0), reverse=True)
    if all_rag_entries:
        header = f"Manual RAG ({product})" if product else "Manual RAG"
        lines.append(f"── {header} ──")
        lines.extend(_format_rag_entries(all_rag_entries))

    # Step 1: Web docs (product-filtered)
    if product:
        result = await client.webdoc_search(query, product, top_k=3)
        if not isinstance(result, str):
            entries = result.get("results", [])
            if entries:
                lines.append(f"── Web docs ({product}) ──")
                lines.extend(_format_webdoc_entries(entries))

    # Step 2: Web docs (all products)
    result = await client.webdoc_search(query, "", top_k=3)
    if not isinstance(result, str):
        entries = result.get("results", [])
        if entries:
            step1_urls = {l.split("URL: ")[-1].strip() for l in lines if "URL: " in l}
            new_entries = [e for e in entries if e.get("url") not in step1_urls]
            if new_entries:
                lines.append("── Web docs (all products) ──")
                lines.extend(_format_webdoc_entries(new_entries))

    # Step 3: of7 source code (product module)
    if module:
        of7 = await client.search_of7(query, module, "both")
        if not isinstance(of7, str):
            of7_entries = of7.get("results", [])
            if of7_entries:
                lines.append(f"── of7 source code ({module}/) ──")
                for r in of7_entries[:10]:
                    lines.append(f"  {r['file']}:{r['line']}: {r['content']}")

    # Step 4: of7 source code (all modules)
    of7 = await client.search_of7(query, "", "both")
    if not isinstance(of7, str):
        of7_entries = of7.get("results", [])
        if of7_entries:
            step3_files = {l.strip().split(":")[0] for l in lines if "── of7" not in l and ":" in l and "/" in l}
            new_of7 = [r for r in of7_entries if r.get("file", "") not in step3_files]
            if new_of7:
                lines.append("── of7 source code (all modules) ──")
                for r in new_of7[:10]:
                    lines.append(f"  {r['file']}:{r['line']}: {r['content']}")

    if not lines:
        return f"No results found for '{query}' in web docs or of7 source code."

    result_text = "\n".join(lines)
    # 저스코어 경고: web doc 결과의 score가 모두 낮으면 LLM에 재검색 유도
    if _all_webdoc_scores_low(lines, threshold=0.3):
        result_text += (
            "\n\n⚠️ WARNING: All web doc results have very low relevance scores (< 0.3). "
            "The product parameter may be incorrect. Try searching with a different product "
            "(e.g., 'base', 'batch', '') or use search_of7/get_header_api for C API details."
        )
    return result_text


# =============================================================================
# Slash Command Handler
# =============================================================================

async def handle_slash_command(command: str) -> AsyncGenerator[dict, None]:
    parts = command.strip().split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/help":
        yield {"type": "slash_result", "content": HELP_TEXT}
    elif cmd == "/clear":
        yield {"type": "slash_clear"}
    elif cmd == "/model":
        llm_url = os.getenv("LEARNING_LLM_URL", "http://192.168.8.11:12810/v1")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{llm_url}/models", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m.get("id", "") for m in data.get("data", [])]
                        yield {"type": "slash_result", "content": f"**vLLM Models:** {', '.join(models)}"}
                    else:
                        yield {"type": "slash_result", "content": f"vLLM server error: {resp.status}"}
        except Exception as e:
            yield {"type": "slash_result", "content": f"Cannot connect to vLLM: {e}"}
    elif cmd == "/tokens":
        yield {"type": "slash_result", "content": "Token tracking is available in the server logs."}
    elif cmd == "/reindex":
        client = get_ofcode_client()
        result = await client.rebuild_index()
        if isinstance(result, str):
            yield {"type": "slash_result", "content": f"Reindex failed: {result}"}
        else:
            yield {"type": "slash_result", "content": f"Index rebuilt: {json.dumps(result, ensure_ascii=False)}"}
    elif cmd == "/crawl-webdoc":
        client = get_ofcode_client()
        result = await client.crawl_webdoc(arg)
        if isinstance(result, str):
            yield {"type": "slash_result", "content": f"Crawl failed: {result}"}
        else:
            yield {"type": "slash_result", "content": f"Crawl complete: {json.dumps(result, ensure_ascii=False)}"}
    else:
        yield {"type": "slash_result", "content": f"Unknown command: `{cmd}`\n\n{HELP_TEXT}"}


# =============================================================================
# Model Auto-Detection (CLI _detect_model_and_context)
# =============================================================================

_detected_model: Optional[str] = None
_detected_context_length: Optional[int] = None
_available_model_ids: set[str] = set()  # vLLM에 로드된 모든 모델 ID 캐시


async def _detect_model() -> tuple[str, int]:
    """vLLM /v1/models API에서 모델 이름과 context length 자동 감지."""
    global _detected_model, _detected_context_length, _available_model_ids
    if _detected_model:
        return _detected_model, _detected_context_length or DEFAULT_CONTEXT_LENGTH

    llm_url = os.getenv("LEARNING_LLM_URL", "http://192.168.8.11:12810/v1")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{llm_url}/models",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = data.get("data", [])
                    if models:
                        m = models[0]
                        _detected_model = m.get("id", "")
                        _detected_context_length = m.get("max_model_len") or DEFAULT_CONTEXT_LENGTH
                        _available_model_ids = {mi.get("id", "") for mi in models}
                        logger.info(
                            f"Auto-detected model: {_detected_model}, "
                            f"context: {_detected_context_length}, "
                            f"available: {_available_model_ids}"
                        )
                        return _detected_model, _detected_context_length
    except Exception as e:
        logger.warning(f"Model auto-detect failed: {e}")

    # Fallback
    fallback = os.getenv("LEARNING_LLM_MODEL", "/opt/models/qwen3-32b")
    _detected_model = fallback
    _detected_context_length = DEFAULT_CONTEXT_LENGTH
    return _detected_model, _detected_context_length


# =============================================================================
# Progressive Compression (CLI Section 7: progressive_compress)
# =============================================================================

def _progressive_compress(messages: list, tools: list, context_limit: int) -> list:
    """CLI의 progressive_compress()를 비동기 환경용으로 포팅.
    Step 1-3만 구현 (Step 4 LLM 요약은 비동기 특성상 agent loop 내에서 처리)."""
    target = context_limit - MIN_OUTPUT_TOKENS - TOKEN_BUFFER

    # Step 1: Tool result 및 긴 assistant content 절삭
    for msg in messages[1:]:
        if msg.get("role") == "tool":
            content = msg.get("content") or ""
            content_lines = content.split("\n")
            if len(content_lines) > TOOL_RESULT_TRUNCATE_LINES:
                msg["content"] = "\n".join(content_lines[:TOOL_RESULT_TRUNCATE_LINES]) + f"\n...(truncated {len(content_lines)} lines)"
        elif msg.get("role") == "assistant":
            content = msg.get("content") or ""
            if len(content) > 800:
                msg["content"] = content[:800] + "\n...(truncated)"

    if estimate_messages_tokens(messages, tools) <= target:
        return messages

    # Step 2: 오래된 메시지 드롭 (system + 최근 N개만 유지)
    if len(messages) > 1 + RECENT_MESSAGES_TO_KEEP:
        system_msg = messages[0]
        recent = messages[-RECENT_MESSAGES_TO_KEEP:]
        messages = [system_msg] + recent
        logger.info(f"Compression Step 2: kept {RECENT_MESSAGES_TO_KEEP} recent messages")

    if estimate_messages_tokens(messages, tools) <= target:
        return messages

    # Step 3: 남은 메시지 공격적 절삭
    max_chars = 300
    for msg in messages[1:]:
        content = msg.get("content") or ""
        if len(content) > max_chars:
            msg["content"] = content[:max_chars] + "\n...(truncated)"

    if estimate_messages_tokens(messages, tools) <= target:
        return messages

    # Emergency: system + 마지막 메시지만 유지
    if len(messages) > 2:
        messages = [messages[0], messages[-1]]
        logger.warning("Emergency compression: kept only last message")

    return messages


def _calculate_max_tokens(messages: list, tools: list, context_limit: int, requested_max: int = DEFAULT_MAX_TOKENS) -> int:
    """CLI의 calculate_max_tokens()와 동일: 예산 기반 max_tokens 계산."""
    input_tokens = estimate_messages_tokens(messages, tools)
    available = context_limit - input_tokens - TOKEN_BUFFER
    if available >= MIN_OUTPUT_TOKENS:
        return min(requested_max, available)
    return max(MIN_OUTPUT_TOKENS, min(requested_max, available))


# =============================================================================
# Agent Loop: vLLM streaming (CLI Section 7: stream_response + agent_loop)
# =============================================================================

async def stream_auto_rag(
    message: str,
    history: Optional[list] = None,
    product_ids: Optional[list] = None,
    enable_thinking: bool = False,
    initial_context: Optional[str] = None,
    language: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """Auto-RAG Agent Loop (SSE イベント生成).

    CLI의 LocalCoder.agent_loop() + stream_response()를 정확히 포팅.
    핵심 차이점: CLI는 OpenAI SDK sync, 여기는 aiohttp async.

    Args:
        initial_context: 사전 수집된 검색 결과 (RAG 모드에서 위임 시 사용).
                         제공 시 auto_rag_context() 호출을 건너뛰고
                         이 컨텍스트를 직접 주입.
    """
    start = time.time()

    # Slash command interception
    if message.strip().startswith("/"):
        async for event in handle_slash_command(message.strip()):
            yield event
        return

    # Model auto-detection (CLI: _detect_model_and_context)
    model, context_limit = await _detect_model()
    llm_url = os.getenv("LEARNING_LLM_URL", "http://192.168.8.11:12810/v1")
    chat_url = f"{llm_url}/chat/completions"

    # 1. Product detection + context injection (CLI: process() 내 auto-rag)
    product, is_of = detect_product_from_query(message)
    augmented_message = message

    # Multi-LoRA: resolve adapter model name from product (CLI: _get_model_for_request)
    adapter_model = model  # default: base model
    if product and product in MULTI_LORA_PRODUCT_MAPPING:
        mapping = MULTI_LORA_PRODUCT_MAPPING[product]
        candidate = mapping.get("adapter", product)
        # 어댑터가 vLLM에 실제 로드되어 있는지 확인 후 폴백
        if _available_model_ids and candidate not in _available_model_ids:
            logger.info(
                f"Auto-RAG Multi-LoRA: product={product} -> adapter={candidate} "
                f"NOT loaded, using base model ({model})"
            )
        else:
            adapter_model = candidate
            logger.info(f"Auto-RAG Multi-LoRA: product={product} -> adapter={adapter_model}")

    # 1a. Code analysis detection (BEFORE context injection):
    #     코드/구문 분석 요청 시 RAG 컨텍스트 주입 및 tool 사용 비활성화
    #     (IMS 이슈 등 무관한 검색 결과가 코드 해석을 방해하는 것을 방지)
    _code_analysis_kw = ["해석", "분석", "구문", "説明", "解析", "解説", "analyze", "explain", "parse", "interpret"]
    is_code_analysis = len(message) > 80 and any(p in message for p in _code_analysis_kw)
    active_tools = [] if is_code_analysis else AUTO_RAG_TOOLS

    if is_code_analysis:
        # 코드 분석 모드: RAG 컨텍스트 대신 분석 지시 추가
        augmented_message = message + (
            "\n\nINSTRUCTION: Analyze and explain the code/syntax above step by step. "
            "Describe each statement (REPORT, FILE, JOB, etc.) and its parameters. "
            "Use your knowledge of the programming language (CA-Easytrieve Plus, ProTrieve, "
            "JCL, COBOL, etc.) to provide a detailed, structured explanation."
        )
        logger.info(f"Auto-RAG code analysis mode: tools disabled, context skipped (query len={len(message)})")
    elif initial_context:
        # RAG 모드에서 위임: 사전 수집된 컨텍스트 사용 (중복 검색 방지)
        augmented_message = message + "\n" + initial_context
        logger.info(f"Auto-RAG using pre-collected context: {len(initial_context)} chars")
    elif is_of:
        yield {"type": "search_progress", "step": "auto_rag_context", "progress": 0.1}
        rag_context = await auto_rag_context(message, product)
        if rag_context:
            augmented_message = message + "\n" + rag_context
            logger.info(f"Auto-RAG context injected: product={product}, context_len={len(rag_context)}")

    # 3. Build messages (CLI와 동일 구조)
    system_content = OPENFRAME_SYSTEM_PROMPT

    # 응답 언어 지시: 사용자 language 설정을 따름
    _lang_map = {"ja": "Japanese", "ko": "Korean", "en": "English", "zh": "Chinese"}
    _resp_lang = _lang_map.get(language or "ja", "Japanese")
    system_content += (
        f"\n\nIMPORTANT - Response Language: "
        f"You MUST respond in {_resp_lang}. "
        f"All explanations, descriptions, and analysis must be written in {_resp_lang}. "
        f"Only switch language if the user explicitly requests a different language in their message."
    )

    if enable_thinking:
        system_content += (
            "\n\nIMPORTANT: Keep your <think> reasoning concise (under 300 tokens). "
            "Focus output tokens on the actual answer, not internal reasoning."
        )
    messages: list[dict] = [
        {"role": "system", "content": system_content},
    ]
    if history:
        for h in history[-10:]:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": augmented_message})

    yield {"type": "agent_mode", "mode": "auto_rag", "auto_detected": False}

    # 4. Agent loop (CLI: agent_loop — max 25 iterations)
    was_truncated = False
    collected_sources: list[dict] = []  # search_webdoc 결과에서 추출한 소스 참조

    # Pre-injected 컨텍스트에서 소스 참조 추출 (tool call 없이 답변할 경우 대비)
    if augmented_message != message:
        pre_sources = _parse_sources_from_tool_result(augmented_message)
        if pre_sources:
            collected_sources.extend(pre_sources)
            logger.info(f"Auto-RAG pre-injected sources: {len(pre_sources)}")
    for iteration in range(MAX_AGENT_ITERATIONS):
        # Proactive budget check (CLI: calculate_max_tokens)
        messages = _progressive_compress(messages, active_tools, context_limit)
        effective_max_tokens = _calculate_max_tokens(messages, active_tools, context_limit)

        # Qwen3 thinking 제어: enable_thinking=False → <think> 블록 비활성화
        payload = {
            "model": adapter_model,
            "messages": messages,
            "max_tokens": effective_max_tokens,
            "temperature": 0.7,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
            "repetition_penalty": 1.1,
            "frequency_penalty": 0.3,
        }
        if active_tools:
            payload["tools"] = active_tools

        accumulated_content = ""
        display_content = ""
        tool_calls_data: dict[int, dict] = {}
        think_filter = ThinkFilter()
        truncated_by_length = False
        repetition_detected = False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    chat_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 400:
                        # CLI: _create_stream error handling — 400 에러 시 토큰 보정
                        error_text = await resp.text()
                        logger.warning(f"vLLM 400 error: {error_text[:300]}")

                        # Parse actual token count from error
                        match = re.search(r"your request has (\d+) input tokens", error_text)
                        if match:
                            actual_input = int(match.group(1))
                            estimated = estimate_messages_tokens(messages, AUTO_RAG_TOOLS)
                            update_token_correction(estimated, actual_input)

                            # 간단 재시도: max_tokens 줄여서
                            available = context_limit - actual_input - 50
                            if available >= MIN_OUTPUT_TOKENS:
                                payload["max_tokens"] = available
                                async with session.post(
                                    chat_url,
                                    json=payload,
                                    timeout=aiohttp.ClientTimeout(total=120),
                                ) as retry_resp:
                                    if retry_resp.status != 200:
                                        yield {"type": "error", "message": f"LLM retry error: {retry_resp.status}"}
                                        return
                                    # 재시도 성공 — 아래 스트리밍 로직으로 연결
                                    resp = retry_resp
                            else:
                                # 압축 후 재시도
                                messages = _progressive_compress(messages, AUTO_RAG_TOOLS, context_limit)
                                new_max = _calculate_max_tokens(messages, AUTO_RAG_TOOLS, context_limit)
                                payload["messages"] = messages
                                payload["max_tokens"] = new_max
                                async with session.post(
                                    chat_url,
                                    json=payload,
                                    timeout=aiohttp.ClientTimeout(total=120),
                                ) as retry_resp:
                                    if retry_resp.status != 200:
                                        yield {"type": "error", "message": f"LLM retry error after compression: {retry_resp.status}"}
                                        return
                                    resp = retry_resp
                        else:
                            yield {"type": "error", "message": f"LLM error: 400 - {error_text[:200]}"}
                            return

                    elif resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Auto-RAG vLLM error: {resp.status} - {error_text[:300]}")
                        yield {"type": "error", "message": f"LLM error: {resp.status}"}
                        return

                    # Stream response (CLI: stream_response — ThinkFilter + tool_calls)
                    async for line in resp.content:
                        line_str = line.decode("utf-8").strip()
                        if not line_str or not line_str.startswith("data: "):
                            continue
                        data_str = line_str[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            if not chunk.get("choices"):
                                continue
                            delta = chunk["choices"][0].get("delta", {})

                            # Text content — ThinkFilter 적용 (CLI와 동일)
                            token = delta.get("content", "")
                            if token:
                                accumulated_content += token
                                display_text, thinking_text = think_filter.feed(token)
                                if display_text:
                                    display_content += display_text
                                    yield {"type": "llm_token", "token": display_text}
                                if thinking_text and enable_thinking:
                                    yield {"type": "thinking", "content": thinking_text}

                                # 반복 감지: display 200자 이상일 때 마지막 150자가 이전에 등장했으면 중단
                                if len(display_content) > 200:
                                    tail = display_content[-150:]
                                    if display_content[:-150].find(tail) >= 0:
                                        repetition_detected = True
                                        logger.warning(
                                            f"[Auto-RAG] Repetition detected at {len(display_content)} chars, "
                                            f"stopping generation"
                                        )
                                        break

                            # finish_reason 감지 (length = max_tokens 도달로 잘림)
                            fr = chunk["choices"][0].get("finish_reason")
                            if fr == "length":
                                truncated_by_length = True
                                logger.warning(
                                    f"[Auto-RAG] finish_reason=length at iteration {iteration+1} "
                                    f"(output truncated, effective_max_tokens={effective_max_tokens})"
                                )
                            elif fr is not None:
                                logger.info(
                                    f"[Auto-RAG] finish_reason={fr} at iteration {iteration+1}, "
                                    f"accumulated={len(accumulated_content)} chars, "
                                    f"display={len(display_content)} chars, "
                                    f"max_tokens={effective_max_tokens}"
                                )

                            # Tool calls (streamed incrementally — CLI와 동일)
                            tc_list = delta.get("tool_calls")
                            if tc_list:
                                for tc_delta in tc_list:
                                    idx = tc_delta.get("index", 0)
                                    if idx not in tool_calls_data:
                                        tool_calls_data[idx] = {"id": "", "name": "", "arguments": ""}
                                    if tc_delta.get("id"):
                                        tool_calls_data[idx]["id"] = tc_delta["id"]
                                    if tc_delta.get("function"):
                                        if tc_delta["function"].get("name"):
                                            tool_calls_data[idx]["name"] = tc_delta["function"]["name"]
                                        if tc_delta["function"].get("arguments"):
                                            tool_calls_data[idx]["arguments"] += tc_delta["function"]["arguments"]

                        except (KeyError, json.JSONDecodeError):
                            continue

        except aiohttp.ClientError as e:
            logger.error(f"Auto-RAG connection error: {e}")
            yield {"type": "error", "message": f"Connection error: {e}"}
            return

        # Flush ThinkFilter (CLI와 동일)
        remaining_display, _ = think_filter.flush()
        if remaining_display:
            display_content += remaining_display
            yield {"type": "llm_token", "token": remaining_display}

        # 반복 감지 시 중복 부분 제거 후 경고
        if repetition_detected and display_content:
            tail = display_content[-150:]
            first_occurrence = display_content[:-150].find(tail)
            if first_occurrence >= 0:
                display_content = display_content[:first_occurrence + 150]

        # finish_reason=length 경고를 프론트엔드에 전송
        if truncated_by_length:
            was_truncated = True
            yield {
                "type": "warning",
                "code": "response_truncated",
                "message": "応答がモデルの最大トークン数に達したため、途中で切れている可能性があります。",
            }

        # Build tool calls list with fallback ID (CLI와 동일)
        tool_calls_list = []
        for idx in sorted(tool_calls_data.keys()):
            tc = tool_calls_data[idx]
            if not tc["id"]:
                tc["id"] = f"call_{uuid.uuid4().hex[:8]}"
            tool_calls_list.append(tc)

        # Hermes fallback (CLI Section 5와 동일)
        if not tool_calls_list and accumulated_content and "<tool_call>" in accumulated_content:
            tool_calls_list = parse_hermes_tool_calls(accumulated_content)
            if tool_calls_list:
                logger.info(f"Parsed {len(tool_calls_list)} Hermes-style tool calls from text")

        # Add assistant message to history (CLI와 동일)
        assistant_msg: dict = {"role": "assistant", "content": display_content or None}
        if tool_calls_list:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls_list
            ]
        messages.append(assistant_msg)

        # No tool calls → final answer, exit loop (CLI와 동일)
        if not tool_calls_list:
            break

        # Execute each tool call (CLI: execute_tool — confirm은 웹에서 불필요)
        for tc in tool_calls_list:
            tool_name = tc["name"]
            try:
                tool_args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                tool_args = {}

            yield {
                "type": "tool_call",
                "name": tool_name,
                "args": tool_args,
                "iteration": iteration + 1,
            }

            try:
                result = await dispatch_tool(tool_name, tool_args)
            except Exception as e:
                result = f"Error executing {tool_name}: {e}"

            # Truncate for context window
            if len(result) > MAX_TOOL_RESULT_LEN:
                result = result[:MAX_TOOL_RESULT_LEN] + "\n... (truncated)"

            # Collect source references from search_webdoc results
            if tool_name == "search_webdoc":
                parsed = _parse_sources_from_tool_result(result)
                collected_sources.extend(parsed)

            # Send preview to frontend
            yield {
                "type": "tool_result",
                "name": tool_name,
                "result": result[:SSE_RESULT_PREVIEW_LEN] + ("..." if len(result) > SSE_RESULT_PREVIEW_LEN else ""),
                "iteration": iteration + 1,
            }

            # Grounding reminder: 검색 결과를 LLM이 무시하지 않도록 강제
            grounded_result = result
            if tool_name == "search_webdoc" and "No results found" not in result:
                grounded_result = (
                    "⚠️ IMPORTANT: Base your response ONLY on the search results below. "
                    "Do NOT use your own knowledge for product names, abbreviations, or definitions. "
                    "If these results define a term differently from your training data, "
                    "USE THE DEFINITION FROM THESE RESULTS.\n\n"
                    f"{result}\n\n"
                    "⚠️ REMINDER: Cite the source document (doc name, page, URL) in your response. "
                    "Any claim not supported by the above results must be omitted."
                )

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": grounded_result,
            })

        if iteration == MAX_AGENT_ITERATIONS - 1:
            logger.warning(f"Reached max iterations ({MAX_AGENT_ITERATIONS})")

    # 유틸리티 제품은 IMS 이슈 소스 제거 (무관한 결과 오염 방지)
    if collected_sources and product in _UTILITY_SEARCH_PRODUCTS:
        collected_sources = [
            s for s in collected_sources
            if not ("ims" in s.get("doc_name", "").lower() or "issue" in s.get("doc_name", "").lower())
        ]

    # Emit sources event (소스 참조 표시 — agentic_rag_service와 동일 형식)
    if collected_sources:
        # 스코어 높은 순으로 정렬, 상위 5개
        collected_sources.sort(key=lambda s: s.get("score", 0), reverse=True)
        yield {
            "type": "sources",
            "results": collected_sources[:5],
            "total": len(collected_sources),
        }

    # Append source citations to response (참고 자료 / IMS 이슈 분리 표시)
    if collected_sources:
        doc_sources = []
        ims_sources = []
        for src in collected_sources[:5]:
            name = src.get("doc_name", "")
            if "ims" in name.lower() or "issue" in name.lower():
                ims_sources.append(src)
            else:
                doc_sources.append(src)

        # 언어별 citation 라벨
        _cite_labels = {
            "ja": ("**参考資料:**", "**IMS イシュー:**"),
            "ko": ("**참고 자료:**", "**IMS 이슈:**"),
            "en": ("**References:**", "**IMS Issues:**"),
            "zh": ("**参考资料:**", "**IMS 问题:**"),
        }
        _doc_label, _ims_label = _cite_labels.get(language or "ja", _cite_labels["ja"])

        citation_lines = ["\n\n---"]
        if doc_sources:
            citation_lines.append(_doc_label)
            for i, src in enumerate(doc_sources, 1):
                name = src.get("doc_name", "")
                page = src.get("source_page", "")
                score = src.get("score", 0)
                url = src.get("url", "")
                if url:
                    citation_lines.append(f"{i}. [{name}]({url}) (score: {score:.2f})")
                elif page:
                    citation_lines.append(f"{i}. {name} p.{page} (score: {score:.2f})")
                else:
                    citation_lines.append(f"{i}. {name} (score: {score:.2f})")
        if ims_sources:
            citation_lines.append(_ims_label)
            for i, src in enumerate(ims_sources, 1):
                name = src.get("doc_name", "")
                page = src.get("source_page", "")
                score = src.get("score", 0)
                url = src.get("url", "")
                if url:
                    citation_lines.append(f"{i}. [{name}]({url}) (score: {score:.2f})")
                elif page:
                    citation_lines.append(f"{i}. {name} p.{page} (score: {score:.2f})")
                else:
                    citation_lines.append(f"{i}. {name} (score: {score:.2f})")
        citation_text = "\n".join(citation_lines)
        yield {"type": "llm_token", "token": citation_text}

    # Done
    elapsed = int((time.time() - start) * 1000)
    yield {
        "type": "done",
        "processing_time_ms": elapsed,
        "iterations": iteration + 1,
        "truncated": was_truncated,
    }


# =============================================================================
# Singleton
# =============================================================================

_instance: Optional["AutoRAGService"] = None


class AutoRAGService:
    """Auto-RAG 서비스 래퍼 (AgenticRAGService에서 위임 호출용)."""

    def __init__(self):
        self.ofcode_client = get_ofcode_client()

    async def stream(
        self,
        message: str,
        history: Optional[list] = None,
        product_ids: Optional[list] = None,
        enable_thinking: bool = False,
        initial_context: Optional[str] = None,
        language: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        async for event in stream_auto_rag(
            message, history, product_ids, enable_thinking,
            initial_context=initial_context,
            language=language,
        ):
            yield event


def get_auto_rag_service() -> AutoRAGService:
    global _instance
    if _instance is None:
        _instance = AutoRAGService()
    return _instance
