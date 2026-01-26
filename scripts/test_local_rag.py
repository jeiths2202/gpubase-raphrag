"""
Test Local RAG Service
Tests document embedding and search using Ollama + PostgreSQL.
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_local_rag():
    """Test the local RAG service with a sample document."""
    print("=" * 60)
    print("Local RAG Service Test (Ollama + PostgreSQL)")
    print("=" * 60)

    # Import services
    import asyncpg
    from app.api.core.config import api_settings
    from app.api.infrastructure.postgres.text_chunk_repository import PostgresTextChunkRepository
    from app.api.services.local_rag_service import LocalRAGService

    # Initialize PostgreSQL connection
    print("\n[Step 1] Connecting to PostgreSQL...")
    dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    chunk_repo = PostgresTextChunkRepository(pool)
    rag_service = LocalRAGService(text_chunk_repository=chunk_repo)
    print("[OK] Connected")

    # Sample document content (OpenFrame installation guide excerpt)
    sample_content = """
    OpenFrame Installation Guide

    1. System Requirements
    - Operating System: Linux (RHEL 7.x or higher recommended)
    - CPU: 4 cores or more
    - Memory: 16GB RAM minimum
    - Disk: 100GB available space

    2. Pre-installation Steps
    Before installing OpenFrame, ensure the following packages are installed:
    - gcc, gcc-c++
    - make, automake
    - libtool
    - ncurses-devel

    3. Installation Procedure
    Step 1: Download the OpenFrame installation package from the official repository.
    Step 2: Extract the package to /opt/tmaxapp directory.
    Step 3: Run the installation script: ./install.sh
    Step 4: Configure the environment variables in ~/.bash_profile

    4. Post-installation Configuration
    After installation, configure the following:
    - Set OPENFRAME_HOME environment variable
    - Configure the database connection in oframe.conf
    - Set up the batch scheduler (optional)
    - Configure the online transaction processor

    5. Verification
    To verify the installation:
    - Run: ofcheck -v
    - Check the log files in $OPENFRAME_HOME/log
    - Test the sample transaction

    MFS (Message Format Service) Guide

    MFS is used for screen formatting in OpenFrame OSI.
    Key concepts:
    - MID (Message Input Descriptor): Defines input message format
    - MOD (Message Output Descriptor): Defines output message format
    - DIF (Device Input Format): Device-specific input
    - DOF (Device Output Format): Device-specific output

    MFS commands:
    - mfsgen: Generate MFS definitions
    - mfslist: List MFS entries
    - mfsdump: Dump MFS data
    """

    # Embed document
    print("\n[Step 2] Embedding document...")
    document_id = "test_doc_001"

    result = await rag_service.embed_document(
        document_id=document_id,
        text_content=sample_content,
        metadata={"source": "test", "language": "en"}
    )

    print(f"[OK] Embedded document:")
    print(f"     Total chunks: {result['total_chunks']}")
    print(f"     Embedded chunks: {result['embedded_chunks']}")
    print(f"     Saved chunks: {result['saved_chunks']}")
    print(f"     Embedding dimension: {result['embedding_dimension']}")

    # Test search
    print("\n[Step 3] Testing search...")
    test_queries = [
        "How to install OpenFrame?",
        "What are the system requirements?",
        "MFS message format",
        "database configuration"
    ]

    for query in test_queries:
        print(f"\n  Query: {query}")
        results = await rag_service.search(query, limit=3, min_similarity=0.2)

        if results:
            print(f"  Found {len(results)} results:")
            for r in results[:2]:
                content_preview = r['content'][:80].replace('\n', ' ')
                print(f"    - [{r['similarity']:.1%}] {content_preview}...")
        else:
            print("  No results found")

    # Get stats
    print("\n[Step 4] Getting stats...")
    stats = await rag_service.get_stats()
    print(f"  Total chunks: {stats.get('total_chunks', 0)}")
    print(f"  Embedded chunks: {stats.get('embedded_chunks', 0)}")
    print(f"  Total documents: {stats.get('total_documents', 0)}")
    print(f"  Embedding model: {stats.get('embedding_model', 'unknown')}")

    print("\n" + "=" * 60)
    print("[OK] Local RAG test completed successfully!")
    print("=" * 60)

    # Close pool
    await pool.close()


if __name__ == "__main__":
    asyncio.run(test_local_rag())
