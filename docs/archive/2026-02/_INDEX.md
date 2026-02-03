# Archive Index - 2026-02

> Archived PDCA documents for February 2026

## Archived Features

| Feature | Archive Date | Match Rate | Status |
|---------|--------------|------------|--------|
| [server-script-improvement](./server-script-improvement/) | 2026-02-03 | 97% | ✅ Completed |
| [rag-backend-integration](./rag-backend-integration/) | 2026-02-03 | 96% | ✅ Completed |
| [summary-quality-improvement](./summary-quality-improvement/) | 2026-02-03 | 94% | ✅ Completed |
| [strategy-aware-learning-dataset](./strategy-aware-learning-dataset/) | 2026-02-03 | 100% | ✅ Completed |
| [chatgpt-quality-pipeline](./chatgpt-quality-pipeline/) | 2026-02-03 | 100% | ✅ Completed |
| [chatgpt-style-webui](./chatgpt-style-webui/) | 2026-02-03 | 91% | ✅ Completed |
| [mindmap-embedding-verification](./mindmap-embedding-verification/) | 2026-02-02 | 100% | ✅ Completed |

---

## summary-quality-improvement

**Purpose**: Quality checking and improvement tools for `uploads/summaries/` data to prevent LLM hallucinations

**Documents**:
- `summary-quality-improvement.plan.md` - Feature plan (osctdlrm hallucination analysis)
- `summary-quality-improvement.design.md` - Component design specifications
- `summary-quality-improvement.analysis.md` - Gap analysis (94% match rate)
- `summary-quality-improvement.report.md` - Completion report

**Key Deliverables**:
- `scripts/manual_processor/models/quality.py` - Data models (220 lines)
- `scripts/manual_processor/quality_checker.py` - Quality checker (454 lines)
- `scripts/manual_processor/quality_enhancer.py` - Quality enhancer (502 lines)
- CLI commands: `quality-check`, `quality-improve`

**Key Fixes**:
- osctdlrm: type="concept" → "command", syntax field added
- 62 items total reclassified from concept to command
- Misclassified items reduced: 100 → 38

**Quality Metrics**:
| Metric | Value |
|--------|-------|
| Total items | 17,431 |
| Incomplete | 8 (0.05%) |
| Duplicates | 2,151 (12.3%) |
| Misclassified | 38 (0.2%) |
| Quality Score | 87.4% |

---

## chatgpt-quality-pipeline

**Purpose**: Backend-focused pipeline improvements for ChatGPT-level document understanding

**Documents**:
- `chatgpt-quality-pipeline.plan.md` - Feature plan (11 information loss points identified)
- `chatgpt-quality-pipeline.design.md` - 4-phase backend implementation design
- `chatgpt-quality-pipeline.report.md` - Completion report (100% match rate)

**Key Deliverables**:
- `ParagraphReconstructor` class - PDF line breaks to semantic paragraphs
- `TableToMarkdownConverter` class - PyMuPDF tables to GFM Markdown
- Context window extension (200→500, 500→1000 chars)
- Answer builder limits relaxation (3→5 sentences, 20→5 code length)
- GFM Markdown output contract in `rag_agent.txt`

**Files Modified**:
- `scripts/manual_processor/parsers/pdf_parser.py` (~150 lines)
- `scripts/manual_processor/parsers/content_parser.py`
- `app/api/services/answer_builder_service.py`
- `app/api/agents/prompts/rag_agent.txt` (~50 lines)

---

## chatgpt-style-webui

**Purpose**: ChatGPT-style chat WebUI with syntax highlighting and collapsible sources

**Documents**:
- `chatgpt-style-webui.plan.md` - Feature plan
- `chatgpt-style-webui.design.md` - Component design specifications
- `chatgpt-style-webui.analysis.md` - Gap analysis (91% match)
- `chatgpt-style-webui.report.md` - Completion report

**Key Deliverables**:
- `chatgpt-style.css` - 535 lines of ChatGPT-style CSS
- `MessageContent.tsx` - Enhanced with rehype-highlight
- `TypingCursor.tsx` - Streaming cursor animation
- `SourcesAccordion.tsx` - Collapsible RAG sources
- i18n translations (EN, KO, JA)

---

## mindmap-embedding-verification

**Purpose**: Verify that `/mindmap` API integrates with Neo4j Vector Index

**Documents**:
- `mindmap-embedding-verification.plan.md` - Verification plan
- `mindmap-embedding-verification.analysis.md` - API test results
- `mindmap-embedding-verification.report.md` - Completion report

**Summary**:
- Health Check: ✅ healthy
- Vector Index: ✅ chunk_embedding ONLINE
- Embedding Coverage: ✅ 100% (42,432 chunks)
- Vector Search: ✅ Working

---

## strategy-aware-learning-dataset

**Purpose**: Strategy-based parsing system for generating learning dataset from 245 PDFs

**Documents**:
- `structure-aware-parsing.plan.md` - Feature plan (16 parsing strategies defined)
- `strategy-aware-learning-dataset.report.md` - Completion report (100% match rate)

**Key Deliverables**:
- `scripts/manual_processor/parsers/strategy_aware_parser.py` - CJK-aware parser (~850 lines)
- `scripts/update_jeus_to_korean.py` - JEUS Korean migration script
- `uploads/summaries/strategy_analysis.json` - 222 manual strategy analysis
- `uploads/summaries/learning_dataset.json` - 20,143 unique learning items

**Statistics**:
- Total PDFs: 245
- Unique Items: 20,143
- JEUS Korean Migration: 76.8% Korean text ratio
- Processing Time: ~30 seconds

**Item Types**:
| Type | Count |
|------|-------|
| concept | 17,074 |
| procedure | 1,887 |
| api | 848 |
| config | 137 |
| command | 136 |
| term | 53 |
| error | 8 |

---

## rag-backend-integration

**Purpose**: RAG Anti-Hallucination Service Integration - FastAPI backend service to prevent LLM hallucinations

**Documents**:
- `rag-backend-integration.plan.md` - Feature plan (hallucination crisis analysis)
- `rag-backend-integration.design.md` - Architecture and API design
- `rag-backend-integration.analysis.md` - Gap analysis (96% match rate)
- `rag-backend-integration.report.md` - Completion report

**Key Deliverables**:
- `app/api/services/rag_anti_hallucination_service.py` - Singleton service (411 lines)
- `app/api/routers/query_rag.py` - 4 REST API endpoints (341 lines)
- Router registration in `app/api/main.py`

**API Endpoints**:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/query/rag` | POST | RAG query (3 modes) |
| `/api/v1/query/rag/search` | POST | Debug search |
| `/api/v1/query/rag/stats` | GET | Statistics |
| `/api/v1/query/rag/health` | GET | Health check |

**3 RAG Modes**:
| Mode | LLM | Accuracy | Use Case |
|------|-----|----------|----------|
| Direct | No | 100% | Exact keyword queries |
| LLM | Yes | 85% | Natural responses |
| Hybrid | Auto | 95% | **Recommended** |

**Statistics**:
- Training Data: 13,594 documents (24 products)
- Match Rate: 96%
- Files Created: 2
- Lines Added: 752

---

## server-script-improvement

**Purpose**: Production-grade improvement of `scripts/server.ps1` for reliable server start/stop operations

**Documents**:
- `server-script-improvement.plan.md` - Feature plan (Start-Process crash analysis)
- `server-script-improvement.design.md` - 13 functions design (550→855 lines)
- `server-script-improvement.analysis.md` - Gap analysis (97% match rate)
- `server-script-improvement.report.md` - Completion report

**Key Deliverables**:
- `scripts/server.ps1` - Main implementation (855 lines, +495 lines)
- `scripts/server.ps1.bak` - Original backup (360 lines)

**Root Cause Fixed**:
```powershell
# Before (broken) - cmd.exe /c causes child process termination
Start-Process cmd.exe /c "python ..." -WindowStyle Hidden

# After (working) - Direct Python execution
Start-Process python -PassThru -RedirectStandardOutput
```

**New Features**:
| Feature | Description |
|---------|-------------|
| Health Check | HTTP `/api/v1/health` polling (60s timeout) |
| Graceful Shutdown | WM_CLOSE → 10s wait → Force kill |
| PID Management | `.pids/` directory for process tracking |
| Environment Validation | Required env vars check |
| Retry Logic | Max 3 attempts on failure |
| Resource Monitoring | CPU/Memory display in status |
| Log Rotation | Auto-delete logs older than 7 days |

**New Parameters**:
| Parameter | Default | Description |
|-----------|---------|-------------|
| `-Timeout` | 60 | Health check timeout (seconds) |
| `-MaxRetries` | 3 | Start retry count |
| `-SkipEnvCheck` | false | Skip environment validation |
| `-GracePeriod` | 10 | Graceful shutdown wait (seconds) |

---

*Last updated: 2026-02-03 (server-script-improvement archived)*
