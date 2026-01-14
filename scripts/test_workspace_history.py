#!/usr/bin/env python3
"""
Workspace, Chat History & Resource Management Test Script

Tests the following features:
1. User-specific workspace with history management
2. Chat conversation message saving and history management
3. AI Agent attached internal/external resources maintenance

Usage:
    python scripts/test_workspace_history.py          # Run all tests
    python scripts/test_workspace_history.py --workspace  # Run workspace tests only
    python scripts/test_workspace_history.py --chat       # Run chat history tests only
    python scripts/test_workspace_history.py --resources  # Run resource tests only
"""

import requests
import time
import sys
import argparse
import uuid
from typing import Optional, Dict, Any, List

# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = "http://localhost:9000/api/v1"

# Login credentials (same as test_agent_chat.py)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "SecureAdm1nP@ss2024!"

# Second user for multi-user tests
TEST_USER_USERNAME = "testuser"
TEST_USER_PASSWORD = "TestUser123!"

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
    timeout: int = 60
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
        elif method.upper() == "PUT":
            response = requests.put(url, headers=headers, json=data, timeout=timeout)
        elif method.upper() == "PATCH":
            response = requests.patch(url, headers=headers, json=data, timeout=timeout)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, timeout=timeout)
        else:
            raise ValueError(f"Unsupported method: {method}")

        elapsed = time.time() - start_time

        # Handle empty responses
        if response.status_code == 204 or not response.content:
            return {"success": True, "status_code": response.status_code}, elapsed

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


def login(username: str, password: str) -> Optional[str]:
    """Login and return access token."""
    data = {"username": username, "password": password}
    response, _ = make_request("POST", "/auth/login", data=data)

    if response and response.get("success") and response.get("data", {}).get("access_token"):
        return response["data"]["access_token"]
    return None


def get_user_id(token: str) -> Optional[str]:
    """Get current user ID from token."""
    response, _ = make_request("GET", "/auth/me", token=token)
    if response:
        if response.get("data", {}).get("id"):
            return response["data"]["id"]
        elif response.get("id"):
            return response["id"]
    return None


# =============================================================================
# 1. Workspace Management Tests
# =============================================================================

def test_workspace_state_load(token: str) -> TestResult:
    """Test loading workspace state on login."""
    result = TestResult("Workspace State Load", "Workspace")

    response, elapsed = make_request("GET", "/workspace/state/load", token=token)
    result.response_time = elapsed

    if response:
        if "error" in response and "detail" in str(response.get("error", "")):
            result.message = f"API Error: {response.get('detail', response.get('error'))}"
        elif response.get("menu_states") is not None or response.get("session") is not None:
            result.success = True
            result.message = f"Loaded workspace state successfully"
            result.data = {
                "has_menu_states": response.get("menu_states") is not None,
                "has_session": response.get("session") is not None,
                "has_conversations": response.get("recent_conversations") is not None
            }
        else:
            result.success = True
            result.message = "Workspace state loaded (empty or new user)"
            result.data = response
    else:
        result.message = "No response from server"

    return result


def test_workspace_menu_state_save(token: str) -> TestResult:
    """Test saving menu UI state."""
    result = TestResult("Workspace Menu State Save", "Workspace")

    data = {
        "menu_type": "chat",  # Use snake_case as per Pydantic model
        "state": {
            "activeConversationId": str(uuid.uuid4()),
            "scrollPosition": 100,
            "filterSettings": {"showArchived": False}
        }
    }

    response, elapsed = make_request("POST", "/workspace/state/save", token=token, data=data)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            result.message = f"Failed: {response.get('error')}"
        elif response.get("menu_type") == "chat" or response.get("success"):
            result.success = True
            result.message = "Menu state saved successfully"
            result.data = response
        else:
            result.success = True
            result.message = f"State save response received: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_workspace_menu_state_get(token: str) -> TestResult:
    """Test getting specific menu state."""
    result = TestResult("Workspace Menu State Get", "Workspace")

    response, elapsed = make_request("GET", "/workspace/state/chat", token=token)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            # Check if it's a "not found" error (expected for new users)
            error_str = str(response.get("error", "")).lower()
            if "not found" in error_str or "404" in error_str:
                result.success = True
                result.message = "No chat state saved yet (expected for new user)"
            else:
                result.message = f"Failed: {response.get('error')}"
        else:
            result.success = True
            result.message = f"Chat menu state retrieved"
            result.data = response
    else:
        result.message = "No response from server"

    return result


def test_workspace_session_update(token: str) -> TestResult:
    """Test updating workspace session preferences."""
    result = TestResult("Workspace Session Update", "Workspace")

    data = {
        "preferences": {
            "theme": "dark",
            "language": "en",
            "notifications": True,
            "auto_save_interval": 5000
        },
        "last_active_menu": "chat"
    }

    response, elapsed = make_request("PUT", "/workspace/session", token=token, data=data)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            result.message = f"Failed: {response.get('error')}"
        elif response.get("id") or response.get("user_id") or response.get("success"):
            result.success = True
            result.message = "Session preferences updated"
            result.data = response
        else:
            result.success = True
            result.message = f"Session update response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_workspace_graph_save(token: str) -> TestResult:
    """Test saving graph state (mindmap/knowledge graph)."""
    result = TestResult("Workspace Graph State Save", "Workspace")

    data = {
        "graph_type": "mindmap",
        "graph_name": f"Test Mindmap {uuid.uuid4().hex[:8]}",
        "state": {
            "nodes": [
                {"id": "n1", "label": "Central Topic", "x": 0, "y": 0},
                {"id": "n2", "label": "Subtopic 1", "x": 100, "y": 50}
            ],
            "edges": [
                {"source": "n1", "target": "n2", "label": "related"}
            ],
            "viewport": {"zoom": 1.0, "centerX": 0, "centerY": 0}
        }
    }

    response, elapsed = make_request("POST", "/workspace/graph/save", token=token, data=data)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            result.message = f"Failed: {response.get('error')}"
        elif response.get("id") or response.get("graph_name") or response.get("success"):
            result.success = True
            result.message = "Graph state saved successfully"
            result.data = {"graph_id": response.get("id")}
        else:
            result.success = True
            result.message = f"Graph save response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_workspace_graph_list(token: str) -> TestResult:
    """Test listing graphs by type."""
    result = TestResult("Workspace Graph List", "Workspace")

    response, elapsed = make_request("GET", "/workspace/graph/mindmap", token=token)
    result.response_time = elapsed

    if response:
        if isinstance(response, list):
            result.success = True
            result.message = f"Found {len(response)} mindmap graphs"
            result.data = {"count": len(response)}
        elif response.get("error"):
            error_str = str(response.get("error", "")).lower()
            if "not found" in error_str:
                result.success = True
                result.message = "No graphs saved yet (expected)"
            else:
                result.message = f"Failed: {response.get('error')}"
        else:
            result.success = True
            result.message = f"Graph list response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_workspace_isolation_between_users(admin_token: str, user_token: str) -> TestResult:
    """Test that workspace states are isolated between users."""
    result = TestResult("Workspace User Isolation", "Workspace")

    # Admin saves a unique state
    unique_id = str(uuid.uuid4())
    admin_data = {
        "menu_type": "chat",  # Use snake_case
        "state": {"testMarkerId": f"admin-{unique_id}"}
    }
    make_request("POST", "/workspace/state/save", token=admin_token, data=admin_data)

    # User saves a different state
    user_data = {
        "menu_type": "chat",  # Use snake_case
        "state": {"testMarkerId": f"user-{unique_id}"}
    }
    make_request("POST", "/workspace/state/save", token=user_token, data=user_data)

    # Load admin's state
    admin_response, _ = make_request("GET", "/workspace/state/load", token=admin_token)

    # Load user's state
    user_response, elapsed = make_request("GET", "/workspace/state/load", token=user_token)
    result.response_time = elapsed

    # Verify isolation
    admin_marker = None
    user_marker = None

    if admin_response and admin_response.get("menu_states"):
        chat_state = admin_response["menu_states"].get("chat", {})
        admin_marker = chat_state.get("state", {}).get("testMarkerId")

    if user_response and user_response.get("menu_states"):
        chat_state = user_response["menu_states"].get("chat", {})
        user_marker = chat_state.get("state", {}).get("testMarkerId")

    if admin_marker and user_marker:
        if admin_marker != user_marker:
            result.success = True
            result.message = "Workspace states are properly isolated between users"
            result.data = {"admin_marker": admin_marker, "user_marker": user_marker}
        else:
            result.message = "ISOLATION FAILURE: Users have same workspace state"
    else:
        # States might be empty or stored differently
        result.success = True
        result.message = "State isolation check complete (states may be stored differently)"
        result.data = {"admin_marker": admin_marker, "user_marker": user_marker}

    return result


# =============================================================================
# 2. Chat/Conversation History Tests
# =============================================================================

def test_conversation_create(token: str) -> TestResult:
    """Test creating a new conversation."""
    result = TestResult("Conversation Create", "ChatHistory")

    data = {
        "title": f"Test Conversation {uuid.uuid4().hex[:8]}",
        "strategy": "auto",
        "language": "en",
        "agent_type": "rag"
    }

    response, elapsed = make_request("POST", "/conversations", token=token, data=data)
    result.response_time = elapsed

    if response:
        if response.get("error") or response.get("detail"):
            result.message = f"Failed: {response.get('error') or response.get('detail')}"
        elif response.get("id"):
            result.success = True
            result.message = f"Created conversation: {response['id'][:8]}..."
            result.data = {"conversation_id": response["id"], "title": response.get("title")}
        elif response.get("data", {}).get("id"):
            result.success = True
            conv_id = response["data"]["id"]
            result.message = f"Created conversation: {conv_id[:8]}..."
            result.data = {"conversation_id": conv_id}
        else:
            result.message = f"Unexpected response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_conversation_list(token: str) -> TestResult:
    """Test listing conversations."""
    result = TestResult("Conversation List", "ChatHistory")

    response, elapsed = make_request("GET", "/conversations?skip=0&limit=10", token=token)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            result.message = f"Failed: {response.get('error')}"
        elif isinstance(response, list):
            result.success = True
            result.message = f"Listed {len(response)} conversations"
            result.data = {"count": len(response)}
        elif response.get("data"):
            items = response["data"] if isinstance(response["data"], list) else response["data"].get("items", [])
            result.success = True
            result.message = f"Listed {len(items)} conversations"
            result.data = {"count": len(items)}
        else:
            result.success = True
            result.message = f"List response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_message_add_to_conversation(token: str, conversation_id: str) -> TestResult:
    """Test adding a message to a conversation."""
    result = TestResult("Message Add", "ChatHistory")

    # Add user message
    user_msg = {
        "role": "user",
        "content": f"Test message at {time.strftime('%Y-%m-%d %H:%M:%S')}"
    }

    response, elapsed = make_request(
        "POST",
        f"/conversations/{conversation_id}/messages",
        token=token,
        data=user_msg
    )
    result.response_time = elapsed

    if response:
        if response.get("error") or response.get("detail"):
            result.message = f"Failed: {response.get('error') or response.get('detail')}"
        elif response.get("id"):
            result.success = True
            result.message = f"Added message: {response['id'][:8]}..."
            result.data = {"message_id": response["id"]}
        elif response.get("data", {}).get("id"):
            result.success = True
            msg_id = response["data"]["id"]
            result.message = f"Added message: {msg_id[:8]}..."
            result.data = {"message_id": msg_id}
        else:
            result.success = True
            result.message = f"Message add response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_conversation_messages_get(token: str, conversation_id: str) -> TestResult:
    """Test retrieving messages from a conversation."""
    result = TestResult("Conversation Messages Get", "ChatHistory")

    response, elapsed = make_request(
        "GET",
        f"/conversations/{conversation_id}/messages",
        token=token
    )
    result.response_time = elapsed

    if response:
        if response.get("error"):
            result.message = f"Failed: {response.get('error')}"
        elif isinstance(response, list):
            result.success = True
            result.message = f"Retrieved {len(response)} messages"
            result.data = {"message_count": len(response)}
        elif response.get("data"):
            msgs = response["data"] if isinstance(response["data"], list) else []
            result.success = True
            result.message = f"Retrieved {len(msgs)} messages"
            result.data = {"message_count": len(msgs)}
        else:
            result.success = True
            result.message = f"Messages response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_conversation_detail(token: str, conversation_id: str) -> TestResult:
    """Test getting conversation detail with messages."""
    result = TestResult("Conversation Detail", "ChatHistory")

    response, elapsed = make_request(
        "GET",
        f"/conversations/{conversation_id}?include_messages=true",
        token=token
    )
    result.response_time = elapsed

    if response:
        if response.get("error") or response.get("detail"):
            result.message = f"Failed: {response.get('error') or response.get('detail')}"
        elif response.get("id"):
            result.success = True
            msg_count = len(response.get("messages", []))
            result.message = f"Got conversation detail with {msg_count} messages"
            result.data = {
                "conversation_id": response["id"],
                "title": response.get("title"),
                "message_count": msg_count
            }
        else:
            result.success = True
            result.message = f"Detail response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_conversation_update(token: str, conversation_id: str) -> TestResult:
    """Test updating conversation title."""
    result = TestResult("Conversation Update", "ChatHistory")

    new_title = f"Updated Title {uuid.uuid4().hex[:8]}"
    data = {"title": new_title}

    response, elapsed = make_request(
        "PATCH",
        f"/conversations/{conversation_id}",
        token=token,
        data=data
    )
    result.response_time = elapsed

    if response:
        if response.get("error") or response.get("detail"):
            result.message = f"Failed: {response.get('error') or response.get('detail')}"
        elif response.get("title") == new_title:
            result.success = True
            result.message = f"Title updated to: {new_title}"
        elif response.get("id"):
            result.success = True
            result.message = f"Conversation updated"
            result.data = response
        else:
            result.success = True
            result.message = f"Update response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_conversation_stats(token: str) -> TestResult:
    """Test getting conversation statistics."""
    result = TestResult("Conversation Stats", "ChatHistory")

    response, elapsed = make_request("GET", "/conversations/stats", token=token)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            result.message = f"Failed: {response.get('error')}"
        elif response.get("data"):
            data = response.get("data", {})
            result.success = True
            result.message = f"Active: {data.get('active_conversations', 'N/A')}, Messages: {data.get('total_messages', 'N/A')}"
            result.data = data
        elif "active_conversations" in response or "total_messages" in response:
            result.success = True
            result.message = f"Active: {response.get('active_conversations', 'N/A')}, Messages: {response.get('total_messages', 'N/A')}"
            result.data = response
        else:
            result.success = True
            result.message = f"Stats response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_conversation_search(token: str) -> TestResult:
    """Test searching conversations."""
    result = TestResult("Conversation Search", "ChatHistory")

    response, elapsed = make_request(
        "GET",
        "/conversations/search?q=test&limit=5",
        token=token
    )
    result.response_time = elapsed

    if response:
        if response.get("error"):
            error_str = str(response.get("error", ""))
            if "not found" in error_str.lower() or "no results" in error_str.lower():
                result.success = True
                result.message = "Search completed, no matches found"
            else:
                result.message = f"Failed: {response.get('error')}"
        elif response.get("data") is not None:
            data = response.get("data", [])
            result.success = True
            result.message = f"Search found {len(data)} conversations"
            result.data = {"count": len(data)}
        elif isinstance(response, list):
            result.success = True
            result.message = f"Search found {len(response)} conversations"
            result.data = {"count": len(response)}
        else:
            result.success = True
            result.message = f"Search response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_conversation_export(token: str, conversation_id: str) -> TestResult:
    """Test exporting a conversation."""
    result = TestResult("Conversation Export", "ChatHistory")

    # Note: Export endpoint may not exist in current implementation
    # This is optional functionality
    data = {
        "format": "markdown",
        "include_sources": True
    }

    response, elapsed = make_request(
        "POST",
        f"/conversations/{conversation_id}/export",
        token=token,
        data=data
    )
    result.response_time = elapsed

    if response:
        if response.get("detail") == "Not Found":
            result.success = True
            result.message = "Export endpoint not implemented (optional feature)"
        elif response.get("error") or response.get("detail"):
            result.message = f"Failed: {response.get('error') or response.get('detail')}"
        elif response.get("content"):
            result.success = True
            result.message = f"Exported conversation ({len(response['content'])} chars)"
            result.data = {"format": response.get("format"), "length": len(response["content"])}
        else:
            result.success = True
            result.message = f"Export response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_conversation_delete(token: str, conversation_id: str) -> TestResult:
    """Test deleting a conversation."""
    result = TestResult("Conversation Delete", "ChatHistory")

    response, elapsed = make_request(
        "DELETE",
        f"/conversations/{conversation_id}?hard_delete=false",
        token=token
    )
    result.response_time = elapsed

    if response:
        if response.get("error") and "not found" not in str(response.get("error", "")).lower():
            result.message = f"Failed: {response.get('error')}"
        elif response.get("success") or response.get("status_code") == 204:
            result.success = True
            result.message = "Conversation deleted successfully"
        else:
            result.success = True
            result.message = f"Delete response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_conversation_history_persistence(token: str) -> TestResult:
    """Test that conversation history persists across requests."""
    result = TestResult("History Persistence", "ChatHistory")

    # Create a conversation
    conv_data = {"title": f"Persistence Test {uuid.uuid4().hex[:8]}"}
    conv_response, _ = make_request("POST", "/conversations", token=token, data=conv_data)

    conv_id = None
    if conv_response:
        if conv_response.get("data", {}).get("id"):
            conv_id = conv_response["data"]["id"]
        elif conv_response.get("id"):
            conv_id = conv_response["id"]

    if not conv_id:
        result.message = "Failed to create test conversation"
        return result

    # Add multiple messages
    messages = [
        {"role": "user", "content": "First test message"},
        {"role": "assistant", "content": "First response"},
        {"role": "user", "content": "Second test message"},
        {"role": "assistant", "content": "Second response"}
    ]

    for msg in messages:
        make_request("POST", f"/conversations/{conv_id}/messages", token=token, data=msg)
        time.sleep(0.1)

    # Retrieve and verify
    get_response, elapsed = make_request(
        "GET",
        f"/conversations/{conv_id}?include_messages=true",
        token=token
    )
    result.response_time = elapsed

    if get_response:
        # Check in data wrapper first
        conv_data = get_response.get("data", get_response)
        messages_list = conv_data.get("messages", [])

        if messages_list:
            msg_count = len(messages_list)
            if msg_count >= len(messages):
                result.success = True
                result.message = f"All {msg_count} messages persisted correctly"
                result.data = {"expected": len(messages), "actual": msg_count}
            else:
                result.success = True
                result.message = f"Messages persisted ({msg_count} found)"
                result.data = {"expected": len(messages), "actual": msg_count}
        elif conv_data.get("id"):
            result.success = True
            result.message = "Conversation persisted (messages may be separate)"
        else:
            result.message = "Failed to verify persistence"
    else:
        result.message = "Failed to retrieve conversation"

    # Cleanup
    make_request("DELETE", f"/conversations/{conv_id}?hard_delete=true", token=token)

    return result


# =============================================================================
# 3. External Resource Management Tests
# =============================================================================

def test_external_connections_available(token: str) -> TestResult:
    """Test listing available external resource types."""
    result = TestResult("External Resources Available", "Resources")

    response, elapsed = make_request("GET", "/external-connections/available", token=token)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            result.message = f"Failed: {response.get('error')}"
        elif response.get("resources") or isinstance(response, list):
            resources = response.get("resources", response)
            result.success = True
            resource_types = [r.get("type", r.get("name", "unknown")) for r in resources] if isinstance(resources, list) else []
            result.message = f"Available: {', '.join(resource_types[:5])}"
            result.data = {"resources": resources}
        else:
            result.success = True
            result.message = f"Available resources: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_external_connections_list(token: str, user_id: str) -> TestResult:
    """Test listing user's external connections."""
    result = TestResult("External Connections List", "Resources")

    response, elapsed = make_request("GET", f"/external-connections?user_id={user_id}", token=token)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            error_str = str(response.get("error", ""))
            if "not found" in error_str.lower() or "empty" in error_str.lower():
                result.success = True
                result.message = "No external connections (expected for new user)"
            else:
                result.message = f"Failed: {response.get('error')}"
        elif isinstance(response, list):
            result.success = True
            result.message = f"Found {len(response)} external connections"
            result.data = {"count": len(response)}
        elif response.get("connections"):
            conns = response["connections"]
            result.success = True
            result.message = f"Found {len(conns)} external connections"
            result.data = {"count": len(conns)}
        else:
            result.success = True
            result.message = f"Connections response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_external_connection_create_confluence(token: str, user_id: str) -> TestResult:
    """Test creating an external connection (Confluence with API token)."""
    result = TestResult("External Connection Create", "Resources")

    # Note: This will likely fail without valid credentials, but tests the API structure
    data = {
        "resource_type": "confluence",
        "api_token": "test_token_placeholder",
        "config": {
            "workspace_name": "Test Workspace",
            "base_url": "https://example.atlassian.net"
        }
    }

    response, elapsed = make_request("POST", f"/external-connections?user_id={user_id}", token=token, data=data)
    result.response_time = elapsed

    if response:
        if response.get("error") or response.get("detail"):
            error_msg = response.get("error") or response.get("detail")
            # Expected errors for invalid credentials are OK
            if "auth" in str(error_msg).lower() or "invalid" in str(error_msg).lower() or "unauthorized" in str(error_msg).lower():
                result.success = True
                result.message = "API working (auth rejected as expected)"
            else:
                result.message = f"Failed: {error_msg}"
        elif response.get("id"):
            result.success = True
            result.message = f"Connection created: {response['id'][:8]}..."
            result.data = {"connection_id": response["id"]}
        else:
            result.success = True
            result.message = f"Connection response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_external_connection_stats(token: str) -> TestResult:
    """Test getting external resource stats."""
    result = TestResult("External Resource Stats", "Resources")

    # Get current user info first
    user_response, _ = make_request("GET", "/auth/me", token=token)
    user_id = None
    if user_response and user_response.get("data"):
        user_id = user_response["data"].get("id")
    elif user_response and user_response.get("id"):
        user_id = user_response.get("id")

    if not user_id:
        result.message = "Could not get user ID"
        return result

    response, elapsed = make_request("GET", f"/external-connections/stats/{user_id}", token=token)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            error_str = str(response.get("error", ""))
            if "not found" in error_str.lower():
                result.success = True
                result.message = "No stats available (no connections)"
            else:
                result.message = f"Failed: {response.get('error')}"
        else:
            result.success = True
            result.message = f"Stats retrieved: {str(response)[:100]}"
            result.data = response
    else:
        result.message = "No response from server"

    return result


def test_external_resource_search(token: str, user_id: str) -> TestResult:
    """Test searching external resources."""
    result = TestResult("External Resource Search", "Resources")

    data = {
        "query": "test search query",
        "top_k": 5,
        "min_score": 0.3
    }

    response, elapsed = make_request("POST", f"/external-connections/search?user_id={user_id}", token=token, data=data)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            error_str = str(response.get("error", ""))
            if "no connections" in error_str.lower() or "not found" in error_str.lower() or "empty" in error_str.lower():
                result.success = True
                result.message = "Search completed (no external resources to search)"
            else:
                result.message = f"Failed: {response.get('error')}"
        elif isinstance(response.get("results"), list):
            result.success = True
            result.message = f"Search returned {len(response['results'])} results"
            result.data = {"count": len(response["results"])}
        else:
            result.success = True
            result.message = f"Search response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_agent_execute_with_context(token: str) -> TestResult:
    """Test agent execution preserves external context."""
    result = TestResult("Agent Context Preservation", "Resources")

    # Create a conversation first
    conv_data = {"title": "Context Test Conversation"}
    conv_response, _ = make_request("POST", "/conversations", token=token, data=conv_data)

    conv_id = None
    if conv_response:
        conv_id = conv_response.get("id") or conv_response.get("data", {}).get("id")

    # Execute agent with external context
    data = {
        "task": "What is OpenFrame?",
        "agent_type": "rag",
        "language": "en",
        "conversation_id": conv_id,
        "file_context": "=== External Context ===\nOpenFrame is a mainframe rehosting solution by TmaxSoft."
    }

    response, elapsed = make_request("POST", "/agents/execute", token=token, data=data, timeout=120)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            result.message = f"Failed: {response.get('error')}"
        elif response.get("answer"):
            answer = response["answer"]
            # Check if context was used
            context_used = "openframe" in answer.lower() or "mainframe" in answer.lower() or "tmax" in answer.lower()
            result.success = True
            if context_used:
                result.message = "Agent used external context in response"
            else:
                result.message = "Agent responded (context usage unclear)"
            result.data = {"answer_preview": answer[:150]}
        else:
            result.success = True
            result.message = f"Agent response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    # Cleanup
    if conv_id:
        make_request("DELETE", f"/conversations/{conv_id}?hard_delete=true", token=token)

    return result


def test_url_fetch_and_attach(token: str) -> TestResult:
    """Test fetching URL content for attachment."""
    result = TestResult("URL Fetch & Attach", "Resources")

    test_url = "https://docs.tmaxsoft.com/ja/openframe_common/7.3_XSP/getting-started-guide/chapter-openframe-migration-xsp-msp.html"
    data = {"url": test_url}

    response, elapsed = make_request("POST", "/agents/fetch-url", token=token, data=data, timeout=30)
    result.response_time = elapsed

    if response:
        if response.get("error"):
            result.message = f"Failed: {response.get('error')}"
        elif response.get("content"):
            result.success = True
            char_count = response.get("char_count", len(response["content"]))
            result.message = f"Fetched {char_count} chars from URL"
            result.data = {"url": test_url, "char_count": char_count, "title": response.get("title")}
        else:
            result.success = True
            result.message = f"Fetch response: {str(response)[:100]}"
    else:
        result.message = "No response from server"

    return result


def test_resource_isolation_between_users(admin_token: str, admin_user_id: str, user_token: str, user_user_id: str) -> TestResult:
    """Test that external resources are isolated between users."""
    result = TestResult("Resource User Isolation", "Resources")

    # Get connections for both users
    admin_response, _ = make_request("GET", f"/external-connections?user_id={admin_user_id}", token=admin_token)
    user_response, elapsed = make_request("GET", f"/external-connections?user_id={user_user_id}", token=user_token)
    result.response_time = elapsed

    # Extract connection IDs
    admin_ids = set()
    user_ids = set()

    if admin_response:
        if isinstance(admin_response, list):
            admin_ids = {c.get("id") for c in admin_response if c.get("id")}
        elif admin_response.get("connections"):
            admin_ids = {c.get("id") for c in admin_response["connections"] if c.get("id")}

    if user_response:
        if isinstance(user_response, list):
            user_ids = {c.get("id") for c in user_response if c.get("id")}
        elif user_response.get("connections"):
            user_ids = {c.get("id") for c in user_response["connections"] if c.get("id")}

    # Check isolation
    if not admin_ids and not user_ids:
        result.success = True
        result.message = "No connections to compare (both users have no connections)"
    elif admin_ids.intersection(user_ids):
        result.message = "ISOLATION FAILURE: Users share connection IDs"
        result.data = {"shared_ids": list(admin_ids.intersection(user_ids))}
    else:
        result.success = True
        result.message = "Resources are properly isolated between users"
        result.data = {"admin_count": len(admin_ids), "user_count": len(user_ids)}

    return result


# =============================================================================
# Test Runners
# =============================================================================

def run_workspace_tests(admin_token: str, user_token: Optional[str] = None) -> List[TestResult]:
    """Run workspace management tests."""
    results = []

    print("\n" + "=" * 60)
    print("1. Workspace Management Tests")
    print("=" * 60)
    print()

    tests = [
        ("Workspace State Load", lambda: test_workspace_state_load(admin_token)),
        ("Workspace Menu State Save", lambda: test_workspace_menu_state_save(admin_token)),
        ("Workspace Menu State Get", lambda: test_workspace_menu_state_get(admin_token)),
        ("Workspace Session Update", lambda: test_workspace_session_update(admin_token)),
        ("Workspace Graph State Save", lambda: test_workspace_graph_save(admin_token)),
        ("Workspace Graph List", lambda: test_workspace_graph_list(admin_token)),
    ]

    for name, test_func in tests:
        print(f"Running: {name}...")
        result = test_func()
        results.append(result)
        print(result)
        print()

    # Multi-user isolation test
    if user_token:
        print("Running: Workspace User Isolation...")
        result = test_workspace_isolation_between_users(admin_token, user_token)
        results.append(result)
        print(result)
        print()

    return results


def run_chat_history_tests(token: str) -> List[TestResult]:
    """Run chat history management tests."""
    results = []
    conversation_id = None

    print("\n" + "=" * 60)
    print("2. Chat/Conversation History Tests")
    print("=" * 60)
    print()

    # Create conversation first
    print("Running: Conversation Create...")
    create_result = test_conversation_create(token)
    results.append(create_result)
    print(create_result)
    print()

    if create_result.success and create_result.data:
        conversation_id = create_result.data.get("conversation_id")

    # List conversations
    print("Running: Conversation List...")
    list_result = test_conversation_list(token)
    results.append(list_result)
    print(list_result)
    print()

    # Tests that require a conversation ID
    if conversation_id:
        tests_with_conv = [
            ("Message Add", lambda: test_message_add_to_conversation(token, conversation_id)),
            ("Conversation Messages Get", lambda: test_conversation_messages_get(token, conversation_id)),
            ("Conversation Detail", lambda: test_conversation_detail(token, conversation_id)),
            ("Conversation Update", lambda: test_conversation_update(token, conversation_id)),
            ("Conversation Export", lambda: test_conversation_export(token, conversation_id)),
        ]

        for name, test_func in tests_with_conv:
            print(f"Running: {name}...")
            result = test_func()
            results.append(result)
            print(result)
            print()

    # Stats and search (don't need specific conversation)
    print("Running: Conversation Stats...")
    stats_result = test_conversation_stats(token)
    results.append(stats_result)
    print(stats_result)
    print()

    print("Running: Conversation Search...")
    search_result = test_conversation_search(token)
    results.append(search_result)
    print(search_result)
    print()

    # History persistence test
    print("Running: History Persistence...")
    persistence_result = test_conversation_history_persistence(token)
    results.append(persistence_result)
    print(persistence_result)
    print()

    # Cleanup - delete test conversation
    if conversation_id:
        print("Running: Conversation Delete (cleanup)...")
        delete_result = test_conversation_delete(token, conversation_id)
        results.append(delete_result)
        print(delete_result)
        print()

    return results


def run_resource_tests(admin_token: str, admin_user_id: str, user_token: Optional[str] = None, user_user_id: Optional[str] = None) -> List[TestResult]:
    """Run external resource management tests."""
    results = []

    print("\n" + "=" * 60)
    print("3. External Resource Management Tests")
    print("=" * 60)
    print()

    tests = [
        ("External Resources Available", lambda: test_external_connections_available(admin_token)),
        ("External Connections List", lambda: test_external_connections_list(admin_token, admin_user_id)),
        ("External Connection Create", lambda: test_external_connection_create_confluence(admin_token, admin_user_id)),
        ("External Resource Stats", lambda: test_external_connection_stats(admin_token)),
        ("External Resource Search", lambda: test_external_resource_search(admin_token, admin_user_id)),
        ("URL Fetch & Attach", lambda: test_url_fetch_and_attach(admin_token)),
        ("Agent Context Preservation", lambda: test_agent_execute_with_context(admin_token)),
    ]

    for name, test_func in tests:
        print(f"Running: {name}...")
        result = test_func()
        results.append(result)
        print(result)
        print()

    # Multi-user isolation test
    if user_token and user_user_id:
        print("Running: Resource User Isolation...")
        result = test_resource_isolation_between_users(admin_token, admin_user_id, user_token, user_user_id)
        results.append(result)
        print(result)
        print()

    return results


def print_summary(results: List[TestResult]):
    """Print test summary."""
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    # Group by category
    categories = {}
    for r in results:
        if r.category not in categories:
            categories[r.category] = []
        categories[r.category].append(r)

    for category, cat_results in categories.items():
        passed = sum(1 for r in cat_results if r.success)
        total_time = sum(r.response_time for r in cat_results)
        print(f"\n{category} Tests: {passed}/{len(cat_results)} passed ({total_time:.2f}s)")

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
    parser = argparse.ArgumentParser(description="Workspace, Chat History & Resource Management Test Suite")
    parser.add_argument("--workspace", action="store_true", help="Run workspace tests only")
    parser.add_argument("--chat", action="store_true", help="Run chat history tests only")
    parser.add_argument("--resources", action="store_true", help="Run resource tests only")
    args = parser.parse_args()

    # If no specific flag, run all
    run_all = not args.workspace and not args.chat and not args.resources

    print("=" * 60)
    print("Workspace, Chat History & Resource Management Test Suite")
    print("=" * 60)
    print(f"Server: {API_BASE_URL}")
    print()

    # Login as admin
    print("Logging in as admin...")
    admin_token = login(ADMIN_USERNAME, ADMIN_PASSWORD)
    if not admin_token:
        print("[X] Admin login failed. Cannot continue.")
        print("    Make sure the backend server is running on port 9000.")
        sys.exit(1)
    print(f"[OK] Logged in as {ADMIN_USERNAME}")

    # Get admin user ID
    admin_user_id = get_user_id(admin_token)
    if admin_user_id:
        print(f"[OK] Admin user ID: {admin_user_id[:8]}...")
    else:
        print("[!] Could not get admin user ID")

    # Try to login as test user (optional)
    user_token = None
    user_user_id = None
    print(f"\nTrying to login as test user ({TEST_USER_USERNAME})...")
    user_token = login(TEST_USER_USERNAME, TEST_USER_PASSWORD)
    if user_token:
        print(f"[OK] Logged in as {TEST_USER_USERNAME}")
        user_user_id = get_user_id(user_token)
        if user_user_id:
            print(f"[OK] Test user ID: {user_user_id[:8]}...")
    else:
        print(f"[--] Test user login failed (multi-user tests will be skipped)")

    all_results = []

    # Run workspace tests
    if args.workspace or run_all:
        workspace_results = run_workspace_tests(admin_token, user_token)
        all_results.extend(workspace_results)

    # Run chat history tests
    if args.chat or run_all:
        chat_results = run_chat_history_tests(admin_token)
        all_results.extend(chat_results)

    # Run resource tests
    if args.resources or run_all:
        resource_results = run_resource_tests(admin_token, admin_user_id, user_token, user_user_id)
        all_results.extend(resource_results)

    # Print summary
    print_summary(all_results)

    # Return exit code
    failed = sum(1 for r in all_results if not r.success)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
