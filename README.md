# HybridRAG KMS

A GPU-based **Hybrid RAG Knowledge Management System** for enterprise legacy mainframe modernization, featuring product-specific Agentic RAG with QLoRA-trained domain LLMs.

## Overview

HybridRAG KMS is an enterprise AI platform purpose-built for **TmaxSoft OpenFrame** migration support. It combines graph-based and vector-based retrieval with domain-specialized LLMs to provide accurate, hallucination-minimized answers about 19 mainframe products across IBM MVS, Fujitsu XSP, and OpenFrame ecosystems.

### Key Capabilities

| Capability | Description |
|------------|-------------|
| **Agentic RAG (6-Phase)** | Product routing → Two-stage retrieval → Template/LLM generation → Post-verification → Source attribution |
| **QLoRA Training Pipeline** | 3-phase CPT→SFT→DPO pipeline producing 22 product-specific LoRA adapters with 95% preference accuracy |
| **Agent Teams (5 Patterns)** | Parallel retrieval, competitive hypothesis, domain specialist, multi-product comparison, self-improvement |
| **Zero-Hallucination Design** | Structured questions (~70-80%) use template responses; freeform questions use LLM with cosine similarity verification |
| **Dynamic Product Discovery** | Auto-discovers 19 products from `uploads/manuals/` directory (245 PDFs) |
| **Multilingual Native** | Full support for Japanese, Korean, and English with language-aware prompts |
| **Vision LLM Integration** | PDF image/chart/table extraction and analysis via MiniCPM-V 2.6 |

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | FastAPI (Python 3.10+) |
| **Frontend** | React 18 + TypeScript + Vite |
| **Graph DB** | Neo4j (Graph + Vector Index, 42K+ chunks, 13K+ entities) |
| **Relational DB** | PostgreSQL 15 + pgvector |
| **RAG LLM** | Qwen 2.5 7B-Instruct + 22 QLoRA adapters (vLLM, GPU 4) |
| **Vision LLM** | MiniCPM-V 2.6 (vLLM, GPU 5-6) |
| **Code LLM** | Qwen 2.5 Coder 3B (vLLM, GPU 7) |
| **Learning LLM** | Qwen 2.5 7B + QLoRA adapter (vLLM, GPU 7) |
| **Embeddings** | NV-EmbedQA-Mistral 7B v2 (NIM, GPU 5) |
| **GPU** | NVIDIA A100-SXM4-40GB x 8 |
| **LLM Framework** | LangChain / LangGraph |

---

## Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    Agent Teams (Pattern Layer)                    │
│  A: Parallel Retrieval  B: Competitive Hypothesis                │
│  C: Domain Specialist   D: Multi-Product   E: Self-Improvement   │
├──────────────────────────────────────────────────────────────────┤
│                  Agentic RAG (Core RAG Layer)                    │
│  Phase 1: Product Routing → Phase 2: Query Classification        │
│  Phase 3: Two-Stage Retrieval → Phase 4: Response Generation     │
│  Phase 5: Post-Verification → Phase 6: Source Attribution        │
├──────────────────────────────────────────────────────────────────┤
│              Base Agent System (Foundation Layer)                 │
│  RAG, IMS, Code, Vision, Planner, Enhancement (Analyst/          │
│  Architect/Coder/QA)                                             │
├──────────────────────────────────────────────────────────────────┤
│                QLoRA Training Pipeline (Offline)                  │
│  CPT (72B) → SFT (7B × 22 adapters) → DPO → vLLM Serving       │
└──────────────────────────────────────────────────────────────────┘
```

### Information Flow

```
User Query: "tjesmgrのBOOTコマンドについて教えてください"
    │
    ▼ Phase 1: Product Routing
    ProductRouterService (keyword + pattern scoring)
    → openframe_mvs (confidence: 0.85) → CONFIRMED
    │
    ▼ Phase 2: Query Classification
    QueryRouter → STRUCTURED (command question)
    │
    ▼ Phase 3: Two-Stage Retrieval
    ├─ Stage 1: Summary search (<10ms, filesystem)
    │   └─ commands/OpenFrame_TJES_MVS.md → tjesmgr BOOT info
    ├─ Stage 2: PDF RAG search (BM25 + keyword, NO LLM)
    │   └─ StructuredKnowledgeStore → PyMuPDF TOC-based
    └─ (Optional) Web Doc Fast Path (score >= 0.9)
    │
    ▼ Phase 4: Response Generation
    ├─ STRUCTURED → Template response (zero hallucination)
    └─ FREEFORM → QLoRA LLM (constrained to search results)
    │
    ▼ Phase 5: Post-Verification (FREEFORM only)
    ResponseVerifier → cosine similarity per sentence
    │
    ▼ Phase 6: Source Attribution
    ProductSources: learning_llm, vector_search, graph_search
```

---

## Agentic RAG System

The core innovation replacing traditional query routing. Instead of classifying queries into vector/graph/hybrid strategies, the system routes to **product-specific agents** with domain-specialized knowledge.

### Core Services

| Service | Role |
|---------|------|
| `AgenticRAGService` | Main orchestrator (6-phase pipeline) |
| `ProductRouterService` | Product identification via keyword/pattern scoring |
| `ManualRegistryService` | Auto-discovers 19 products from PDF directories |
| `DynamicProductAgentService` | Creates per-product agents from registry |
| `StructuredKnowledgeStore` | PyMuPDF-based PDF parsing + BM25 search |
| `SummarySearchService` | Filesystem-based summary search (<10ms) |
| `SummaryBM25Service` | BM25 ranking for summary documents |
| `WebDocSearchService` | docs.tmaxsoft.com fast-path search |
| `ProductContextMemory` | LangGraph Store-based routing memory |
| `ResponseVerifier` | Per-sentence cosine similarity verification |
| `LearningLLMService` | QLoRA adapter-based domain LLM generation |

### Design Principles

| Principle | Details |
|-----------|---------|
| **No LLM in retrieval** | Search is deterministic (keyword + BM25) — no hallucination risk |
| **LLM only for generation** | Constrained to search results |
| **Structured first** | 70-80% of queries use template responses (zero hallucination) |
| **Dynamic products** | `uploads/manuals/` scan → 19 products auto-discovered |
| **File context priority** | Attached files always take precedence over DB search |

### Product Router Scoring

```
keyword_score = 0.15 × weight
pattern_score = 0.3 × weight
max_score = 1.5 (normalization)

CONFIRMED:            conf >= 0.8 and gap >= 0.3
CLARIFICATION_NEEDED: 0.5 <= conf < 0.8 (auto-confirm if 1 candidate + conf >= 0.6)
NO_MATCH:             conf < 0.5
```

### Summary System (Two-Stage Retrieval)

Pre-computed summaries from 245 PDFs enable sub-10ms first-stage retrieval:

```
uploads/summaries/
├── error-codes/     # ~1,200 error codes (46 files)
├── glossary/        # A-Z terminology (26 files)
├── commands/        # OpenFrame commands (tjesmgr, hidbmgr, ...)
├── configs/         # Configuration parameters
├── apis/            # Programming API functions
└── terms/           # Domain terminology
```

---

## Agent Teams (5 Patterns)

Feature-flagged collaboration patterns built on top of Agentic RAG. All flags default to OFF — when disabled, the system falls through to standard Agentic RAG with zero overhead.

| Pattern | Flag | Description |
|---------|------|-------------|
| **A: Parallel Retrieval** | `AGENT_TEAMS_PARALLEL_RETRIEVAL` | Web Doc + PDF RAG parallel search via `asyncio.gather` |
| **B: Competitive Hypothesis** | `AGENT_TEAMS_COMPETITIVE_HYPOTHESIS` | Multiple temperature generations → rule-based evaluation |
| **C: Domain Specialist** | `AGENT_TEAMS_DOMAIN_SPECIALIST` | Related product QLoRA adapters in parallel → confidence selection |
| **D: Multi-Product** | `AGENT_TEAMS_MULTI_PRODUCT` | Per-product independent search+LLM → synthesis for comparison queries |
| **E: Self-Improvement** | `AGENT_TEAMS_SELF_IMPROVEMENT` | Feedback JSONL accumulation → QLoRA retraining data |

**Key constraint**: No external LLM API (Claude, GPT) — all LLM calls use local vLLM with Qwen + QLoRA adapters.

---

## QLoRA Training Pipeline

### Motivation

- E2E test **53% failure rate** (21/45) due to LLM hallucination on OpenFrame domain knowledge
- Generic LLMs (Qwen 2.5) lack TmaxSoft 19-product domain expertise
- 72B full fine-tuning exceeds GPU memory → **QLoRA (4-bit + LoRA)** adopted

### 3-Phase Pipeline

```
Phase 1: CPT (Continued Pre-Training) ─── Domain knowledge injection
    │ Base: Qwen2.5-72B, Plain Text 72MB (~34.3M tokens)
    │ LoRA r=64 α=128, FSDP A100×4, 2 epochs
    │ Result: Perplexity 1.65, Loss 0.11 (2h 28m)
    ↓
Phase 2: SFT (Supervised Fine-Tuning) ─── Product-specific Q-A
    │ Base: Qwen2.5-7B × 22 products
    │ ChatML format, LoRA r=64 α=16, LR=2e-4
    │ Result: 22 Multi-LoRA adapters (~69min total)
    ↓
Phase 3: DPO (Direct Preference Optimization) ─── Hallucination suppression
    │ 2,000 preference pairs (chosen vs rejected)
    │ 3 strategies: Cross-product (0.6%), Factual mutation (55.7%), SFT cross-match (43.7%)
    │ Result: 95% preference accuracy, Loss 75% reduction (0.69→0.17)
    ↓
vLLM Serving (port 12804) ─── Dynamic QLoRA adapter loading
```

### Dataset Evolution (PDCA Iterations)

```
v4 → 22-product baseline extraction
v5 → Paraphrase + back-translation augmentation
v6 → Cross-product balance adjustment
v7 → Semantic cleaning (cosine similarity 0.95+ dedup)
v8 → Pattern filtering (NDB removal, Q-A mismatch 40%+ removal)
v9 → PDCA 2nd iteration refinement (current production)
```

### RAFT Integration

Based on ["RAFT: Adapting Language Model to Domain Specific RAG"](https://arxiv.org/abs/2403.10131):

| Concept | KMS Application |
|---------|----------------|
| Oracle Document (D*) | Summary-based Two-Stage Retrieval results |
| Distractor Document (Dk) | DPO cross-product documents |
| Chain-of-Thought citation | `ResponseVerifier` word overlap verification |
| Effect | Model learns to ignore irrelevant documents in search results |

---

## Base Agent System

9 specialized agents with intent-based routing:

| Agent | Domain | Key Capabilities |
|-------|--------|------------------|
| **Auto** | General | Default agent with automatic sub-routing |
| **RAG** | Knowledge Q&A | Hybrid vector/graph retrieval, file context priority |
| **IMS** | Issue Management | IMS SSO integration, issue search, report generation |
| **Vision** | Image Analysis | PDF image extraction, chart analysis, document OCR |
| **Code** | Code Generation | Code synthesis, analysis, multi-language support |
| **Planner** | Task Planning | Multi-step decomposition, dependency analysis |
| **Enhancement Analyst** | Requirements | Auto type classification, feasibility, risk analysis |
| **Enhancement Architect** | Design | Architecture proposal, API design, security review |
| **Enhancement Coder** | Implementation | Code generation from architecture, test generation |
| **Enhancement QA** | Testing | Test strategy, unit/integration/E2E execution |

### Deep Agents (LangGraph)

RAG Agent supports LangGraph-based Deep Agent mode with tool calling (`vector_search`, `graph_query`), checkpointing via `MemorySaver`, and automatic fallback to standard agents on failure.

### Enterprise Orchestration

DAG-based multi-agent task decomposition with parallel execution, result evaluation, automatic retry, and synthesis for complex cross-domain queries.

---

## Frontend (React + TypeScript)

### Pages

| Page | Description |
|------|-------------|
| **Agentic RAG** | Product-specific RAG chat with streaming, source attribution, table/image display |
| **OpenFrame RAG** | Legacy product-based RAG interface |
| **Open Agent** | General AI agent chat with multi-agent routing |
| **MindMap** | LLM-generated knowledge mind maps (React Flow) |
| **Admin Dashboard** | User management, system settings, traces |
| **Knowledge Graph** | Interactive graph visualization |
| **Enhancement Management** | AI-driven feature request lifecycle |
| **IMS Crawler** | Issue tracking integration with SSE streaming |
| **Support Dashboard** | Real-time expert notification panel |
| **Document Management** | PDF upload, processing, chunking |
| **Login/SSO** | Authentication with Google OAuth support |

### Internationalization

Full i18n support across 3 languages with 9+ translation namespaces:

| Language | Coverage |
|----------|----------|
| English (en) | 100% |
| Japanese (ja) | 100% |
| Korean (ko) | 100% |

---

## Project Structure

```
gpubase-raphrag/
├── app/api/                      # FastAPI backend
│   ├── main.py                   # Entry point, middleware, router registration
│   ├── core/                     # Config, DI, security, auth
│   ├── routers/                  # 27+ API routers
│   ├── services/                 # 157+ service modules
│   │   ├── agentic_rag_service.py        # Agentic RAG orchestrator
│   │   ├── product_router_service.py     # Product routing
│   │   ├── structured_knowledge_store.py # PDF search
│   │   ├── summary_search_service.py     # Summary search
│   │   ├── learning_llm_service.py       # QLoRA LLM
│   │   ├── agent_teams/                  # 5 team patterns
│   │   └── jcl_diagnosis/                # JCL error diagnosis
│   ├── models/                   # 55+ Pydantic schemas
│   ├── agents/                   # Agent system (orchestrator, executor, adapters)
│   ├── adapters/                 # LangChain, vision, mock adapters
│   ├── ports/                    # Hexagonal architecture interfaces
│   ├── connectors/               # Confluence, GitHub, Notion, Google Drive
│   └── ims_crawler/              # IMS integration (DDD architecture)
│
├── kms-portal-ui/                # React frontend
│   ├── src/
│   │   ├── pages/                # 26+ page components
│   │   ├── components/           # Shared UI components
│   │   ├── api/                  # API service clients
│   │   ├── stores/               # Zustand state management
│   │   ├── hooks/                # Custom React hooks
│   │   ├── i18n/locales/         # en, ja, ko translations
│   │   └── styles/               # CSS (chatgpt-style, agent-chat)
│   └── vite.config.ts
│
├── scripts/
│   ├── training/                 # QLoRA training pipeline
│   │   ├── run_full_pipeline.py  # Full CPT→SFT→DPO orchestrator
│   │   ├── run_cpt_training.py   # Phase 1: CPT
│   │   ├── train_multi_lora_v4.py # Phase 2: SFT (22 adapters)
│   │   ├── run_dpo_training.py   # Phase 3: DPO
│   │   └── convert_to_qlora.py   # Dataset format conversion
│   ├── manual_processor/         # PDF → summary extraction
│   ├── entity_pipeline/          # Chunk-entity extraction (99.9% coverage)
│   └── server.ps1                # Windows service management
│
├── uploads/
│   ├── manuals/                  # 19 products, 245 PDFs
│   ├── summaries/                # Pre-computed summaries
│   ├── pdf_images/               # Extracted PDF images
│   ├── training_text/            # CPT plain text + DPO pairs
│   └── web_doc_index/            # docs.tmaxsoft.com index
│
├── e2e/                          # E2E tests (Playwright)
├── tests/                        # Unit/integration tests
├── docs/                         # PDCA documentation
├── docker/                       # Docker configuration
├── kms.docker-compose.yml        # GPU service definitions
├── CLAUDE.md                     # Claude Code guidance
└── AGENT.md                      # Agent system & QLoRA guide
```

---

## Quick Start

### Prerequisites

- NVIDIA A100 GPU (or compatible CUDA GPU)
- Docker with NVIDIA Container Toolkit
- Node.js 18+ (frontend)
- Python 3.10+ (backend)

### 1. Environment Setup

```bash
# Copy environment template
cp .env.example .env
# Edit .env with your database passwords and API keys
```

Required environment variables:
| Variable | Description |
|----------|-------------|
| `JWT_SECRET_KEY` | JWT signing key (min 32 chars) |
| `ENCRYPTION_MASTER_KEY` | OAuth token encryption (min 32 chars) |
| `NEO4J_PASSWORD` | Neo4j database password |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `HUGGING_FACE_HUB_TOKEN` | HuggingFace model access |
| `NGC_API_KEY` | NVIDIA NGC API key (for NIM containers) |

### 2. Start GPU Services (Docker)

```bash
# Start all services
docker-compose -f kms.docker-compose.yml up -d

# Check status
docker ps | grep -E "graphrag|kms|neo4j|postgres"
```

### 3. Start Backend

```bash
# Docker
docker-compose -f kms.docker-compose.yml up -d kms-backend

# Or direct (Windows)
.\scripts\server.ps1 backend start
```

### 4. Start Frontend

```bash
cd kms-portal-ui
npm install
npm run dev    # http://localhost:3000
```

### 5. Verify

```bash
# Login and get token
TOKEN=$(curl -s -X POST http://localhost:9000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"SecureAdm1nP@ss2024!"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

# Test Agentic RAG
curl -s -X POST http://localhost:9000/api/v1/agentic-rag/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "tjesmgrのBOOTコマンドについて教えてください", "language": "ja"}'
```

---

## Port Allocations

| Port | Service | GPU |
|------|---------|-----|
| 3000 | React Frontend | - |
| 9000 | FastAPI Backend | - |
| 5432 | PostgreSQL + pgvector | - |
| 5050 | pgAdmin Web UI | - |
| 7474 | Neo4j HTTP | - |
| 7687 | Neo4j Bolt | - |
| 12800 | Qwen 2.5 7B Text LLM | GPU 4 |
| 12801 | NV-EmbedQA Embedding | GPU 5 |
| 12802 | Qwen 2.5 Coder 3B | GPU 7 |
| 12803 | MiniCPM-V 2.6 Vision | GPU 5,6 |
| 12804 | Learning LLM (QLoRA) | GPU 7 |

### GPU Allocation

| GPU | Service | VRAM |
|-----|---------|------|
| GPU 4 | Qwen 2.5 7B (Text LLM) | ~32 GiB |
| GPU 5 | NV-EmbedQA Embedding | ~36 GiB |
| GPU 5,6 | MiniCPM-V 2.6 (Vision, Tensor Parallel) | ~36 GiB |
| GPU 7 | CodeQwen 3B (0.4) + Learning LLM (0.5) | ~36 GiB |

---

## API Endpoints

**Base Path:** `/api/v1`

### Core RAG
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/agentic-rag/chat` | Agentic RAG chat (product-specific) |
| POST | `/agentic-rag/stream` | Agentic RAG streaming (SSE) |
| GET | `/agentic-rag/products` | List available products |
| POST | `/agents/stream` | Agent streaming (auto/rag/code/vision/planner) |
| POST | `/agents/enterprise/stream` | Multi-agent orchestration (DAG) |

### Knowledge & Documents
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/query` | Hybrid RAG query |
| POST | `/documents` | Upload document |
| POST | `/knowledge-graph/generate` | Generate knowledge graph |
| POST | `/mindmap/generate` | Generate mind map |
| POST | `/content/summarize` | AI summarization |

### Authentication & Admin
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | JWT authentication |
| POST | `/auth/register` | User registration |
| GET | `/admin/users` | User management |
| GET | `/health` | Health check |
| GET | `/system/status` | System status |

### Specialized
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/vision/query` | Vision-aware document query |
| POST | `/ims-search` | IMS issue search (BM25 + Semantic) |
| POST | `/enhancements` | Enhancement request lifecycle |
| POST | `/verified-knowledge/learn` | Trigger QLoRA learning from verified data |
| GET | `/graph-visualization/data` | Knowledge graph visualization data |

---

## E2E Testing

Playwright-based hallucination detection tests covering 45 test cases across OpenFrame components:

```bash
cd e2e

# Main hallucination test (45 cases)
node e2e_sentence_test.js

# Keyword search test
node e2e_keyword_test.js

# Individual command tests
node e2e_tjesmgr.js
node e2e_tacfmgr.js
```

### Test Coverage

| Category | Components |
|----------|------------|
| Manager commands | tjesmgr, tacfmgr, hidbmgr, ndbmgr, oscmgr, osimgr, volmgr, catmgr |
| Utilities | idcams, iebgener, iebcopy, dfsort, dsmigin, dsmigout |
| JCL | JOB, EXEC, DD statements |
| Config files | tjes.conf, osc.conf, tacf.conf, ds.conf |
| Error codes | ABEND S0C7, S0C4, S806 |
| VSAM types | KSDS, ESDS, GDG, PDS |

### Hallucination Detection

Tests detect when the LLM confuses products:
```javascript
{
  keyword: 'tjesmgr',
  query: 'tjesmgrについて説明してください。',
  expected: ['tjesmgr', 'TJES'],       // Must appear
  notExpected: ['oscmgr', 'osimgr']    // Hallucination if present
}
```

---

## Knowledge Graph

Neo4j-based graph with hybrid vector + entity search:

| Metric | Value |
|--------|-------|
| Chunks | 42,596 |
| Entities | 13,450 |
| MENTIONS relationships | 476,215 |
| Entity-connected chunks | 99.9% (42,545/42,596) |

Entity types: config (4,454), command (2,823), concept (1,934), error_code (1,016), product, technology

### Entity Pipeline

Batch extraction from chunks using 3-phase approach:
1. **Summary dictionary match** (confidence 0.95) — 17,489 entries from summaries
2. **Regex pattern match** (confidence 0.80) — command/error code patterns
3. **Katakana fallback** (confidence 0.70) — Japanese technical terms

```bash
python -m scripts.entity_pipeline.batch_extract [--dry-run] [--verify ENTITY]
```

---

## Development

### Backend

```bash
python -m app.api.main --mode develop    # Dev server (auto-reload)
python -m app.api.main --mode product    # Production
pip install -r requirements-api.txt
```

### Frontend

```bash
cd kms-portal-ui
npm install
npm run dev          # Dev server (port 3000)
npm run build        # Production build
```

### Windows Direct Execution

```powershell
.\scripts\server.ps1 all start       # Start all
.\scripts\server.ps1 all stop        # Stop all
.\scripts\server.ps1 status          # Check status
```

### Testing

```bash
# Backend unit tests
python -m pytest tests/ -v

# Frontend tests
cd kms-portal-ui && npm run test:run

# E2E hallucination tests
cd e2e && node e2e_sentence_test.js
```

---

## QLoRA Training Scripts

| Script | Purpose |
|--------|---------|
| `scripts/training/run_full_pipeline.py` | Full pipeline orchestrator (CPT→SFT→DPO) |
| `scripts/training/run_cpt_training.py` | Phase 1: Continued Pre-Training |
| `scripts/training/train_multi_lora_v4.py` | Phase 2: SFT (22 product adapters) |
| `scripts/training/run_dpo_training.py` | Phase 3: DPO preference optimization |
| `scripts/training/convert_to_qlora.py` | Dataset format conversion |
| `scripts/training/generate_dpo_data.py` | DPO preference pair generation |
| `scripts/manual_processor/main.py` | PDF → summary extraction |
| `scripts/entity_pipeline/batch_extract.py` | Chunk → entity extraction |

---

## Supported Products (19)

Products auto-discovered from `uploads/manuals/`:

| Family | Products |
|--------|----------|
| **OpenFrame** | MVS 7.1, MSP 7, VOS3 7, HIDB 7 |
| **OpenFrame Tools** | OFASM, OFCOBOL, OFPLI, OFStudio |
| **Tmax** | Tmax 5 |
| **Tibero** | Tibero 7 |
| **Fujitsu** | XSP (OSIV/XSP), AIM/DB, AIM/DC |
| **IBM Legacy** | JCL, VSAM, CICS |
| **General** | Installation Guide, Migration Guide |

---

## Release History

| Version | Date | Highlights |
|---------|------|------------|
| **v2.0.0-qlora-agentic-rag** | 2026-02 | Agentic RAG, QLoRA pipeline, Agent Teams, Vision LLM, Entity Pipeline |
| v1.2.0 | 2026-01 | Enhancement management, enterprise orchestration |
| v1.1.0 | 2026-01 | Multi-agent system, IMS integration |
| v1.0.0-gpu-local-llm | 2025-12 | Initial GPU-based RAG with Nemotron LLM |

---

## Documentation

| Document | Description |
|----------|-------------|
| [CLAUDE.md](CLAUDE.md) | Claude Code development guidance |
| [AGENT.md](AGENT.md) | Agent system & QLoRA pipeline guide |
| [app/api/CLAUDE.md](app/api/CLAUDE.md) | Backend architecture details |
| [app/api/agents/CLAUDE.md](app/api/agents/CLAUDE.md) | Agent implementation details |
| [kms-portal-ui/CLAUDE.md](kms-portal-ui/CLAUDE.md) | Frontend architecture details |

---

## License

Proprietary - TmaxSoft Japan / TmaxSoft Co., Ltd.
