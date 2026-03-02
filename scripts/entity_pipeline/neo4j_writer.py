"""
Neo4j Batch Writer - EntityバッチMERGE + 統計クエリ

冪等性保証: MERGE使用により再実行で重複なし
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from neo4j import GraphDatabase, AsyncGraphDatabase


@dataclass
class DbStats:
    """Neo4jデータベース統計"""
    total_chunks: int
    connected_chunks: int
    orphan_chunks: int
    total_entities: int
    total_mentions: int

    @property
    def orphan_pct(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return self.orphan_chunks / self.total_chunks * 100

    @property
    def connected_pct(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return self.connected_chunks / self.total_chunks * 100


@dataclass
class WriteResult:
    """バッチ書き込み結果"""
    entities_processed: int = 0
    mentions_processed: int = 0


class Neo4jBatchWriter:
    """Neo4jバッチ書き込み (同期ドライバ使用)"""

    MERGE_BATCH_SIZE = 500
    INTER_BATCH_DELAY = 0.01  # 10ms

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def get_stats(self) -> DbStats:
        """現在のDB統計を取得"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (c:Chunk)
                OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
                WITH c, count(e) AS ec
                RETURN
                    count(c) AS total_chunks,
                    sum(CASE WHEN ec > 0 THEN 1 ELSE 0 END) AS connected_chunks,
                    sum(CASE WHEN ec = 0 THEN 1 ELSE 0 END) AS orphan_chunks
            """)
            row = result.single()
            total_chunks = row["total_chunks"]
            connected = row["connected_chunks"]
            orphan = row["orphan_chunks"]

            # Entity・MENTIONS カウント
            result2 = session.run("""
                MATCH (e:Entity) RETURN count(e) AS cnt
            """)
            total_entities = result2.single()["cnt"]

            result3 = session.run("""
                MATCH ()-[r:MENTIONS]->() RETURN count(r) AS cnt
            """)
            total_mentions = result3.single()["cnt"]

        return DbStats(
            total_chunks=total_chunks,
            connected_chunks=connected,
            orphan_chunks=orphan,
            total_entities=total_entities,
            total_mentions=total_mentions,
        )

    def fetch_orphan_chunks(self, skip: int, limit: int) -> List[Dict]:
        """Entity未接続のChunkをバッチフェッチ"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (c:Chunk)
                WHERE NOT (c)-[:MENTIONS]->(:Entity)
                  AND c.content IS NOT NULL
                  AND size(c.content) >= 30
                RETURN c.id AS id, c.content AS content
                ORDER BY c.id
                SKIP $skip LIMIT $limit
            """, skip=skip, limit=limit)
            return [{"id": r["id"], "content": r["content"]} for r in result]

    def write_batch(self, entities: List) -> WriteResult:
        """Entityバッチ書き込み (MERGE保証)

        Args:
            entities: List of ExtractedEntity (name, entity_type, confidence, chunk_id)
        """
        if not entities:
            return WriteResult()

        # Entity重複排除 (同一name+chunk_idは1つに)
        unique = {}
        for e in entities:
            key = (e.name.lower(), e.chunk_id)
            if key not in unique or e.confidence > unique[key].confidence:
                unique[key] = e

        items = [
            {
                "name": e.name,
                "type": e.entity_type,
                "confidence": e.confidence,
                "chunk_id": e.chunk_id,
            }
            for e in unique.values()
        ]

        total_result = WriteResult()

        for i in range(0, len(items), self.MERGE_BATCH_SIZE):
            batch = items[i:i + self.MERGE_BATCH_SIZE]
            result = self._execute_merge(batch)
            total_result.entities_processed += result.entities_processed
            total_result.mentions_processed += result.mentions_processed

            if i + self.MERGE_BATCH_SIZE < len(items):
                time.sleep(self.INTER_BATCH_DELAY)

        return total_result

    def _execute_merge(self, batch: List[Dict]) -> WriteResult:
        """バッチMERGE実行"""
        with self.driver.session() as session:
            result = session.run("""
                UNWIND $batch AS item
                MERGE (e:Entity {name: item.name})
                  ON CREATE SET
                    e.type = item.type,
                    e.confidence = item.confidence,
                    e.source = 'pipeline_v1',
                    e.created_at = datetime()
                  ON MATCH SET
                    e.confidence = CASE
                      WHEN item.confidence > e.confidence
                      THEN item.confidence
                      ELSE e.confidence END
                WITH e, item
                MATCH (c:Chunk {id: item.chunk_id})
                MERGE (c)-[:MENTIONS]->(e)
                RETURN count(*) AS cnt
            """, batch=batch)
            row = result.single()
            cnt = row["cnt"] if row else 0

        return WriteResult(
            entities_processed=len(batch),
            mentions_processed=cnt,
        )

    def get_entity_type_distribution(self, source: Optional[str] = None) -> Dict[str, int]:
        """Entity種別分布を取得"""
        query = "MATCH (e:Entity)"
        params = {}
        if source:
            query += " WHERE e.source = $source"
            params["source"] = source
        query += " RETURN e.type AS type, count(e) AS cnt ORDER BY cnt DESC"

        with self.driver.session() as session:
            result = session.run(query, **params)
            return {r["type"]: r["cnt"] for r in result}

    def verify_entity(self, entity_name: str) -> Dict:
        """特定Entityの接続状態を検証"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (e:Entity)
                WHERE toLower(e.name) = toLower($name)
                OPTIONAL MATCH (c:Chunk)-[:MENTIONS]->(e)
                RETURN
                    e.name AS name,
                    e.type AS type,
                    e.confidence AS confidence,
                    e.source AS source,
                    count(c) AS chunk_count,
                    collect(substring(c.content, 0, 80))[..3] AS sample_chunks
            """, name=entity_name)
            row = result.single()
            if not row:
                return {"found": False, "name": entity_name}
            return {
                "found": True,
                "name": row["name"],
                "type": row["type"],
                "confidence": row["confidence"],
                "source": row["source"],
                "chunk_count": row["chunk_count"],
                "sample_chunks": row["sample_chunks"],
            }
