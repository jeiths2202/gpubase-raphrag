"""
GraphRAG System using Nemotron NIM + Neo4J + LangChain
Supports both Graph RAG and Vector RAG (Hybrid mode)
"""
import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.graphs import Neo4jGraph
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# Optional: Import embedding service for hybrid mode
try:
    from embeddings import NeMoEmbeddingService
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

class GraphRAG:
    def __init__(
        self,
        llm_url: str = "http://localhost:12800/v1",
        llm_model: str = "nvidia/nvidia-nemotron-nano-9b-v2",
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "graphrag2024",
        enable_embeddings: bool = False,
        embedding_url: str = "http://localhost:12801/v1"
    ):
        self.llm = ChatOpenAI(
            base_url=llm_url,
            model=llm_model,
            api_key="not-needed",
            temperature=0.1
        )

        self.graph = Neo4jGraph(
            url=neo4j_uri,
            username=neo4j_user,
            password=neo4j_password
        )

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )

        # Optional embedding service for hybrid mode
        self.embedding_service = None
        self.enable_embeddings = enable_embeddings
        if enable_embeddings and EMBEDDINGS_AVAILABLE:
            try:
                self.embedding_service = NeMoEmbeddingService(base_url=embedding_url)
                print("Embedding service initialized")
            except Exception as e:
                print(f"Embedding service not available: {e}")
                self.enable_embeddings = False

        self._init_schema()

    def _init_schema(self):
        constraints = [
            "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE"
        ]
        for constraint in constraints:
            try:
                self.graph.query(constraint)
            except Exception as e:
                print(f"Schema warning: {e}")

        # Create vector index if embeddings are enabled
        if self.enable_embeddings:
            try:
                self.graph.query("""
                    CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
                    FOR (c:Chunk) ON (c.embedding)
                    OPTIONS {
                        indexConfig: {
                            `vector.dimensions`: 4096,
                            `vector.similarity_function`: 'cosine'
                        }
                    }
                """)
                print("Vector index created/verified")
            except Exception as e:
                print(f"Vector index warning: {e}")

    def add_document(self, content: str, metadata: Dict[str, Any] = None) -> str:
        import hashlib
        doc_id = hashlib.md5(content[:100].encode()).hexdigest()[:12]

        self.graph.query(
            "MERGE (d:Document {id: $doc_id}) SET d.content = $content",
            {"doc_id": doc_id, "content": content[:500]}
        )

        chunks = self.text_splitter.split_text(content)

        # Generate embeddings in batch if enabled
        embeddings = None
        if self.enable_embeddings and self.embedding_service:
            try:
                embeddings = self.embedding_service.embed_batch(chunks, input_type="passage")
            except Exception as e:
                print(f"Batch embedding error: {e}")

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"

            # Include embedding if available
            if embeddings and i < len(embeddings):
                self.graph.query(
                    """
                    MERGE (c:Chunk {id: $chunk_id})
                    SET c.content = $content, c.index = $index, c.embedding = $embedding
                    WITH c
                    MATCH (d:Document {id: $doc_id})
                    MERGE (d)-[:CONTAINS]->(c)
                    """,
                    {"chunk_id": chunk_id, "content": chunk, "index": i,
                     "doc_id": doc_id, "embedding": embeddings[i]}
                )
            else:
                self.graph.query(
                    """
                    MERGE (c:Chunk {id: $chunk_id})
                    SET c.content = $content, c.index = $index
                    WITH c
                    MATCH (d:Document {id: $doc_id})
                    MERGE (d)-[:CONTAINS]->(c)
                    """,
                    {"chunk_id": chunk_id, "content": chunk, "index": i, "doc_id": doc_id}
                )

            entities = self._extract_entities(chunk)

            for entity in entities:
                self.graph.query(
                    """
                    MERGE (e:Entity {name: $entity_name})
                    WITH e
                    MATCH (c:Chunk {id: $chunk_id})
                    MERGE (c)-[:MENTIONS]->(e)
                    """,
                    {"entity_name": entity, "chunk_id": chunk_id}
                )

        return doc_id

    def _extract_entities(self, text: str) -> List[str]:
        prompt = f"""Extract key entities (people, organizations, locations, concepts) from the text.
Return only a comma-separated list of entities.

Text: {text[:500]}

Entities:"""

        try:
            response = self.llm.invoke(prompt)
            entities_str = response.content.strip()
            entities = [e.strip() for e in entities_str.split(",") if e.strip()]
            return entities[:10]
        except Exception as e:
            print(f"Entity extraction error: {e}")
            return []

    def query(self, question: str, language: str = "auto") -> str:
        search_result = self.graph.query(
            """
            MATCH (c:Chunk)
            OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
            RETURN c.content AS chunk, collect(DISTINCT e.name) AS entities
            LIMIT 5
            """
        )

        context_parts = []
        for result in search_result:
            context_parts.append(f"Content: {result['chunk']}")
            if result['entities']:
                context_parts.append(f"Entities: {', '.join(result['entities'])}")

        context = "\n".join(context_parts) if context_parts else "No information found."

        lang_instruction = ""
        if language == "ko":
            lang_instruction = "Please respond in Korean."
        elif language == "ja":
            lang_instruction = "Please respond in Japanese."

        prompt = f"""Based on the context, answer the question.
{lang_instruction}

Context:
{context}

Question: {question}

Answer:"""

        response = self.llm.invoke(prompt)
        return response.content

    def get_graph_stats(self) -> Dict[str, int]:
        result = self.graph.query(
            """
            MATCH (d:Document) WITH count(d) as docs
            MATCH (c:Chunk) WITH docs, count(c) as chunks
            MATCH (e:Entity) WITH docs, chunks, count(e) as entities
            MATCH ()-[r]->() WITH docs, chunks, entities, count(r) as rels
            RETURN docs, chunks, entities, rels
            """
        )

        if result:
            return {
                "documents": result[0]["docs"],
                "chunks": result[0]["chunks"],
                "entities": result[0]["entities"],
                "relationships": result[0]["rels"]
            }
        return {"documents": 0, "chunks": 0, "entities": 0, "relationships": 0}


def main():
    print("Initializing GraphRAG...")
    rag = GraphRAG()

    test_docs = [
        """NVIDIA is a technology company founded by Jensen Huang in 1993.
        The company is headquartered in Santa Clara, California.
        NVIDIA is known for its graphics processing units (GPUs) and AI technologies.""",
        """Neo4j is a graph database management system developed by Neo4j, Inc.
        It is implemented in Java and uses the Cypher Query Language for data access.
        Neo4j is used for applications including fraud detection and recommendation engines."""
    ]

    print("\nAdding test documents...")
    for i, doc in enumerate(test_docs):
        doc_id = rag.add_document(doc)
        print(f"  Added document {i+1}: {doc_id}")

    print("\nGraph Statistics:")
    stats = rag.get_graph_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\nTesting queries...")

    q1 = "Who founded NVIDIA?"
    print(f"\nQ: {q1}")
    print(f"A: {rag.query(q1)}")

    print("\nGraphRAG test completed!")


if __name__ == "__main__":
    main()
