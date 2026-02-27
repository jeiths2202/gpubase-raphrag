# Completion Report: rag-table-image-display

## 概要

| 項目 | 値 |
|------|-----|
| Feature | RAG 응답 테이블/이미지 WebUI 출력 |
| 完了日 | 2026-02-27 |
| Match Rate | 95% |
| PDCA Iterations | 1 (85% → 95%) |
| 修正ファイル数 | 3 (Backend 1, Frontend 2) |

## 1. 背景と目標

### 問題

Agentic RAG ページで LLM 応答がテキストのみで出力され、PDF から抽出されたテーブルや図がWebUI に表示されなかった。

**根本原因:**
- `_build_table_supplement()` の `score >= 3.0` 制限により、ほとんどの検索結果でテーブル補足がスキップされていた
- 検索結果 Top-1 のみ対象で、関連テーブルのカバレッジが不足
- 画像のクリック拡大機能なし

### 目標 (Plan から)

1. RAG 検索結果に関連**テーブル**がある場合、GFM マークダウンで応答に含める
2. RAG 検索結果に関連**画像**がある場合、画像 URL で応答に含める
3. フロントエンドでテーブルは styled table、画像はクリック拡大可能にレンダリング

## 2. 実装内容

### Backend: `app/api/services/agentic_rag_service.py`

#### 変更 1: スコア制限の緩和
```python
# Before
for r in results[:1]:
    if r.relevance_score < 3.0:
        continue

# After
for r in results[:3]:
    if r.relevance_score <= 0:
        continue
```
- `score >= 3.0` → `score > 0` に緩和（ほぼすべての有効な検索結果が対象）
- Top-1 → Top-3 に拡大（テーブル/画像カバレッジ向上）

#### 変更 2: セーフガード追加
```python
MAX_TABLE_ROWS = 20  # テーブル行数制限
MAX_IMAGES = 2       # 画像数制限
```
- テーブル: ヘッダー 1行 + データ最大 20行に切り捨て
- 画像: ページあたり最大 2枚に制限

#### 変更 3: キーワードマッチング検証
```python
# CJK 2-gram + ASCII トークンによるクエリ↔テーブル交差検証
query_keywords = set()
if query:
    q_lower = query.lower()
    for tok in re.findall(r'[a-z0-9_]{2,}', q_lower):
        query_keywords.add(tok)
    for cjk_run in re.findall(r'[\u3040-\u9fff\uac00-\ud7af]+', q_lower):
        for i in range(len(cjk_run) - 1):
            query_keywords.add(cjk_run[i:i+2])
```
- 日本語/韓国語/中国語をCJK 2-gramで処理（スペース分割不可の言語に対応）
- ASCII キーワードも併用（`osc`, `tdlrm` など）
- テーブル内容にクエリキーワードが1つ以上含まれない場合スキップ

#### 変更 4: メソッドシグネチャ拡張
```python
def _build_table_supplement(self, results, query: str = "") -> str:
```
- 4つの呼び出しサイトすべてで `query=request.message` を渡すように変更

### Frontend: `MessageContent.tsx`

#### 変更 5: 画像クリック拡大
```tsx
const [enlargedImg, setEnlargedImg] = useState<string | null>(null);

// img handler
img: ({ src, alt }) => (
  <img
    src={src} alt={alt || 'Image'}
    className={`${prefix}-markdown-img`}
    loading="lazy"
    style={{ cursor: 'pointer' }}
    onClick={() => src && setEnlargedImg(src)}
  />
),

// Overlay modal
{enlargedImg && (
  <div className={`${prefix}-image-overlay`}
       onClick={() => setEnlargedImg(null)}>
    <img src={enlargedImg} alt="Enlarged"
         className={`${prefix}-image-enlarged`} />
  </div>
)}
```

### Frontend: `AgentChat.css`

#### 変更 6: 画像 hover + オーバーレイ CSS
```css
.agent-markdown-img:hover { opacity: 0.85; }

.agent-image-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.8);
  display: flex; align-items: center; justify-content: center;
  cursor: zoom-out;
}
.agent-image-enlarged {
  max-width: 90vw; max-height: 90vh;
  object-fit: contain;
}
```

## 3. Gap Analysis 結果

### 1次分析: 85%

| Gap | 内容 |
|-----|------|
| キーワード検証なし | スコア緩和により無関係テーブルが含まれる可能性 |
| 画像クリック拡大なし | Plan 目標3番未充足 |
| CSS prefix 確認 | `agent-markdown-img` 存在を確認済み |

### 修正後: 95%

| Category | Score | Status |
|----------|:-----:|:------:|
| Backend - Score 緩和 | 100% | ✅ |
| Backend - Top-3 拡大 | 100% | ✅ |
| Backend - Table Enrichment | 100% | ✅ |
| Backend - Image Extraction | 100% | ✅ |
| Safeguard - テーブル 20行制限 | 100% | ✅ |
| Safeguard - 画像 2枚制限 | 100% | ✅ |
| Safeguard - キーワード検証 | 100% | ✅ |
| Frontend - テーブルレンダリング | 100% | ✅ |
| Frontend - 画像 CSS | 100% | ✅ |
| Frontend - 画像クリック拡大 | 100% | ✅ |
| 非修正範囲遵守 | 100% | ✅ |

残り 5%: `structured_knowledge_store.py` の `enrich_content_with_tables()` / `_extract_page_images()` は既存動作で十分と判断し、追加変更不要。

## 4. テスト結果

### API テスト

| クエリ | テーブル | 画像 | ルーティング | 所要時間 |
|--------|:--------:|:----:|:------------:|:--------:|
| OSCシステムサーバーの一覧を教えてください | ✅ 5 tables | - (該当ページに画像なし) | openframe_mvs | ~60s |
| osctdlrmに대해서 알려줘 | - (該当ページにテーブルなし) | - | openframe_mvs | ~3.4s |

### 動作フロー確認

```
SSE Stream:
  classification → search_progress → llm_token(×N)
  → llm_token("---\n\n**参考テーブル:**\n\n| ... |")  ← 新規追加
  → verification → graph_data → sources → done
```

- テーブルは `llm_token` イベントとして SSE ストリームに追加
- フロントエンドの `react-markdown` + `remarkGfm` が GFM テーブルをレンダリング
- `MessageContent` の `table` コンポーネントが水平スクロール付きスタイルを適用

## 5. 修正ファイル一覧

| ファイル | 変更内容 | 行数 |
|----------|----------|:----:|
| `app/api/services/agentic_rag_service.py` | score 緩和, top-3, 行制限, 画像制限, CJK キーワード検証, query パラメータ追加 | ~30行 |
| `kms-portal-ui/src/components/AgentChat/MessageContent.tsx` | 画像クリック拡大 (enlargedImg state + overlay) | ~15行 |
| `kms-portal-ui/src/components/AgentChat.css` | hover 効果 + フルスクリーンオーバーレイ CSS | ~20行 |

## 6. アーキテクチャへの影響

### 影響なし (非破壊的変更)
- `enrich_content_with_tables()` — 既存動作維持
- `_extract_page_images()` — 既存動作維持
- `BlockRenderer` / `useStreamingChat` — 未修正
- SSE イベント構造 — 変更なし（`llm_token` に追加マークダウンを付加するのみ）

### 後方互換性
- `_build_table_supplement(results)` — `query` パラメータはデフォルト `""` で後方互換
- キーワード検証は `query_keywords` が空（query なし）の場合スキップ

## 7. 今後の改善ポイント

| 項目 | 優先度 | 説明 |
|------|:------:|------|
| 画像 Lazy Loading 最適化 | Low | 画像が多い場合の Intersection Observer 導入 |
| テーブル列幅自動調整 | Low | 長いテーブルの列幅を内容に応じて調整 |
| 画像キャッシュ | Low | 同じ PDF ページの画像をブラウザキャッシュ活用 |

## 8. PDCA サイクル振り返り

```
[Plan] ✅ → [Do] ✅ → [Check] ✅ (85%→95%) → [Report] ✅
```

- **Plan**: 原因分析 (score >= 3.0 制限) と修正範囲を明確化
- **Do**: Backend score 緩和 + top-3 + セーフガード実装
- **Check**: Gap Analysis で 3 つの Gap 発見 → 即時修正 → 95% 達成
- **Report**: 本レポート
