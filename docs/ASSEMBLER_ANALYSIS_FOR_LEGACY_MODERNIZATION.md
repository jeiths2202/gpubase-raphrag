# Assembler Analysis for Legacy Modernization Intelligence Platform

**Date**: 2026-02-18
**Project**: Legacy Modernization Intelligence Platform (11-agent COBOL/JCL/MAP/ASM analysis system)
**Purpose**: Technical reference for Assembler (ASM) code analysis capabilities

---

## Overview

This document connects the comprehensive Fujitsu assembler research to the KMS Legacy Modernization platform's Assembler (ASM) analysis capabilities.

### ASM Module Scope

The Legacy Modernization Intelligence Platform's **11-agent system** includes specific analysis for:
1. **COBOL programs** - Primary business logic language
2. **JCL (Job Control Language)** - Batch execution control
3. **MAP (screen definitions)** - CICS terminal I/O
4. **Assembler (ASM)** - Low-level system utilities and performance-critical code

---

## Assembler Code Patterns in Mainframe Systems

### Where Assembler Code Appears

In enterprise mainframe systems migrating with OpenFrame, Assembler code is typically found in:

1. **System Utilities** (10-15% of codebase)
   - File I/O handlers and device drivers
   - Performance-critical routines
   - System service wrappers

2. **Linkage Modules** (5-10%)
   - Language interop (COBOL ↔ Assembler)
   - Dynamic library loaders
   - Runtime system calls

3. **Legacy Communication Handlers** (5%)
   - Network protocol adapters
   - Message queue integration
   - Terminal I/O processing

4. **Data Processing Routines** (5%)
   - Cryptographic functions
   - Data validation/transformation
   - Custom compression algorithms

### Code Complexity Indicators

| Pattern | Complexity | Migration Risk |
|---------|----------|-----------------|
| **BSAM Sequential I/O** | Low | Low (mappable to modern file APIs) |
| **Register-heavy arithmetic** | Medium | Medium (needs verification) |
| **Dynamic memory management** | High | High (needs refactoring) |
| **Direct hardware access** | Very High | Very High (platform-specific) |
| **Inline system SVCs** | Medium | Medium (map to OS calls) |

---

## Assembler Analysis Capabilities for KMS Platform

### 1. Instruction Set Analysis

**What to Detect**:

- **Load/Store Instructions**: L, LR, ST, STH, LA (basic addressability)
- **Arithmetic Instructions**: A, S, M, D (verify overflow handling)
- **Logical Instructions**: N, O, X (bitwise operations)
- **Branch Instructions**: B, BC, BALR, BASSM (control flow)
- **Advanced Instructions**: Advanced/extended instructions requiring special handling

**Why It Matters**:
- Determines CPU architecture requirements for migration
- Identifies performance-critical code patterns
- Detects deprecated instruction usage

**Example Analysis**:
```
Detected Instructions:
  L    R5,MYADDR      → Standard load (safe)
  BALR R14,R15        → Branch and link (linkage handling)
  SVC  9              → Supervisor call (OS-dependent, requires mapping)
```

### 2. Register Usage Analysis

**Critical Registers**:

| Register | Purpose | Risk Level | Recommendation |
|----------|---------|-----------|-----------------|
| R13 | Save area pointer | Medium | Verify proper save/restore |
| R14 | Return address | Medium | Critical for linkage; validate |
| R15 | Entry/return code | Medium | Ensure proper cleanup |
| R2-R12 | General purpose | Low | Verify preservation |

**Detection Points**:
- Register initialization
- Register preservation/restoration
- Return address handling
- Save area management

**Example Finding**:
```
RISK: Register R14 used without proper BALR/BASSM linkage
      Line 45: "BR R14" without prior save/restore
      Recommendation: Verify caller/callee contract
```

### 3. Macro Analysis

**Common Macros to Track**:

| Macro | Category | Purpose | Migration Impact |
|-------|----------|---------|-----------------|
| **OPEN/CLOSE** | File I/O | Open/close file | High - needs translation to file APIs |
| **READ/WRITE** | File I/O | Record operations | High - sequential I/O mapping |
| **GET/PUT** | File I/O | Queued I/O | High - automatic buffering |
| **SAVE/RESTORE** | Linkage | Register preservation | Medium - varies by method |
| **GETMAIN/FREEMAIN** | Memory | Allocation | Medium - map to malloc/free |
| **SVC** | System | Supervisor call | High - OS-dependent mapping |

**Detection Example**:
```
Macros Detected:
  OPEN MYFILE         → File operation (BSAM/QSAM)
  READ MYFILE,1       → Sequential read
  CLOSE MYFILE        → File closure

Impact: File I/O operations detected - requires sequential file API mapping
```

### 4. Linkage Convention Analysis

**Linkage Patterns**:

```
Pattern 1: Standard BAL-Style Linkage
  STM R14,R12,12(R13)    → Save caller's registers
  ST R13,4(R15)          → Save caller's save area pointer
  ST R15,8(R13)          → Link save areas
  LR R13,R15             → Update current save area
  ...code...
  LM R14,R12,12(R13)     → Restore caller's registers
  BR R14                 → Return to caller

Pattern 2: Register-Based Subroutine
  Register Parameters: R1 = parameter address
  Register Return: R15 = return code

Migration: Translate to standard calling conventions (C linkage, stack-based)
```

**Analysis Output**:
```
Linkage Convention Detected: BAL-Style (Standard Mainframe)
Parameters: Via R1 register
Return Code: Via R15 register
Save Area: Dynamically allocated
Complexity: Medium - standard conversion available
```

### 5. Data Definition Analysis

**Data Declarations**:

| Declaration | Type | Purpose | Analysis |
|-------------|------|---------|----------|
| `DC F'123'` | Fullword | 4-byte constant | Verify alignment, endianness |
| `DC C'TEXT'` | Character | ASCII/EBCDIC string | Identify encoding issues |
| `DC X'FF'` | Hexadecimal | Binary constants | Verify interpretation |
| `DS 100C` | Storage | Work buffer | Estimate memory usage |
| `EQU 1000` | Constant | Symbolic value | Identify magic numbers |

**Example**:
```
Data Definitions Detected:
  CONST1   DC F'123'         → Fullword integer
  BUFFER   DS 256C           → 256-byte work area
  OFFSET   EQU 100           → Symbolic constant

Analysis:
  - Total static data: ~260 bytes
  - Alignment requirements: Even addresses (standard)
  - Magic numbers: 1 detected (100) - consider externalization
```

### 6. Control Flow Analysis

**Branch Patterns**:

- **Unconditional**: `B LABEL` (always branch)
- **Conditional**: `BC 4,LABEL` (branch on condition code)
- **Subroutine Call**: `BALR R14,R15` (branch and link register)
- **Return**: `BR R14` (branch to register)

**Analysis for Complexity**:
```
Control Flow Patterns:
  - Unconditional branches: 3
  - Conditional branches: 8
    - Compare/branch pairs: 5 (moderate complexity)
    - Loop constructs: 2
  - Subroutine calls: 4
  - Return statements: 4

Complexity Score: MEDIUM
Recommendation: Straightforward translation, standard control flow patterns
```

---

## Integration with KMS Agents

### ASM Agent Responsibilities

The **ASM (Assembler) Agent** in the 11-agent system analyzes:

1. **Instruction Complexity**
   - Identifies complex instruction sequences
   - Detects deprecated/obsolete instructions
   - Flags performance-critical sections

2. **Linkage Compatibility**
   - Validates register save/restore
   - Checks parameter passing conventions
   - Verifies return address handling

3. **Resource Usage**
   - Memory allocation patterns
   - File descriptor management
   - System resource references

4. **Portability Risks**
   - Platform-specific code
   - Direct hardware access
   - OS-dependent system calls

### Agent Output Format

```json
{
  "analysis_type": "assembler",
  "file": "UTILITY01.asm",
  "version": "1.0",
  "summary": {
    "total_instructions": 247,
    "complexity_score": 6.5,
    "estimated_effort_days": 3
  },
  "findings": {
    "critical": [
      {
        "type": "register_usage",
        "risk": "R14 used without linkage context",
        "line": 45,
        "recommendation": "Add BALR/BASSM or document calling convention"
      }
    ],
    "warnings": [
      {
        "type": "macro_usage",
        "pattern": "OPEN/READ/CLOSE",
        "impact": "File I/O operations - requires API mapping",
        "count": 3
      }
    ],
    "info": [
      {
        "type": "instruction_pattern",
        "pattern": "Standard BAL linkage",
        "portability": "HIGH"
      }
    ]
  },
  "recommendations": [
    "Refactor BSAM I/O to modern file APIs",
    "Verify register save area structure",
    "Map SVC 9 to OS termination call"
  ]
}
```

---

## Code Pattern Reference

### Pattern 1: File I/O with BSAM

**Original Assembler**:
```
MYFILE   DCB DSORG=PS,MACRF=(R,W),RECFM=FB,LRECL=80
         OPEN MYFILE
         READ MYFILE,1
         CLOSE MYFILE
```

**Migration Path**:
```
Fujitsu/OpenFrame → Modern Platform

1. Map DCB parameters to file operation context
   DSORG=PS → Sequential file type
   RECFM=FB → Fixed-length blocked records
   LRECL=80 → Record length

2. Translate OPEN → fopen() or file.open()

3. Translate READ → fread() or file.read()

4. Translate CLOSE → fclose() or file.close()

Risk Level: LOW-MEDIUM
Effort: 1 day per occurrence
```

### Pattern 2: Subroutine Linkage

**Original Assembler**:
```
MYSUB    STM R14,R12,12(R13)
         ST R13,4(R15)
         LR R13,R15
         ST R15,8(R13)
         LA R15,SAVEAREA
         ... code ...
         LM R14,R12,12(R13)
         BR R14
```

**Migration Path**:
```
Fujitsu/OpenFrame → C/Modern Language

1. Identify parameter passing via R1
2. Identify return code in R15
3. Translate register frame to stack frame
4. Convert to standard calling convention (e.g., C linkage)
5. Allocate save area on stack automatically

Risk Level: MEDIUM
Effort: 2-3 days per subroutine
Testing: Critical - linkage errors cause crashes
```

### Pattern 3: Supervisor Call (SVC)

**Original Assembler**:
```
         SVC 9              ; Program termination
         or
         SVC 19             ; File open (example)
```

**Migration Path**:
```
Fujitsu/OpenFrame SVC → OS API

SVC 9       → exit(0) or equivalent
SVC 19      → fopen() or equivalent
SVC custom  → Map to OpenFrame equivalent

1. Identify SVC number
2. Determine OS service being requested
3. Map to modern equivalent
4. Handle return code translation

Risk Level: MEDIUM-HIGH (OS-dependent)
Effort: 1-2 days per SVC type
Testing: Required - OS behavior may differ
```

---

## Recommendations for ASM Analysis

### Quick Assessment (30 minutes)

1. **Count Instructions**: Identify instruction types
2. **Detect Macros**: Find OPEN/CLOSE/READ/WRITE patterns
3. **Check Linkage**: Validate register preservation
4. **Estimate Size**: Lines of code ÷ 200 = rough effort estimate

### Detailed Analysis (2-4 hours)

1. **Register Flow**: Trace R1, R13, R14, R15 usage
2. **Data Structures**: Identify all DS/DC declarations
3. **Control Flow**: Map all branches and loops
4. **External References**: Identify called subroutines and system services
5. **Complexity**: Calculate based on instruction patterns and branch density

### Migration Planning (1-2 days)

1. **Refactoring Strategy**: Group similar patterns
2. **Testing Plan**: Define test cases per pattern
3. **Resource Allocation**: Assign developers by pattern type
4. **Risk Mitigation**: Plan for critical sections
5. **Timeline**: Estimate effort and dependencies

---

## References

### Comprehensive Research
- File: `FUJITSU_ASSEMBLER_RESEARCH.md` (29 reference sources, ~7000 words)
- Covers: Fujitsu BS2000 ASSEMBH, FACOM M-Series, IBM HLASM, differences, integration

### Quick Reference
- File: `ASSEMBLER_QUICK_REFERENCE.md` (summary, tables, patterns)
- Use for: Quick lookups during analysis

### Official Documentation
1. Fujitsu BS2000 ASSEMBH Reference Manual v1.3
   - https://bs2manuals.ts.fujitsu.com/download/manual/957.1

2. IBM HLASM Language Reference 1.6
   - https://www.ibm.com/docs/en/SSENW6_1.6.0/pdf/asmr1024_pdf.pdf

3. System/360 Assembly (Wikibooks)
   - https://en.wikibooks.org/wiki/360_Assembly

---

## Appendix: ASM Analysis Metrics

### Complexity Scoring

```
Base Score = 0

+ 0.5 per branch instruction
+ 1.0 per macro (OPEN/CLOSE/READ/WRITE)
+ 0.5 per system call (SVC)
+ 0.25 per arithmetic instruction
+ 0.1 per load/store instruction
+ 1.0 per register save/restore sequence
+ 2.0 per unknown instruction
+ 1.5 per self-modifying code pattern

Score 0-2:   LOW complexity
Score 2-5:   MEDIUM complexity
Score 5-8:   HIGH complexity
Score 8+:    VERY HIGH complexity
```

### Effort Estimation

```
Complexity × 0.5 days = Rough migration effort

Example:
  Complexity Score: 6.5
  Estimated Effort: 6.5 × 0.5 = 3.25 days
  With testing and documentation: +50% → ~5 days
```

### Risk Matrix

```
Risk = Complexity × Unknown_Factor × External_Dependencies

LOW:       Score 0-3, standard patterns, single module
MEDIUM:    Score 3-6, common patterns, multiple dependencies
HIGH:      Score 6-9, complex patterns, system-dependent
CRITICAL:  Score 9+, undocumented, hardware-specific
```

---

**Document Purpose**: Integration guide for ASM (Assembler) analysis component of the Legacy Modernization Intelligence Platform

**Last Updated**: 2026-02-18
**Status**: Ready for deployment in analysis agents
