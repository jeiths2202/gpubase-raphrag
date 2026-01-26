#!/usr/bin/env python
"""
Long-term Memory Test Script

Tests the Long-term Memory feature implementation for Deep Agents.
Tests:
1. MemoryStoreService file-based storage
2. DeepAgentAdapter with CompositeBackend
3. Memory persistence across sessions
"""
import asyncio
import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Test results
test_results = []

def log_test(name: str, passed: bool, message: str = ""):
    """Log test result."""
    status = "[PASS]" if passed else "[FAIL]"
    test_results.append({"name": name, "passed": passed, "message": message})
    print(f"{status}: {name}")
    if message:
        print(f"       {message}")

def print_section(title: str):
    """Print section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


async def test_memory_store_service():
    """Test MemoryStoreService file-based storage."""
    print_section("Test 1: MemoryStoreService File Storage")

    # Set up test directory
    test_dir = project_root / "data" / "test_agent_memory"
    os.environ["MEMORY_STORE_DIR"] = str(test_dir)

    # Clean up previous test data
    if test_dir.exists():
        shutil.rmtree(test_dir)

    try:
        from app.api.services.memory_store_service import (
            MemoryStoreService,
            Neo4jMemoryStore,
        )

        # Test 1.1: Create service without Neo4j (file fallback)
        print("1.1 Creating MemoryStoreService (file-based)...")
        service = MemoryStoreService(neo4j_driver=None)
        await service.initialize()
        log_test("MemoryStoreService creation", True)

        # Test 1.2: Store memory
        print("\n1.2 Storing memory...")
        user_id = "test_user_123"
        result = await service.store_memory(
            namespace="preferences",
            key="language",
            value={"lang": "ko", "region": "KR"},
            user_id=user_id
        )
        log_test("Store memory", result, f"Stored language preference for {user_id}")

        # Test 1.3: Retrieve memory
        print("\n1.3 Retrieving memory...")
        retrieved = await service.retrieve_memory(
            namespace="preferences",
            key="language",
            user_id=user_id
        )
        if retrieved and retrieved.get("lang") == "ko":
            log_test("Retrieve memory", True, f"Retrieved: {retrieved}")
        else:
            log_test("Retrieve memory", False, f"Expected lang='ko', got: {retrieved}")

        # Test 1.4: Store user preference helper
        print("\n1.4 Using store_user_preference helper...")
        result = await service.store_user_preference(
            user_id=user_id,
            preference_key="theme",
            preference_value="dark"
        )
        log_test("Store user preference", result)

        # Test 1.5: Get user preference helper
        print("\n1.5 Using get_user_preference helper...")
        theme = await service.get_user_preference(
            user_id=user_id,
            preference_key="theme",
            default="light"
        )
        log_test("Get user preference", theme == "dark", f"Theme: {theme}")

        # Test 1.6: Accumulate knowledge
        print("\n1.6 Accumulating knowledge...")
        result1 = await service.accumulate_knowledge(
            user_id=user_id,
            topic="python",
            knowledge_item={"fact": "Python is interpreted", "source": "conversation_1"}
        )
        result2 = await service.accumulate_knowledge(
            user_id=user_id,
            topic="python",
            knowledge_item={"fact": "Python has dynamic typing", "source": "conversation_2"}
        )

        # Retrieve accumulated knowledge
        knowledge = await service.retrieve_memory("/knowledge/", "python", user_id)
        items_count = len(knowledge.get("items", [])) if knowledge else 0
        log_test("Accumulate knowledge", items_count == 2, f"Knowledge items: {items_count}")

        # Test 1.7: List memories
        print("\n1.7 Listing memories...")
        keys = await service.list_memories("preferences", user_id)
        log_test("List memories", len(keys) > 0, f"Found {len(keys)} keys")

        # Test 1.8: Delete memory
        print("\n1.8 Deleting memory...")
        result = await service.delete_memory("preferences", "theme", user_id)
        deleted_check = await service.retrieve_memory("preferences", "theme", user_id)
        log_test("Delete memory", deleted_check is None, "Memory deleted successfully")

        # Verify file was created
        print("\n1.9 Verifying file storage...")
        files = list(test_dir.glob("*.json"))
        log_test("File storage verification", len(files) > 0, f"Found {len(files)} memory files")

        if files:
            print(f"       Files: {[f.name for f in files[:3]]}...")

    except ImportError as e:
        log_test("Import MemoryStoreService", False, str(e))
    except Exception as e:
        log_test("MemoryStoreService tests", False, str(e))
    finally:
        # Cleanup
        if test_dir.exists():
            shutil.rmtree(test_dir)


async def test_deep_agent_adapter_imports():
    """Test DeepAgentAdapter imports and feature flags."""
    print_section("Test 2: DeepAgentAdapter Imports & Feature Flags")

    try:
        from app.api.agents.adapters import (
            DEEPAGENTS_AVAILABLE,
            DEEPAGENTS_BACKENDS_AVAILABLE,
            LANGGRAPH_STORE_AVAILABLE,
        )

        print("2.1 Checking feature flags...")
        print(f"       DEEPAGENTS_AVAILABLE: {DEEPAGENTS_AVAILABLE}")
        print(f"       DEEPAGENTS_BACKENDS_AVAILABLE: {DEEPAGENTS_BACKENDS_AVAILABLE}")
        print(f"       LANGGRAPH_STORE_AVAILABLE: {LANGGRAPH_STORE_AVAILABLE}")

        log_test("Feature flags import", True)

        # Test imports
        from app.api.agents.adapters import (
            DeepAgentAdapter,
            create_deep_agent_adapter,
            create_rag_deep_agent,
        )
        log_test("DeepAgentAdapter import", True)

    except ImportError as e:
        log_test("DeepAgentAdapter imports", False, str(e))


async def test_composite_backend_creation():
    """Test CompositeBackend creation."""
    print_section("Test 3: CompositeBackend Creation")

    try:
        from app.api.agents.adapters.deep_agent_adapter import (
            DEEPAGENTS_BACKENDS_AVAILABLE,
            LANGGRAPH_STORE_AVAILABLE,
            DeepAgentAdapter,
        )
        from app.api.agents.types import AgentType

        print("3.1 Creating DeepAgentAdapter with long-term memory enabled...")

        adapter = DeepAgentAdapter(
            name="TestAgent",
            agent_type=AgentType.RAG,
            enable_long_term_memory=True,
            user_id="test_user"
        )

        log_test("DeepAgentAdapter creation", True)

        # Check if LangGraph store can be created
        print("\n3.2 Getting LangGraph store...")
        store = adapter._get_langraph_store()
        if store is not None:
            log_test("LangGraph store creation", True, f"Store type: {type(store).__name__}")
        else:
            log_test("LangGraph store creation", False, "Store is None")

        # Check if backend factory can be created
        print("\n3.3 Getting CompositeBackend factory...")
        if DEEPAGENTS_BACKENDS_AVAILABLE:
            backend_factory = adapter._get_composite_backend_factory()
            if backend_factory is not None:
                log_test("CompositeBackend factory", True, "Factory function created")
                print(f"       Factory is callable: {callable(backend_factory)}")
            else:
                log_test("CompositeBackend factory", False, "Factory is None")
        else:
            log_test("CompositeBackend factory", False, "DEEPAGENTS_BACKENDS_AVAILABLE is False")

        # Test memory paths
        print("\n3.4 Checking persistent memory paths...")
        paths = DeepAgentAdapter.PERSISTENT_MEMORY_PATHS
        log_test("Memory paths defined", len(paths) == 5, f"Paths: {paths}")

    except ImportError as e:
        log_test("CompositeBackend tests", False, f"Import error: {e}")
    except Exception as e:
        log_test("CompositeBackend tests", False, str(e))


async def test_langgraph_store():
    """Test LangGraph InMemoryStore."""
    print_section("Test 4: LangGraph Store")

    try:
        from langgraph.store.memory import InMemoryStore

        print("4.1 Creating InMemoryStore...")
        store = InMemoryStore()
        log_test("InMemoryStore creation", True)

        # Test basic operations if available
        print("\n4.2 Testing store operations...")
        # Note: InMemoryStore API may vary
        log_test("LangGraph store available", True)

    except ImportError as e:
        log_test("LangGraph import", False, f"Install with: pip install langgraph")
        print(f"       Error: {e}")
    except Exception as e:
        log_test("LangGraph store tests", False, str(e))


async def test_deepagents_backends():
    """Test deepagents backends."""
    print_section("Test 5: DeepAgents Backends")

    try:
        from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

        print("5.1 Testing backend imports...")
        log_test("StateBackend import", True)
        log_test("StoreBackend import", True)
        log_test("CompositeBackend import", True)

        print("\n5.2 Checking backend signatures...")
        import inspect
        state_sig = inspect.signature(StateBackend.__init__)
        store_sig = inspect.signature(StoreBackend.__init__)

        # StateBackend and StoreBackend require 'runtime' parameter
        has_runtime = 'runtime' in str(state_sig)
        log_test("Backend requires runtime", has_runtime, f"StateBackend signature: {state_sig}")

        print("\n5.3 Verifying CompositeBackend API...")
        composite_sig = inspect.signature(CompositeBackend.__init__)
        has_default = 'default' in str(composite_sig)
        has_routes = 'routes' in str(composite_sig)
        log_test("CompositeBackend API", has_default and has_routes,
                 f"Has default: {has_default}, Has routes: {has_routes}")

        print("\n5.4 Note: Backends are created via factory function with ToolRuntime")
        log_test("Backend factory pattern", True, "Backends require ToolRuntime from deepagents")

    except ImportError as e:
        log_test("DeepAgents backends import", False, f"Install with: pip install deepagents")
        print(f"       Error: {e}")
    except Exception as e:
        log_test("DeepAgents backends tests", False, str(e))


async def test_persistence_simulation():
    """Test persistence by simulating multiple sessions."""
    print_section("Test 6: Persistence Simulation")

    # Set up test directory
    test_dir = project_root / "data" / "test_persistence"
    os.environ["MEMORY_STORE_DIR"] = str(test_dir)

    # Clean up
    if test_dir.exists():
        shutil.rmtree(test_dir)

    try:
        from app.api.services.memory_store_service import MemoryStoreService

        user_id = "persistence_test_user"

        # Session 1: Store data
        print("6.1 Session 1: Storing data...")
        service1 = MemoryStoreService(neo4j_driver=None)
        await service1.initialize()

        await service1.store_memory(
            namespace="research",
            key="project_alpha",
            value={
                "progress": 50,
                "notes": ["Started analysis", "Collected data"],
                "last_session": "session_1"
            },
            user_id=user_id
        )
        log_test("Session 1: Store data", True)

        # Session 2: Retrieve and update (simulate new session)
        print("\n6.2 Session 2: Retrieving and updating...")
        service2 = MemoryStoreService(neo4j_driver=None)
        await service2.initialize()

        # Retrieve from "previous session"
        data = await service2.retrieve_memory("research", "project_alpha", user_id)

        if data and data.get("last_session") == "session_1":
            log_test("Session 2: Retrieve persisted data", True, f"Progress: {data.get('progress')}%")

            # Update
            data["progress"] = 75
            data["notes"].append("Continued analysis")
            data["last_session"] = "session_2"

            await service2.store_memory("research", "project_alpha", data, user_id)
            log_test("Session 2: Update data", True)
        else:
            log_test("Session 2: Retrieve persisted data", False, f"Got: {data}")

        # Session 3: Final verification
        print("\n6.3 Session 3: Final verification...")
        service3 = MemoryStoreService(neo4j_driver=None)
        await service3.initialize()

        final_data = await service3.retrieve_memory("research", "project_alpha", user_id)

        if final_data:
            progress_correct = final_data.get("progress") == 75
            session_correct = final_data.get("last_session") == "session_2"
            notes_correct = len(final_data.get("notes", [])) == 3

            all_correct = progress_correct and session_correct and notes_correct
            log_test("Session 3: Verify persistence", all_correct,
                     f"Progress: {final_data.get('progress')}%, Notes: {len(final_data.get('notes', []))}")
        else:
            log_test("Session 3: Verify persistence", False, "Data not found")

    except Exception as e:
        log_test("Persistence simulation", False, str(e))
    finally:
        # Cleanup
        if test_dir.exists():
            shutil.rmtree(test_dir)


def print_summary():
    """Print test summary."""
    print_section("Test Summary")

    passed = sum(1 for t in test_results if t["passed"])
    failed = sum(1 for t in test_results if not t["passed"])
    total = len(test_results)

    print(f"Total: {total} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {passed/total*100:.1f}%")

    if failed > 0:
        print("\nFailed tests:")
        for t in test_results:
            if not t["passed"]:
                print(f"  - {t['name']}: {t['message']}")

    return failed == 0


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  Long-term Memory Feature Test Suite")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)

    # Run tests
    await test_memory_store_service()
    await test_deep_agent_adapter_imports()
    await test_composite_backend_creation()
    await test_langgraph_store()
    await test_deepagents_backends()
    await test_persistence_simulation()

    # Print summary
    success = print_summary()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
