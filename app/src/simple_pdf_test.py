#!/usr/bin/env python3
"""Simple PDF RAG Test - Process first 10 pages only"""
import os
import sys
import hashlib
from pypdf import PdfReader
from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Configuration
PDF_PATH = "/home/ofuser/workspaces/ijswork/graphrag/app/OF_Common_MVS_7.1_Error-Reference-Guide_v3.1.3_JP.pdf"
LLM_URL = "http://localhost:12800/v1"
LLM_MODEL = "nvidia/nvidia-nemotron-nano-9b-v2"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "graphrag2024"

def main():
    print("=" * 60)
    print("Simple PDF RAG Test")
    print("=" * 60)

    # Step 1: Load PDF (first 10 pages only)
    print("\n[1] Loading PDF...")
    reader = PdfReader(PDF_PATH)
    total_pages = len(reader.pages)
    pages_to_process = min(10, total_pages)
    print(f"    Total pages: {total_pages}, Processing: {pages_to_process}")

    all_text = []
    for i in range(pages_to_process):
        text = reader.pages[i].extract_text()
        if text:
            all_text.append(text)

    full_text = "\n".join(all_text)
    print(f"    Extracted {len(full_text)} characters")

    # Step 2: Initialize components
    print("\n[2] Initializing LLM and Neo4J...")
    llm = ChatOpenAI(
        base_url=LLM_URL,
        model=LLM_MODEL,
        api_key="not-needed",
        temperature=0.1
    )

    graph = Neo4jGraph(
        url=NEO4J_URI,
        username=NEO4J_USER,
        password=NEO4J_PASSWORD
    )

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=100
    )

    # Step 3: Chunk the text
    print("\n[3] Chunking text...")
    chunks = text_splitter.split_text(full_text)
    print(f"    Created {len(chunks)} chunks")

    # Step 4: Store in Neo4J (first 20 chunks only)
    print("\n[4] Storing in Neo4J...")
    doc_id = hashlib.md5(full_text[:100].encode()).hexdigest()[:12]

    graph.query(
        "MERGE (d:Document {id: $doc_id}) SET d.type = 'pdf', d.source = 'OF_MVS_Error_Guide'",
        {"doc_id": doc_id}
    )

    chunks_to_store = min(20, len(chunks))
    for i in range(chunks_to_store):
        chunk_id = f"{doc_id}_c{i}"
        graph.query(
            """
            MERGE (c:Chunk {id: $chunk_id})
            SET c.content = $content, c.index = $index
            WITH c
            MATCH (d:Document {id: $doc_id})
            MERGE (d)-[:CONTAINS]->(c)
            """,
            {"chunk_id": chunk_id, "content": chunks[i], "index": i, "doc_id": doc_id}
        )
    print(f"    Stored {chunks_to_store} chunks")

    # Step 5: Graph stats
    print("\n[5] Graph Statistics:")
    stats = graph.query("""
        MATCH (d:Document) WITH count(d) as docs
        MATCH (c:Chunk) WITH docs, count(c) as chunks
        RETURN docs, chunks
    """)
    if stats:
        print(f"    Documents: {stats[0]['docs']}")
        print(f"    Chunks: {stats[0]['chunks']}")

    # Step 6: Test RAG queries
    print("\n" + "=" * 60)
    print("[6] RAG Query Tests")
    print("=" * 60)

    def rag_query(question):
        # Get relevant chunks
        results = graph.query(
            """
            MATCH (c:Chunk)
            RETURN c.content AS content
            LIMIT 3
            """
        )

        context = "\n".join([r['content'][:400] for r in results if r['content']])

        prompt = f"""Based on this context from a Japanese MVS error reference guide, answer the question.
Respond in the same language as the question.

Context:
{context}

Question: {question}

Answer:"""

        response = llm.invoke(prompt)
        answer = response.content

        # Clean thinking tokens
        if "</think>" in answer:
            answer = answer.split("</think>")[-1].strip()

        return answer[:500]

    # Test queries
    queries = [
        "このドキュメントは何についてですか?",
        "What is this document about?",
        "エラーの種類を教えてください",
    ]

    for q in queries:
        print(f"\nQ: {q}")
        try:
            a = rag_query(q)
            print(f"A: {a}")
        except Exception as e:
            print(f"Error: {e}")
        print("-" * 40)

    print("\n" + "=" * 60)
    print("PDF RAG Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
