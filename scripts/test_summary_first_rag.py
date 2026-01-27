#!/usr/bin/env python3
"""
Test script for Summary-First RAG implementation.

Usage:
    python scripts/test_summary_first_rag.py

This script tests the Summary-First RAG search functionality
by directly calling the service without needing the full API.
"""

import asyncio
import sys
import io
from pathlib import Path

# Handle Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def test_summary_bm25_service():
    """Test the Summary BM25 Service directly"""
    print("=" * 60)
    print("Testing Summary BM25 Service")
    print("=" * 60)

    from app.api.services.summary_bm25_service import SummaryBM25Service

    service = SummaryBM25Service(
        summaries_dir=project_root / "uploads" / "summaries"
    )

    # Initialize
    print("\n1. Initializing BM25 index...")
    success = await service.initialize()
    print(f"   Initialized: {success}")
    print(f"   Documents loaded: {service.document_count}")
    print(f"   Error codes indexed: {len(service._error_code_index)}")
    print(f"   Commands indexed: {len(service._command_index)}")
    print(f"   Terms indexed: {len(service._term_index)}")

    if not success:
        print("   FAILED: Could not initialize service")
        return

    # Test 1: Error code search
    print("\n2. Testing error code search: '-5212'")
    result = await service.search_error_code("-5212")
    if result:
        print(f"   Found: {result.document.name}")
        print(f"   Description: {result.document.description}")
        print(f"   Solution: {result.document.solution}")
        print(f"   Score: {result.score}")
    else:
        print("   Not found")

    # Test 2: Command search
    print("\n3. Testing command search: 'tjesmgr'")
    results = await service.search_command("tjesmgr")
    if results:
        print(f"   Found {len(results)} result(s)")
        for i, r in enumerate(results[:3]):
            print(f"   {i+1}. {r.document.name} ({r.document.product})")
    else:
        print("   Not found")

    # Test 3: Term search
    print("\n4. Testing term search: 'TACF'")
    result = await service.search_term("TACF")
    if result:
        print(f"   Found: {result.document.name}")
        full_name = result.document.metadata.get("full_name", "N/A")
        print(f"   Full name: {full_name}")
    else:
        print("   Not found")

    # Test 4: Comprehensive search
    print("\n5. Testing comprehensive search: 'TJES 에러 -5212'")
    result = await service.comprehensive_search("TJES 에러 -5212")
    print(f"   Confidence: {result.confidence.value}")
    print(f"   Total results: {result.total_results}")
    print(f"   Detected error codes: {result.detected_error_codes}")
    print(f"   Detected terms: {result.detected_terms}")
    print(f"   Categories: {[c.value for c in result.matched_categories]}")

    if result.results:
        print("\n   Top 3 results:")
        for i, r in enumerate(result.results[:3]):
            print(f"   {i+1}. [{r.document.doc_type.value}] {r.document.name} (score: {r.score:.3f})")

    # Test 5: Context string generation
    print("\n6. Testing context string generation:")
    context = result.get_context_string(max_results=2)
    print(f"   Context:\n{context[:500]}...")

    # Test 6: BM25 full-text search
    print("\n7. Testing BM25 full-text search: 'dataset allocation error'")
    results = await service.search("dataset allocation error", top_k=5)
    if results:
        print(f"   Found {len(results)} results")
        for i, r in enumerate(results):
            print(f"   {i+1}. [{r.document.doc_type.value}] {r.document.name} (score: {r.score:.3f})")

    print("\n" + "=" * 60)
    print("Summary-First RAG Service Test Complete")
    print("=" * 60)


async def test_pdf_page_loader():
    """Test the PDF Page Loader Service"""
    print("\n" + "=" * 60)
    print("Testing PDF Page Loader Service")
    print("=" * 60)

    from app.api.services.pdf_page_loader_service import PDFPageLoaderService

    service = PDFPageLoaderService(
        uploads_dir=project_root / "uploads"
    )

    # Find a PDF to test with
    pdf_dir = project_root / "uploads"
    pdfs = list(pdf_dir.rglob("*.pdf"))

    if not pdfs:
        print("No PDF files found in uploads directory")
        return

    test_pdf = pdfs[0]
    print(f"\nUsing test PDF: {test_pdf.name}")

    # Test page loading
    print("\n1. Loading page 1...")
    pages = await service.load_pages(str(test_pdf), [1])
    if pages:
        page = pages[0]
        print(f"   Text length: {len(page.text)} characters")
        print(f"   Word count: {page.word_count}")
        print(f"   Has tables: {page.has_tables}")
        print(f"   Preview: {page.text[:200]}...")
    else:
        print("   Could not load page")

    # Test page with context
    print("\n2. Loading page 5 with context...")
    pages = await service.load_page_with_context(str(test_pdf), 5, context_pages=1)
    print(f"   Loaded {len(pages)} pages (4, 5, 6)")

    print("\n" + "=" * 60)
    print("PDF Page Loader Test Complete")
    print("=" * 60)


async def main():
    """Run all tests"""
    print("\n" + "#" * 60)
    print("# Summary-First RAG Implementation Test Suite")
    print("#" * 60)

    await test_summary_bm25_service()
    await test_pdf_page_loader()

    print("\n" + "#" * 60)
    print("# All tests completed!")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(main())
