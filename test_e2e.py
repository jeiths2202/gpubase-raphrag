#!/usr/bin/env python3
"""E2E Test Suite for OpenFrame Code CLI.

Tests all components: tool functions, token management, remote API,
LLM streaming, agent loop, and special commands.

Usage:
    python test_e2e.py
"""

import json
import os
import sys
import tempfile
import time

# Fix Windows encoding
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openframe_code.core import (
    # Token estimation
    estimate_tokens,
    estimate_messages_tokens,
    update_token_correction,
    _token_correction_factor,
    # Tool functions
    tool_read_file,
    tool_write_file,
    tool_edit_file,
    tool_bash,
    tool_grep_search,
    tool_glob_search,
    tool_list_directory,
    # OpenFrame remote tools
    _ofcode_api,
    _check_ofcode_server,
    tool_search_of7,
    tool_get_module_info,
    tool_get_function_def,
    tool_get_header_api,
    tool_get_architecture,
    tool_find_callers,
    # Config & classes
    DEFAULT_SERVER,
    DEFAULT_OFCODE_SERVER,
    DEFAULT_CONTEXT_LENGTH,
    MIN_OUTPUT_TOKENS,
    TOKEN_BUFFER,
    TOOLS,
    OPENFRAME_TOOLS,
    SYSTEM_PROMPT,
    OPENFRAME_SYSTEM_PROMPT,
    LocalCoder,
)


# ─────────────────────────────────────────────────────
# Test framework
# ─────────────────────────────────────────────────────

PASS = 0
FAIL = 0
SKIP = 0
RESULTS = []


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append(("PASS", name, detail))
        print(f"  \033[32mPASS\033[0m {name}" + (f" ({detail})" if detail else ""))
    else:
        FAIL += 1
        RESULTS.append(("FAIL", name, detail))
        print(f"  \033[31mFAIL\033[0m {name}" + (f" ({detail})" if detail else ""))


def skip(name, reason=""):
    global SKIP
    SKIP += 1
    RESULTS.append(("SKIP", name, reason))
    print(f"  \033[33mSKIP\033[0m {name}" + (f" ({reason})" if reason else ""))


def section(title):
    print(f"\n\033[1m{'='*60}\033[0m")
    print(f"\033[1m  {title}\033[0m")
    print(f"\033[1m{'='*60}\033[0m")


# ─────────────────────────────────────────────────────
# Test 1: Token Estimation
# ─────────────────────────────────────────────────────

def test_token_estimation():
    section("1. Token Estimation")

    # Basic estimation
    t = estimate_tokens("Hello world")
    test("estimate_tokens basic", t > 0, f"'Hello world' = {t} tokens")

    # Empty string
    t = estimate_tokens("")
    test("estimate_tokens empty", t == 0, f"empty = {t}")

    # Korean text (should be higher per-char ratio)
    t_en = estimate_tokens("Hello world, this is a test.")
    t_kr = estimate_tokens("안녕하세요, 이것은 테스트입니다.")
    test("estimate_tokens CJK vs English", t_kr > 0 and t_en > 0,
         f"EN={t_en}, KR={t_kr}")

    # Messages estimation
    msgs = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
    ]
    t = estimate_messages_tokens(msgs)
    test("estimate_messages_tokens", t > 0, f"{t} tokens for 2 msgs")

    # Messages with tools
    t_no_tools = estimate_messages_tokens(msgs)
    t_with_tools = estimate_messages_tokens(msgs, tools=TOOLS)
    test("tools add tokens", t_with_tools > t_no_tools,
         f"without={t_no_tools}, with={t_with_tools}, diff={t_with_tools - t_no_tools}")

    # Correction factor
    import openframe_code.core as core_mod
    old_factor = core_mod._token_correction_factor
    update_token_correction(100, 120)  # underestimated
    new_factor = core_mod._token_correction_factor
    test("correction factor updates", new_factor != old_factor,
         f"old={old_factor:.3f}, new={new_factor:.3f}")
    # Reset
    core_mod._token_correction_factor = 1.0


# ─────────────────────────────────────────────────────
# Test 2: Base Tool Functions
# ─────────────────────────────────────────────────────

def test_base_tools():
    section("2. Base Tools (7 tools)")

    # Create temp directory for testing
    tmpdir = tempfile.mkdtemp(prefix="ofcode_e2e_")
    test_file = os.path.join(tmpdir, "test.txt")

    # --- write_file ---
    result = tool_write_file(test_file, "Line 1\nLine 2\nLine 3\n")
    test("write_file creates file", os.path.exists(test_file), result.split('\n')[0])

    # --- read_file ---
    result = tool_read_file(test_file)
    test("read_file reads content", "Line 1" in result and "Line 2" in result, f"{len(result)} chars")

    result = tool_read_file(test_file, offset=2, limit=1)
    test("read_file offset/limit", "Line 2" in result and "Line 1" not in result, result.strip())

    # --- edit_file ---
    result = tool_edit_file(test_file, "Line 2", "Line TWO")
    test("edit_file replaces string", "Line TWO" not in result or "Error" not in result,
         result.split('\n')[0] if result else "empty")
    verify = tool_read_file(test_file)
    test("edit_file result verified", "Line TWO" in verify, "Line TWO found in file")

    # edit_file with non-unique match
    tool_write_file(os.path.join(tmpdir, "dup.txt"), "aaa\naaa\n")
    result = tool_edit_file(os.path.join(tmpdir, "dup.txt"), "aaa", "bbb")
    test("edit_file non-unique error", "Error" in result or "not unique" in result.lower() or "multiple" in result.lower(),
         result[:80])

    # --- bash ---
    result = tool_bash("echo hello_e2e_test", timeout=5)
    test("bash executes command", "hello_e2e_test" in result, result.strip()[:60])

    result = tool_bash("exit 1", timeout=5)
    test("bash captures exit code", "exit code" in result.lower() or "Error" in result or "1" in result,
         result.strip()[:60])

    # --- list_directory ---
    result = tool_list_directory(tmpdir)
    test("list_directory works", "test.txt" in result, f"found test.txt in listing")

    result = tool_list_directory("/nonexistent_path_xyz")
    test("list_directory bad path", "Error" in result, result[:60])

    # --- glob_search ---
    result = tool_glob_search("*.txt", path=tmpdir)
    test("glob_search finds files", "test.txt" in result, f"found in glob results")

    # --- grep_search ---
    result = tool_grep_search("Line TWO", path=tmpdir)
    test("grep_search finds pattern", "test.txt" in result and "Line TWO" in result,
         f"{len(result)} chars")

    result = tool_grep_search("NONEXISTENT_PATTERN_XYZ", path=tmpdir)
    test("grep_search no match", "No matches" in result or result.strip() == "" or len(result) < 50,
         result.strip()[:60])

    # --- read non-existent file ---
    result = tool_read_file("/nonexistent_file_xyz.txt")
    test("read_file non-existent", "Error" in result, result[:60])

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


# ─────────────────────────────────────────────────────
# Test 3: OpenFrame Remote API Tools
# ─────────────────────────────────────────────────────

def test_openframe_tools():
    section("3. OpenFrame Remote API Tools (6 tools)")

    import openframe_code.core as core_mod

    # Set server URL
    core_mod._ofcode_server_url = DEFAULT_OFCODE_SERVER

    # --- Health check ---
    ok, info = _check_ofcode_server()
    test("ofcode-server health", ok, info[:80] if isinstance(info, str) else str(info)[:80])

    if not ok:
        skip("search_of7", "server unreachable")
        skip("get_module_info", "server unreachable")
        skip("get_function_def", "server unreachable")
        skip("get_header_api", "server unreachable")
        skip("get_architecture", "server unreachable")
        skip("find_callers", "server unreachable")
        return

    # --- search_of7 ---
    result = tool_search_of7("dbio_open")
    test("search_of7 finds function", "dbio" in result.lower(), f"{len(result)} chars")

    result = tool_search_of7("dsio", module="base")
    test("search_of7 with module filter", len(result) > 10, f"{len(result)} chars")

    result = tool_search_of7("XYZNONEXISTENT999")
    test("search_of7 no match", "no results" in result.lower() or "0 " in result or len(result) < 100,
         result[:80])

    # --- get_module_info ---
    result = tool_get_module_info("base")
    test("get_module_info base", "base" in result.lower() and len(result) > 50,
         f"{len(result)} chars")

    result = tool_get_module_info("nonexistent_module")
    test("get_module_info invalid", "error" in result.lower() or "not found" in result.lower() or len(result) < 100,
         result[:80])

    # --- get_function_def ---
    result = tool_get_function_def("dbio_open")
    test("get_function_def dbio_open", "dbio" in result.lower(), f"{len(result)} chars")

    result = tool_get_function_def("XYZNONEXISTENT_func")
    test("get_function_def not found", "not found" in result.lower() or "error" in result.lower(),
         result[:80])

    # --- get_header_api ---
    result = tool_get_header_api("dbio.h")
    test("get_header_api dbio.h", "dbio" in result.lower() and len(result) > 30,
         f"{len(result)} chars")

    result = tool_get_header_api("nonexistent.h")
    test("get_header_api not found", "not found" in result.lower() or "error" in result.lower(),
         result[:80])

    # --- get_architecture ---
    result = tool_get_architecture()
    test("get_architecture returns data", len(result) > 100 and ("base" in result.lower() or "module" in result.lower()),
         f"{len(result)} chars")

    # --- find_callers ---
    result = tool_find_callers("dbio_open")
    test("find_callers dbio_open", len(result) > 10, f"{len(result)} chars")

    result = tool_find_callers("dbio_open", module="base")
    test("find_callers with module", len(result) > 10, f"{len(result)} chars")


# ─────────────────────────────────────────────────────
# Test 4: Token Budget & Progressive Compression
# ─────────────────────────────────────────────────────

def test_token_budget():
    section("4. Token Budget & Progressive Compression")

    try:
        coder = LocalCoder(
            server=DEFAULT_SERVER,
            no_confirm=True,
            openframe=True,
            ofcode_server=DEFAULT_OFCODE_SERVER,
        )
        test("LocalCoder init (openframe)", True, f"model={coder.model}, ctx={coder.context_limit}")
    except Exception as e:
        test("LocalCoder init", False, str(e)[:80])
        return

    # get_token_usage
    input_tokens, available = coder.get_token_usage()
    test("get_token_usage returns values", input_tokens > 0 and available >= 0,
         f"input={input_tokens}, available={available}")

    # calculate_max_tokens with fresh context
    max_t = coder.calculate_max_tokens()
    test("calculate_max_tokens returns valid", max_t >= MIN_OUTPUT_TOKENS,
         f"max_tokens={max_t}")

    # Simulate context filling
    original_msg_count = len(coder.messages)
    for i in range(20):
        coder.messages.append({"role": "user", "content": f"This is a long test message number {i}. " * 20})
        coder.messages.append({"role": "assistant", "content": f"This is a long response for message {i}. " * 20})
        coder.messages.append({"role": "tool", "tool_call_id": f"call_{i}",
                                "content": f"Tool result line\n" * 50})

    input_after, available_after = coder.get_token_usage()
    test("context filled up", input_after > input_tokens,
         f"input went from {input_tokens} to {input_after}")

    # Progressive compress should run
    max_t2 = coder.calculate_max_tokens()
    msg_count_after = len(coder.messages)
    test("progressive_compress ran", msg_count_after < original_msg_count + 60,
         f"messages: {original_msg_count + 60} -> {msg_count_after}")
    test("max_tokens still valid after compress", max_t2 >= MIN_OUTPUT_TOKENS,
         f"max_tokens={max_t2}")


# ─────────────────────────────────────────────────────
# Test 5: LLM Streaming & Tool Calling
# ─────────────────────────────────────────────────────

def test_llm_streaming():
    section("5. LLM Streaming & Chat")

    try:
        coder = LocalCoder(
            server=DEFAULT_SERVER,
            no_confirm=True,
            openframe=False,
        )
    except Exception as e:
        test("LocalCoder init (basic)", False, str(e)[:80])
        return

    # Simple chat - should get text response without tool calls
    coder.messages.append({"role": "user", "content": "/no_think\nSay exactly: TEST_OK_12345"})
    content, tool_calls = coder.stream_response()
    test("streaming returns content", content is not None and len(content) > 0,
         f"{len(content)} chars" if content else "None")
    test("simple chat no tool calls", len(tool_calls) == 0,
         f"{len(tool_calls)} tool calls")
    test("response contains expected", content is not None and "TEST_OK" in (content or ""),
         (content or "")[:80])


def test_tool_calling():
    section("6. LLM Tool Calling (Agent Loop)")

    try:
        coder = LocalCoder(
            server=DEFAULT_SERVER,
            no_confirm=True,
            openframe=False,
        )
    except Exception as e:
        test("LocalCoder init for tool test", False, str(e)[:80])
        return

    # Ask something that should trigger read_file tool
    coder.messages.append({
        "role": "user",
        "content": "/no_think\nUse the list_directory tool to list files in the current directory. Just call the tool and report what you see.",
    })

    # Run agent loop
    coder.agent_loop()

    # Check that tool was called (messages should have tool results)
    tool_results = [m for m in coder.messages if m.get("role") == "tool"]
    test("agent loop called tool", len(tool_results) > 0,
         f"{len(tool_results)} tool results in history")

    tool_call_msgs = [m for m in coder.messages if m.get("role") == "assistant" and m.get("tool_calls")]
    test("assistant made tool calls", len(tool_call_msgs) > 0,
         f"{len(tool_call_msgs)} assistant msgs with tool calls")


# ─────────────────────────────────────────────────────
# Test 6: Special Commands
# ─────────────────────────────────────────────────────

def test_special_commands():
    section("7. Special Commands")

    try:
        coder = LocalCoder(
            server=DEFAULT_SERVER,
            no_confirm=True,
            openframe=True,
            ofcode_server=DEFAULT_OFCODE_SERVER,
        )
    except Exception as e:
        test("LocalCoder init for commands", False, str(e)[:80])
        return

    # Add some messages
    coder.messages.append({"role": "user", "content": "test"})
    coder.messages.append({"role": "assistant", "content": "reply"})
    original_count = len(coder.messages)

    # /tokens - just verify it doesn't crash
    try:
        coder.process("/tokens")
        test("/tokens command", True, "no crash")
    except Exception as e:
        test("/tokens command", False, str(e)[:60])

    # /model
    try:
        coder.process("/model")
        test("/model command", True, "no crash")
    except Exception as e:
        test("/model command", False, str(e)[:60])

    # /history
    try:
        coder.process("/history")
        test("/history command", True, "no crash")
    except Exception as e:
        test("/history command", False, str(e)[:60])

    # /compact
    for i in range(15):
        coder.messages.append({"role": "user", "content": f"msg {i}"})
        coder.messages.append({"role": "assistant", "content": f"reply {i}"})
    before = len(coder.messages)
    coder.process("/compact")
    after = len(coder.messages)
    test("/compact reduces messages", after < before,
         f"{before} -> {after} messages")

    # /clear
    coder.process("/clear")
    test("/clear resets messages", len(coder.messages) == 1 and coder.messages[0]["role"] == "system",
         f"{len(coder.messages)} messages after clear")

    # Unknown command
    try:
        coder.process("/unknown_xyz")
        test("/unknown command handled", True, "no crash")
    except Exception as e:
        test("/unknown command handled", False, str(e)[:60])


# ─────────────────────────────────────────────────────
# Test 7: OpenFrame Mode Tool Calling via LLM
# ─────────────────────────────────────────────────────

def test_openframe_agent():
    section("8. OpenFrame Mode Agent Loop (LLM + Remote API)")

    try:
        coder = LocalCoder(
            server=DEFAULT_SERVER,
            no_confirm=True,
            openframe=True,
            ofcode_server=DEFAULT_OFCODE_SERVER,
        )
    except Exception as e:
        test("LocalCoder init (openframe agent)", False, str(e)[:80])
        return

    # Ask about OpenFrame architecture - should use get_architecture or search_of7
    coder.messages.append({
        "role": "user",
        "content": "/no_think\nUse the get_architecture tool to show me the OpenFrame module overview.",
    })

    coder.agent_loop()

    tool_results = [m for m in coder.messages if m.get("role") == "tool"]
    test("OpenFrame agent called API tool", len(tool_results) > 0,
         f"{len(tool_results)} tool results")

    # Check that we got meaningful content back
    if tool_results:
        last_result = tool_results[-1].get("content", "")
        test("API tool returned data", len(last_result) > 50,
             f"{len(last_result)} chars in tool result")
    else:
        test("API tool returned data", False, "no tool results")


# ─────────────────────────────────────────────────────
# Test 8: Error Correction Loop
# ─────────────────────────────────────────────────────

def test_error_correction():
    section("9. Token Error Correction")

    import openframe_code.core as core_mod

    # Test _parse_token_count_from_error
    try:
        coder = LocalCoder(
            server=DEFAULT_SERVER,
            no_confirm=True,
            openframe=False,
        )
    except Exception as e:
        test("LocalCoder init for error test", False, str(e)[:80])
        return

    error_msg = "'max_tokens' is too large: 4096. This model's maximum context length is 8192 tokens and your request has 4888 input tokens"
    parsed = coder._parse_token_count_from_error(error_msg)
    test("parse token count from error", parsed == 4888, f"parsed={parsed}")

    error_msg2 = "some other error"
    parsed2 = coder._parse_token_count_from_error(error_msg2)
    test("parse token count no match", parsed2 is None, f"parsed={parsed2}")


# ─────────────────────────────────────────────────────
# Test 9: System Prompt Formatting
# ─────────────────────────────────────────────────────

def test_system_prompts():
    section("10. System Prompt Formatting")

    cwd = os.getcwd()

    # Basic prompt
    try:
        prompt = SYSTEM_PROMPT.format(cwd=cwd)
        test("SYSTEM_PROMPT formats", "{cwd}" not in prompt and cwd in prompt, f"{len(prompt)} chars")
    except Exception as e:
        test("SYSTEM_PROMPT formats", False, str(e)[:60])

    # OpenFrame prompt
    try:
        prompt = OPENFRAME_SYSTEM_PROMPT.format(cwd=cwd)
        test("OPENFRAME_SYSTEM_PROMPT formats", "{cwd}" not in prompt and cwd in prompt,
             f"{len(prompt)} chars")
    except Exception as e:
        test("OPENFRAME_SYSTEM_PROMPT formats", False, str(e)[:60])

    # Ensure no {of7_root} placeholder remains
    test("no of7_root in OPENFRAME_PROMPT", "{of7_root}" not in OPENFRAME_SYSTEM_PROMPT,
         "clean")


# ─────────────────────────────────────────────────────
# Test 10: Tool Schema Completeness
# ─────────────────────────────────────────────────────

def test_tool_schemas():
    section("11. Tool Schema Completeness")

    # Base tools
    base_names = {t["function"]["name"] for t in TOOLS}
    expected_base = {"read_file", "write_file", "edit_file", "bash", "grep_search", "glob_search", "list_directory"}
    test("all 7 base tools defined", base_names == expected_base,
         f"found: {base_names}")

    # OpenFrame tools
    of_names = {t["function"]["name"] for t in OPENFRAME_TOOLS}
    expected_of = {"search_of7", "get_module_info", "get_function_def", "get_header_api", "get_architecture", "find_callers", "search_webdoc"}
    test("all 7 OpenFrame tools defined", of_names == expected_of,
         f"found: {of_names}")

    # Each tool has valid schema
    all_tools = TOOLS + OPENFRAME_TOOLS
    all_valid = True
    for t in all_tools:
        func = t.get("function", {})
        if not func.get("name") or not func.get("description") or "parameters" not in func:
            all_valid = False
            break
    test("all tools have name/desc/params", all_valid, f"{len(all_tools)} tools checked")


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\033[1m")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   OpenFrame Code CLI - E2E Test Suite                   ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("\033[0m")

    t0 = time.time()

    # Unit-level tests (no server needed)
    test_token_estimation()
    test_base_tools()
    test_tool_schemas()
    test_system_prompts()

    # Integration tests (need ofcode-server)
    test_openframe_tools()

    # Integration tests (need vLLM server)
    test_token_budget()
    test_error_correction()

    # LLM tests (need vLLM + actual model inference)
    test_llm_streaming()
    test_tool_calling()
    test_openframe_agent()

    # Special commands
    test_special_commands()

    elapsed = time.time() - t0

    # Summary
    print(f"\n\033[1m{'='*60}\033[0m")
    print(f"\033[1m  RESULTS\033[0m")
    print(f"\033[1m{'='*60}\033[0m")
    print(f"  \033[32mPASS: {PASS}\033[0m")
    print(f"  \033[31mFAIL: {FAIL}\033[0m")
    print(f"  \033[33mSKIP: {SKIP}\033[0m")
    print(f"  Total: {PASS + FAIL + SKIP}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"\033[1m{'='*60}\033[0m")

    if FAIL > 0:
        print(f"\n\033[31mFailed tests:\033[0m")
        for status, name, detail in RESULTS:
            if status == "FAIL":
                print(f"  - {name}: {detail}")

    sys.exit(1 if FAIL > 0 else 0)
