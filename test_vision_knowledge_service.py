"""
Test Vision Knowledge Service

Tests the new VisionKnowledgeService that combines:
1. Summary search (keyword extraction)
2. PDF page resolution
3. MiniCPM-V image analysis
"""

import asyncio
import json
import logging
import sys
import io
from pathlib import Path

# Fix Windows console encoding for CJK characters
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Enable debug logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(name)s - %(message)s'
)
# Enable debug for vision knowledge service
logging.getLogger("app.api.services.vision_knowledge_service").setLevel(logging.DEBUG)

# Add project root to path
sys.path.insert(0, ".")


async def test_pdf_path_resolution():
    """Test PDF path resolution from keywords"""
    print("\n" + "=" * 60)
    print("[Test 1] PDF Path Resolution")
    print("=" * 60)

    from app.api.services.vision_knowledge_service import VisionKnowledgeService

    service = VisionKnowledgeService()

    # Test resolving PDF paths
    test_keywords = [
        "Utility-Reference-Guide",
        "Error-Reference-Guide",
        "TJES-Guide",
        "Base-Guide",
        "HiDB-Guide",
    ]

    for keyword in test_keywords:
        pdf_path = await service._resolve_pdf_path(keyword)
        if pdf_path:
            print(f"  {keyword} -> {pdf_path.name}")
        else:
            print(f"  {keyword} -> NOT FOUND")

    print("\n[OK] PDF path resolution test completed")


async def test_summary_search():
    """Test summary search integration"""
    print("\n" + "=" * 60)
    print("[Test 2] Summary Search Integration")
    print("=" * 60)

    from app.api.services.summary_search_service import get_summary_search_service

    service = get_summary_search_service()

    test_queries = [
        "IDCAMSのALTERコマンドで変更できる属性は?",
        "tjesmgr BOOT",
        "-5212 에러",
    ]

    for query in test_queries:
        print(f"\n  Query: {query[:50]}...")
        result = await service.comprehensive_search(query)

        print(f"  Results: {result.get('total_results', 0)}")
        print(f"  Confidence: {result.get('confidence', 'unknown')}")

        for r in result.get("results", [])[:2]:
            print(f"    - [{r.get('type')}] {r.get('command') or r.get('name') or r.get('term', '')}")

    print("\n[OK] Summary search test completed")


async def test_page_image_rendering():
    """Test PDF page rendering"""
    print("\n" + "=" * 60)
    print("[Test 3] PDF Page Rendering")
    print("=" * 60)

    from app.api.services.vision_knowledge_service import VisionKnowledgeService

    service = VisionKnowledgeService()

    # Find a PDF to test
    pdf_path = await service._resolve_pdf_path("Utility-Reference-Guide")

    if not pdf_path:
        print("  [SKIP] No PDF found for testing")
        return

    print(f"  Using PDF: {pdf_path.name}")

    # Render pages 43, 44 (where ALTER command table is)
    pages_to_render = [43, 44]
    images = await service._render_pdf_pages(pdf_path, pages_to_render)

    print(f"  Rendered {len(images)} pages")
    for i, img in enumerate(images):
        print(f"    Page {pages_to_render[i]}: {len(img)/1024:.1f} KB")

    print("\n[OK] Page rendering test completed")


async def test_vision_knowledge_full():
    """Test full Vision Knowledge pipeline"""
    print("\n" + "=" * 60)
    print("[Test 4] Full Vision Knowledge Pipeline")
    print("=" * 60)

    from app.api.services.vision_knowledge_service import get_vision_knowledge_service

    service = get_vision_knowledge_service()

    # Test query that should trigger Vision analysis
    query = "IDCAMSのALTERコマンドで変更できる属性は何ですか?"
    print(f"\n  Query: {query}")

    try:
        result = await service.search_with_vision(
            query=query,
            language="ja",
            max_pages=2,
        )

        print(f"\n  Result Type: {result.get('type')}")

        if result.get("type") == "vision_enriched":
            print(f"  Images Analyzed: {result.get('image_count', 0)}")
            print(f"  Sources: {result.get('sources', [])}")
            print(f"\n  Answer Preview (first 500 chars):")
            answer = result.get("answer", "")
            print(f"  {answer[:500]}...")
        else:
            print(f"  Summary Context: {result.get('summary_context', '')[:200]}...")
            print(f"  Message: {result.get('message', 'N/A')}")

    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()

    print("\n[OK] Full pipeline test completed")


async def test_minicpm_health():
    """Test MiniCPM-V server health"""
    print("\n" + "=" * 60)
    print("[Test 5] MiniCPM-V Health Check")
    print("=" * 60)

    try:
        from app.api.adapters.vision.minicpm_vision_adapter import MiniCPMVisionAdapter

        adapter = MiniCPMVisionAdapter(
            base_url="http://192.168.8.11:12803/v1",
            model="openbmb/MiniCPM-V-2_6",
        )

        is_healthy = await adapter.health_check()
        print(f"  MiniCPM-V Status: {'OK' if is_healthy else 'UNAVAILABLE'}")

        if is_healthy:
            info = adapter.get_model_info()
            print(f"  Model: {info.get('model')}")
            print(f"  Capabilities: {', '.join(info.get('capabilities', []))}")

    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\n[OK] Health check completed")


async def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("Vision Knowledge Service Tests")
    print("=" * 60)

    # Test 1: PDF path resolution
    await test_pdf_path_resolution()

    # Test 2: Summary search
    await test_summary_search()

    # Test 3: Page rendering
    await test_page_image_rendering()

    # Test 4: MiniCPM health
    await test_minicpm_health()

    # Test 5: Full pipeline
    await test_vision_knowledge_full()

    print("\n" + "=" * 60)
    print("[ALL TESTS COMPLETED]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
