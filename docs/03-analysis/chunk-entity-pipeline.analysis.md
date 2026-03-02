# Gap Analysis: chunk-entity-pipeline

> **Design**: `docs/02-design/features/chunk-entity-pipeline.design.md` (v1.0)
> **Date**: 2026-02-27
> **Match Rate**: **92%**

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Module Structure (Design §3) | 95% | OK |
| Data Model (Design §2) | 95% | OK |
| Cypher Queries (Design §5) | 98% | OK |
| CLI Arguments (Design §8) | 78% | WARN |
| Knowledge Graph Service (Design §4) | 98% | OK |
| Entity Normalization (Design §6) | 95% | OK |
| Error Handling (Design §7) | 75% | WARN |
| Verification Scenarios (Design §10) | 100% | OK |
| **Overall** | **92%** | **PASS** |

---

## Verification Scenarios Results

### V-1: 孤立Chunk削減率
- **Target**: orphan_pct < 20%
- **Actual**: orphan_pct = **0.1%** (51/42,596)
- **Result**: FAR EXCEEDS target

### V-2: osctdlrm検証
- Entity found: `osctdlrm`, type=command, confidence=0.95, source=pipeline_v1
- Connected chunks: **14** (up from 0)
- **Result**: PASS

### V-3: 冪等性検証
- Second run: new_entities=0, new_mentions=0
- **Result**: PASS (MERGE guarantees idempotency)

### V-4: 既存データ保全
- Pre-existing entities (source != pipeline_v1): preserved
- **Result**: PASS

---

## Pipeline Results

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Connected Chunks | 3,437 (8.1%) | 42,545 (99.9%) | **+39,108** |
| Orphan Chunks | 39,159 (91.9%) | 51 (0.1%) | **-99.9%** |
| Entity Nodes | 3,211 | 13,450 | **+10,239** |
| MENTIONS Relations | 9,606 | 476,215 | **+466,609** |
| Summary Dict Size | — | 17,489 | — |

### New Entity Type Distribution (pipeline_v1)

| Type | Count |
|------|-------|
| config | 4,454 |
| command | 2,823 |
| concept | 1,934 |
| error_code | 1,016 |
| product | 8 |
| technology | 4 |

---

## Missing Items (Design ○, Implementation ×)

| # | Item | Section | Impact | Notes |
|---|------|---------|--------|-------|
| 1 | `--skip-summary` CLI arg | §8 | Low | デバッグ用、必須でない |
| 2 | `--skip-patterns` CLI arg | §8 | Low | デバッグ用、必須でない |
| 3 | `--neo4j-uri/user/pass` CLI args | §8 | Low | .env使用で代替 |
| 4 | Neo4j timeout retry (3x backoff) | §7 | Medium | 実運用では有用 |
| 5 | Neo4j deadlock retry | §7 | Medium | 実運用では有用 |
| 6 | ABEND error pattern | §3.3 | Low | KG serviceに存在 |
| 7 | TmaxSoft product patterns | §3.3 | Low | KG serviceに存在 |
| 8 | JAPANESE_PATTERNS CONFIG | §4.2 | Low | 設定用語の日本語パターン |

## Added Items (Design ×, Implementation ○) — 全てPositive

| # | Item | File | Impact |
|---|------|------|--------|
| 1 | `--verify ENTITY` CLI arg | batch_extract.py | Entity接続検証機能 |
| 2 | Token-based O(1) matching | pattern_extractor.py | **85x高速化** |
| 3 | Non-ASCII key separation | pattern_extractor.py | 日本語キー処理最適化 |
| 4 | Smart skip pointer | batch_extract.py | 無限ループ防止 |
| 5 | ETA progress display | batch_extract.py | UX向上 |
| 6 | `verify_entity()` method | neo4j_writer.py | 検証支援 |
| 7 | `get_entity_type_distribution()` | neo4j_writer.py | 統計出力 |
| 8 | Chunk.id index creation | Neo4j DB | **154x書き込み高速化** |

## Changed Items (Design ≠ Implementation)

| # | Item | Design | Implementation | Impact |
|---|------|--------|---------------|--------|
| 1 | Neo4j driver | AsyncGraphDatabase | GraphDatabase (sync) | CLI用途に適切 |
| 2 | MERGE_BATCH_SIZE | 100 | 500 | Positive (5x) |
| 3 | INTER_BATCH_DELAY | 0.1s | 0.01s | Positive (10x) |
| 4 | Summary matching | O(17K) linear | O(200) set intersection | **Positive (85x)** |
| 5 | ACRONYM type | 別EntityType | "concept"に統一 | EntityType enum制約 |

---

## Recommended Actions

### 即座に対応不要 (Match Rate ≥ 90%)

Missing itemsは全てLow〜Medium impactで、パイプラインの中核機能は完全に動作している。

### 将来的な改善候補
1. **Neo4j retry logic** (Medium) — 大規模本番環境でのネットワーク不安定時に有用
2. **--skip-summary/--skip-patterns** (Low) — パフォーマンス分析時のデバッグ用
3. **追加regex patterns** (Low) — JCL keywords, ABEND, TmaxSoft products

### Design Document更新推奨
- BATCH_SIZE: 100 → 500
- INTER_BATCH_DELAY: 0.1s → 0.01s
- トークンベース高速化の記述追加
- `--verify` CLI引数の記述追加
- Chunk.id index要件の記述追加
