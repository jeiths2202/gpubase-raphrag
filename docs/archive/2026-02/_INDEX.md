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
| [parallel-orchestrator-dag](./parallel-orchestrator-dag/) | 2026-02-17 | 91% | ✅ Completed |
| [enterprise-legacy-modernization](./enterprise-legacy-modernization/) | 2026-02-18 | 99% | ✅ Completed |
| [legacy-host-openframe-agents](./legacy-host-openframe-agents/) | 2026-02-18 | 100% | ✅ Completed |
| [mindmap-embedding-verification](./mindmap-embedding-verification/) | 2026-02-02 | 100% | ✅ Completed |
| [legacy-modernization-analysis-ui](./legacy-modernization-analysis-ui/) | 2026-02-19 | 98% | ✅ Completed |
| [vllm-hybrid-search-artifact-view](./vllm-hybrid-search-artifact-view/) | 2026-02-19 | 97% | ✅ Completed |
| [xsp-jcl-c-parser-wrapper](./xsp-jcl-c-parser-wrapper/) | 2026-02-19 | 95% | ✅ Completed |
| [legacy-analysis-datatable-persistence](./legacy-analysis-datatable-persistence/) | 2026-02-19 | 97% | ✅ Completed |

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

## parallel-orchestrator-dag

**Purpose**: Parallel/sequential query orchestration with DAG visualization for Agentic RAG pipeline

**Documents**:
- `parallel-orchestrator-dag.plan.md` - Feature plan (comparison/pipeline detection)
- `parallel-orchestrator-dag.design.md` - DAG execution architecture design
- `parallel-orchestrator-dag.analysis.md` - Gap analysis (91% match rate)
- `parallel-orchestrator-dag.report.md` - Completion report

**Key Deliverables**:
- `_analyze_query_pattern()` - Regex-based comparison/sequential detection (ja/ko/en)
- `_stream_parallel_comparison()` - asyncio.gather parallel search + LLM synthesis
- `_stream_pipeline()` - Sequential task execution with accumulated context
- Frontend DAG auto-open on trace_data SSE events

**Files Modified**:
- `app/api/services/agentic_rag_service.py` (~250 lines added)
- `kms-portal-ui/src/components/AgentChat.tsx` (1 line)
- `kms-portal-ui/src/pages/AgenticRAGPage.tsx` (6 lines)

**Key Metrics**:
| Metric | Value |
|--------|-------|
| Match Rate | 91% |
| Gaps Fixed | 3 (casing, trace_id, semaphore) |
| Iterations | 1 |

---

## enterprise-legacy-modernization

**Purpose**: Enterprise Legacy Modernization Intelligence Platform — 8 autonomous agents analyzing COBOL/JCL/MAP/ASM for OpenFrame migration

**Documents**:
- `enterprise-legacy-modernization.plan.md` - Feature plan (5 FRs, 10 deliverables, 6 phases)
- `enterprise-legacy-modernization.design.md` - Full design (3,312 lines, 30 sections)
- `enterprise-legacy-modernization.design-review.md` - Design review (83→99/100)
- `enterprise-legacy-modernization.analysis.md` - Gap analysis (99% match rate, 133/133 items)
- `enterprise-legacy-modernization.report.md` - Completion report

**Key Architecture**:
- 8 Autonomous Agents: COBOL Expert, JCL Expert, MAP Expert, ASM Expert, Compatibility Analyzer, QA Agent, Reviewer, Report Generator
- Deterministic Parser Supremacy: Tree-sitter AST (COBOL/JCL), Regex-based (MAP/ASM)
- 5-Rule Conflict Resolution: Parser immutable → QA veto → Reviewer escalation → Confidence-based → Orchestrator
- Redis Streams Event Bus with OpenTelemetry trace propagation
- SharedWorkspaceState with field-level write permissions per agent role
- PipelineStateMachine: 12 states, max 5 reanalysis iterations
- PostgreSQL (6 tables with RLS) + Redis (state/pub-sub) + MinIO (assets)
- Plugin System: 5 plugin types (PARSER, QA_RULE, REPORT_FORMAT, CAPABILITY_DB, AGENT)

**Functional Requirements**:
| FR | Description | Coverage |
|----|-------------|----------|
| FR-01 | Deterministic Parser Core (COBOL/JCL/MAP/ASM) | 6/6 (100%) |
| FR-02 | Compatibility Analysis Engine | 5/5 (100%) |
| FR-03 | Autonomous Agent Teamwork | 7/7 (100%) |
| FR-04 | Report Generation | 9/9 (100%) |
| FR-05 | Enterprise Deployment | 8/8 (100%) |

**PDCA Metrics**:
| Metric | Value |
|--------|-------|
| Match Rate | 99% |
| Design Review | 83 → 99/100 |
| Gaps Resolved | 28 (3 Critical, 7 Significant, 12 Minor, 6 IC) |
| Document Growth | 1,912 → 3,312 lines (+73%) |
| Iterations | 0 (passed first check) |

---

## legacy-host-openframe-agents

**Purpose**: Claude Code specialist agents for Legacy HOST mainframe analysis and TmaxSoft OpenFrame migration guidance

**Documents**:
- `legacy-host-openframe-agents.plan.md` - Feature plan (8 agents + 2 commands)
- `legacy-host-openframe-agents.analysis.md` - Gap analysis (97% → 100% match rate)
- `legacy-host-openframe-agents.report.md` - Completion report

**Key Deliverables**:
- 8 Claude Code agents in `.claude/agents/` (legacy-cobol/jcl/asm/map-expert, openframe-batch/online/cobol/infra-expert)
- 2 Slash commands in `.claude/commands/` (`/legacy-analyze`, `/openframe-migrate`)
- 35 domain responsibilities covered (19 Legacy + 16 OpenFrame)
- 25 product-version entries across 11 OpenFrame products
- 4 Fujitsu XSP spec documents integrated

**Quality Metrics**:
| Metric | Value |
|--------|-------|
| Match Rate | 97% → 100% |
| Deliverables | 10/10 (100%) |
| Domain Coverage | 35/35 (100%) |
| Product Coverage | 25/25 (100%) |
| Iterations | 0 |

---

## legacy-modernization-analysis-ui

**Purpose**: Multi-file batch analysis UI for Legacy Modernization — upload up to 10 COBOL/JCL/MAP/ASM files, get per-file incompatibility reports with summary dashboard

**Documents**:
- `legacy-modernization-analysis-ui.plan.md` - Feature plan (5 FRs, 10 steps)
- `legacy-modernization-analysis-ui.design.md` - Component design (API, SSE, UI)
- `legacy-modernization-analysis-ui.analysis.md` - Gap analysis (98% match rate)
- `legacy-modernization-analysis-ui.report.md` - Completion report

**Key Deliverables**:
- Backend: `POST /api/v1/legacy/batch-analyze` with SSE streaming
- `BatchAnalysisService` with asyncio.Semaphore(3) concurrency
- `BatchSummaryCard` component (aggregate stats, risk breakdown, support rate bar)
- `FileAccordion` component (expandable per-file results)
- `IncompatibilityReportView` component (7-section report)
- i18n translations (EN, KO, JA) — 28 keys added

**PDCA Metrics**:
| Metric | Value |
|--------|-------|
| Match Rate | 98% |
| Iterations | 0 |
| Steps Completed | 10/10 |
| TypeScript Errors Fixed | 26 |

---

## xsp-jcl-c-parser-wrapper

**Purpose**: OF7 XSP JCL C파서를 Python ctypes로 직접 호출하는 공통모듈 — 기존 Python regex 파서(8 패턴) 대체

**Documents**:
- `xsp-jcl-c-parser-wrapper.plan.md` - Feature plan (8 FRs, 5 phases)
- `xsp-jcl-c-parser-wrapper.design.md` - Architecture design (1,047 lines)
- `xsp-jcl-c-parser-wrapper.analysis.md` - Gap analysis (95% match rate)
- `xsp-jcl-c-parser-wrapper.report.md` - Completion report

**Key Deliverables**:
- `parsers/xspjcl/lib/kms_xspjcl_wrapper.c` - C wrapper with JSON serialization (750 lines)
- `parsers/xspjcl/models.py` - 15 Pydantic models + 3 enums (379 lines)
- `parsers/xspjcl/converter.py` - XSPParseResult → ParserResult converter (389 lines)
- `parsers/xspjcl/wrapper.py` - ctypes C library wrapper (249 lines)
- `parsers/xspjcl/__init__.py` - XSPParserAdapter (136 lines)
- `parsers/xspjcl/lib/Makefile` + `build.sh` - Build system

**Key Metrics**:
| Metric | Value |
|--------|-------|
| Match Rate | 95% |
| Files Created | 7 (2,039 lines) |
| Statement Types | 46 (design: 41) |
| Error Codes | 22 (design: 9) |
| Parser Features | 15/15 (100%) |
| Design Exceedances | 8 areas |
| Iterations | 0 |

---

## legacy-analysis-datatable-persistence

**Purpose**: Legacy Modernization 분석 결과의 PostgreSQL 영구 저장, Data Table UI, 팝업 상세 페이지

**Documents**:
- `legacy-analysis-datatable-persistence.plan.md` - Feature plan (10 phases, 17 files)
- `legacy-analysis-datatable-persistence.analysis.md` - Gap analysis (97% match rate)
- `legacy-analysis-datatable-persistence.report.md` - Completion report

**Key Deliverables**:
- `app/api/infrastructure/postgres/legacy_analysis_repository.py` - PostgreSQL CRUD (340 lines)
- `kms-portal-ui/src/components/ModernizationAI/AnalysisDataTable.tsx` - Data Table (393 lines)
- `kms-portal-ui/src/pages/LegacyAnalysisDetailPage.tsx` - Popup detail page (437 lines)
- 3 API endpoints: GET/DELETE `/legacy/analyses`, GET `/legacy/analyses/{id}`
- i18n translations (EN, KO, JA) — 24 keys per locale

**Key Metrics**:
| Metric | Value |
|--------|-------|
| Match Rate | 97% |
| Files Created | 5 (1,958 lines) |
| Files Modified | 11 |
| Code Quality | 9.7/10 |
| DB Columns | 25 (5 indexes, 4 JSONB) |
| Design Exceedances | 5 areas |
| Iterations | 0 |

---

*Last updated: 2026-02-19 (legacy-analysis-datatable-persistence archived)*
