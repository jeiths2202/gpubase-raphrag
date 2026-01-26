"""
PDF Document RAG Test - Japanese Error Reference Guide
"""
import os
import sys
from typing import List, Dict, Any
from pypdf import PdfReader
from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph
from langchain_text_splitters import RecursiveCharacterTextSplitter
import hashlib

class PDFGraphRAG:
    def __init__(
        self,
        llm_url: str = "http://localhost:12800/v1",
        llm_model: str = "nvidia/nvidia-nemotron-nano-9b-v2",
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "graphrag2024"
    ):
        print("Initializing PDFGraphRAG...")
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
            chunk_size=800,
            chunk_overlap=150,
            separators=["\n\n", "\n", "。", ".", " ", ""]
        )

        self._init_schema()
        print("Initialization complete.")

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
                pass

    def load_pdf(self, pdf_path: str) -> str:
        """Load PDF and extract text from all pages"""
        print(f"\nLoading PDF: {pdf_path}")
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        print(f"  Total pages: {total_pages}")

        all_text = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                all_text.append(text)
            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{total_pages} pages...")

        full_text = "\n".join(all_text)
        print(f"  Extracted {len(full_text)} characters")
        return full_text

    def add_document(self, content: str, metadata: Dict[str, Any] = None) -> str:
        """Add document to graph with chunking and entity extraction"""
        doc_id = hashlib.md5(content[:200].encode()).hexdigest()[:12]

        # Store document node
        self.graph.query(
            "MERGE (d:Document {id: $doc_id}) SET d.content = $content, d.type = 'pdf'",
            {"doc_id": doc_id, "content": content[:1000]}
        )

        # Split into chunks
        chunks = self.text_splitter.split_text(content)
        print(f"\n[Chunking] Created {len(chunks)} chunks")

        # Process each chunk
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"

            # Store chunk
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

            # Extract entities (every 5th chunk to save time)
            if i % 5 == 0:
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

            if (i + 1) % 20 == 0:
                print(f"  Processed {i + 1}/{len(chunks)} chunks...")

        print(f"  Document added: {doc_id}")
        return doc_id

    def _extract_entities(self, text: str) -> List[str]:
        """Extract entities using LLM"""
        prompt = f"""Extract key entities (error codes, system names, technical terms, procedures) from this Japanese technical document text.
Return only a comma-separated list of entities. Focus on error codes (like MVS-xxxx) and technical terms.

Text: {text[:600]}

Entities:"""

        try:
            response = self.llm.invoke(prompt)
            entities_str = response.content.strip()
            # Clean up the response
            if "<think>" in entities_str:
                entities_str = entities_str.split("</think>")[-1].strip()
            entities = [e.strip() for e in entities_str.split(",") if e.strip() and len(e.strip()) < 50]
            return entities[:8]
        except Exception as e:
            print(f"Entity extraction error: {e}")
            return []

    def query(self, question: str) -> str:
        """Query the graph and generate answer"""
        # Search for relevant chunks
        search_result = self.graph.query(
            """
            MATCH (c:Chunk)
            WHERE c.content CONTAINS $keyword OR c.content CONTAINS $keyword2
            OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
            RETURN c.content AS chunk, collect(DISTINCT e.name) AS entities
            LIMIT 3
            """,
            {"keyword": question[:20], "keyword2": question.split()[0] if question.split() else ""}
        )

        # If no keyword match, get some chunks
        if not search_result:
            search_result = self.graph.query(
                """
                MATCH (c:Chunk)
                OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
                RETURN c.content AS chunk, collect(DISTINCT e.name) AS entities
                LIMIT 3
                """
            )

        context_parts = []
        for result in search_result:
            if result['chunk']:
                context_parts.append(f"Content: {result['chunk'][:500]}")
                if result['entities']:
                    context_parts.append(f"Related entities: {', '.join(result['entities'][:5])}")

        context = "\n".join(context_parts) if context_parts else "No relevant information found."

        prompt = f"""Based on the following context from a Japanese technical error reference guide, answer the question.
If the question is in Japanese, respond in Japanese. If in English, respond in English.

Context:
{context}

Question: {question}

Answer:"""

        response = self.llm.invoke(prompt)
        answer = response.content

        # Clean thinking tokens if present
        if "<think>" in answer and "</think>" in answer:
            answer = answer.split("</think>")[-1].strip()

        return answer

    def get_stats(self) -> Dict[str, int]:
        """Get graph statistics"""
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
    print("=" * 60)
    print("PDF GraphRAG Test - Japanese Error Reference Guide")
    print("=" * 60)

    # Initialize RAG
    rag = PDFGraphRAG()

    # PDF path
    pdf_path = "/home/ofuser/workspaces/ijswork/graphrag/app/OF_Common_MVS_7.1_Error-Reference-Guide_v3.1.3_JP.pdf"

    # Load and process PDF
    print("\n[Phase 1] Loading PDF Document...")
    pdf_text = rag.load_pdf(pdf_path)

    print("\n[Phase 2] Adding to Graph (Chunking + Entity Extraction)...")
    doc_id = rag.add_document(pdf_text, {"source": "OF_Common_MVS_Error_Guide", "language": "ja"})

    print("\n[Phase 3] Graph Statistics:")
    stats = rag.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 60)
    print("[Phase 4] RAG Query Tests")
    print("=" * 60)

    # Test queries
    test_queries = [
        "エラーコードについて教えてください",
        "MVSシステムのエラー対処方法は?",
        "What types of errors are documented?",
        "このドキュメントの目的は何ですか?",
    ]

    for q in test_queries:
        print(f"\nQ: {q}")
        answer = rag.query(q)
        # Truncate long answers
        if len(answer) > 400:
            answer = answer[:400] + "..."
        print(f"A: {answer}")
        print("-" * 40)

    print("\n" + "=" * 60)
    print("PDF GraphRAG Test Completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
