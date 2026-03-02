# PDF 청킹 아키텍처

> Feature: pdf-chunking-architecture
> Status: IMPLEMENTED
> Date: 2026-02-16

---

## 1. 개요

KMS 시스템은 용도에 따라 3가지 독립된 PDF 청킹 경로를 운용한다. 각 경로는 서로 다른 검색 요구사항에 맞춰 설계되었으며, 공통적으로 PyMuPDF(fitz)를 PDF 파서로 사용한다.

| 경로 | 용도 | 청킹 전략 | 검색 속도 |
|------|------|----------|----------|
| A: Manual Processor | 요약본 생성 | 시맨틱/TOC 기반 | N/A (생성 전용) |
| B: StructuredKnowledgeStore | Agentic RAG 검색 | Markdown 섹션 + PDF TOC | <10ms |
| C: PostgreSQL Vector Store | 레거시 RAG | 고정 크기 | 10~50ms |

---

## 2. 경로 A: Manual Processor (요약본 생성용)

scripts/manual_processor/ 디렉토리에 위치하며, PDF에서 구조화된 요약본(Markdown)을 생성하는 파이프라인이다.

### 2.1 처리 흐름

```
PDF
 -> PDFParser (PyMuPDF)
     -> 페이지 텍스트 + 테이블 추출
     -> ParagraphReconstructor (줄바꿈 -> 의미 단락 복원)
     -> TableToMarkdownConverter (PyMuPDF 테이블 -> GFM Markdown)
 -> StructureParser
     -> TOC 4단계 계층 구조 (Chapter, Section, Subsection, Paragraph)
 -> SemanticChunker
     -> EnhancedChunk[] (200~1500자, 섹션 경계 존중)
 -> Markdown 요약본 (uploads/summaries/)
```

### 2.2 청크 설정

| 파라미터 | 값 | 설명 |
|---------|-----|------|
| min_size | 200자 | 최소 청크 크기 |
| target_size | 800자 | 목표 청크 크기 |
| max_size | 1500자 | 최대 청크 크기 |
| overlap | 5~20% | 청크 간 겹침 (크기에 따라 적응적) |

### 2.3 ParagraphReconstructor 규칙

PDF에서 추출한 줄 단위 텍스트를 의미 있는 단락으로 재구성한다.

- 문장 종결 부호(.!?。？！) -> 단락 끝
- 콜론(:) -> 리스트 시작 표지
- 빈 줄 -> 단락 구분
- 리스트 마커(-, *, 1. 등) -> 별도 항목
- 헤딩 패턴(1.1, 第2章 등) -> 별도 단락

### 2.4 EnhancedChunk 메타데이터

| 필드 | 설명 |
|------|------|
| chunk_id | MD5 해시 (중복 제거용) |
| content | 청크 텍스트 |
| chunk_type | TEXT, TABLE, IMAGE, MIXED |
| section_title | 계층 섹션명 (예: "1.2.3 설정 방법") |
| section_level | 1~4 (Chapter~Paragraph) |
| page_range | (시작 페이지, 종료 페이지) |
| images[] | 포함된 이미지 목록 |
| tables[] | 포함된 테이블 목록 |
| keywords[] | 자동 추출 키워드 (최대 7개) |
| previous_chunk_id | 이전 청크 연결 |
| next_chunk_id | 다음 청크 연결 |

---

## 3. 경로 B: StructuredKnowledgeStore (Agentic RAG 검색용)

app/api/services/structured_knowledge_store.py (약 1050줄)에 위치하며, Agentic RAG에서 사용하는 핵심 검색 경로다. 메모리에 캐시하여 10ms 이내 검색을 보장한다.

### 3.1 사용 라이브러리

| 라이브러리 | 용도 | 선택 이유 |
|-----------|------|----------|
| PyMuPDF (pymupdf/fitz) | PDF 파싱, TOC 추출, 텍스트/이미지/테이블 추출, 드로잉 분석 | C++ 기반으로 처리속도 빠름, TOC/드로잉/블록 단위 좌표 접근 지원 |
| re (표준 라이브러리) | 서브커맨드 패턴 감지, CJK 토큰화, 텍스트 정리 | 정규식 기반 다국어 토큰화에 적합 |
| math (표준 라이브러리) | IDF 가중치 계산 (log 함수) | - |
| glob (표준 라이브러리) | 파일 경로 패턴 매칭 (요약본/PDF 탐색) | - |
| dataclasses (표준 라이브러리) | SearchResult, ProductSearchContext 모델 | 경량 데이터 클래스 |

외부 라이브러리 의존성은 PyMuPDF 하나뿐이며, 나머지는 Python 표준 라이브러리만 사용한다. LLM이나 임베딩 모델에 의존하지 않아 결정론적이고 빠른 검색이 가능하다.

### 3.2 처리 흐름

```
PDF/Markdown/학습JSON
 -> 파일 형식 판별:
    .pdf  -> _parse_pdf()
    .json -> _parse_learning_json() (ChatML Q&A 쌍)
    기타   -> _parse_markdown() (## 헤더 기반 섹션 분리)
 -> PDF 처리 시:
    -> doc.get_toc()로 TOC 추출 시도
       성공(3개 이상) -> _parse_pdf_by_toc() (L1~L3 계층 처리)
       실패           -> _parse_pdf_by_headings() (숫자 헤딩 패턴 fallback)
    -> Front Matter 제외 (表紙, 目次, 改訂履歴)
    -> 부모-자식 관계 분석 (자식 있는 부모는 스킵, 개요만 별도 저장)
    -> _build_hierarchical_title() (역방향 부모 탐색으로 계층 타이틀 조합)
    -> _extract_page_text_with_codeblocks() (음영->코드블록, 테이블->GFM)
    -> _clean_pdf_text() (반복 헤더/푸터 제거, 코드블록 내부 보존)
    -> 대형 섹션(>8000자) -> _split_by_subcommands() (대문자 패턴 분할)
 -> Dict[] (메모리 캐시, _cache[domain] = sections)
 -> 검색 시: _tokenize_query() + _calc_document_frequencies() + search()
```

### 3.3 TOC 기반 계층 파싱 (_parse_pdf_by_toc)

PDF의 목차 구조를 L1->L2->L3로 파싱하여 섹션 경계를 잡는다. L4 이하는 무시한다.

핵심 로직:
1. 前付 스킵: "目次", "表紙", "改訂履歴" 항목과 그 이전 모든 항목을 건너뜀
2. 부모-자식 분석: 각 TOC 항목에 대해 하위 레벨 항목이 있는지 확인
3. 자식 있는 부모 처리: 콘텐츠 추출을 스킵하되, 첫 자식 이전의 개요 텍스트(100자 이상)는 "(概要)" 접미사로 별도 저장
4. 계층 타이틀: 역방향 탐색으로 직계 부모를 찾아 "IDCAMS > 機能コマンド" 형식으로 조합 (번호 접두사 "1.4.2." 자동 제거)

```
TOC 예시:
  (level:1, "제1장 개요", page:10)
  (level:2, "1.1 시스템 구성", page:12)
  (level:3, "1.1.1 네트워크 설정", page:14)

-> 부모-자식 분석: "제1장 개요"는 자식 있음 -> 스킵 (개요만 저장)
-> 섹션 경계: page 12~13, page 14~(다음 TOC항목)
-> 타이틀: "시스템 구성 > 네트워크 설정" (번호 제거됨)
```

### 3.4 서브커맨드 분리 (_split_by_subcommands)

명령어 레퍼런스 같이 한 섹션이 8000자를 넘으면 대문자 패턴으로 자동 분리한다.

```
정규식: ^([A-Z][A-Z0-9]+(?: [A-Z0-9]+)*)$
감지 예시: ALTER, DEFINE, DEFINE CLUSTER, LISTCAT
```

분리 판정 조건:
- 대문자 패턴 매칭 + 3자 이상
- 직전 또는 직후에 빈 줄 필수 (문장 중간의 약어 제거)
- 밀집 필터: 10줄 이내 5개 이상 연속이면 테이블/파라미터 목록으로 판단하여 제외
- 최소 2개 이상의 서브커맨드가 감지되어야 분할 실행

노이즈 제외 목록: TABLE OF CONTENTS, PAGE, CHAPTER, SECTION, FIGURE, EXAMPLE, NOTE, WARNING, DD, JCL, JOB, EXEC 등

분리 전:
```
"IDCAMS > 機能コマンド" (12000자)
  ALTER 설명...
  DEFINE 설명...
  DEFINE CLUSTER 설명...
  LISTCAT 설명...
```

분리 후:
```
"IDCAMS > 機能コマンド > ALTER" (2500자, p.37 추정)
"IDCAMS > 機能コマンド > DEFINE" (3200자, p.42 추정)
"IDCAMS > 機能コマンド > DEFINE CLUSTER" (3800자, p.48 추정)
"IDCAMS > 機能コマンド > LISTCAT" (2500자, p.55 추정)
```

페이지 번호는 섹션 내 라인 위치 비율로 추정한다: est_page = start_page + int(line_ratio * total_pages)

### 3.5 코드블록 감지 (_get_shaded_rects + _extract_page_text_with_codeblocks)

PyMuPDF의 page.get_drawings() API로 PDF 내 음영 사각형을 감지하여 코드블록으로 변환한다.

음영 영역 감지 조건:
- fill 색상이 존재 (fill is not None)
- 너비 > 200px, 높이 >= 15px
- 회색 계열 색상 (RGB 각 값이 0.05~0.98 범위)
- 흰색(>0.98)과 검정(<0.05)은 제외

텍스트 추출 과정:
1. page.get_text("dict")로 블록별 좌표+텍스트 추출
2. 각 텍스트 라인의 y좌표 중심점이 음영 rect 내에 있으면 코드로 표시
3. 인접한 코드 라인은 하나의 ``` 블록으로 병합
4. 테이블 영역 내 텍스트는 스킵하고 GFM Markdown 테이블로 대체
5. 모든 요소를 y좌표 순으로 정렬하여 원문 순서 유지

### 3.6 테이블 처리 (지연 추출 전략)

성능 최적화를 위해 PDF 초기 로드 시에는 테이블을 추출하지 않는다.

- 초기 파싱: extract_tables=False (기본값) -> 테이블 영역 무시, 텍스트만 추출
- 검색 시: extract_tables=True -> 해당 페이지의 find_tables() 호출

지연 추출의 이유:
- find_tables()는 페이지당 50~200ms 소요
- 245개 PDF, 4000+ 페이지를 초기 로딩 시 모두 처리하면 약 400초 소요
- 검색 시에는 1~5페이지만 대상으로 하여 100~1000ms로 처리 가능

테이블 감지 전제조건: drawing_count >= 5 (드로잉이 5개 미만이면 테이블 가능성 낮음)

테이블 변환: PyMuPDF table.extract() -> GFM Markdown 형식 (| header | sep | body |)

### 3.7 텍스트 정리 (_clean_pdf_text)

코드블록 내부를 보존하면서 PDF 노이즈를 제거한다.

1. 前付 제거: "目次" 행이 있으면 그 행까지 삭제
2. 코드블록 분리: 정규식 ```...```으로 분리하여 코드 내부는 그대로 유지
3. 일반 텍스트: 연속 공백 정리, 페이지 번호 패턴(-N-) 제거, 연속 빈 줄 축소
4. 반복 헤더/푸터: 같은 줄이 3회 이상 등장하면 제거 (코드블록 외부만)

### 3.8 이미지 추출 (_extract_page_images)

PyMuPDF의 Pixmap API로 페이지 내 이미지를 추출하여 PNG 파일로 저장한다.

- CMYK 색상 공간은 자동으로 RGB 변환
- 50x50 미만의 작은 이미지(아이콘 등)는 스킵
- 저장 경로: uploads/pdf_images/{product_id}/p{page}_img{idx}.png
- Markdown 이미지 참조 반환: ![Figure (p.45)](/uploads/pdf_images/mvs_openframe_7.1/p45_img0.png)

### 3.9 Front Matter 제외 목록

| 패턴 | 설명 |
|------|------|
| 目次 | 목차 |
| もくじ | 목차 (히라가나) |
| 改訂履歴 | 개정이력 |
| 表紙 | 표지 |

TOC 기반 파싱에서는 "目次" 항목과 그 이전 항목을 모두 건너뛴다.
Heading 기반 파싱에서는 텍스트 내 "目次" 행까지 삭제한다.

### 3.10 검색 알고리즘 (Progressive Token + IDF)

LLM 없이 키워드 기반으로 검색하며, 다음 단계로 구성된다.

#### 3.10.1 토큰화 (_tokenize_query)

다국어 쿼리를 의미 있는 토큰으로 분리한다.

| 언어 | 패턴 | 최소 길이 |
|------|------|----------|
| 영문+숫자 | [a-z0-9][a-z0-9_-]*[a-z0-9] 또는 [a-z0-9] | 2자 (1자 영문 제거) |
| 카타카나 | [\u30a0-\u30ff]{2,} | 2자 |
| 한자 | [\u4e00-\u9fff]+ | 1자 |
| 한국어 | [\uac00-\ud7af]{2,} | 2자 |
| 히라가나 | [\u3040-\u309f]{2,} | 2자 |

불용어 목록 (약 60개):
- 일본어 조사/접속사: の, は, が, を, に, で, と 등
- 일본어 기능어구: について, してください, とは, ている, できる 등
- 영어: the, a, an, of, in, what, how, explain, please 등

#### 3.10.2 IDF 가중치 계산 (_calc_document_frequencies)

```
IDF(token) = log((N + 1) / (DF + 1)) + 1.0
- N: 검색 대상 전체 섹션 수
- DF: 해당 토큰이 포함된 섹션 수
```

희소한 토큰(제품명, 명령어명 등)은 높은 IDF 가중치를 받아 검색 정확도가 올라간다.

#### 3.10.3 Progressive Token 스코어링

전체 후보 섹션에 대해 토큰별로 순차적으로 점수를 부여한다.

| 매칭 위치 | 점수 |
|----------|------|
| 섹션 타이틀에 토큰 포함 | +3.0 * IDF |
| 섹션 본문에 토큰 포함 | +1.0 * IDF |

중간 프루닝: 2번째 토큰 처리 후, 후보 수가 top_k*20을 초과하면 상위만 남기고 축소한다. 이로써 수천 개 섹션에서도 일정한 처리 속도를 유지한다.

#### 3.10.4 에러코드 정확 매칭 보너스

쿼리에 4~5자리 숫자 패턴(-XXXX)이 있고, error_codes 도메인의 섹션 타이틀이나 본문에 해당 코드가 포함되면 +10.0 보너스를 부여한다.

#### 3.10.5 커버리지 보정

매칭된 토큰 비율로 최종 점수를 조정한다.

```
coverage = matched_tokens / total_tokens  (0.0 ~ 1.0)
coverage_factor = 0.5 + 0.5 * coverage    (0.5 ~ 1.0)
최종 점수 = 원점수 * coverage_factor
```

쿼리의 모든 토큰이 매칭되면 점수 100% 유지, 일부만 매칭되면 최대 50%까지 감점된다.

#### 3.10.6 도메인 부스트

권위 있는 데이터 소스를 우선 배치하기 위해 도메인별 가중치를 적용한다.

| 도메인 | 부스트 배율 | 이유 |
|--------|-----------|------|
| pdf_manuals | 1.5 | PDF 원본 최우선 (가장 정확한 원본 데이터) |
| commands | 1.3 | 명령어 요약본 (구조화된 정보) |
| configs | 1.2 | 설정 파라미터 (구조화된 정보) |
| error_codes | 1.3 / 0.7 | 에러코드 패턴 있으면 1.3, 없으면 0.7 (오염 방지) |
| glossary | 0.6 | 용어 요약본 (중복/노이즈 가능성) |
| learning_qa | 0.4 | QLoRA 학습 데이터 (cross-product 오염 가능성이 있어 강하게 감점) |

#### 3.10.7 중복 제거

content 앞 120자를 정규화(알파벳+숫자+CJK만 추출)하여 fingerprint로 사용한다. 동일 fingerprint를 가진 결과는 첫 번째만 유지하고 나머지는 제거한다. 이로써 요약본과 PDF 원본에서 같은 내용이 중복 반환되는 것을 방지한다.

### 3.11 학습 데이터 통합 (_parse_learning_json)

QLoRA 학습용 JSON 파일(ChatML 형식)도 검색 대상으로 활용한다.

- ChatML에서 user 메시지를 title로, assistant 메시지를 content로 변환
- 답변 길이 20자 미만은 스킵 (너무 짧은 Q&A 제외)
- domain: "learning_qa"로 분류되어 도메인 부스트 0.4 적용 (cross-product 오염 방지)

### 3.12 SearchResult 모델

| 필드 | 타입 | 설명 |
|------|------|------|
| title | str | 계층 섹션 제목 (예: "IDCAMS > DEFINE > CLUSTER") |
| content | str | 섹션 본문 (최대 8000자) |
| source_file | str | 원본 파일명 (PDF/Markdown/JSON) |
| source_page | str | 페이지 번호 (예: "p.45") |
| relevance_score | float | Progressive Token + IDF 점수 (도메인 부스트/커버리지 보정 후) |
| domain | str | commands, error_codes, configs, glossary, pdf_manuals, learning_qa |
| product | str | 제품 ID (예: mvs_openframe_7.1) |
| source_path | str | PDF 파일 전체 경로 (지연 테이블/이미지 추출용) |

### 3.13 성능 특성

| 항목 | 수치 |
|------|------|
| 초기 로딩 | 제품당 1~5초 (245개 PDF 전체 파싱, 1회만 실행) |
| 검색 속도 | <10ms (메모리 캐시 + Progressive Token 프루닝) |
| 메모리 사용 | 제품당 수~수십 MB (섹션 수에 비례) |
| 섹션 크기 제한 | 최대 8000자 (초과 시 서브커맨드 분할) |
| 테이블 추출 | 50~200ms/page (검색 시 lazy extraction, 1~5페이지) |
| 이미지 추출 | 50x50px 이상만, CMYK->RGB 자동 변환 |

검색 결과 예시 (tjesmgr BOOT 질문):
- 타이틀 매칭(3.0*IDF)으로 "tjesmgr > BOOT" 섹션이 최상위에 배치
- pdf_manuals 도메인 부스트(1.5)로 PDF 원본이 요약본보다 우선
- learning_qa 데이터는 0.4 감점으로 cross-product 오염 방지
- 에러코드가 아닌 일반 질문에서 error_codes 도메인은 0.7 감점

---

## 4. 경로 C: PostgreSQL Vector Store (레거시 RAG)

app/api/infrastructure/postgres/text_chunk_repository.py에 위치하며, 임베딩 기반 벡터 검색에 사용된다.

### 4.1 처리 흐름

```
문서
 -> 고정 크기 텍스트 청크
 -> NIM 임베딩 모델 (4096차원)
 -> PostgreSQL pgvector 저장
 -> 코사인 유사도 검색
```

### 4.2 스키마

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | TEXT PK | 청크 고유 ID |
| document_id | TEXT | 원본 문서 ID |
| chunk_index | INTEGER | 순차 청크 번호 |
| content | TEXT | 청크 텍스트 |
| content_length | INTEGER | 텍스트 길이 |
| chunk_type | TEXT | text, code, table 등 |
| page_number | INTEGER | PDF 페이지 번호 |
| embedding | vector(4096) | NIM 임베딩 벡터 |
| has_embedding | BOOLEAN | 임베딩 존재 여부 |
| metadata | JSONB | 기타 메타데이터 |

---

## 5. 경로별 비교

| 항목 | Manual Processor | StructuredKnowledgeStore | PostgreSQL Vector |
|------|-----------------|------------------------|------------------|
| 청킹 전략 | 시맨틱/TOC 기반 | Markdown 섹션 + PDF TOC | 고정 크기 |
| 경계 기준 | 섹션 경계 존중 | 섹션 헤더 + 서브커맨드 | 없음 |
| 메타데이터 | 풀 (L1~4 계층, 이미지, 테이블) | 중간 (title, page, domain) | 최소 (id, page) |
| LLM 필요 | 없음 | 없음 | 임베딩 모델 필요 |
| 검색 속도 | N/A (생성 전용) | <10ms (메모리 캐시) | 10~50ms (DB 쿼리) |
| 테이블 처리 | 즉시 추출 | 지연 추출 (검색 시) | 텍스트로 변환 |
| 이미지 처리 | Vision LLM 설명 | PNG 추출 + 참조 | 미지원 |

---

## 6. 중복 제거 및 필터링

### 6.1 중복 제거 (StrategyAwareParser)

같은 (이름, 타입, 제품) 조합이 여러 번 나오면 설명이 긴 쪽을 보존한다.

### 6.2 필터링 규칙

| 규칙 | 조건 |
|------|------|
| 최소 이름 길이 | 4자 (단축 명령어 제외) |
| 최대 이름 길이 | 50자 (명령어/API), 80자 (개념) |
| 페이지 번호 패턴 | 숫자만으로 된 라인 제외 |
| 인코딩 깨짐 | mojibake 패턴 제외 |
| 일본어 조사만 | 히라가나 조각 제외 |
| 의미 문자 비율 | CJK/영문/숫자 30% 이상 필요 |

---

## 7. 전체 데이터 흐름

```
                        PDF MANUAL (245개, 19제품)
                              |
          +-------------------+-------------------+
          |                   |                   |
     PDFParser          StructureParser    StrategyAwareParser
     (페이지+테이블)      (TOC 계층)          (학습 데이터)
          |                   |                   |
     Page[]             DocumentStructure   LearningDataItem[]
     Tables[]           HierarchyNode[]     (중복 제거됨)
          |                   |                   |
          +-------------------+-------------------+
                              |
                      SemanticChunker
                              |
                      EnhancedChunk[]
                              |
          +-------------------+-------------------+
          |                   |                   |
    Markdown 요약본     PostgreSQL          Agent Memory
    (uploads/          text_chunks         (LangGraph)
     summaries/)       (pgvector)          (QLoRA 학습용)
          |                   |
    StructuredKnowledge  Vector Search
    Store (메모리 캐시)   (코사인 유사도)
          |                   |
    Agentic RAG          레거시 RAG
    (<10ms 검색)         (10~50ms 검색)
```

---

## 8. PDF Chunk Visualizer (CLI 도구)

scripts/pdf_chunk_visualizer.py에 위치하며, 경로 B(StructuredKnowledgeStore)의 청킹 로직을 그대로 사용하여 PDF를 청킹하고 결과를 HTML로 시각화하는 도구다.

### 8.1 사용법

```bash
# 단일 PDF 청킹 + HTML 시각화
python -m scripts.pdf_chunk_visualizer <pdf_path>

# 검색 기능 포함 (Progressive Token + IDF 검색 결과 표시)
python -m scripts.pdf_chunk_visualizer <pdf_path> --search "BOOT 명령어"

# 통계만 출력 (트리 형태로 섹션 계층 구조 표시)
python -m scripts.pdf_chunk_visualizer <pdf_path> --stats-only

# JSON 형식 출력
python -m scripts.pdf_chunk_visualizer <pdf_path> --json -o output.json

# 여러 PDF 동시 처리 (요약 index.html 자동 생성)
python -m scripts.pdf_chunk_visualizer uploads/manuals/MVS_*/*.pdf --output-dir temp/chunk_viz
```

### 8.2 출력 모드

| 모드 | 옵션 | 출력 |
|------|------|------|
| HTML 시각화 | (기본) | 인터랙티브 HTML (대시보드 + 섹션 카드) |
| 통계 전용 | --stats-only | 콘솔에 트리 형태로 섹션 구조 출력 |
| JSON 내보내기 | --json | 청킹 결과를 JSON 배열로 출력 |
| 멀티 PDF | 복수 경로 + --output-dir | 개별 HTML + 요약 index.html |

### 8.3 HTML 시각화 기능

통계 대시보드:
- 총 섹션 수, 총 문자 수, 평균/최소/최대 섹션 크기
- 코드블록 포함 섹션 수, 테이블 포함 섹션 수
- 크기 분포 차트 (small/medium/large/xlarge)

PDF TOC 트리 뷰:
- L1~L3 계층 구조 시각화
- 레벨별 들여쓰기 + 페이지 번호 표시

섹션 카드:
- 크기별 색상 코딩 (녹색 <500자, 파랑 500-2K, 주황 2K-5K, 빨강 5K+)
- CODE/TABLE 뱃지 (코드블록/테이블 포함 여부)
- 크기 비율 바 (최대 섹션 대비 비율)
- 클릭으로 본문 펼침/접기
- Expand All / Collapse All 버튼

필터링:
- 텍스트 검색 필터 (타이틀/본문에서 실시간 검색)
- 크기별 필터 (Small/Medium/Large/XLarge 버튼)

검색 결과 (--search 옵션 사용 시):
- StructuredKnowledgeStore.search()와 동일한 검색 로직 사용
- 상위 10건의 결과를 relevance_score와 함께 표시

### 8.4 테스트 결과

| PDF | 섹션 수 | 총 문자 | 파싱 시간 | 코드블록 | 테이블 |
|-----|--------|---------|----------|---------|-------|
| TJES-Guide (146p) | 138 | 243,537 | 365ms | 109 | 4 |
| Base-Guide (55p) | 41 | 63,605 | 126ms | - | - |
| Dataset-Guide (135p) | 116 | 201,357 | 305ms | - | - |

---

## 9. 주요 파일 목록

| 파일 | 역할 |
|------|------|
| scripts/manual_processor/parsers/pdf_parser.py | PDF 텍스트 + 테이블 추출 |
| scripts/manual_processor/parsers/content_parser.py | 콘텐츠 구조 파싱 |
| scripts/manual_processor/parsers/strategy_aware_parser.py | 학습 데이터 추출 |
| scripts/manual_processor/chunkers/ | 시맨틱 청커, 설정 |
| scripts/manual_processor/models/chunk.py | EnhancedChunk 모델 (232줄) |
| app/api/services/structured_knowledge_store.py | 메모리 캐시 검색 (1050줄) |
| app/api/infrastructure/postgres/text_chunk_repository.py | pgvector 저장소 |
| app/api/models/document.py | 문서/청크 모델 |
| scripts/pdf_chunk_visualizer.py | PDF 청킹 시각화 CLI 도구 |
