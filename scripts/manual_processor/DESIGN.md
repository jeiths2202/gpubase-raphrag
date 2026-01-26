# OpenFrame 매뉴얼 요약본 시스템 설계

## 1. 개요

사용자의 비구조화된 질문 ("TJES가 뭐야", "-5212 에러 알려줘")에서 정확한 정보를 찾기 위한 **Two-Stage Retrieval** 시스템.

```
사용자 질문: "-5212 에러 알려줘"
     ↓
[1단계] 요약본 검색 (파일 시스템 기반)
     → error-codes/DSALC-5000.md에서 -5212 찾기
     → 컨텍스트: "DSALC = 데이터셋 할당 모듈, OpenFrame Base"
     ↓
[2단계] 벡터/그래프 DB 검색 (풍부해진 쿼리)
     → "OpenFrame Base DSALC 데이터셋 할당 -5212 에러"
     ↓
정확한 결과 반환
```

## 2. 요약본 디렉토리 구조

```
uploads/summaries/
├── index.md                      # 전체 인덱스 (메타데이터)
├── glossary/                     # 용어 사전
│   ├── index.md                  # 용어 전체 목록
│   ├── A.md                      # A로 시작하는 용어
│   ├── T.md                      # TJES, TACF, TSO 등
│   └── ...
├── error-codes/                  # 에러 코드 사전
│   ├── index.md                  # 에러 범위별 목록
│   ├── BASE-0.md                 # Non-VSAM (-0)
│   ├── BASE-1000.md              # TSAM (-1000)
│   ├── BASE-5000.md              # DSALC (-5000) ← -5212 포함
│   └── ...
├── products/                     # 제품별 요약
│   ├── index.md                  # 제품 목록
│   ├── openframe-base.md         # OpenFrame Base 개요
│   ├── openframe-batch.md        # Batch 시스템 (TJES 포함)
│   ├── openframe-tacf.md         # TACF 보안
│   ├── tibero.md                 # Tibero DB
│   └── tmax.md                   # Tmax TP 모니터
├── components/                   # 컴포넌트 사전
│   ├── index.md                  # 컴포넌트 전체 목록
│   ├── obmjschd.md               # Job Scheduler
│   ├── tjclrun.md                # JCL Runner
│   └── ...
└── commands/                     # 명령어 사전
    ├── index.md                  # 명령어 목록
    ├── tjesmgr.md                # TJES Manager 명령어
    └── ...
```

## 3. 마크다운 파일 포맷

### 3.1 용어 사전 (glossary/*.md)

```markdown
---
type: glossary
language: ja
generated: 2025-01-25T10:00:00Z
source_files:
  - OF_Batch_XSP_7.3_TJES-Guide_v3.2.1_ja.pdf
---

# T

## TJES
- **정식명칭**: Tmax Job Entry Subsystem
- **제품군**: OpenFrame Batch (XSP/MSP/MVS)
- **설명**: 富士通メインフレームのJESに対応するバッチ・ジョブ管理モジュール
- **주요기능**:
  - JCLを通じてジョブをサブミット
  - ジョブのスケジューリング
  - ジョブの出力処理
- **관련용어**: JCL, ジョブグループ, ランナー, スプール
- **참조매뉴얼**: OF_Batch_XSP_7.3_TJES-Guide_v3.2.1_ja.pdf

## TACF
- **정식명칭**: Tmax Access Control Facility
- **제품군**: OpenFrame Security
- **설명**: OpenFrameのセキュリティ製品
...
```

### 3.2 에러 코드 사전 (error-codes/*.md)

```markdown
---
type: error-codes
module: DSALC
range: -5000 ~ -5999
language: ja
generated: 2025-01-25T10:00:00Z
source_files:
  - OF_Common_XSP_7.3_Error-Reference-Guide_v3.2.1_ja.pdf
---

# DSALC 에러 코드 (-5000)

## 모듈 개요
DSALCモジュールは、データセットの割り当てを処理します。

## 에러 목록

### DSALC_ERR_ALREADY_CATALOGED (-5211)
- **설명**: 新規データセットがすでにカタログ化されている場合
- **대처방법**: 状況を確認してデータセットを削除した後、再実行します
- **참고**: -

### DSALC_ERR_INVALID_DSNAME (-5202)
- **설명**: データセット名が無効な場合に発生します
- **대처방법**: 有効なデータセット名を指定して再実行します
- **참고**: -
...
```

### 3.3 제품 요약 (products/*.md)

```markdown
---
type: product
product_id: openframe-batch
language: ja
version: "7.3"
generated: 2025-01-25T10:00:00Z
source_files:
  - OF_Batch_XSP_7.3_TJES-Guide_v3.2.1_ja.pdf
  - OF_Batch_XSP_7.3_Batch-Guide_v3.2.1_ja.pdf
---

# OpenFrame Batch

## 개요
OpenFrame Batchは、メインフレームのバッチ処理をUNIX環境で実行するための製品です。

## 주요 컴포넌트
| 컴포넌트 | 설명 |
|---------|------|
| TJES | ジョブ管理サブシステム |
| tjclrun | JCL実行モジュール |
| obmjschd | ジョブスケジューラー |

## 관련 매뉴얼
- TJES-Guide: ジョブ管理の詳細
- Batch-Guide: バッチ処理の概要
- JCL-Reference-Guide: JCL文法
...
```

## 4. 파일명 패턴 분석

현재 매뉴얼 파일명 규칙:
```
OF_<Component>_<Platform>_<Version>_<GuideType>_<DocVersion>_<Language>.pdf

예시:
- OF_Common_XSP_7.3_Error-Reference-Guide_v3.2.1_ja.pdf
- OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_jp.pdf
- Tibero_7_SQL_Reference_Guide_v2.1.1_jp.pdf
```

**Component**: Base, Batch, Common, TACF, GW, OSC, OSI, AIM, NDB, COBOL, ASM
**Platform**: XSP, MSP, MVS (또는 없음)
**GuideType**: Error-Reference-Guide, Installation-Guide, User-Guide, etc.

## 5. 처리 파이프라인

```
[PDF 파일]
     ↓
[1] PDF 파서 (pymupdf)
     - 텍스트 추출
     - TOC 추출
     - 메타데이터 추출
     ↓
[2] 콘텐츠 분류기
     - Error-Reference-Guide → 에러 코드 추출
     - *-Guide → 용어/개념 추출
     - Installation-Guide → 설치 관련 정보
     ↓
[3] LLM 기반 요약기 (선택적)
     - 복잡한 개념 요약
     - 용어 정의 생성
     ↓
[4] Markdown 생성기
     - 표준 포맷으로 변환
     - YAML frontmatter 추가
     ↓
[5] 인덱스 생성기
     - 전체 인덱스 갱신
     - 검색 최적화
```

## 6. 구현 모듈

```
scripts/manual_processor/
├── __init__.py
├── main.py                    # CLI 엔트리포인트
├── config.py                  # 설정
├── models/
│   ├── __init__.py
│   ├── manual.py              # 매뉴얼 메타데이터 모델
│   ├── error_code.py          # 에러 코드 모델
│   └── glossary.py            # 용어 모델
├── parsers/
│   ├── __init__.py
│   ├── pdf_parser.py          # PDF 파싱
│   ├── error_parser.py        # 에러 코드 파싱
│   └── content_parser.py      # 일반 콘텐츠 파싱
├── generators/
│   ├── __init__.py
│   ├── markdown_generator.py  # Markdown 생성
│   └── index_generator.py     # 인덱스 생성
└── utils/
    ├── __init__.py
    └── file_utils.py          # 파일 유틸리티
```

## 7. 사용 방법

```bash
# 전체 매뉴얼 처리
python -m scripts.manual_processor.main process-all

# 특정 PDF 처리
python -m scripts.manual_processor.main process /path/to/manual.pdf

# 에러 코드만 추출
python -m scripts.manual_processor.main extract-errors

# 인덱스 재생성
python -m scripts.manual_processor.main rebuild-index
```

## 8. Agent 연동

요약본은 다음과 같이 Agent에서 활용:

```python
# RAG Agent 프롬프트에 추가
async def enrich_query(user_query: str) -> str:
    """사용자 쿼리를 요약본으로 보강"""

    # 1. 에러 코드 패턴 감지
    error_match = re.search(r'-?\d{4,5}', user_query)
    if error_match:
        error_code = error_match.group()
        context = await search_error_summaries(error_code)
        return f"{user_query}\n\n[컨텍스트: {context}]"

    # 2. 용어 검색
    terms = extract_technical_terms(user_query)
    for term in terms:
        definition = await search_glossary(term)
        if definition:
            user_query += f"\n[{term}: {definition}]"

    return user_query
```
