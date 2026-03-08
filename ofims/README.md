# ofims - IMS Semantic Search CLI

BGE-M3 IR 모델 기반 자연어 IMS 이슈 검색 CLI 도구입니다.
21,215개 IMS 이슈를 자연어 질의로 검색하고, 이슈 분석/요약/지식 생성을 수행합니다.

## 실행 방법

```bash
# 프로젝트 루트에서 모듈로 실행
python -m ofims <command> [options]
```

## 서브커맨드

### search - 시맨틱 검색

자연어 질의를 BGE-M3 벡터로 변환하여 유사 IMS 이슈를 검색합니다.

```bash
python -m ofims search "TJES 배치 잡 실행 에러"
python -m ofims search "VSAM 데이터셋 오류" --limit 20
python -m ofims search "에러" --product "OpenFrame Batch"
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--limit` | 10 | 최대 결과 수 |
| `--product` | None | 제품명 필터 |

### detail - 이슈 상세 조회

이슈 메타데이터, 상세 내용, 조치 이력, 참조 이슈/URL 정보를 조회합니다.

```bash
python -m ofims detail 110005
python -m ofims detail 347574
```

### related - 관련 이슈 탐색

이슈 본문의 IMS#XXXXXX 패턴을 추출하여 관련 이슈 목록을 반환합니다.

```bash
python -m ofims related 347574
```

### summarize - 이슈 요약

LLM을 사용하여 이슈 내용을 구조화된 요약(핵심 요약, 주요 포인트, 해결 방법)으로 생성합니다.

```bash
python -m ofims summarize 110005
python -m ofims summarize 110005 --lang ko
python -m ofims summarize 110005 --lang ja
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--lang` | auto | 응답 언어: auto, ko, ja, en |

### chat - 검색 + 채팅 (SSE 스트리밍)

자연어 질문 → 시맨틱 검색 → 관련 이슈 컨텍스트 로드 → LLM 실시간 스트리밍 답변을 수행합니다.

```bash
python -m ofims chat "배치 잡 실행시 에러 원인이 뭔가요?"
python -m ofims chat "tjesmgr BOOT 실패 해결법" --limit 10
python -m ofims chat "VSAM 관련 문제" --no-related --lang ko
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--limit` | 5 | 검색할 이슈 수 |
| `--no-related` | False | 관련 이슈 자동 포함 비활성화 |
| `--lang` | auto | 응답 언어 |

### create-knowledge - 지식 문서 생성

하나 이상의 IMS 이슈 내용을 분석하여 재사용 가능한 Markdown 지식 문서를 생성합니다.

```bash
python -m ofims create-knowledge 110005 60605 --title "TJES Batch Error Guide"
python -m ofims create-knowledge 347574 345945 344074 --title "리턴코드 트러블슈팅" --lang ko
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--title` | (필수) | 지식 문서 제목 |
| `--lang` | auto | 생성 언어 |

## 글로벌 옵션

모든 서브커맨드에 공통으로 적용됩니다.

```bash
python -m ofims --url http://192.168.8.11:9000 search "에러"
python -m ofims --user admin --password "비밀번호" detail 110005
```

| 옵션 | 환경변수 | 기본값 |
|------|----------|--------|
| `--url` | `OFIMS_API_URL` | `http://localhost:9000` |
| `--user` | `OFIMS_USERNAME` | `admin` |
| `--password` | `OFIMS_PASSWORD` | (설정 파일 참조) |

## 환경변수 설정

```bash
export OFIMS_API_URL=http://localhost:9000
export OFIMS_USERNAME=admin
export OFIMS_PASSWORD="SecureAdm1nP@ss2024!"
```

## 의존성

```
requests
```

## API 엔드포인트 매핑

| CLI 커맨드 | HTTP Method | API Endpoint |
|------------|-------------|--------------|
| search | POST | `/api/v1/ims-chat/search` |
| detail | GET | `/api/v1/ims-chat/issues/{ims_id}` |
| related | GET | `/api/v1/ims-chat/issues/{ims_id}/related` |
| summarize | POST | `/api/v1/ims-chat/issues/summarize` |
| chat | POST | `/api/v1/ims-chat/chat/semantic` |
| create-knowledge | POST | `/api/v1/ims-chat/knowledge/create` |
