"""
Embed PDF Documents Locally
Uses Ollama + PostgreSQL for embedding (no Neo4j/GPU required).
"""
import asyncio
import sys
import os
import fitz  # PyMuPDF

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF using PyMuPDF."""
    doc = fitz.open(pdf_path)
    text_parts = []

    for page_num, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            text_parts.append(f"[Page {page_num + 1}]\n{text}")

    doc.close()
    return "\n\n".join(text_parts)


async def embed_pdf(pdf_path: str, rag_service, document_id: str = None):
    """Embed a single PDF file."""
    filename = os.path.basename(pdf_path)
    doc_id = document_id or f"doc_{filename.replace('.', '_')}"

    print(f"\n  Processing: {filename}")

    # Extract text
    print("    Extracting text...")
    text_content = extract_text_from_pdf(pdf_path)
    print(f"    Extracted {len(text_content)} characters")

    if len(text_content) < 100:
        print("    [SKIP] Not enough text content")
        return None

    # Embed
    print("    Embedding chunks...")
    result = await rag_service.embed_document(
        document_id=doc_id,
        text_content=text_content,
        metadata={"filename": filename, "source": "pdf"}
    )

    print(f"    [OK] {result['saved_chunks']} chunks embedded")
    return result


async def main():
    """Main function to embed PDF documents."""
    print("=" * 60)
    print("PDF Document Embedding (Ollama + PostgreSQL)")
    print("=" * 60)

    # PDF files to embed
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_files = [
        os.path.join(project_root, "OF_Base_7.1_Installation-Guide_v3.1.2_kr.pdf"),
        os.path.join(project_root, "OF_OSI_7.2_MFS-Reference-Guide_v3.1.2_kr.pdf"),
    ]

    # Check which files exist
    existing_files = [f for f in pdf_files if os.path.exists(f)]
    if not existing_files:
        print("[ERROR] No PDF files found")
        return

    print(f"\nFound {len(existing_files)} PDF file(s) to embed")

    # Initialize services
    print("\n[Step 1] Initializing services...")
    import asyncpg
    from app.api.core.config import api_settings
    from app.api.infrastructure.postgres.text_chunk_repository import PostgresTextChunkRepository
    from app.api.services.local_rag_service import LocalRAGService

    dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    chunk_repo = PostgresTextChunkRepository(pool)
    rag_service = LocalRAGService(text_chunk_repository=chunk_repo)
    print("[OK] Services initialized")

    # Embed each PDF
    print("\n[Step 2] Embedding documents...")
    total_chunks = 0
    successful = 0

    for pdf_path in existing_files:
        try:
            result = await embed_pdf(pdf_path, rag_service)
            if result:
                total_chunks += result['saved_chunks']
                successful += 1
        except Exception as e:
            print(f"    [ERROR] Failed: {e}")

    # Get final stats
    print("\n[Step 3] Final statistics...")
    stats = await rag_service.get_stats()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  PDFs processed: {successful}/{len(existing_files)}")
    print(f"  Total chunks: {stats.get('total_chunks', 0)}")
    print(f"  Embedded chunks: {stats.get('embedded_chunks', 0)}")
    print(f"  Total documents: {stats.get('total_documents', 0)}")
    print(f"  Embedding model: {stats.get('embedding_model', 'unknown')}")
    print("=" * 60)

    # Test search
    print("\n[Step 4] Testing search...")
    test_queries = [
        "OpenFrame installation",
        "MFS message format",
        "system requirements"
    ]

    for query in test_queries:
        results = await rag_service.search(query, limit=2, min_similarity=0.3)
        print(f"\n  Query: {query}")
        if results:
            for r in results:
                # Handle Unicode for Windows console
                preview = r['content'][:60].replace('\n', ' ')
                preview_safe = preview.encode('ascii', 'replace').decode('ascii')
                print(f"    - [{r['similarity']:.1%}] {preview_safe}...")
        else:
            print("    No results")

    print("\n[OK] Embedding complete! You can now test RAG at http://localhost:3000/agent")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
