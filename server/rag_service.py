"""rag_service: Neo4j vector search via bge-m3 embeddings.

Provides RAG retrieval from OpenFrame product manuals stored in Neo4j.
Uses bge-m3 (1024d) to encode queries, then searches Neo4j's chunk_embedding
vector index for the most relevant document chunks.
"""

import json
import os
from typing import List, Dict, Optional

import httpx

# ── Configuration ──
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://192.168.8.11:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "graphrag2024")
BGE_M3_URL = os.environ.get("BGE_M3_URL", "http://192.168.8.11:12801")
EMBED_TIMEOUT = float(os.environ.get("RAG_EMBED_TIMEOUT", "5.0"))
NEO4J_TIMEOUT = float(os.environ.get("RAG_NEO4J_TIMEOUT", "5.0"))

# Product name → filename patterns for Neo4j Document filtering
PRODUCT_FILE_PATTERNS = {
    "ofasm": ["ofasm"],
    "osc": ["osc", "cics"],
    "batch": ["batch", "tjes"],
    "ims": ["ims"],
    "base": ["of_base", "base-guide", "base_"],
    "ofcobol": ["ofcobol", "cobol"],
    "tacf": ["tacf"],
    "aim": ["aim"],
    "gw": ["of_gw", "gw_"],
    "ndb": ["ndb"],
    "hidb": ["hidb"],
    "common": ["common"],
    "ibm": ["asmr1022", "hlasm"],
}


def _get_embedding(text: str) -> Optional[List[float]]:
    """Get 1024d embedding from bge-m3 service."""
    try:
        resp = httpx.post(
            f"{BGE_M3_URL}/v1/embeddings",
            json={"input": [text], "model": "bge-m3"},
            timeout=EMBED_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        print(f"[rag_service] bge-m3 embedding error: {e}")
        return None


class RAGService:
    """Neo4j vector search service for OpenFrame manuals."""

    def __init__(self):
        self._driver = None
        self._available = False

    def connect(self) -> bool:
        """Initialize Neo4j driver."""
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            self._available = True
            print(f"[rag_service] Neo4j connected: {NEO4J_URI}")
            return True
        except Exception as e:
            print(f"[rag_service] Neo4j connection failed: {e}")
            self._available = False
            return False

    @property
    def available(self) -> bool:
        return self._available and self._driver is not None

    def search(
        self,
        query: str,
        product: str = "",
        top_k: int = 3,
    ) -> List[Dict]:
        """Search Neo4j vector index for relevant document chunks.

        Args:
            query: Search query text
            product: Product name for filtering (e.g. "OFASM", "OSC")
            top_k: Number of results to return

        Returns:
            List of dicts with keys: content, doc_name, page_number, score
        """
        if not self.available:
            return []

        # 1. Get query embedding from bge-m3
        embedding = _get_embedding(query)
        if embedding is None:
            return []

        # 2. Build Cypher query
        product_lower = product.lower().strip() if product else ""
        patterns = PRODUCT_FILE_PATTERNS.get(product_lower, [])

        if patterns:
            # Product-filtered search: fetch more candidates, filter in Cypher
            cypher = """
            CALL db.index.vector.queryNodes('chunk_embedding', $k, $embedding)
            YIELD node, score
            MATCH (d:Document)-[:HAS_CHUNK|CONTAINS]->(node)
            WHERE ANY(pattern IN $patterns WHERE toLower(d.filename) CONTAINS pattern)
            RETURN node.content AS content,
                   d.filename AS doc_name,
                   node.page_number AS page_number,
                   score
            ORDER BY score DESC
            LIMIT $limit
            """
            params = {
                "k": top_k * 10,  # fetch more for filtering
                "embedding": embedding,
                "patterns": patterns,
                "limit": top_k,
            }
        else:
            # Unfiltered search
            cypher = """
            CALL db.index.vector.queryNodes('chunk_embedding', $k, $embedding)
            YIELD node, score
            MATCH (d:Document)-[:HAS_CHUNK|CONTAINS]->(node)
            RETURN node.content AS content,
                   d.filename AS doc_name,
                   node.page_number AS page_number,
                   score
            ORDER BY score DESC
            LIMIT $limit
            """
            params = {
                "k": top_k * 5,  # fetch more for dedup
                "embedding": embedding,
                "limit": top_k * 5,
            }

        # 3. Execute query
        try:
            with self._driver.session() as session:
                result = session.run(cypher, params)
                records = []
                seen_content = set()
                for record in result:
                    content = record["content"] or ""
                    # Deduplicate by content prefix (same chunk in multiple docs)
                    content_key = content[:200]
                    if content_key in seen_content:
                        continue
                    seen_content.add(content_key)
                    # Truncate long content to avoid context overflow
                    if len(content) > 600:
                        content = content[:600] + "..."
                    records.append({
                        "content": content,
                        "doc_name": record["doc_name"] or "",
                        "page_number": record["page_number"],
                        "score": round(float(record["score"]), 4),
                    })
                    if len(records) >= top_k:
                        break
                return records
        except Exception as e:
            print(f"[rag_service] Neo4j search error: {e}")
            return []

    def get_status(self) -> Dict:
        """Return service status."""
        if not self.available:
            return {"available": False, "neo4j_uri": NEO4J_URI}
        try:
            with self._driver.session() as session:
                result = session.run(
                    "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL "
                    "RETURN count(c) AS total"
                )
                total = result.single()["total"]
            return {
                "available": True,
                "neo4j_uri": NEO4J_URI,
                "bge_m3_url": BGE_M3_URL,
                "total_chunks": total,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    def close(self):
        """Close Neo4j driver."""
        if self._driver:
            self._driver.close()
            self._driver = None
            self._available = False
