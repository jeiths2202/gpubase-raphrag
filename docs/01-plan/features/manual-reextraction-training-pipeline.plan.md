# Manual Re-extraction & Training Pipeline Plan

> **Feature**: manual-reextraction-training-pipeline
> **Created**: 2026-02-20
> **Updated**: 2026-02-21 (v10 검증 기반 개선)
> **Author**: Claude Opus 4.6
> **Status**: Plan Phase → Do Phase (Iteration 2)
> **Level**: Enterprise

## 1. 배경 및 목적

### 1.1 현재 상황
- **매뉴얼 PDF**: `uploads/manuals/` 에 19개 제품, 245개 PDF 존재
- **기존 요약본**: `uploads/summaries/` 에 error-codes, glossary, commands, configs, apis, concepts, procedures, structures 디렉토리
- **기존 학습 데이터**: `multi_lora_v9_improved/` (v9, 2,647개 레코드, 22개 제품)
- **기존 CPT 텍스트**: `uploads/training_text/corpus.txt` (72MB, ~34M tokens)

### 1.2 문제점 (초기)

| 문제 | 영향 | 증거 |
|------|------|------|
| **에러코드 99.7% 빈 항목** | RAG 응답에서 에러 정보 환각 | -5212 에러 Hallucination 발생 (E2E 테스트) |
| **기존 파서 PDF 포맷 불일치** | `error_parser.py`의 regex가 PyMuPDF 추출 포맷 미매칭 | Format A(라벨 후행) vs Format B(라벨 선행) 미분류 |
| **단일 언어(일본어) 학습 데이터** | 한국어/영어 쿼리 처리 성능 저하 | v9 데이터셋 language=ja 편중 |
| **요약본 기반 Q-A 품질 저하** | 원본 PDF 정보 누락 → 부정확한 학습 데이터 | v9 removal rate 59.3% (4,040개 제거) |
| **CPT 텍스트 품질 미검증** | 도메인 지식 주입 효과 불확실 | corpus.txt 품질 체크 미실시 |

### 1.3 v10 검증 결과 및 잔존 이슈 (2026-02-21)

> **v10 Do Phase 완료 후 검증 결과**. 초기 문제의 대부분은 해결되었으나, 4가지 잔존 이슈를 식별함.

#### v10 달성 현황

| 항목 | v9 | v10 | 개선율 |
|------|-----|-----|--------|
| SFT 총 레코드 | 2,647 | 18,112 (8,257 OF10) | +584% |
| 제품 수 | 22 | 24 (OF 10개 분리 완료) | +2 신규 |
| 에러코드 채워짐 비율 | ~0.3% | ≥99% | 해결 |
| Q-A 품질 점수 | 41.69% | 87.95% | +46.3p |
| ChatML 포맷 호환 | 100% | 100% | 유지 |
| CPT 품질 | 미검증 | 100% (4,220 chunks) | 해결 |
| DPO 품질 | 100% | 100% (2,000 pairs) | 유지 |

#### 잔존 이슈 4가지

| # | 이슈 | 현황 | 영향도 | 우선순위 |
|---|------|------|--------|----------|
| I-01 | **SFT 중복 14.5%** | 1,196/8,257 건 중복 (gateway 31%, base 27%) | 중 | P0 |
| I-02 | **한국어 데이터 0%** | OpenFrame 10개 제품 전부 일본어만 | 고 | P0 |
| I-03 | **CPT 6개 제품 누락** | batch, base, osc, tacf, osi, aim, hidb = 0 chunks | 고 | P0 |
| I-04 | **HiDB 35건 극소량** | 학습 효과가 낮을 가능성 | 저 | P1 |

#### I-01: SFT 중복 상세

```
제품별 중복률:
┌──────────────────────┬────────┬───────────┬───────┐
│         제품         │ 레코드 │   중복    │ 유효  │
├──────────────────────┼────────┼───────────┼───────┤
│ openframe_gateway_v2 │ 254    │ 78 (31%) │ 176   │ ← 최악
│ openframe_base_v2    │ 488    │ 130 (27%) │ 358   │
│ openframe_tacf_v2    │ 250    │ 64 (26%)  │ 186   │
│ openframe_aim_v2     │ 275    │ 59 (21%)  │ 216   │
│ openframe_common_v2  │ 4,512  │ 663 (15%) │ 3,849 │
│ openframe_batch_v2   │ 1,603  │ 194 (12%) │ 1,409 │
│ openframe_osc_v2     │ 401    │ 1         │ 400   │
│ openframe_vos3_v2    │ 287    │ 7         │ 280   │
│ openframe_osi_v2     │ 152    │ 0         │ 152   │
│ openframe_hidb_v2    │ 35     │ 0         │ 35    │
└──────────────────────┴────────┴───────────┴───────┘
```

**원인 분석**: MVS/MSP/XSP 3개 디렉토리에서 동일 제품의 PDF가 버전만 다르게 존재
- 예: `OF_Base_MVS_7.1.pdf`, `OF_Base_MSP_7.3.pdf`, `OF_Base_XSP_7.3.pdf` → 동일 내용, 3중 중복

#### I-02: 한국어 데이터 부재

- OpenFrame 매뉴얼은 전부 일본어 (일본 고객사 대상)
- JEUS만 한국어 매뉴얼 보유 (1,811건 생성 완료)
- 한국어 Q-A를 얻으려면 **일본어 원문 → 한국어 번역** 필요

#### I-03: CPT 제품별 커버리지

```
CPT 코퍼스 분석 (4,220 chunks):
┌──────────────────────────────────┬──────────┐
│              제품                │  chunks  │
├──────────────────────────────────┼──────────┤
│ openframe_common (MVS/MSP/XSP)  │ 1,506    │ ← 36% (과대)
│ jeus_v2 (KO)                    │ 349      │
│ tibero7, tmax, ofcobol, ...     │ 2,365    │ ← 비-OF 제품
│ batch, base, osc, tacf, osi,    │ 0        │ ← 누락!
│ aim, hidb, gateway, ndb         │          │
└──────────────────────────────────┴──────────┘
```

**원인**: CPT 생성기가 디렉토리 단위로만 처리하여 MVS/MSP/XSP → `openframe_common`으로 일괄 매핑

#### I-04: HiDB 데이터 극소량

- `openframe_hidb_v2`: SFT 35건 (전체의 0.4%)
- HiDB 매뉴얼이 1-2개 PDF로 제한적
- 양이 적어 LoRA 어댑터 학습 시 과적합(overfitting) 우려

### 1.4 목표

#### Phase 1 목표 (v10 초기 — 완료)
1. ~~**전체 매뉴얼 재추출**: 245개 PDF를 PyMuPDF로 처음부터 다시 추출~~ ✅
2. **3개 언어 지원**: 한국어, 영어, 일본어로 학습 데이터 생성 — ⚠️ 부분 달성 (일본어만)
3. ~~**4가지 학습 포맷**: SFT, DPO, CPT, ChatML 생성~~ ✅
4. ~~**품질 검증 파이프라인**: 자동화된 학습 데이터 품질 체크~~ ✅

#### Phase 2 목표 (v10 개선 — 현재)
5. **SFT 중복 제거**: 14.5% → 3% 이하로 감소
6. **한국어 Q-A 생성**: OpenFrame 10개 제품에 한국어 데이터 추가
7. **CPT 제품별 분할**: 6개 누락 제품의 CPT 코퍼스 생성
8. **소량 제품 증강**: HiDB 35건 → 100건 이상 확보

## 2. 요구사항

### 2.1 기능 요구사항

| ID | 요구사항 | 우선순위 | 설명 |
|----|----------|----------|------|
| FR-01 | PyMuPDF 기반 전체 PDF 텍스트 추출 | P0 | 245개 PDF에서 텍스트, TOC, 테이블, 이미지 메타 추출 |
| FR-02 | 구조화된 청크 분할 | P0 | TOC 기반 계층적 섹션 분할 (Chapter > Section > Subsection) |
| FR-03 | 에러코드 전용 파서 개선 | P0 | Format A/B 자동 감지, 모듈별 분류 |
| FR-04 | 명령어/설정/API/용어 추출 | P0 | 기존 comprehensive_parser 대체 |
| FR-05 | SFT 학습 데이터 생성 (ChatML) | P0 | Qwen2.5 `<\|im_start\|>/<\|im_end\|>` 포맷 |
| FR-06 | CPT 학습 데이터 생성 (Plain Text) | P0 | `<\|endoftext\|>` 구분, 4096 토큰 청크 |
| FR-07 | DPO 학습 데이터 생성 (Preference) | P1 | chosen/rejected 쌍 자동 생성 |
| FR-08 | 3개 언어 Q-A 생성 | P1 | 원문(JA) + 번역(KO/EN) 학습 데이터 |
| FR-09 | 학습 데이터 품질 체크 | P0 | 길이/중복/Q-A 일치도/언어 균형 검증 |
| FR-10 | 제품별 분할 | P1 | 19개 제품별 독립 학습 세트 (Multi-LoRA용) |
| FR-11 | Train/Eval 분할 | P1 | 80:20 자동 분할, stratified by product |

### 2.2 비기능 요구사항

| ID | 요구사항 | 기준 |
|----|----------|------|
| NFR-01 | 전체 추출 시간 | 245개 PDF → 30분 이내 |
| NFR-02 | 메모리 사용량 | 8GB 이내 (단일 PDF 처리 시 500MB 이내) |
| NFR-03 | 에러코드 추출 정확도 | ≥99% (빈 항목 ≤1%) |
| NFR-04 | Q-A 품질 점수 | ≥95% (truncated/meaningless 5% 이하) |
| NFR-05 | 언어 균형 | JA:KO:EN = 40:30:30 (±10%) |
| NFR-06 | ChatML 호환성 | Qwen2.5 special tokens 100% 호환 |
| NFR-07 | 재실행 가능 | 멱등성 보장 (동일 입력 → 동일 출력) |

## 3. 솔루션 설계

### 3.1 전체 파이프라인 아키텍처

```
Phase 1: PDF 추출
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
uploads/manuals/ (19 products, 245 PDFs)
    │
    ├─► PyMuPDF 텍스트 추출
    │     ├─ TOC 구조 파싱
    │     ├─ 페이지별 텍스트 추출
    │     ├─ 테이블 감지 및 추출
    │     └─ 이미지 메타데이터 수집
    │
    └─► Raw Text Store
          uploads/extracted_raw/{product}/{pdf_name}.json

Phase 2: 구조화 파싱
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Raw Text Store
    │
    ├─► 에러코드 파서 (Format A/B 자동감지)
    │     └─► uploads/summaries/error-codes/*.md
    │
    ├─► 명령어 파서
    │     └─► uploads/summaries/commands/*.md
    │
    ├─► 설정 파서
    │     └─► uploads/summaries/configs/*.md
    │
    ├─► API 파서
    │     └─► uploads/summaries/apis/*.md
    │
    ├─► 용어/개념 파서
    │     └─► uploads/summaries/glossary/*.md
    │
    └─► 구조 파서 (TOC 기반)
          └─► uploads/summaries/structures/*.json

Phase 3: 학습 데이터 생성
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Summaries + Raw Text
    │
    ├─► SFT Generator (ChatML)
    │     ├─ 타입별 Q-A 템플릿 (command/error/config/api/concept)
    │     ├─ 3개 언어 생성 (JA→KO, JA→EN)
    │     └─► uploads/training/v10/sft/{product}/train.jsonl
    │
    ├─► CPT Generator (Plain Text)
    │     ├─ 원문 텍스트 청킹 (4096 tokens)
    │     ├─ <|endoftext|> 문서 경계
    │     └─► uploads/training/v10/cpt/corpus.txt
    │
    └─► DPO Generator (Preference Pairs)
          ├─ Oracle vs Distractor 문서
          ├─ 교차제품 방해 문서
          └─► uploads/training/v10/dpo/preferences.jsonl

Phase 4: 품질 검증
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All Training Data
    │
    ├─► Length Validator (min/max 토큰)
    ├─► Duplicate Detector (cosine similarity ≥0.95)
    ├─► Q-A Coherence Checker (단어 겹침 ≥30%)
    ├─► Language Balance Checker (JA/KO/EN 비율)
    ├─► ChatML Format Validator (special tokens 검증)
    └─► Quality Report
          └─► uploads/training/v10/quality_report.json
```

### 3.2 디렉토리 구조

```
scripts/
├── manual_reextractor/              # 새 스크립트 패키지
│   ├── __init__.py
│   ├── main.py                      # CLI 진입점
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── pdf_extractor.py         # PyMuPDF 텍스트/TOC/테이블 추출
│   │   ├── error_extractor.py       # 에러코드 추출 (Format A/B)
│   │   ├── command_extractor.py     # 명령어 추출
│   │   ├── config_extractor.py      # 설정 파라미터 추출
│   │   ├── api_extractor.py         # API 함수 추출
│   │   └── glossary_extractor.py    # 용어/개념 추출
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── summary_generator.py     # Markdown 요약본 생성
│   │   ├── sft_generator.py         # SFT ChatML 학습 데이터
│   │   ├── cpt_generator.py         # CPT Plain Text 학습 데이터
│   │   ├── dpo_generator.py         # DPO Preference Pairs
│   │   └── index_generator.py       # 인덱스 재생성
│   ├── translators/
│   │   ├── __init__.py
│   │   └── trilingual.py            # JA→KO, JA→EN 번역 (템플릿 + 룰기반)
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── length_validator.py      # 토큰 길이 검증
│   │   ├── duplicate_detector.py    # 중복 검출 (cosine similarity)
│   │   ├── coherence_checker.py     # Q-A 일치도 검증
│   │   ├── language_checker.py      # 언어 균형 검증
│   │   └── format_validator.py      # ChatML 포맷 검증
│   ├── models/
│   │   ├── __init__.py
│   │   ├── extracted.py             # 추출 데이터 모델
│   │   └── training.py              # 학습 데이터 모델
│   └── config.py                    # 설정 (경로, 임계값, 제품 매핑)

uploads/
├── extracted_raw/                   # Phase 1 출력 (원시 추출)
│   ├── {product_id}/
│   │   └── {pdf_name}.json
│   └── extraction_stats.json
├── summaries/                       # Phase 2 출력 (기존 디렉토리 갱신)
│   ├── error-codes/                 # 갱신
│   ├── commands/                    # 갱신
│   ├── configs/                     # 갱신
│   ├── apis/                        # 갱신
│   ├── glossary/                    # 갱신
│   └── structures/                  # 갱신
└── training/
    └── v10/                         # Phase 3 출력
        ├── sft/
        │   ├── train_all.jsonl      # 전체 SFT (ChatML)
        │   ├── eval_all.jsonl       # 전체 평가셋
        │   └── {product_id}/
        │       ├── train.jsonl
        │       └── eval.jsonl
        ├── cpt/
        │   ├── corpus_ja.txt        # 일본어 원문
        │   ├── corpus_ko.txt        # 한국어 (JEUS KR 포함)
        │   └── corpus_en.txt        # 영어
        ├── dpo/
        │   ├── preferences.jsonl    # DPO 쌍
        │   └── stats.json
        └── quality_report.json      # 품질 보고서
```

### 3.3 Phase 1: PDF 추출 상세

#### 3.3.1 PyMuPDF 추출 전략

```python
# 각 PDF에서 추출하는 데이터
class PDFExtraction:
    product_id: str           # 제품 ID (디렉토리명 기반)
    pdf_name: str             # PDF 파일명
    language: str             # 감지된 언어 (ja/ko/en)
    total_pages: int
    toc: List[TOCEntry]       # 목차 (level, title, page)
    pages: List[PageContent]  # 페이지별 텍스트
    tables: List[TableData]   # 감지된 테이블
    metadata: dict            # PDF 메타데이터
```

#### 3.3.2 제품별 처리

| 제품 | PDFs | 언어 | 특이사항 |
|------|------|------|---------|
| MVS_Openframe 7.1 | 39 | JA | Error Reference Guide 포함 (454p) |
| MSP_Openframe 7.3 | 35 | JA | Error Reference Guide 포함 (244p) |
| XSP_Openframe 7.3 | 30 | JA | Error Reference Guide 포함 (243p) |
| VOS3_Openframe 2.0 | 10 | JA | Error Reference Guide 포함 (194p) |
| Tibero 7 FixSet01 | 23 | JA | Error Reference Guide 포함 (538p) |
| Tmax_6.0 | 34 | JA | - |
| JEUS_8.5 | 24 | **KR** | 유일한 한국어 매뉴얼 |
| JEUS_8 | 23 | JA | - |
| OFCOBOL_4 | 2 | JA | - |
| OFAsm_4 | 2 | JA | - |
| ProSort_2SP3 | 2 | JA | - |
| ProSync_FS01 | 3 | JA | - |
| ProTrieve_v2_1 | 1 | JA | 최소 PDF |
| OFGW_7 | 4 | JA | - |
| OFManager_7.2 | 2 | JA | - |
| OFMiner_7Fix1 | 2 | JA | - |
| OFPli_3 | 3 | JA | - |
| OFStudio_7 | 2 | JA | - |
| WebtoB_5Fix2 | 4 | JA | - |

### 3.4 Phase 2: 구조화 파싱 상세

#### 3.4.1 에러코드 추출기 (개선판)
- `scripts/fix_error_descriptions.py`의 검증된 로직 재사용
- Format A (라벨 후행: Base 모듈) + Format B (라벨 선행: AIM/NDB) 자동 감지
- 40+ 모듈 → 파일 prefix 매핑 (BASE, BATCH, AIM, NDB, TACF)
- TOC 라인 자동 필터링

#### 3.4.2 명령어 추출기
- 패턴: `### {command_name}`, `구문:`, `설명:`, `옵션:`, `사용예:`
- 대상: tjesmgr, tacfmgr, hidbmgr, oscmgr, osimgr, catmgr, volmgr 등

#### 3.4.3 설정 추출기
- 패턴: `{SECTION}:{KEY} = {VALUE}`, `설명:`, `기본값:`, `범위:`
- 대상: tjes.conf, osc.conf, tacf.conf, ds.conf 등

#### 3.4.4 Q-A 템플릿 (SFT용)

| 타입 | 질문 템플릿 (JA) | 질문 템플릿 (KO) | 질문 템플릿 (EN) |
|------|------------------|------------------|------------------|
| error | `エラー {code} の原因と対処方法は？` | `에러 {code}의 원인과 해결방법은?` | `What causes error {code} and how to fix it?` |
| command | `{name} コマンドの使い方は？` | `{name} 명령어 사용법은?` | `How to use {name} command?` |
| config | `{key} 設定パラメータの説明は？` | `{key} 설정 파라미터 설명은?` | `What does {key} configuration parameter do?` |
| api | `{name} 関数の使い方は？` | `{name} 함수 사용법은?` | `How to use {name} function?` |
| concept | `{name} とは何ですか？` | `{name}이란 무엇인가요?` | `What is {name}?` |

### 3.5 Phase 3: 학습 데이터 포맷

#### 3.5.1 SFT (ChatML) 포맷
```json
{
  "text": "<|im_start|>system\nあなたはOpenFrameの専門家です。<|im_end|>\n<|im_start|>user\nエラー -5212 の原因と対処方法は？<|im_end|>\n<|im_start|>assistant\nエラー -5212 (DSALC_ERR_DATASET_NOT_FOUND) は既存のデータセットが見つからない場合に発生します。\n\n対処方法: 状況を確認してデータセットを作成した後、再実行します。<|im_end|>",
  "product": "openframe_common_v2",
  "language": "ja",
  "source": "OF_Common_MVS_7.1_Error-Reference-Guide_v3.1.3_JP.pdf",
  "type": "error"
}
```

#### 3.5.2 CPT (Plain Text) 포맷
```
<|endoftext|>
OpenFrame Base エラーコード

DSALC_ERR_NO_RESOURCE (-5001)
リソースが足りない場合に発生します。
データセットの設定を変更するか、システム管理者にお問い合わせください。

DSALC_ERR_INVALID_DSNAME (-5202)
データセット名が無効な場合に発生します。
有効なデータセット名を指定して再実行します。
<|endoftext|>
```

#### 3.5.3 DPO (Preference Pairs) 포맷
```json
{
  "prompt": "<|im_start|>system\nあなたはOpenFrameの専門家です。<|im_end|>\n<|im_start|>user\ntjesmgrコマンドについて説明してください。<|im_end|>\n",
  "chosen": "<|im_start|>assistant\ntjesmgrはTJES (Tmax Job Entry Subsystem) の管理コマンドです。主な機能: BOOT (起動), SHUTDOWN (停止), ...<|im_end|>",
  "rejected": "<|im_start|>assistant\ntjesmgrはOSC (Online SC) のトランザクション管理コマンドです。CICS互換の...<|im_end|>",
  "product": "openframe_batch_v2",
  "strategy": "cross_product"
}
```

#### 3.5.4 ChatML (Qwen2.5 Special Tokens)
```
Token IDs:
- <|im_start|> = 151644
- <|im_end|>   = 151645 (eos_token)
- <|endoftext|> = 151643 (padding)
```

### 3.6 Phase 4: 품질 검증 상세

#### 3.6.1 검증 항목

| 검증 | 기준 | 불합격 시 처리 |
|------|------|---------------|
| 최소 길이 | instruction ≥10 chars, response ≥20 chars | 제거 |
| 최대 길이 | response ≤4096 tokens | 자르기 |
| 중복 | cosine similarity ≥0.95 | 하나만 보존 |
| Q-A 일치도 | 키워드 겹침 ≥30% | 제거 |
| 언어 감지 | instruction/response 동일 언어 | 제거 |
| ChatML 포맷 | special tokens 존재 여부 | 재생성 |
| 빈 필드 | description/solution 비어있으면 | 제거 |
| 제품 균형 | 제품당 최소 20개 | 증강 경고 |

#### 3.6.2 품질 보고서 형식
```json
{
  "version": "v10",
  "generated": "2026-02-20T...",
  "total_records": 0,
  "by_format": {
    "sft": { "total": 0, "train": 0, "eval": 0 },
    "cpt": { "total_tokens": 0, "chunks": 0 },
    "dpo": { "total_pairs": 0 }
  },
  "by_language": { "ja": 0, "ko": 0, "en": 0 },
  "by_product": {},
  "quality_checks": {
    "passed": 0,
    "failed": 0,
    "removal_breakdown": {},
    "average_score": 0.0
  },
  "comparison_with_v9": {
    "record_change": "+N%",
    "quality_change": "+N%",
    "new_products": [],
    "language_coverage": "JA+KO+EN vs JA-only"
  }
}
```

## 4. v10 개선 계획 (Iteration 2)

### 4.1 I-01 해결: SFT 중복 제거

#### 원인
MVS/MSP/XSP 3개 디렉토리가 동일 OpenFrame 컴포넌트(Base, Batch, TACF 등)의 버전별 PDF를 포함.
같은 제품의 거의 동일한 내용이 3중으로 생성됨.

#### 해결 전략: 2단계 중복 제거

**Step 1: 사전 중복 방지 (생성 단계)**
- `sft_generator.py`에 PDF 파일명 기반 중복 감지 추가
- 동일 컴포넌트의 버전별 PDF (예: `OF_Base_MVS_7.1.pdf` vs `OF_Base_MSP_7.3.pdf`)
  → 최신 버전(가장 높은 버전/가장 큰 파일)만 사용
- `config.py`에 `PDF_DEDUP_STRATEGY = "latest_version"` 설정 추가

```python
# config.py 추가
PDF_DEDUP_STRATEGY = "latest_version"  # "latest_version" | "largest_file" | "all"

# sft_generator.py 추가 로직
def _deduplicate_pdfs(self, pdfs_by_product: Dict[str, List[Path]]) -> Dict[str, List[Path]]:
    """동일 컴포넌트의 버전별 중복 PDF를 필터링"""
    for product_id, pdfs in pdfs_by_product.items():
        # OF_{Component}_{Platform}_{Version}.pdf → Component 기준 그룹핑
        groups = defaultdict(list)
        for pdf in pdfs:
            component = self._extract_component_name(pdf.stem)
            groups[component].append(pdf)

        # 각 그룹에서 최신 버전/최대 파일만 선택
        deduped = []
        for component, group_pdfs in groups.items():
            if len(group_pdfs) == 1:
                deduped.append(group_pdfs[0])
            else:
                selected = max(group_pdfs, key=lambda p: p.stat().st_size)
                deduped.append(selected)
        pdfs_by_product[product_id] = deduped
    return pdfs_by_product
```

**Step 2: 사후 중복 제거 (검증 단계)**
- `validate_training.py`의 기존 duplicate detector를 강화
- exact match + TF-IDF cosine similarity ≥ 0.90 → 중복 판정 (현재 0.95에서 하향)
- 중복 쌍 중 응답이 더 긴 레코드를 보존

#### 목표
| 지표 | 현재 | 목표 |
|------|------|------|
| 전체 중복률 | 14.5% (1,196건) | ≤3% (~210건) |
| gateway 중복률 | 31% | ≤5% |
| base 중복률 | 27% | ≤5% |
| 유효 레코드 | 7,061 | ≥7,000 (중복 제거 후) |

### 4.2 I-02 해결: 한국어 데이터 생성

#### 전략: 룰 기반 템플릿 번역 (LLM 미사용)

OpenFrame 매뉴얼이 전부 일본어이므로, SFT의 Q-A 쌍을 한국어로 번역하여 생성.
LLM 기반 번역은 환각 리스크가 있으므로, **템플릿 기반 룰 번역**을 사용.

```python
# translators/ko_translator.py

# 질문 템플릿 번역 매핑
JA_TO_KO_QUESTION_TEMPLATES = {
    # error 타입
    "エラー {code} の原因と対処方法は？": "에러 {code}의 원인과 해결 방법은?",
    "エラーコード {code} について説明してください": "에러 코드 {code}에 대해 설명해 주세요",

    # command 타입
    "{name} コマンドの使い方は？": "{name} 명령어 사용법은?",
    "{name} コマンドについて説明してください": "{name} 명령어에 대해 설명해 주세요",

    # config 타입
    "{key} 設定パラメータの説明は？": "{key} 설정 파라미터 설명은?",

    # concept 타입
    "{name} とは何ですか？": "{name}란 무엇인가요?",
    "{name} について説明してください": "{name}에 대해 설명해 주세요",
}

# 응답 내 기술 용어는 번역하지 않음 (고유명사 보존)
PRESERVE_TERMS = [
    "OpenFrame", "TJES", "TACF", "HiDB", "OSC", "OSI",
    "tjesmgr", "tacfmgr", "hidbmgr", "oscmgr", "osimgr",
    "VSAM", "KSDS", "ESDS", "JCL", "COBOL", "PDS",
    # ... 전체 기술 용어 목록
]

# 응답 번역 전략
# 1. 질문: 템플릿 매칭으로 한국어 질문 생성
# 2. 응답: 일본어 응답을 유지 (기술 문서이므로 원문 보존)
#    → 또는: 공통 패턴만 한국어화 (설명, 원인, 해결방법 헤더)
RESPONSE_HEADER_MAP = {
    "原因": "원인",
    "対処方法": "해결 방법",
    "説明": "설명",
    "使用方法": "사용 방법",
    "オプション": "옵션",
    "注意事項": "주의 사항",
    "関連コマンド": "관련 명령어",
    "参照": "참조",
    "デフォルト値": "기본값",
    "設定範囲": "설정 범위",
}
```

#### 생성 방법

```
일본어 SFT 레코드 (7,061건 유효)
    │
    ├─► 질문 템플릿 매칭 → 한국어 질문 생성
    │     (5가지 타입별 템플릿 치환)
    │
    ├─► 응답 헤더 번역 → 구조 한국어화
    │     (原因→원인, 対処方法→해결 방법 등)
    │
    ├─► 기술 용어 보존 (PRESERVE_TERMS)
    │     (tjesmgr, VSAM, KSDS 등 번역 안 함)
    │
    └─► 한국어 SFT 레코드 생성
          uploads/training/v10/sft/{product}/train.jsonl (language=ko 추가)
```

#### 목표
| 지표 | 현재 | 목표 |
|------|------|------|
| 한국어 비율 (OF 10제품) | 0% | ≥40% (ja:ko = 60:40) |
| 한국어 레코드 수 | 0 | ~4,700건 (7,061 × 0.67) |
| 총 SFT 레코드 (OF) | 7,061 | ~11,800건 (ja + ko) |

### 4.3 I-03 해결: CPT 제품별 분할

#### 원인
`cpt_generator.py`가 디렉토리 단위로 처리하여 MVS/MSP/XSP 전체를 `openframe_common`으로 매핑.
SFT에서는 `_resolve_product_id()`로 PDF별 제품 식별을 구현했으나, CPT에는 미적용.

#### 해결 전략: CPT 생성기에 동일한 PDF별 제품 분할 적용

```python
# cpt_generator.py 수정

def generate_all(self):
    """CPT 코퍼스를 제품별로 분할 생성"""
    product_texts = defaultdict(list)  # product_id → [text_chunks]

    for dir_name, dir_path in self.manual_dirs:
        product_id = DIRECTORY_TO_PRODUCT.get(dir_name)
        use_split = dir_name in COMPONENT_SPLIT_DIRS

        for pdf in dir_path.glob("*.pdf"):
            # SFT와 동일한 로직으로 제품 식별
            resolved_pid = self._resolve_product_id(
                pdf.name, product_id, use_split
            )

            text = extract_text_from_pdf(pdf)
            product_texts[resolved_pid].append(text)

    # 언어별 코퍼스 파일 생성
    for lang in ["ja", "ko"]:
        corpus_path = self.output_dir / "cpt" / f"corpus_{lang}.txt"
        with open(corpus_path, "w", encoding="utf-8") as f:
            for pid, texts in product_texts.items():
                for text in texts:
                    chunks = self._chunk_text(text, max_tokens=4096)
                    for chunk in chunks:
                        f.write(f"<|endoftext|>\n{chunk}\n")
```

#### 목표

| 제품 | 현재 CPT chunks | 목표 |
|------|-----------------|------|
| openframe_common_v2 | 1,506 (과대) | ~600 (common 전용만) |
| openframe_batch_v2 | 0 | ~200 |
| openframe_base_v2 | 0 | ~150 |
| openframe_osc_v2 | 0 | ~100 |
| openframe_tacf_v2 | 0 | ~80 |
| openframe_osi_v2 | 0 | ~50 |
| openframe_aim_v2 | 0 | ~80 |
| openframe_hidb_v2 | 0 | ~20 |
| openframe_gateway_v2 | 0 | ~50 |
| openframe_ndb_v2 | 0 | ~50 |

### 4.4 I-04 해결: HiDB 소량 데이터 증강

#### 전략: 패러프레이즈 + 난이도 변이

HiDB PDF가 1-2개로 원본 데이터 자체가 적으므로, 기존 35건을 기반으로 증강.

```
HiDB 35건 원본
    │
    ├─► 패러프레이즈 (질문 재구성)
    │     "hidbmgr OPEN コマンドの使い方は？"
    │     → "hidbmgr OPEN の実行手順を教えてください"
    │     → "hidbmgr で OPEN を実行する方法は？"
    │
    ├─► 난이도 변이 (초보/중급/고급)
    │     초보: "hidbmgrとは何ですか？"
    │     중급: "hidbmgr OPEN の各オプションの意味は？"
    │     고급: "hidbmgr で障害復旧する手順は？"
    │
    ├─► 관련 제품 교차 Q-A
    │     "HiDBとOSCの連携方法は？"
    │     "HiDBのVSAMデータセット管理は？"
    │
    └─► 증강된 HiDB 레코드 (~100건)
```

#### 목표
| 지표 | 현재 | 목표 |
|------|------|------|
| HiDB SFT 레코드 (JA) | 35 | ≥100 |
| HiDB SFT 레코드 (KO) | 0 | ≥67 (JA의 67%) |
| HiDB CPT chunks | 0 | ≥20 |

### 4.5 구현 우선순위

```
Iteration 2 실행 순서:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1: I-01 SFT 중복 제거 (P0, ~2시간)
  ├─ sft_generator.py: PDF 사전 중복 제거 로직 추가
  ├─ validate_training.py: cosine similarity 0.90 임계값
  └─ 재생성 + 검증 실행

Step 2: I-03 CPT 제품별 분할 (P0, ~1시간)
  ├─ cpt_generator.py: _resolve_product_id() 적용
  ├─ 제품별 corpus 분할 생성
  └─ 검증: 10개 OF 제품 모두 chunks > 0 확인

Step 3: I-02 한국어 데이터 생성 (P0, ~3시간)
  ├─ translators/ko_translator.py: 템플릿 번역기 구현
  ├─ sft_generator.py: 한국어 레코드 생성 파이프라인 추가
  ├─ system prompt 한국어 버전 추가
  └─ 검증: OF 10개 제품 × 2언어 확인

Step 4: I-04 HiDB 증강 (P1, ~1시간)
  ├─ augmentor.py: 패러프레이즈 + 난이도 변이 구현
  ├─ HiDB 35건 → 100건 증강
  └─ 검증: 증강 데이터 품질 체크

Step 5: 전체 재검증 + tar 재패키징 (~30분)
  ├─ validate-training 전체 실행
  ├─ 4가지 이슈 모두 해결 확인
  └─ kms_v10_training.tar.gz 재패키징
```

## 5. 초기 구현 순서 (Phase 1 — 완료)

### Phase 1: PDF 추출기 (Day 1-2) ✅
1. `scripts/manual_reextractor/` 패키지 생성
2. `pdf_extractor.py`: PyMuPDF 기반 텍스트/TOC/테이블 추출
3. 19개 제품 × 245 PDF 전체 추출 실행
4. `uploads/extracted_raw/` 에 JSON 저장

### Phase 2: 구조화 파서 (Day 2-3)
1. `error_extractor.py`: fix_error_descriptions.py 로직 통합
2. `command_extractor.py`: 명령어 패턴 추출
3. `config_extractor.py`: 설정 파라미터 추출
4. `api_extractor.py`: API 함수 추출
5. `glossary_extractor.py`: 용어/개념 추출
6. `summary_generator.py`: Markdown 요약본 생성
7. 기존 `uploads/summaries/` 갱신

### Phase 3: 학습 데이터 생성 (Day 3-4)
1. `sft_generator.py`: ChatML Q-A 쌍 생성 (3개 언어)
2. `cpt_generator.py`: Plain Text 청킹 (3개 언어)
3. `dpo_generator.py`: Preference 쌍 생성
4. `trilingual.py`: 템플릿 기반 다국어 변환
5. 제품별 분할 + Train/Eval 분할

### Phase 4: 품질 검증 (Day 4-5)
1. 5개 Validator 구현
2. 전체 학습 데이터 검증 실행
3. 품질 보고서 생성
4. v9 대비 비교 분석

## 5. 성공 기준

| 기준 | 목표값 | 측정 방법 |
|------|--------|----------|
| PDF 추출 완료율 | 245/245 (100%) | 추출 로그 확인 |
| 에러코드 채워짐 비율 | ≥99% | 빈 설명 필드 카운트 |
| SFT 레코드 수 | ≥5,000 (v9 대비 2× 이상) | train_all.jsonl 라인 수 |
| 3개 언어 커버리지 | JA/KO/EN 모두 존재 | language 필드 분포 |
| 품질 점수 | ≥95% | quality_report.json |
| DPO 쌍 수 | ≥2,000 | preferences.jsonl 라인 수 |
| CPT 코퍼스 크기 | ≥70MB | corpus_*.txt 합산 |
| ChatML 포맷 호환 | 100% | format_validator 통과율 |

## 6. 리스크 및 완화

| 리스크 | 영향 | 확률 | 완화 |
|--------|------|------|------|
| PDF 추출 시 테이블 레이아웃 깨짐 | 에러코드/명령어 파싱 실패 | 중 | Format A/B 자동 감지 + 수동 fallback |
| JEUS KR 매뉴얼 파싱 차이 | 한국어 데이터 품질 저하 | 저 | 한국어 전용 패턴 추가 |
| Tibero PDF 고유 포맷 | 에러코드 추출 실패 (현재 0건) | 고 | 별도 Tibero 파서 구현 |
| 3개 언어 번역 품질 | 학습 데이터 노이즈 | 중 | 템플릿 기반 (LLM 번역 아닌 룰 기반) |
| 메모리 초과 (대형 PDF) | 추출 프로세스 크래시 | 저 | 페이지 단위 처리, GC 강제 호출 |

## 7. 의존성

| 의존성 | 용도 | 버전 |
|--------|------|------|
| PyMuPDF (fitz) | PDF 텍스트/TOC 추출 | ≥1.23 |
| tiktoken | 토큰 수 계산 (Qwen2.5) | ≥0.5 |
| scikit-learn | 코사인 유사도 (중복 감지) | ≥1.3 |
| langdetect | 언어 감지 | ≥1.0 |

## 8. CLI 인터페이스

```bash
# 전체 파이프라인 실행
python -m scripts.manual_reextractor.main run-all

# Phase별 개별 실행
python -m scripts.manual_reextractor.main extract    # Phase 1: PDF 추출
python -m scripts.manual_reextractor.main parse      # Phase 2: 구조화 파싱
python -m scripts.manual_reextractor.main generate   # Phase 3: 학습 데이터 생성
python -m scripts.manual_reextractor.main validate   # Phase 4: 품질 검증

# 옵션
python -m scripts.manual_reextractor.main extract --product MVS_Openframe  # 특정 제품만
python -m scripts.manual_reextractor.main generate --format sft            # 특정 포맷만
python -m scripts.manual_reextractor.main generate --lang ja,ko,en         # 언어 지정
python -m scripts.manual_reextractor.main validate --report                # 품질 보고서만
python -m scripts.manual_reextractor.main run-all --dry-run                # 미리보기
```
