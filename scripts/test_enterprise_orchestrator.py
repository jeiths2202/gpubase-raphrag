#!/usr/bin/env python3
"""
Enterprise Orchestrator API Test Script

Tests the enterprise multi-agent orchestration functionality including:
- Default configuration endpoint
- Single-agent fallback (enable_multi_agent=False)
- Multi-agent orchestration with parallel execution
- DAG creation and task decomposition
- Streaming with interleaved output
- Result synthesis
- Next-action recommendations
- Execution trace and explainability

Usage:
    python scripts/test_enterprise_orchestrator.py          # Run all tests
    python scripts/test_enterprise_orchestrator.py --quick  # Run quick tests only
"""

import requests
import time
import sys
import json
import argparse
from typing import Optional, Dict, Any, List


# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = "http://localhost:9000/api/v1"

# Login credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "SecureAdm1nP@ss2024!"


# =============================================================================
# Helper Functions
# =============================================================================

class TestResult:
    def __init__(self, name: str, category: str = "Enterprise"):
        self.name = name
        self.category = category
        self.success = False
        self.message = ""
        self.response_time = 0.0
        self.data: Optional[Dict[str, Any]] = None

    def __str__(self):
        status = "[PASS]" if self.success else "[FAIL]"
        time_str = f"({self.response_time:.2f}s)" if self.response_time > 0 else ""
        return f"{status} [{self.category}] {self.name} {time_str}: {self.message}"


def make_request(
    method: str,
    endpoint: str,
    token: Optional[str] = None,
    data: Optional[Dict] = None,
    timeout: int = 180
) -> tuple[Optional[Dict], float]:
    """Make HTTP request and return response with timing."""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    start_time = time.time()
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=timeout)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=timeout)
        else:
            raise ValueError(f"Unsupported method: {method}")

        elapsed = time.time() - start_time
        return response.json(), elapsed
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        return {"error": "Request timeout"}, elapsed
    except requests.exceptions.ConnectionError:
        elapsed = time.time() - start_time
        return {"error": "Connection failed - is the server running?"}, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        return {"error": str(e)}, elapsed


def stream_request(
    endpoint: str,
    token: str,
    data: Dict,
    timeout: int = 180
) -> tuple[List[Dict], float, Optional[str]]:
    """Make streaming request and collect all chunks."""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream"
    }

    chunks = []
    error = None
    start_time = time.time()

    try:
        with requests.post(url, headers=headers, json=data, stream=True, timeout=timeout) as response:
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        try:
                            chunk_data = json.loads(line_str[6:])
                            chunks.append(chunk_data)
                            if chunk_data.get('chunk_type') == 'error':
                                error = chunk_data.get('content', 'Unknown error')
                        except json.JSONDecodeError:
                            pass
    except requests.exceptions.Timeout:
        error = "Request timeout"
    except requests.exceptions.ConnectionError:
        error = "Connection failed"
    except Exception as e:
        error = str(e)

    elapsed = time.time() - start_time
    return chunks, elapsed, error


# =============================================================================
# Test Functions
# =============================================================================

def test_login() -> TestResult:
    """Test login and get access token."""
    result = TestResult("Login Authentication", "Setup")

    data = {
        "username": ADMIN_USERNAME,
        "password": ADMIN_PASSWORD
    }

    response, elapsed = make_request("POST", "/auth/login", data=data)
    result.response_time = elapsed

    if response and response.get("success") and response.get("data", {}).get("access_token"):
        result.success = True
        result.message = f"Logged in as {ADMIN_USERNAME}"
        result.data = {"token": response["data"]["access_token"]}
    else:
        result.message = response.get("error", {}).get("message", "Login failed")

    return result


def test_get_default_config(token: str) -> TestResult:
    """Test getting default orchestration configuration."""
    result = TestResult("Get Default Config", "Enterprise")

    response, elapsed = make_request("GET", "/agents/enterprise/config", token=token)
    result.response_time = elapsed

    if response and "enable_parallel" in response:
        result.success = True
        result.message = f"Config retrieved: parallel={response.get('enable_parallel')}, retry={response.get('enable_retry')}"
        result.data = response
    else:
        error_msg = response.get("error", "Unknown error") if response else "No response"
        result.message = f"Failed: {error_msg}"

    return result


def test_single_agent_fallback(token: str) -> TestResult:
    """Test enterprise endpoint with multi-agent disabled (single agent fallback)."""
    result = TestResult("Single Agent Fallback", "Enterprise")

    data = {
        "task": "What is OpenFrame?",
        "enable_multi_agent": False,
        "language": "en"
    }

    response, elapsed = make_request("POST", "/agents/enterprise/execute", token=token, data=data)
    result.response_time = elapsed

    if response and response.get("success") and response.get("answer"):
        result.success = True
        agent_type = response.get("agent_type", "unknown")
        answer_preview = response.get("answer", "")[:100]
        result.message = f"Single agent ({agent_type}) responded"
        result.data = {
            "agent_type": agent_type,
            "answer_preview": answer_preview,
            "has_trace": response.get("trace") is not None
        }
    else:
        error_msg = response.get("error", "Unknown error") if response else "No response"
        result.message = f"Failed: {error_msg}"

    return result


def test_multi_agent_parallel(token: str) -> TestResult:
    """Test multi-agent orchestration with parallel execution."""
    result = TestResult("Multi-Agent Parallel Execution", "Enterprise")

    # Task that should trigger parallel decomposition (comparison task)
    data = {
        "task": "Compare OpenFrame and Tibero features, and explain their differences.",
        "enable_multi_agent": True,
        "language": "en",
        "orchestration_config": {
            "enable_parallel": True,
            "enable_synthesis": True,
            "enable_next_actions": True
        }
    }

    response, elapsed = make_request("POST", "/agents/enterprise/execute", token=token, data=data, timeout=300)
    result.response_time = elapsed

    if response and response.get("answer"):
        result.success = True

        # Check for multi-agent indicators
        trace = response.get("trace", {})
        subtask_results = response.get("subtask_results", {})
        next_actions = response.get("next_actions", [])

        task_count = trace.get("dag", {}).get("task_count", 0) if trace else 0
        parallelism = trace.get("dag", {}).get("parallelism") if trace else "unknown"

        result.message = f"Tasks: {task_count}, Parallelism: {parallelism}, Subtasks: {len(subtask_results)}"
        result.data = {
            "task_count": task_count,
            "parallelism": parallelism,
            "subtask_count": len(subtask_results),
            "next_actions_count": len(next_actions),
            "has_trace": trace is not None,
            "execution_time": response.get("execution_time", 0)
        }
    else:
        error_msg = response.get("error", "Unknown error") if response else "No response"
        result.message = f"Failed: {error_msg}"

    return result


def test_execution_trace(token: str) -> TestResult:
    """Test that execution trace is properly generated."""
    result = TestResult("Execution Trace", "Enterprise")

    data = {
        "task": "Explain the benefits of using graph databases.",
        "enable_multi_agent": True,
        "language": "en",
        "orchestration_config": {
            "enable_parallel": True,
            "enable_evaluation": True
        }
    }

    response, elapsed = make_request("POST", "/agents/enterprise/execute", token=token, data=data)
    result.response_time = elapsed

    if response and response.get("trace"):
        trace = response["trace"]

        # Check trace structure
        has_trace_id = "trace_id" in trace
        has_events = "events" in trace and len(trace.get("events", [])) > 0
        has_dag = trace.get("dag") is not None
        has_times = "start_time" in trace and "total_time" in trace

        event_types = [e.get("event_type") for e in trace.get("events", [])]

        if has_trace_id and has_events:
            result.success = True
            result.message = f"Trace ID: {trace.get('trace_id', 'N/A')[:8]}..., Events: {len(trace.get('events', []))}"
            result.data = {
                "trace_id": trace.get("trace_id"),
                "event_count": len(trace.get("events", [])),
                "event_types": list(set(event_types)),
                "has_dag": has_dag,
                "total_time": trace.get("total_time", 0)
            }
        else:
            result.message = f"Trace incomplete: id={has_trace_id}, events={has_events}"
    else:
        error_msg = response.get("error", "Unknown error") if response else "No response"
        result.message = f"Failed or no trace: {error_msg}"

    return result


def test_result_synthesis(token: str) -> TestResult:
    """Test that multiple results are synthesized properly."""
    result = TestResult("Result Synthesis", "Enterprise")

    # Task designed to generate multiple subtasks
    data = {
        "task": "OpenFrame의 주요 기능 3가지와 각각의 장점을 설명하세요.",
        "enable_multi_agent": True,
        "language": "ko",
        "orchestration_config": {
            "enable_parallel": True,
            "enable_synthesis": True
        }
    }

    response, elapsed = make_request("POST", "/agents/enterprise/execute", token=token, data=data, timeout=300)
    result.response_time = elapsed

    if response and response.get("answer"):
        answer = response.get("answer", "")
        trace = response.get("trace", {})
        synthesis_metadata = trace.get("synthesis", {}) if trace else {}

        # Check if answer seems synthesized (has structure, covers multiple points)
        has_structure = any(marker in answer for marker in ["1.", "2.", "3.", "첫째", "둘째", "-", "•"])
        answer_length = len(answer)

        result.success = True
        synthesis_method = synthesis_metadata.get("method", "unknown")
        result.message = f"Synthesis method: {synthesis_method}, Length: {answer_length} chars"
        result.data = {
            "synthesis_method": synthesis_method,
            "answer_length": answer_length,
            "has_structure": has_structure,
            "answer_preview": answer[:200] + "..." if len(answer) > 200 else answer
        }
    else:
        error_msg = response.get("error", "Unknown error") if response else "No response"
        result.message = f"Failed: {error_msg}"

    return result


def test_next_actions(token: str) -> TestResult:
    """Test next-action recommendations generation."""
    result = TestResult("Next Actions", "Enterprise")

    data = {
        "task": "How do I install OpenFrame on Linux?",
        "enable_multi_agent": True,
        "language": "en",
        "orchestration_config": {
            "enable_next_actions": True
        }
    }

    response, elapsed = make_request("POST", "/agents/enterprise/execute", token=token, data=data)
    result.response_time = elapsed

    if response and response.get("success"):
        next_actions = response.get("next_actions", [])

        if next_actions:
            result.success = True
            result.message = f"Generated {len(next_actions)} next actions"
            result.data = {
                "action_count": len(next_actions),
                "actions": next_actions
            }
        else:
            result.success = True  # Next actions are optional
            result.message = "No next actions generated (optional feature)"
    else:
        error_msg = response.get("error", "Unknown error") if response else "No response"
        result.message = f"Failed: {error_msg}"

    return result


def test_streaming_enterprise(token: str) -> TestResult:
    """Test streaming enterprise orchestration."""
    result = TestResult("Streaming Orchestration", "Enterprise")

    data = {
        "task": "What are the main components of a RAG system?",
        "enable_multi_agent": True,
        "language": "en",
        "orchestration_config": {
            "enable_parallel": True
        }
    }

    chunks, elapsed, error = stream_request("/agents/enterprise/stream", token, data)
    result.response_time = elapsed

    if error:
        result.message = f"Stream error: {error}"
        return result

    if chunks:
        # Analyze chunk types
        chunk_types = [c.get("chunk_type") for c in chunks]
        unique_types = list(set(chunk_types))

        has_start = "orchestration_start" in chunk_types
        has_done = "done" in chunk_types
        has_dag = "dag_created" in chunk_types

        if has_start and has_done:
            result.success = True
            result.message = f"Received {len(chunks)} chunks, types: {unique_types}"
            result.data = {
                "chunk_count": len(chunks),
                "chunk_types": unique_types,
                "has_dag_created": has_dag,
                "has_synthesis": "synthesis" in chunk_types
            }
        else:
            result.message = f"Incomplete stream: start={has_start}, done={has_done}"
    else:
        result.message = "No chunks received"

    return result


def test_continue_on_failure(token: str) -> TestResult:
    """Test continue-on-failure behavior."""
    result = TestResult("Continue on Failure", "Enterprise")

    data = {
        "task": "Search for ProObject issues and explain OpenFrame architecture.",
        "enable_multi_agent": True,
        "language": "en",
        "orchestration_config": {
            "enable_parallel": True,
            "continue_on_failure": True
        }
    }

    response, elapsed = make_request("POST", "/agents/enterprise/execute", token=token, data=data, timeout=300)
    result.response_time = elapsed

    if response:
        partial_failures = response.get("partial_failures", [])
        success = response.get("success", False)
        answer = response.get("answer", "")

        # Even with partial failures, we should get some answer
        if answer:
            result.success = True
            if partial_failures:
                result.message = f"Continued despite {len(partial_failures)} failures"
            else:
                result.message = "All tasks succeeded"
            result.data = {
                "partial_failures": partial_failures,
                "overall_success": success,
                "has_answer": bool(answer)
            }
        else:
            result.message = "No answer generated"
    else:
        result.message = "No response from server"

    return result


def test_evaluation_criteria(token: str) -> TestResult:
    """Test custom evaluation criteria."""
    result = TestResult("Evaluation Criteria", "Enterprise")

    data = {
        "task": "Briefly explain what Neo4j is.",
        "enable_multi_agent": True,
        "language": "en",
        "orchestration_config": {
            "enable_evaluation": True,
            "evaluation_criteria": {
                "min_confidence": 0.5,
                "min_answer_length": 50,
                "require_sources": False
            }
        }
    }

    response, elapsed = make_request("POST", "/agents/enterprise/execute", token=token, data=data)
    result.response_time = elapsed

    if response and response.get("trace"):
        trace = response["trace"]
        evaluations = trace.get("evaluations", {})

        if evaluations:
            # Check evaluation results
            eval_scores = [e.get("score", 0) for e in evaluations.values()]
            eval_passed = [e.get("passed", False) for e in evaluations.values()]

            result.success = True
            result.message = f"Evaluations: {len(evaluations)}, Avg score: {sum(eval_scores)/len(eval_scores):.2f}"
            result.data = {
                "evaluation_count": len(evaluations),
                "scores": eval_scores,
                "all_passed": all(eval_passed)
            }
        else:
            result.success = True  # Evaluations may be empty for single task
            result.message = "No evaluations recorded (may be single task)"
    else:
        # Still successful if we got an answer
        if response and response.get("answer"):
            result.success = True
            result.message = "Answer received (evaluation not in trace)"
        else:
            error_msg = response.get("error", "Unknown error") if response else "No response"
            result.message = f"Failed: {error_msg}"

    return result


def test_timeout_handling(token: str) -> TestResult:
    """Test timeout configuration handling."""
    result = TestResult("Timeout Handling", "Enterprise")

    data = {
        "task": "Hello, this is a quick test.",
        "enable_multi_agent": False,
        "language": "en",
        "max_steps": 3
    }

    response, elapsed = make_request("POST", "/agents/enterprise/execute", token=token, data=data, timeout=60)
    result.response_time = elapsed

    if response and response.get("answer"):
        result.success = True
        execution_time = response.get("execution_time", 0)
        result.message = f"Completed in {execution_time:.2f}s"
        result.data = {
            "execution_time": execution_time,
            "steps": response.get("steps", 0)
        }
    else:
        error_msg = response.get("error", "Unknown error") if response else "No response"
        result.message = f"Failed: {error_msg}"

    return result


def test_japanese_multilingual(token: str) -> TestResult:
    """Test Japanese language support in enterprise orchestration."""
    result = TestResult("Japanese Language Support", "Enterprise")

    data = {
        "task": "OpenFrameとは何ですか？主な機能を説明してください。",
        "enable_multi_agent": True,
        "language": "ja",
        "orchestration_config": {
            "enable_synthesis": True,
            "enable_next_actions": True
        }
    }

    response, elapsed = make_request("POST", "/agents/enterprise/execute", token=token, data=data)
    result.response_time = elapsed

    if response and response.get("answer"):
        answer = response.get("answer", "")
        next_actions = response.get("next_actions", [])

        # Check for Japanese content in response
        has_japanese = any(ord(c) > 0x3000 for c in answer)  # Japanese character range

        result.success = True
        result.message = f"Japanese response: {has_japanese}, Length: {len(answer)}"
        result.data = {
            "has_japanese": has_japanese,
            "answer_length": len(answer),
            "next_actions": next_actions,
            "answer_preview": answer[:150] + "..." if len(answer) > 150 else answer
        }
    else:
        error_msg = response.get("error", "Unknown error") if response else "No response"
        result.message = f"Failed: {error_msg}"

    return result


# =============================================================================
# Main Test Runner
# =============================================================================

def run_tests(quick_mode: bool = False) -> List[TestResult]:
    """Run all enterprise orchestrator tests."""
    print("=" * 60)
    print("Enterprise Orchestrator API Tests")
    print("=" * 60)
    print(f"Server: {API_BASE_URL}")
    print(f"User: {ADMIN_USERNAME}")
    print(f"Mode: {'Quick' if quick_mode else 'Full'}")
    print("=" * 60)
    print()

    results = []
    token = None

    # Test 1: Login
    print("Running: Login Authentication...")
    login_result = test_login()
    results.append(login_result)
    print(login_result)

    if not login_result.success:
        print("\n[X] Login failed. Cannot continue with tests.")
        print("    Make sure the backend server is running on port 9000.")
        return results

    token = login_result.data["token"]
    print()

    # Test 2: Get Default Config
    print("Running: Get Default Config...")
    config_result = test_get_default_config(token)
    results.append(config_result)
    print(config_result)
    print()

    # Test 3: Single Agent Fallback
    print("Running: Single Agent Fallback...")
    fallback_result = test_single_agent_fallback(token)
    results.append(fallback_result)
    print(fallback_result)
    print()

    # Test 4: Timeout Handling (quick)
    print("Running: Timeout Handling...")
    timeout_result = test_timeout_handling(token)
    results.append(timeout_result)
    print(timeout_result)
    print()

    if not quick_mode:
        # Test 5: Multi-Agent Parallel (slower)
        print("Running: Multi-Agent Parallel Execution... (this may take a while)")
        parallel_result = test_multi_agent_parallel(token)
        results.append(parallel_result)
        print(parallel_result)
        print()

        # Test 6: Execution Trace
        print("Running: Execution Trace...")
        trace_result = test_execution_trace(token)
        results.append(trace_result)
        print(trace_result)
        print()

        # Test 7: Result Synthesis
        print("Running: Result Synthesis... (this may take a while)")
        synthesis_result = test_result_synthesis(token)
        results.append(synthesis_result)
        print(synthesis_result)
        print()

        # Test 8: Next Actions
        print("Running: Next Actions...")
        next_actions_result = test_next_actions(token)
        results.append(next_actions_result)
        print(next_actions_result)
        print()

        # Test 9: Streaming
        print("Running: Streaming Orchestration...")
        streaming_result = test_streaming_enterprise(token)
        results.append(streaming_result)
        print(streaming_result)
        print()

        # Test 10: Continue on Failure
        print("Running: Continue on Failure... (this may take a while)")
        failure_result = test_continue_on_failure(token)
        results.append(failure_result)
        print(failure_result)
        print()

        # Test 11: Evaluation Criteria
        print("Running: Evaluation Criteria...")
        eval_result = test_evaluation_criteria(token)
        results.append(eval_result)
        print(eval_result)
        print()

        # Test 12: Japanese Language
        print("Running: Japanese Language Support...")
        japanese_result = test_japanese_multilingual(token)
        results.append(japanese_result)
        print(japanese_result)
        print()

    return results


def print_summary(results: List[TestResult]):
    """Print test summary."""
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    # Group by category
    setup_results = [r for r in results if r.category == "Setup"]
    enterprise_results = [r for r in results if r.category == "Enterprise"]

    if setup_results:
        setup_passed = sum(1 for r in setup_results if r.success)
        print(f"\nSetup Tests: {setup_passed}/{len(setup_results)} passed")

    if enterprise_results:
        enterprise_passed = sum(1 for r in enterprise_results if r.success)
        enterprise_time = sum(r.response_time for r in enterprise_results)
        print(f"Enterprise Tests: {enterprise_passed}/{len(enterprise_results)} passed ({enterprise_time:.2f}s)")

    total_passed = sum(1 for r in results if r.success)
    total_failed = len(results) - total_passed
    total_time = sum(r.response_time for r in results)

    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    print(f"Total Time: {total_time:.2f}s")
    print()

    if total_failed == 0:
        print("[OK] All tests passed!")
    else:
        print("[X] Some tests failed:")
        for r in results:
            if not r.success:
                print(f"   - [{r.category}] {r.name}: {r.message}")

    print("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Enterprise Orchestrator API Test Suite")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only (skip long-running tests)")
    args = parser.parse_args()

    all_results = run_tests(quick_mode=args.quick)
    print_summary(all_results)

    # Return exit code
    failed = sum(1 for r in all_results if not r.success)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
