"""
Phase 3: Chunk + BGE-M3 Embed + Neo4j MERGE
이슈 텍스트를 청킹, 임베딩 생성, Neo4j에 저장하여 기존 vector_search에서 검색 가능하게 함.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from neo4j import GraphDatabase

from .config import (
    BGE_M3_URL,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT,
    IMS_PRODUCT_TO_PRODUCT_ID,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    OUTPUT_DIR,
)
from .content_filter import filter_issue_text

logger = logging.getLogger(__name__)


# ── 엔티티 추출 (knowledge_graph_service.py 패턴 재사용) ──────────

# EntityType 값은 Neo4j Entity.type 필드에 저장
ENTITY_PATTERNS: dict[str, list[str]] = {
    "COMMAND": [
        r'\b[a-z]{2,10}mgr\b',
        r'\b(?:tjesmgr|hidbmgr|ofmgr|tacfmgr|tsomgr|vtammgr|cicsmgr|oscmgr)\s+[A-Z]+\b',
        r'\b(?:osctdl(?:init|rm|update)|oscmcsvr|oscscview|oscsddump|oscsdgen|oscfdump|oscfgen|oscrsasvr)\b',
        r'\b(?:dsmigin|dsmigout|dsview|dscreate|dsdelete|dscopy|dsrename|dslist|dsentool)\b',
        r'\b(?:ofcbppf|ofconfig|oferror|ofjclpp|offile|ofsautil|ofudtool|ofrpmsvr)\b',
        r'\b(?:tjesinit|tjesdown|tjesclean|tjclrun)\b',
        r'\b(?:IDCAMS|IEBGENER|IEBCOPY|IEFBR14|SORT|DFSORT|IKJEFT01|ADRDSSU|AMASPZAP)\b',
        r'\b(?:tmboot|tmdown|ofboot|ofdown|jesinit|jesdown|tmadmin|oscboot|oscdown)\b',
    ],
    "ERROR_CODE": [
        r'(?<![A-Za-z])-\d{4,5}(?!\d)',
        r'\b(?:JEUS|TIBERO|TMAX|OFM|OFCOBOL|OFASM|ORA|SQL|ERR|ERROR)-\d{4,5}\b',
        r'\b[A-Z]{2,10}_ERR_[A-Z_]+\b',
        r'\bS[0-9][0-9A-F]{2}\b',
    ],
    "CONFIG": [
        r'\b(?:oframe|tjes|hidb|osc|tacf|ds|batch|ofgw|ofmanager)\.conf\b',
        r'\b(?:OPENFRAME_HOME|TMAX_HOST_ADDR|TB_SID|COBDIR|TMAXDIR|TMAX_DIR|OFGW_HOME)\b',
    ],
    "PRODUCT": [
        r'\bOpenFrame[/ ]?(?:Base|TJES|OSC|TACF|HIDB|ASM|COBOL|Manager|Gateway|Studio)\b',
        r'\b(?:Tmax|Tibero|JEUS|ProObject|WebtoB)\s*\d*\b',
        r'\b(?:OFMiner|OFStudio|OFManager|OFGW)\b',
    ],
    "TECHNOLOGY": [
        r'\b(?:VSAM|KSDS|ESDS|RRDS|LDS|PDS|GDG|SMS)\b',
        r'\b(?:CICS|IMS|DB2|JES2|JES3|TSO|ISPF|VTAM)\b',
        r'\b(?:COBOL|JCL|REXX|Assembler)\b',
    ],
}


def extract_entities(text: str) -> list[dict]:
    """패턴 기반 엔티티 추출. 중복 제거."""
    seen: set[str] = set()
    entities: list[dict] = []

    for entity_type, patterns in ENTITY_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                name = match.group(0).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                entities.append({
                    "name": name,
                    "type": entity_type,
                    "confidence": 0.85,
                })

    return entities


# ── 임베딩 생성 ────────────────────────────────────────────────────


def embed_texts(texts: list[str]) -> list[list[float]]:
    """BGE-M3 1024-dim dense 임베딩 생성 (동기)."""
    if not texts:
        return []

    with httpx.Client(timeout=EMBEDDING_TIMEOUT) as client:
        resp = client.post(
            f"{BGE_M3_URL}/v1/embeddings",
            json={"input": texts, "model": EMBEDDING_MODEL},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        # 입력 순서대로 정렬
        sorted_data = sorted(data, key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]


# ── 청킹 ──────────────────────────────────────────────────────────


def _make_chunk_id(ims_id: str, chunk_type: str) -> str:
    """결정적 chunk ID 생성 (재실행 시 동일 ID 보장 → MERGE 멱등성)."""
    raw = f"ims_{ims_id}_{chunk_type}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def chunk_issue(ims_id: str, text: str) -> list[dict]:
    """
    이슈 텍스트를 필터링 후 1-2개 청크로 분할.
    - description: 메타헤더 + 문의 내용 (필터링 완료)
    - action_log: 응답 및 조치 (기술적 내용만, 있을 경우)
    """
    # 콘텐츠 필터 적용: 노이즈 제거, 기술 내용만 추출
    filtered = filter_issue_text(text)

    chunks: list[dict] = []

    # '## 응답 및 조치' 기준으로 분할 (필터 출력 형식)
    parts = filtered.split("## 응답 및 조치", maxsplit=1)

    desc_text = parts[0].strip()
    if desc_text:
        chunks.append({
            "chunk_id": _make_chunk_id(ims_id, "description"),
            "content": desc_text,
            "chunk_type": "ims_description",
        })

    if len(parts) > 1:
        action_text = parts[1].strip()
        if action_text and len(action_text) > 20:
            chunks.append({
                "chunk_id": _make_chunk_id(ims_id, "action_log"),
                "content": f"## 응답 및 조치\n{action_text}",
                "chunk_type": "ims_action_log",
            })

    return chunks


# ── Neo4j 저장 ─────────────────────────────────────────────────────


CYPHER_MERGE_DOC = """
MERGE (d:Document {filename: $filename})
ON CREATE SET
  d.type = 'ims_issue',
  d.product = $product_id,
  d.ims_id = $ims_id,
  d.title = $subject,
  d.status = $status,
  d.customer = $customer,
  d.source_url = $source_url,
  d.created_at = datetime()
ON MATCH SET
  d.status = $status,
  d.title = $subject,
  d.updated_at = datetime()
RETURN d.filename AS filename
"""

CYPHER_MERGE_CHUNK = """
MERGE (c:Chunk {id: $chunk_id})
ON CREATE SET
  c.content = $content,
  c.embedding = $embedding,
  c.source = $filename,
  c.page_number = 0,
  c.chunk_type = $chunk_type
ON MATCH SET
  c.content = $content,
  c.embedding = $embedding,
  c.chunk_type = $chunk_type
WITH c
MATCH (d:Document {filename: $filename})
MERGE (d)-[:HAS_CHUNK]->(c)
RETURN c.id AS chunk_id
"""

CYPHER_MERGE_ENTITY = """
UNWIND $entities AS item
MERGE (e:Entity {name: item.name})
  ON CREATE SET
    e.type = item.type,
    e.confidence = item.confidence,
    e.created_at = datetime()
  ON MATCH SET
    e.confidence = CASE
      WHEN item.confidence > e.confidence THEN item.confidence
      ELSE e.confidence END
WITH e, item
MATCH (c:Chunk {id: item.chunk_id})
MERGE (c)-[:MENTIONS]->(e)
RETURN count(*) AS cnt
"""


def embed_and_store(
    output_dir: Optional[Path] = None,
    batch_size: int = 10,
    force: bool = False,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> dict:
    """
    .txt 파일 → 청킹 → BGE-M3 임베딩 → Neo4j MERGE.
    dry_run=True 시 BGE-M3 호출 없이 zero-vector로 Neo4j MERGE 검증.
    limit: 처리할 파일 수 제한 (테스트용).
    """
    output_dir = output_dir or OUTPUT_DIR
    index_path = output_dir / "index.json"

    if not index_path.exists():
        raise FileNotFoundError(f"index.json not found: {index_path}")

    # 인덱스 로드
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index_map = {item["ims_id"]: item for item in index}

    # .txt 파일 수집
    txt_files = sorted(output_dir.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"No .txt files found in {output_dir}")

    if limit:
        txt_files = txt_files[:limit]
        logger.info(f"Limited to {limit} files (out of {len(list(output_dir.glob('*.txt')))})")

    logger.info(f"Found {len(txt_files)} .txt files to process")

    # Neo4j 연결
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    logger.info(f"Connected to Neo4j at {NEO4J_URI}")

    stats = {
        "total_files": len(txt_files),
        "documents_created": 0,
        "chunks_created": 0,
        "entities_created": 0,
        "skipped": 0,
        "failed": 0,
    }

    try:
        # 배치 처리
        for batch_start in range(0, len(txt_files), batch_size):
            batch_files = txt_files[batch_start:batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            total_batches = (len(txt_files) + batch_size - 1) // batch_size
            logger.info(f"Batch {batch_num}/{total_batches}: {len(batch_files)} files")

            # 1. 파일 읽기 + 청킹
            all_chunks: list[dict] = []
            file_meta: list[dict] = []

            for txt_path in batch_files:
                ims_id = txt_path.stem
                meta = index_map.get(ims_id, {"ims_id": ims_id})

                text = txt_path.read_text(encoding="utf-8")
                if not text.strip():
                    stats["skipped"] += 1
                    continue

                chunks = chunk_issue(ims_id, text)
                for chunk in chunks:
                    chunk["ims_id"] = ims_id
                    chunk["filename"] = f"ims_issue_{ims_id}.txt"
                    chunk["meta"] = meta
                all_chunks.extend(chunks)
                file_meta.append(meta)

            if not all_chunks:
                continue

            # 2. BGE-M3 임베딩 생성 (배치) 또는 dry-run zero-vector
            texts_to_embed = [c["content"] for c in all_chunks]
            if dry_run:
                embeddings = [[0.0] * EMBEDDING_DIM for _ in texts_to_embed]
                logger.info(f"  [DRY-RUN] Using zero vectors ({EMBEDDING_DIM}-dim) for {len(texts_to_embed)} chunks")
            else:
                try:
                    embeddings = embed_texts(texts_to_embed)
                except Exception as e:
                    logger.error(f"Embedding failed for batch {batch_num}: {e}")
                    stats["failed"] += len(batch_files)
                    continue

            for chunk, emb in zip(all_chunks, embeddings):
                chunk["embedding"] = emb

            # 3. Neo4j 저장
            with driver.session() as session:
                # Document 노드
                seen_docs: set[str] = set()
                for chunk in all_chunks:
                    fname = chunk["filename"]
                    if fname in seen_docs:
                        continue
                    seen_docs.add(fname)

                    meta = chunk["meta"]
                    product_id = meta.get("product_id") or IMS_PRODUCT_TO_PRODUCT_ID.get(
                        meta.get("product", ""), ""
                    )

                    session.run(CYPHER_MERGE_DOC, {
                        "filename": fname,
                        "product_id": product_id,
                        "ims_id": meta.get("ims_id", ""),
                        "subject": meta.get("subject", ""),
                        "status": meta.get("status", ""),
                        "customer": meta.get("customer", ""),
                        "source_url": meta.get("source_url", ""),
                    })
                    stats["documents_created"] += 1

                # Chunk 노드 + HAS_CHUNK 관계
                for chunk in all_chunks:
                    session.run(CYPHER_MERGE_CHUNK, {
                        "chunk_id": chunk["chunk_id"],
                        "content": chunk["content"],
                        "embedding": chunk["embedding"],
                        "filename": chunk["filename"],
                        "chunk_type": chunk["chunk_type"],
                    })
                    stats["chunks_created"] += 1

                # Entity 추출 + MENTIONS 관계
                entity_batch: list[dict] = []
                for chunk in all_chunks:
                    entities = extract_entities(chunk["content"])
                    for ent in entities:
                        ent["chunk_id"] = chunk["chunk_id"]
                    entity_batch.extend(entities)

                if entity_batch:
                    result = session.run(CYPHER_MERGE_ENTITY, {"entities": entity_batch})
                    row = result.single()
                    stats["entities_created"] += row["cnt"] if row else 0

            logger.info(
                f"Batch {batch_num} done: "
                f"{len(seen_docs)} docs, {len(all_chunks)} chunks, "
                f"{len(entity_batch)} entity relations"
            )

    finally:
        driver.close()

    logger.info(
        f"Embedding complete: {stats['documents_created']} docs, "
        f"{stats['chunks_created']} chunks, {stats['entities_created']} entities, "
        f"{stats['skipped']} skipped, {stats['failed']} failed"
    )
    return stats


# ── 통계 + 테스트 검색 ─────────────────────────────────────────────


def get_stats() -> dict:
    """Neo4j에 저장된 IMS 이슈 통계."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            docs = session.run(
                "MATCH (d:Document {type: 'ims_issue'}) RETURN count(d) AS cnt"
            ).single()["cnt"]

            chunks = session.run(
                "MATCH (d:Document {type: 'ims_issue'})-[:HAS_CHUNK]->(c:Chunk) "
                "RETURN count(c) AS cnt"
            ).single()["cnt"]

            entities = session.run(
                "MATCH (d:Document {type: 'ims_issue'})-[:HAS_CHUNK]->(c:Chunk)"
                "-[:MENTIONS]->(e:Entity) "
                "RETURN count(DISTINCT e) AS cnt"
            ).single()["cnt"]

            # 제품별 분포
            products = session.run(
                "MATCH (d:Document {type: 'ims_issue'}) "
                "RETURN d.product AS product, count(d) AS cnt "
                "ORDER BY cnt DESC"
            )
            product_dist = {r["product"]: r["cnt"] for r in products}

        return {
            "documents": docs,
            "chunks": chunks,
            "entities": entities,
            "products": product_dist,
        }
    finally:
        driver.close()


def test_search(query: str, top_k: int = 5) -> list[dict]:
    """BGE-M3 임베딩으로 IMS 이슈 벡터 검색 테스트."""
    # 쿼리 임베딩
    query_emb = embed_texts([query])[0]

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            # 코사인 유사도 기반 검색 (IMS 이슈만)
            result = session.run("""
                MATCH (d:Document {type: 'ims_issue'})-[:HAS_CHUNK]->(c:Chunk)
                WHERE c.embedding IS NOT NULL
                WITH c, d,
                     gds.similarity.cosine(c.embedding, $query_embedding) AS score
                ORDER BY score DESC
                LIMIT $top_k
                RETURN c.id AS chunk_id,
                       c.content AS content,
                       c.chunk_type AS chunk_type,
                       d.ims_id AS ims_id,
                       d.title AS title,
                       d.product AS product,
                       score
            """, {
                "query_embedding": query_emb,
                "top_k": top_k,
            })

            results = []
            for r in result:
                results.append({
                    "ims_id": r["ims_id"],
                    "title": r["title"],
                    "product": r["product"],
                    "chunk_type": r["chunk_type"],
                    "score": round(r["score"], 4),
                    "content": r["content"][:200] + "..." if len(r["content"]) > 200 else r["content"],
                })
            return results
    finally:
        driver.close()
