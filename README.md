# GraphRAG

A multilingual Graph-based Retrieval-Augmented Generation system.

## Overview

GraphRAG combines knowledge graph technology with LLM capabilities for enhanced document retrieval and question answering.

**Tech Stack:**
- **LLM**: NVIDIA Nemotron Nano 9B v2 (via NIM Container)
- **Database**: Neo4j Graph Database
- **Framework**: LangChain/LangGraph
- **GPU**: NVIDIA A100-SXM4-40GB

## Architecture

```
Document --CONTAINS--> Chunk --MENTIONS--> Entity
```

### Data Pipeline
1. Text extraction (pypdf for PDFs)
2. Recursive text splitting (1000 chars, 200 overlap)
3. Document/Chunk node creation in Neo4j
4. LLM-based entity extraction
5. Entity node creation with MENTIONS relationships
6. Query via graph search + context retrieval + LLM answer generation

## Project Structure

```
graphrag/
├── app/
│   ├── requirements.txt
│   ├── docs/                    # PDF documents (JP/KR/EN)
│   └── src/
│       ├── graphrag.py          # Core GraphRAG class
│       ├── pdf_rag_test.py      # PDF processing test
│       ├── simple_pdf_test.py   # Quick PDF test (10 pages)
│       ├── rag_qa.py            # QA module
│       └── batch_upload.py      # Batch upload utility
├── docker/
│   └── .env                     # Environment configuration
└── neo4j/                       # Neo4j data directory
```

## Installation

```bash
pip install -r app/requirements.txt
```

## Usage

```bash
# Run core GraphRAG test
python app/src/graphrag.py

# Run full PDF processing test
python app/src/pdf_rag_test.py

# Run quick PDF test (10 pages max)
python app/src/simple_pdf_test.py
```

## Configuration

Environment variables (docker/.env):

| Variable | Description | Default |
|----------|-------------|---------|
| LLM_API_URL | Nemotron NIM endpoint | http://localhost:12800/v1/chat/completions |
| LLM_MODEL | LLM model name | nvidia/nvidia-nemotron-nano-9b-v2 |
| NEO4J_URI | Neo4j Bolt connection | bolt://localhost:7687 |
| NEO4J_USER | Neo4j username | neo4j |
| NEO4J_PASSWORD | Neo4j password | - |
| NGC_API_KEY | NVIDIA NGC API key | - |

## Port Allocations

| Port | Service |
|------|---------|
| 12800 | Nemotron NIM LLM API |
| 7474 | Neo4j HTTP |
| 7687 | Neo4j Bolt |
| 8080 | GraphRAG API (planned) |

## Features

- Multilingual support (Japanese, Korean, English)
- Graph-based context retrieval
- LLM-based entity extraction
- Optimized chunking with overlap

## License

Proprietary
