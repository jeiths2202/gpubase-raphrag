# Plan: OFStudio Data Quality Improvement

> OFStudio 제품 학습 데이터셋 품질 개선

## 1. 개요

### 1.1 배경

현재 OFStudio 학습 데이터셋의 품질 분석 결과:

| 품질 유형 | 항목 수 | 비율 |
|----------|--------|------|
| TOC 항목 (목차) | 76 | 34.7% |
| 불완전한 이름 | 31 | 14.2% |
| 짧은 설명 (<30자) | 25 | 11.4% |
| **양호한 품질** | **87** | **39.7%** |

**문제점**:
- 전체 219개 중 60.3%가 품질 이슈 보유
- TOC 페이지에서 목차 항목이 그대로 추출됨
- 불완전한 문장이 name으로 사용됨 (예: "の確認", "とアンインストール")
- Installation Guide 특성상 절차 설명이 아닌 목차/참조가 많음

### 1.2 목표

- OFStudio 학습 데이터 품질률 **39.7% → 85% 이상**으로 향상
- TOC/페이지 참조 항목 자동 필터링
- 불완전 문장 감지 및 제외
- Installation/User Guide 전략 개선

### 1.3 범위

| 포함 | 제외 |
|------|------|
| OFStudio 2개 PDF 재처리 | 다른 제품 학습데이터 |
| S14_INSTALL_GUIDE 전략 개선 | 새로운 전략 추가 |
| 품질 필터 강화 | PDF 원본 수정 |

---

## 2. 현재 상태 분석

### 2.1 소스 파일

| PDF | 전략 | 항목 수 | 품질 이슈 |
|-----|------|--------|----------|
| `OpenFrame_Studio_7_Installation_Guide_v2.1.1_jp.pdf` | S14_INSTALL_GUIDE | 124 | TOC 다수 |
| `OpenFrame_Studio_7_User_Guide_v2.1.1_jp.pdf` | S13_USER_GUIDE | 95 | 불완전 문장 |

### 2.2 품질 이슈 상세

#### Issue 1: TOC 항목 추출 (34.7%)

```json
{
  "name": "Installing OpenFrameStudio7",
  "description": "[図 3.7] OFStudioのインストール – Install Complete .............................................................. 19"
}
```

**원인**: TOC 페이지에서 섹션 헤더 패턴이 매칭됨

#### Issue 2: 불완전한 이름 (14.2%)

```json
{
  "name": "の確認",
  "description": "第3章 クライアントのインストールとアンインストール"
}
```

**원인**: 일본어 조사로 시작하는 문장 fragment가 name으로 추출

#### Issue 3: 짧은 설명 (11.4%)

```json
{
  "name": "ガイド",
  "description": "OpenFrame Studio 7"
}
```

**원인**: 최소 설명 길이 검증이 10자로 너무 낮음

---

## 3. 개선 방안

### 3.1 TOC 페이지 감지 강화

```python
def _is_toc_page(self, text: str) -> bool:
    """TOC 페이지 감지 (강화)"""
    indicators = [
        len(re.findall(r'\.\.\.\s*\d+', text)) > 3,  # 점선+페이지 3개 이상
        len(re.findall(r'第\d+章', text)) > 2,       # 장 번호 3개 이상
        len(re.findall(r'\[図\s*\d+\.\d+\]', text)) > 2,  # 그림 참조 3개 이상
        '目次' in text[:100],                        # 페이지 상단에 "목차"
    ]
    return sum(indicators) >= 2
```

### 3.2 불완전 이름 필터 추가

```python
def _is_valid_japanese_name(self, name: str) -> bool:
    """일본어 이름 유효성 검증 (강화)"""
    # 조사로 시작하면 무효
    if re.match(r'^[のをはがにでとからまでよりへ]', name):
        return False
    # 조사로 끝나면 무효 (문장 중간 절단)
    if re.match(r'.*[のをはがにでとからまでよりへ]$', name) and len(name) < 10:
        return False
    # 최소 길이 4자
    if len(name) < 4:
        return False
    return True
```

### 3.3 최소 설명 길이 증가

| 항목 | 현재 | 개선 |
|------|------|------|
| 최소 설명 길이 | 10자 | **30자** |
| concept 타입 | 10자 | **50자** |
| procedure 타입 | 10자 | **30자** |

### 3.4 Installation Guide 전략 개선

```python
S14_INSTALL_GUIDE = {
    "extract_patterns": {
        "procedure": [
            r"(?:手順|Step|ステップ)\s*(\d+)[:：]?\s*(.+)",
            r"(?:インストール|Installation)[:：]?\s*(.+)",
        ],
    },
    "skip_patterns": [
        r"\[図\s*\d+\.\d+\]",      # 그림 참조
        r"\.{3,}\s*\d+",           # 점선+페이지
        r"第\d+章\s+.+\.{2,}",     # 장 목차
    ],
    "min_description_length": 30,
}
```

---

## 4. 구현 계획

### 4.1 Phase 1: 필터 강화 (30분)

- [ ] `_is_toc_page()` 메서드 추가
- [ ] `_is_valid_japanese_name()` 강화
- [ ] 최소 설명 길이 파라미터화

### 4.2 Phase 2: 전략 패턴 업데이트 (30분)

- [ ] S14_INSTALL_GUIDE skip_patterns 추가
- [ ] S13_USER_GUIDE skip_patterns 추가
- [ ] 전략별 min_description_length 설정

### 4.3 Phase 3: 재처리 및 검증 (30분)

- [ ] OFStudio PDF만 재처리
- [ ] 품질 비교 (Before/After)
- [ ] learning_dataset.json 업데이트

---

## 5. 예상 결과

### 5.1 품질 개선 예상

| 지표 | Before | After |
|------|--------|-------|
| 총 항목 | 219 | ~100 |
| 양호 품질 비율 | 39.7% | **85%+** |
| TOC 항목 | 76 | 0 |
| 불완전 이름 | 31 | 0 |

### 5.2 항목 수 감소 이유

- 품질 필터 강화로 저품질 항목 제거
- TOC 페이지 전체 스킵
- 불완전 문장 필터링

**참고**: 항목 수 감소는 의도된 결과이며, 남은 항목의 품질이 더 중요함

---

## 6. 성공 기준

| 항목 | 목표 | 측정 방법 |
|------|------|----------|
| 양호 품질 비율 | ≥ 85% | 품질 분석 스크립트 |
| TOC 항목 | 0개 | 패턴 매칭 검사 |
| 불완전 이름 | 0개 | 조사 패턴 검사 |
| 최소 설명 길이 | ≥ 30자 | 길이 검증 |

---

## 7. 영향 범위

### 7.1 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `scripts/manual_processor/parsers/strategy_aware_parser.py` | 필터 메서드 추가, 전략 패턴 업데이트 |

### 7.2 영향받는 제품

- **직접 영향**: OFStudio (재처리)
- **간접 영향**: 동일 전략(S13, S14) 사용 제품 (품질 향상 기대)

---

**작성일**: 2026-02-03
**작성자**: Claude Code
**상태**: Plan Complete
**버전**: v1.0
