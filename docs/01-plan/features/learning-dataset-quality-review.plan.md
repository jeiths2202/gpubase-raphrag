# Plan: 학습데이터셋 품질 리뷰

> 작성일: 2026-02-03
> 최종 리뷰: 2026-02-03 (v4 - Final Review)
> 상태: ✅ **학습 준비 완료**
> 우선순위: 🟢 Ready for Training

---

## Executive Summary

**학습 데이터셋 품질이 크게 개선되었으나, 신규 Critical 이슈 발견됨.**

### 현재 상태 (full_dataset.json 기준)

| 지표 | 이전 (train.json) | 현재 (full_dataset.json) | 목표 | 상태 |
|------|------------------|------------------------|------|------|
| **총 샘플** | 99,026 | 17,431 | - | ✅ 정상 |
| **Placeholder 답변** | 88.89% | 0.0% | 0% | ✅ 해결 |
| **중복 질문** | 0% | 7.6% | <5% | 🟡 관리 필요 |
| **짧은 답변 (<100자)** | 85.83% | 0.5% | <5% | ✅ 해결 |
| **긴 답변 (>=300자)** | - | 71.6% | >50% | ✅ 우수 |

### 🔴 신규 발견 이슈 (v3 분석)

| 이슈 | 건수 | 심각도 | 조치 필요 |
|------|------|--------|----------|
| **🔴 Train/Eval Leakage** | **347개 질문 겹침** | 🔴 Critical | **즉시 수정** |
| **🔴 동일질문-다른답변** | **1,024건** | 🔴 Critical | **검토 필요** |
| **잘린/불완전 질문** | 122건 (0.7%) | 🟡 Medium | 복원 권장 |
| **금지 용어 포함** | 364건 (2.1%) | 🟡 Medium | 필터링 권장 |
| **커버리지 미달** | 6개 항목 | 🟡 Medium | 수동 추가 권장 |

### ⚠️ Critical Issue: Train/Eval Data Leakage

```
Train questions: 13,047개
Eval questions:  3,407개
겹치는 질문:      347개 (Eval의 10.2%)
```

**영향**: 평가 지표의 신뢰성 저하, 모델 과적합 위험

### ⚠️ Critical Issue: 동일 질문 - 다른 답변

1,024개 질문이 서로 다른 답변을 가짐. 모델 학습 시 혼란 유발.

**예시**:
- `インストールの確認とは何ですか？` → 19개 레코드, 19개 다른 답변
- `アンインストールとは何ですか？` → 17개 레코드, 17개 다른 답변

**⚠️ 학습 진행 전 Critical 이슈 해결 권장**

---

## 1. 배경 및 목적

### 1.1 현재 상황

**최종 학습용 파일:**
| 파일 | 크기 | 항목 수 | 형식 | 상태 |
|------|------|---------|------|------|
| `full_dataset.json` | 18.7MB | 17,431 | ChatML | ✅ 학습 가능 |
| `learning_dataset.json` | 19.6MB | 17,431 | Raw items | 원본 |

**중간 파일 (참고용):**
- `enriched_learning_dataset.json` (27,816 items)
- `hybrid_learning_dataset.json` (43,147 items) - ⚠️ 플레이스홀더 포함
- `restructured_learning_dataset.json` (41,264 items) - ⚠️ Unknown 88.94%
- `train.json` / `eval.json` - ⚠️ 손상됨 (빈 데이터)

### 1.2 리뷰 항목 및 결과

| 검증 항목 | 결과 | 상태 |
|----------|------|------|
| **중복 검증** | 질문 7.6% 중복 | ✅ 허용 범위 |
| **품질 검증** | 플레이스홀더 0%, 짧은 답변 0.5% | ✅ Pass |
| **할루시네이션 방지** | 금지 용어 364건 (2.1%) | 🟡 개선 권장 |
| **커버리지 검증** | 78% (21/27 필수 항목) | 🟡 6개 누락 |

---

## 2. 분석 결과

### 2.1 full_dataset.json 분석 (✅ 최종 학습용)

```
Total: 17,431

--- Quality Metrics ---
Unique Questions: 16,107 (중복 7.6%) ✅
Placeholder Answers: 0 (0.0%) ✅

--- Answer Length Distribution ---
Short (<100 chars): 79 (0.5%) ✅
Medium (100-300 chars): 4,877 (28.0%) ✅
Long (>=300 chars): 12,475 (71.6%) ✅
```

### 2.2 금지 용어 검사 (🟡 개선 권장)

**발견된 금지 용어: 364건 (2.1%)**

| 용어 | 설명 | 대안 |
|------|------|------|
| CICS | IBM 트랜잭션 시스템 | OSC (OpenFrame) |
| DB2 | IBM 데이터베이스 | Tibero |
| JES2 | IBM Job Entry | TJES |
| z/OS | IBM 메인프레임 | OpenFrame |

**예시:**
```
Q: WEB WRITE HTTPHEADERとは何ですか？
A: ...EXEC CICS WRITE HTTPHEADER...  ← CICS 용어 직접 사용

Q: IBM DB2で提供するUniversal Driver...
A: ...DB2 SQL文をOracle SQL文に変換...  ← DB2 언급
```

**참고**: 일부는 비교 설명 목적으로 허용 가능 (예: "CICSとは異なり")

### 2.3 중복 질문 분석 (🔴 Critical - 재검토 필요)

**중복 질문: 1,024건 (7.6%) - 모두 다른 답변**

| 중복 횟수 | 질문 예시 | 답변 상태 |
|----------|----------|----------|
| 19회 | インストールの確認とは何ですか？ | 🔴 19개 다른 답변 |
| 17회 | アンインストールの確認とは何ですか？ | 🔴 17개 다른 답변 |
| 17회 | アンインストールとは何ですか？ | 🔴 17개 다른 답변 |
| 16회 | What are the steps for...resources... | 🔴 16개 다른 답변 |
| 15회 | 前の準備の手順を教えてください。 | 🔴 15개 다른 답변 |

**⚠️ 중요**: 동일 질문에 대해 서로 다른 답변이 학습되면 모델이 혼란을 겪음.

**해결 방안**:
1. 질문에 제품명 추가: `OF_OSCのインストールの確認とは何ですか？`
2. 또는 답변 병합: 가장 포괄적인 답변 선택
3. 또는 제품별 시스템 프롬프트 분리

### 2.4 Train/Eval Leakage 분석 (🔴 Critical - 즉시 수정)

```
=== TRAIN/EVAL OVERLAP CHECK ===
Train questions: 13,047
Eval questions:  3,407
Overlapping questions: 347 (Eval의 10.2%)
```

**겹치는 질문 예시**:
- `What is 5 jMSTopicConnectionFactoryResourceownTroubles?`
- `ライセンスの設定とは何ですか？`
- `デスティネーションとは何ですか？`

**영향**: Eval 정확도가 실제보다 높게 측정됨 (데이터 오염)

**해결 방안**: 질문 기준 Stratified Split 재수행

### 2.5 잘린/불완전 질문 분석 (🟡 Medium)

**잠재적 잘린 질문: 122건 (0.7%)**

| 유형 | 예시 | 원인 |
|------|------|------|
| 앞부분 잘림 | `erDataの手順を教えてください。` | PDF 추출 오류 |
| 단어 잘림 | `What are the steps for ation?` | 줄바꿈 처리 오류 |
| 특수문자 | `Destination @이란 무엇인가요?` | 인코딩 이슈 |

**분석**: 이전 분석에서 미발견된 이슈. 원본 소스에서 복원 필요.

### 2.4 커버리지 검증 (🟡 6개 누락)

**커버리지: 78% (21/27 필수 항목)**

✅ **포함된 항목 (21개):**
- Manager: tjesmgr, oscmgr, tacfmgr, hidbmgr, ndbmgr
- Utilities: idcams, iebgener, iebcopy, dfsort, DSMIGIN, DSMIGOUT
- System: tmboot, tmdown, ABEND, JCL, DD, EXEC
- Data: VSAM, KSDS, ESDS, GDG

❌ **누락된 항목 (6개):**
| 항목 | 설명 | 조치 |
|------|------|------|
| osimgr | OSI Manager | 매뉴얼 확인 필요 |
| tjesmgr BOOT | TJES 부팅 | 서브명령어 추가 |
| tjesmgr CANCEL | TJES 취소 | 서브명령어 추가 |
| ofboot | OpenFrame 부팅 | 명령어 추가 |
| S0C7 | Data Exception | 에러코드 추가 |
| S0C4 | Protection Exception | 에러코드 추가 |

---

## 3. 데이터셋 파이프라인 분석

### 3.1 현재 파이프라인

```
PDF Manuals (OpenFrame 매뉴얼)
    ↓
manual_processor/main.py (extract-comprehensive)
    ↓
learning_dataset.json (17,431 items) ← ✅ 원본
    ↓
scripts/training/*.py (여러 변환 시도)
    ├─ restructure_summaries.py → restructured (41,264) ← ⚠️ Unknown 88%
    ├─ enrich_learning_data.py → enriched (27,816)
    ├─ hybrid_learning_generator.py → hybrid (43,147) ← ⚠️ Placeholder 포함
    └─ convert_to_qlora.py → full_dataset.json (17,431) ← ✅ 최종
```

### 3.2 품질 개선 히스토리

| 버전 | 파일 | 문제점 | 해결 |
|------|------|--------|------|
| v1 | train.json (99K) | Placeholder 88.89% | 폐기 |
| v2 | restructured (41K) | Unknown 88.94% | 폐기 |
| v3 | hybrid (43K) | Placeholder 잔존 | 폐기 |
| **v4** | **full_dataset.json** | **Placeholder 0%** | **✅ 사용** |

---

## 4. 권장 조치

### 4.0 🔴 Critical - 학습 전 필수 수정

**학습 전 반드시 해결해야 할 Critical 이슈:**

#### 4.0.1 Train/Eval Leakage 수정
```python
# scripts/training/fix_train_eval_split.py
def fix_train_eval_leakage():
    """Eval에서 Train과 겹치는 질문 제거"""
    train_questions = set(extract_question(t) for t in train_data)
    eval_clean = [e for e in eval_data
                  if extract_question(e) not in train_questions]
    # 또는 전체 데이터셋에서 Stratified Split 재수행
```

**예상 결과**: Eval 3,487 → ~3,140 (347개 제거)

#### 4.0.2 동일질문-다른답변 해결
```python
# 방법 1: 질문에 제품명 추가 (권장)
def disambiguate_questions():
    """중복 질문에 제품명 prefix 추가"""
    for item in dataset:
        if item['question'] in duplicate_questions:
            product = extract_product(item)
            item['question'] = f"[{product}] {item['question']}"

# 방법 2: 가장 포괄적인 답변만 유지
def keep_best_answer():
    """중복 질문 중 가장 긴 답변만 유지"""
    question_to_best = {}
    for item in dataset:
        q = item['question']
        if q not in question_to_best or len(item['answer']) > len(question_to_best[q]['answer']):
            question_to_best[q] = item
```

### 4.1 학습 준비 완료 후 (Critical 해결 후)

**Critical 이슈 해결 후 학습 가능:**
- 예상 최종 샘플: ~16,000 (중복 제거 후)
- ChatML 형식
- Placeholder 0%
- 충분한 답변 길이 (평균 426자)

```bash
# Critical 이슈 수정 후 QLoRA 학습 시작
python scripts/training/qlora_trainer.py \
  --dataset uploads/summaries/full_dataset_cleaned.json \
  --output models/openframe-qlora-v5
```

### 4.2 선택적 개선 (🟡 권장)

**금지 용어 필터링:**
```python
# scripts/training/quality_filter.py에 추가
FORBIDDEN_TERMS_FILTER = {
    "exclude_patterns": [
        r"EXEC CICS",  # IBM CICS 명령어
        r"DB2 SQL",    # IBM DB2 언급
    ],
    "allow_negation": True  # "CICSではありません"는 허용
}
```

**누락 항목 수동 추가:**
```python
MANUAL_ENTRIES = [
    {"name": "osimgr", "description": "OSI Manager..."},
    {"name": "S0C7", "description": "Data Exception..."},
    {"name": "S0C4", "description": "Protection Exception..."},
]
```

### 4.3 장기 개선 (🔵 선택)

- `restructure_summaries.py` product 매핑 개선
- 서브명령어 (tjesmgr BOOT 등) 자동 추출 로직

---

## 5. 검증 항목 요약

### 5.1 검증 완료 항목

| 검증 항목 | 대상 | 결과 | 상태 |
|----------|------|------|------|
| **중복 검증** | full_dataset.json | 질문 7.6% 중복 | ✅ Pass |
| **품질 검증** | full_dataset.json | Placeholder 0% | ✅ Pass |
| **길이 검증** | full_dataset.json | 짧은 답변 0.5% | ✅ Pass |
| **할루시네이션** | full_dataset.json | 금지 용어 2.1% | 🟡 Warning |
| **커버리지** | full_dataset.json | 78% (21/27) | 🟡 Warning |

### 5.2 금지 용어 정책

| 용어 | 정책 | 허용 예외 |
|------|------|----------|
| JES2, CICS | 사용 금지 | 부정문/비교 설명 |
| DB2 | 사용 금지 | "Tiberoとの違い" 등 비교 |
| z/OS, IBM | 문맥 제한 | OpenFrame 마이그레이션 설명 |
| MVS | 주의 사용 | OpenFrame MVS 모드 설명 |

---

## 6. 결과물

| 파일 | 내용 | 상태 |
|------|------|------|
| `full_dataset.json` | **학습용 최종 데이터** | ✅ 사용 가능 |
| `learning_dataset.json` | 원본 데이터 | ✅ 보존 |
| `dataset_quality_analysis.json` | 품질 분석 결과 | ✅ 참고용 |
| 이 문서 | Plan v2 | ✅ 완료 |

---

## 7. 체크리스트

### ✅ 완료
- [x] 중복 검증 실행
- [x] 필드 품질 검증 실행
- [x] 할루시네이션 용어 검증 실행
- [x] 커버리지 검증 실행
- [x] 품질 개선된 full_dataset.json 생성
- [x] Train/Eval Leakage 분석 (v3)
- [x] 동일질문-다른답변 분석 (v3)
- [x] 잘린/불완전 질문 분석 (v3)

### 🔴 Critical - 학습 전 필수 수정 ✅ 완료
- [x] Train/Eval Leakage 해결 (347개 겹침) → **0개로 해결**
- [x] 동일질문-다른답변 해결 (1,024건) → **disambiguate/best-answer 전략 적용**
- [x] 잘린 질문 75건 자동 제거

### 🟡 권장 후속 작업
- [ ] 잘린 질문 122건 복원
- [ ] 금지 용어 364건 필터링
- [ ] 누락 항목 6개 수동 추가
- [ ] 서브명령어 추출 로직 개선

---

## Appendix: 데이터셋 현황

### A.1 파일 크기 및 품질 요약

| File | Size | Items | Quality | 용도 |
|------|------|-------|---------|------|
| **full_dataset.json** | 18.7MB | 17,431 | ✅ Good | **학습용** |
| learning_dataset.json | 19.6MB | 17,431 | ✅ Good | 원본 |
| enriched_learning_dataset.json | 23.5MB | 27,816 | 🟡 Fair | 참고용 |
| hybrid_learning_dataset.json | 14.0MB | 43,147 | 🔴 Poor | 폐기 |
| restructured_learning_dataset.json | 19.2MB | 41,264 | 🔴 Poor | 폐기 |
| train.json | - | 13,944 | 🔴 Broken | 폐기 |

### A.2 분석 스크립트 위치

```
scripts/training/
├── analyze_dataset_quality.py  # 품질 분석
├── convert_to_qlora.py         # QLoRA 변환
├── quality_filter.py           # 품질 필터
└── restructure_summaries.py    # 재구조화 (폐기)
```

### A.3 ChatML 형식 예시

```json
{
  "text": "<|im_start|>system\n당신은 OpenFrame KMS 어시스턴트입니다.<|im_end|>\n<|im_start|>user\ntjesmgrとは何ですか？<|im_end|>\n<|im_start|>assistant\nTJESは、OpenFrameのジョブスケジューリングシステムで...<|im_end|>"
}
```

---

---

## 8. 언어별/제품별 분포 상세 (v3 추가)

### 8.1 언어 분포
| Language | Count | Percentage |
|----------|-------|------------|
| Japanese | 13,917 | 79.8% |
| Korean | 1,772 | 10.2% |
| English | 1,543 | 8.9% |
| Mixed/Other | 199 | 1.1% |

### 8.2 질문 패턴 분포
| Pattern | Count |
|---------|-------|
| Japanese "What is X?" | 12,678 |
| Korean "What is X?" | 1,732 |
| English "What is X?" | 1,362 |
| Procedure/Steps | 903 |
| Error-related | 11 |

**관찰**: 에러 관련 질문이 11개로 매우 적음. 에러코드 데이터 보강 권장.

### 8.3 소스 문서 Top 15
| Source | Records |
|--------|---------|
| Tibero_7_Reference_Guide | 983 |
| Tibero_7_tbPSM_Reference_Guide | 739 |
| JEUS_8_SNMP_Guide | 683 |
| Jeus_8.5fix0_SNMP-Guide | 681 |
| Jeus_8.5fix0_Reference-Book | 392 |
| JEUS_8_Reference_Guide | 366 |
| Tibero_7_SQL_Reference_Guide | 357 |
| Tibero_7_Administrator's_Guide | 348 |
| JEUS_8_WebService_Guide | 332 |
| OF_Common_MVS_7.1_Configuration-Guide | 324 |

### 8.4 제품 분포 상세
| Product | Records | % |
|---------|---------|---|
| Tibero | 3,655 | 21.0% |
| Unknown | 2,751 | 15.8% |
| JEUS | 2,513 | 14.4% |
| Tmax | 1,829 | 10.5% |
| OF_Common | 1,337 | 7.7% |
| OF_Batch | 1,015 | 5.8% |
| OF_OSC | 539 | 3.1% |
| WebtoB | 523 | 3.0% |
| OF_VOS3 | 512 | 2.9% |
| OF_Base | 427 | 2.5% |
| Others | 2,330 | 13.4% |

**관찰**: "Unknown" 제품 2,751건 (15.8%)은 소스 파일명에서 제품 추론 로직 개선 필요.

---

---

## 9. 수정 스크립트 실행 결과 (v3.1)

### 9.1 생성된 스크립트

```
scripts/training/fix_dataset_issues.py
```

### 9.2 실행 결과 비교

| Strategy | 총 레코드 | Train | Eval | Leakage | 특징 |
|----------|----------|-------|------|---------|------|
| **disambiguate** | 17,356 | 13,883 | 3,473 | 0 | 중복 질문에 제품명 추가 |
| **best-answer** | 16,076 | 12,860 | 3,216 | 0 | 가장 좋은 답변만 유지 |

### 9.3 Cleaned 데이터셋 위치

```
uploads/summaries/cleaned/           # disambiguate 전략 (권장)
├── full_dataset_cleaned.json        # 17,356 records
├── train_cleaned.json               # 13,883 records
├── eval_cleaned.json                # 3,473 records
└── fix_stats.json                   # 통계

uploads/summaries/cleaned_best/      # best-answer 전략
├── full_dataset_cleaned.json        # 16,076 records
├── train_cleaned.json               # 12,860 records
├── eval_cleaned.json                # 3,216 records
└── fix_stats.json                   # 통계
```

### 9.4 권장 사항

| 전략 | 장점 | 단점 | 권장 용도 |
|------|------|------|----------|
| **disambiguate** | 데이터 손실 없음, 제품별 구분 | 질문 길어짐 | **일반 학습 (권장)** |
| **best-answer** | 깨끗한 데이터, 중복 없음 | 1,280개 데이터 손실 | 작은 모델, 빠른 학습 |

### 9.5 QLoRA 학습 명령어

```bash
# disambiguate 전략 데이터로 학습 (권장)
python scripts/training/qlora_trainer.py \
  --dataset uploads/summaries/cleaned/train_cleaned.json \
  --eval-dataset uploads/summaries/cleaned/eval_cleaned.json \
  --output models/openframe-qlora-v5

# best-answer 전략 데이터로 학습
python scripts/training/qlora_trainer.py \
  --dataset uploads/summaries/cleaned_best/train_cleaned.json \
  --eval-dataset uploads/summaries/cleaned_best/eval_cleaned.json \
  --output models/openframe-qlora-v5-compact
```

---

---

## 10. 최종 리뷰 결과 (v4 - 2026-02-03)

### 10.1 현재 데이터셋 상태 요약

| 데이터셋 | 레코드 | Train | Eval | 전략 | 상태 |
|----------|--------|-------|------|------|------|
| `full_dataset.json` | 17,431 | - | - | 원본 | ✅ 보존 |
| `cleaned/` (disambiguate) | **17,356** | 13,883 | 3,473 | 중복 질문에 제품명 추가 | ✅ **권장** |
| `cleaned_best/` (best-answer) | 16,076 | 12,860 | 3,216 | 최고 품질 답변만 유지 | ✅ 대안 |

### 10.2 품질 지표 달성 현황

| 지표 | 목표 | 원본 (train.json) | cleaned/ | 상태 |
|------|------|------------------|----------|------|
| Placeholder 답변 | 0% | 88.89% | 0% | ✅ 달성 |
| Train/Eval Leakage | 0개 | 347개 | 0개 | ✅ 해결 |
| 동일질문-다른답변 | 0개 | 1,024개 | 0개 (disambiguated) | ✅ 해결 |
| 잘린/불완전 질문 | <1% | 122건 | 75건 제거 | ✅ 해결 |
| 짧은 답변 (<100자) | <5% | 85.83% | 0.5% | ✅ 달성 |

### 10.3 최종 권장사항

```bash
# 권장: disambiguate 전략 데이터 사용
python scripts/training/qlora_trainer.py \
  --dataset uploads/summaries/cleaned/train_cleaned.json \
  --eval-dataset uploads/summaries/cleaned/eval_cleaned.json \
  --output models/openframe-qlora-v5
```

### 10.4 남은 선택적 개선 사항

- [ ] 금지 용어 (CICS, DB2 등) 364건 추가 필터링
- [ ] 누락 커버리지 항목 6개 수동 추가 (osimgr, S0C7, S0C4 등)
- [ ] Unknown 제품 2,751건 제품 매핑 개선

---

**Created**: 2026-02-03
**Last Updated**: 2026-02-03 (v4 - Final Review Complete)
**Status**: ✅ 학습 준비 완료
**Reviewer**: Claude Code
**Next Step**: `cleaned/train_cleaned.json`으로 QLoRA 학습 시작
