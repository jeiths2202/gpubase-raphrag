# Plan: Legacy HOST & OpenFrame Claude Code Agents

**Feature**: legacy-host-openframe-agents
**Phase**: Plan → Do (직접 구현)
**Date**: 2026-02-18
**Priority**: High (Legacy Modernization Intelligence Platform 지원)

---

## 1. Overview

### 1.1 Goal
Legacy HOST 메인프레임 코드(COBOL, JCL, ASM, MAP)와 TmaxSoft OpenFrame 제품에 대한 Claude Code 전문 에이전트 및 슬래시 커맨드를 생성.

### 1.2 Background
- KMS Legacy Modernization Platform은 11개 백엔드 Agent로 COBOL/JCL/MAP/ASM 분석 수행
- Claude Code 사용자가 직접 레거시 코드를 분석하거나 OpenFrame 마이그레이션 질문 가능
- `docs/specs/XSP/` Fujitsu XSP 사양서 + `uploads/manuals/` 19개 제품 PDF 참조

### 1.3 Scope
- Legacy HOST 전문 에이전트 4개 (COBOL, JCL, ASM, MAP)
- TmaxSoft OpenFrame 전문 에이전트 4개 (Batch, Online, COBOL, Infra)
- 슬래시 커맨드 2개 (legacy-analyze, openframe-migrate)

---

## 2. Deliverables

### 2.1 Claude Code Agents (`.claude/agents/`)

| Agent | Role | Reference |
|-------|------|-----------|
| `legacy-cobol-expert` | COBOL 소스 분석 (IBM/Fujitsu) | `docs/specs/XSP/02_COBOL_SPEC.md` |
| `legacy-jcl-expert` | JCL 분석 (MVS/XSP) | `docs/specs/XSP/01_JCL_SPEC.md` |
| `legacy-asm-expert` | Assembler 분석 (HLASM/ASSEMBH) | `docs/specs/XSP/03_ASM_SPEC.md` |
| `legacy-map-expert` | BMS/PSAM MAP 화면 분석 | `app/api/legacy_modernization/parsers/map_parser.py` |
| `openframe-batch-expert` | Batch/TJES/JCL 마이그레이션 | `uploads/manuals/MVS_Openframe 7.1*/` |
| `openframe-online-expert` | OSC/OSI/AIM 온라인 시스템 | `uploads/manuals/XSP_Openframe 7.3*/` |
| `openframe-cobol-expert` | OFCOBOL 컴파일러/마이그레이션 | `uploads/manuals/OFCOBOL_4*/` |
| `openframe-infra-expert` | TACF/GW/Base/Manager 인프라 | `uploads/manuals/MVS_Openframe 7.1*/` |

### 2.2 Slash Commands (`.claude/commands/`)

| Command | Description |
|---------|-------------|
| `/legacy-analyze` | Legacy HOST 코드 분석 (COBOL/JCL/ASM/MAP 자동 감지) |
| `/openframe-migrate` | OpenFrame 마이그레이션 호환성 분석 |

---

## 3. Agent Design

### 3.1 Agent Format
```yaml
---
name: agent-name
description: "When to use description with examples"
model: sonnet
memory: project
---
System prompt with domain expertise...
```

### 3.2 Legacy HOST Agent Responsibilities
- **COBOL Expert**: DIVISION 구조, CICS/DB2/IMS/AIM-DB 인터페이스, FILE I/O, COPYBOOK 분석
- **JCL Expert**: JOB/EXEC/DD, AIMPED, PROC, COND/IF, VSAM/GDG, 유틸리티 분석
- **ASM Expert**: 명령어/디렉티브/매크로, 레지스터 사용, SVC, DSECT, 링키지 분석
- **MAP Expert**: BMS DFHMSD/DFHMDI/DFHMDF, PSAM, 필드 속성, 커서 제어 분석

### 3.3 OpenFrame Agent Responsibilities
- **Batch Expert**: TJES, JCL 변환, 배치 엔진, dsmigin/dsmigout, SORT
- **Online Expert**: OSC(CICS 호환), OSI(IMS 호환), AIM(XSP/MSP) 온라인
- **COBOL Expert**: OFCOBOL 컴파일, 벤더 차이(OSVS/ENT/MVS), ofcbppf
- **Infra Expert**: TACF 보안, OFGW, OFManager, Base 설정, 시스템 명령어

---

## 4. Reference Data

### 4.1 Products (products.json)
11개 OpenFrame 제품 × 다중 버전:
- AIM(XSP/MSP): 7.0, 7.1, 7.3
- OSC: 7.0, 7.1, 7.3, 8.0
- OSI: 6.0, 7.0, 7.1
- ASM: 4.0
- COBOL(OSVS/ENT/MVS): 4.0
- Batch: 7.0, 7.1, 7.3
- HiDB: 3.0, 3.3, 7.2
- TACF: 7.0, 7.1

### 4.2 Manual PDFs
- `uploads/manuals/` 19개 제품 디렉토리, 245+ PDF
- `docs/specs/XSP/` Fujitsu XSP 사양서 4개

---

## 5. Implementation
직접 구현 (Do phase). Plan 승인 후 즉시 파일 생성.
