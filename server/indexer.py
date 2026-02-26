#!/usr/bin/env python3
"""Build OpenFrame 7 codebase index for OpenFrame Code CLI.

Scans of7/ directory to extract function definitions, struct definitions,
header APIs, and module structure into of7_index.json.

Usage:
    python build_of7_index.py [--of7-root /path/to/of7]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Regex patterns for C code extraction
RE_FUNC_DEF = re.compile(
    r'^(?:static\s+)?(?:inline\s+)?'
    r'(?:(?:unsigned|signed|const|volatile|struct|enum)\s+)*'
    r'(?:void|int|char|long|short|float|double|size_t|ssize_t|int32_t|int64_t|uint32_t|uint64_t'
    r'|DBIO_\w+|DS_\w+|OF_\w+|SAF_\w+|TDBCONN_\w+|\w+_t)\s*\*?\s+'
    r'(\w+)\s*\(',
    re.MULTILINE
)

RE_FUNC_DEF_SIMPLE = re.compile(
    r'^(\w[\w\s\*]+?)\s+(\w+)\s*\([^;]*$',
    re.MULTILINE
)

RE_STRUCT_DEF = re.compile(
    r'(?:typedef\s+)?struct\s+(\w+)',
    re.MULTILINE
)

RE_FUNC_DECL = re.compile(
    r'^\s*(?:extern\s+)?(?:(?:unsigned|signed|const|volatile|struct|enum)\s+)*'
    r'(?:\w+)\s*\*?\s+(\w+)\s*\([^)]*\)\s*;',
    re.MULTILINE
)

RE_DEFINE = re.compile(
    r'^#define\s+(\w+)',
    re.MULTILINE
)

# Module descriptions from codemap.html
MODULE_INFO = {
    "base": {
        "description": "OpenFrame 핵심 런타임. 공유 인프라, 파서, 데이터 저장소, 서버, 파일 핸들러, 유틸리티",
        "subdirs_desc": {
            "include": "98개 헤더 파일 - 핵심 데이터 모델, 인터페이스, 모듈 간 계약 정의",
            "parser": "JCL, COBOL85, MSP, MVS, VOS3, XSP 방언 파서 (Yacc/Lex 기반)",
            "ds": "데이터 저장소 - ams, dbio, dsio, dsalc, mqnio, volm, sms",
            "server": "서버 프로세스 - cmsvr(연결), dmsvr(데이터), sasvr(보안), uisvr(UI)",
            "fh": "파일 핸들러 - TB, COBOL, DB2, C++, PL/I",
            "common": "공통 라이브러리 - memm(메모리), ofcom(로깅/설정), smf(모니터링)",
            "tdbconnsw": "DB 연결 스위치 - PostgreSQL/Tibero/Oracle 드라이버 전환",
            "analysis": "코드 분석 도구 - adl2xml, cob85info, cobinfo, schinfo",
            "saf": "보안 인증 프레임워크 (SAF)",
            "sort": "정렬 엔진 (ProSort)",
            "adjust": "문자 코드 변환 (EBCDIC/SJIS)",
            "tool": "데이터셋 관리 도구 - dscopy, dscreate, dsdelete, dslist 등",
            "cobsw": "COBOL 스위치/어댑터",
            "config": "런타임 설정 관리",
            "console": "콘솔 인터페이스",
            "cpm": "Copy Member 관리",
            "dist": "분산 처리",
            "errcode": "에러 코드 정의",
            "errdoc": "에러 문서",
            "make": "빌드 시스템 규칙 (rules.dir, rules.lib, rules.svr)",
            "msgcode": "메시지 코드 정의",
            "ofcee": "언어 환경 지원",
            "scripts": "스크립트 유틸리티",
            "tsys": "시스템 유틸리티",
            "vtam": "VTAM 네트워크 통신",
            "api3270": "3270 터미널 API",
        },
    },
    "batch": {
        "description": "배치 처리 시스템. JCL 실행, TJES 작업 스케줄링, TSO 에뮬레이션, 출력 관리",
        "subdirs_desc": {
            "tjes": "작업 스케줄러 - jmsvr, jschd",
            "tso": "TSO 에뮬레이션",
            "output": "출력 관리 - jmcliout, pmsvr",
            "common": "공통 컴포넌트 - 이벤트, 리더",
            "tool": "JCL 분석, TJES 관리 도구",
            "ulib": "사용자 호출 라이브러리",
            "util": "정렬/파일 유틸리티",
            "sdm": "XSP 유틸리티",
        },
    },
    "ims": {
        "description": "IMS 계층형 데이터베이스 시스템. DLI 인터페이스, HIDB 엔진, DB/DC 통신",
        "subdirs_desc": {
            "hidb": "HIDB 코어 엔진",
            "dli": "데이터 언어 인터페이스 (DLI)",
            "dbdc": "DB/DC CICS 연동",
            "imsdc": "IMS 데이터 통신",
            "tool": "생성 도구 - acbgen, dbdgen, psbgen",
            "util": "DFS 유틸리티",
            "common": "IMS 공유 컴포넌트",
        },
    },
    "osc": {
        "description": "CICS 온라인 트랜잭션 처리 에뮬레이션. 75개+ CICS 라이브러리, 게이트웨이, 서버",
        "subdirs_desc": {
            "lib": "75개+ CICS 패키지 라이브러리",
            "svr": "OSC 서버 프로세스",
            "gw": "3270 게이트웨이, 웹서비스 게이트웨이",
            "tool": "관리/빌드/전처리 도구",
            "cicsinc": "CICS 전용 헤더",
            "dvt": "데모/테스트 환경",
            "ivp": "설치 검증 프로그램",
        },
    },
    "osi": {
        "description": "OpenFrame 시스템 인터페이스. 시스템 수준 통합, 메시지 큐, 이벤트 관리",
        "subdirs_desc": {
            "lib": "40개+ OSI 모듈",
            "server": "OSI 서버 프로세스",
            "gw": "3270 게이트웨이",
            "tool": "부팅/빌드/이벤트 관리 도구",
            "install": "설치 및 설정",
        },
    },
}


def scan_directory(of7_root):
    """Scan of7 directory and build index."""
    index = {
        "meta": {
            "of7_root": str(of7_root),
            "version": "1.0",
        },
        "modules": {},
        "functions": {},
        "structs": {},
        "headers": {},
    }

    of7_path = Path(of7_root)

    # Scan each top-level module
    for module_name in ["base", "batch", "ims", "osc", "osi"]:
        module_path = of7_path / module_name
        if not module_path.exists():
            continue

        # Get subdirectories
        subdirs = sorted([
            d.name for d in module_path.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ])

        # Count files
        c_files = list(module_path.rglob("*.c"))
        h_files = list(module_path.rglob("*.h"))

        module_info = MODULE_INFO.get(module_name, {})
        index["modules"][module_name] = {
            "description": module_info.get("description", ""),
            "subdirs": subdirs,
            "subdirs_desc": module_info.get("subdirs_desc", {}),
            "c_files": len(c_files),
            "h_files": len(h_files),
            "total_files": len(c_files) + len(h_files),
        }

        # Scan header files for API declarations
        for h_file in h_files:
            rel_path = str(h_file.relative_to(of7_path)).replace("\\", "/")
            header_name = h_file.name

            try:
                content = h_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            funcs = RE_FUNC_DECL.findall(content)
            structs = RE_STRUCT_DEF.findall(content)
            defines = [m for m in RE_DEFINE.findall(content)
                       if not m.startswith("_") and len(m) > 3]

            if header_name not in index["headers"] or len(funcs) > 0:
                index["headers"][header_name] = {
                    "path": rel_path,
                    "module": module_name,
                    "functions": funcs[:50],  # limit
                    "structs": structs[:30],
                    "defines": defines[:30],
                }

            # Register structs
            for s in structs:
                if len(s) > 2 and s not in ("__cplusplus",):
                    index["structs"][s] = {
                        "file": rel_path,
                        "module": module_name,
                    }

        # Scan C files for function definitions
        for c_file in c_files:
            rel_path = str(c_file.relative_to(of7_path)).replace("\\", "/")

            try:
                content = c_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = content.split("\n")
            skip_names = {"if", "for", "while", "switch", "return", "main", "else", "do", "sizeof", "typeof"}

            for line_no, line in enumerate(lines, 1):
                line_stripped = line.strip()
                # Skip comments, preprocessor, blank lines
                if not line_stripped or line_stripped.startswith(("//", "/*", "*", "#")):
                    continue

                # Pattern 1: Single-line definition "type func_name(...)"
                if "(" in line_stripped and not line_stripped.endswith(";"):
                    m = RE_FUNC_DEF.match(line_stripped)
                    if m:
                        func_name = m.group(1)
                        if len(func_name) > 2 and func_name not in skip_names:
                            index["functions"][func_name] = {
                                "file": rel_path,
                                "line": line_no,
                                "module": module_name,
                            }
                            continue

                # Pattern 2: Function name at start of line with '(' - return type on previous line
                # e.g., previous line: "int" or "static int", current line: "dbio_open(...)"
                m2 = re.match(r'^(\w+)\s*\(', line_stripped)
                if m2 and not line_stripped.endswith(";"):
                    func_name = m2.group(1)
                    if len(func_name) > 2 and func_name not in skip_names:
                        # Check previous non-empty line looks like a return type
                        prev_idx = line_no - 2
                        while prev_idx >= 0 and not lines[prev_idx].strip():
                            prev_idx -= 1
                        if prev_idx >= 0:
                            prev = lines[prev_idx].strip()
                            # Previous line should be a type (short, no parens, no semicolons)
                            if (prev and len(prev) < 60 and "(" not in prev
                                    and ";" not in prev and not prev.startswith(("//", "/*", "*", "#", "{", "}"))):
                                index["functions"][func_name] = {
                                    "file": rel_path,
                                    "line": line_no,
                                    "module": module_name,
                                }

    return index


DEFAULT_OUTPUT_DIR = Path.home() / ".ofcode"


def main():
    parser = argparse.ArgumentParser(
        description="Build OpenFrame 7 codebase index for ofcode CLI",
        epilog="Example: ofcode-build-index --of7-root /home/user/of7",
    )
    parser.add_argument(
        "--of7-root",
        required=True,
        help="Path to of7 source root (required)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=f"Output index file path (default: {DEFAULT_OUTPUT_DIR / 'of7_index.json'})",
    )
    args = parser.parse_args()

    of7_root = Path(args.of7_root).resolve()
    if not of7_root.exists():
        print(f"Error: of7 root not found: {of7_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {of7_root}...")
    index = scan_directory(of7_root)

    # Summary
    print(f"  Modules: {len(index['modules'])}")
    print(f"  Functions: {len(index['functions'])}")
    print(f"  Structs: {len(index['structs'])}")
    print(f"  Headers: {len(index['headers'])}")

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = DEFAULT_OUTPUT_DIR / "of7_index.json"

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    size_kb = output_path.stat().st_size / 1024
    print(f"  Index written to {output_path} ({size_kb:.1f} KB)")
    print(f"  of7_root saved: {of7_root}")
    print(f"\n  Now run: ofcode --openframe")


if __name__ == "__main__":
    main()
