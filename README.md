# GraphRAG

A multilingual Hybrid RAG system combining Graph-based and Vector-based retrieval.

## Overview

GraphRAG combines knowledge graph technology with vector embeddings and LLM capabilities for enhanced document retrieval and question answering.

**Tech Stack:**
- **LLM**: NVIDIA Nemotron Nano 9B v2 (via NIM Container, GPU 7)
- **Embeddings**: NVIDIA NV-EmbedQA-Mistral7B-v2 (via NIM Container, GPU 4,5)
- **Database**: Neo4j Graph Database with Vector Index
- **Framework**: LangChain/LangGraph
- **GPU**: NVIDIA A100-SXM4-40GB

## Architecture

```
                     +------------------+
                     |   User Query     |
                     +--------+---------+
                              |
                     +--------v---------+
                     |  Query Router    |
                     +--------+---------+
                              |
        +---------------------+---------------------+
        |                     |                     |
        v                     v                     v
+-------+-------+    +--------+--------+   +--------+--------+
| Vector RAG    |    |   Graph RAG     |   |  Hybrid RAG     |
| (Semantic)    |    |  (Relational)   |   |   (Combined)    |
+-------+-------+    +--------+--------+   +--------+--------+
        |                     |                     |
        v                     v                     v
+-------+-------+    +--------+--------+   +--------+--------+
| Neo4j Vector  |    | Neo4j Graph     |   |  Both           |
| Index Search  |    | Traversal       |   |  Approaches     |
+---------------+    +-----------------+   +-----------------+
```

### Graph Schema
```
Document --CONTAINS--> Chunk --MENTIONS--> Entity
                         |
                         +-- embedding: LIST<FLOAT> (4096 dimensions)
```

### Query Routing Logic

| Query Type | Example | Strategy |
|------------|---------|----------|
| Vector | "What is OFCobol?", "Explain error code" | Semantic similarity search |
| Graph | "Document relationships", "List all errors" | Graph traversal |
| Hybrid | "Compare products", "Detailed context" | Both strategies combined |

## Project Structure

```
graphrag/
├── app/
│   ├── requirements.txt
│   ├── docs/                    # PDF documents (JP/KR/EN)
│   └── src/
│       ├── config.py            # Configuration management
│       ├── embeddings.py        # NeMo Embedding service
│       ├── query_router.py      # Query classification
│       ├── vector_rag.py        # Vector-based RAG
│       ├── hybrid_rag.py        # Hybrid RAG orchestrator
│       ├── graphrag.py          # Core GraphRAG class
│       ├── pdf_rag_test.py      # PDF processing test
│       ├── simple_pdf_test.py   # Quick PDF test
│       ├── rag_qa.py            # QA module
│       └── batch_upload.py      # Batch upload utility
├── docker/
│   ├── docker-compose.yml       # Container orchestration
│   └── .env                     # Environment configuration
└── neo4j/                       # Neo4j data directory
```

## Installation

```bash
pip install -r app/requirements.txt
```

## Quick Start

### 1. Start Services (Docker)

```bash
cd docker
docker-compose up -d
```

### 2. Run GraphRAG

```bash
# Basic GraphRAG (Graph only)
python app/src/graphrag.py

# Hybrid RAG (Vector + Graph)
python app/src/hybrid_rag.py
```

### 3. Test PDF Processing

```bash
python app/src/pdf_rag_test.py
```

## Configuration

Environment variables (docker/.env):

| Variable | Description | Default |
|----------|-------------|---------|
| LLM_API_URL | Nemotron NIM endpoint | http://localhost:12800/v1/chat/completions |
| LLM_MODEL | LLM model name | nvidia/nvidia-nemotron-nano-9b-v2 |
| EMBEDDING_API_URL | Embedding NIM endpoint | http://localhost:12801/v1 |
| EMBEDDING_MODEL | Embedding model name | nvidia/nv-embedqa-mistral-7b-v2 |
| NEO4J_URI | Neo4j Bolt connection | bolt://localhost:7687 |
| NEO4J_USER | Neo4j username | neo4j |
| NEO4J_PASSWORD | Neo4j password | - |
| NGC_API_KEY | NVIDIA NGC API key | - |

## Port Allocations

| Port | Service |
|------|---------|
| 12800 | Nemotron NIM LLM API (GPU 7) |
| 12801 | NeMo Embedding NIM API (GPU 4,5) |
| 7474 | Neo4j HTTP |
| 7687 | Neo4j Bolt |

## Features

- **Hybrid RAG**: Automatic routing between Vector and Graph search
- **Multilingual**: Japanese, Korean, English support
- **Vector Search**: Neo4j vector index with cosine similarity
- **Graph Search**: Entity-based relationship traversal
- **Query Classification**: LLM-based query routing
- **Batch Processing**: Efficient document ingestion with embeddings

## License

Proprietary
