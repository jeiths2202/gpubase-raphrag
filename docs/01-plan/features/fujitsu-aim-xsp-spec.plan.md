# Plan: Fujitsu AIM/XSP Language Specification

**Feature**: fujitsu-aim-xsp-spec
**Phase**: Plan → Completed (Spec documents generated)
**Date**: 2026-02-18
**Priority**: High (Legacy Modernization 11-agent system support)

---

## 1. Overview

### 1.1 Goal
Fujitsu OSIV/XSP 메인프레임의 JCL, COBOL, ASM 문법을 웹 조사하여 파악하고, 체계적인 사양(Spec) 문서로 정리.

### 1.2 Background
- KMS Legacy Modernization Intelligence Platform은 11개 Agent로 COBOL/JCL/MAP/ASM 분석 수행
- Fujitsu XSP는 IBM MVS와 유사하지만 고유한 차이점 존재 (AIM/DB, AIMPED, TSS, JEF encoding 등)
- Agent가 Fujitsu XSP 코드를 정확히 분석하려면 언어별 사양서가 필요

### 1.3 Scope
- OSIV/XSP architecture & subsystems
- JCL XSP syntax (JOB/EXEC/DD + AIMPED)
- COBOL 85/2000/NetCOBOL syntax + AIM/DB DML
- ASSEMBH instruction set, directives, macros, linkage conventions

---

## 2. Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-01 | XSP OS/AIM/DB/AIM/DC architecture 사양서 | Completed |
| FR-02 | JCL XSP syntax specification (AIMPED 포함) | Completed |
| FR-03 | COBOL 85/2000 syntax + AIM/DB DML interface | Completed |
| FR-04 | ASM (ASSEMBH) instruction/directive/macro spec | Completed |
| FR-05 | IBM MVS vs XSP 차이점 정리 | Completed |
| FR-06 | OpenFrame migration considerations per language | Completed |

---

## 3. Deliverables

### 3.1 Output Location
`docs/specs/XSP/`

### 3.2 Documents

| File | Size | Content |
|------|------|---------|
| `README.md` | Index | 전체 사양서 인덱스 + architecture diagram |
| `00_XSP_ARCHITECTURE.md` | ~300 lines | OSIV/XSP, AIM/DB, AIM/DC, GS21, FACOM, encoding |
| `01_JCL_SPEC.md` | ~350 lines | JCL statements, procedures, conditional, utilities |
| `02_COBOL_SPEC.md` | ~400 lines | All divisions, data types, AIM/DB DML, screen handling |
| `03_ASM_SPEC.md` | ~350 lines | Instructions, directives, macros, registers, file I/O |

---

## 4. Research Sources

총 60+ authoritative references:
- Fujitsu 공식 매뉴얼 (BS2000, NetCOBOL, ASSEMBH)
- IPSJ Computer Museum archives
- Fujitsu GlobalServer product pages
- IBM HLASM/z/OS reference (비교 목적)
- TmaxSoft OpenFrame documentation
- Community technical resources (Wikibooks, Qiita, SimoTime)

---

## 5. Key Findings Summary

### 5.1 XSP vs IBM MVS 핵심 차이

| Aspect | XSP | IBM MVS |
|--------|-----|---------|
| Job Management | Native (No JES) | JES2/JES3 |
| TP Monitor | AIM/DC + IDCM | CICS |
| Database | AIM/DB (CODASYL 1977) | DB2/IMS |
| JCL Extension | AIMPED | N/A |
| Char Encoding | JEF EBCDIC | Standard EBCDIC |
| Interactive | TSS | TSO/ISPF |

### 5.2 Compatibility Level

- **COBOL**: HIGH (COBOL 85 표준 호환, AIM/DB DML 제외)
- **ASM**: HIGH (System/370 호환, SVC 번호/system macro 차이)
- **JCL**: MEDIUM-HIGH (JOB/EXEC/DD 호환, AIMPED/XSP-native 차이)

---

## 6. Next Steps

- [ ] Legacy Modernization agents에 XSP spec 반영 (prompt tuning)
- [ ] XSP COBOL → OpenFrame COBOL 변환 패턴 정의
- [ ] AIM/DB DML → SQL 변환 매핑 테이블
- [ ] JEF → Unicode 문자 변환 규칙 정의
