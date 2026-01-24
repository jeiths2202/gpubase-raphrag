# Smarter RAG - GPU Reallocation Guide

## Overview

This guide explains how to reallocate GPU resources for the Smarter RAG system:
- **Before**: Mistral NeMo 12B (Code LLM) - ~24GB VRAM
- **After**: CodeQwen 3B (Code LLM) - ~6GB VRAM + Learning LLM (Qwen2.5-7B QLoRA) - ~8GB VRAM

## Current GPU Allocation (Before)

| GPU | Service | VRAM Usage |
|-----|---------|------------|
| 4 | Qwen2.5-7B (RAG LLM) | ~14GB |
| 5 | Mistral NeMo 12B (Code LLM) | ~24GB |
| 6 | Vision LLM | ~16GB |
| 7 | Embeddings | ~14GB |

## Proposed GPU Allocation (After)

| GPU | Service | VRAM Usage |
|-----|---------|------------|
| 4 | Qwen2.5-7B (RAG LLM) | ~14GB |
| 5 | CodeQwen-1.5-3B (Code LLM) | ~6GB |
| 5 | Learning LLM (Qwen2.5-7B QLoRA) | ~8GB |
| 6 | Vision LLM | ~16GB |
| 7 | Embeddings | ~14GB |

## Step 1: Deploy Lighter Code LLM

### Option A: NIM Container (Recommended)
```bash
# Stop existing Mistral NeMo container
docker stop mistral-coder-graphrag

# Deploy CodeQwen 3B
docker run -d \
  --name codeqwen-graphrag \
  --gpus '"device=5"' \
  -p 12802:8000 \
  -e NVIDIA_VISIBLE_DEVICES=5 \
  nvcr.io/nim/qwen/qwen2.5-coder-3b-instruct:latest
```

### Option B: vLLM
```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-3B-Instruct \
  --port 12802 \
  --gpu-memory-utilization 0.3 \
  --tensor-parallel-size 1
```

### Option C: Ollama (Lightweight)
```bash
# On Ollama server
ollama pull qwen2.5-coder:3b

# Test
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5-coder:3b",
  "prompt": "def fibonacci(n):"
}'
```

## Step 2: Update Environment Variables

Add to `/opt/kms/.env`:
```bash
# ==================== Code LLM (Lighter Model) ====================
# Option 1: NIM/vLLM endpoint
CODE_LLM_API_URL=http://codeqwen-graphrag:8000/v1/chat/completions
CODE_LLM_MODEL=Qwen/Qwen2.5-Coder-3B-Instruct

# Option 2: Ollama fallback
CODE_LLM_USE_OLLAMA=true
CODE_LLM_OLLAMA_MODEL=qwen2.5-coder:3b

# ==================== Learning LLM ====================
ENABLE_LEARNING_LLM=true
LEARNING_LLM_AUTO_LOAD=false
LEARNING_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
LEARNING_LLM_DEVICE=cuda:1
LEARNING_LLM_LOAD_IN_4BIT=true
```

## Step 3: Configure Learning LLM

The Learning LLM will use GPU 5's remaining memory (~8GB) with 4-bit quantization:

```python
# Automatic configuration in main.py
# Set these environment variables:
ENABLE_LEARNING_LLM=true
LEARNING_LLM_AUTO_LOAD=false  # Load on first request
```

### Manual Loading (Admin API)
```bash
# Reload latest adapter
curl -X POST http://localhost:9000/api/v1/verified-knowledge/learning-llm/reload \
  -H "Content-Type: application/json" \
  -d '{"adapter_name": null}'

# Check status
curl http://localhost:9000/api/v1/verified-knowledge/learning-llm/status
```

## Step 4: Verify Configuration

### Check Code LLM
```bash
curl -X POST http://localhost:9000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Write a Python function to calculate factorial",
    "strategy": "code"
  }'
```

### Check Learning LLM
```bash
curl http://localhost:9000/api/v1/verified-knowledge/learning-llm/status
```

### Check GPU Usage
```bash
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv
```

## Memory Estimation

| Model | Precision | VRAM |
|-------|-----------|------|
| Qwen2.5-7B (RAG) | FP16 | ~14GB |
| CodeQwen-1.5-3B | FP16 | ~6GB |
| Qwen2.5-7B + QLoRA | INT4 | ~8GB |
| NV-EmbedQA-Mistral-7B | FP16 | ~14GB |

## Fallback Configuration

If the lighter code model underperforms, you can configure Ollama fallback:

```bash
# .env
CODE_LLM_FALLBACK_TO_OLLAMA=true
OLLAMA_CODE_MODEL=qwen2.5-coder:7b  # Larger Ollama model
```

## Troubleshooting

### OOM Error
```bash
# Reduce batch size
LEARNING_LLM_MAX_BATCH_SIZE=1

# Force garbage collection
curl -X POST http://localhost:9000/api/v1/verified-knowledge/learning-llm/unload
```

### Model Not Loading
```bash
# Check adapter directory
ls -la /opt/kms/models/qlora_adapters/

# Check logs
tail -f /opt/kms/logs/backend_*.log | grep -i learning
```

## Performance Comparison

| Metric | Mistral NeMo 12B | CodeQwen 3B |
|--------|------------------|-------------|
| VRAM | ~24GB | ~6GB |
| Inference Speed | ~50 tok/s | ~120 tok/s |
| Code Quality | Excellent | Good |
| Multilingual | Good | Excellent (CJK) |

CodeQwen 3B is recommended for this setup because:
1. Smaller memory footprint
2. Better CJK (Korean/Japanese) support
3. Optimized for code tasks
4. Allows Learning LLM on same GPU
