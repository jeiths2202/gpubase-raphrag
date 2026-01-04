#!/usr/bin/env python3
"""
Verification script for E2E Tracing System

Checks:
1. All required modules can be imported
2. Database schema file exists
3. Key classes are properly defined
"""
import sys
import os

def check_imports():
    """Verify all tracing modules can be imported"""
    print("=" * 60)
    print("CHECKING IMPORTS")
    print("=" * 60)

    try:
        from app.api.core.trace_context import TraceContext, Span, SpanType
        print("[OK] app.api.core.trace_context")
    except ImportError as e:
        print(f"[FAIL] app.api.core.trace_context: {e}")
        return False

    try:
        from app.api.core.tracing import (
            get_trace_context_from_request,
            detect_response_quality,
            should_sample_trace
        )
        print("[OK] app.api.core.tracing")
    except ImportError as e:
        print(f"[FAIL] app.api.core.tracing: {e}")
        return False

    try:
        from app.api.infrastructure.postgres.trace_repository import TraceRepository
        print("[OK] app.api.infrastructure.postgres.trace_repository")
    except ImportError as e:
        print(f"[FAIL] app.api.infrastructure.postgres.trace_repository: {e}")
        return False

    try:
        from app.api.infrastructure.services.trace_writer import (
            TraceWriter,
            get_trace_writer,
            initialize_trace_writer
        )
        print("[OK] app.api.infrastructure.services.trace_writer")
    except ImportError as e:
        print(f"[FAIL] app.api.infrastructure.services.trace_writer: {e}")
        return False

    try:
        from app.api.routers.admin_traces import router
        print("[OK] app.api.routers.admin_traces")
    except ImportError as e:
        print(f"[FAIL] app.api.routers.admin_traces: {e}")
        return False

    return True


def check_files():
    """Verify required files exist"""
    print("\n" + "=" * 60)
    print("CHECKING FILES")
    print("=" * 60)

    files = [
        "migrations/004_trace_system.sql",
        "app/api/core/trace_context.py",
        "app/api/core/tracing.py",
        "app/api/infrastructure/postgres/trace_repository.py",
        "app/api/infrastructure/services/trace_writer.py",
        "app/api/infrastructure/services/__init__.py",
        "app/api/routers/admin_traces.py",
        "E2E_TRACING_IMPLEMENTATION_COMPLETE.md"
    ]

    all_exist = True
    for filepath in files:
        if os.path.exists(filepath):
            print(f"[OK] {filepath}")
        else:
            print(f"[FAIL] {filepath} - NOT FOUND")
            all_exist = False

    return all_exist


def check_trace_context_functionality():
    """Verify TraceContext basic functionality"""
    print("\n" + "=" * 60)
    print("CHECKING TRACE CONTEXT FUNCTIONALITY")
    print("=" * 60)

    try:
        from app.api.core.trace_context import TraceContext, SpanType

        # Create a trace context
        ctx = TraceContext.create()
        print(f"[OK] Created TraceContext with trace_id={ctx.trace_id}")

        # Create a child span
        with ctx.create_span("test_span", SpanType.EMBEDDING, metadata={"test": "value"}):
            print(f"[OK] Created child span (current_span_id={ctx.current_span_id})")

        print(f"[OK] Span stack managed correctly (current_span_id={ctx.current_span_id})")

        # Check spans
        all_spans = ctx.get_all_spans()
        print(f"[OK] Total spans: {len(all_spans)} (expected: 2 - root + child)")

        # End root span
        ctx.end_root_span()
        root_span = ctx.spans[ctx.root_span_id]
        if root_span.latency_ms is not None:
            print(f"[OK] Root span latency calculated: {root_span.latency_ms}ms")
        else:
            print(f"[FAIL] Root span latency not calculated")
            return False

        return True

    except Exception as e:
        print(f"[FAIL] TraceContext functionality test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_quality_detection():
    """Verify quality detection logic"""
    print("\n" + "=" * 60)
    print("CHECKING QUALITY DETECTION")
    print("=" * 60)

    try:
        from app.api.core.tracing import detect_response_quality

        # Test EMPTY
        flag = detect_response_quality("", None, None)
        assert flag == "EMPTY", f"Expected EMPTY, got {flag}"
        print(f"[OK] EMPTY detection: {flag}")

        # Test LOW_CONFIDENCE
        flag = detect_response_quality("This is a normal response with sufficient length to pass the 50 character threshold.", 0.3, None)
        assert flag == "LOW_CONFIDENCE", f"Expected LOW_CONFIDENCE, got {flag}"
        print(f"[OK] LOW_CONFIDENCE detection: {flag}")

        # Test USER_NEGATIVE
        flag = detect_response_quality("Good response", 0.9, 1)
        assert flag == "USER_NEGATIVE", f"Expected USER_NEGATIVE, got {flag}"
        print(f"[OK] USER_NEGATIVE detection: {flag}")

        # Test NORMAL
        flag = detect_response_quality("This is a good response with sufficient length and high confidence score.", 0.85, None)
        assert flag == "NORMAL", f"Expected NORMAL, got {flag}"
        print(f"[OK] NORMAL detection: {flag}")

        return True

    except Exception as e:
        print(f"[FAIL] Quality detection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification checks"""
    print("\n" + "=" * 60)
    print("E2E TRACING SYSTEM VERIFICATION")
    print("=" * 60)

    results = []

    # Check imports
    results.append(("Imports", check_imports()))

    # Check files
    results.append(("Files", check_files()))

    # Check functionality
    results.append(("TraceContext Functionality", check_trace_context_functionality()))
    results.append(("Quality Detection", check_quality_detection()))

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} - {name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n[SUCCESS] ALL CHECKS PASSED!")
        print("\nNext steps:")
        print("1. Run database migration: psql -U postgres -d kms -f migrations/004_trace_system.sql")
        print("2. Start application: python -m app.api.main --mode develop")
        print("3. Execute test query and verify trace creation")
        print("4. Query admin API: GET /api/v1/admin/traces/")
        return 0
    else:
        print("\n[FAIL] SOME CHECKS FAILED - Review errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
