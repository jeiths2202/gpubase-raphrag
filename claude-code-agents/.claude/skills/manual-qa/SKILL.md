---
name: manual-qa
description: マニュアルベースの技術Q&A共通ガイドライン。各製品エージェントが参照する共通ルールとベストプラクティスを定義します。
---

# マニュアルQ&A 共通ガイドライン

## 概要
このスキルは、Legacy HOSTシステムおよびTmaxSoft OpenFrame製品のマニュアルに基づく
技術Q&Aを行う全エージェント共通のガイドラインです。

## 対象エージェント一覧

### Legacy HOSTシステム
| エージェント | コマンド | 対象システム | マニュアルパス |
|---|---|---|---|
| legacy-xsp-agent | /legacy-xsp | 富士通 XSP | docs/specs/XSP/ |
| legacy-msp-agent | /legacy-msp | 富士通 MSP | docs/specs/MSP/ |
| legacy-mvs-agent | /legacy-mvs | IBM MVS | docs/specs/MVS/ |
| legacy-vos3-agent | /legacy-vos3 | 日立 VOS3 | docs/specs/VOS3/ |

### TmaxSoft OpenFrame
| エージェント | コマンド | 対象製品 | マニュアルパス |
|---|---|---|---|
| of-xsp-agent | /of-xsp | OpenFrame XSP 7.3 | uploads/manuals/XSP_Openframe 7.3_v3.2.1_JP/ |
| of-msp-agent | /of-msp | OpenFrame MSP 7.3 | uploads/manuals/MSP_Openframe 7.3_v2.1.1_JP/ |
| of-mvs-agent | /of-mvs | OpenFrame MVS 7.1 | manuals/MVS_Openframe 7.1_v3.1.3_JP/ |
| of-asm-agent | /of-asm | OFAsm 4 | uploads/manuals/OFAsm_4_v3.1.2_JP/ |
| of-cobol-agent | /of-cobol | OFCOBOL 4 | uploads/manuals/OFCOBOL_4_v3.1.2_JP/ |
| of-batch-agent | /of-batch | OpenFrame BATCH | uploads/manuals/BATCH_OpenFrame/ |
| of-hidb-agent | /of-hidb | OpenFrame HiDB | uploads/manuals/HiDB_OpenFrame/ |
| of-vos3-agent | /of-vos3 | OpenFrame VOS3 2.0 | manuals/VOS3_Openframe 2.0 _v2.1.1 _JP/ |

## 共通動作ルール

### 1. ドキュメント検索手順
```
Step 1: Glob でディレクトリ構造を把握
Step 2: Grep でキーワード検索（日本語・英語両方で検索）
Step 3: Read で該当ファイルを精読
Step 4: 複数ファイルに関連情報がある場合はすべて確認
```

### 2. 回答品質基準
- **正確性**: マニュアルに記載された内容のみに基づく
- **出典明記**: ファイル名・セクション・ページを必ず記載
- **未記載の明示**: マニュアルに無い場合は明確に「記載なし」と回答
- **推測禁止**: 推測や一般知識での補完は行わない

### 3. 日本語対応
- マニュアルは日本語で記述されている
- Grepでの検索は日本語キーワードも使用する
- 回答は質問の言語に合わせる（日本語の質問には日本語、韓国語には韓国語、英語には英語）

### 4. エラーハンドリング
- マニュアルディレクトリが空の場合: 「マニュアルが配置されていません」と通知
- ファイルが読めない場合: エラー内容を報告し、別のアプローチを試行
- 検索結果が0件の場合: 類似キーワードで再検索を試行

## マイグレーション比較クエリ
ユーザーがLegacyとOpenFrameの比較を求めた場合:
1. 該当するLegacyエージェントとOpenFrameエージェントの**両方**を呼び出す
2. 両者の回答を対比表形式でまとめる
3. 差異ポイント・注意事項を明確に記載
