# Enterprise CPT/DPO Stability & Multi-LoRA Governance System

> Architecture Document v1.0 | 2026-02-15

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CI/CD PIPELINE ORCHESTRATOR                     │
│                        (pipeline.py)                                │
├────────┬────────┬────────┬────────┬────────┬────────────────────────┤
│ Step 1 │ Step 2 │ Step 3 │ Step 4 │ Step 5 │ Step 6               │
│  CPT   │ Hallu- │ Drift  │Quality │ Beta   │ Deploy               │
│ Valid. │ cina.  │ Anal.  │ Gate   │ Auto   │ Decision             │
│        │ Guard  │        │        │ Tune   │                      │
└───┬────┴───┬────┴───┬────┴───┬────┴───┬────┴───┬────────────────────┘
    │        │        │        │        │        │
    ▼        ▼        ▼        ▼        ▼        ▼
┌────────────────────────────────────────────────────────────────────┐
│                        GOVERNANCE MODULES                          │
│                                                                    │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐        │
│  │ kl_metrics   │  │ hallucination │  │ drift_monitor    │        │
│  │              │  │ _guard        │  │                  │        │
│  │ • Token KL   │  │ • Citation    │  │ • Z-score detect │        │
│  │ • Sequence KL│  │ • Self-verify │  │ • Moving average │        │
│  │ • Histogram  │  │ • Fabrication │  │ • Trend analysis │        │
│  └──────┬───────┘  └──────┬────────┘  └──────┬───────────┘        │
│         │                 │                   │                    │
│  ┌──────▼─────────────────▼───────────────────▼──────────┐        │
│  │              cpt_validation.py                         │        │
│  │  • KL divergence    • Perplexity delta                │        │
│  │  • Task score       • Response length                  │        │
│  │  • Token distribution shift (JS divergence)            │        │
│  └───────────────────────┬────────────────────────────────┘        │
│                          │                                         │
│  ┌───────────────────────▼────────────────────────────────┐        │
│  │              quality_gate.py                           │        │
│  │  22 Products × 5 Gates = 110 Quality Checks           │        │
│  │  → SQLite DB   → Prometheus metrics                    │        │
│  └───────────────────────┬────────────────────────────────┘        │
│                          │                                         │
│  ┌───────────────────────▼────────────────────────────────┐        │
│  │              beta_autotune.py                          │        │
│  │  4 Signals → Weighted Adjustment → Beta Update         │        │
│  │  KL(0.4) + Hall(0.25) + Reward(0.2) + Task(0.15)     │        │
│  └────────────────────────────────────────────────────────┘        │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                     SERVING INFRASTRUCTURE                         │
│                                                                    │
│  ┌────────────────────────────────────────────────────────┐        │
│  │              adapter_router.py                         │        │
│  │                                                        │        │
│  │  Base Model (Qwen2.5-7B, 4-bit NF4, shared)          │        │
│  │       │                                                │        │
│  │       ├── jeus_v2 adapter (~8MB)                      │        │
│  │       ├── tibero7_v2 adapter                          │        │
│  │       ├── openframe_base_v2 adapter                   │        │
│  │       ├── ... (22 product adapters)                   │        │
│  │       └── openframe_gateway_v2 adapter                │        │
│  │                                                        │        │
│  │  Features:                                             │        │
│  │  • Keyword-based routing                               │        │
│  │  • LRU adapter eviction (max 5 loaded)                │        │
│  │  • Governance gate integration (block unapproved)      │        │
│  │  • Health check + latency metrics                     │        │
│  └────────────────────────────────────────────────────────┘        │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                     MONITORING & DASHBOARD                         │
│                                                                    │
│  SQLite DB (metrics.db)     Grafana Dashboard (JSON)              │
│  • quality_gate_runs        • KL trend per product                │
│  • product_gate_results     • Hallucination rate trend            │
│  • drift_metrics            • Token entropy shift                 │
│                             • Embedding cosine shift              │
│  Prometheus Exposition      • Active drift alerts table           │
│  • governance_kl_divergence                                       │
│  • governance_hallucination_rate                                  │
│  • governance_task_score                                          │
│  • governance_quality_gate_pass                                   │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Layout

```
scripts/
├── governance/                          # Governance system
│   ├── __init__.py                      # Package + version
│   ├── governance_config.py             # Central config (thresholds, products)
│   ├── kl_metrics.py                    # KL divergence calculator
│   ├── cpt_validation.py               # CPT automated validation
│   ├── hallucination_guard.py           # 3-stage hallucination detection
│   ├── quality_gate.py                  # 22-product unified gate
│   ├── drift_monitor.py                 # Drift tracking + dashboard
│   ├── beta_autotune.py                 # DPO beta auto-tuning
│   ├── pipeline.py                      # CI/CD pipeline orchestrator
│   └── ARCHITECTURE.md                  # This document
│
├── serving/                             # Serving infrastructure
│   ├── __init__.py
│   └── adapter_router.py               # Multi-LoRA dynamic routing
│
└── (existing training scripts)
```

**Runtime output:**
```
/raid/users/ofuser/qlora/governance/      # Governance outputs
├── metrics.db                            # SQLite metrics store
├── beta_history.json                     # Beta tuning history
├── pipeline_YYYYMMDD_HHMMSS/            # Per-run directory
│   ├── config.json                       # Frozen config (reproducibility)
│   ├── validate_cpt.json                 # CPT validation results
│   ├── hallucination_guard.json          # Hallucination results
│   ├── drift_analysis.json               # Drift report
│   ├── drift_dashboard.json              # Grafana dashboard config
│   ├── quality_gate.json                 # Quality gate results
│   ├── prometheus_metrics.txt            # Prometheus exposition
│   ├── beta_autotune.json                # Beta adjustment results
│   ├── deployment_decision.json          # Final deploy/block decision
│   └── pipeline_report.json             # Full pipeline summary
```

---

## 3. Module Dependency Graph

```
governance_config.py          ← foundation (no deps)
        │
        ├── kl_metrics.py     ← uses thresholds
        │       │
        ├── cpt_validation.py ← uses kl_metrics
        │       │
        ├── hallucination_guard.py  ← independent
        │       │
        ├── drift_monitor.py  ← uses governance_config
        │       │
        ├── quality_gate.py   ← aggregates all metrics
        │       │
        ├── beta_autotune.py  ← uses governance_config
        │       │
        └── pipeline.py       ← orchestrates all modules
                │
        adapter_router.py     ← uses governance_config + gate results
```

---

## 4. Execution Order

### Full Pipeline

```
1. [CONFIG]      Load/create GovernanceConfig
2. [VALIDATE]    CPT Validation
                   ├── Load base model + CPT adapter
                   ├── For each of 22 products:
                   │   ├── KL divergence (kl_metrics)
                   │   ├── Perplexity (base vs CPT)
                   │   ├── Task score (cloze test)
                   │   ├── Response length delta
                   │   └── Token distribution shift (JS divergence)
                   └── → validate_cpt.json

3. [HALLU]       Hallucination Guard
                   ├── For each product:
                   │   ├── Stage 1: Citation enforcement
                   │   ├── Stage 2: Self-verification pass
                   │   └── Stage 3: Fabrication detection
                   └── → hallucination_guard.json

4. [DRIFT]       Drift Analysis
                   ├── Load historical metrics from DB
                   ├── Z-score computation per metric
                   ├── Moving average + trend regression
                   ├── Alert classification
                   └── → drift_analysis.json + drift_dashboard.json

5. [GATE]        Quality Gate
                   ├── Aggregate results from steps 2-4
                   ├── Per-product pass/fail (5 gates × 22 products)
                   ├── Overall deployment decision
                   ├── Store to SQLite DB
                   └── → quality_gate.json + prometheus_metrics.txt

6. [BETA]        Beta Auto-Tune
                   ├── Compute 4 signals per product
                   ├── Weighted adjustment (KL:0.4, Hall:0.25, Reward:0.2, Task:0.15)
                   ├── Clamp to [min_beta, max_beta]
                   ├── Update history
                   └── → beta_autotune.json + beta_history.json

7. [DEPLOY]      Deployment Decision
                   ├── If quality_gate.overall_pass AND auto_deploy: APPROVED
                   ├── If quality_gate.overall_pass AND !auto_deploy: MANUAL_REVIEW
                   └── If !quality_gate.overall_pass: BLOCKED
```

### CLI Commands

```bash
# Full pipeline (mock mode, no GPU needed)
python -m scripts.governance.pipeline --mock

# Full pipeline with models
python -m scripts.governance.pipeline --gpu 4

# With custom config
python -m scripts.governance.pipeline --config /path/to/config.json --gpu 4

# Single product
python -m scripts.governance.pipeline --product jeus_v2 --mock

# CPT validation only
python -m scripts.governance.cpt_validation \
    --base-model Qwen/Qwen2.5-7B-Instruct \
    --cpt-adapter /raid/users/ofuser/qlora/outputs/cpt_adapter \
    --eval-data uploads/summaries/multi_lora_v9/eval_all.json \
    --output /raid/users/ofuser/qlora/governance/cpt_validation.json \
    --gpu 4
```

---

## 5. Config Schema

```json
{
  "base_model": "Qwen/Qwen2.5-7B-Instruct",
  "cpt_model": "Qwen/Qwen2.5-72B-Instruct",
  "adapter_base_dir": "/raid/users/ofuser/qlora/outputs",
  "dataset_base_dir": "uploads/summaries/multi_lora_v9",
  "governance_output_dir": "/raid/users/ofuser/qlora/governance",
  "metrics_db_path": "/raid/users/ofuser/qlora/governance/metrics.db",
  "products": ["jeus_v2", "tibero7_v2", "...all 22 products..."],
  "quality_gate": {
    "kl": {
      "warn": 5.0,
      "fail": 10.0,
      "critical": 15.0,
      "max_std": 3.0
    },
    "hallucination": {
      "max_rate": 0.05,
      "min_citation_ratio": 0.8,
      "max_fabrication_score": 0.1,
      "confidence_threshold": 0.7
    },
    "perplexity": {
      "max_increase_pct": 10.0,
      "warn_increase_pct": 5.0
    },
    "drift": {
      "z_score_warn": 2.0,
      "z_score_critical": 3.0,
      "moving_avg_window": 10,
      "min_history_points": 5
    },
    "beta_tuning": {
      "initial_beta": 0.1,
      "min_beta": 0.01,
      "max_beta": 0.5,
      "adjustment_step": 0.02,
      "kl_target": 5.0,
      "reward_margin_min": 0.5
    },
    "min_task_score": 0.7,
    "min_eval_samples": 5,
    "require_all_products_pass": true
  },
  "gpu_ids": [4, 5, 6, 7],
  "max_retries": 2,
  "parallel_eval": true,
  "auto_deploy": false
}
```

---

## 6. Example Metric Outputs

### CPT Validation Result (per product)

```json
{
  "product_id": "jeus_v2",
  "kl_divergence": 3.42,
  "kl_std": 1.15,
  "perplexity_base": 12.8,
  "perplexity_cpt": 11.2,
  "perplexity_delta": -1.6,
  "perplexity_delta_pct": -12.5,
  "task_score_base": 0.73,
  "task_score_cpt": 0.81,
  "task_score_delta": 0.08,
  "length_mean_base": 85.3,
  "length_mean_cpt": 91.7,
  "length_delta": 6.4,
  "length_delta_pct": 7.5,
  "token_distribution_shift": 0.089,
  "num_eval_samples": 210,
  "passed": true,
  "fail_reasons": []
}
```

### Quality Gate Result (per product)

```json
{
  "product_id": "jeus_v2",
  "kl_divergence": 3.42,
  "hallucination_rate": 0.023,
  "task_score": 0.81,
  "drift_status": "stable",
  "perplexity_delta_pct": -12.5,
  "kl_pass": true,
  "hallucination_pass": true,
  "task_score_pass": true,
  "drift_pass": true,
  "perplexity_pass": true,
  "overall_pass": true,
  "approval_status": "approved",
  "fail_reasons": [],
  "warnings": []
}
```

### Beta Auto-Tuning Result

```json
{
  "product_id": "jeus_v2",
  "beta_old": 0.1,
  "beta_new": 0.08,
  "adjustment": -0.02,
  "reason": "Beta decreased (dominant: kl). Signals: KL=7.200, Hallucination=2.0%",
  "signals": {
    "kl": {"value": -0.03, "input": 7.2},
    "hallucination": {"value": -0.005, "input": 0.02},
    "reward_margin": {"value": 0.0, "input": 0.65},
    "task_accuracy": {"value": 0.0, "input": 0.81}
  },
  "confidence": 0.75,
  "timestamp": "2026-02-15T12:00:00+00:00"
}
```

### Drift Alert

```json
{
  "product_id": "openframe_osc_v2",
  "metric_name": "kl_divergence",
  "current_value": 8.45,
  "mean_value": 4.12,
  "std_value": 1.33,
  "z_score": 3.25,
  "drift_level": "critical",
  "moving_avg": 5.67,
  "trend_direction": "increasing",
  "message": "[CRITICAL] openframe_osc_v2/kl_divergence: z-score=3.25 exceeds threshold"
}
```

### Hallucination Guard Result

```json
{
  "grounded": true,
  "missing_citations": 1,
  "total_claims": 8,
  "citation_ratio": 0.875,
  "fabrication_score": 0.03,
  "fabricated_entities": [],
  "self_verification_score": 0.85,
  "confidence": 0.87
}
```

### Pipeline Report

```json
{
  "run_id": "pipeline_20260215_120000",
  "timestamp": "2026-02-15T12:05:30+00:00",
  "config_hash": "a1b2c3d4",
  "total_steps": 6,
  "completed_steps": 6,
  "failed_steps": 0,
  "skipped_steps": 0,
  "overall_status": "success",
  "deployment_decision": "manual_review",
  "duration_total_ms": 45230.5,
  "steps": [
    {"step_name": "validate_cpt", "status": "success", "duration_ms": 15420},
    {"step_name": "hallucination_guard", "status": "success", "duration_ms": 12300},
    {"step_name": "drift_analysis", "status": "success", "duration_ms": 850},
    {"step_name": "quality_gate", "status": "success", "duration_ms": 120},
    {"step_name": "beta_autotune", "status": "success", "duration_ms": 45},
    {"step_name": "deployment_decision", "status": "success", "duration_ms": 5}
  ]
}
```

---

## 7. Integration Points

### Existing System

| Integration | File | Method |
|-------------|------|--------|
| Training callback | `resume_utils.py` | Extend `TrainingStateTracker` |
| DPO metrics | `dpo_pipeline/evaluation/metrics.py` | Reuse `ProductEvalResult` |
| LoRA API server | `lora_api_server_v3.py` | Add governance metadata endpoint |
| Perplexity eval | `evaluate_perplexity.py` | Compatible with `CPTValidator` |

### External Systems

| System | Integration |
|--------|------------|
| Grafana | `drift_dashboard.json` import |
| Prometheus | `prometheus_metrics.txt` scrape |
| CI/CD (Jenkins/GitHub Actions) | `pipeline_report.json` parse |
| PostgreSQL | Extend SQLite → PostgreSQL adapter |

---

## 8. Design Decisions

### Why SQLite (not PostgreSQL)?

- 학습 서버에서 독립 실행 가능 (DB 서버 불필요)
- 파이프라인 재현성: DB 파일 자체가 아티팩트
- 추후 PostgreSQL 마이그레이션 용이 (쿼리 호환)

### Why per-product adapters (not merged)?

- 제품 간 지식 간섭 방지
- 개별 제품 롤백 가능
- 제품별 독립적 quality gate 적용

### Why rule-based hallucination detection + LLM self-verify?

- 규칙 기반: 빠르고 결정적 (citation/entity check)
- LLM 자기 검증: 의미적 grounding 검증 (보완)
- 3단계 조합으로 false positive/negative 최소화

### Why beta auto-tune with 4 signals?

- 단일 신호 의존 시 과보정 위험
- 가중 평균 + 스텝 크기 제한으로 안정성 확보
- 이력 기반 추세 분석으로 진동 방지
