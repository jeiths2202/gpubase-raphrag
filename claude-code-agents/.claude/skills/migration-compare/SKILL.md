---
name: migration-compare
description: LegacyメインフレームとOpenFrameの機能比較・マイグレーション差異分析。Legacy側とOpenFrame側の両マニュアルを参照して差異レポートを生成します。
context: fork
allowed-tools: Task, Read, Grep, Glob, Bash
---

# Legacy ↔ OpenFrame マイグレーション比較分析

以下の手順で、LegacyシステムとOpenFrameの差異を分析してください。

## 対象マッピング
| Legacy | OpenFrame | Legacyパス | OpenFrameパス |
|---|---|---|---|
| XSP | OpenFrame XSP | docs/specs/XSP/ | uploads/manuals/XSP_Openframe 7.3_v3.2.1_JP/ |
| MSP | OpenFrame MSP | docs/specs/MSP/ | uploads/manuals/MSP_Openframe 7.3_v2.1.1_JP/ |
| MVS | OpenFrame MVS | docs/specs/MVS/ | manuals/MVS_Openframe 7.1_v3.1.3_JP/ |
| VOS3 | OpenFrame VOS3 | docs/specs/VOS3/ | manuals/VOS3_Openframe 2.0 _v2.1.1 _JP/ |

## 分析手順
1. $ARGUMENTS からLegacy製品とOpenFrame製品を特定
2. 該当するLegacyマニュアルから関連機能を調査
3. 対応するOpenFrameマニュアルから同機能を調査
4. 差異を以下の形式でレポート

## レポート形式
### 機能比較表
| 項目 | Legacy | OpenFrame | 差異・注意点 |
|---|---|---|---|

### 互換性サマリ
- 完全互換の機能
- 部分互換の機能（要修正）
- 非互換の機能（代替手段あり）
- 非対応の機能

### マイグレーション推奨事項
- 移行時の注意点
- 推奨される変換手順

$ARGUMENTS
