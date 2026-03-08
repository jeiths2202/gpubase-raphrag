# Gap Analysis: ims-semantic-search

## Summary

| Metric | Value |
|--------|-------|
| Match Rate | 81.1% (60/74 checkpoints) |
| Critical Gaps | 5 |
| Minor Gaps | 9 |
| Status | Needs iteration |

## Category Scores

| Category | Score | Gaps |
|----------|-------|------|
| Data Models | 13/13 (100%) | 0 |
| Service Core | 8/10 (80%) | 2 - missing depth param, cache size config |
| Router Endpoints | 5/6 (83%) | 1 - error codes not differentiated |
| SSE Events | 4/6 (67%) | 2 - missing total_context_chars, total_tokens |
| CLI Package | 6/6 (100%) | 0 |
| Config Settings | 4/7 (57%) | 3 - missing MAX_LIMIT, MAX_CONTEXT_ISSUES, CACHE_SIZE |
| Error Handling | 4/6 (67%) | 2 - generic 500 for BGE-M3/Neo4j failures |
| Neo4j Filter | 3/4 (75%) | 1 - overly broad 'ims' CONTAINS |
| LLM Integration | 5/6 (83%) | 1 - no timeout differentiation |
| File Parser | 4/4 (100%) | 0 |
| Reference Extraction | 4/4 (100%) | 0 |
| Method Signatures | 2/4 (50%) | 2 - missing depth, Optional return |

## Gap Details

### GAP-01: Missing config settings (Config)
- **Design**: `IMS_SEARCH_MAX_LIMIT`, `IMS_CHAT_MAX_CONTEXT_ISSUES`, `IMS_ISSUE_CACHE_SIZE`
- **Implementation**: Only `IMS_ISSUES_DIR`, `IMS_ISSUES_REMOTE_DIR`, `IMS_SEARCH_DEFAULT_LIMIT`, `IMS_CHAT_MAX_CONTEXT_CHARS`
- **Fix**: Add 3 missing settings to `config.py`

### GAP-02: Error handling uses generic 500 (Router)
- **Design**: 503 for BGE-M3/Neo4j unavailable, 504 for LLM timeout, 400 for invalid ims_id
- **Implementation**: All errors return 500
- **Fix**: Add specific HTTP status codes in router endpoints

### GAP-03: SSE context_loaded missing total_context_chars (SSE)
- **Design**: `context_loaded` event should include `total_context_chars`
- **Implementation**: Only `issues_loaded` and `related_loaded`
- **Fix**: Add `total_context_chars` to context_loaded event

### GAP-04: SSE done missing total_tokens (SSE)
- **Design**: `done` event should include `total_tokens`
- **Implementation**: Only `conversation_id`
- **Fix**: Count tokens during streaming and include in done event

### GAP-05: get_related_issues missing depth parameter (Service)
- **Design**: `depth` parameter for multi-hop traversal
- **Implementation**: Fixed 1-depth only
- **Fix**: Add optional `depth` parameter (default=1)

### GAP-06: Neo4j filter too broad (Neo4j)
- **Design**: Specific IMS issue document filtering
- **Implementation**: `toLower(d.filename) CONTAINS 'ims'` matches non-issue docs
- **Fix**: Change to `CONTAINS 'ims_issue'` or remove fallback

### GAP-07: Cache size not configurable (Service)
- **Design**: Configurable cache size via settings
- **Implementation**: Hardcoded 500
- **Fix**: Use `IMS_ISSUE_CACHE_SIZE` from config

### GAP-08: summarize_issue lacks 503/504 differentiation (Router)
- **Design**: 503 when LLM unavailable, 504 on timeout
- **Implementation**: Returns None → 404
- **Fix**: Propagate specific exceptions from LLM calls

### GAP-09-14: Minor gaps in method signatures, LLM timeout config, search limit validation
- Various minor alignment issues between design and implementation
- See iteration fixes below

## Recommendation

Proceed with `/pdca iterate` to fix all 14 gaps. Primary focus on:
1. Config settings (GAP-01) - foundation for other fixes
2. Error handling (GAP-02, GAP-08) - user experience
3. SSE event fields (GAP-03, GAP-04) - API completeness
