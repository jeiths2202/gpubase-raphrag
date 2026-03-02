# Task Instructions for AI Code Agent

**Date**: 2026-02-05
**Priority**: CRITICAL - Immediate Action Required
**Project**: Multi-LoRA v3 Hallucination Mitigation

---

## Executive Summary

The Multi-LoRA v3 system serving 24 TmaxSoft product adapters is experiencing severe hallucination issues due to training data quality problems. This document provides comprehensive analysis and actionable tasks for AI agents to resolve these issues.

### Critical Metrics
- **Total Training Examples**: 43,515 across 24 products
- **Data Quality Issues**: 23,470 examples (53.9%) contain errors
- **Severity**: 7 products have >60% error rate
- **Impact**: Model reproduces training data errors during inference

---

## Problem Statement

### Current Issues

#### 1. Hallucination Examples
```
❌ Model Output: "説明清めます" (broken encoding)
✅ Expected: "説明します"

❌ Model Output: "业务" (Chinese simplified characters)
✅ Expected: "業務" (Japanese)

❌ Model Output: "SOFO (Single Day Fault Opression)" (non-existent acronym)
✅ Expected: Valid technical terms only
```

#### 2. Root Causes

**A. Training Data Quality Issues (53.9% of data)**

| Issue Type | Average % | Description |
|------------|-----------|-------------|
| Broken Encoding | 26.3% | PDF parsing errors: "syste)m" instead of "system" |
| Chinese Characters | 20.5% | Simplified Chinese mixed into Japanese text (8,935 cases) |
| Excessive Repetition | 14.2% | Same word repeated >10% of content |
| Incomplete Sentences | 7.3% | Sentences starting mid-context (e.g., "で構成されています") |

**B. Critical Products (Priority 1 - 7 products with >60% errors)**

| Product | Examples | Error Rate | Primary Issues |
|---------|----------|------------|----------------|
| tmax_v2 | 4,785 | 81.1% | Encoding (54.6%), Chinese (44.6%) |
| openframe_batch_v2 | 2,443 | 63.5% | Encoding (33.6%), Repetition (22.5%) |
| protrieve_v2 | 561 | 63.5% | Encoding (41.2%), Chinese (30.7%) |
| tibero7_v2 | 8,870 | 63.3% | Chinese (38.4%), Encoding (32.2%) |
| ofpli_v2 | 372 | 62.9% | Chinese (48.9%), Encoding (29.6%) |
| prosort_v2 | 184 | 61.4% | Chinese (44.0%), Encoding (20.1%) |
| ofcobol_v2 | 288 | 60.1% | Chinese (39.6%), Repetition (21.5%) |

**C. Model Behavior**
- The LoRA adapters learned corrupted patterns from training data
- During inference, models reproduce the same errors
- Parameter tuning alone is insufficient (temperature 0.05 still produces errors)

---

## File Locations

### Training Data
```
Base Path: /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/uploads/summaries/multi_lora_v3/

Structure:
├── tmax_v2/
│   ├── train.json          # 4,785 examples (81.1% errors)
│   ├── eval.json
│   └── stats.json
├── tibero7_v2/
│   ├── train.json          # 8,870 examples (63.3% errors)
│   └── ...
├── openframe_batch_v2/
│   ├── train.json          # 2,443 examples (63.5% errors)
│   └── ...
└── ... (21 more products)
```

### Quality Validation Reports
```
Location: /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/test_0203/

Files:
├── DATA_QUALITY_REPORT_COMPLETE.md     # 24-product comprehensive report
├── PROBLEM_SAMPLES.md                   # Detailed error samples
├── quality_validation_report.json      # Machine-readable results (3.0 MB)
├── problem_samples.json                 # Sample JSON data
├── validate_training_data.py           # Validation script
└── extract_problem_samples.py          # Sample extraction script
```

### Current API Server
```
File: /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/test_0203/lora_api_server_v3.py
Port: 12815
GPU: 5
Base Model: Qwen/Qwen2.5-7B-Instruct
Adapters: 24 products

Current Parameters (already optimized):
- max_tokens: 300 (reduced from 512)
- temperature: 0.1 (reduced from 0.7)
- top_p: 0.85 (reduced from 0.92)
- top_k: 40 (reduced from 50)
- repetition_penalty: 1.3 (increased from 1.25)
```

### Existing RAG Infrastructure
```
Services:
- Neo4j Graph DB: ports 7474 (HTTP), 7687 (Bolt) - RUNNING ✅
- Embedding Service: port 12801 (nemo-embedding) - STOPPED ❌

Code:
- app/api/services/conversation_rag_integration.py
- app/api/services/ims_rag_integration.py
- app/api/services/local_rag_adapter.py
- app/api/services/local_rag_service.py
- app/api/services/multimodal_embedding.py

Docker:
- docker/docker-compose.yml (nemo-embedding service defined)
```

---

## Solution Approach

### Phase 1: Immediate Action (Recommended - 70% Improvement)

#### Task 1: RAG Integration with LoRA

**Objective**: Implement hybrid RAG + LoRA system to provide accurate context and reduce hallucinations by 70%

**Current State**:
```python
# ❌ LoRA-only approach (causing hallucinations)
response = lora_model(user_query)
# Model generates from corrupted training patterns
```

**Target State**:
```python
# ✅ RAG + LoRA hybrid approach
context = vector_search(user_query, product=adapter_name)  # Retrieve accurate docs
response = lora_model(user_query, context=context)          # Generate with context
# Model uses retrieved documents as ground truth
```

**Implementation Steps**:

1. **Start Embedding Service**
   ```bash
   cd /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/docker
   docker compose up -d nemo-embedding

   # Verify service
   curl http://localhost:12801/v1/models
   ```

2. **Index Priority 1 Product Documents** (7 products)

   Target products:
   - tmax_v2
   - tibero7_v2
   - openframe_batch_v2
   - protrieve_v2
   - ofpli_v2
   - prosort_v2
   - ofcobol_v2

   Source documents location:
   ```
   /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/uploads/documents/
   ```

   Action: Use existing document processor to embed into Neo4j vector index
   ```bash
   python scripts/cli_document_processor.py \
     --products tmax,tibero7,openframe_batch,protrieve,ofpli,prosort,ofcobol \
     --embed \
     --neo4j-uri bolt://localhost:7687
   ```

3. **Modify LoRA API Server to Use RAG**

   File: `test_0203/lora_api_server_v3.py`

   Add RAG integration:
   ```python
   # Import RAG service
   from app.api.services.local_rag_service import LocalRAGService

   # Initialize RAG service at startup
   rag_service = LocalRAGService(
       neo4j_uri="bolt://localhost:7687",
       neo4j_user="neo4j",
       neo4j_password=os.getenv("NEO4J_PASSWORD"),
       embedding_url="http://localhost:12801"
   )

   # Modify chat endpoint (around line 288)
   @app.post("/chat", response_model=ChatResponse)
   async def chat(request: ChatRequest):
       global model, tokenizer

       # ... existing adapter validation ...

       # NEW: Retrieve context from RAG
       rag_results = await rag_service.search(
           query=request.message,
           product=request.adapter,
           top_k=3  # Get top 3 relevant chunks
       )

       # NEW: Build context-aware prompt
       context_text = "\n\n".join([r["content"] for r in rag_results])

       messages = [
           {
               "role": "system",
               "content": f"You are a {ADAPTER_CONFIGS[request.adapter]['description']} expert. "
                         f"Use the following documentation context to provide accurate answers.\n\n"
                         f"Context:\n{context_text}"
           },
           {"role": "user", "content": request.message}
       ]

       # ... rest of existing generation code ...
   ```

4. **Test RAG Integration**

   Test script:
   ```python
   # test_rag_integration.py
   import requests

   # Test with known hallucination case
   response = requests.post("http://localhost:12815/chat", json={
       "adapter": "openframe_base_v2",
       "message": "OpenFrame/Baseシステムの紹介",
       "temperature": 0.1
   })

   print("Response:", response.json()["response"])

   # Verify:
   # - No "説明清めます" (broken encoding)
   # - No "业务" (Chinese characters)
   # - No "SOFO" (non-existent acronyms)
   # - Accurate technical content from documents
   ```

5. **A/B Testing Setup**

   Compare:
   - Current LoRA-only (port 12815, no RAG)
   - New RAG + LoRA (same port, with RAG)

   Metrics to track:
   - Hallucination rate (manual review of 100 responses)
   - Response accuracy (compared to source documents)
   - User satisfaction (if available)

**Expected Outcomes**:
- 70% reduction in hallucination occurrences
- Responses grounded in actual documentation
- Immediate deployment without retraining
- Works in parallel with data cleaning efforts

**Estimated Time**: 1-2 days

---

### Phase 2: Data Cleaning (1-2 weeks)

#### Task 2: Automated Data Filtering

**Objective**: Remove corrupted training examples from Priority 1 products

**Implementation**:

1. **Run Automated Filter**
   ```bash
   cd /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/test_0203

   python filter_training_data.py \
     --input /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/uploads/summaries/multi_lora_v3 \
     --output /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/uploads/summaries/multi_lora_v3_cleaned \
     --products tmax_v2,tibero7_v2,openframe_batch_v2,protrieve_v2,ofpli_v2,prosort_v2,ofcobol_v2 \
     --filters broken_encoding,chinese_simplified,excessive_repetition,incomplete_sentence
   ```

2. **Create Filter Script** (if not exists)

   File: `test_0203/filter_training_data.py`

   ```python
   #!/usr/bin/env python3
   """
   Automated training data cleaning script
   Removes examples with quality issues identified by validation
   """
   import json
   import re
   from pathlib import Path
   from collections import Counter

   def is_broken_encoding(text: str) -> bool:
       """Check for encoding errors"""
       patterns = [
           r'[�]',
           r'syste\s*\)\s*m',
           r'\w+\s*\)\s*\w+',
           r'[a-zA-Z]{2,}\s*[）】]',
       ]
       return any(re.search(p, text) for p in patterns)

   def has_chinese_simplified(text: str) -> bool:
       """Check for Chinese simplified characters"""
       chinese_chars = ['清', '业', '为', '关', '产', '说', '应', '实',
                       '进', '时', '后', '动', '来', '现', '两', '义',
                       '数', '类', '图', '认']
       return any(char in text for char in chinese_chars)

   def has_excessive_repetition(text: str) -> bool:
       """Check for excessive repetition (>10% same word)"""
       words = text.split()
       if len(words) < 10:
           return False
       most_common = Counter(words).most_common(1)[0]
       return most_common[1] > len(words) * 0.1

   def is_incomplete_sentence(text: str) -> bool:
       """Check if sentence starts mid-context"""
       patterns = [r'^[ぁ-ん]', r'^で', r'^に', r'^を', r'^が']
       return any(re.match(p, text) for p in patterns)

   def filter_dataset(input_file: Path, output_file: Path) -> dict:
       """Filter a single product's training data"""
       with open(input_file) as f:
           data = json.load(f)

       filtered_data = []
       removed = {'broken_encoding': 0, 'chinese_simplified': 0,
                 'excessive_repetition': 0, 'incomplete_sentence': 0}

       for item in data:
           text = item.get('text', '')
           try:
               assistant = text.split('<|im_start|>assistant')[1].split('<|im_end|>')[0].strip()
           except:
               continue

           # Check all filters
           if is_broken_encoding(assistant):
               removed['broken_encoding'] += 1
               continue
           if has_chinese_simplified(assistant):
               removed['chinese_simplified'] += 1
               continue
           if has_excessive_repetition(assistant):
               removed['excessive_repetition'] += 1
               continue
           if is_incomplete_sentence(assistant):
               removed['incomplete_sentence'] += 1
               continue

           filtered_data.append(item)

       # Save cleaned data
       output_file.parent.mkdir(parents=True, exist_ok=True)
       with open(output_file, 'w', encoding='utf-8') as f:
           json.dump(filtered_data, f, ensure_ascii=False, indent=2)

       return {
           'original': len(data),
           'cleaned': len(filtered_data),
           'removed': sum(removed.values()),
           'removal_rate': sum(removed.values()) / len(data),
           'removed_by_type': removed
       }

   # Main execution logic here...
   ```

**Expected Results** (Priority 1 products):
```
Before: 17,503 examples
After:  ~7,200 examples (59% removed)

Breakdown:
- Broken encoding removed: 7,401
- Chinese characters removed: 6,560
- Excessive repetition removed: 3,513
- Incomplete sentences removed: 918
```

**Estimated Time**: 2-3 days

#### Task 3: Manual Quality Review

**Objective**: Human verification of edge cases

**Process**:
1. Sample 100 examples from each Priority 1 product (700 total)
2. Manual review for:
   - False positives (good data incorrectly filtered)
   - False negatives (bad data that passed filters)
   - Edge cases requiring new filter rules
3. Update filter rules and re-run

**Estimated Time**: 3-5 days

---

### Phase 3: Data Augmentation (2-3 weeks)

#### Task 4: PDF Re-parsing

**Objective**: Re-extract training data from source PDFs using better OCR

**Implementation**:

```bash
# Re-parse Priority 1 product documents
python scripts/cli_document_processor.py \
  --input /raid/users/ofuser/documents/source_pdfs/ \
  --output /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/uploads/summaries/multi_lora_v3_reprocessed \
  --parser tesseract \
  --lang jpn \
  --min-confidence 0.9 \
  --validate \
  --products tmax,tibero7,openframe_batch,protrieve,ofpli,prosort,ofcobol
```

**Parameters**:
- `--parser tesseract`: Use Tesseract OCR engine (better than default)
- `--lang jpn`: Japanese language model
- `--min-confidence 0.9`: Only accept high-confidence text recognition
- `--validate`: Run quality checks during extraction

**Expected**: +40-60% more examples from previously missed PDF sections

**Estimated Time**: 1 week

#### Task 5: Data Augmentation Techniques

**A. Question Paraphrasing**

Generate 3 variations of each question:
```python
original = "OpenFrameの主な機能は何ですか？"

variations = [
    "OpenFrameはどのような機能を提供していますか？",
    "OpenFrameの代表的な機能について教えてください",
    "OpenFrameが持つ主要機能を説明してください"
]
```

**B. Back Translation (English → Japanese)**

If English documentation exists:
1. Translate English docs to Japanese
2. Validate translation quality
3. Add as training examples

**Target**: Increase Priority 1 data from 7,200 → 21,000+ examples (3x augmentation)

**Estimated Time**: 1-2 weeks

---

### Phase 4: Model Retraining (1 week)

#### Task 6: Retrain Priority 1 Adapters

**Objective**: Train new LoRA adapters on cleaned + augmented data

**Training Configuration**:
```python
# Improved training config to prevent overfitting
TrainingArguments(
    output_dir="/raid/users/ofuser/qlora/outputs_v4",
    num_train_epochs=2,              # Reduced from 3
    learning_rate=1e-4,              # Reduced from 2e-4
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    weight_decay=0.01,               # Increased from 0.001
    logging_steps=10,
    eval_strategy="steps",
    eval_steps=50,                   # Frequent evaluation
    save_steps=100,
    save_total_limit=2,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    early_stopping_patience=3,       # Stop if no improvement
    warmup_steps=100,
    fp16=True,
    optim="paged_adamw_8bit",
)
```

**Validation Strategy**:
- 80% training, 20% validation split
- Monitor validation loss to prevent overfitting
- Test on holdout hallucination cases

**Estimated Time**: 1 week (parallel training on multiple GPUs)

---

## Success Criteria

### Phase 1 (RAG Integration) - Week 1
- [ ] Embedding service running on port 12801
- [ ] Priority 1 products indexed in Neo4j (7 products)
- [ ] RAG + LoRA hybrid service deployed
- [ ] Hallucination rate reduced by >60% (manual review of 100 responses)
- [ ] Zero occurrences of "説明清めます", "业务", "SOFO" in test responses

### Phase 2 (Data Cleaning) - Week 2-3
- [ ] Automated filter script created and tested
- [ ] Priority 1 training data filtered (17,503 → 7,200 examples)
- [ ] Manual review completed (700 samples)
- [ ] Filter accuracy >95% (validated on manual review)

### Phase 3 (Data Augmentation) - Week 4-5
- [ ] Priority 1 PDFs re-parsed with Tesseract
- [ ] Question paraphrasing completed (3x variations)
- [ ] Training data augmented to 21,000+ examples
- [ ] Data quality validation passed (>90% clean)

### Phase 4 (Retraining) - Week 6
- [ ] New LoRA adapters trained on cleaned data
- [ ] Validation loss converged without overfitting
- [ ] A/B testing shows >80% improvement over baseline
- [ ] Production deployment completed

---

## Priority Order

### CRITICAL (This Week)
1. ✅ **Task 1: RAG Integration** - 70% improvement without retraining

### HIGH (Week 2-3)
2. **Task 2: Automated Data Filtering** - Clean existing data
3. **Task 3: Manual Quality Review** - Validate filtering

### MEDIUM (Week 4-5)
4. **Task 4: PDF Re-parsing** - Extract more clean data
5. **Task 5: Data Augmentation** - Expand training set

### LOWER (Week 6+)
6. **Task 6: Model Retraining** - New adapters on clean data

---

## Key Contacts & Resources

### File Paths Summary
```
Training Data:     /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/uploads/summaries/multi_lora_v3/
Validation Reports: /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/test_0203/
API Server:        /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/test_0203/lora_api_server_v3.py
RAG Services:      /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/app/api/services/
Docker Config:     /raid/users/ofuser/work/ijswork/gpubase-raphrag-new/docker/docker-compose.yml
```

### Service Endpoints
```
LoRA API:         http://localhost:12815 (GPU 5)
Neo4j HTTP:       http://localhost:7474
Neo4j Bolt:       bolt://localhost:7687
Embedding:        http://localhost:12801 (currently stopped)
```

### Key Environment Variables
```bash
NEO4J_PASSWORD=<set in .env>
NGC_API_KEY=<required for NIM embedding service>
CUDA_VISIBLE_DEVICES=5  # For LoRA API server
```

---

## Next Steps for AI Agent

1. **Start with Task 1 (RAG Integration)**:
   - Read existing RAG service code in `app/api/services/`
   - Start embedding service: `docker compose up -d nemo-embedding`
   - Implement RAG integration in LoRA API server
   - Test and measure hallucination reduction

2. **Report Progress**:
   - Document implementation steps
   - Share test results (before/after examples)
   - Identify any blockers or issues

3. **Proceed to Task 2** (after Task 1 success):
   - Create automated filter script
   - Process Priority 1 products
   - Generate cleaning report

---

## Notes

- **Parallel Execution**: RAG integration (Phase 1) can run in parallel with data cleaning (Phase 2)
- **Incremental Deployment**: Deploy RAG for Priority 1 products first, then expand to others
- **Monitoring**: Set up logging to track hallucination rates in production
- **Rollback Plan**: Keep original LoRA-only service available as backup on different port

---

**Document Version**: 1.0
**Last Updated**: 2026-02-05
**Status**: Ready for AI Agent Execution
