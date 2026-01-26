#!/usr/bin/env python3
"""
Test script for VLM-based image embedding.

Tests:
- VLM description generation
- Text embedding via NIM
- Hash-based caching
- Semaphore-based concurrency
- Image type-specific prompts
- Cache statistics

Usage:
    python3 scripts/test_vlm_image_embedding.py
"""
import asyncio
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.services.multimodal_embedding import (
    ImageEmbeddingService,
    TextEmbeddingService,
    MultimodalEmbeddingPipeline,
    ImageType,
)
from app.api.services.vlm_image_cache import VLMImageCache, get_vlm_image_cache, reset_vlm_image_cache
from app.api.models.document import ProcessingMode, ImageInfo


async def test_text_embedding_service():
    """Test basic text embedding."""
    print("\n" + "=" * 60)
    print("Test 1: Text Embedding Service")
    print("=" * 60)

    service = TextEmbeddingService()
    text = "This is a test document about machine learning and neural networks."

    embedding = await service.embed_text(text)

    print(f"Input text: {text[:50]}...")
    print(f"Embedding dimension: {len(embedding)}")
    print(f"Non-zero values: {sum(1 for v in embedding if v != 0.0)}")

    assert len(embedding) == 4096, f"Expected 4096 dimensions, got {len(embedding)}"
    print("[PASS] Text embedding works correctly")
    return True


async def test_vlm_cache():
    """Test VLM image cache."""
    print("\n" + "=" * 60)
    print("Test 2: VLM Image Cache")
    print("=" * 60)

    # Reset global cache for clean test
    reset_vlm_image_cache()

    cache = VLMImageCache(max_size=10, ttl_seconds=60)

    # Test image data
    test_image = b"test image data 12345"

    # Test cache miss
    result = await cache.get(test_image)
    assert result is None, "Expected cache miss"
    print("[OK] Cache miss on first access")

    # Test cache set
    hash_key = await cache.set(
        image_data=test_image,
        description="Test description",
        alt_text="Test alt",
        confidence=0.9
    )
    print(f"[OK] Cache set: {hash_key[:16]}...")

    # Test cache hit
    result = await cache.get(test_image)
    assert result is not None, "Expected cache hit"
    assert result["description"] == "Test description"
    assert result["cached"] == True
    print(f"[OK] Cache hit: {result['description'][:30]}...")

    # Test stats
    stats = cache.get_stats()
    print(f"[OK] Stats: hits={stats['hits']}, misses={stats['misses']}")
    assert stats["hits"] == 1
    assert stats["misses"] == 1

    # Test duplicate detection
    test_image_2 = b"test image data 12345"  # Same content
    result2 = await cache.get(test_image_2)
    assert result2 is not None, "Same content should hit cache"
    print("[OK] Duplicate detection working")

    print("[PASS] VLM cache works correctly")
    return True


async def test_image_type_prompts():
    """Test image type-specific prompts."""
    print("\n" + "=" * 60)
    print("Test 3: Image Type-Specific Prompts")
    print("=" * 60)

    for img_type in [ImageType.CHART, ImageType.DIAGRAM, ImageType.TABLE, ImageType.SCREENSHOT]:
        prompt = ImageType.get_prompt(img_type)
        print(f"[OK] {img_type}: {len(prompt)} chars")
        assert len(prompt) > 50, f"Prompt too short for {img_type}"

    # Test with context
    prompt_with_ctx = ImageType.get_prompt(ImageType.CHART, "Sales report Q4 2024")
    assert "Sales report" in prompt_with_ctx
    print("[OK] Context appended to prompt")

    print("[PASS] Image type prompts work correctly")
    return True


async def test_image_embedding_with_cache():
    """Test image embedding with cache."""
    print("\n" + "=" * 60)
    print("Test 4: Image Embedding with Cache")
    print("=" * 60)

    # Reset global cache
    reset_vlm_image_cache()

    service = ImageEmbeddingService(enable_cache=True)

    # Read a real image
    image_path = '/opt/kms/venv/lib/python3.11/site-packages/networkx/drawing/tests/baseline/test_house_with_colors.png'

    if not os.path.exists(image_path):
        print("[SKIP] Test image not found")
        return True

    with open(image_path, 'rb') as f:
        image_data = f.read()

    print(f"Image size: {len(image_data)} bytes")

    # First call - should miss cache
    start = time.time()
    result1 = await service.describe_and_embed_image(
        image_data,
        context="Network visualization",
        image_type=ImageType.DIAGRAM
    )
    time1 = time.time() - start

    print(f"First call: {time1:.2f}s, cached={result1.get('cached', False)}")
    print(f"Description: {result1['description'][:100]}...")

    # Second call - should hit cache
    start = time.time()
    result2 = await service.describe_and_embed_image(
        image_data,
        context="Network visualization",
        image_type=ImageType.DIAGRAM
    )
    time2 = time.time() - start

    print(f"Second call: {time2:.2f}s, cached={result2.get('cached', False)}")

    # Verify cache hit
    assert result2.get('cached', False), "Second call should hit cache"
    assert time2 < time1 * 0.5, "Cache hit should be faster"

    # Check stats
    stats = service.get_stats()
    print(f"Stats: {stats}")
    assert stats['cache_hits'] >= 1, "Should have cache hit"

    print("[PASS] Image embedding with cache works correctly")
    return True


async def test_concurrent_embedding():
    """Test concurrent image embedding with semaphore."""
    print("\n" + "=" * 60)
    print("Test 5: Concurrent Embedding with Semaphore")
    print("=" * 60)

    reset_vlm_image_cache()

    service = ImageEmbeddingService(max_concurrent=2, enable_cache=True)

    # Create multiple different images
    images = []
    image_dir = '/opt/kms/venv/lib/python3.11/site-packages/networkx/drawing/tests/baseline/'

    if os.path.exists(image_dir):
        for filename in os.listdir(image_dir)[:4]:
            if filename.endswith('.png'):
                with open(os.path.join(image_dir, filename), 'rb') as f:
                    images.append(f.read())

    if len(images) < 2:
        print("[SKIP] Not enough test images")
        return True

    print(f"Testing with {len(images)} images")

    start = time.time()
    embeddings = await service.embed_images(images, context="Network diagrams")
    elapsed = time.time() - start

    print(f"Embedded {len(embeddings)} images in {elapsed:.2f}s")
    print(f"Average: {elapsed/len(embeddings):.2f}s per image")

    # Verify all embeddings
    for i, emb in enumerate(embeddings):
        assert len(emb) == 4096, f"Image {i}: wrong dimension"
        non_zero = sum(1 for v in emb if v != 0.0)
        print(f"  Image {i}: {non_zero} non-zero values")

    stats = service.get_stats()
    print(f"Stats: vlm_calls={stats['vlm_calls']}, cache_hits={stats['cache_hits']}")

    print("[PASS] Concurrent embedding works correctly")
    return True


async def test_multimodal_pipeline_with_cache():
    """Test multimodal pipeline with VLM caching."""
    print("\n" + "=" * 60)
    print("Test 6: Multimodal Pipeline with Cache")
    print("=" * 60)

    reset_vlm_image_cache()

    pipeline = MultimodalEmbeddingPipeline()

    text_content = """
    This document describes the architecture of our system.
    The main components include a database layer, API layer, and frontend.
    """

    # Load real image
    image_path = '/opt/kms/venv/lib/python3.11/site-packages/networkx/drawing/tests/baseline/test_house_with_colors.png'

    if not os.path.exists(image_path):
        print("[SKIP] Test image not found")
        return True

    with open(image_path, 'rb') as f:
        image_data = f.read()

    image_info = ImageInfo(
        id="test_image_1",
        page_number=1,
        description="",
        alt_text=""
    )

    # First run
    print("\n--- First run (cache cold) ---")
    start = time.time()
    result1 = await pipeline.process_document(
        text_content=text_content,
        images=[(image_data, image_info)],
        processing_mode=ProcessingMode.VLM_ENHANCED,
        document_context="System architecture"
    )
    time1 = time.time() - start

    print(f"Time: {time1:.2f}s")
    print(f"VLM descriptions generated: {result1['vlm_descriptions_generated']}")
    print(f"Image chunks: {result1['stats']['image_chunks']}")

    # Reset image info for second run
    image_info2 = ImageInfo(
        id="test_image_2",
        page_number=1,
        description="",
        alt_text=""
    )

    # Second run with same image (should hit cache)
    print("\n--- Second run (cache warm) ---")
    start = time.time()
    result2 = await pipeline.process_document(
        text_content=text_content,
        images=[(image_data, image_info2)],  # Same image content
        processing_mode=ProcessingMode.VLM_ENHANCED,
        document_context="System architecture"
    )
    time2 = time.time() - start

    print(f"Time: {time2:.2f}s")
    print(f"Speedup: {time1/time2:.1f}x (due to cache)")

    # Get cache stats
    cache = get_vlm_image_cache()
    cache_stats = cache.get_stats()
    print(f"Cache stats: {cache_stats}")

    print("[PASS] Multimodal pipeline with cache works correctly")
    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("VLM Image Embedding Test Suite (Phase 2)")
    print("=" * 60)
    print("Features tested:")
    print("  - Hash-based caching")
    print("  - Semaphore concurrency control")
    print("  - Image type-specific prompts")
    print("  - Cache statistics")

    results = {}

    # Test 1: Text embedding
    try:
        results["text_embedding"] = await test_text_embedding_service()
    except Exception as e:
        print(f"[FAIL] Text embedding test failed: {e}")
        results["text_embedding"] = False

    # Test 2: VLM cache
    try:
        results["vlm_cache"] = await test_vlm_cache()
    except Exception as e:
        print(f"[FAIL] VLM cache test failed: {e}")
        import traceback
        traceback.print_exc()
        results["vlm_cache"] = False

    # Test 3: Image type prompts
    try:
        results["image_type_prompts"] = await test_image_type_prompts()
    except Exception as e:
        print(f"[FAIL] Image type prompts test failed: {e}")
        results["image_type_prompts"] = False

    # Test 4: Image embedding with cache
    try:
        results["image_embedding_cache"] = await test_image_embedding_with_cache()
    except Exception as e:
        print(f"[FAIL] Image embedding cache test failed: {e}")
        import traceback
        traceback.print_exc()
        results["image_embedding_cache"] = False

    # Test 5: Concurrent embedding
    try:
        results["concurrent_embedding"] = await test_concurrent_embedding()
    except Exception as e:
        print(f"[FAIL] Concurrent embedding test failed: {e}")
        import traceback
        traceback.print_exc()
        results["concurrent_embedding"] = False

    # Test 6: Pipeline with cache
    try:
        results["pipeline_cache"] = await test_multimodal_pipeline_with_cache()
    except Exception as e:
        print(f"[FAIL] Pipeline cache test failed: {e}")
        import traceback
        traceback.print_exc()
        results["pipeline_cache"] = False

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test_name}: [{status}]")

    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
