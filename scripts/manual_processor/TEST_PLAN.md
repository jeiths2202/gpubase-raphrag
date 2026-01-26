# LLM 파서 검증 테스트 계획서

## 개요

이 문서는 LLM 기반 매뉴얼 파서의 추출 품질을 검증하기 위한 종합 테스트 계획입니다.

## 테스트 도구

| 스크립트 | 용도 |
|----------|------|
| `test_extraction_patterns.py` | 기본 패턴 검증 (15개 테스트) |
| `test_comprehensive_patterns.py` | 종합 패턴 검증 (42개 테스트) |
| `validate_summaries.py` | 검색 서비스 통합 검증 |

## 테스트 카테고리

### 1. CONFIG (설정 파라미터) - 9개 테스트

| 테스트명 | 우선순위 | 패턴 예시 | 기대 수 |
|----------|----------|-----------|---------|
| 대문자_언더스코어 설정 | 🔴 Critical | TJES_SPOOL_DIR | 50+ |
| 단일 대문자 설정 | 🟠 High | EDITOR, SETUID | 20+ |
| 디렉토리/경로 설정 | 🟠 High | *_DIR, *_PATH | 20+ |
| 크기/카운트 설정 | 🟡 Medium | *_SIZE, *_COUNT | 15+ |
| 타임아웃/인터벌 설정 | 🟡 Medium | *_TIMEOUT | 10+ |
| 모드/타입 설정 | 🟡 Medium | *_MODE, *_TYPE | 15+ |
| 포트/호스트 설정 | 🟡 Medium | *_PORT, *_HOST | 5+ |
| 인증/보안 설정 | 🟡 Medium | *_AUTH, *_KEY | 5+ |
| 환경 변수 | 🟡 Medium | $OPENFRAME_HOME | 5+ |

### 2. CONCEPT (개념/용어) - 15개 테스트

| 테스트명 | 우선순위 | 패턴 예시 | 기대 수 |
|----------|----------|-----------|---------|
| 약어 (2-6자) | 🔴 Critical | VSAM, JCL, CICS | 50+ |
| 데이터 타입 | 🟠 High | BLOB, VARCHAR | 5+ |
| SQL DDL 명령어 | 🟠 High | CREATE TABLE | 10+ |
| SQL DML 명령어 | 🟡 Medium | SELECT, INSERT | 5+ |
| 동작 모드 | 🟡 Medium | Batch Mode | 10+ |
| 아키텍처 컴포넌트 | 🟡 Medium | Node, Cluster | 10+ |
| 데이터셋/파일 유형 | 🟠 High | PDS, VSAM, KSDS | 5+ |
| JCL 키워드 | 🟠 High | DD, JOB, EXEC | 5+ |
| 시스템 프로세스 | 🟡 Medium | DBWR, LGWR | 5+ |
| 트랜잭션/락 개념 | 🟡 Medium | Transaction, Lock | 5+ |
| DD 파라미터 | 🟠 High | DSN, DISP, DCB | 10+ |
| JOB 파라미터 | 🟡 Medium | CLASS, REGION | 5+ |
| EXEC 파라미터 | 🟡 Medium | PGM, PROC | 5+ |
| 파일 확장자 | 🟢 Low | .cob, .jcl | 5+ |
| 시스템 메시지 ID | 🟡 Medium | IEF142I | 10+ |

### 3. COMMAND (명령어) - 7개 테스트

| 테스트명 | 우선순위 | 패턴 예시 | 기대 수 |
|----------|----------|-----------|---------|
| 초기화/부팅 명령어 | 🔴 Critical | tjesinit, oscboot | 15+ |
| 종료/다운 명령어 | 🔴 Critical | oscdown, shutdown | 10+ |
| 관리 도구 | 🟠 High | tjesmgr, tacfadm | 15+ |
| 데이터셋 유틸리티 | 🟠 High | dsmigin, idcams | 10+ |
| 컴파일러/번역기 | 🟡 Medium | ofcob, ofasm | 5+ |
| 마이그레이션 도구 | 🟡 Medium | dsmigin, tbimport | 5+ |
| 모니터링/진단 도구 | 🟡 Medium | tjstat, osctrace | 5+ |

### 4. API (API 함수) - 5개 테스트

| 테스트명 | 우선순위 | 패턴 예시 | 기대 수 |
|----------|----------|-----------|---------|
| C 스타일 API | 🔴 Critical | tcfh_stow, tfcd_read | 30+ |
| EXEC CICS 명령어 | 🔴 Critical | EXEC CICS READ | 10+ |
| EXEC SQL 명령어 | 🟠 High | EXEC SQL SELECT | 5+ |
| EXEC DLI 명령어 | 🟡 Medium | EXEC DLI GU | 3+ |
| 콜백/핸들러 함수 | 🟢 Low | error_callback | 3+ |

### 5. ERROR_CODE (에러 코드) - 6개 테스트

| 테스트명 | 우선순위 | 패턴 예시 | 기대 수 |
|----------|----------|-----------|---------|
| 음수 에러 코드 (4자리) | 🔴 Critical | -5001, -5212 | 100+ |
| 음수 에러 코드 (5자리) | 🔴 Critical | -21001, -63702 | 50+ |
| 시스템 ABEND (Sxxx) | 🔴 Critical | S0C7, S322 | 10+ |
| 사용자 ABEND (Uxxxx) | 🟠 High | U4038, U0001 | 5+ |
| 모듈별 에러명 | 🟠 High | DSALC_ERR_xxx | 50+ |
| SQL 에러 코드 | 🟡 Medium | SQLCODE -811 | 5+ |

## 테스트 실행 방법

### 기본 테스트
```bash
python3 scripts/manual_processor/test_extraction_patterns.py
```

### 종합 테스트
```bash
python3 scripts/manual_processor/test_comprehensive_patterns.py
```

### 특정 카테고리만 테스트
```bash
python3 scripts/manual_processor/test_comprehensive_patterns.py --category config
python3 scripts/manual_processor/test_comprehensive_patterns.py --category error_code
```

### 결과 JSON 저장
```bash
python3 scripts/manual_processor/test_comprehensive_patterns.py \
  --output /opt/kms/uploads/summaries/test_results.json
```

## 합격 기준

| 레벨 | 기준 | 조치 |
|------|------|------|
| 🟢 합격 | Critical 100%, 전체 80%+ | 배포 가능 |
| 🟡 조건부 합격 | Critical 80%+, 전체 70%+ | 경미한 개선 후 배포 |
| 🔴 불합격 | Critical < 80% 또는 전체 < 70% | 개선 필수 |

## 현재 상태 (2026-01-25)

| 지표 | 현재 | 목표 | 상태 |
|------|------|------|------|
| 전체 통과율 | 66.7% | 80%+ | 🟡 개선 필요 |
| Critical 통과율 | 66.7% | 100% | 🔴 개선 필요 |

### 개선 완료 항목
- [x] CONFIG 전용 프롬프트 추가
- [x] CONCEPT 전용 프롬프트 추가
- [x] ERROR 전용 프롬프트 추가 (ABEND 코드 포함)
- [x] DEVELOPER 전용 프롬프트 추가 (EXEC 명령어 포함)
- [x] 패턴 감지 함수 추가 (_has_exec_pattern, _has_abend_pattern)

### 개선 예정 항목
- [ ] 종료/다운 명령어 추출 강화
- [ ] 모듈별 에러명 (DSALC_ERR_xxx) 추출
- [ ] 환경 변수 ($OPENFRAME_HOME) 추출
- [ ] 컴파일러/번역기 명령어 추출 강화

## 재검증 일정

1. **현재 추출 완료 후** (81/175 → 175/175)
   - 종합 테스트 재실행
   - 개선 효과 측정

2. **프롬프트 개선 후 재추출**
   - 실패 패턴 대상 매뉴얼만 재처리
   - 전체 재검증

## 파일 위치

```
scripts/manual_processor/
├── test_extraction_patterns.py      # 기본 테스트
├── test_comprehensive_patterns.py   # 종합 테스트
├── validate_summaries.py            # 통합 검증
├── TEST_PLAN.md                     # 이 문서
└── parsers/
    └── llm_parser.py                # LLM 파서 (프롬프트 포함)

uploads/summaries/
├── comprehensive_test_results.json  # 종합 테스트 결과
├── pattern_test_results.json        # 기본 테스트 결과
└── validation_results.json          # 검색 검증 결과
```
