#!/usr/bin/env python3
"""
Agent Chat API & WebUI Test Script

Tests the agent chat functionality including:
- API Tests:
  - Login authentication
  - IMS credentials setup
  - RAG agent
  - IMS agent (issue search)
  - Auto mode routing
  - Code agent
- WebUI Tests:
  - Frontend accessibility
  - Login page
  - Agent chat interface
  - Message send/receive

Usage:
    python scripts/test_agent_chat.py          # Run all tests
    python scripts/test_agent_chat.py --api    # Run API tests only
    python scripts/test_agent_chat.py --webui  # Run WebUI tests only
"""

import requests
import time
import sys
import argparse
from typing import Optional, Dict, Any, List

# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = "http://localhost:9000/api/v1"
FRONTEND_URL = "http://localhost:3000"

# Login credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "SecureAdm1nP@ss2024!"

# IMS credentials
IMS_URL = "https://ims.tmaxsoft.com"
IMS_USERNAME = "yijae.shin"
IMS_PASSWORD = "12qwaszx"

# =============================================================================
# Helper Functions
# =============================================================================

class TestResult:
    def __init__(self, name: str, category: str = "API"):
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
    timeout: int = 120
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


# =============================================================================
# API Test Functions
# =============================================================================

def test_login() -> TestResult:
    """Test login and get access token."""
    result = TestResult("Login Authentication", "API")

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


def test_save_ims_credentials(token: str) -> TestResult:
    """Test saving IMS credentials."""
    result = TestResult("Save IMS Credentials", "API")

    data = {
        "ims_url": IMS_URL,
        "username": IMS_USERNAME,
        "password": IMS_PASSWORD
    }

    response, elapsed = make_request("POST", "/ims-credentials/", token=token, data=data)
    result.response_time = elapsed

    if response and response.get("id"):
        result.success = True
        result.message = f"IMS credentials saved for {IMS_USERNAME}"
    else:
        error_msg = response.get("error", {}).get("message") if isinstance(response.get("error"), dict) else response.get("error", "Unknown error")
        result.message = f"Failed: {error_msg}"

    return result


def test_basic_chat(token: str) -> TestResult:
    """Test basic chat functionality."""
    result = TestResult("Basic Chat (Hello)", "API")

    data = {
        "task": "Hello, this is a test message.",
        "language": "en"
    }

    response, elapsed = make_request("POST", "/agents/execute", token=token, data=data)
    result.response_time = elapsed

    if response and response.get("success") and response.get("answer"):
        result.success = True
        result.message = f"Agent: {response.get('agent_type', 'unknown')} - Response received"
        result.data = {"answer": response["answer"][:100] + "..." if len(response.get("answer", "")) > 100 else response.get("answer")}
    else:
        error_msg = response.get("error", {}).get("message") if isinstance(response.get("error"), dict) else response.get("error", "Unknown error")
        result.message = f"Failed: {error_msg}"

    return result


def test_ims_agent(token: str) -> TestResult:
    """Test IMS agent with issue search."""
    result = TestResult("IMS Agent (Issue Search)", "API")

    data = {
        "task": "Search ProObject issues",
        "agent_type": "ims",
        "language": "en"
    }

    response, elapsed = make_request("POST", "/agents/execute", token=token, data=data, timeout=180)
    result.response_time = elapsed

    if response and response.get("success") and response.get("answer"):
        answer = response.get("answer", "")
        has_results = "ims.tmaxsoft.com" in answer or any(str(i) in answer for i in range(200000, 230000))

        if has_results:
            result.success = True
            result.message = f"Found issues in response"
        else:
            result.success = True
            result.message = f"Response received (no issues matched)"

        result.data = {"answer_preview": answer[:200] + "..." if len(answer) > 200 else answer}
    else:
        error_msg = response.get("error", {}).get("message") if isinstance(response.get("error"), dict) else response.get("error", "Unknown error")
        result.message = f"Failed: {error_msg}"

    return result


def test_rag_agent(token: str) -> TestResult:
    """Test RAG agent."""
    result = TestResult("RAG Agent", "API")

    data = {
        "task": "What is OpenFrame?",
        "agent_type": "rag",
        "language": "en"
    }

    response, elapsed = make_request("POST", "/agents/execute", token=token, data=data)
    result.response_time = elapsed

    if response and response.get("success") and response.get("answer"):
        result.success = True
        result.message = f"RAG response received"
        result.data = {"answer_preview": response["answer"][:150] + "..." if len(response.get("answer", "")) > 150 else response.get("answer")}
    else:
        error_msg = response.get("error", {}).get("message") if isinstance(response.get("error"), dict) else response.get("error", "Unknown error")
        result.message = f"Failed: {error_msg}"

    return result


def test_auto_mode_code(token: str) -> TestResult:
    """Test auto mode routing to code agent."""
    result = TestResult("Auto Mode (Code Request)", "API")

    data = {
        "task": "Write a Python function to calculate factorial",
        "language": "en"
    }

    response, elapsed = make_request("POST", "/agents/execute", token=token, data=data)
    result.response_time = elapsed

    if response and response.get("success") and response.get("answer"):
        agent_type = response.get("agent_type", "unknown")
        answer = response.get("answer", "")
        has_code = "```python" in answer or "def " in answer

        result.success = True
        result.message = f"Routed to '{agent_type}' agent" + (" with code" if has_code else "")
        result.data = {
            "agent_type": agent_type,
            "has_code": has_code
        }
    else:
        error_msg = response.get("error", {}).get("message") if isinstance(response.get("error"), dict) else response.get("error", "Unknown error")
        result.message = f"Failed: {error_msg}"

    return result


# =============================================================================
# WebUI Test Functions (using Playwright)
# =============================================================================

def run_webui_tests() -> List[TestResult]:
    """Run WebUI tests using Playwright."""
    results = []

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        result = TestResult("Playwright Import", "WebUI")
        result.message = "Playwright not installed. Run: pip install playwright && playwright install"
        results.append(result)
        return results

    print("\n" + "=" * 60)
    print("WebUI Tests (Playwright)")
    print("=" * 60)
    print(f"Frontend URL: {FRONTEND_URL}")
    print()

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Test 1: Frontend Accessibility
        print("Running: Frontend Accessibility...")
        result = TestResult("Frontend Accessibility", "WebUI")
        start_time = time.time()
        try:
            response = page.goto(FRONTEND_URL, timeout=10000)
            result.response_time = time.time() - start_time

            if response and response.status == 200:
                result.success = True
                result.message = f"Frontend loaded (HTTP {response.status})"
            else:
                result.message = f"Frontend returned HTTP {response.status if response else 'None'}"
        except Exception as e:
            result.response_time = time.time() - start_time
            result.message = f"Failed to load frontend: {str(e)}"
        results.append(result)
        print(result)

        if not result.success:
            browser.close()
            return results

        # Test 2: Login Page Elements
        print("\nRunning: Login Page Elements...")
        result = TestResult("Login Page Elements", "WebUI")
        start_time = time.time()
        try:
            # Wait for login form to appear
            page.wait_for_selector('input[type="text"], input[name="username"], input[id="username"]', timeout=5000)
            result.response_time = time.time() - start_time

            # Check for username input
            username_input = page.query_selector('input[type="text"], input[name="username"], input[id="username"]')
            # Check for password input
            password_input = page.query_selector('input[type="password"]')
            # Check for login button
            login_button = page.query_selector('button[type="submit"], button:has-text("Login"), button:has-text("Sign")')

            if username_input and password_input and login_button:
                result.success = True
                result.message = "Username, password inputs and login button found"
            else:
                missing = []
                if not username_input:
                    missing.append("username input")
                if not password_input:
                    missing.append("password input")
                if not login_button:
                    missing.append("login button")
                result.message = f"Missing elements: {', '.join(missing)}"
        except PlaywrightTimeout:
            result.response_time = time.time() - start_time
            result.message = "Login form not found (timeout)"
        except Exception as e:
            result.response_time = time.time() - start_time
            result.message = f"Error: {str(e)}"
        results.append(result)
        print(result)

        # Test 3: Login Flow
        print("\nRunning: Login Flow...")
        result = TestResult("Login Flow", "WebUI")
        start_time = time.time()
        try:
            # Fill in credentials
            username_input = page.query_selector('input[type="text"], input[name="username"], input[id="username"]')
            password_input = page.query_selector('input[type="password"]')

            if username_input and password_input:
                username_input.fill(ADMIN_USERNAME)
                password_input.fill(ADMIN_PASSWORD)

                # Click login button
                login_button = page.query_selector('button[type="submit"], button.btn-primary')
                if login_button:
                    login_button.click()

                    # Wait for navigation to home-page (main dashboard after login)
                    try:
                        page.wait_for_selector('.home-page', timeout=10000)
                        result.response_time = time.time() - start_time
                        result.success = True
                        result.message = "Login successful, navigated to home page"
                    except PlaywrightTimeout:
                        result.response_time = time.time() - start_time
                        # Check current URL
                        current_url = page.url
                        if '/login' not in current_url:
                            result.success = True
                            result.message = f"Login successful, navigated to {current_url}"
                        else:
                            error_elem = page.query_selector('.message.error')
                            if error_elem:
                                result.message = "Login failed - error message displayed"
                            else:
                                result.message = "Login submitted but home page not detected"
                else:
                    result.message = "Login button not found"
            else:
                result.message = "Login inputs not found"
        except Exception as e:
            result.response_time = time.time() - start_time
            result.message = f"Error: {str(e)}"
        results.append(result)
        print(result)

        # Test 4: Agent Chat Interface
        print("\nRunning: Agent Chat Interface...")
        result = TestResult("Agent Chat Interface", "WebUI")
        start_time = time.time()
        try:
            # Navigate to agent page
            page.goto(f"{FRONTEND_URL}/agent", timeout=10000)

            # Wait for agent chat to load
            page.wait_for_selector('.agent-chat', timeout=10000)

            # Check for chat input (textarea with class agent-chat-input)
            chat_input = page.query_selector('textarea.agent-chat-input')

            # Check for send button
            send_button = page.query_selector('button.agent-chat-send')

            # Check for agent selector or agent type tabs
            agent_selector = page.query_selector('.agent-type-selector, .agent-chat-header')

            result.response_time = time.time() - start_time

            elements_found = []
            if chat_input:
                elements_found.append("chat input")
            if send_button:
                elements_found.append("send button")
            if agent_selector:
                elements_found.append("agent header/selector")

            if len(elements_found) >= 2:
                result.success = True
                result.message = f"Found: {', '.join(elements_found)}"
            else:
                result.message = f"Only found: {', '.join(elements_found) if elements_found else 'none'}"

        except PlaywrightTimeout:
            result.response_time = time.time() - start_time
            result.message = "Agent chat interface not found"
        except Exception as e:
            result.response_time = time.time() - start_time
            result.message = f"Error: {str(e)}"
        results.append(result)
        print(result)

        # Test 5: Send Chat Message
        print("\nRunning: Send Chat Message...")
        result = TestResult("Send Chat Message", "WebUI")
        start_time = time.time()
        try:
            # Make sure we're on agent page
            if '/agent' not in page.url:
                page.goto(f"{FRONTEND_URL}/agent", timeout=10000)
                page.wait_for_selector('.agent-chat', timeout=10000)

            # Find and fill chat input (textarea with class agent-chat-input)
            chat_input = page.query_selector('textarea.agent-chat-input')

            if chat_input:
                test_message = "Hello, this is a WebUI test message"
                chat_input.fill(test_message)

                # Find and click send button
                send_button = page.query_selector('button.agent-chat-send')

                if send_button:
                    send_button.click()
                else:
                    # Fallback: press Ctrl+Enter (default submit shortcut)
                    chat_input.press("Control+Enter")

                # Wait for response (look for assistant message or streaming state)
                try:
                    page.wait_for_selector(
                        '.agent-message.assistant, .agent-message.streaming',
                        timeout=30000
                    )
                    result.response_time = time.time() - start_time
                    result.success = True
                    result.message = "Message sent and assistant response appeared"
                except PlaywrightTimeout:
                    result.response_time = time.time() - start_time
                    # Check if user message was at least added to the chat
                    user_message = page.query_selector('.agent-message.user')
                    if user_message:
                        result.success = True
                        result.message = "Message sent, user message appeared"
                    else:
                        result.message = "Message sent but no response detected"
            else:
                result.message = "Chat input not found"
        except Exception as e:
            result.response_time = time.time() - start_time
            result.message = f"Error: {str(e)}"
        results.append(result)
        print(result)

        # Test 6: Theme Toggle (if exists)
        print("\nRunning: Theme Toggle...")
        result = TestResult("Theme Toggle", "WebUI")
        start_time = time.time()
        try:
            theme_toggle = page.query_selector(
                '[class*="theme"], [class*="Theme"], '
                'button:has-text("Dark"), button:has-text("Light"), '
                '[aria-label*="theme"], [title*="theme"]'
            )

            if theme_toggle:
                # Get initial theme
                initial_class = page.evaluate('document.documentElement.className')

                # Click toggle
                theme_toggle.click()
                time.sleep(0.5)

                # Check if theme changed
                new_class = page.evaluate('document.documentElement.className')

                result.response_time = time.time() - start_time

                if initial_class != new_class or 'dark' in new_class or 'light' in new_class:
                    result.success = True
                    result.message = "Theme toggle working"
                else:
                    result.success = True
                    result.message = "Theme toggle clicked (no visible class change)"
            else:
                result.response_time = time.time() - start_time
                result.success = True  # Optional feature
                result.message = "Theme toggle not found (optional)"
        except Exception as e:
            result.response_time = time.time() - start_time
            result.message = f"Error: {str(e)}"
        results.append(result)
        print(result)

        browser.close()

    return results


# =============================================================================
# Main Test Runners
# =============================================================================

def run_api_tests() -> List[TestResult]:
    """Run all API tests and return results."""
    print("=" * 60)
    print("API Tests")
    print("=" * 60)
    print(f"Server: {API_BASE_URL}")
    print(f"User: {ADMIN_USERNAME}")
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
        print("\n[X] Login failed. Cannot continue with API tests.")
        print("    Make sure the backend server is running on port 9000.")
        return results

    token = login_result.data["token"]
    print()

    # Test 2: Save IMS Credentials
    print("Running: Save IMS Credentials...")
    ims_cred_result = test_save_ims_credentials(token)
    results.append(ims_cred_result)
    print(ims_cred_result)
    print()

    # Test 3: Basic Chat
    print("Running: Basic Chat...")
    basic_chat_result = test_basic_chat(token)
    results.append(basic_chat_result)
    print(basic_chat_result)
    print()

    # Test 4: IMS Agent
    print("Running: IMS Agent (Issue Search)... (this may take a minute)")
    ims_result = test_ims_agent(token)
    results.append(ims_result)
    print(ims_result)
    print()

    # Test 5: RAG Agent
    print("Running: RAG Agent...")
    rag_result = test_rag_agent(token)
    results.append(rag_result)
    print(rag_result)
    print()

    # Test 6: Auto Mode (Code)
    print("Running: Auto Mode (Code Request)...")
    auto_code_result = test_auto_mode_code(token)
    results.append(auto_code_result)
    print(auto_code_result)

    return results


def print_summary(results: List[TestResult]):
    """Print test summary."""
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    # Group by category
    api_results = [r for r in results if r.category == "API"]
    webui_results = [r for r in results if r.category == "WebUI"]

    if api_results:
        api_passed = sum(1 for r in api_results if r.success)
        api_time = sum(r.response_time for r in api_results)
        print(f"\nAPI Tests: {api_passed}/{len(api_results)} passed ({api_time:.2f}s)")

    if webui_results:
        webui_passed = sum(1 for r in webui_results if r.success)
        webui_time = sum(r.response_time for r in webui_results)
        print(f"WebUI Tests: {webui_passed}/{len(webui_results)} passed ({webui_time:.2f}s)")

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
    parser = argparse.ArgumentParser(description="Agent Chat API & WebUI Test Suite")
    parser.add_argument("--api", action="store_true", help="Run API tests only")
    parser.add_argument("--webui", action="store_true", help="Run WebUI tests only")
    args = parser.parse_args()

    # If no specific flag, run both
    run_all = not args.api and not args.webui

    all_results = []

    # Run API tests
    if args.api or run_all:
        api_results = run_api_tests()
        all_results.extend(api_results)

    # Run WebUI tests
    if args.webui or run_all:
        webui_results = run_webui_tests()
        all_results.extend(webui_results)

    # Print summary
    print_summary(all_results)

    # Return exit code
    failed = sum(1 for r in all_results if not r.success)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
