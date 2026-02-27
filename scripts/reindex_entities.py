#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entity Reindexing Script
Extracts entities from all Chunk nodes and creates Entity nodes with MENTIONS relationships.

This script applies the new OpenFrame entity patterns (COMMAND, ERROR_CODE, CONFIG)
to all existing chunks in the Neo4j database.

Usage:
    python scripts/reindex_entities.py [--batch-size 100] [--dry-run]

Options:
    --batch-size    Number of chunks to process per batch (default: 100)
    --dry-run       Preview without writing to database
    --doc-filter    Filter by document ID pattern (e.g., "pdf_")
"""
import asyncio
import argparse
import sys
import os
import time
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import after path setup
from neo4j import AsyncGraphDatabase
from dotenv import load_dotenv

# Load environment
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


async def get_chunk_count(driver) -> int:
    """Get total number of chunks"""
    async with driver.session() as session:
        result = await session.run("MATCH (c:Chunk) RETURN count(c) as count")
        record = await result.single()
        return record["count"] if record else 0


async def get_chunks_batch(driver, skip: int, limit: int, doc_filter: str = None) -> List[Dict]:
    """Get a batch of chunks"""
    async with driver.session() as session:
        if doc_filter:
            query = """
            MATCH (c:Chunk)
            WHERE c.doc_id STARTS WITH $doc_filter
            RETURN c.id as chunk_id, c.content as content, c.doc_id as doc_id
            ORDER BY c.id
            SKIP $skip LIMIT $limit
            """
            result = await session.run(query, skip=skip, limit=limit, doc_filter=doc_filter)
        else:
            query = """
            MATCH (c:Chunk)
            RETURN c.id as chunk_id, c.content as content, c.doc_id as doc_id
            ORDER BY c.id
            SKIP $skip LIMIT $limit
            """
            result = await session.run(query, skip=skip, limit=limit)

        records = await result.data()
        return records


async def create_entity_and_link(driver, entity_name: str, entity_type: str, chunk_id: str, dry_run: bool = False):
    """Create Entity node and MENTIONS relationship"""
    if dry_run:
        return

    async with driver.session() as session:
        # MERGE Entity and create relationship
        query = """
        MATCH (c:Chunk {id: $chunk_id})
        MERGE (e:Entity {name: $entity_name})
        ON CREATE SET e.entity_type = $entity_type, e.created_at = datetime()
        MERGE (c)-[:MENTIONS]->(e)
        """
        await session.run(query, chunk_id=chunk_id, entity_name=entity_name, entity_type=entity_type)


async def extract_entities_from_text(text: str) -> List[Dict[str, str]]:
    """Extract entities from text using the new patterns"""
    import re

    entities = []
    seen = set()

    # OpenFrame command patterns
    command_patterns = [
        r'\b(?:tjes|hidb|of|tac|tso|vtam|cics|batch|online)mgr\b',
        r'\b(?:tjesmgr|hidbmgr|ofmgr|tacfmgr|tsomgr|vtammgr|cicsmgr)\s+[A-Z]+\b',
        r'\b(?:IDCAMS|IEBGENER|IEBCOPY|IEFBR14|SORT|DFSORT)\b',
    ]

    # Error code patterns
    error_patterns = [
        r'(?<![A-Z])-\d{4,5}(?![0-9])',
        r'\b(?:JEUS|TIBERO|TMAX|OFM|OFCOBOL|OFASM|ORA|SQL|ERR|ERROR)-\d{4,5}\b',
        r'\b(?:DSALC|BASE|AIM|TJES|HIDB|TACF)_(?:ERR|ERROR)_[A-Z_]+\b',
    ]

    # Config patterns
    config_patterns = [
        r'\b(?:oframe|tjes|hidb|osc|tacf)\.conf\b',
        r'\b(?:OPENFRAME_HOME|TMAX_HOST_ADDR|TB_SID|COBDIR)\b',
    ]

    # Extract commands
    for pattern in command_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            name = match.group().strip()
            if name.lower() not in seen:
                seen.add(name.lower())
                entities.append({"name": name, "type": "command"})

    # Extract error codes
    for pattern in error_patterns:
        for match in re.finditer(pattern, text):
            name = match.group().strip()
            if name.lower() not in seen:
                seen.add(name.lower())
                entities.append({"name": name, "type": "error_code"})

    # Extract configs
    for pattern in config_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            name = match.group().strip()
            if name.lower() not in seen:
                seen.add(name.lower())
                entities.append({"name": name, "type": "config"})

    return entities


async def reindex_entities(batch_size: int = 100, dry_run: bool = False, doc_filter: str = None):
    """Main reindexing function"""
    print("=" * 60)
    print("Entity Reindexing - OpenFrame Patterns")
    print("=" * 60)
    print(f"Neo4j URI: {NEO4J_URI}")
    print(f"Batch size: {batch_size}")
    print(f"Dry run: {dry_run}")
    if doc_filter:
        print(f"Document filter: {doc_filter}")
    print("-" * 60)

    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        # Get total chunk count
        total_chunks = await get_chunk_count(driver)
        print(f"Total chunks in database: {total_chunks}")

        # Statistics
        stats = {
            "chunks_processed": 0,
            "entities_created": 0,
            "relationships_created": 0,
            "by_type": {"command": 0, "error_code": 0, "config": 0}
        }

        start_time = time.time()
        skip = 0

        while True:
            # Get batch of chunks
            chunks = await get_chunks_batch(driver, skip, batch_size, doc_filter)

            if not chunks:
                break

            for chunk in chunks:
                chunk_id = chunk["chunk_id"]
                content = chunk.get("content", "")

                if not content:
                    continue

                # Extract entities
                entities = await extract_entities_from_text(content)

                for entity in entities:
                    # Create entity and link
                    await create_entity_and_link(
                        driver,
                        entity["name"],
                        entity["type"],
                        chunk_id,
                        dry_run
                    )
                    stats["entities_created"] += 1
                    stats["relationships_created"] += 1
                    stats["by_type"][entity["type"]] += 1

                stats["chunks_processed"] += 1

            # Progress
            elapsed = time.time() - start_time
            rate = stats["chunks_processed"] / elapsed if elapsed > 0 else 0
            print(f"Processed {stats['chunks_processed']}/{total_chunks} chunks "
                  f"({stats['chunks_processed']/total_chunks*100:.1f}%) - "
                  f"{rate:.1f} chunks/sec - "
                  f"Entities: {stats['entities_created']}")

            skip += batch_size

        # Final report
        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print("Reindexing Complete!")
        print("=" * 60)
        print(f"Time elapsed: {elapsed:.1f} seconds")
        print(f"Chunks processed: {stats['chunks_processed']}")
        print(f"Entities created/updated: {stats['entities_created']}")
        print(f"MENTIONS relationships: {stats['relationships_created']}")
        print("\nBy Entity Type:")
        print(f"  COMMAND: {stats['by_type']['command']}")
        print(f"  ERROR_CODE: {stats['by_type']['error_code']}")
        print(f"  CONFIG: {stats['by_type']['config']}")

        if dry_run:
            print("\n[DRY RUN] No changes were written to the database.")

    finally:
        await driver.close()


def main():
    parser = argparse.ArgumentParser(description="Reindex entities in Neo4j")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--doc-filter", type=str, help="Filter by document ID prefix")

    args = parser.parse_args()

    asyncio.run(reindex_entities(
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        doc_filter=args.doc_filter
    ))


if __name__ == "__main__":
    main()
