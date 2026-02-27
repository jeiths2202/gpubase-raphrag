#!/usr/bin/env python3
"""QLoRA 어댑터 테스트 스크립트"""

import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

# GPU 설정
os.environ["CUDA_VISIBLE_DEVICES"] = "5"

def load_model_with_adapter(adapter_path: str):
    """베이스 모델과 어댑터 로드"""
    base_model = "Qwen/Qwen2.5-7B-Instruct"

    print(f"Loading base model: {base_model}")

    # 4bit 양자화 설정
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # 베이스 모델 로드
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    # 토크나이저 로드
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)

    # 어댑터 로드
    print(f"Loading adapter: {adapter_path}")
    model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()

    return model, tokenizer

def generate_response(model, tokenizer, question: str, max_new_tokens: int = 512):
    """응답 생성"""
    messages = [
        {"role": "system", "content": "당신은 TmaxSoft 제품에 대한 전문 기술 지원 엔지니어입니다. 정확하고 상세한 기술 정보를 제공합니다."},
        {"role": "user", "content": question}
    ]

    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )

    response = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    return response

def main():
    # 테스트할 어댑터 목록
    adapters = {
        "tmax": "qlora_adapters/tmax/openframe_ko_20260201_135130",
        "tibero7": "qlora_adapters/tibero7/openframe_ko_20260131_184925",
        "msp_openframe": "qlora_adapters/msp_openframe/openframe_ko_20260131_131057",
    }

    # 제품별 테스트 질문
    test_questions = {
        "tmax": "Tmax에서 서버 프로세스 관리는 어떻게 하나요?",
        "tibero7": "Tibero에서 테이블스페이스를 생성하는 방법을 알려주세요.",
        "msp_openframe": "OpenFrame에서 JCL 작업을 실행하는 방법은?",
    }

    # tmax 어댑터로 테스트
    adapter_name = "tmax"
    adapter_path = adapters[adapter_name]

    print("=" * 60)
    print(f"Testing adapter: {adapter_name}")
    print("=" * 60)

    model, tokenizer = load_model_with_adapter(adapter_path)

    # 여러 질문 테스트
    questions = [
        test_questions[adapter_name],
        "Tmax 시스템의 주요 구성요소는 무엇인가요?",
        "tmboot 명령어 사용법을 설명해주세요.",
    ]

    for i, question in enumerate(questions, 1):
        print(f"\n[질문 {i}] {question}")
        print("-" * 40)
        response = generate_response(model, tokenizer, question)
        print(f"[응답]\n{response}")
        print("-" * 40)

    print("\n테스트 완료!")

if __name__ == "__main__":
    main()
