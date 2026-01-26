"""
Test script for Multimodal RAG PDF image processing.
Extracts images from PDF, generates descriptions via Ollama bakllava,
and stores embeddings in PostgreSQL.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path


async def test_pdf_processing():
    """Test PDF image extraction and processing."""

    # Import services
    from app.api.services.multimodal_rag_service import MultimodalRAGService
    from app.api.infrastructure.postgres.image_embedding_repository import PostgresImageEmbeddingRepository
    from app.api.core.config import get_api_settings
    import asyncpg

    settings = get_api_settings()

    # Setup database connection
    dsn = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    print("Connecting to PostgreSQL...")

    try:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        print("[OK] Database connected")
    except Exception as e:
        print(f"[FAIL] Database connection failed: {e}")
        print("\nMake sure PostgreSQL is running and the migration has been applied.")
        return

    # Initialize repository and service
    repository = PostgresImageEmbeddingRepository(pool)
    service = MultimodalRAGService(image_repository=repository)

    # PDF file path
    pdf_path = Path("OF_Batch_MVS_7.1_Batch-Guide_v3.1.3_kr.pdf")
    document_id = "test-of-batch-mvs-guide"

    if not pdf_path.exists():
        print(f"[FAIL] PDF not found: {pdf_path}")
        return

    print(f"\nProcessing PDF: {pdf_path}")
    print(f"Document ID: {document_id}")

    try:
        # Process PDF images
        result = await service.process_pdf_images(
            pdf_path=pdf_path,
            document_id=document_id,
            generate_descriptions=True,
            generate_embeddings=True,
        )

        print(f"\n[OK] Processing complete!")
        print(f"  Images extracted: {result.get('images_extracted', 0)}")
        print(f"  Images processed: {result.get('images_processed', 0)}")
        print(f"  Embeddings generated: {result.get('embeddings_generated', 0)}")

        if result.get('errors'):
            print(f"  Errors: {len(result['errors'])}")
            for err in result['errors'][:3]:
                print(f"    - {err}")

        # Test search
        print("\nTesting image search...")
        search_results = await service.search_images(
            query="diagram",
            limit=5,
            include_data=False,
        )

        print(f"  Found {len(search_results)} images for query 'diagram'")
        for i, img in enumerate(search_results):
            print(f"  {i+1}. {img.get('image_id', 'N/A')[:30]}... (similarity: {img.get('similarity', 0):.2f})")

        # List document images
        print("\nDocument images:")
        doc_images = await service.get_document_images(document_id)
        print(f"  Total images for document: {len(doc_images)}")
        for i, img in enumerate(doc_images[:5]):
            desc = img.get('description', 'No description')[:50]
            print(f"  {i+1}. Page {img.get('page_number', 'N/A')}: {desc}...")

    except Exception as e:
        print(f"\n[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await pool.close()
        print("\n[OK] Database connection closed")


if __name__ == "__main__":
    print("=" * 60)
    print("Multimodal RAG PDF Processing Test")
    print("=" * 60)
    asyncio.run(test_pdf_processing())
