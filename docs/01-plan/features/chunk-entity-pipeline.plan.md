# Plan: Chunk-Entity Pipeline (孤立Chunk Entity自動抽出・接続)

## 1. 概要

### 背景
Neo4jに格納された42,596個のChunkノードのうち、**39,159個（91.9%）がEntityノードに未接続**。
現在のEntity抽出は英語/韓国語パターンのみで、**日本語ドキュメント（OpenFrameマニュアル群）に対応するパターンが完全に欠落**している。

### 現状データ
| 指標 | 値 |
|------|-----|
| 全Chunk数 | 42,596 |
| Entity接続あり | 3,437 (8.1%) |
| **Entity接続なし（孤立）** | **39,159 (91.9%)** |
| 全Entity数 | 3,211 |
| MENTIONS関係数 | 9,606 |
| Entity種別 | ERROR_CODE(2326), COMMAND(336), ACRONYM(277), CONCEPT(168), PROPER_NOUN(77), PERSON(27) |

### 根本原因分析
1. **日本語パターン未定義**: `ENTITY_PATTERNS`に日本語マッチ用正規表現がゼロ
2. **OpenFrame用語の不足**: `osctdlrm`, `dsmigin`, `ofcbppf`等のツール名がCOMMANDパターンに未登録
3. **LLM抽出が未実装**: `_extract_with_llm()`はモック（0.3s sleep + 簡易キャピタル抽出のみ）
4. **バッチ処理パイプライン不在**: 既存Chunkに対する一括Entity抽出・接続スクリプトがない
5. **Summaryベース抽出の未活用**: `uploads/summaries/`に蓄積された構造化知識（コマンド、エラーコード、設定）が直接Entity生成に未活用

### 目標
- 孤立Chunkの**80%以上**にEntity接続を新規作成（39,159→約7,800以下に削減）
- 新規Entity数: **5,000〜10,000個**追加（現在3,211 → 8,000〜13,000）
- 処理時間: 全42,596 Chunk処理を**30分以内**（バッチ、LLM不使用の純パターン抽出）

---

## 2. 機能要件

### FR-1: 日本語Entity抽出パターン追加
`ENTITY_PATTERNS`に以下の日本語パターンを追加:

| EntityType | パターン例 | 抽出対象 |
|-----------|-----------|---------|
| COMMAND | `r'\b(?:osc[a-z]+|tjes[a-z]*|hidb[a-z]*|tacf[a-z]*|ofrm[a-z]*|dsmigin|dsmigout|ofcbppf|idcams)\b'` | osctdlrm, oscmgr, dsmigin等 |
| COMMAND | `r'\b[a-z]{2,}mgr\b'` | 任意の*mgrパターン |
| CONFIG | `r'[A-Z_]{2,}(?:_DIR|_HOME|_BASE|_PATH|_URL|_PORT)\b'` | OPENFRAME_HOME, TMAX_DIR等 |
| CONCEPT_JA | `r'[ァ-ヶー]{3,}(?:・[ァ-ヶー]{2,})*'` | カタカナ技術用語 |
| CONCEPT_JA | `r'(?:共有メモリ|バッチ処理|トランザクション|データセット|リージョン|コンソール|サーバー)'` | 日本語複合語 |
| PRODUCT | `r'\bOpenFrame[/ ]?(?:Base|TJES|OSC|TACF|HIDB|ASM|COBOL)\b'` | 製品名 |
| PRODUCT | `r'\b(?:Tmax|Tibero|JEUS|ProObject|WebtoB)\b'` | TmaxSoft製品 |
| FILE_PATH | `r'\$\{?[A-Z_]+\}?/[a-z_/]+(?:\.[a-z]+)?'` | `${OPENFRAME_HOME}/log/...` |

### FR-2: Summary駆動Entity生成
`uploads/summaries/` の構造化データから直接Entityを生成:

| Summary種別 | Entity Type | 生成方法 |
|------------|------------|---------|
| `commands/*.md` | COMMAND | `## ` 見出しのコマンド名 + サブコマンド |
| `error-codes/*.md` | ERROR_CODE | `-XXXX: DESCRIPTION` パターン |
| `configs/*.md` | CONFIG | パラメータ名 + 設定ファイル名 |
| `glossary/*.md` | ACRONYM/CONCEPT | 用語名 + 正式名称 |
| `concepts/*.md` | CONCEPT | 概念名 |

### FR-3: バッチEntity抽出パイプライン
孤立Chunkに対する一括処理スクリプト:

```
Phase 1: パターンベース抽出 (高速、LLM不要)
  ├─ 日本語+英語+韓国語パターンを全孤立Chunkに適用
  ├─ Summary辞書とのマッチング（完全一致+部分一致）
  └─ 所要時間: ~15分 (42K chunks)

Phase 2: 統計ベース抽出 (中速、LLM不要)
  ├─ TF-IDF重要語抽出 → 頻出3文字以上の連続カタカナ/英単語
  ├─ 既存Entity名との類似度マッチ（編集距離≤2）
  └─ 所要時間: ~10分

Phase 3: LLM抽出 (低速、オプション)
  ├─ Phase 1-2で未抽出のChunkのみ対象
  ├─ vLLM (Qwen) で構造化抽出プロンプト
  └─ 所要時間: ~60分 (バッチAPI)
```

### FR-4: Entity重複排除・正規化
- 大文字/小文字の統一（`tjesmgr` = `TJESMGR` = `Tjesmgr`）
- 略語展開（`TJES` → Entity aliasに `Tmax Job Entry Subsystem` 追加）
- 同義語クラスタリング（`osctdlrm` ↔ `osctdlrmツール` ↔ `TDL共有メモリ削除`）

### FR-5: 増分処理対応
- 新規文書アップロード時にEntity自動抽出
- 既にEntity接続済みのChunkはスキップ
- 進捗トラッキング（処理済みChunk数、新規Entity数、新規MENTIONS数）

---

## 3. 非機能要件

| 項目 | 要件 |
|------|------|
| 処理速度 | Phase 1: 42K chunks / 15分以内 |
| メモリ使用量 | Peak < 2GB (バッチサイズ制御) |
| 冪等性 | 同一スクリプト再実行で重複Entity/関係が発生しない (`MERGE`使用) |
| 可観測性 | 処理進捗ログ (10%ごと)、最終レポート出力 |
| 既存影響 | 既存Entity・MENTIONS関係を変更・削除しない |

---

## 4. 技術設計（概要）

### 4.1 ファイル構成

| ファイル | 役割 | 変更種別 |
|---------|------|---------|
| `app/api/services/knowledge_graph_service.py` | ENTITY_PATTERNS拡張 (日本語+OpenFrame追加) | 修正 |
| `scripts/entity_pipeline/batch_extract.py` | **バッチEntity抽出パイプライン (メイン)** | 新規 |
| `scripts/entity_pipeline/pattern_extractor.py` | 日本語+英語パターンマッチャー | 新規 |
| `scripts/entity_pipeline/summary_extractor.py` | Summary辞書ベースEntity生成 | 新規 |
| `scripts/entity_pipeline/neo4j_writer.py` | Neo4jバッチ書き込み (MERGE) | 新規 |
| `scripts/entity_pipeline/report.py` | 処理結果レポート生成 | 新規 |

### 4.2 処理フロー

```
[batch_extract.py]
    │
    ├─ Step 1: Summary辞書ロード
    │   └─ uploads/summaries/{commands,error-codes,configs,glossary,concepts}/*.md
    │       → entity_dict: Dict[str, EntityInfo]  (~5,000エントリ)
    │
    ├─ Step 2: Neo4j孤立Chunkフェッチ (バッチ500件ずつ)
    │   └─ MATCH (c:Chunk) WHERE NOT (c)-[:MENTIONS]->(:Entity)
    │       RETURN c.id, c.content SKIP $skip LIMIT 500
    │
    ├─ Step 3: パターン抽出
    │   ├─ pattern_extractor.extract(chunk.content)
    │   │   ├─ ENTITY_PATTERNS (英語+日本語+韓国語)
    │   │   ├─ Summary辞書マッチング (完全一致 conf=0.95, 部分一致 conf=0.80)
    │   │   └─ TF-IDF重要語 (conf=0.75)
    │   └─ → List[ExtractedEntity]
    │
    ├─ Step 4: Entity正規化
    │   ├─ 大文字/小文字統一
    │   ├─ 既存Entityとの重複チェック
    │   └─ → List[NormalizedEntity]
    │
    ├─ Step 5: Neo4jバッチ書き込み
    │   ├─ UNWIND $entities AS e
    │   │   MERGE (ent:Entity {name: e.name})
    │   │   ON CREATE SET ent.type = e.type, ent.confidence = e.confidence, ent.created_at = datetime()
    │   │   ON MATCH SET ent.confidence = CASE WHEN e.confidence > ent.confidence THEN e.confidence ELSE ent.confidence END
    │   │   WITH ent, e
    │   │   MATCH (c:Chunk {id: e.chunk_id})
    │   │   MERGE (c)-[:MENTIONS]->(ent)
    │   └─ バッチサイズ: 100 Entity/クエリ
    │
    └─ Step 6: レポート出力
        ├─ 処理Chunk数、新規Entity数、新規MENTIONS数
        ├─ Entity種別分布
        └─ 残存孤立Chunk数 + サンプル
```

### 4.3 Cypher クエリ設計

```cypher
-- 孤立Chunkフェッチ (ページング)
MATCH (c:Chunk)
WHERE NOT (c)-[:MENTIONS]->(:Entity)
RETURN c.id AS id, c.content AS content
ORDER BY c.id
SKIP $skip LIMIT $batch_size

-- バッチEntity作成 + MENTIONS接続 (UNWIND)
UNWIND $batch AS item
MERGE (e:Entity {name: item.name})
ON CREATE SET e.type = item.type,
              e.confidence = item.confidence,
              e.source = 'pipeline_v1',
              e.created_at = datetime()
ON MATCH SET e.confidence = CASE
    WHEN item.confidence > e.confidence THEN item.confidence
    ELSE e.confidence END
WITH e, item
MATCH (c:Chunk {id: item.chunk_id})
MERGE (c)-[:MENTIONS]->(e)

-- 処理結果確認
MATCH (c:Chunk)
OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
RETURN
  count(c) AS total_chunks,
  count(CASE WHEN e IS NOT NULL THEN 1 END) AS connected_chunks,
  count(CASE WHEN e IS NULL THEN 1 END) AS orphan_chunks
```

---

## 5. 実装順序

| Step | 作業内容 | 依存 | 見積り |
|------|---------|------|--------|
| 1 | `knowledge_graph_service.py`: 日本語+OpenFrameパターン追加 | なし | 30分 |
| 2 | `scripts/entity_pipeline/pattern_extractor.py`: パターンマッチャー | Step 1 | 45分 |
| 3 | `scripts/entity_pipeline/summary_extractor.py`: Summary辞書ロード | なし | 30分 |
| 4 | `scripts/entity_pipeline/neo4j_writer.py`: バッチ書き込み | なし | 30分 |
| 5 | `scripts/entity_pipeline/batch_extract.py`: メインパイプライン | Step 2-4 | 45分 |
| 6 | パイプライン実行 + レポート確認 | Step 5 | 30分 |
| 7 | 検証: osctdlrm等の具体例でEntity接続確認 | Step 6 | 15分 |

---

## 6. 検証基準

| ID | 検証項目 | 合格基準 |
|----|---------|---------|
| V-1 | 孤立Chunk削減率 | 91.9% → **20%以下** |
| V-2 | 新規Entity数 | **+5,000以上** (現在3,211 → 8,000+) |
| V-3 | osctdlrmのEntity接続 | 5つのChunk全てにMENTIONS関係あり |
| V-4 | 冪等性 | 2回実行で重複Entity/関係がゼロ |
| V-5 | 既存データ保全 | 既存3,437接続済みChunkに影響なし |
| V-6 | Entity種別分布 | COMMAND, PRODUCT, CONCEPT_JA が上位に含まれる |
| V-7 | Auto-RAG検索改善 | osctdlrmクエリでNeo4j vector search結果が改善 |

---

## 7. リスクと対策

| リスク | 影響度 | 対策 |
|--------|--------|------|
| パターン過剰マッチ（ノイズEntity） | 中 | confidence閾値0.70 + Entity名最小3文字 + 不要語リスト |
| Neo4j書き込み負荷 | 低 | バッチサイズ100 + 500ms間隔で制御 |
| 文字化けChunk | 中 | UTF-8デコード不可のChunkはスキップ + ログ記録 |
| Summary辞書の不完全性 | 低 | パターンマッチとの二重抽出で補完 |

---

## 8. 成功指標

```
BEFORE:
  Chunks with Entity: 3,437 / 42,596 (8.1%)
  Total Entities: 3,211

AFTER (目標):
  Chunks with Entity: 34,000+ / 42,596 (80%+)
  Total Entities: 8,000+
  New MENTIONS relations: 25,000+
```
