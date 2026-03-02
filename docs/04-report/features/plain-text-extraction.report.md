# Plain Text Extraction for LLM Pre-training Report

> **Status**: Complete
>
> **Project**: HybridRAG KMS
> **Feature**: plain-text-extraction (PDF Manual Plain Text Extractor)
> **Completion Date**: 2026-02-11
> **Target**: `uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP` (39 PDFs)

---

## 1. Executive Summary

### 1.1 Feature Overview

| Item | Content |
|------|---------|
| **Feature** | PDF Manual Plain Text Extraction for LLM Pre-training |
| **Purpose** | ChatML 형식이 아닌 plain text로 제품 매뉴얼을 추출하여 Continued Pre-training에 활용 |
| **Script** | `scripts/training/extract_plain_text.py` |
| **Input** | `uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP/` (39 PDF files) |
| **Output** | `uploads/training_text/MVS_Openframe_7.1/` (39 .txt + corpus.txt) |

### 1.2 Results Summary

```
┌────────────────────────────────────────────────────┐
│  Extraction Results                                 │
├────────────────────────────────────────────────────┤
│  Total PDFs:          39                            │
│  Success:             39 (100%)                     │
│  Failed:              0                             │
│  Total Pages:         4,030                         │
│  Skipped Front Pages: 164                           │
│  Total Characters:    4,332,766 (~4.3M)             │
│  Total Lines:         155,835                       │
│  Corpus File:         8.5 MB (corpus.txt)           │
│  Avg per PDF:         111,096 chars                 │
└────────────────────────────────────────────────────┘
```

### 1.3 ChatML vs Plain Text 비교

| 항목 | 기존 ChatML (convert_to_qlora.py) | 신규 Plain Text (extract_plain_text.py) |
|------|-----------------------------------|----------------------------------------|
| **출력 형식** | `<\|im_start\|>system...` ChatML | 순수 텍스트 (구조 보존) |
| **용도** | QLoRA Fine-tuning (instruction tuning) | Continued Pre-training (domain adaptation) |
| **데이터 단위** | instruction-response 쌍 | 문서 전체 텍스트 |
| **구조** | Q&A 템플릿 기반 | TOC 기반 섹션 구조 (`#` 헤딩) |
| **테이블** | 미포함 또는 텍스트화 | GFM Markdown 테이블 |
| **의존성** | learning_dataset.json 필요 | PDF 직접 파싱 (독립 실행) |

---

## 2. Architecture

### 2.1 Processing Pipeline

```
PDF File
  │
  ├── 1. PyMuPDF로 페이지별 텍스트 추출
  │     └── doc.get_text() / page.find_tables()
  │
  ├── 2. 프론트매터 자동 스킵
  │     ├── TOC 분석: "第N章" 패턴 찾아 본문 시작 결정
  │     └── 스킵 대상: 표지, 문서정보, 목차, 그림목차
  │
  ├── 3. 헤더/푸터 패턴 제거
  │     ├── "OpenFrame ... Guide" 반복 텍스트
  │     ├── 페이지 번호 (숫자, 로마 숫자)
  │     └── Copyright/TmaxSoft 푸터
  │
  ├── 4. 단락 재구성 (ParagraphReconstructor)
  │     ├── PDF 줄바꿈 → 의미 단위 단락 병합
  │     ├── 문장 종결자(。.!?)로 단락 경계 판단
  │     ├── 불릿/번호 리스트 → 별도 라인 보존
  │     └── 코드 블록 ($, KEY=VAL) → 원형 보존
  │
  ├── 5. TOC 기반 섹션 헤더 삽입
  │     ├── Level 1 → # 第1章 タイトル
  │     ├── Level 2 → ## 1.1. サブタイトル
  │     └── Level 3 → ### 1.1.1. 詳細
  │
  ├── 6. 테이블 → GFM Markdown 변환
  │     └── PyMuPDF find_tables() → | Header | ... |
  │
  └── 7. 출력
        ├── 개별 .txt 파일 (PDF당 1개)
        ├── corpus.txt 합본 (--merge 옵션)
        └── extraction_stats.json 통계
```

### 2.2 Key Classes

| Class | Role |
|-------|------|
| `PlainTextExtractor` | 메인 추출기. PDF 파싱, 프론트매터 스킵, 텍스트 정제, 단락 재구성 |
| `ExtractionStats` | 추출 통계 데이터클래스 |
| `extract_directory()` | 디렉토리 일괄 처리 + 합본 생성 함수 |

### 2.3 File Structure

```
scripts/training/
├── extract_plain_text.py          # [NEW] Plain text 추출 스크립트
├── convert_to_qlora.py            # [기존] ChatML 형식 변환
├── openframe_qlora_full_extractor.py  # [기존] PDF→instruction-response 추출
└── ...

uploads/
├── manuals/
│   └── MVS_Openframe 7.1_v3.1.3_JP/   # 입력 PDF (39개)
└── training_text/
    └── MVS_Openframe_7.1/              # 출력 텍스트
        ├── corpus.txt                   # 합본 (8.5MB)
        ├── extraction_stats.json        # 통계
        ├── OF_Base_7.1_Base-Guide_v3.1.2_jp.txt
        ├── OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_jp.txt
        └── ... (39개 .txt)
```

---

## 3. Usage Guide

### 3.1 Basic Commands

```bash
# 디렉토리 전체 추출 (개별 .txt 파일 생성)
python scripts/training/extract_plain_text.py \
  -i "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP"

# 합본 파일도 생성
python scripts/training/extract_plain_text.py \
  -i "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP" --merge

# 출력 디렉토리 지정
python scripts/training/extract_plain_text.py \
  -i "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP" \
  -o uploads/training_text/custom_dir --merge

# 단일 PDF만 추출
python scripts/training/extract_plain_text.py \
  -i "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP/OF_Base_7.1_Base-Guide_v3.1.2_jp.pdf"

# 통계만 확인 (파일 저장 없음)
python scripts/training/extract_plain_text.py \
  -i "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP" --stats
```

### 3.2 CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--input`, `-i` | (required) | 입력 PDF 파일 또는 디렉토리 경로 |
| `--output`, `-o` | `uploads/training_text/<dir_name>` | 출력 디렉토리 |
| `--merge` | `false` | corpus.txt 합본 파일 생성 |
| `--stats` | `false` | 통계만 출력 (파일 저장 안 함) |
| `--no-toc-headers` | `false` | TOC 기반 `#` 섹션 헤더 삽입 비활성화 |
| `--keep-front-matter` | `false` | 프론트매터(표지, 목차) 페이지 포함 |
| `--min-line-length` | `2` | 최소 라인 길이 (이하 제거) |

### 3.3 Output Format

개별 `.txt` 파일 예시:

```
このガイドについて 対象読者 本書は、...

前提知識 本書を理解するには、OpenFrame/Batchについての知識が必要です。

# 第1章 TJESの紹介

本章では、TJESの特徴、コンポーネント、マルチノードのTJES構成...

## 1.1. 概要

OpenFrame TJES（Tmax Job Entry Subsystem、以下TJES）は、
メインフレームのJESに対応するOpenFrameシステムのバッチ・ジョブ管理モジュールです。

●JCLを使用してジョブをサブミットします。
– IBMメインフレームのMVS JCLをサポート
– CONTROL-M、A-AUTOなどの外部スケジューラーとの連携をサポート

| 項目 | 説明 |
|---|---|
| プラットフォーム | Linux x86 2.6以上 |
| データベース | Tibero 6 (Fixset07) |
```

`corpus.txt` 합본 형식:

```
================================================================================
Document: OF_Base_7.1_Base-Guide_v3.1.2_jp.pdf
================================================================================

(본문 텍스트)


================================================================================
Document: OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_jp.pdf
================================================================================

(본문 텍스트)
```

---

## 4. Text Processing Details

### 4.1 Front Matter Skip Logic

TOC가 있는 PDF와 없는 PDF에서 다른 전략을 사용합니다.

**TOC가 있는 경우** (대부분의 매뉴얼):
1. PDF 내장 TOC 엔트리 순회
2. 스킵 대상 제목 필터: `目次`, `OpenFrame`, `文書情報`, `図目次`, `表目次`
3. 첫 번째 실제 챕터(`第N章`, `付録A`) 또는 서문(`このガイドについて`) 페이지를 본문 시작으로 결정

**TOC가 없는 경우**:
1. 처음 15페이지 텍스트 스캔
2. `目次`, `発行日`, `ガイドバージョン` 등 프론트매터 패턴 감지
3. 마지막 프론트매터 페이지 이후를 본문 시작으로 결정

### 4.2 Header/Footer Removal Patterns

| Pattern | Example |
|---------|---------|
| Guide 헤더 | `OpenFrame Base Guide v3.1.2` |
| 페이지 번호 | `42`, `iv`, `xii` |
| 구분선 번호 | `\| 51`, `52 \|` |
| Copyright | `TmaxSoft Co., Ltd.` |

### 4.3 Paragraph Reconstruction Rules

PDF 텍스트는 고정 폭에서 줄바꿈되어 의미 단위와 무관하게 끊깁니다. 다음 규칙으로 재구성합니다:

| 조건 | 처리 |
|------|------|
| 빈 줄 | 단락 구분자 |
| 문장 종결자(。.!?)로 끝남 | 단락 완료 |
| 불릿/번호 리스트 (`●`, `–`, `1.`) | 별도 라인 유지 |
| 섹션 제목 (`第N章`, `1.1.`) | 별도 단락 |
| 코드 라인 (`$`, `KEY=`, `[SECTION]`) | 원형 보존 |
| 기타 연속 줄 | 공백으로 연결하여 단락 병합 |

### 4.4 Table Conversion

PyMuPDF `find_tables()` → GFM Markdown:

```
Before (PDF):
  項目        説明
  DATABASE    接続するデータベース名
  USERNAME    データベースユーザー名

After (GFM Markdown):
  | 項目 | 説明 |
  |---|---|
  | DATABASE | 接続するデータベース名 |
  | USERNAME | データベースユーザー名 |
```

---

## 5. Extraction Results by PDF

### 5.1 Top 10 by Character Count

| # | PDF File | Pages | Processed | Chars | Lines |
|---|----------|-------|-----------|-------|-------|
| 1 | OF_Common_MVS_7.1_Error-Reference-Guide | 454 | 448 | 531,196 | 21,890 |
| 2 | OF_OSC_7.1_Developer-Guide | 288 | 268 | 373,915 | 11,663 |
| 3 | OF_Common_MVS_7.1_Tool-Reference-Guide | 294 | 280 | 348,657 | 12,017 |
| 4 | OF_Common_MVS_7.1_Configuration-Guide | 290 | 276 | 328,460 | 15,922 |
| 5 | OF_Common_MVS_7.1_Utility-Reference-Guide | 228 | 215 | 294,039 | 10,007 |
| 6 | OF_Manager_7.1Fix1_User-Guide | 268 | 262 | 289,137 | 9,921 |
| 7 | OF_Batch_MVS_7.1_JCL-Reference-Guide | 190 | 175 | 186,859 | 8,346 |
| 8 | OF_Batch_MVS_7.1_TSO-Administrator-Guide | 206 | 195 | 176,955 | 6,960 |
| 9 | OF_Batch_MVS_7.1_TJES-Guide | 152 | 139 | 169,613 | 6,058 |
| 10 | OF_Base_7.1_Dataset-Guide | 126 | 114 | 134,901 | 4,338 |

### 5.2 By Component

| Component | PDFs | Total Chars | Description |
|-----------|------|-------------|-------------|
| OF_Common_MVS | 7 | 1,665,020 | 공통 가이드 (Config, Error, Tool, Utility, Migration, Getting Started) |
| OF_Batch_MVS | 6 | 726,183 | 배치 처리 (TJES, JCL, TSO, Sort, IPF, Install) |
| OF_OSC | 6 | 677,556 | Online System for CICS |
| OF_Manager | 2 | 377,605 | 관리 도구 |
| OF_Base | 3 | 226,318 | 기반 시스템 |
| OF_OSI | 7 | 263,386 | Online System for IMS |
| OF_TACF | 2 | 159,771 | 보안 (TACF) |
| OF_GW | 3 | 136,616 | Gateway/WebTerminal |
| OF_HiDB | 2 | 82,111 | 계층형 DB |
| **Total** | **39** | **4,332,766** | |

---

## 6. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PyMuPDF | >= 1.23.0 | PDF 텍스트/테이블/TOC 추출 |
| Python | >= 3.8 | 스크립트 런타임 |

```bash
pip install PyMuPDF
```

---

## 7. Known Limitations

| # | Issue | Impact | Workaround |
|---|-------|--------|------------|
| 1 | 일부 PDF에서 프론트매터가 스킵되지 않음 (TOC 구조가 표준과 다른 경우) | "このガイドについて" 같은 서문이 포함됨 (학습에 유용하므로 문제 아님) | `--keep-front-matter` 옵션으로 제어 |
| 2 | 페이지 헤더/푸터 잔여 패턴 | `第1章 TJESの紹介  1` 같은 반복 텍스트가 남을 수 있음 | 추가 정규식 패턴 등록 가능 |
| 3 | 이미지/차트 내 텍스트 | PyMuPDF get_text()로는 이미지 내 텍스트 추출 불가 | Vision LLM (MiniCPM-V) 연동 필요 시 별도 파이프라인 |
| 4 | 중복 PDF (Migration-Guide 2개) | 동일 내용이 2번 추출됨 | 수동으로 중복 파일 제거 필요 |
| 5 | 테이블 위치 | 테이블이 페이지 끝에 추가됨 (원본 위치 미보존) | 복잡한 위치 기반 삽입은 향후 개선 |

---

## 8. Future Improvements

| # | Improvement | Priority | Description |
|---|-------------|----------|-------------|
| 1 | 다른 제품 디렉토리 지원 | High | `uploads/manuals/` 하위 19개 제품 전체로 확장 |
| 2 | 중복 문서 자동 감지 | Medium | 파일 해시 비교로 동일 PDF 자동 스킵 |
| 3 | 이미지 캡션 추출 | Low | `page.get_images()` + OCR로 이미지 텍스트 추가 |
| 4 | Chunking 통합 | Medium | 추출된 텍스트를 semantic chunk 단위로 분할 |
| 5 | 멀티프로세스 병렬 처리 | Low | 대규모 PDF 처리 시 `multiprocessing.Pool` 활용 |

---

## 9. Training Methodology

> **원칙**: 제품 매뉴얼에 대한 학습데이터이므로 학습 시간이 오래걸리더라도 **표준적이며 LLM이 정확한 답변**을 할 수 있는 학습 방식을 사용합니다.

### 9.1 3-Phase Training Pipeline

정확도 우선의 도메인 특화 LLM을 만들기 위해 **3단계 순차 학습 파이프라인**을 적용합니다.

```
Phase 1: CPT (Continued Pre-Training)          Phase 2: SFT (Supervised Fine-Tuning)         Phase 3: DPO (Optional)
─────────────────────────────────                ─────────────────────────────────              ────────────────────
Plain Text (corpus.txt)                          ChatML Q&A pairs                               Preference pairs
→ 도메인 지식 주입                                → 지시 따르기 학습                               → 응답 품질 정렬
→ Next-token prediction                          → Instruction-Response format                  → 선호도 기반 최적화
→ 기존 지식 유지 + 신규 지식 흡수                   → 기존 convert_to_qlora.py 활용                  → Hallucination 억제
```

| Phase | 입력 데이터 | 형식 | 목적 | 소요 시간 (예상) |
|-------|------------|------|------|-----------------|
| **Phase 1: CPT** | `corpus.txt` (8.5MB, ~1M tokens) | Plain text | 도메인 용어/구조/패턴 학습 | 2-4시간 (A100 1장) |
| **Phase 2: SFT** | `learning_dataset.json` (ChatML) | `<\|im_start\|>` format | 질의응답 형식 학습 | 1-2시간 (기존 파이프라인) |
| **Phase 3: DPO** | (선택) Preference 쌍 | chosen/rejected pairs | 응답 품질 정렬 | 1-2시간 |

### 9.2 Phase 1: Continued Pre-Training (CPT)

#### 9.2.1 왜 CPT가 필요한가?

기존 SFT-only 파이프라인의 한계:
- SFT는 **형식(format)** 을 학습하지만, **도메인 지식(knowledge)** 흡수에는 비효율적
- 매뉴얼의 전문 용어(예: `tjesmgr`, `DSALC`, `VSAM`)가 base model 어휘에 없거나 의미가 다름
- CPT를 먼저 수행하면 모델이 도메인 어휘와 문맥을 이해한 상태에서 SFT를 수행하므로 정확도 대폭 향상

#### 9.2.2 데이터 준비

**Data Mixing (Catastrophic Forgetting 방지)**

CPT에서 도메인 데이터만 사용하면 기존 일반 지식이 소실됩니다 (Catastrophic Forgetting). 이를 방지하기 위해 데이터 믹싱을 적용합니다:

| 데이터 카테고리 | 비율 | 소스 | 목적 |
|---------------|------|------|------|
| **도메인 (매뉴얼)** | 40% | `corpus.txt` (8.5MB) | OpenFrame 전문 지식 |
| **일반 일본어** | 30% | Wikipedia-ja, CC-100-ja | 일본어 능력 유지 |
| **코드** | 20% | StarCoder subset, JCL 샘플 | 코드 이해력 유지 |
| **수학/논리** | 10% | GSM8K, MATH subset | 추론 능력 유지 |

```
최종 학습 데이터: ~21MB (도메인 8.5MB ÷ 0.4 = ~21MB 총량)
├── domain/corpus.txt          8.5MB (40%)
├── general/wiki_ja.txt        6.3MB (30%)
├── code/code_mix.txt          4.2MB (20%)
└── math/math_mix.txt          2.1MB (10%)
```

> **주의**: 데이터 믹싱 비율은 실험을 통해 조정해야 합니다. 도메인 데이터 비율이 높을수록 전문성은 올라가지만, 범용 능력이 저하될 위험이 있습니다.

#### 9.2.3 CPT Hyperparameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Base Model** | `Qwen/Qwen2.5-7B-Instruct` | 현재 프로덕션 모델 |
| **Method** | QLoRA 4-bit (nf4) | A100 40GB 메모리 제약 |
| **LoRA Rank (r)** | **128** | CPT는 SFT(r=64)보다 높은 rank 필요. 더 많은 파라미터로 도메인 지식 흡수 |
| **LoRA Alpha** | 256 | alpha = 2 * r (표준 비율) |
| **LoRA Dropout** | 0.05 | CPT는 낮은 dropout (SFT의 0.1보다 낮음) |
| **Target Modules** | `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` + **`embed_tokens, lm_head`** | 임베딩 레이어 포함이 도메인 적응에 중요 |
| **Learning Rate** | **2e-5** | CPT는 SFT(2e-4)보다 10x 낮은 LR 사용 (기존 지식 보존) |
| **Embed/LM Head LR** | **2e-6** | 임베딩 레이어는 메인 LR의 1/10 (안정성) |
| **LR Scheduler** | Cosine with warmup | 안정적 수렴 |
| **Warmup Ratio** | 0.05 (5%) | 전체 스텝의 5%를 warmup에 사용 |
| **Weight Decay** | **0.1** | 과적합 방지 (소규모 코퍼스이므로 필수) |
| **Epochs** | **3** | 소규모 코퍼스(~1M tokens)이므로 다중 에폭 필요 |
| **Max Seq Length** | **4096** | 매뉴얼 섹션이 길므로 긴 컨텍스트 지원 |
| **Batch Size** | 1 (per device) | A100 40GB 메모리 제약 |
| **Gradient Accumulation** | 8 | 유효 배치 사이즈 = 8 |
| **Optimizer** | `paged_adamw_32bit` | 메모리 효율적 optimizer |
| **BF16** | True | A100 지원 |
| **Gradient Checkpointing** | True | 메모리 절약 |

#### 9.2.4 CPT 학습 구현 개요

```python
# Phase 1: CPT 학습 핵심 설정 (pseudocode)
from transformers import TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model

# QLoRA config (CPT용 - SFT보다 높은 rank)
lora_config = LoraConfig(
    r=128,                           # SFT(64)보다 높은 rank
    lora_alpha=256,
    lora_dropout=0.05,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
        "embed_tokens", "lm_head"    # 임베딩 포함 (CPT 핵심)
    ],
    task_type="CAUSAL_LM",
)

# Training arguments (CPT용)
training_args = TrainingArguments(
    output_dir="models/cpt_openframe_v1",
    num_train_epochs=3,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=2e-5,              # SFT(2e-4)보다 10x 낮음
    lr_scheduler_type="cosine",
    warmup_ratio=0.05,
    weight_decay=0.1,
    max_grad_norm=1.0,
    bf16=True,
    gradient_checkpointing=True,
    save_strategy="steps",
    save_steps=500,
    logging_steps=10,
    max_steps=-1,                    # 에폭 기반
)

# Dataset: 순수 텍스트 (next-token prediction)
# ChatML 템플릿 없이 plain text를 tokenize하여 학습
dataset = load_dataset("text", data_files={
    "train": [
        "uploads/training_text/MVS_Openframe_7.1/corpus.txt",  # 40%
        "data/general_ja.txt",                                   # 30%
        "data/code_mix.txt",                                     # 20%
        "data/math_mix.txt",                                     # 10%
    ]
})
```

### 9.3 Phase 2: SFT (Supervised Fine-Tuning)

CPT 완료 후, 기존 QLoRA SFT 파이프라인을 적용합니다.

#### 9.3.1 SFT Hyperparameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Base** | Phase 1 CPT adapter 병합된 모델 | CPT 지식 위에 SFT |
| **Method** | QLoRA 4-bit (nf4) | 기존 파이프라인과 동일 |
| **LoRA Rank (r)** | 64 | 기존 설정 유지 |
| **LoRA Alpha** | 16 | 기존 설정 유지 |
| **Target Modules** | `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` | 임베딩 제외 (SFT) |
| **Learning Rate** | 2e-4 | 기존 SFT LR |
| **Epochs** | 3 | 기존 설정 |
| **Max Seq Length** | 2048 | ChatML 형식은 상대적으로 짧음 |
| **Data Format** | ChatML (`<\|im_start\|>system...`) | `convert_to_qlora.py` 출력 |

#### 9.3.2 SFT 데이터

기존 `convert_to_qlora.py`로 생성된 ChatML 데이터를 사용합니다:

```json
{
  "messages": [
    {"role": "system", "content": "あなたはOpenFrame MVSの専門アシスタントです..."},
    {"role": "user", "content": "tjesmgrのBOOTコマンドについて説明してください"},
    {"role": "assistant", "content": "tjesmgr BOOTコマンドは、TJESノードを初期化するコマンドです..."}
  ]
}
```

### 9.4 Phase 3: DPO (선택 사항)

Hallucination 억제를 위한 선호도 정렬 학습입니다. E2E 테스트에서 발견된 Hallucination 케이스를 활용합니다.

#### 9.4.1 DPO 데이터 구성

```json
{
  "prompt": "tjesmgrについて説明してください",
  "chosen": "tjesmgrはTJESの管理ツールで、BOOT、CANCEL、CHANGE等のコマンドを提供します...",
  "rejected": "tjesmgrはOSCの管理ツールで、oscmgrと同様の機能を持ちます..."
}
```

| 소스 | 활용 방법 |
|------|----------|
| E2E Hallucination 결과 (`sentence_test_results.json`) | `notExpected` 키워드가 포함된 응답 → `rejected` |
| 올바른 RAG 응답 | `expected` 키워드가 포함된 응답 → `chosen` |

### 9.5 Evaluation Strategy

#### 9.5.1 평가 메트릭

| Phase | Metric | 방법 | 목표 |
|-------|--------|------|------|
| CPT | **Perplexity** | 홀드아웃 매뉴얼 텍스트에서 측정 | CPT 전 대비 30%+ 감소 |
| CPT | **도메인 용어 Recall** | OpenFrame 전문 용어 100개로 cloze test | 80%+ 정답률 |
| SFT | **E2E RAG Accuracy** | 기존 45개 테스트 케이스 | 기존 대비 향상 |
| SFT | **Hallucination Rate** | `notExpected` 키워드 포함율 | 10% 이하 |
| DPO | **Win Rate** | Chosen vs Rejected 선택 비율 | 90%+ |

#### 9.5.2 평가 실행

```bash
# 1. CPT 후 Perplexity 측정
python scripts/training/evaluate_perplexity.py \
  --model models/cpt_openframe_v1 \
  --test-data uploads/training_text/MVS_Openframe_7.1/test_holdout.txt

# 2. SFT 후 E2E Hallucination 테스트
cd e2e && node e2e_sentence_test.js

# 3. 수동 품질 평가 (10개 대표 질문)
python scripts/training/manual_eval.py \
  --model models/sft_openframe_v1 \
  --questions scripts/training/eval_questions.json
```

### 9.6 Execution Plan

#### Step 1: 데이터 준비

```bash
# 1-1. 도메인 데이터 (이미 완료)
python scripts/training/extract_plain_text.py \
  -i "uploads/manuals/MVS_Openframe 7.1_v3.1.3_JP" --merge

# 1-2. 믹싱 데이터 준비 (일반/코드/수학)
python scripts/training/prepare_mixing_data.py \
  --domain uploads/training_text/MVS_Openframe_7.1/corpus.txt \
  --domain-ratio 0.4 \
  --output uploads/training_text/MVS_Openframe_7.1/mixed_corpus.txt
```

#### Step 2: Phase 1 CPT 실행

```bash
python scripts/training/run_cpt_training.py \
  --base-model Qwen/Qwen2.5-7B-Instruct \
  --train-data uploads/training_text/MVS_Openframe_7.1/mixed_corpus.txt \
  --output-dir models/cpt_openframe_v1 \
  --lora-rank 128 \
  --learning-rate 2e-5 \
  --epochs 3 \
  --max-seq-length 4096 \
  --gpu 5
```

#### Step 3: CPT adapter 병합

```bash
python scripts/training/merge_adapter.py \
  --base-model Qwen/Qwen2.5-7B-Instruct \
  --adapter models/cpt_openframe_v1 \
  --output models/qwen2.5-7b-openframe-cpt
```

#### Step 4: Phase 2 SFT 실행

```bash
# 기존 SFT 파이프라인 사용 (base model만 CPT 모델로 교체)
python scripts/training/qlora_trainer.py \
  --base-model models/qwen2.5-7b-openframe-cpt \
  --train-data uploads/summaries/multi_lora_v9_improved/ \
  --output-dir models/sft_openframe_v1 \
  --lora-rank 64 \
  --learning-rate 2e-4 \
  --epochs 3
```

#### Step 5: 평가 및 배포

```bash
# E2E Hallucination 테스트
cd e2e && node e2e_sentence_test.js

# 결과 비교 (CPT+SFT vs SFT-only)
python scripts/training/compare_results.py \
  --baseline e2e/sentence_test_results_baseline.json \
  --new e2e/sentence_test_results.json
```

### 9.7 기존 인프라와의 호환성

| 항목 | 현재 (SFT-only) | 개선 (CPT+SFT) | 변경점 |
|------|-----------------|----------------|--------|
| Base Model | Qwen/Qwen2.5-7B-Instruct | 동일 | 없음 |
| GPU | A100-SXM4-40GB (Device 5) | 동일 | 없음 |
| QLoRA 4-bit | nf4, double quant | 동일 | 없음 |
| LoRA Rank | r=64 | CPT: r=128, SFT: r=64 | CPT 시 rank 상향 |
| Learning Rate | 2e-4 | CPT: 2e-5, SFT: 2e-4 | CPT 시 LR 10x 감소 |
| Target Modules | 7 linear layers | CPT: +embed_tokens, lm_head | CPT 시 임베딩 포함 |
| Serving (vLLM) | port 12815, 24 adapters | 동일 | adapter 교체만 필요 |
| Framework | transformers + trl + peft | 동일 | 추가 의존성 없음 |

### 9.8 학습 방식 비교 요약

| 방식 | 장점 | 단점 | 권장 시나리오 |
|------|------|------|-------------|
| **SFT-only** (현재) | 빠른 학습, 즉시 Q&A 가능 | 도메인 용어 이해 부족, Hallucination 높음 | 프로토타이핑, 빠른 검증 |
| **CPT+SFT** (권장) | 도메인 지식 깊은 이해, 정확도 높음 | 학습 시간 2-3배 증가, 믹싱 데이터 준비 필요 | **프로덕션 배포** |
| **CPT+SFT+DPO** (최적) | 최고 정확도, Hallucination 최소화 | 학습 시간 3-4배, DPO 데이터 수동 구축 필요 | 고정밀 요구 환경 |

> **결론**: 제품 매뉴얼 KMS 시스템의 정확도를 최우선으로 하므로, **CPT+SFT+DPO** 전체 파이프라인을 적용합니다.

---

## 10. Implementation Status

### 10.1 구현된 스크립트 (7개)

| # | Script | Purpose | Status |
|---|--------|---------|--------|
| 1 | `scripts/training/prepare_mixing_data.py` | CPT 데이터 믹싱 (40/30/20/10) | Implemented |
| 2 | `scripts/training/run_cpt_training.py` | Phase 1: CPT (Dual LR, r=128) | Implemented |
| 3 | `scripts/training/merge_adapter.py` | LoRA adapter 병합 유틸리티 | Implemented |
| 4 | `scripts/training/generate_dpo_data.py` | DPO preference pair 생성 (3전략) | Implemented |
| 5 | `scripts/training/run_dpo_training.py` | Phase 3: DPO (DPOTrainer) | Implemented |
| 6 | `scripts/training/evaluate_perplexity.py` | Perplexity + Cloze test | Implemented |
| 7 | `scripts/training/run_full_pipeline.py` | 전체 오케스트레이터 | Implemented |

### 10.2 Quick Start

```bash
# 전체 파이프라인 실행 (CPT → SFT → DPO)
python scripts/training/run_full_pipeline.py --phase all --gpu 5

# 개별 Phase 실행
python scripts/training/run_full_pipeline.py --phase cpt --gpu 5
python scripts/training/run_full_pipeline.py --phase sft --gpu 5
python scripts/training/run_full_pipeline.py --phase dpo --gpu 5

# 오프라인 모드 (air-gapped GPU 서버)
python scripts/training/run_full_pipeline.py --phase all --gpu 5 --offline

# 실패 지점부터 재시작
python scripts/training/run_full_pipeline.py --phase all --gpu 5 --resume

# 설정 확인 (Dry Run)
python scripts/training/run_full_pipeline.py --phase all --dry-run
```

### 10.3 DPO 데이터 생성 결과

```
전략별 생성 pair 수:
  factual_product_swap: 1,014  (명령어 제품명 교체)
  factual_desc_swap:      797  (명령어 설명 교차)
  sft_cross_match:        177  (SFT 교차 제품 오답)
  e2e_cross_product:       12  (E2E notExpected 패턴)
  ─────────────────────────────
  Total (중복 제거 후):  2,000 pairs (cap)
  소스: 명령어 4,630개, 용어 1,361개, E2E 53개 테스트, SFT 22개 제품
```
