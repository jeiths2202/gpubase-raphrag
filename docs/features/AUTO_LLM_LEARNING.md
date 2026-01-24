# Auto LLM Learning System

**Version**: v1.0.0-gpu-local-llm
**Last Updated**: 2026-01-24

---

## 1. 개요

Auto LLM Learning System은 사용자 피드백(👍/👎)을 자동으로 수집하고 학습하여 RAG 시스템의 응답 품질을 지속적으로 개선하는 시스템입니다.

### 핵심 개념

```
┌─────────────────────────────────────────────────────────────────┐
│                  CONTINUOUS LEARNING LOOP                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│     User Query                                                  │
│         │                                                       │
│         ▼                                                       │
│    ┌─────────┐                                                  │
│    │   RAG   │  ← Smarter RAG Priority 적용                    │
│    │ System  │                                                  │
│    └────┬────┘                                                  │
│         │                                                       │
│         ▼                                                       │
│    System Response                                              │
│         │                                                       │
│         ▼                                                       │
│    ┌─────────┐                                                  │
│    │  User   │  👍 = 학습 대상 (Verified Knowledge)            │
│    │Feedback │  👎 = 제거 대상 (Unlearning)                     │
│    └────┬────┘                                                  │
│         │                                                       │
│         ▼                                                       │
│    ┌─────────────────────────────────────────────────────┐     │
│    │           Daily Training Pipeline                    │     │
│    │                                                      │     │
│    │  Verified Knowledge  →  QLoRA Fine-tuning  →  New   │     │
│    │       Store              (00:00 UTC)          Model │     │
│    │                                                      │     │
│    └─────────────────────────────────────────────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 아키텍처

### 2.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AUTO LLM LEARNING ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────────────────────────────────────┐    │
│  │   Frontend  │    │                Backend                       │    │
│  │             │    │                                              │    │
│  │ ┌─────────┐ │    │  ┌───────────────────────────────────────┐  │    │
│  │ │Feedback │ │    │  │        User Feedback Service          │  │    │
│  │ │  UI     │─┼────┼─→│                                       │  │    │
│  │ │(👍/👎) │ │    │  │  • Quick feedback (positive/negative) │  │    │
│  │ └─────────┘ │    │  │  • Detailed feedback (categories)     │  │    │
│  │             │    │  │  • Citation feedback                  │  │    │
│  │             │    │  └──────────────────┬────────────────────┘  │    │
│  │             │    │                     │                        │    │
│  │             │    │          ┌──────────┴──────────┐             │    │
│  │             │    │          │                     │             │    │
│  │             │    │          ▼                     ▼             │    │
│  │             │    │  ┌──────────────┐     ┌──────────────┐      │    │
│  │             │    │  │   Verified   │     │   Unlearn    │      │    │
│  │             │    │  │  Knowledge   │     │    Queue     │      │    │
│  │             │    │  │    Store     │     │   (👎 Data)  │      │    │
│  │             │    │  │   (👍 Data)  │     │              │      │    │
│  │             │    │  └──────┬───────┘     └──────┬───────┘      │    │
│  │             │    │         │                    │               │    │
│  │             │    │         └────────┬───────────┘               │    │
│  │             │    │                  │                           │    │
│  │             │    │                  ▼                           │    │
│  │             │    │  ┌───────────────────────────────────────┐  │    │
│  │             │    │  │       Daily Training Pipeline          │  │    │
│  │             │    │  │           (00:00 UTC)                  │  │    │
│  │             │    │  │                                        │  │    │
│  │             │    │  │  1. Fetch verified knowledge          │  │    │
│  │             │    │  │  2. Prepare training data             │  │    │
│  │             │    │  │  3. QLoRA fine-tuning                 │  │    │
│  │             │    │  │  4. Apply unlearning                  │  │    │
│  │             │    │  │  5. Save new adapters                 │  │    │
│  │             │    │  │                                        │  │    │
│  │             │    │  └──────────────────┬─────────────────────┘  │    │
│  │             │    │                     │                        │    │
│  │             │    │                     ▼                        │    │
│  │             │    │  ┌───────────────────────────────────────┐  │    │
│  │             │    │  │        Learning LLM Service           │  │    │
│  │             │    │  │                                       │  │    │
│  │             │    │  │  Model: Qwen2.5-7B-Instruct          │  │    │
│  │             │    │  │  Method: QLoRA (4-bit)               │  │    │
│  │             │    │  │  VRAM: ~8GB                          │  │    │
│  │             │    │  │                                       │  │    │
│  │             │    │  └───────────────────────────────────────┘  │    │
│  │             │    │                                              │    │
│  └─────────────┘    └──────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Smarter RAG Priority

응답 생성 시 다음 우선순위를 따릅니다:

```
┌─────────────────────────────────────────────────────────────┐
│                  SMARTER RAG PRIORITY                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Priority 1: Verified Knowledge Store                       │
│  ═══════════════════════════════════                       │
│  • 조건: similarity ≥ 0.85                                  │
│  • 소스: 사용자가 👍한 Q&A 쌍                               │
│  • 장점: 100% 검증된 정확한 답변                            │
│                                                             │
│         │                                                   │
│         │ (매칭 없음)                                       │
│         ▼                                                   │
│                                                             │
│  Priority 2: Learning LLM                                   │
│  ═══════════════════════════                                │
│  • 조건: confidence ≥ 0.6                                   │
│  • 소스: QLoRA 학습된 패턴                                  │
│  • 장점: 유사 질문에 대한 일반화된 답변                     │
│                                                             │
│         │                                                   │
│         │ (신뢰도 부족)                                     │
│         ▼                                                   │
│                                                             │
│  Priority 3: General RAG                                    │
│  ═══════════════════════                                    │
│  • 소스: 문서 검색 + LLM 생성                               │
│  • 특징: Hallucination Prevention 적용                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 핵심 컴포넌트

### 3.1 User Feedback Service

사용자 피드백을 수집하고 처리합니다.

```python
# app/api/services/user_feedback_service.py

from enum import Enum
from typing import Optional
from datetime import datetime

class FeedbackType(Enum):
    POSITIVE = "positive"  # 👍
    NEGATIVE = "negative"  # 👎

class FeedbackCategory(Enum):
    ACCURATE = "accurate"           # 정확함
    HELPFUL = "helpful"             # 도움됨
    INACCURATE = "inaccurate"       # 부정확
    INCOMPLETE = "incomplete"       # 불완전
    IRRELEVANT = "irrelevant"       # 관련없음
    OUTDATED = "outdated"           # 오래됨


class UserFeedbackService:
    """
    사용자 피드백 관리 서비스

    기능:
    - 빠른 피드백 (👍/👎)
    - 상세 피드백 (카테고리, 코멘트)
    - 인용 피드백 (출처 정확도)
    """

    def __init__(
        self,
        feedback_repository: FeedbackRepository,
        verified_knowledge_service: VerifiedKnowledgeService
    ):
        self.repository = feedback_repository
        self.verified_knowledge = verified_knowledge_service

    async def submit_quick_feedback(
        self,
        message_id: str,
        conversation_id: str,
        feedback_type: FeedbackType,
        query: str,
        answer: str,
        user_id: str
    ) -> FeedbackResult:
        """빠른 피드백 제출 (👍/👎)"""

        # 1. 피드백 저장
        feedback = await self.repository.save(Feedback(
            message_id=message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            feedback_type=feedback_type,
            query_snapshot=query,
            answer_snapshot=answer,
            created_at=datetime.utcnow()
        ))

        # 2. 긍정 피드백: Verified Knowledge에 추가
        if feedback_type == FeedbackType.POSITIVE:
            await self.verified_knowledge.store(
                query=query,
                answer=answer,
                source="user_feedback",
                verified_by=user_id
            )
            return FeedbackResult(
                success=True,
                message="피드백이 저장되었습니다. 이 응답은 향후 학습에 활용됩니다."
            )

        # 3. 부정 피드백: Unlearn Queue에 추가
        else:
            await self.verified_knowledge.mark_for_unlearning(
                query=query,
                answer=answer,
                reason="negative_feedback"
            )
            return FeedbackResult(
                success=True,
                message="피드백이 저장되었습니다. 더 나은 응답을 위해 개선하겠습니다."
            )

    async def submit_detailed_feedback(
        self,
        message_id: str,
        feedback_type: FeedbackType,
        categories: List[FeedbackCategory],
        comment: Optional[str],
        user_id: str
    ) -> FeedbackResult:
        """상세 피드백 제출"""

        feedback = await self.repository.save(DetailedFeedback(
            message_id=message_id,
            user_id=user_id,
            feedback_type=feedback_type,
            categories=categories,
            comment=comment,
            created_at=datetime.utcnow()
        ))

        # HITL 신호 생성 (부정 피드백 시)
        if feedback_type == FeedbackType.NEGATIVE:
            await self._generate_hitl_signal(feedback)

        return FeedbackResult(success=True)

    async def submit_citation_feedback(
        self,
        message_id: str,
        citation_id: str,
        is_accurate: bool,
        user_id: str
    ) -> FeedbackResult:
        """인용 정확도 피드백"""

        await self.repository.save_citation_feedback(CitationFeedback(
            message_id=message_id,
            citation_id=citation_id,
            is_accurate=is_accurate,
            user_id=user_id,
            created_at=datetime.utcnow()
        ))

        return FeedbackResult(success=True)

    async def _generate_hitl_signal(self, feedback: DetailedFeedback):
        """Human-in-the-Loop 신호 생성"""
        # 관리자에게 검토 요청 알림
        await self.notification_service.notify_admin(
            type="HITL_REVIEW_REQUIRED",
            data={
                "message_id": feedback.message_id,
                "categories": [c.value for c in feedback.categories],
                "comment": feedback.comment
            }
        )
```

### 3.2 Verified Knowledge Service

검증된 Q&A 쌍을 저장하고 검색합니다.

```python
# app/api/services/verified_knowledge_service.py

class VerifiedKnowledgeService:
    """
    검증된 지식 관리 서비스

    저장 대상:
    - 사용자 👍 피드백 받은 Q&A
    - 관리자 검증된 Q&A

    검색 조건:
    - 유사도 ≥ 0.85
    """

    MIN_SIMILARITY_THRESHOLD = 0.85

    def __init__(
        self,
        repository: VerifiedKnowledgeRepository,
        embedding_service: EmbeddingService
    ):
        self.repository = repository
        self.embedding = embedding_service

    async def search(
        self,
        query: str,
        top_k: int = 3
    ) -> List[VerifiedKnowledge]:
        """유사한 검증된 지식 검색"""

        # 1. 쿼리 임베딩
        query_embedding = await self.embedding.embed(query)

        # 2. 유사도 검색
        results = await self.repository.search_by_embedding(
            embedding=query_embedding,
            threshold=self.MIN_SIMILARITY_THRESHOLD,
            limit=top_k
        )

        return results

    async def store(
        self,
        query: str,
        answer: str,
        source: str,
        verified_by: str,
        metadata: Optional[dict] = None
    ) -> VerifiedKnowledge:
        """검증된 지식 저장"""

        # 1. 쿼리 임베딩
        query_embedding = await self.embedding.embed(query)

        # 2. 중복 확인
        existing = await self.repository.find_by_query(query)
        if existing:
            # 업데이트 (재확인된 것으로 처리)
            existing.verification_count += 1
            existing.last_verified_at = datetime.utcnow()
            return await self.repository.update(existing)

        # 3. 새로 저장
        knowledge = VerifiedKnowledge(
            id=generate_id(),
            query=query,
            answer=answer,
            query_embedding=query_embedding,
            source=source,
            verified_by=verified_by,
            status=VerificationStatus.ACTIVE,
            verification_count=1,
            created_at=datetime.utcnow(),
            metadata=metadata or {}
        )

        return await self.repository.save(knowledge)

    async def mark_for_unlearning(
        self,
        query: str,
        answer: str,
        reason: str
    ):
        """제거 대상으로 표시"""

        # 기존 지식 찾기
        existing = await self.repository.find_by_query(query)

        if existing:
            existing.status = VerificationStatus.DEPRECATED
            existing.deprecation_reason = reason
            existing.deprecated_at = datetime.utcnow()
            await self.repository.update(existing)

        # Unlearn Queue에 추가
        await self.repository.add_to_unlearn_queue(UnlearnItem(
            query=query,
            answer=answer,
            reason=reason,
            created_at=datetime.utcnow()
        ))

    async def get_training_batch(
        self,
        batch_size: int = 1000,
        include_unlearn: bool = True
    ) -> TrainingBatch:
        """학습용 배치 데이터 가져오기"""

        # 1. 학습 대상 (👍)
        verified = await self.repository.get_unlearned_knowledge(
            limit=batch_size,
            status=VerificationStatus.ACTIVE
        )

        # 2. 제거 대상 (👎)
        unlearn = []
        if include_unlearn:
            unlearn = await self.repository.get_unlearn_queue(limit=batch_size)

        return TrainingBatch(
            learn_samples=[
                TrainingSample(
                    query=v.query,
                    answer=v.answer,
                    action="learn"
                ) for v in verified
            ],
            unlearn_samples=[
                TrainingSample(
                    query=u.query,
                    answer=u.answer,
                    action="unlearn"
                ) for u in unlearn
            ],
            created_at=datetime.utcnow()
        )
```

### 3.3 Learning LLM Service

QLoRA로 학습된 LLM을 관리합니다.

```python
# app/api/services/learning_llm_service.py

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel, LoraConfig

class LearningLLMService:
    """
    학습 LLM 서비스

    모델: Qwen2.5-7B-Instruct
    방법: QLoRA (4-bit 양자화)
    VRAM: ~8GB
    """

    def __init__(self, config: LearningLLMConfig):
        self.config = config
        self.model = None
        self.tokenizer = None
        self.adapter_version = None

    async def load(self):
        """모델 로드 (Lazy Loading)"""

        if self.model is not None:
            return

        # 4-bit 양자화 설정
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True
        )

        # 베이스 모델 로드
        self.model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,  # "Qwen/Qwen2.5-7B-Instruct"
            quantization_config=bnb_config,
            device_map={"": self.config.device},  # "cuda:1"
            torch_dtype=torch.float16
        )

        # 어댑터 로드 (있는 경우)
        adapter_path = self._get_latest_adapter()
        if adapter_path:
            self.model = PeftModel.from_pretrained(
                self.model,
                adapter_path
            )
            self.adapter_version = adapter_path.name

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.config.model_name
        )

    async def generate(
        self,
        query: str,
        max_tokens: int = 512
    ) -> LearningLLMResponse:
        """응답 생성"""

        await self.load()

        # 프롬프트 구성
        prompt = self._build_prompt(query)

        # 토큰화
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt"
        ).to(self.model.device)

        # 생성
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=0.1,
                do_sample=True,
                pad_token_id=self.tokenizer.pad_token_id
            )

        # 디코딩
        response = self.tokenizer.decode(
            outputs[0][inputs['input_ids'].shape[1]:],
            skip_special_tokens=True
        )

        # 신뢰도 계산
        confidence = self._calculate_confidence(outputs)

        return LearningLLMResponse(
            answer=response,
            confidence=confidence,
            adapter_version=self.adapter_version,
            model_name=self.config.model_name
        )

    def _calculate_confidence(self, outputs) -> float:
        """신뢰도 계산 (Perplexity 기반)"""
        # 낮은 perplexity = 높은 신뢰도
        logits = outputs.scores
        # ... perplexity 계산 로직
        return confidence

    def _build_prompt(self, query: str) -> str:
        """프롬프트 구성"""
        return f"""<|im_start|>system
당신은 기술 문서 기반 Q&A 시스템입니다.
검증된 지식을 바탕으로 정확하게 답변하세요.
<|im_end|>
<|im_start|>user
{query}
<|im_end|>
<|im_start|>assistant
"""

    async def reload_adapters(self):
        """어댑터 재로드"""
        adapter_path = self._get_latest_adapter()
        if adapter_path and adapter_path.name != self.adapter_version:
            self.model = PeftModel.from_pretrained(
                self.model.base_model,
                adapter_path
            )
            self.adapter_version = adapter_path.name

    async def unload(self):
        """메모리에서 모델 해제"""
        if self.model:
            del self.model
            self.model = None
            torch.cuda.empty_cache()
```

### 3.4 Training Pipeline

일일 학습 파이프라인입니다.

```python
# app/api/services/training_pipeline.py

from peft import get_peft_model, LoraConfig, TaskType
from transformers import TrainingArguments, Trainer
from datasets import Dataset

class TrainingPipeline:
    """
    QLoRA 학습 파이프라인

    스케줄: 매일 00:00 UTC
    """

    def __init__(
        self,
        verified_knowledge_service: VerifiedKnowledgeService,
        learning_llm_service: LearningLLMService,
        config: TrainingConfig
    ):
        self.verified_knowledge = verified_knowledge_service
        self.learning_llm = learning_llm_service
        self.config = config

    async def run_training(
        self,
        min_samples: int = 100,
        include_unlearn: bool = True
    ) -> TrainingResult:
        """학습 실행"""

        # 1. 학습 데이터 준비
        batch = await self.verified_knowledge.get_training_batch(
            batch_size=self.config.batch_size,
            include_unlearn=include_unlearn
        )

        if len(batch.learn_samples) < min_samples:
            return TrainingResult(
                success=False,
                reason=f"Not enough samples: {len(batch.learn_samples)} < {min_samples}"
            )

        # 2. 데이터셋 생성
        dataset = self._prepare_dataset(batch)

        # 3. LoRA 설정
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"]
        )

        # 4. 모델 준비
        model = get_peft_model(
            self.learning_llm.model.base_model,
            lora_config
        )

        # 5. 학습 인자
        training_args = TrainingArguments(
            output_dir=self.config.output_dir,
            num_train_epochs=3,
            per_device_train_batch_size=4,
            gradient_accumulation_steps=4,
            learning_rate=2e-4,
            fp16=True,
            save_strategy="epoch",
            logging_steps=10,
            warmup_ratio=0.03
        )

        # 6. Trainer
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=dataset
        )

        # 7. 학습 실행
        train_result = trainer.train()

        # 8. 어댑터 저장
        adapter_path = self._save_adapter(model)

        # 9. 학습 데이터 상태 업데이트
        await self._mark_samples_as_trained(batch.learn_samples)

        # 10. Unlearning 처리
        if include_unlearn and batch.unlearn_samples:
            await self._process_unlearning(batch.unlearn_samples)

        return TrainingResult(
            success=True,
            adapter_path=adapter_path,
            metrics={
                "loss": train_result.training_loss,
                "samples_trained": len(batch.learn_samples),
                "samples_unlearned": len(batch.unlearn_samples)
            }
        )

    def _prepare_dataset(self, batch: TrainingBatch) -> Dataset:
        """학습 데이터셋 준비"""
        data = []
        for sample in batch.learn_samples:
            data.append({
                "text": f"<|im_start|>user\n{sample.query}<|im_end|>\n"
                        f"<|im_start|>assistant\n{sample.answer}<|im_end|>"
            })
        return Dataset.from_list(data)

    async def _process_unlearning(self, samples: List[TrainingSample]):
        """Unlearning 처리 (Negative Sampling)"""
        # 부정적 샘플을 학습에서 제외하고
        # 해당 패턴에 대해 낮은 확률을 학습
        for sample in samples:
            await self.verified_knowledge.repository.mark_unlearned(
                query=sample.query
            )
```

---

## 4. API Endpoints

### 4.1 피드백 API

```bash
# 빠른 피드백 (👍/👎)
POST /api/v1/feedback/quick
Content-Type: application/json

{
  "message_id": "msg_abc123",
  "conversation_id": "conv_xyz789",
  "feedback_type": "positive",  # or "negative"
  "query": "JEUS 설치 방법",
  "answer": "1. 다운로드\n2. 압축 해제\n3. 설정..."
}

Response:
{
  "success": true,
  "message": "피드백이 저장되었습니다. 이 응답은 향후 학습에 활용됩니다."
}
```

```bash
# 상세 피드백
POST /api/v1/feedback/detailed
Content-Type: application/json

{
  "message_id": "msg_abc123",
  "feedback_type": "negative",
  "categories": ["inaccurate", "incomplete"],
  "comment": "JEUS 8 기준인데 JEUS 7 설명이 섞여있습니다"
}
```

```bash
# 인용 피드백
POST /api/v1/feedback/citation
Content-Type: application/json

{
  "message_id": "msg_abc123",
  "citation_id": "cite_001",
  "is_accurate": false
}
```

### 4.2 Verified Knowledge API

```bash
# 검증된 지식 검색
GET /api/v1/verified-knowledge/search?query=JEUS%20설치&limit=5

Response:
{
  "results": [
    {
      "id": "vk_001",
      "query": "JEUS 설치 방법",
      "answer": "1. 다운로드...",
      "similarity": 0.92,
      "verification_count": 15,
      "last_verified_at": "2026-01-20T..."
    }
  ]
}
```

```bash
# 통계
GET /api/v1/verified-knowledge/stats/overview

Response:
{
  "total_count": 1523,
  "active_count": 1450,
  "deprecated_count": 73,
  "trained_count": 1200,
  "pending_training_count": 250,
  "avg_feedback_score": 4.2,
  "last_training_at": "2026-01-24T00:00:00Z"
}
```

### 4.3 Learning LLM API

```bash
# LLM 상태 확인
GET /api/v1/verified-knowledge/learning-llm/status

Response:
{
  "loaded": true,
  "model_name": "Qwen/Qwen2.5-7B-Instruct",
  "adapter_version": "adapter_20260124_v3",
  "device": "cuda:1",
  "vram_usage_gb": 7.8
}
```

```bash
# 응답 생성
POST /api/v1/verified-knowledge/learning-llm/generate
Content-Type: application/json

{
  "query": "JEUS WebAdmin 접속 방법"
}

Response:
{
  "answer": "JEUS WebAdmin 접속 방법:\n1. 브라우저에서 http://host:9736/webadmin 접속\n2. ...",
  "confidence": 0.85,
  "adapter_version": "adapter_20260124_v3",
  "source": "learning_llm"
}
```

```bash
# 수동 학습 트리거
POST /api/v1/verified-knowledge/training/trigger
Content-Type: application/json

{
  "min_samples": 100,
  "include_unlearn": true
}

Response:
{
  "batch_id": "batch_20260124_001",
  "status": "started",
  "estimated_time_minutes": 30
}
```

---

## 5. 데이터베이스 스키마

```sql
-- 검증된 지식
CREATE TABLE verified_knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    query_embedding VECTOR(1024),
    source VARCHAR(50) NOT NULL,  -- 'user_feedback', 'admin_verified'
    verified_by UUID REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'deprecated', 'trained'
    verification_count INT DEFAULT 1,
    deprecation_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    last_verified_at TIMESTAMP DEFAULT NOW(),
    trained_at TIMESTAMP,
    deprecated_at TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_vk_embedding ON verified_knowledge
    USING ivfflat (query_embedding vector_cosine_ops);
CREATE INDEX idx_vk_status ON verified_knowledge(status);

-- Unlearn 큐
CREATE TABLE unlearn_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    reason VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'processed'
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP
);

-- 학습 배치
CREATE TABLE training_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    total_samples INT NOT NULL,
    trained_samples INT DEFAULT 0,
    unlearn_samples INT DEFAULT 0,
    status VARCHAR(20) NOT NULL,  -- 'pending', 'running', 'completed', 'failed'
    adapter_path TEXT,
    metrics JSONB,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 사용자 피드백
CREATE TABLE user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL,
    conversation_id UUID,
    user_id UUID REFERENCES users(id),
    feedback_type VARCHAR(20) NOT NULL,  -- 'positive', 'negative'
    query_snapshot TEXT,
    answer_snapshot TEXT,
    categories VARCHAR(50)[],
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_feedback_type ON user_feedback(feedback_type);
CREATE INDEX idx_feedback_user ON user_feedback(user_id);
```

---

## 6. 설정

```bash
# .env

# Learning LLM
ENABLE_LEARNING_LLM=true
LEARNING_LLM_AUTO_LOAD=false          # Lazy loading
LEARNING_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
LEARNING_LLM_DEVICE=cuda:1
LEARNING_LLM_LOAD_IN_4BIT=true

# Verified Knowledge
VERIFIED_KNOWLEDGE_MIN_SIMILARITY=0.85
VERIFIED_KNOWLEDGE_TRAINING_SCHEDULE="0 0 * * *"  # Daily 00:00 UTC

# Training
TRAINING_MIN_SAMPLES=100
TRAINING_BATCH_SIZE=1000
TRAINING_OUTPUT_DIR=/opt/kms/models/qlora_adapters
TRAINING_EPOCHS=3
TRAINING_LEARNING_RATE=2e-4

# Smarter RAG Priority
SMARTER_RAG_ENABLED=true
SMARTER_RAG_VK_THRESHOLD=0.85         # Verified Knowledge
SMARTER_RAG_LLM_THRESHOLD=0.6         # Learning LLM
SMARTER_RAG_HIGH_CONFIDENCE=0.8
```

---

## 7. 모니터링

### Admin Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│                    LEARNING SYSTEM DASHBOARD                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Verified Knowledge Stats                                       │
│  ═══════════════════════                                       │
│  Total: 1,523  |  Active: 1,450  |  Trained: 1,200             │
│  Pending: 250  |  Deprecated: 73                                │
│                                                                 │
│  Feedback Stats (Last 7 Days)                                   │
│  ════════════════════════════                                   │
│  👍 Positive: 234  |  👎 Negative: 18                           │
│  Ratio: 92.9%                                                   │
│                                                                 │
│  Training History                                               │
│  ════════════════                                               │
│  | Date       | Samples | Loss   | Status    |                 │
│  |------------|---------|--------|-----------|                 │
│  | 2026-01-24 | 250     | 0.0823 | Completed |                 │
│  | 2026-01-23 | 180     | 0.0912 | Completed |                 │
│  | 2026-01-22 | 320     | 0.0756 | Completed |                 │
│                                                                 │
│  Learning LLM Status                                            │
│  ═══════════════════                                           │
│  Model: Qwen2.5-7B  |  Loaded: Yes  |  VRAM: 7.8GB             │
│  Adapter: v3 (2026-01-24)                                       │
│                                                                 │
│  [Trigger Training]  [Reload Adapters]  [Unload Model]         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. 관련 파일

| 파일 | 설명 |
|------|------|
| `app/api/services/user_feedback_service.py` | 사용자 피드백 서비스 |
| `app/api/services/verified_knowledge_service.py` | 검증된 지식 서비스 |
| `app/api/services/learning_llm_service.py` | Learning LLM 서비스 |
| `app/api/routers/user_feedback.py` | 피드백 API |
| `app/api/routers/verified_knowledge.py` | Verified Knowledge API |
| `app/api/infrastructure/postgres/verified_knowledge_repository.py` | Repository |

---

**See Also**:
- [AI Driven RAG System](./AI_DRIVEN_RAG_SYSTEM.md)
- [Hallucination Prevention](./HALLUCINATION_PREVENTION.md)
- [SMARTER_RAG_SYSTEM.md](../SMARTER_RAG_SYSTEM.md)
