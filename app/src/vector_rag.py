"""
Vector RAG Module for GraphRAG Hybrid System
Uses Neo4j Vector Index for semantic similarity search
"""
import re
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_community.graphs import Neo4jGraph
from embeddings import NeMoEmbeddingService
from config import config


class VectorRAG:
    """
    Vector-based RAG using Neo4j vector index for semantic search
    """

    def __init__(
        self,
        graph: Optional[Neo4jGraph] = None,
        embedding_service: Optional[NeMoEmbeddingService] = None,
        llm: Optional[ChatOpenAI] = None
    ):
        """
        Initialize VectorRAG

        Args:
            graph: Neo4j graph connection
            embedding_service: NeMo embedding service
            llm: Language model for answer generation
        """
        self.graph = graph or Neo4jGraph(
            url=config.neo4j.uri,
            username=config.neo4j.user,
            password=config.neo4j.password
        )

        self.embedding_service = embedding_service or NeMoEmbeddingService()

        self.llm = llm or ChatOpenAI(
            base_url=config.llm.api_url.replace("/chat/completions", ""),
            model=config.llm.model,
            api_key="not-needed",
            temperature=0.1
        )

        self.vector_index_name = config.vector.index_name
        self.dimension = config.vector.dimension

    def init_vector_index(self) -> bool:
        """
        Create vector index on Chunk.embedding if not exists

        Returns:
            True if successful
        """
        try:
            self.graph.query(f"""
                CREATE VECTOR INDEX {self.vector_index_name} IF NOT EXISTS
                FOR (c:Chunk) ON (c.embedding)
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {self.dimension},
                        `vector.similarity_function`: '{config.vector.similarity_function}'
                    }}
                }}
            """)
            print(f"Vector index '{self.vector_index_name}' created/verified")
            return True
        except Exception as e:
            print(f"Vector index creation error: {e}")
            return False

    def add_embedding_to_chunk(self, chunk_id: str, content: str) -> bool:
        """
        Add embedding to an existing chunk

        Args:
            chunk_id: The chunk's unique ID
            content: The chunk's text content

        Returns:
            True if successful
        """
        try:
            embedding = self.embedding_service.embed_text(content, input_type="passage")

            self.graph.query(
                """
                MATCH (c:Chunk {id: $chunk_id})
                SET c.embedding = $embedding
                """,
                {"chunk_id": chunk_id, "embedding": embedding}
            )
            return True
        except Exception as e:
            print(f"Error adding embedding to chunk {chunk_id}: {e}")
            return False

    def add_embeddings_batch(self, chunks: List[Dict[str, str]]) -> int:
        """
        Add embeddings to multiple chunks in batch

        Args:
            chunks: List of dicts with 'id' and 'content' keys

        Returns:
            Number of successfully processed chunks
        """
        if not chunks:
            return 0

        # Generate embeddings in batch
        contents = [c["content"] for c in chunks]
        embeddings = self.embedding_service.embed_batch(contents, input_type="passage")

        success_count = 0
        for chunk, embedding in zip(chunks, embeddings):
            try:
                self.graph.query(
                    """
                    MATCH (c:Chunk {id: $chunk_id})
                    SET c.embedding = $embedding
                    """,
                    {"chunk_id": chunk["id"], "embedding": embedding}
                )
                success_count += 1
            except Exception as e:
                print(f"Error updating chunk {chunk['id']}: {e}")

        return success_count

    def search_similar(
        self,
        query: str,
        k: int = 5,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks using vector similarity

        Args:
            query: The search query
            k: Number of results to return
            min_score: Minimum similarity score threshold

        Returns:
            List of matching chunks with scores
        """
        # Generate query embedding
        query_embedding = self.embedding_service.embed_text(query, input_type="query")

        # Search using Neo4j vector index
        results = self.graph.query(
            f"""
            CALL db.index.vector.queryNodes('{self.vector_index_name}', $k, $embedding)
            YIELD node, score
            WHERE score >= $min_score
            MATCH (d:Document)-[:CONTAINS]->(node)
            OPTIONAL MATCH (node)-[:MENTIONS]->(e:Entity)
            RETURN
                node.id AS chunk_id,
                node.content AS content,
                node.index AS chunk_index,
                score,
                d.id AS doc_id,
                collect(DISTINCT e.name)[..5] AS entities
            ORDER BY score DESC
            """,
            {"k": k, "embedding": query_embedding, "min_score": min_score}
        )

        return [
            {
                "chunk_id": r["chunk_id"],
                "content": r["content"],
                "chunk_index": r["chunk_index"],
                "score": r["score"],
                "doc_id": r["doc_id"],
                "entities": r["entities"] or [],
                "source": "vector"
            }
            for r in results
        ]

    def query(
        self,
        question: str,
        k: int = 5,
        language: str = "auto"
    ) -> str:
        """
        Answer a question using vector search + LLM

        Args:
            question: The user's question
            k: Number of chunks to retrieve
            language: Response language (auto, ko, ja, en)

        Returns:
            Generated answer
        """
        # Search for relevant chunks
        results = self.search_similar(question, k=k)

        if not results:
            return "관련 정보를 찾을 수 없습니다." if language == "ko" else \
                   "関連情報が見つかりません。" if language == "ja" else \
                   "No relevant information found."

        # Build context
        context_parts = []
        for i, r in enumerate(results, 1):
            context_parts.append(f"[{i}] {r['content'][:500]}")
            if r["entities"]:
                context_parts.append(f"    Related: {', '.join(r['entities'])}")

        context = "\n\n".join(context_parts)

        # Language instruction
        lang_instruction = ""
        if language == "ko":
            lang_instruction = "Please respond in Korean."
        elif language == "ja":
            lang_instruction = "Please respond in Japanese."

        # Generate answer
        prompt = f"""Based on the context below, answer the question.
{lang_instruction}

Context:
{context}

Question: {question}

Answer:"""

        response = self.llm.invoke(prompt)
        answer = response.content

        # Clean thinking tokens
        if "</think>" in answer:
            answer = answer.split("</think>")[-1].strip()

        return answer

    def get_chunks_without_embeddings(self, limit: int = 100) -> List[Dict]:
        """
        Get chunks that don't have embeddings yet

        Args:
            limit: Maximum number of chunks to return

        Returns:
            List of chunks without embeddings
        """
        results = self.graph.query(
            """
            MATCH (c:Chunk)
            WHERE c.embedding IS NULL
            RETURN c.id AS id, c.content AS content
            LIMIT $limit
            """,
            {"limit": limit}
        )

        return [{"id": r["id"], "content": r["content"]} for r in results]

    def backfill_embeddings(self, batch_size: int = 50) -> int:
        """
        Add embeddings to all chunks that don't have them

        Args:
            batch_size: Number of chunks to process at once

        Returns:
            Total number of chunks processed
        """
        total_processed = 0

        while True:
            chunks = self.get_chunks_without_embeddings(limit=batch_size)

            if not chunks:
                break

            count = self.add_embeddings_batch(chunks)
            total_processed += count
            print(f"Processed {total_processed} chunks...")

        return total_processed

    def get_vector_stats(self) -> Dict[str, Any]:
        """
        Get statistics about vector embeddings

        Returns:
            Dictionary with stats
        """
        result = self.graph.query(
            """
            MATCH (c:Chunk)
            WITH count(c) AS total,
                 sum(CASE WHEN c.embedding IS NOT NULL THEN 1 ELSE 0 END) AS with_embedding
            RETURN total, with_embedding, total - with_embedding AS without_embedding
            """
        )

        if result:
            return {
                "total_chunks": result[0]["total"],
                "with_embedding": result[0]["with_embedding"],
                "without_embedding": result[0]["without_embedding"],
                "coverage": result[0]["with_embedding"] / max(result[0]["total"], 1) * 100
            }
        return {"total_chunks": 0, "with_embedding": 0, "without_embedding": 0, "coverage": 0}


def get_vector_rag() -> VectorRAG:
    """Get a configured VectorRAG instance"""
    return VectorRAG()


if __name__ == "__main__":
    # Test VectorRAG
    print("Testing VectorRAG...")

    vrag = VectorRAG()

    # Initialize vector index
    print("\n1. Initializing vector index...")
    vrag.init_vector_index()

    # Get stats
    print("\n2. Vector stats:")
    stats = vrag.get_vector_stats()
    for k, v in stats.items():
        print(f"   {k}: {v}")

    # Test search (if embeddings exist)
    if stats["with_embedding"] > 0:
        print("\n3. Testing vector search...")
        results = vrag.search_similar("What is GraphRAG?", k=3)
        for r in results:
            print(f"   Score: {r['score']:.4f} - {r['content'][:60]}...")

    print("\nVectorRAG test completed!")
