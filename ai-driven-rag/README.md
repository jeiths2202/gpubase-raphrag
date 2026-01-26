# AI Driven RAG System

Pure AI-driven RAG system using Local LLM with Tool Calling.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface                          │
│                   CLI  /  REST API                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│              AI Agent (Tool Calling Loop)                   │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Local LLM (Qwen2.5 / Nemotron)                    │    │
│  │  - No hardcoded rules                              │    │
│  │  - AI decides: intent, tool selection, response    │    │
│  │  - OpenAI-compatible function calling              │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                  │
│  ┌───────────────────────▼────────────────────────────┐    │
│  │              Tool Executor                          │    │
│  │  Executes tools and returns results to LLM         │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                       Tools                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ vector_search│  │ graph_query  │  │ document_read│      │
│  │              │  │              │  │              │      │
│  │ Semantic     │  │ Relationship │  │ Full content │      │
│  │ similarity   │  │ traversal    │  │ retrieval    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Data Sources                             │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │   Neo4j      │  │   Embeddings │                        │
│  │   Database   │  │   Service    │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

## Key Principles

### No Rule-Based Logic
All decisions are made by the LLM:
- **Intent**: LLM understands user intent naturally from the query
- **Tool Selection**: LLM chooses which tools to call based on the task
- **Search Strategy**: LLM decides vector/graph/both dynamically
- **Response Format**: LLM formats the response appropriately

### Minimal Python Code
- `tools/`: Thin wrappers around Neo4j and embedding services
- `agent/`: Simple tool-calling loop (no business logic)
- `cli/api/`: Pure I/O layer

## Project Structure

```
ai-driven-rag/
├── tools/
│   ├── __init__.py
│   ├── base.py              # Tool base class & registry
│   ├── vector_search.py     # Semantic search tool
│   ├── graph_query.py       # Graph relationship tool
│   └── document_read.py     # Document content tool
├── agent/
│   ├── __init__.py
│   ├── core.py              # AI Agent with tool calling
│   ├── llm.py               # LLM client (OpenAI-compatible)
│   └── prompts.py           # System prompts
├── cli/
│   ├── __init__.py
│   └── main.py              # CLI interface
├── api/
│   ├── __init__.py
│   └── main.py              # REST API (FastAPI)
├── config.py                # Configuration
├── requirements.txt
└── README.md
```

## Supported LLMs

| LLM | Tool Calling | Notes |
|-----|--------------|-------|
| Qwen2.5 (3B-72B) | ✅ Native | Best tool calling support |
| Nemotron Nano 9B | ✅ OpenAI-compat | Current KMS LLM |
| Mistral NeMo 12B | ✅ Native | Good for code tasks |
| Llama 3.1+ | ✅ Native | Community favorite |

## Quick Start

```bash
cd /opt/kms/ai-driven-rag

# Install dependencies
pip install -r requirements.txt

# Run CLI
python -m cli.main "에러 코드 E001에 대해 찾아줘"

# Or start API server
python -m api.main
# Then: curl -X POST http://localhost:8000/query -d '{"query": "..."}'
```

## Environment Variables

Uses existing `/opt/kms/.env`:
```bash
# Neo4j
NEO4J_URI=bolt://neo4j-graphrag:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...

# LLM (choose one)
LLM_API_URL=http://localhost:12800/v1      # Nemotron
# LLM_API_URL=http://localhost:11434/v1    # Ollama

# Embeddings
EMBEDDING_API_URL=http://nemo-embedding-graphrag:8000/v1
```

## How It Works

```
User: "에러 코드 E001의 원인과 해결방법을 알려줘"
         │
         ▼
┌─────────────────────────────────────────┐
│ LLM thinks: "I need to search for E001" │
│ → Calls: vector_search(query="E001")    │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Tool returns: [doc1, doc2, doc3]        │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ LLM thinks: "Need more context on doc1" │
│ → Calls: document_read(doc_id="doc1")   │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ LLM synthesizes final answer            │
│ "E001은 연결 타임아웃 오류입니다..."     │
└─────────────────────────────────────────┘
```

## Comparison: Rule-Based vs AI-Driven

| Aspect | Current (Rule-Based) | New (AI-Driven) |
|--------|---------------------|-----------------|
| Intent Detection | 80+ regex patterns | LLM understands naturally |
| Tool Selection | Hardcoded per agent type | LLM chooses dynamically |
| Search Strategy | If-else routing | LLM evaluates context |
| Response Mode | 6-case decision tree | LLM decides |
| Adding Features | Modify Python code | Update system prompt |
| Multilingual | Separate patterns per lang | LLM handles natively |
