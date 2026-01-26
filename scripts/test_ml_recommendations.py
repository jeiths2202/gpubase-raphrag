#!/usr/bin/env python3
"""
Test ML-based entity recommendations for ambiguous terms.

Usage:
    python scripts/test_ml_recommendations.py "JEUS WAS에서 MFS 설정하는 방법"
    python scripts/test_ml_recommendations.py "메인프레임 마이그레이션 중 MFS 에러"
"""
import asyncio
import json
import logging
import math
import os
import sys
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)


async def get_query_embedding(client: httpx.AsyncClient, query: str, base_url: str, model: str) -> list[float]:
    """Generate embedding for query using NV-EmbedQA API."""
    response = await client.post(
        f"{base_url}/embeddings",
        json={
            "input": query,
            "model": model,
            "input_type": "query",  # Use 'query' type for search queries
        },
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["data"][0]["embedding"]


async def test_recommendations(query: str):
    """Test ML recommendations for a query."""
    import asyncpg

    # Database connection
    pool = await asyncpg.create_pool(
        host=os.getenv('POSTGRES_HOST', 'postgres-kms'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        database=os.getenv('POSTGRES_DB', 'ragdb'),
        user=os.getenv('POSTGRES_USER', 'raguser'),
        password=os.getenv('POSTGRES_PASSWORD', 'ragpassword123'),
    )

    # Embedding service
    embedding_base_url = os.getenv('EMBEDDING_API_URL', 'http://nemo-embedding-graphrag:8000/v1')
    embedding_model = os.getenv('EMBEDDING_MODEL', 'nvidia/nv-embedqa-mistral-7b-v2')

    print("=" * 70)
    print(f"Query: {query}")
    print("=" * 70)

    # Find matching terms in query
    query_lower = query.lower()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, term, term_normalized, possible_entities, entity_embeddings
            FROM ambiguous_terms
            WHERE is_active = TRUE AND entity_embeddings IS NOT NULL
            ORDER BY priority DESC
        """)

    # Check which terms match
    matching_terms = []
    for row in rows:
        term_normalized = row['term_normalized']
        if term_normalized in query_lower.split():
            matching_terms.append(row)

    if not matching_terms:
        print("\nNo ambiguous terms detected in query.")
        await pool.close()
        return

    print(f"\nDetected {len(matching_terms)} ambiguous term(s)")

    async with httpx.AsyncClient() as client:
        # Generate query embedding
        print(f"\nGenerating query embedding...")
        query_embedding = await get_query_embedding(client, query, embedding_base_url, embedding_model)
        print(f"Query embedding: {len(query_embedding)} dimensions")

        # Process each matching term
        for row in matching_terms:
            term = row['term']
            possible_entities = row['possible_entities']
            entity_embeddings = row['entity_embeddings']

            if isinstance(possible_entities, str):
                possible_entities = json.loads(possible_entities)
            if isinstance(entity_embeddings, str):
                entity_embeddings = json.loads(entity_embeddings)

            print(f"\n{'─' * 70}")
            print(f"Term: {term}")
            print(f"{'─' * 70}")

            # Calculate similarity for each entity
            similarities = []
            for entity in possible_entities:
                entity_id = entity['id']
                entity_name = entity['name']
                entity_desc = entity['description']

                if entity_id in entity_embeddings:
                    entity_emb = entity_embeddings[entity_id]
                    similarity = cosine_similarity(query_embedding, entity_emb)
                    # Convert to confidence (0.5-1.0 → 0-100%)
                    confidence = max(0.0, min(1.0, (similarity - 0.5) * 2)) * 100

                    similarities.append({
                        'entity_id': entity_id,
                        'entity_name': entity_name,
                        'description': entity_desc,
                        'similarity': similarity,
                        'confidence': confidence,
                    })

            # Sort by similarity
            similarities.sort(key=lambda x: x['similarity'], reverse=True)

            # Display results
            print(f"\nPossible interpretations (ranked by ML similarity):\n")
            for i, sim in enumerate(similarities):
                marker = "★ RECOMMENDED" if i == 0 else ""
                print(f"  {i+1}. {sim['entity_name']}")
                print(f"     Description: {sim['description']}")
                print(f"     Similarity: {sim['similarity']:.4f}")
                print(f"     Confidence: {sim['confidence']:.1f}% {marker}")
                print()

    await pool.close()
    print("=" * 70)


async def run_test_cases():
    """Run predefined test cases."""
    test_queries = [
        # Should recommend JEUS MFS (WAS context)
        "JEUS WAS에서 MFS 설정하는 방법",

        # Should recommend OpenFrame MFS (mainframe context)
        "메인프레임 마이그레이션 중 MFS 에러",

        # Should recommend Tmax MFS (distributed file context)
        "Tmax 분산 환경에서 MFS 파일 동기화",

        # Should recommend JEUS WebAdmin
        "WAS 관리 콘솔 WebAdmin 접속 오류",

        # Should recommend Tibero WebAdmin
        "데이터베이스 SQL 쿼리 WebAdmin 사용법",

        # Should recommend Tmax TP
        "트랜잭션 처리 모니터 TP 설정",

        # Should recommend JEUS Manager
        "도메인 관리 서버 Manager 시작 방법",
    ]

    for query in test_queries:
        await test_recommendations(query)
        print("\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Test specific query
        query = " ".join(sys.argv[1:])
        asyncio.run(test_recommendations(query))
    else:
        # Run all test cases
        asyncio.run(run_test_cases())
