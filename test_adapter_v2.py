#!/usr/bin/env python3
"""QLoRA 어댑터 테스트 스크립트 v2 - 다국어 테스트"""

import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

os.environ["CUDA_VISIBLE_DEVICES"] = "5"

def load_model_with_adapter(adapter_path: str):
    base_model = "Qwen/Qwen2.5-7B-Instruct"
    print(f"Loading base model: {base_model}")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)

    print(f"Loading adapter: {adapter_path}")
    model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()

    return model, tokenizer

def generate_response(model, tokenizer, question: str, lang: str = "ko", max_new_tokens: int = 300):
    system_prompts = {
        "ko": "당신은 TmaxSoft 제품 전문 기술 지원 엔지니어입니다. 반드시 한국어로만 답변하세요.",
        "ja": "あなたはTmaxSoft製品の専門技術サポートエンジニアです。日本語で回答してください。",
        "en": "You are a TmaxSoft product technical support engineer. Please answer in English.",
    }

    messages = [
        {"role": "system", "content": system_prompts.get(lang, system_prompts["ko"])},
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

def test_adapter(adapter_name: str, adapter_path: str, questions: list):
    print("\n" + "=" * 70)
    print(f"Testing: {adapter_name}")
    print(f"Adapter: {adapter_path}")
    print("=" * 70)

    model, tokenizer = load_model_with_adapter(adapter_path)

    for lang, question in questions:
        print(f"\n[{lang.upper()}] {question}")
        print("-" * 50)
        response = generate_response(model, tokenizer, question, lang)
        print(f"{response[:500]}...")
        print("-" * 50)

    # 메모리 정리
    del model
    torch.cuda.empty_cache()

def main():
    adapters = [
        ("tmax", "qlora_adapters/tmax/openframe_ko_20260201_135130", [
            ("ko", "Tmax에서 서버 프로세스를 시작하는 방법은?"),
            ("ko", "tmadmin 명령어로 할 수 있는 작업은 무엇인가요?"),
        ]),
        ("tibero7", "qlora_adapters/tibero7/openframe_ko_20260131_184925", [
            ("ko", "Tibero에서 테이블스페이스를 생성하는 SQL 구문은?"),
            ("ko", "Tibero의 백업 방법을 설명해주세요."),
        ]),
        ("ofcobol", "qlora_adapters/ofcobol/openframe_ko_20260201_085854", [
            ("ko", "OpenFrame COBOL 컴파일 방법을 알려주세요."),
        ]),
    ]

    for adapter_name, adapter_path, questions in adapters:
        test_adapter(adapter_name, adapter_path, questions)

    print("\n" + "=" * 70)
    print("All tests completed!")
    print("=" * 70)

if __name__ == "__main__":
    main()
