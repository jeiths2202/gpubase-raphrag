#!/usr/bin/env python3
"""
Neo4j Entity Schema Setup Script
Entity 레이블, MENTIONS 관계, 인덱스 생성

Usage:
    python scripts/setup_entity_schema.py
"""
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from neo4j import GraphDatabase


def setup_entity_schema():
    """Neo4j Entity 스키마 구성"""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "graphrag2024")

    print(f"Connecting to Neo4j: {uri}")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session() as session:
            # 1. Entity 레이블 유니크 제약조건 생성
            print("\n[1/5] Creating Entity unique constraint...")
            try:
                session.run(
                    "CREATE CONSTRAINT entity_name IF NOT EXISTS "
                    "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
                )
                print("  ✓ Entity name unique constraint created")
            except Exception as e:
                print(f"  ⚠ Constraint: {e}")

            # 2. Entity 인덱스 생성 (검색 성능)
            print("\n[2/5] Creating Entity indexes...")
            try:
                session.run(
                    "CREATE INDEX entity_type_idx IF NOT EXISTS "
                    "FOR (e:Entity) ON (e.type)"
                )
                print("  ✓ Entity type index created")
            except Exception as e:
                print(f"  ⚠ Type index: {e}")

            try:
                session.run(
                    "CREATE TEXT INDEX entity_name_text_idx IF NOT EXISTS "
                    "FOR (e:Entity) ON (e.name)"
                )
                print("  ✓ Entity name text index created")
            except Exception as e:
                print(f"  ⚠ Text index: {e}")

            # 3. MENTIONS 관계 생성 확인용 샘플 데이터 (Optional)
            print("\n[3/5] Verifying MENTIONS relationship pattern...")
            result = session.run("""
                MATCH (c:Chunk)
                RETURN count(c) as chunk_count
            """)
            chunk_count = result.single()["chunk_count"]
            print(f"  ✓ Found {chunk_count} Chunk nodes")

            # 4. 스키마 정보 확인
            print("\n[4/5] Checking current schema...")
            result = session.run("CALL db.labels() YIELD label RETURN collect(label) as labels")
            labels = result.single()["labels"]
            print(f"  Labels: {labels}")

            result = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) as types")
            rel_types = result.single()["types"]
            print(f"  Relationship types: {rel_types}")

            # 5. 제약조건 및 인덱스 확인
            print("\n[5/5] Verifying constraints and indexes...")
            result = session.run("SHOW CONSTRAINTS")
            constraints = list(result)
            print(f"  Constraints ({len(constraints)}):")
            for c in constraints:
                print(f"    - {c.get('name', 'N/A')}: {c.get('labelsOrTypes', 'N/A')} on {c.get('properties', 'N/A')}")

            result = session.run("SHOW INDEXES")
            indexes = list(result)
            print(f"  Indexes ({len(indexes)}):")
            for idx in indexes:
                print(f"    - {idx.get('name', 'N/A')}: {idx.get('labelsOrTypes', 'N/A')} ({idx.get('type', 'N/A')})")

            print("\n" + "=" * 50)
            print("Entity schema setup completed!")
            print("=" * 50)

            # Entity가 없으면 샘플 Entity 생성 제안
            result = session.run("MATCH (e:Entity) RETURN count(e) as count")
            entity_count = result.single()["count"]
            if entity_count == 0:
                print("\n⚠ No Entity nodes found.")
                print("  To extract entities from existing chunks, run:")
                print("  python scripts/extract_entities.py")

    finally:
        driver.close()


if __name__ == "__main__":
    setup_entity_schema()
