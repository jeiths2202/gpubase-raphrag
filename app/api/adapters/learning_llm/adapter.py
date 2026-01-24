"""
Learning LLM Adapter

QLoRA로 파인튜닝된 모델을 로드하고 추론을 수행합니다.
RAG 파이프라인에서 Verified Knowledge 기반 응답 생성에 사용됩니다.
"""
import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

logger = logging.getLogger(__name__)


class LearningLLMAdapter:
    """
    Learning LLM 어댑터

    QLoRA 파인튜닝된 모델을 사용하여 추론을 수행합니다.
    Verified Knowledge Store에서 학습된 지식을 기반으로 응답합니다.
    """

    def __init__(
        self,
        base_model: str = "Qwen/Qwen2.5-7B-Instruct",
        adapter_path: Optional[str] = None,
        device_map: str = "auto",
        load_in_4bit: bool = True,
    ):
        self.base_model = base_model
        self.adapter_path = adapter_path
        self.device_map = device_map
        self.load_in_4bit = load_in_4bit

        self.model = None
        self.tokenizer = None
        self.is_loaded = False
        self.current_adapter = None

    async def load(self, adapter_name: Optional[str] = None) -> bool:
        """
        모델 로드

        Args:
            adapter_name: 특정 어댑터 이름 (None이면 최신 어댑터 사용)

        Returns:
            로드 성공 여부
        """
        try:
            logger.info(f"Loading Learning LLM: {self.base_model}")

            # Find adapter path
            adapter_dir = Path("/opt/kms/models/qlora_adapters")

            if adapter_name:
                adapter_path = adapter_dir / adapter_name
            else:
                # Find latest adapter
                adapters = sorted(adapter_dir.glob("qlora_*"), reverse=True)
                if not adapters:
                    logger.warning("No trained adapters found")
                    return False
                adapter_path = adapters[0]

            if not adapter_path.exists():
                logger.warning(f"Adapter not found: {adapter_path}")
                return False

            logger.info(f"Loading adapter: {adapter_path}")

            # BitsAndBytes config for 4-bit
            bnb_config = None
            if self.load_in_4bit:
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                )

            # Load base model
            self.model = AutoModelForCausalLM.from_pretrained(
                self.base_model,
                quantization_config=bnb_config,
                device_map=self.device_map,
                trust_remote_code=True,
                torch_dtype=torch.bfloat16,
            )

            # Load adapter
            self.model = PeftModel.from_pretrained(
                self.model,
                str(adapter_path),
            )

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.base_model,
                trust_remote_code=True,
            )

            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            self.is_loaded = True
            self.current_adapter = adapter_path.name

            logger.info(f"Learning LLM loaded successfully: {self.current_adapter}")
            return True

        except Exception as e:
            logger.error(f"Failed to load Learning LLM: {e}")
            return False

    async def unload(self):
        """모델 언로드"""
        if self.model:
            del self.model
            self.model = None

        if self.tokenizer:
            del self.tokenizer
            self.tokenizer = None

        torch.cuda.empty_cache()
        self.is_loaded = False
        self.current_adapter = None

        logger.info("Learning LLM unloaded")

    async def reload_adapter(self, adapter_name: str) -> bool:
        """새 어댑터로 리로드"""
        await self.unload()
        return await self.load(adapter_name)

    def _format_prompt(self, question: str, context: Optional[str] = None) -> str:
        """프롬프트 포맷팅"""
        if context:
            user_content = f"{question}\n\nContext:\n{context}"
        else:
            user_content = question

        prompt = f"""<|im_start|>system
You are a helpful KMS assistant that provides accurate answers based on verified knowledge.<|im_end|>
<|im_start|>user
{user_content}<|im_end|>
<|im_start|>assistant
"""
        return prompt

    async def generate(
        self,
        question: str,
        context: Optional[str] = None,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        do_sample: bool = True,
    ) -> str:
        """
        응답 생성

        Args:
            question: 사용자 질문
            context: 추가 컨텍스트 (optional)
            max_new_tokens: 최대 생성 토큰 수
            temperature: 샘플링 온도
            top_p: Top-p 샘플링
            do_sample: 샘플링 사용 여부

        Returns:
            생성된 응답
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        prompt = self._format_prompt(question, context)

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=2048,
        ).to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=do_sample,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )

        # Decode only new tokens
        response = self.tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:],
            skip_special_tokens=True
        )

        return response.strip()

    async def generate_stream(
        self,
        question: str,
        context: Optional[str] = None,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> AsyncGenerator[str, None]:
        """
        스트리밍 응답 생성

        Args:
            question: 사용자 질문
            context: 추가 컨텍스트 (optional)

        Yields:
            생성된 토큰들
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        from transformers import TextIteratorStreamer
        from threading import Thread

        prompt = self._format_prompt(question, context)

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=2048,
        ).to(self.model.device)

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_special_tokens=True,
            skip_prompt=True,
        )

        generation_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=True,
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
        )

        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        for text in streamer:
            yield text

        thread.join()

    async def get_confidence(
        self,
        question: str,
        answer: str,
    ) -> float:
        """
        응답에 대한 신뢰도 계산

        학습된 지식에 기반한 응답인지 확인합니다.

        Args:
            question: 질문
            answer: 응답

        Returns:
            신뢰도 (0-1)
        """
        if not self.is_loaded:
            return 0.0

        try:
            # Generate a response and compare
            generated = await self.generate(
                question,
                max_new_tokens=256,
                temperature=0.1,  # Low temperature for deterministic output
                do_sample=False,
            )

            # Simple similarity check (can be improved with embedding similarity)
            from difflib import SequenceMatcher
            similarity = SequenceMatcher(None, answer.lower(), generated.lower()).ratio()

            return similarity

        except Exception as e:
            logger.error(f"Error calculating confidence: {e}")
            return 0.0

    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        return {
            "is_loaded": self.is_loaded,
            "base_model": self.base_model,
            "current_adapter": self.current_adapter,
            "device_map": self.device_map,
            "load_in_4bit": self.load_in_4bit,
        }


# ============================================
# Singleton Instance
# ============================================

_learning_llm_adapter: Optional[LearningLLMAdapter] = None


def get_learning_llm_adapter() -> Optional[LearningLLMAdapter]:
    """Get Learning LLM adapter singleton"""
    global _learning_llm_adapter
    return _learning_llm_adapter


async def initialize_learning_llm_adapter(
    base_model: str = "Qwen/Qwen2.5-7B-Instruct",
    adapter_name: Optional[str] = None,
    auto_load: bool = True,
) -> LearningLLMAdapter:
    """Initialize Learning LLM adapter"""
    global _learning_llm_adapter

    _learning_llm_adapter = LearningLLMAdapter(
        base_model=base_model,
    )

    if auto_load:
        await _learning_llm_adapter.load(adapter_name)

    logger.info("Learning LLM adapter initialized")
    return _learning_llm_adapter
