#!/usr/bin/env python3
"""
Generate CLIP embeddings for images in the database.

This script:
1. Loads images that don't have CLIP embeddings
2. Generates CLIP embeddings using sentence-transformers
3. Stores embeddings back to database
"""
import asyncio
import asyncpg
import os
import sys
from typing import List, Dict, Any

# Load environment variables from .env file
def load_env():
    env_path = "/opt/kms/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    if ' #' in line:
                        line = line.split(' #')[0].strip()
                    key, value = line.split('=', 1)
                    os.environ[key] = value

load_env()


class SimpleCLIPService:
    """Simplified CLIP service for batch embedding generation."""

    def __init__(self, model_name: str = "clip-ViT-B-32"):
        self.model_name = model_name
        self.model = None
        self.dimension = 512

    def load_model(self):
        """Load CLIP model."""
        if self.model is not None:
            return

        from sentence_transformers import SentenceTransformer
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading CLIP model {self.model_name} on {device}...")
        self.model = SentenceTransformer(self.model_name, device=device)
        print("Model loaded!")

    def embed_image(self, image_data: bytes) -> List[float]:
        """Generate CLIP embedding for an image."""
        from PIL import Image
        import io

        self.load_model()

        # Load image
        image = Image.open(io.BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Resize if too large
        max_size = 1024
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        # Generate embedding
        embedding = self.model.encode(
            image,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        return embedding.tolist()

    def embed_images(self, images: List[bytes], batch_size: int = 8) -> List[List[float]]:
        """Generate CLIP embeddings for multiple images."""
        from PIL import Image
        import io

        self.load_model()

        # Preprocess images
        pil_images = []
        for img_data in images:
            try:
                image = Image.open(io.BytesIO(img_data))
                if image.mode != "RGB":
                    image = image.convert("RGB")

                max_size = 1024
                if max(image.size) > max_size:
                    ratio = max_size / max(image.size)
                    new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                    image = image.resize(new_size, Image.Resampling.LANCZOS)

                pil_images.append(image)
            except Exception as e:
                print(f"Warning: Failed to process image: {e}")
                pil_images.append(None)

        # Generate embeddings
        embeddings = []
        for i in range(0, len(pil_images), batch_size):
            batch = pil_images[i:i + batch_size]
            valid_batch = [img for img in batch if img is not None]
            valid_indices = [j for j, img in enumerate(batch) if img is not None]

            if valid_batch:
                batch_embeddings = self.model.encode(
                    valid_batch,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    batch_size=batch_size
                )

                # Reconstruct results
                batch_results = [[0.0] * self.dimension] * len(batch)
                for idx, emb in zip(valid_indices, batch_embeddings):
                    batch_results[idx] = emb.tolist()

                embeddings.extend(batch_results)
            else:
                embeddings.extend([[0.0] * self.dimension] * len(batch))

        return embeddings


async def get_images_without_embedding(pool, limit: int = 100) -> List[Dict[str, Any]]:
    """Get images that need embeddings."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT image_id, document_id, page_number, image_data, mime_type
            FROM image_embeddings
            WHERE clip_embedding IS NULL
            ORDER BY created_at
            LIMIT $1
        """, limit)
        return [dict(row) for row in rows]


async def update_clip_embedding(pool, image_id: str, embedding: List[float]) -> bool:
    """Update CLIP embedding for an image."""
    from datetime import datetime, timezone

    async with pool.acquire() as conn:
        embedding_str = f"[{','.join(str(v) for v in embedding)}]"
        result = await conn.execute("""
            UPDATE image_embeddings
            SET clip_embedding = $2::vector,
                updated_at = $3
            WHERE image_id = $1
        """, image_id, embedding_str, datetime.now(timezone.utc))
        return result == "UPDATE 1"


async def main():
    print("=" * 60)
    print("CLIP Embedding Generator")
    print("=" * 60)

    # Connect to database
    print("\nConnecting to database...")
    pool = await asyncpg.create_pool(
        host=os.environ.get('POSTGRES_HOST', 'localhost'),
        port=int(os.environ.get('POSTGRES_PORT', 5432)),
        user=os.environ.get('POSTGRES_USER', 'postgres'),
        password=os.environ.get('POSTGRES_PASSWORD', 'postgres'),
        database=os.environ.get('POSTGRES_DB', 'kms'),
        min_size=1,
        max_size=5
    )

    # Get images without embeddings
    print("Fetching images without CLIP embeddings...")
    images = await get_images_without_embedding(pool, limit=100)

    if not images:
        print("No images need embedding generation.")
        await pool.close()
        return

    print(f"Found {len(images)} images to process")

    # Initialize CLIP service
    clip = SimpleCLIPService()

    # Process images
    success_count = 0
    error_count = 0

    for i, img in enumerate(images):
        image_id = img['image_id']
        print(f"\n[{i+1}/{len(images)}] Processing {image_id}...", end=" ")

        try:
            # Get image data (handle memoryview)
            image_data = img['image_data']
            if isinstance(image_data, memoryview):
                image_data = bytes(image_data)

            # Generate embedding
            embedding = clip.embed_image(image_data)

            # Check if embedding is valid (not all zeros)
            if sum(1 for v in embedding if v != 0.0) == 0:
                print("SKIP (invalid embedding)")
                error_count += 1
                continue

            # Update database
            updated = await update_clip_embedding(pool, image_id, embedding)

            if updated:
                print(f"OK (dim={len(embedding)})")
                success_count += 1
            else:
                print("FAIL (db update)")
                error_count += 1

        except Exception as e:
            print(f"ERROR: {e}")
            error_count += 1

    # Summary
    print("\n" + "=" * 60)
    print(f"Completed: {success_count} success, {error_count} errors")
    print("=" * 60)

    # Verify
    async with pool.acquire() as conn:
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM image_embeddings WHERE clip_embedding IS NOT NULL
        """)
        print(f"\nTotal images with CLIP embeddings: {count}")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
