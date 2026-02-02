#!/usr/bin/env python3
"""
8개 제품 LoRA 어댑터 API 서버
FastAPI + Transformers + PEFT
GPU 5, 포트 12810
"""

import os
os.environ["CUDA_VISIBLE_DEVICES"] = "5"

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
import uvicorn
from contextlib import asynccontextmanager

# 설정
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
PORT = 12810
BASE_PATH = "/raid/users/ofuser/qlora/outputs"

# 8개 제품 어댑터 정의
ADAPTER_CONFIGS = {
    "openframe_mvs": {
        "path": f"{BASE_PATH}/openframe_qlora_adapter/openframe_ko_20260130_150120",
        "description": "OpenFrame MVS 7.1 (38개 PDF 문서)"
    },
    "msp_openframe": {
        "path": f"{BASE_PATH}/qlora_adapters/msp_openframe/openframe_ko_20260131_131057",
        "description": "MSP OpenFrame"
    },
    "vos3_openframe": {
        "path": f"{BASE_PATH}/qlora_adapters/vos3_openframe/openframe_ko_20260131_173439",
        "description": "VOS3 OpenFrame"
    },
    "xsp_openframe": {
        "path": f"{BASE_PATH}/qlora_adapters/xsp_openframe/openframe_ko_20260201_092321",
        "description": "XSP OpenFrame"
    },
    "tibero7": {
        "path": f"{BASE_PATH}/qlora_adapters/tibero7/openframe_ko_20260131_184925",
        "description": "Tibero 7 Database"
    },
    "tmax": {
        "path": f"{BASE_PATH}/qlora_adapters/tmax/openframe_ko_20260201_135130",
        "description": "Tmax TP Monitor"
    },
    "ofcobol": {
        "path": f"{BASE_PATH}/qlora_adapters/ofcobol/openframe_ko_20260201_085854",
        "description": "OpenFrame COBOL"
    },
    "ofasm": {
        "path": f"{BASE_PATH}/qlora_adapters/ofasm/openframe_ko_20260201_030623",
        "description": "OpenFrame ASM"
    },
}

# 전역 변수
model = None
tokenizer = None
loaded_adapters: Dict[str, bool] = {}

class ChatRequest(BaseModel):
    adapter: str
    message: str
    max_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.7

class ChatResponse(BaseModel):
    adapter: str
    response: str
    tokens_generated: int

def load_base_model():
    """베이스 모델 로드"""
    global model, tokenizer

    print("=" * 60)
    print("베이스 모델 로드 중...")
    print("=" * 60)

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)

    print(f"✅ 베이스 모델 로드 완료: {BASE_MODEL}")
    return model, tokenizer

def load_adapter(adapter_name: str):
    """어댑터 로드"""
    global model, loaded_adapters

    if adapter_name not in ADAPTER_CONFIGS:
        raise ValueError(f"Unknown adapter: {adapter_name}")

    if adapter_name in loaded_adapters and loaded_adapters[adapter_name]:
        # 이미 로드된 어댑터로 전환
        model.set_adapter(adapter_name)
        return

    adapter_path = ADAPTER_CONFIGS[adapter_name]["path"]

    if not os.path.exists(os.path.join(adapter_path, "adapter_model.safetensors")):
        raise ValueError(f"Adapter not found: {adapter_path}")

    print(f"어댑터 로드 중: {adapter_name}")

    # 첫 번째 어댑터인 경우 PeftModel로 래핑
    if not loaded_adapters:
        model = PeftModel.from_pretrained(model, adapter_path, adapter_name=adapter_name)
    else:
        # 추가 어댑터 로드
        model.load_adapter(adapter_path, adapter_name=adapter_name)

    model.set_adapter(adapter_name)
    loaded_adapters[adapter_name] = True
    print(f"✅ 어댑터 로드 완료: {adapter_name}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 모델 로드
    load_base_model()

    # 모든 어댑터 사전 로드
    print("\n" + "=" * 60)
    print("8개 어댑터 로드 중...")
    print("=" * 60)

    for adapter_name in ADAPTER_CONFIGS.keys():
        try:
            load_adapter(adapter_name)
        except Exception as e:
            print(f"❌ {adapter_name} 로드 실패: {e}")

    print("\n" + "=" * 60)
    print(f"서버 준비 완료! http://0.0.0.0:{PORT}")
    print(f"로드된 어댑터: {list(loaded_adapters.keys())}")
    print("=" * 60)

    yield

    # 종료 시 정리
    print("서버 종료 중...")

app = FastAPI(
    title="TmaxSoft LoRA Adapter API",
    description="8개 제품 LoRA 어댑터 서빙 API",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    return {
        "service": "TmaxSoft LoRA Adapter API",
        "adapters": list(ADAPTER_CONFIGS.keys()),
        "loaded": list(loaded_adapters.keys()),
        "base_model": BASE_MODEL
    }

@app.get("/adapters")
async def list_adapters():
    return {
        name: {
            "description": config["description"],
            "loaded": loaded_adapters.get(name, False)
        }
        for name, config in ADAPTER_CONFIGS.items()
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    global model, tokenizer

    if request.adapter not in ADAPTER_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Unknown adapter: {request.adapter}")

    if request.adapter not in loaded_adapters:
        raise HTTPException(status_code=400, detail=f"Adapter not loaded: {request.adapter}")

    # 어댑터 전환
    model.set_adapter(request.adapter)

    # 메시지 생성
    messages = [
        {"role": "system", "content": f"당신은 {ADAPTER_CONFIGS[request.adapter]['description']} 전문 기술 지원 엔지니어입니다. 정확하고 상세하게 답변하세요."},
        {"role": "user", "content": request.message}
    ]

    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=request.max_tokens,
            do_sample=True,
            temperature=request.temperature,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )

    response_tokens = outputs[0][inputs['input_ids'].shape[1]:]
    response = tokenizer.decode(response_tokens, skip_special_tokens=True)

    return ChatResponse(
        adapter=request.adapter,
        response=response,
        tokens_generated=len(response_tokens)
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "gpu": "5", "adapters_loaded": len(loaded_adapters)}

if __name__ == "__main__":
    print("=" * 60)
    print("TmaxSoft 8개 제품 LoRA API 서버")
    print("=" * 60)
    print(f"GPU: 5")
    print(f"Port: {PORT}")
    print(f"Base Model: {BASE_MODEL}")
    print(f"Adapters: {len(ADAPTER_CONFIGS)}")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=PORT)
