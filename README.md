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

The system uses a **hybrid classification approach** combining rule-based keyword matching with embedding-based semantic similarity for intelligent query routing.

| Query Type | Strategy | Use Case |
|------------|----------|----------|
| **Vector** | Semantic similarity search | Definitions, explanations, methods |
| **Graph** | Entity-based graph traversal | Comparisons, lists, relationships |
| **Hybrid** | Both strategies combined | Error troubleshooting, detailed analysis |

#### Classification Methods

| Method | Accuracy | Speed | Description |
|--------|----------|-------|-------------|
| **Rule-based** | 100% | Fast | Keyword/pattern matching |
| **Embedding** | 82.9% | Medium | Cosine similarity with prototype vectors |
| **Hybrid** | 100% | Medium | Rule + Embedding combined (default) |

#### Multilingual Query Examples

| Language | Vector | Graph | Hybrid |
|----------|--------|-------|--------|
| **English** | "What is OpenFrame?" | "Compare A and B" | "How to fix error?" |
| **Korean** | "OpenFrame이란?" | "A와 B의 차이점" | "에러 해결 방법" |
| **Japanese** | "OpenFrameとは?" | "AとBの違いは?" | "エラーの対処方法" |

#### Error Code Detection

Queries containing error codes (e.g., `NVSM_ERR_SYSTEM_FWRITE`, `OFM-1234`) are automatically detected and routed:
- **Error code + troubleshooting keywords** → HYBRID (semantic + entity search)
- **Error code only** → GRAPH (entity lookup)

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
│       ├── chat_rag.py          # Interactive chat interface
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

### 2. Run Interactive Chat

```bash
cd app/src
python chat_rag.py
```

**Chat Commands:**
- `/help` - Show help
- `/stats` - Show database statistics
- `/history` - Show chat history
- `/clear` - Clear history
- `/quit` - Exit

**Example Session:**
```
You: NVSM_ERR_SYSTEM_FWRITE 에러의 조치방법에 대해서 알려주세요

Strategy: [HYBRID/Combined]
Language: ko | Sources: 5 | Time: 3.66s

NVSM_ERR_SYSTEM_FWRITE(-922) 에러가 발생한 경우, 스풀에 출력된
시스템 함수 호출 관련 에러 메시지를 확인하여 구체적인 원인을
파악해야 합니다.
```

### 3. Run Programmatic RAG

```bash
# Basic GraphRAG (Graph only)
python app/src/graphrag.py

# Hybrid RAG (Vector + Graph)
python app/src/hybrid_rag.py
```

### 4. Test PDF Processing

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

### Core Features
- **Hybrid RAG**: Automatic routing between Vector and Graph search
- **Interactive Chat**: Command-line chatbot interface with UTF-8 support
- **Vector Search**: Neo4j vector index with 4096-dimensional embeddings
- **Graph Search**: Entity-based relationship traversal
- **Batch Processing**: Efficient document ingestion with parallel processing

### Multilingual Support
- **Languages**: Japanese (日本語), Korean (한국어), English
- **Query Detection**: Automatic language detection and response
- **Keyword Patterns**: Language-specific routing patterns
- **Error Code Handling**: Universal error code detection across languages

### Query Router Features
- **35 Test Cases**: Comprehensive test coverage (EN/KO/JP)
- **100% Accuracy**: All query types correctly classified
- **Pattern Matching**: Regex-based pattern detection for each language
- **Error Code Detection**: Automatic detection of patterns like `ERR_`, `ERROR`, `FAIL`

### Embedding Classifier

The embedding classifier uses **prototype vectors** for probabilistic query classification:

```
Query → Embed → Cosine Similarity → Softmax → Probabilities
                    ↓
         Compare with prototypes:
         - Vector: 14 multilingual examples
         - Graph: 14 multilingual examples
         - Hybrid: 14 multilingual examples
```

**How it works:**
1. Generate 4096-dimensional embeddings for prototype queries (EN/KO/JP)
2. Compute mean vector for each query type (vector, graph, hybrid)
3. For new queries, compute cosine similarity with each prototype
4. Apply softmax to get classification probabilities

**Caching:**

Prototype embeddings are cached to avoid regeneration on startup:

| Feature | Description |
|---------|-------------|
| **Cache Location** | `app/src/.cache/prototype_embeddings.json` |
| **Cache Size** | ~353KB (3 × 4096d vectors) |
| **Invalidation** | Automatic when prototype queries change |
| **Performance** | ~0.1s (cached) vs ~3-5s (uncached) |

```bash
# Cache is automatically created on first run
# To force regeneration, delete the cache:
rm -rf app/src/.cache/
```

**Test the classifier:**
```bash
cd app/src

# Rule-based only
python query_router.py

# Embedding classifier only
python query_router.py -e

# Compare all methods
python query_router.py -c
```

**Example output:**
```
Q: NVSM_ERR_SYSTEM_FWRITE 에러의 조치방법
   Expected: hybrid
   Rule: hybrid ✓ | Emb: hybrid ✓ | Hybrid: hybrid ✓
```

### Supported Query Patterns

| Pattern Type | Keywords (EN/KO/JP) |
|--------------|---------------------|
| Definition | "what is", "이란", "とは" |
| Method | "how to", "방법", "方法" |
| Comparison | "compare", "비교", "比較" |
| List | "all", "모든", "すべて" |
| Troubleshoot | "fix", "해결", "解決" |

## License

Proprietary
