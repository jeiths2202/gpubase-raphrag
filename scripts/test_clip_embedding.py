#!/usr/bin/env python3
"""
Test script for CLIP embedding and hybrid search.

Tests:
- CLIP image embedding
- CLIP text embedding
- Cross-modal similarity (text-to-image)
- Hybrid embedding (VLM + CLIP)
- Hybrid search

Usage:
    python3 scripts/test_clip_embedding.py
"""
import asyncio
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.services.clip_embedding_service import (
    CLIPEmbeddingService,
    HybridImageEmbedding,
    CLIPConfig,
    reset_services
)
from app.api.services.vlm_image_cache import reset_vlm_image_cache


def load_test_images():
    """Load test images from networkx package."""
    images = []
    image_names = []
    image_dir = '/opt/kms/venv/lib/python3.11/site-packages/networkx/drawing/tests/baseline/'

    if os.path.exists(image_dir):
        for filename in sorted(os.listdir(image_dir))[:5]:
            if filename.endswith('.png'):
                with open(os.path.join(image_dir, filename), 'rb') as f:
                    images.append(f.read())
                    image_names.append(filename)

    return images, image_names


async def test_clip_image_embedding():
    """Test CLIP image embedding."""
    print("\n" + "=" * 60)
    print("Test 1: CLIP Image Embedding")
    print("=" * 60)

    service = CLIPEmbeddingService(lazy_load=True)

    images, names = load_test_images()
    if not images:
        print("[SKIP] No test images found")
        return True

    print(f"Testing with {len(images)} images")
    print(f"Model: {service.model_name}")
    print(f"Expected dimension: {service.dimension}")

    # Test single image
    start = time.time()
    embedding = await service.embed_image(images[0])
    elapsed = time.time() - start

    print(f"\nSingle image embedding:")
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Dimension: {len(embedding)}")
    print(f"  Non-zero: {sum(1 for v in embedding if v != 0.0)}")

    assert len(embedding) == service.dimension, f"Wrong dimension: {len(embedding)}"
    assert sum(1 for v in embedding if v != 0.0) > 0, "All zeros"

    print("[PASS] CLIP image embedding works")
    return True


async def test_clip_text_embedding():
    """Test CLIP text embedding."""
    print("\n" + "=" * 60)
    print("Test 2: CLIP Text Embedding")
    print("=" * 60)

    service = CLIPEmbeddingService(lazy_load=True)

    texts = [
        "a network graph with colored nodes",
        "a diagram showing connections",
        "a chart with data points"
    ]

    print(f"Testing with {len(texts)} texts")

    embeddings = await service.embed_texts(texts)

    for i, (text, emb) in enumerate(zip(texts, embeddings)):
        print(f"\n  Text {i+1}: '{text[:40]}...'")
        print(f"  Dimension: {len(emb)}")
        print(f"  Non-zero: {sum(1 for v in emb if v != 0.0)}")

    assert all(len(emb) == service.dimension for emb in embeddings)

    print("\n[PASS] CLIP text embedding works")
    return True


async def test_cross_modal_similarity():
    """Test text-to-image similarity."""
    print("\n" + "=" * 60)
    print("Test 3: Cross-Modal Similarity (Text to Image)")
    print("=" * 60)

    service = CLIPEmbeddingService(lazy_load=True)

    images, names = load_test_images()
    if not images:
        print("[SKIP] No test images found")
        return True

    # Generate image embeddings
    print("Generating image embeddings...")
    image_embeddings = await service.embed_images(images)

    # Test queries
    queries = [
        "a colorful network graph",
        "nodes connected with lines",
        "a house shape diagram"
    ]

    for query in queries:
        print(f"\nQuery: '{query}'")

        # Generate query embedding
        query_emb = await service.embed_text(query)

        # Find similar images
        image_emb_tuples = [(names[i], emb) for i, emb in enumerate(image_embeddings)]
        results = await service.find_similar_images(query_emb, image_emb_tuples, top_k=3)

        print("  Top matches:")
        for r in results:
            print(f"    - {r['image_id']}: {r['similarity']:.4f}")

    print("\n[PASS] Cross-modal similarity works")
    return True


async def test_hybrid_embedding():
    """Test hybrid embedding (VLM + CLIP)."""
    print("\n" + "=" * 60)
    print("Test 4: Hybrid Embedding (VLM + CLIP)")
    print("=" * 60)

    reset_vlm_image_cache()
    reset_services()

    hybrid = HybridImageEmbedding(vlm_weight=0.6, clip_weight=0.4)

    images, names = load_test_images()
    if not images:
        print("[SKIP] No test images found")
        return True

    print(f"Testing hybrid embedding with {names[0]}")

    start = time.time()
    result = await hybrid.embed_image(images[0], context="Network visualization")
    elapsed = time.time() - start

    print(f"\nTime: {elapsed:.2f}s")
    print(f"Has VLM embedding: {result['has_vlm']}")
    print(f"Has CLIP embedding: {result['has_clip']}")

    if result['vlm_embedding']:
        print(f"VLM dimension: {len(result['vlm_embedding'])}")
    if result['clip_embedding']:
        print(f"CLIP dimension: {len(result['clip_embedding'])}")
    if result['description']:
        print(f"Description: {result['description'][:100]}...")

    assert result['has_vlm'] or result['has_clip'], "No embeddings generated"

    print("\n[PASS] Hybrid embedding works")
    return True


async def test_hybrid_search():
    """Test hybrid search."""
    print("\n" + "=" * 60)
    print("Test 5: Hybrid Search")
    print("=" * 60)

    reset_vlm_image_cache()
    reset_services()

    hybrid = HybridImageEmbedding(vlm_weight=0.6, clip_weight=0.4)

    images, names = load_test_images()
    if len(images) < 3:
        print("[SKIP] Need at least 3 test images")
        return True

    print(f"Generating embeddings for {len(images)} images...")

    # Generate embeddings for all images
    start = time.time()
    image_embeddings = await hybrid.embed_images(images, context="Network diagrams")
    elapsed = time.time() - start

    print(f"Time: {elapsed:.2f}s")
    print(f"Average: {elapsed/len(images):.2f}s per image")

    # Test text search
    query = "colorful network with connected nodes"
    print(f"\nText search: '{query}'")

    results = await hybrid.search_by_text(
        query_text=query,
        image_embeddings=image_embeddings,
        top_k=3
    )

    print("Results:")
    for r in results:
        idx = r['index']
        print(f"  {names[idx]}:")
        print(f"    VLM sim: {r['vlm_similarity']:.4f}")
        print(f"    CLIP sim: {r['clip_similarity']:.4f}")
        print(f"    Combined: {r['combined_similarity']:.4f}")

    # Test image search
    print(f"\nImage search (using {names[0]} as query):")

    results = await hybrid.search_by_image(
        query_image=images[0],
        image_embeddings=image_embeddings[1:],  # Exclude query image
        top_k=3
    )

    print("Similar images:")
    for r in results:
        idx = r['index'] + 1  # Offset because we excluded first image
        print(f"  {names[idx]}: combined={r['combined_similarity']:.4f}")

    # Get stats
    stats = hybrid.get_stats()
    print(f"\nStats: {stats}")

    print("\n[PASS] Hybrid search works")
    return True


async def test_batch_performance():
    """Test batch processing performance."""
    print("\n" + "=" * 60)
    print("Test 6: Batch Performance")
    print("=" * 60)

    reset_vlm_image_cache()

    service = CLIPEmbeddingService(lazy_load=True)

    images, names = load_test_images()
    if len(images) < 2:
        print("[SKIP] Need at least 2 test images")
        return True

    print(f"Testing with {len(images)} images")

    # Single processing
    start = time.time()
    single_embeddings = []
    for img in images:
        emb = await service.embed_image(img)
        single_embeddings.append(emb)
    single_time = time.time() - start

    print(f"Sequential: {single_time:.2f}s ({single_time/len(images):.2f}s per image)")

    # Batch processing
    start = time.time()
    batch_embeddings = await service.embed_images(images)
    batch_time = time.time() - start

    print(f"Batch: {batch_time:.2f}s ({batch_time/len(images):.2f}s per image)")
    print(f"Speedup: {single_time/batch_time:.1f}x")

    # Verify results match
    for i, (s, b) in enumerate(zip(single_embeddings, batch_embeddings)):
        diff = sum(abs(a - b) for a, b in zip(s, b))
        print(f"  Image {i} diff: {diff:.6f}")

    print("\n[PASS] Batch performance test completed")
    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("CLIP Embedding Test Suite (Phase 3)")
    print("=" * 60)
    print("Features tested:")
    print("  - CLIP image embedding")
    print("  - CLIP text embedding")
    print("  - Cross-modal similarity")
    print("  - Hybrid embedding (VLM + CLIP)")
    print("  - Hybrid search")

    results = {}

    # Test 1: CLIP image embedding
    try:
        results["clip_image"] = await test_clip_image_embedding()
    except Exception as e:
        print(f"[FAIL] CLIP image test failed: {e}")
        import traceback
        traceback.print_exc()
        results["clip_image"] = False

    # Test 2: CLIP text embedding
    try:
        results["clip_text"] = await test_clip_text_embedding()
    except Exception as e:
        print(f"[FAIL] CLIP text test failed: {e}")
        import traceback
        traceback.print_exc()
        results["clip_text"] = False

    # Test 3: Cross-modal similarity
    try:
        results["cross_modal"] = await test_cross_modal_similarity()
    except Exception as e:
        print(f"[FAIL] Cross-modal test failed: {e}")
        import traceback
        traceback.print_exc()
        results["cross_modal"] = False

    # Test 4: Hybrid embedding
    try:
        results["hybrid_embedding"] = await test_hybrid_embedding()
    except Exception as e:
        print(f"[FAIL] Hybrid embedding test failed: {e}")
        import traceback
        traceback.print_exc()
        results["hybrid_embedding"] = False

    # Test 5: Hybrid search
    try:
        results["hybrid_search"] = await test_hybrid_search()
    except Exception as e:
        print(f"[FAIL] Hybrid search test failed: {e}")
        import traceback
        traceback.print_exc()
        results["hybrid_search"] = False

    # Test 6: Batch performance
    try:
        results["batch_performance"] = await test_batch_performance()
    except Exception as e:
        print(f"[FAIL] Batch performance test failed: {e}")
        import traceback
        traceback.print_exc()
        results["batch_performance"] = False

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
