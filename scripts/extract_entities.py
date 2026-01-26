#!/usr/bin/env python3
"""
Entity Extraction Script
기존 Chunk에서 Entity 추출 및 MENTIONS 관계 생성

Usage:
    python scripts/extract_entities.py [--limit N]
"""
import os
import re
import sys
import argparse
from typing import List, Dict, Set
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from neo4j import GraphDatabase


# Entity 추출 패턴 (기술 용어, 개념, 키워드)
ENTITY_PATTERNS = {
    "TECHNOLOGY": [
        # Programming/DB
        r'\b(?:Python|Java|JavaScript|TypeScript|Go|Rust|C\+\+|SQL|NoSQL)\b',
        r'\b(?:Neo4j|PostgreSQL|MongoDB|Redis|Elasticsearch|MySQL)\b',
        r'\b(?:React|Vue|Angular|FastAPI|Django|Flask|Spring)\b',
        r'\b(?:Docker|Kubernetes|AWS|Azure|GCP)\b',
        # AI/ML
        r'\b(?:GPT|Claude|LLM|RAG|NLP|ML|AI|Transformer|BERT|Embedding)\b',
        r'\b(?:LangChain|LlamaIndex|Vector|Graph)\b',
    ],
    "CONCEPT": [
        # Korean technical terms
        r'[가-힣]+(?:시스템|프로세스|아키텍처|모델|알고리즘|서비스)',
        r'[가-힣]+(?:검색|분석|처리|생성|추출|학습|최적화)',
        # English concepts
        r'\b(?:API|SDK|CLI|GUI|REST|GraphQL|gRPC)\b',
        r'\b(?:Index|Query|Schema|Node|Edge|Relationship)\b',
    ],
    "TERM": [
        # MFS/IMS specific (based on the screenshot context)
        r'\b(?:DEV|DIV|DPAGE|DFLD|FMT|FMTEND|MSG|MFS)\b',
        r'\b(?:3270|VTAM|IMS|TM|DB|DC)\b',
        # Technical abbreviations
        r'\b[A-Z]{2,6}\b(?=\s|$|[,.])',
    ],
}

# 불용어 (추출에서 제외)
STOPWORDS = {
    'THE', 'AND', 'FOR', 'WITH', 'NOT', 'BUT', 'ALL', 'ARE', 'HAS', 'WAS',
    'WERE', 'BEEN', 'HAVE', 'THIS', 'THAT', 'FROM', 'WILL', 'CAN', 'MAY',
    'GET', 'SET', 'PUT', 'POST', 'DELETE', 'HTTP', 'HTTPS', 'WWW', 'ORG',
    'COM', 'NET', 'JSON', 'XML', 'HTML', 'CSS', 'IF', 'OR', 'IN', 'ON',
    'TO', 'IS', 'IT', 'AS', 'AT', 'BY', 'OF', 'AN', 'BE', 'DO', 'NO',
    'UP', 'SO', 'WE', 'US', 'OK', 'VS', 'ID', 'MY', 'GO',
}


def extract_entities_from_text(text: str) -> Dict[str, Set[str]]:
    """텍스트에서 Entity 추출"""
    entities: Dict[str, Set[str]] = {
        "TECHNOLOGY": set(),
        "CONCEPT": set(),
        "TERM": set(),
    }

    for entity_type, patterns in ENTITY_PATTERNS.items():
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                normalized = match.strip()
                # 불용어 및 짧은 단어 필터링
                if len(normalized) >= 2 and normalized.upper() not in STOPWORDS:
                    entities[entity_type].add(normalized)

    return entities


def extract_entities(limit: int = None):
    """기존 Chunk에서 Entity 추출 및 Neo4j에 저장"""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "graphrag2024")

    print(f"Connecting to Neo4j: {uri}")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session() as session:
            # Chunk 가져오기
            query = "MATCH (c:Chunk) RETURN c.id as id, c.content as content"
            if limit:
                query += f" LIMIT {limit}"

            result = session.run(query)
            chunks = list(result)

            print(f"Processing {len(chunks)} chunks...")

            total_entities = 0
            total_relationships = 0

            for i, chunk in enumerate(chunks):
                chunk_id = chunk["id"]
                content = chunk["content"] or ""

                # Entity 추출
                entities = extract_entities_from_text(content)

                for entity_type, entity_names in entities.items():
                    for entity_name in entity_names:
                        # Entity 생성 또는 병합
                        session.run("""
                            MERGE (e:Entity {name: $name})
                            ON CREATE SET e.type = $type, e.created_at = datetime()
                            ON MATCH SET e.mention_count = coalesce(e.mention_count, 0) + 1
                        """, {"name": entity_name, "type": entity_type})
                        total_entities += 1

                        # MENTIONS 관계 생성
                        session.run("""
                            MATCH (c:Chunk {id: $chunk_id})
                            MATCH (e:Entity {name: $entity_name})
                            MERGE (c)-[:MENTIONS]->(e)
                        """, {"chunk_id": chunk_id, "entity_name": entity_name})
                        total_relationships += 1

                if (i + 1) % 10 == 0:
                    print(f"  Processed {i + 1}/{len(chunks)} chunks...")

            # 결과 요약
            print("\n" + "=" * 50)
            print("Entity Extraction Complete!")
            print("=" * 50)

            # 통계 조회
            result = session.run("""
                MATCH (e:Entity)
                WITH e.type as type, count(e) as count
                RETURN type, count
                ORDER BY count DESC
            """)
            print("\nEntity Statistics by Type:")
            for record in result:
                print(f"  - {record['type']}: {record['count']} entities")

            result = session.run("MATCH ()-[r:MENTIONS]->() RETURN count(r) as count")
            mentions_count = result.single()["count"]
            print(f"\nTotal MENTIONS relationships: {mentions_count}")

            # 샘플 Entity 출력
            print("\nSample Entities:")
            result = session.run("""
                MATCH (e:Entity)<-[r:MENTIONS]-()
                WITH e, count(r) as mentions
                ORDER BY mentions DESC
                LIMIT 10
                RETURN e.name as name, e.type as type, mentions
            """)
            for record in result:
                print(f"  - {record['name']} ({record['type']}): {record['mentions']} mentions")

    finally:
        driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract entities from chunks")
    parser.add_argument("--limit", type=int, help="Limit number of chunks to process")
    args = parser.parse_args()

    extract_entities(limit=args.limit)
