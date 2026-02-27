---
description: OpenFrame 마이그레이션 호환성을 분석합니다. Legacy HOST 코드의 OpenFrame 제품 호환성, 변환 요구사항, 마이그레이션 리스크를 평가합니다.
---

# OpenFrame Migration Analysis

Legacy HOST 코드를 TmaxSoft OpenFrame으로 마이그레이션하기 위한 호환성 분석 스킬입니다.

## 사용법

```
/openframe-migrate <파일경로 또는 질문>
/openframe-migrate app/legacy/PROG001.cbl
/openframe-migrate "CICS COBOL 프로그램을 OSC로 마이그레이션"
/openframe-migrate "Fujitsu XSP JCL을 OpenFrame Batch로 변환"
```

## 지원 마이그레이션 경로

### Source → Target 매핑

| Source Platform | Target Product | Agent |
|----------------|---------------|-------|
| IBM MVS Batch/JCL | OpenFrame Batch (TJES) | `openframe-batch-expert` |
| IBM CICS Online | OpenFrame OSC | `openframe-online-expert` |
| IBM IMS/DC | OpenFrame OSI | `openframe-online-expert` |
| IBM COBOL | OFCOBOL (ENT/MVS) | `openframe-cobol-expert` |
| IBM HLASM | OFASM | `legacy-asm-expert` |
| Fujitsu XSP Batch | OpenFrame Batch (XSP) | `openframe-batch-expert` |
| Fujitsu AIM/DC | OpenFrame AIM(XSP) | `openframe-online-expert` |
| Fujitsu NetCOBOL | OFCOBOL (OSVS) | `openframe-cobol-expert` |
| Fujitsu ASSEMBH | OFASM | `legacy-asm-expert` |
| TACF/RACF Security | OpenFrame TACF | `openframe-infra-expert` |

### OpenFrame 제품 버전

| Product Family | Versions | Asset Types |
|---------------|----------|-------------|
| AIM(XSP) | 7.0, 7.1, 7.3 | COBOL, MAP |
| AIM(MSP) | 7.0, 7.1, 7.3 | COBOL, MAP |
| OSC | 7.0, 7.1, 7.3, 8.0 | COBOL, MAP |
| OSI | 6.0, 7.0, 7.1 | COBOL |
| OFASM | 4.0 | Assembler |
| OFCOBOL(OSVS/ENT/MVS) | 4.0 | COBOL |
| Batch | 7.0, 7.1, 7.3 | JCL, COBOL |
| HiDB | 3.0, 3.3, 7.2 | COBOL |
| TACF | 7.0, 7.1 | JCL |

## 분석 단계

1. **소스 플랫폼 식별**: IBM MVS / Fujitsu XSP / 기타
2. **코드 언어 분석**: COBOL/JCL/ASM/MAP 자동 감지
3. **벤더 특수 기능 식별**: CICS, DB2, IMS, AIM/DB, AIMPED 등
4. **OpenFrame 제품 매핑**: 적절한 타겟 제품 선정
5. **호환성 평가**: capability 매트릭스 기반 지원 수준 판정
6. **변환 요구사항 도출**: 자동 변환 vs 수동 변환 분류
7. **리스크 평가**: 마이그레이션 복잡도 및 리스크

## 호환성 수준

| Level | Description | Action |
|-------|-------------|--------|
| **Full** | OpenFrame에서 완전 지원 | 변환 불필요 또는 자동 변환 |
| **Partial** | 일부 기능 제한 | 대체 구현 필요 |
| **Workaround** | 우회 방법 존재 | 코드 수정 필요 |
| **Unsupported** | 미지원 | 재작성 또는 대체 기술 |

## 마이그레이션 체크리스트

### COBOL 마이그레이션
- [ ] COBOL 벤더 식별 (IBM/Fujitsu/표준)
- [ ] CICS/DB2/IMS 인터페이스 매핑
- [ ] AIM/DB DML → SQL/VSAM 변환 계획
- [ ] COPYBOOK 의존성 해석
- [ ] ofcbppf 전처리 필요 여부
- [ ] OFCOBOL 컴파일 테스트

### JCL 마이그레이션
- [ ] JCL 문법 호환성 확인
- [ ] Dataset 마이그레이션 계획 (dsmigin)
- [ ] VSAM DEFINE → OpenFrame VSAM
- [ ] 유틸리티 프로그램 호환성
- [ ] AIMPED → OpenFrame DB adapter
- [ ] TJES 배치 설정

### 온라인 마이그레이션
- [ ] CICS→OSC / IMS→OSI / AIM→AIM 매핑
- [ ] BMS MAP → OpenFrame MAP
- [ ] 트랜잭션 정의
- [ ] TACF 보안 설정
- [ ] 통합 테스트

## 참조 자료

### 제품 매뉴얼
- `uploads/manuals/` (19개 제품, 245+ PDF)
- `docs/specs/XSP/` (Fujitsu XSP 사양서)

### Capability 데이터
- `app/api/legacy_modernization/capabilities/products.json`
- `app/api/legacy_modernization/capabilities/_base.json`

### API 엔드포인트
- `POST /api/v1/legacy/analyze` - 자동 분석 파이프라인
- `GET /api/v1/legacy/products` - 지원 제품 목록

## 출력 형식

```markdown
## OpenFrame Migration Assessment

### Source Analysis
- Platform: [IBM MVS / Fujitsu XSP]
- Language: [COBOL/JCL/ASM/MAP]
- Vendor Features: [CICS/DB2/IMS/AIM-DB]

### Target Product
- Product: [OpenFrame product name]
- Version: [recommended version]

### Compatibility Matrix
| Feature | Support Level | Effort | Notes |
|---------|-------------|--------|-------|

### Migration Steps
1. [Step-by-step migration procedure]

### Risk Assessment
| Risk | Severity | Mitigation |
|------|----------|-----------|

### Estimated Effort
- Automatic Conversion: N%
- Manual Conversion: N%
- Rewrite Required: N%
```

$ARGUMENTS에 파일 경로가 포함된 경우 파일을 읽어 자동 분석합니다. 질문인 경우 적절한 OpenFrame 전문 에이전트를 호출합니다.
