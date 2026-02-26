"""ofcode-server: FastAPI server for OpenFrame 7 source code search API.

Provides REST endpoints for searching, indexing, and querying the of7 codebase.
Runs inside Docker with of7 source mounted at /data/of7.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="ofcode-server", version="0.1.0")

# ── Configuration ──
OF7_ROOT = os.environ.get("OF7_ROOT", "/data/of7")
INDEX_PATH = os.environ.get("INDEX_PATH", "/data/of7_index.json")

# ── Global state ──
_index = None
_web_doc_search = None
_rag_service = None


def _load_index():
    global _index
    if not os.path.exists(INDEX_PATH):
        return False
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        _index = json.load(f)
    return True


@app.on_event("startup")
def startup():
    if _load_index():
        nf = len(_index.get("functions", {}))
        ns = len(_index.get("structs", {}))
        nh = len(_index.get("headers", {}))
        print(f"Index loaded: {nf} functions, {ns} structs, {nh} headers")
    else:
        print(f"Warning: Index not found at {INDEX_PATH}. Run /rebuild-index first.")

    # Load web doc index if available
    global _web_doc_search
    from web_doc_service import WebDocSearchService
    _web_doc_search = WebDocSearchService()
    if _web_doc_search.load_index():
        status = _web_doc_search.get_status()
        print(f"WebDoc index loaded: {status['total_pages']} pages, products: {list(status['products'].keys())}")
    else:
        print("WebDoc index not found. Run POST /api/webdoc/crawl to build it.")

    # Connect to Neo4j RAG service
    global _rag_service
    from rag_service import RAGService
    _rag_service = RAGService()
    if _rag_service.connect():
        status = _rag_service.get_status()
        print(f"RAG service connected: {status.get('total_chunks', 0)} chunks in Neo4j")
    else:
        print("RAG service unavailable (Neo4j connection failed). Continuing without RAG.")


# ── Request/Response models ──

class SearchRequest(BaseModel):
    query: str
    module: Optional[str] = ""
    file_type: Optional[str] = "both"
    max_results: Optional[int] = 30


class FunctionRequest(BaseModel):
    function_name: str


class HeaderRequest(BaseModel):
    header_name: str


class ModuleRequest(BaseModel):
    module: str


class CallerRequest(BaseModel):
    function_name: str
    module: Optional[str] = ""


# ── Health check ──

@app.get("/health")
def health():
    return {
        "status": "ok",
        "of7_root": OF7_ROOT,
        "of7_exists": os.path.isdir(OF7_ROOT),
        "index_loaded": _index is not None,
    }


# ── Search endpoints ──

@app.post("/api/search")
def search_of7(req: SearchRequest):
    if not os.path.isdir(OF7_ROOT):
        raise HTTPException(500, f"OF7 root not found: {OF7_ROOT}")

    try:
        regex = re.compile(req.query, re.IGNORECASE)
    except re.error as e:
        raise HTTPException(400, f"Invalid regex: {e}")

    search_base = os.path.join(OF7_ROOT, req.module) if req.module else OF7_ROOT
    if not os.path.isdir(search_base):
        raise HTTPException(404, f"Module path not found: {req.module}")

    extensions = set()
    if req.file_type == "c":
        extensions = {".c"}
    elif req.file_type == "h":
        extensions = {".h"}
    else:
        extensions = {".c", ".h"}

    results = []
    for root, dirs, files in os.walk(search_base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in extensions:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, 1):
                        if regex.search(line):
                            rel = os.path.relpath(fpath, OF7_ROOT).replace("\\", "/")
                            results.append({
                                "file": rel,
                                "line": lineno,
                                "content": line.rstrip()[:200],
                            })
                            if len(results) >= req.max_results:
                                return {"results": results, "truncated": True}
            except (OSError, UnicodeDecodeError):
                continue

    return {"results": results, "truncated": False}


@app.post("/api/module")
def get_module_info(req: ModuleRequest):
    if not _index:
        raise HTTPException(500, "Index not loaded")

    parts = req.module.strip("/").split("/")
    top_module = parts[0]

    mod_info = _index.get("modules", {}).get(top_module)
    if not mod_info:
        available = list(_index.get("modules", {}).keys())
        raise HTTPException(404, f"Module '{top_module}' not found. Available: {available}")

    result = {
        "module": top_module,
        "description": mod_info.get("description", ""),
        "c_files": mod_info.get("c_files", 0),
        "h_files": mod_info.get("h_files", 0),
        "total_files": mod_info.get("total_files", 0),
        "subdirs": mod_info.get("subdirs", []),
        "subdirs_desc": mod_info.get("subdirs_desc", {}),
    }

    # If subdir specified, add detail
    if len(parts) > 1:
        subdir = parts[1]
        subdir_path = os.path.join(OF7_ROOT, *parts)
        if os.path.isdir(subdir_path):
            c_count = len([f for f in os.listdir(subdir_path) if f.endswith(".c")])
            h_count = len([f for f in os.listdir(subdir_path) if f.endswith(".h")])
            sub_subdirs = [d for d in os.listdir(subdir_path)
                           if os.path.isdir(os.path.join(subdir_path, d))]
            result["subdir_detail"] = {
                "name": "/".join(parts),
                "c_files": c_count,
                "h_files": h_count,
                "subdirs": sorted(sub_subdirs),
            }

    return result


@app.post("/api/function")
def get_function_def(req: FunctionRequest):
    if not _index:
        raise HTTPException(500, "Index not loaded")

    funcs = _index.get("functions", {})
    info = funcs.get(req.function_name)

    if not info:
        # Partial match
        matches = [(name, data) for name, data in funcs.items()
                    if req.function_name.lower() in name.lower()]
        if not matches:
            return {"found": False, "message": f"Function '{req.function_name}' not found."}
        if len(matches) > 20:
            return {
                "found": False,
                "message": f"Too many matches ({len(matches)}). Be more specific.",
                "matches": [{"name": m[0], "file": m[1]["file"], "line": m[1]["line"]}
                            for m in matches[:20]],
            }
        if len(matches) == 1:
            req.function_name = matches[0][0]
            info = matches[0][1]
        else:
            return {
                "found": False,
                "matches": [{"name": m[0], "file": m[1]["file"], "line": m[1]["line"]}
                            for m in matches],
            }

    # Read source code around the function
    file_path = os.path.join(OF7_ROOT, info["file"])
    code_lines = []

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            start = max(0, info["line"] - 5)
            end = min(len(all_lines), info["line"] + 30)
            for i in range(start, end):
                code_lines.append({
                    "num": i + 1,
                    "text": all_lines[i].rstrip(),
                    "is_def": i == info["line"] - 1,
                })
        except Exception:
            pass

    return {
        "found": True,
        "name": req.function_name,
        "file": info["file"],
        "line": info["line"],
        "module": info.get("module", ""),
        "code": code_lines,
    }


@app.post("/api/header")
def get_header_api(req: HeaderRequest):
    if not _index:
        raise HTTPException(500, "Index not loaded")

    header_name = req.header_name
    if not header_name.endswith(".h"):
        header_name += ".h"

    headers = _index.get("headers", {})
    info = headers.get(header_name)
    if not info:
        matches = [name for name in headers if header_name.lower() in name.lower()]
        if matches:
            return {"found": False, "suggestions": matches[:10]}
        raise HTTPException(404, f"Header '{header_name}' not found.")

    return {
        "found": True,
        "header": header_name,
        "path": info.get("path", ""),
        "module": info.get("module", ""),
        "functions": info.get("functions", []),
        "structs": info.get("structs", []),
        "defines": info.get("defines", []),
    }


@app.get("/api/architecture")
def get_architecture():
    return {
        "diagram": """\
OpenFrame 7 Architecture - 6-Layer Stack
=========================================

Layer 1: Entry Points (User Programs)
  COBOL programs | JCL scripts | CICS transactions | IMS DLI calls | SQL | TSO commands
  |
  v
Layer 2: Language & Control
  JCL Parser(Yacc/Lex) | COBOL Parser(cob85p) | MVS/MSP/VOS3/XSP dialects
  batch/TJES scheduler | osc/CICS processor | ims/DLI engine
  |
  v
Layer 3: Server / Runtime
  cmsvr(connection mgmt) | dmsvr(data mgmt) | sasvr(security auth)
  uisvr(UI processing) | smlog(system monitor) | oscmgr(CICS mgr) | osiofmgr(OSI mgr)
  |
  v
Layer 4: Data Access (base/ds/)
  dsalc(dataset allocation) -> dsio(dataset I/O) -> dbio(database I/O) -> mqnio(MQ I/O)
  volm(volume mgmt) | sms(storage mgmt) | VSAM/SAM/tsam
  |
  v
Layer 5: Common Services
  memm(memory) | ofcom(logging/config) | saf(security) | spinlock | ttree | smf(monitoring)
  |
  v
Layer 6: Database Backend (base/tdbconnsw/)
  tdbconnsw -- DB Connection Router
  +-- tdbconn_odbc   -> PostgreSQL (migration target)
  +-- tdbconn_tbodbc -> Tibero (ODBC)
  +-- tdbconn_tbr    -> Tibero (native)
  +-- tdbconn_tboci  -> Tibero (OCI)
  +-- tdbconn_ora    -> Oracle (OCI, legacy)

Stats: 5 modules, 94+ subdirs, 5322 C/H files, 269K lines""",
    }


@app.post("/api/callers")
def find_callers(req: CallerRequest):
    if not os.path.isdir(OF7_ROOT):
        raise HTTPException(500, f"OF7 root not found: {OF7_ROOT}")

    pattern = re.compile(r'\b' + re.escape(req.function_name) + r'\s*\(')
    search_base = os.path.join(OF7_ROOT, req.module) if req.module else OF7_ROOT

    if not os.path.isdir(search_base):
        raise HTTPException(404, f"Path not found: {req.module}")

    results = []
    for root, dirs, files in os.walk(search_base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if not fname.endswith((".c", ".h")):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, 1):
                        if pattern.search(line):
                            rel = os.path.relpath(fpath, OF7_ROOT).replace("\\", "/")
                            results.append({
                                "file": rel,
                                "line": lineno,
                                "content": line.rstrip()[:200],
                            })
                            if len(results) >= 20:
                                return {"results": results, "truncated": True}
            except (OSError, UnicodeDecodeError):
                continue

    return {"results": results, "truncated": False}


@app.post("/api/rebuild-index")
def rebuild_index():
    """Rebuild the of7 index from source."""
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from indexer import scan_directory

    if not os.path.isdir(OF7_ROOT):
        raise HTTPException(500, f"OF7 root not found: {OF7_ROOT}")

    index = scan_directory(Path(OF7_ROOT))

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    global _index
    _index = index

    return {
        "status": "ok",
        "modules": len(index.get("modules", {})),
        "functions": len(index.get("functions", {})),
        "structs": len(index.get("structs", {})),
        "headers": len(index.get("headers", {})),
    }


# ── Web Document Endpoints ──

class WebDocSearchRequest(BaseModel):
    query: str
    product: Optional[str] = ""
    top_k: Optional[int] = 5


@app.post("/api/webdoc/search")
def search_webdoc(req: WebDocSearchRequest):
    if _web_doc_search is None:
        raise HTTPException(500, "WebDoc search service not initialized")
    results = _web_doc_search.search(
        query=req.query,
        product=req.product or "",
        top_k=req.top_k or 5,
    )
    return {"results": results, "query": req.query}


class WebDocCrawlRequest(BaseModel):
    product: Optional[str] = ""


@app.post("/api/webdoc/crawl")
async def crawl_webdoc(req: WebDocCrawlRequest = WebDocCrawlRequest()):
    from web_doc_service import crawl_all
    try:
        index = await crawl_all(product=req.product or "")
    except Exception as e:
        raise HTTPException(500, f"Crawl failed: {e}")

    # Reload search index
    if _web_doc_search is not None:
        _web_doc_search.reload()

    return {
        "status": "ok",
        "total_pages": index.total_pages,
        "products": index.products,
        "crawled_at": index.crawled_at,
    }


@app.get("/api/webdoc/status")
def webdoc_status():
    if _web_doc_search is None:
        return {"loaded": False, "total_pages": 0}
    return _web_doc_search.get_status()


# ── RAG (Neo4j Vector Search) Endpoints ──

class RAGSearchRequest(BaseModel):
    query: str
    product: Optional[str] = ""
    top_k: Optional[int] = 3


@app.post("/api/rag/search")
def rag_search(req: RAGSearchRequest):
    if _rag_service is None or not _rag_service.available:
        return {"results": [], "error": "RAG service not available"}
    results = _rag_service.search(
        query=req.query,
        product=req.product or "",
        top_k=req.top_k or 3,
    )
    return {"results": results, "query": req.query}


@app.get("/api/rag/status")
def rag_status():
    if _rag_service is None:
        return {"available": False}
    return _rag_service.get_status()
