---
description: Legacy HOST 메인프레임 코드를 분석합니다. COBOL/JCL/ASM/MAP 소스를 자동 감지하여 적절한 전문 에이전트로 분석합니다.
---

# Legacy Code Analysis

레거시 메인프레임 소스코드를 분석하는 스킬입니다. IBM MVS 및 Fujitsu XSP 코드를 지원합니다.

## 사용법

```
/legacy-analyze <파일경로 또는 코드 설명>
/legacy-analyze app/legacy/PROG001.cbl
/legacy-analyze "이 COBOL 프로그램의 CICS 명령어 분석"
```

## 자동 언어 감지

소스코드를 분석하여 자동으로 적절한 에이전트를 선택합니다:

| 언어 감지 기준 | Agent | 감지 패턴 |
|---------------|-------|-----------|
| COBOL | `legacy-cobol-expert` | `IDENTIFICATION DIVISION`, `PROCEDURE DIVISION`, `WORKING-STORAGE`, `EXEC CICS`, `EXEC SQL` |
| JCL | `legacy-jcl-expert` | `//.*JOB`, `//.*EXEC`, `//.*DD`, `AIMPED` |
| Assembler | `legacy-asm-expert` | `CSECT`, `DSECT`, `USING`, `BALR`, `DC`, `DS` |
| MAP | `legacy-map-expert` | `DFHMSD`, `DFHMDI`, `DFHMDF`, `PSAM` |

## 분석 단계

1. **언어 감지**: 소스코드 패턴으로 COBOL/JCL/ASM/MAP 식별
2. **구조 분석**: 프로그램 구조 파싱 (Division, Statement, Instruction)
3. **Feature 추출**: 벤더별 특수 기능 식별 (CICS, DB2, IMS, AIM/DB)
4. **호환성 평가**: OpenFrame 마이그레이션 관점 호환성 분석
5. **보고서 생성**: 구조화된 분석 리포트 출력

## 분석 항목

### COBOL 분석
- Division/Section 구조
- CICS/DB2/IMS/AIM-DB 인터페이스
- FILE I/O 패턴 (VSAM, Sequential)
- COPYBOOK 의존성 트리
- 데이터 타입 (PIC clause 분석)
- CALL 인터페이스 (BY REFERENCE/CONTENT/VALUE)

### JCL 분석
- JOB/EXEC/DD statement 파싱
- Dataset 인벤토리 (DSN, DISP, DCB)
- 조건부 실행 (COND/IF) 플로우
- 유틸리티 프로그램 식별 (SORT, IDCAMS, IEBCOPY)
- VSAM/GDG 작업 추적
- XSP AIMPED 확장 감지

### Assembler 분석
- 명령어 프로파일 (Load/Store, Arithmetic, Branch)
- 레지스터 사용 추적
- DSECT 구조 매핑
- SVC 호출 식별
- 매크로 사용 분석
- 링키지 컨벤션 확인

### MAP 분석
- 화면 레이아웃 시각화
- 필드 인벤토리 (위치, 길이, 속성)
- 입력/출력 필드 분류
- COBOL DSECT 링키지
- 속성 바이트 분석

## 참조 사양서

분석 시 다음 사양서를 참조합니다:
- `docs/specs/XSP/00_XSP_ARCHITECTURE.md` - XSP 아키텍처
- `docs/specs/XSP/01_JCL_SPEC.md` - JCL 사양
- `docs/specs/XSP/02_COBOL_SPEC.md` - COBOL 사양
- `docs/specs/XSP/03_ASM_SPEC.md` - ASM 사양

## 출력 형식

분석 결과는 다음 형식으로 출력됩니다:

```markdown
## Legacy Code Analysis Report

### Overview
- Language: [COBOL/JCL/ASM/MAP]
- Platform: [IBM MVS / Fujitsu XSP]
- Complexity: [LOW/MEDIUM/HIGH/CRITICAL]

### Structure Analysis
[언어별 구조 분석 결과]

### Feature Detection
[벤더 특수 기능 목록]

### Migration Assessment
[OpenFrame 호환성 평가]

### Recommendations
[마이그레이션 권장사항]
```

자동으로 언어를 감지하여 적절한 전문 에이전트(legacy-cobol-expert, legacy-jcl-expert, legacy-asm-expert, legacy-map-expert)를 호출합니다. $ARGUMENTS가 파일 경로인 경우 해당 파일을 읽어 분석합니다.
