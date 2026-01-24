#!/usr/bin/env python3
"""
Generate entity embeddings for all active ambiguous terms.

This script generates embedding vectors for each possible entity
of ambiguous terms, enabling ML-based recommendations.

Usage:
    python scripts/generate_term_embeddings.py
"""
import asyncio
import json
import logging
import os
import sys
import httpx

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def generate_embedding(client: httpx.AsyncClient, text: str, base_url: str, model: str) -> list[float]:
    """Generate embedding for text using NV-EmbedQA API."""
    response = await client.post(
        f"{base_url}/embeddings",
        json={
            "input": text,
            "model": model,
            "input_type": "passage",  # Required for NV-EmbedQA
        },
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["data"][0]["embedding"]


async def main():
    """Generate embeddings for all active ambiguous terms."""
    import asyncpg

    # Get database connection
    pool = await asyncpg.create_pool(
        host=os.getenv('POSTGRES_HOST', 'postgres-kms'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        database=os.getenv('POSTGRES_DB', 'ragdb'),
        user=os.getenv('POSTGRES_USER', 'raguser'),
        password=os.getenv('POSTGRES_PASSWORD', 'ragpassword123'),
    )

    logger.info("Connected to PostgreSQL")

    # Embedding service configuration
    embedding_base_url = os.getenv('EMBEDDING_API_URL', 'http://nemo-embedding-graphrag:8000/v1')
    embedding_model = os.getenv('EMBEDDING_MODEL', 'nvidia/nv-embedqa-mistral-7b-v2')

    logger.info(f"Using embedding service: {embedding_base_url}")
    logger.info(f"Model: {embedding_model}")

    # Get all active terms
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, term, term_normalized, possible_entities, entity_embeddings
            FROM ambiguous_terms
            WHERE is_active = TRUE
            ORDER BY id
        """)

    logger.info(f"Found {len(rows)} active ambiguous terms")

    processed = 0
    failed = 0
    skipped = 0

    async with httpx.AsyncClient() as client:
        for row in rows:
            term_id = row['id']
            term = row['term']
            possible_entities = row['possible_entities']
            existing_embeddings = row['entity_embeddings']

            # Parse JSON if needed
            if isinstance(possible_entities, str):
                possible_entities = json.loads(possible_entities)

            if not possible_entities:
                logger.warning(f"Term {term_id} ({term}) has no possible entities, skipping")
                skipped += 1
                continue

            # Skip if embeddings already exist
            if existing_embeddings:
                logger.info(f"Term {term_id} ({term}) already has embeddings, skipping")
                skipped += 1
                continue

            logger.info(f"Generating embeddings for term {term_id} ({term}) with {len(possible_entities)} entities...")

            try:
                entity_embeddings = {}

                for entity in possible_entities:
                    entity_id = entity.get('id', '')
                    entity_name = entity.get('name', '')
                    entity_desc = entity.get('description', '')
                    keywords = entity.get('keywords', [])

                    # Create rich text for embedding
                    keywords_str = ", ".join(keywords) if keywords else ""
                    text = f"{entity_name}. {entity_desc}"
                    if keywords_str:
                        text += f" Keywords: {keywords_str}"

                    # Generate embedding
                    embedding = await generate_embedding(client, text, embedding_base_url, embedding_model)
                    entity_embeddings[entity_id] = embedding

                    logger.info(f"  Generated embedding for entity: {entity_id} ({len(embedding)} dims)")

                # Save to database
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE ambiguous_terms
                        SET entity_embeddings = $2::jsonb, updated_at = NOW()
                        WHERE id = $1
                    """, term_id, json.dumps(entity_embeddings))

                logger.info(f"  Saved {len(entity_embeddings)} entity embeddings for term {term_id}")
                processed += 1

            except Exception as e:
                logger.error(f"Failed to generate embeddings for term {term_id} ({term}): {e}")
                failed += 1

    await pool.close()

    logger.info("=" * 50)
    logger.info(f"Embedding generation complete:")
    logger.info(f"  Processed: {processed}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Skipped: {skipped}")
    logger.info("=" * 50)

    return processed, failed, skipped


if __name__ == "__main__":
    asyncio.run(main())
