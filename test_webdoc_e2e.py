#!/usr/bin/env python3
"""E2E Test: LLM search_webdoc tool calling.

Tests that the LLM actually invokes search_webdoc when asked about OFASM documentation.

Usage:
    python test_webdoc_e2e.py
"""

import json
import os
import sys
import time

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openframe_code.core import (
    _ofcode_api,
    tool_search_webdoc,
    DEFAULT_SERVER,
    DEFAULT_OFCODE_SERVER,
    OPENFRAME_TOOLS,
    LocalCoder,
)

PASS = 0
FAIL = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \033[32mPASS\033[0m {name}" + (f" ({detail})" if detail else ""))
    else:
        FAIL += 1
        print(f"  \033[31mFAIL\033[0m {name}" + (f" ({detail})" if detail else ""))


def section(title):
    print(f"\n\033[1m{'='*60}\033[0m")
    print(f"\033[1m  {title}\033[0m")
    print(f"\033[1m{'='*60}\033[0m")


# ── Test 1: Tool Schema ──

def test_schema():
    section("1. search_webdoc Tool Schema")

    of_names = {t["function"]["name"] for t in OPENFRAME_TOOLS}
    test("search_webdoc in OPENFRAME_TOOLS", "search_webdoc" in of_names,
         f"tools: {of_names}")

    webdoc_tool = next((t for t in OPENFRAME_TOOLS if t["function"]["name"] == "search_webdoc"), None)
    test("search_webdoc has query param",
         "query" in webdoc_tool["function"]["parameters"]["properties"],
         "query param found")
    test("search_webdoc has product param",
         "product" in webdoc_tool["function"]["parameters"]["properties"],
         "product param found")


# ── Test 2: Direct API ──

def test_direct_api():
    section("2. Direct API Call (no LLM)")

    import openframe_code.core as core_mod
    core_mod._ofcode_server_url = DEFAULT_OFCODE_SERVER

    # Status
    result = _ofcode_api("/api/webdoc/status")
    test("webdoc status API", isinstance(result, dict) and result.get("loaded"),
         f"pages={result.get('total_pages', 0)}")

    # Search
    result = tool_search_webdoc("OFASM")
    test("tool_search_webdoc returns results",
         "OFASM" in result and "URL:" in result,
         f"{len(result)} chars")

    result = tool_search_webdoc("인터페이스", product="OFASM")
    test("tool_search_webdoc with product filter",
         "URL:" in result or "No web documentation" in result,
         f"{len(result)} chars")


# ── Test 3: LLM calls search_webdoc ──

def test_llm_calls_search_webdoc():
    section("3. LLM Agent Loop - search_webdoc E2E")

    try:
        coder = LocalCoder(
            server=DEFAULT_SERVER,
            no_confirm=True,
            openframe=True,
            ofcode_server=DEFAULT_OFCODE_SERVER,
        )
        test("LocalCoder init (openframe)", True, f"model={coder.model}")
    except Exception as e:
        test("LocalCoder init", False, str(e)[:80])
        return

    # Prompt designed to trigger search_webdoc
    coder.messages.append({
        "role": "user",
        "content": (
            "/no_think\n"
            "Use the search_webdoc tool to search for 'OFASM interface' documentation. "
            "Call the tool first, then briefly summarize the results."
        ),
    })

    print("\n  [Running agent loop - LLM inference...]")
    t0 = time.time()
    coder.agent_loop()
    elapsed = time.time() - t0
    print(f"  [Agent loop completed in {elapsed:.1f}s]")

    # Check: assistant made a tool call for search_webdoc
    tool_call_msgs = []
    for m in coder.messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                if isinstance(tc, dict):
                    name = tc.get("function", {}).get("name", "") if isinstance(tc.get("function"), dict) else tc.get("name", "")
                else:
                    name = getattr(getattr(tc, "function", None), "name", "") or ""
                tool_call_msgs.append(name)

    test("LLM called search_webdoc", "search_webdoc" in tool_call_msgs,
         f"tool calls: {tool_call_msgs}")

    # Check: tool result exists
    tool_results = [m for m in coder.messages if m.get("role") == "tool"]
    test("tool result in history", len(tool_results) > 0,
         f"{len(tool_results)} tool results")

    # Check: tool result contains OFASM data
    webdoc_results = [m for m in tool_results if "OFASM" in m.get("content", "") or "URL:" in m.get("content", "")]
    test("tool result contains OFASM data", len(webdoc_results) > 0,
         f"{len(webdoc_results)} results with OFASM data")

    # Check: final assistant response summarizes
    last_assistant = None
    for m in reversed(coder.messages):
        if m.get("role") == "assistant" and m.get("content") and not m.get("tool_calls"):
            last_assistant = m["content"]
            break
    test("assistant gave final summary", last_assistant is not None and len(last_assistant) > 20,
         f"{len(last_assistant)} chars" if last_assistant else "no summary")


# ── Test 4: Natural language triggers search_webdoc ──

def test_natural_language_trigger():
    section("4. Natural Language Trigger (Korean)")

    try:
        coder = LocalCoder(
            server=DEFAULT_SERVER,
            no_confirm=True,
            openframe=True,
            ofcode_server=DEFAULT_OFCODE_SERVER,
        )
    except Exception as e:
        test("LocalCoder init", False, str(e)[:80])
        return

    # Natural Korean prompt - LLM should decide to use search_webdoc
    coder.messages.append({
        "role": "user",
        "content": (
            "/no_think\n"
            "OFASM 매뉴얼에서 인터페이스 작성 방법을 찾아줘. "
            "search_webdoc 도구를 사용해서 검색하고 결과를 알려줘."
        ),
    })

    print("\n  [Running agent loop - Korean prompt...]")
    t0 = time.time()
    coder.agent_loop()
    elapsed = time.time() - t0
    print(f"  [Agent loop completed in {elapsed:.1f}s]")

    # Check search_webdoc was called
    tool_names = []
    for m in coder.messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                if isinstance(tc, dict):
                    name = tc.get("function", {}).get("name", "") if isinstance(tc.get("function"), dict) else tc.get("name", "")
                else:
                    name = getattr(getattr(tc, "function", None), "name", "") or ""
                tool_names.append(name)

    test("Korean prompt triggered search_webdoc", "search_webdoc" in tool_names,
         f"tools called: {tool_names}")

    tool_results = [m for m in coder.messages if m.get("role") == "tool"]
    has_ofasm = any("OFASM" in m.get("content", "") for m in tool_results)
    test("search returned OFASM results", has_ofasm,
         f"{len(tool_results)} tool results")


# ── Test 5: PDF-specific direct API tests ──

def test_pdf_direct_api():
    section("5. PDF Search - Direct API")

    import openframe_code.core as core_mod
    core_mod._ofcode_server_url = DEFAULT_OFCODE_SERVER

    # Status: confirm PDF chunks increased total page count
    result = _ofcode_api("/api/webdoc/status")
    total = result.get("total_pages", 0) if isinstance(result, dict) else 0
    test("index has PDF chunks (>100 pages)", total > 100,
         f"total_pages={total}")

    # Search: HLASM-specific term should only exist in PDF
    result = tool_search_webdoc("HLASM assembler instruction")
    has_pdf_url = "asmr1022.pdf" in result
    test("HLASM query returns PDF results", has_pdf_url,
         f"{len(result)} chars")

    # Search: assembler MACRO definition (PDF content)
    result = tool_search_webdoc("MACRO definition")
    has_macro = "MACRO" in result.upper() or "macro" in result.lower()
    test("MACRO query matches PDF content", has_macro,
         f"{len(result)} chars")

    # Search: PDF chunk URL format contains #chunk-
    has_chunk_ref = "#chunk-" in result
    test("PDF results use #chunk-N URL format", has_chunk_ref,
         "chunk ref found" if has_chunk_ref else "no chunk ref")

    # Search: section-based title from PDF (e.g. "Chapter 5")
    result = tool_search_webdoc("assembler instruction statements")
    has_chapter = "Chapter" in result or "chapter" in result.lower()
    test("PDF section titles in results", has_chapter,
         f"{len(result)} chars")

    # Search: product filter still works with PDF content
    result = tool_search_webdoc("USING instruction", product="OFASM")
    has_result = "URL:" in result or "No web documentation" in result
    test("product filter works with PDF", has_result,
         f"{len(result)} chars")


# ── Test 6: LLM searches PDF content ──

def test_llm_pdf_search():
    section("6. LLM Agent Loop - PDF Content Search")

    try:
        coder = LocalCoder(
            server=DEFAULT_SERVER,
            no_confirm=True,
            openframe=True,
            ofcode_server=DEFAULT_OFCODE_SERVER,
        )
        test("LocalCoder init (PDF test)", True, f"model={coder.model}")
    except Exception as e:
        test("LocalCoder init", False, str(e)[:80])
        return

    # Prompt about HLASM content that only exists in the PDF
    coder.messages.append({
        "role": "user",
        "content": (
            "/no_think\n"
            "Use the search_webdoc tool to search for 'HLASM assembler instruction' documentation. "
            "Call the tool first, then briefly summarize what you found."
        ),
    })

    print("\n  [Running agent loop - PDF search prompt...]")
    t0 = time.time()
    coder.agent_loop()
    elapsed = time.time() - t0
    print(f"  [Agent loop completed in {elapsed:.1f}s]")

    # Check: search_webdoc was called
    tool_call_names = []
    for m in coder.messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                if isinstance(tc, dict):
                    name = tc.get("function", {}).get("name", "") if isinstance(tc.get("function"), dict) else tc.get("name", "")
                else:
                    name = getattr(getattr(tc, "function", None), "name", "") or ""
                tool_call_names.append(name)

    test("LLM called search_webdoc for HLASM", "search_webdoc" in tool_call_names,
         f"tool calls: {tool_call_names}")

    # Check: tool result contains PDF URL
    tool_results = [m for m in coder.messages if m.get("role") == "tool"]
    has_pdf = any("asmr1022.pdf" in m.get("content", "") for m in tool_results)
    test("tool result contains PDF URL", has_pdf,
         f"{len(tool_results)} tool results")

    # Check: tool result has chunk references
    has_chunk = any("#chunk-" in m.get("content", "") for m in tool_results)
    test("tool result has PDF chunk refs", has_chunk,
         "chunk refs found" if has_chunk else "no chunk refs")

    # Check: final summary mentions assembler/HLASM
    last_assistant = None
    for m in reversed(coder.messages):
        if m.get("role") == "assistant" and m.get("content") and not m.get("tool_calls"):
            last_assistant = m["content"]
            break
    has_asm_summary = (
        last_assistant is not None
        and len(last_assistant) > 20
        and any(kw in last_assistant.lower() for kw in ["assembler", "hlasm", "instruction", "macro"])
    )
    test("assistant summary references assembler content", has_asm_summary,
         f"{len(last_assistant)} chars" if last_assistant else "no summary")


# ── Test 7: LLM PDF search with Korean prompt ──

def test_llm_pdf_korean():
    section("7. LLM PDF Search - Korean Prompt")

    try:
        coder = LocalCoder(
            server=DEFAULT_SERVER,
            no_confirm=True,
            openframe=True,
            ofcode_server=DEFAULT_OFCODE_SERVER,
        )
    except Exception as e:
        test("LocalCoder init", False, str(e)[:80])
        return

    # Korean prompt asking about HLASM content from the PDF
    coder.messages.append({
        "role": "user",
        "content": (
            "/no_think\n"
            "IBM HLASM 레퍼런스에서 어셈블러 명령어(assembler instruction)에 대해 "
            "search_webdoc 도구로 검색하고 결과를 요약해줘."
        ),
    })

    print("\n  [Running agent loop - Korean PDF prompt...]")
    t0 = time.time()
    coder.agent_loop()
    elapsed = time.time() - t0
    print(f"  [Agent loop completed in {elapsed:.1f}s]")

    # Check: search_webdoc was called
    tool_names = []
    for m in coder.messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                if isinstance(tc, dict):
                    name = tc.get("function", {}).get("name", "") if isinstance(tc.get("function"), dict) else tc.get("name", "")
                else:
                    name = getattr(getattr(tc, "function", None), "name", "") or ""
                tool_names.append(name)

    test("Korean HLASM prompt triggered search_webdoc", "search_webdoc" in tool_names,
         f"tools called: {tool_names}")

    # Check: result has PDF data
    tool_results = [m for m in coder.messages if m.get("role") == "tool"]
    has_pdf = any("asmr1022.pdf" in m.get("content", "") for m in tool_results)
    test("Korean search returned PDF results", has_pdf,
         f"{len(tool_results)} tool results")

    # Check: assistant gave a summary
    last_assistant = None
    for m in reversed(coder.messages):
        if m.get("role") == "assistant" and m.get("content") and not m.get("tool_calls"):
            last_assistant = m["content"]
            break
    test("assistant gave Korean summary", last_assistant is not None and len(last_assistant) > 20,
         f"{len(last_assistant)} chars" if last_assistant else "no summary")


# ── Main ──

if __name__ == "__main__":
    print("\033[1m")
    print("+" + "="*58 + "+")
    print("|   search_webdoc E2E Test - LLM Tool Calling              |")
    print("|   (includes PDF search tests)                            |")
    print("+" + "="*58 + "+")
    print("\033[0m")

    t0 = time.time()

    test_schema()
    test_direct_api()
    test_llm_calls_search_webdoc()
    test_natural_language_trigger()
    test_pdf_direct_api()
    test_llm_pdf_search()
    test_llm_pdf_korean()

    elapsed = time.time() - t0

    print(f"\n\033[1m{'='*60}\033[0m")
    print(f"  \033[32mPASS: {PASS}\033[0m  |  \033[31mFAIL: {FAIL}\033[0m  |  Time: {elapsed:.1f}s")
    print(f"\033[1m{'='*60}\033[0m")

    sys.exit(1 if FAIL > 0 else 0)
