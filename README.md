# HybridRAG

A multilingual Hybrid RAG system combining Graph-based and Vector-based retrieval.

## Overview

HybridRAG combines knowledge graph technology with vector embeddings and LLM capabilities for enhanced document retrieval and question answering.

**Tech Stack:**
- **RAG LLM**: NVIDIA Nemotron Nano 9B v2 (via NIM Container, GPU 7)
- **Code LLM**: Mistral NeMo 12B (via vLLM, GPU 0)
- **Embeddings**: NVIDIA NV-EmbedQA-Mistral7B-v2 (via NIM Container, GPU 4,5)
- **Database**: Neo4j Graph Database with Vector Index
- **Framework**: LangChain/LangGraph
- **GPU**: NVIDIA A100-SXM4-40GB × 8

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
   +------------+-------------+-------------+------------+
   |            |             |             |            |
   v            v             v             v            |
+--+---+   +----+----+   +----+----+   +----+----+      |
|Vector|   | Graph   |   | Hybrid  |   |  Code   |      |
| RAG  |   |  RAG    |   |   RAG   |   | Agent   |      |
+--+---+   +----+----+   +----+----+   +----+----+      |
   |            |             |             |            |
   v            v             v             v            |
+--+--------+   +--+------+   +--+-----+   +--+--------+ |
|Neo4j      |   |Neo4j    |   | Both   |   |Mistral   | |
|Vector Idx |   |Graph    |   |Methods |   |NeMo 12B  | |
+-----------+   +---------+   +--------+   +----------+ |
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
| **Code** | Direct to Code LLM | Code generation, analysis, implementation |

#### Classification Methods

| Method | Accuracy | Speed | Description |
|--------|----------|-------|-------------|
| **Rule-based** | 100% | Fast | Keyword/pattern matching |
| **Embedding** | 82.9% | Medium | Cosine similarity with prototype vectors |
| **Hybrid** | 100% | Medium | Rule + Embedding combined (default) |

#### Multilingual Query Examples

| Language | Vector | Graph | Hybrid | Code |
|----------|--------|-------|--------|------|
| **English** | "What is OpenFrame?" | "Compare A and B" | "How to fix error?" | "Write a Python function" |
| **Korean** | "OpenFrame이란?" | "A와 B의 차이점" | "에러 해결 방법" | "Python 코드 작성해줘" |
| **Japanese** | "OpenFrameとは?" | "AとBの違いは?" | "エラーの対処方法" | "Pythonコードを書いて" |

#### Error Code Detection

Queries containing error codes are automatically detected and routed:

| Pattern | Example | Routing |
|---------|---------|---------|
| Uppercase with ERR/ERROR | `NVSM_ERR_SYSTEM_FWRITE` | HYBRID/GRAPH |
| Standard format | `OFM-1234` | HYBRID/GRAPH |
| **Numeric codes** | `-5212`, `-5211` | **HYBRID (direct search)** |

- **Error code + troubleshooting keywords** → HYBRID (semantic + entity search)
- **Error code only** → GRAPH (entity lookup)
- **Numeric error codes** → HYBRID with direct content search (highest priority)

**Numeric Error Code Example:**
```
Query: -5212에러코드의 의미와 해결방법

Strategy: [HYBRID/Combined]
Sources: 10

DSALC_ERR_DATASET_NOT_FOUND (-5212) 에러는 기존의 데이터세트가
찾히지 않는 경우에 발생합니다.

해결방법: 데이터세트를 생성한 후 다시 실행
```

#### Code Query Detection

Queries requesting code generation or analysis are automatically routed to the Code LLM (Mistral NeMo 12B):

| Language | Detection Keywords |
|----------|-------------------|
| **English** | `write code`, `sample code`, `implement`, `python function` |
| **Korean** | `코드 작성`, `샘플 코드`, `구현`, `코드 분석` |
| **Japanese** | `コードを書`, `関数を書`, `サンプルコード`, `実装` |

**Example:**
```
You: Python으로 피보나치 함수를 작성해줘

Strategy: [CODE/Mistral-NeMo]
Language: ko | Sources: 0 | Time: 2.15s

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
```

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
│       ├── graphrag.py          # Core HybridRAG class
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
- `/context` - Toggle conversation context mode
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
# Basic HybridRAG (Graph only)
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
| CODE_LLM_API_URL | Mistral NeMo endpoint | http://localhost:12802/v1/chat/completions |
| CODE_LLM_MODEL | Code LLM model name | mistralai/Mistral-Nemo-Instruct-2407 |
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
| 12802 | Mistral NeMo Code LLM (GPU 0) |
| 7474 | Neo4j HTTP |
| 7687 | Neo4j Bolt |

## Features

### Core Features
- **Hybrid RAG**: Automatic routing between Vector and Graph search
- **Code Agent**: Dedicated Code LLM (Mistral NeMo 12B) for code generation/analysis
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

### Comprehensive Query Detection

Automatically detects queries that require listing multiple items and adjusts retrieval accordingly:

| Setting | Normal Query | Comprehensive Query |
|---------|-------------|---------------------|
| **Results (k)** | 5 | 10 |
| **Content/chunk** | 500 chars | 800 chars |
| **Prompt** | Standard | "List ALL relevant items" |

**Detection Patterns:**

| Language | Patterns |
|----------|----------|
| **Korean** | `알려주세요`, `목록`, `종류`, `옵션`, `툴`, `도구` |
| **Japanese** | `教えてください`, `種類`, `一覧`, `ツール` |
| **English** | `all`, `list`, `what are`, `tools`, `options` |

**Example:**
```
Query: ofcobol의 전처리툴을 알려주세요.
→ Detected as comprehensive query
→ Returns: ofconv, ofcbpp, ofcbppf, osccblpp (all tools)
```

### Deep Analysis Mode

For queries requesting detailed, thorough analysis, the system provides extended search and comprehensive responses:

| Setting | Normal | Comprehensive | **Deep Analysis** |
|---------|--------|---------------|-------------------|
| **Results (k)** | 5 | 10 | **20** |
| **Content/chunk** | 500 chars | 800 chars | **1500 chars** |
| **Prompt** | Standard | List all items | **심층 분석 모드** |

**Detection Keywords:**

| Language | Patterns |
|----------|----------|
| **Korean** | `자세하게`, `상세하게`, `소상히`, `깊이`, `심층`, `철저히` |
| **Japanese** | `詳しく`, `詳細に`, `深く`, `徹底的に` |
| **English** | `deep think`, `ultra deep`, `in detail`, `thoroughly` |

**Example:**
```
Query: -5212 에러코드에 대해서 자세하게 설명해줘

Strategy: [HYBRID/Combined]
Sources: 20

→ Detailed response with:
  - Error code explanation (DSALC_ERR_DATASET_NOT_FOUND)
  - Cause analysis (4 detailed points)
  - Solutions (5 step-by-step methods)
  - Example scenarios
  - Related error codes (-5211, -5213)
  - Additional context and recommendations
```

### Topic Density Search

The system uses **Topic Density** to prioritize documents where the query's key concept is a central topic, not just mentioned:

```
Query: "ebcdic데이터셋을 sjis로 마이그레이션 방법"
                    ↓
         Key Concept Extraction (LLM + Pattern)
                    ↓
         Extracted: "마이그레이션"
                    ↓
         Topic Density Calculation per Document:
         ┌─────────────────────────────────────────┐
         │ Document              │ Density │ Rank │
         ├───────────────────────┼─────────┼──────┤
         │ Migration Guide       │ 68.80%  │  1   │ ← Prioritized
         │ General Doc A         │  5.20%  │  2   │
         │ General Doc B         │  2.10%  │  3   │
         └─────────────────────────────────────────┘
                    ↓
         Return chunks from high-density documents first
```

**Topic Density Formula:**
```
Topic Density = (Chunks containing concept) / (Total chunks in document)
```

**Key Concept Extraction:**

| Method | Description |
|--------|-------------|
| **LLM-based** | Extracts central action/process word from query |
| **Pattern Fallback** | Matches action words: 마이그레이션, 설치, 변환, 에러, etc. |

**Applied Strategies:**

| Strategy | Topic Density | Priority Order |
|----------|---------------|----------------|
| **VECTOR** | ✅ Applied | Topic Density → Vector Similarity |
| **HYBRID** | ✅ Applied | Error Code → Topic Density → Vector + Graph |
| **GRAPH** | ❌ N/A | Entity-based traversal |
| **CODE** | ❌ N/A | Direct Code LLM |

**Priority Order by Strategy:**

*VECTOR Strategy:*
1. **Topic Density Results** - Concept-central documents
2. **Vector Similarity Results** - Semantic embedding search

*HYBRID Strategy:*
1. **Error Code Results** - Exact match (highest priority)
2. **Topic Density Results** - Concept-central documents
3. **Vector + Graph Results** - Semantic + entity search

**Example Results:**

| Query | Key Concept | Strategy | Top Document | Topic Density |
|-------|-------------|----------|--------------|---------------|
| ebcdic→sjis 마이그레이션 | 마이그레이션 | VECTOR | Migration Guide | **68.80%** |
| OpenFrame 설치 방법 | 설치 | VECTOR | Installation Guide | **78.33%** |
| JCL 에러 해결 | 에러 | HYBRID | Error Reference | **93.50%** |

**Benefits:**
- Finds documents where the concept is **central**, not just mentioned
- Reduces noise from unrelated documents that happen to contain the keyword
- Improves answer relevance for topic-specific queries
- Works across both VECTOR and HYBRID strategies for comprehensive coverage

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
| Code | "write code", "코드 작성", "コードを書" |

## License

Proprietary
