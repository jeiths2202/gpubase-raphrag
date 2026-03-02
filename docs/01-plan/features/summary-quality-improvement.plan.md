# Summary Quality Improvement Plan

> **Feature**: summary-quality-improvement
> **Created**: 2026-02-03
> **Author**: Claude Opus 4.5
> **Status**: Plan Phase
> **Trigger**: osctdlrm Hallucination 발생 (WebUI 테스트 중)

## 1. 배경 및 목적

### 1.1 현재 상황

**요약본 데이터 현황:**
| 항목 | 값 |
|------|-----|
| 총 항목 수 | 17,431개 |
| 제품 수 | 25개 |
| 타입 | command(94), concept(15,834), procedure(919), api(518), config(58), error(4), term(4) |
| 저장 위치 | `uploads/summaries/` |

**디렉토리 구조:**
```
uploads/summaries/
├── commands/          # 명령어 요약본
├── glossary/          # 용어 사전
├── error-codes/       # 에러 코드 사전
├── apis/              # API 함수 사전
├── configs/           # 설정 파라미터
├── concepts/          # 개념 설명
├── terms/             # 기술 용어
├── learning_dataset.json  # 학습 데이터셋
└── index.json         # 통합 인덱스
```

### 1.2 발견된 문제점

#### 1.2.1 Hallucination 케이스 분석

| 질문 | 올바른 답변 | LLM 응답 (Hallucination) |
|------|-------------|--------------------------|
| "osctdlrmについて説明してください" | `osctdlrm [options] <region>` (TDL 공유 메모리 삭제 도구) | `oscadmin osctdlrm` (리전 재시작 도구) |

**원인 분석:**
1. **불완전한 설명 필드**: O.md에서 "8.30. osctdlrm"만 기록 (장 번호만)
2. **정보 혼합**: 별개 명령어(oscadmin, osctdlrm) 정보 섞임
3. **타입 분류 오류**: osctdlrm이 command가 아닌 concept으로 분류

#### 1.2.2 데이터 품질 문제 유형

| 문제 유형 | 영향 범위 | 심각도 |
|-----------|----------|--------|
| **불완전한 설명** | commands/*.md의 ~30% | Critical |
| **중복 항목** | oscdown(3회), oscboot(3회) 등 | High |
| **타입 분류 오류** | 명령어가 concept으로 분류 | High |
| **언어 혼합** | 일부 설명이 깨진 문자로 표시 | Medium |

### 1.3 목표

1. **P0**: 불완전한 설명 필드 보완 (장 번호만 있는 항목)
2. **P0**: 중복 항목 통합 및 정리
3. **P1**: 타입 분류 정확도 향상 (command vs concept)
4. **P1**: 명령어 구문(syntax) 정보 완성도 향상
5. **P2**: learning_dataset.json 재생성

## 2. 요구사항

### 2.1 기능 요구사항

| ID | 요구사항 | 우선순위 | 상세 |
|----|----------|----------|------|
| FR-01 | 불완전한 설명 검출 | P0 | 장 번호만 있는 항목 식별 |
| FR-02 | PDF 원본에서 설명 재추출 | P0 | 불완전 항목에 대해 상세 설명 보완 |
| FR-03 | 중복 항목 탐지 및 통합 | P0 | 같은 명령어의 중복 항목 병합 |
| FR-04 | 타입 재분류 | P1 | command 패턴 기반 자동 재분류 |
| FR-05 | 구문(syntax) 완성도 검증 | P1 | syntax 필드 누락 항목 보완 |
| FR-06 | learning_dataset.json 재생성 | P2 | 개선된 요약본으로 재생성 |

### 2.2 비기능 요구사항

| ID | 요구사항 | 기준 |
|----|----------|------|
| NFR-01 | 처리 시간 | 전체 PDF 245개 재분석 < 2시간 |
| NFR-02 | 설명 완성도 | 불완전 설명 0% |
| NFR-03 | 중복 제거율 | 중복 0개 |

## 3. 솔루션 설계

### 3.1 품질 검사 도구

```python
# scripts/manual_processor/quality_checker.py

def check_incomplete_descriptions():
    """장 번호만 있는 불완전한 설명 검출"""
    incomplete = []
    pattern = r'^[\d.]+\s*\w+$'  # "8.30. osctdlrm" 패턴

    for item in items:
        if re.match(pattern, item['description'].strip()):
            incomplete.append(item)

    return incomplete

def check_duplicates():
    """중복 항목 검출"""
    name_counts = {}
    for item in items:
        name = item.get('name', '')
        if name:
            name_counts[name] = name_counts.get(name, 0) + 1

    return {k: v for k, v in name_counts.items() if v > 1}

def check_type_classification():
    """타입 분류 검증"""
    misclassified = []
    command_patterns = [
        r'^[\w]+mgr$',      # tjesmgr, oscmgr 등
        r'^[\w]+admin$',    # oscadmin 등
        r'^[\w]+init$',     # osctdlinit 등
        r'^[\w]+rm$',       # osctdlrm 등
        r'^\$',             # $ 시작 명령어
    ]

    for item in items:
        if item['type'] == 'concept':
            for pattern in command_patterns:
                if re.match(pattern, item['name'], re.IGNORECASE):
                    misclassified.append(item)
                    break

    return misclassified
```

### 3.2 개선 파이프라인

```
Phase 1: 품질 검사
├── check_incomplete_descriptions()
├── check_duplicates()
└── check_type_classification()
    ↓
Phase 2: 원본 PDF 재분석
├── identify_affected_pdfs()
├── re-extract_descriptions()
└── merge_duplicates()
    ↓
Phase 3: 요약본 재생성
├── update_commands/*.md
├── update_index.json
└── regenerate_learning_dataset.json
    ↓
Phase 4: 검증
├── quality_report()
└── e2e_hallucination_test()
```

### 3.3 영향받는 파일

| 카테고리 | 파일 | 액션 |
|----------|------|------|
| 요약본 | `commands/O.md` | 불완전 설명 보완 |
| 요약본 | `commands/OpenFrame_OSC_MVS.md` | 중복 제거 |
| 요약본 | `commands/OpenFrame_Common_MVS.md` | 중복 제거 |
| 인덱스 | `index.json` | 재생성 |
| 학습 데이터 | `learning_dataset.json` | 재생성 |

## 4. 구현 계획

### 4.1 Phase 1: 품질 검사 도구 (Day 1)

| 단계 | 작업 | 산출물 |
|------|------|--------|
| 1.1 | 품질 검사 스크립트 작성 | `quality_checker.py` |
| 1.2 | 전체 요약본 스캔 | `quality_report.json` |
| 1.3 | 문제 항목 리스트 생성 | 불완전/중복/분류오류 목록 |

### 4.2 Phase 2: 원본 재분석 (Day 1-2)

| 단계 | 작업 | 산출물 |
|------|------|--------|
| 2.1 | 문제 항목의 원본 PDF 식별 | PDF 목록 |
| 2.2 | 해당 페이지에서 상세 설명 재추출 | 보완된 설명 |
| 2.3 | 중복 항목 병합 규칙 정의 | 병합 규칙 |
| 2.4 | 수동 검토 필요 항목 플래그 | 검토 대상 |

### 4.3 Phase 3: 요약본 재생성 (Day 2)

| 단계 | 작업 | 산출물 |
|------|------|--------|
| 3.1 | commands/*.md 업데이트 | 개선된 요약본 |
| 3.2 | index.json 재생성 | 통합 인덱스 |
| 3.3 | learning_dataset.json 재생성 | 학습 데이터셋 |

### 4.4 Phase 4: 검증 (Day 3)

| 단계 | 작업 | 산출물 |
|------|------|--------|
| 4.1 | 품질 리포트 생성 | 개선 전/후 비교 |
| 4.2 | osctdlrm Hallucination 재테스트 | 테스트 결과 |
| 4.3 | E2E Hallucination 테스트 | 전체 테스트 결과 |

## 5. 품질 검사 기준

### 5.1 설명 완성도 기준

| 등급 | 기준 | 예시 |
|------|------|------|
| **A (완전)** | 기능 + 구문 + 옵션 + 예제 | "osctdlrmは、TDL共有メモリを完全に削除するためのツールです..." |
| **B (양호)** | 기능 + 구문 | "TDL共有メモリを削除します。構文: osctdlrm [options] <region>" |
| **C (기본)** | 기능만 | "TDL共有メモリを削除するツール" |
| **F (불완전)** | 장 번호만 | "8.30. osctdlrm" |

**목표: F 등급 0%, C 이상 100%**

### 5.2 중복 제거 기준

| 상황 | 처리 방법 |
|------|----------|
| 같은 명령어, 다른 설명 | 가장 완전한 설명 선택 |
| 같은 명령어, 다른 소스 | 소스 병합, 중복 설명 제거 |
| 유사 명령어 (오타) | 수동 검토 후 결정 |

## 6. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| PDF 파싱 오류 | 설명 추출 실패 | 수동 보완 |
| 대량 변경으로 인한 새로운 오류 | 품질 저하 | 단계별 검증 |
| 학습 데이터 호환성 | 기존 모델 영향 | 버전 관리 |

## 7. 성공 기준

| 기준 | 목표 | 현재 |
|------|------|------|
| 불완전 설명 비율 | 0% | ~30% (추정) |
| 중복 항목 수 | 0개 | 7개+ (OSC 관련) |
| 타입 분류 정확도 | 100% | ~95% (추정) |
| osctdlrm Hallucination | 해결 | 발생 |
| E2E Hallucination 테스트 | Pass rate 95%+ | TBD |

## 8. 다음 단계

1. `/pdca design summary-quality-improvement` - 상세 설계
2. Phase 1: 품질 검사 도구 구현
3. Phase 2-3: 요약본 재생성
4. Phase 4: 검증 및 리포트

---

**참조 파일**:
- `uploads/summaries/learning_dataset.json` - 학습 데이터셋
- `uploads/summaries/commands/O.md` - 문제 발견 파일
- `uploads/summaries/index.json` - 통합 인덱스
- `scripts/manual_processor/main.py` - 기존 처리 스크립트

**관련 이슈**:
- Hallucination: osctdlrm → "oscadmin osctdlrm" (잘못된 응답)
- 원인: 불완전한 설명 데이터 + 정보 혼합
