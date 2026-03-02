# Analysis History (Detailed)

## Older Analyses (moved from MEMORY.md for space)

### parallel-orchestrator-dag (2026-02-17, re-verified)
- **Match Rate**: 80.8% (up from 71.1%, tests excluded as deferred)
- **Fixed Gaps**: parallelism_type casing now lowercase, trace_id now in DAG init events
- **Remaining Gaps**: Semaphore(2) defined but not applied in _search_subject(), no tests (deferred)
- **Design**: `docs/02-design/features/parallel-orchestrator-dag.design.md`
- **Analysis**: `docs/03-analysis/parallel-orchestrator-dag.analysis.md` (v0.2)

### enterprise-legacy-modernization (2026-02-18, Plan-vs-Design)
- **Match Rate**: 100% (Plan-to-Design, 133 items checked)
- **Overall Score**: 99% (1% deduction for 6 implementation-detail gaps deferred to Do phase)
- **Plan**: `docs/01-plan/features/enterprise-legacy-modernization.plan.md` (451 lines)
- **Design**: `docs/02-design/features/enterprise-legacy-modernization.design.md` (3,312 lines, 30 sections)

### version-specific-parser (2026-02-18, Design-vs-Implementation)
- **Match Rate**: 96% (112 items checked, 105 exact, 4 acceptable variations, 3 gaps)
- **Design**: `docs/02-design/features/version-specific-parser.design.md` (563 lines)
- **Analysis**: `docs/03-analysis/version-specific-parser.analysis.md` (v1.0)

### legacy-host-openframe-agents (2026-02-18, Plan-vs-Implementation)
- **Match Rate**: 97% (152 items checked, 148 exact, 0 acceptable, 4 minor path discrepancies)
- **Plan**: `docs/01-plan/features/legacy-host-openframe-agents.plan.md` (99 lines)
- **Analysis**: `docs/03-analysis/legacy-host-openframe-agents.analysis.md` (v1.0)

### legacy-modernization-analysis-ui (2026-02-19, Design-vs-Implementation)
- **Match Rate**: 98% (211 items checked, 207 exact, 3 acceptable variations, 1 gap)
- **Design**: `docs/02-design/features/legacy-modernization-analysis-ui.design.md` (884 lines)
- **Analysis**: `docs/03-analysis/legacy-modernization-analysis-ui.analysis.md` (v1.0)

### vllm-hybrid-search-artifact-view (2026-02-19, Plan-vs-Implementation)
- **Match Rate**: 97% (38 items checked, 36 exact, 1 partial, 0 missing)
- **Plan**: `docs/01-plan/features/vllm-hybrid-search-artifact-view.plan.md` (186 lines)
- **Analysis**: `docs/03-analysis/vllm-hybrid-search-artifact-view.analysis.md` (v1.0)
- **CRITICAL BUG**: `from ..core.config import settings` -- module exports `api_settings` not `settings`

### xsp-parser-faithful-wrapper (2026-02-19, Plan-vs-Implementation)
- **Match Rate**: 100% (51 items checked, 51 exact, 1 acceptable variation, 0 gaps)
- **Plan**: `docs/01-plan/features/xsp-parser-faithful-wrapper.plan.md` (266 lines)
- **Analysis**: `docs/03-analysis/xsp-parser-faithful-wrapper.analysis.md` (v1.0)

### rag-context-pollution-fix (2026-02-20, Design-vs-Implementation)
- **Match Rate**: 92% (25 items checked, 19 exact, 4 acceptable variations, 2 missing)
- **Design**: `docs/02-design/features/rag-context-pollution-fix.design.md` (642 lines, v2.0)
- **Analysis**: `docs/03-analysis/rag-context-pollution-fix.analysis.md` (v1.0)

### manual-reextraction-training-pipeline (2026-02-21, Plan-vs-Implementation)
- **Match Rate**: 71% (23 items checked, 10 exact, 5 acceptable variations, 8 gaps)
- **Plan**: `docs/01-plan/features/manual-reextraction-training-pipeline.plan.md` (Section 4, lines 446-698)
- **Analysis**: `docs/03-analysis/manual-reextraction-training-pipeline.analysis.md` (v1.0)

### unified-lora-dataset (2026-02-22, Design-vs-Implementation)
- **Match Rate**: 97% (155 items checked, 142 exact, 10 acceptable variations, 3 gaps)
- **Design**: `docs/02-design/features/unified-lora-dataset.design.md` (1030 lines)
- **Analysis**: `docs/03-analysis/unified-lora-dataset.analysis.md` (v1.0)
- **CRITICAL BUG**: `main.py:459` passes `config.manuals_dir` (Path) to `UnifiedSFTGenerator(config: ProcessorConfig)`

### unified-lora-dataset-v2 (2026-02-22, Design-vs-Implementation)
- **Match Rate**: 97% (68 items checked, 61 exact, 5 acceptable variations, 2 gaps)
- **Design**: `docs/02-design/features/unified-lora-dataset-v2.design.md` (636 lines)
- **Analysis**: `docs/03-analysis/unified-lora-dataset-v2.analysis.md` (v1.0)

### qwen3-dataset-pipeline (2026-02-24, Design-vs-Implementation)
- **Match Rate**: 96% (186 items checked, 163 exact, 15 acceptable variations, 8 gaps)
- **Design**: `docs/02-design/features/qwen3-dataset-pipeline.design.md` (2308 lines)
- **Analysis**: `docs/03-analysis/qwen3-dataset-pipeline.analysis.md` (v1.0)
