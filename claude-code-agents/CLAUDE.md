# TmaxSoft メインフレームナレッジマネジメントシステム (KMS)

## プロジェクト概要
LegacyメインフレームおよびTmaxSoft OpenFrame製品の技術マニュアルに基づくAI Q&Aシステム。
各製品ごとに専門エージェントを配置し、正確なマニュアルベースの回答を提供する。

## 利用可能なコマンド一覧

### Legacy HOSTシステム
```
/legacy-xsp <質問>    → 富士通 XSP メインフレーム
/legacy-msp <質問>    → 富士通 MSP メインフレーム
/legacy-mvs <質問>    → IBM MVS メインフレーム
/legacy-vos3 <質問>   → 日立 VOS3 メインフレーム
```

### TmaxSoft OpenFrame
```
/of-xsp <質問>        → OpenFrame XSP 7.3
/of-msp <質問>        → OpenFrame MSP 7.3
/of-mvs <質問>        → OpenFrame MVS 7.1
/of-asm <質問>        → OFAsm 4（アセンブラ）
/of-cobol <質問>      → OFCOBOL 4（COBOL）
/of-batch <質問>      → OpenFrame BATCH
/of-hidb <質問>       → OpenFrame HiDB（階層型DB）
/of-vos3 <質問>       → OpenFrame VOS3 2.0
```

## 使用例
```
/legacy-xsp XSPのJCLでDD文の書き方を教えて
/of-cobol OFCOBOLのコンパイルオプション一覧
/of-mvs OpenFrame MVSでVSAMファイルを定義する方法
/legacy-mvs MVSのIDCAMSユーティリティの使い方
```

## マニュアルディレクトリ構成
```
docs/specs/
├── XSP/          # Legacy XSP マニュアル
├── MSP/          # Legacy MSP マニュアル
├── MVS/          # Legacy MVS マニュアル
└── VOS3/         # Legacy VOS3 マニュアル

uploads/manuals/
├── XSP_Openframe 7.3_v3.2.1_JP/     # OpenFrame XSP
├── MSP_Openframe 7.3_v2.1.1_JP/     # OpenFrame MSP
├── OFAsm_4_v3.1.2_JP/               # OpenFrame ASM
├── OFCOBOL_4_v3.1.2_JP/             # OpenFrame COBOL
├── MVS_Openframe 7.1_v3.1.3_JP/     # OpenFrame MVS
└── VOS3_Openframe 2.0 _v2.1.1 _JP/  # OpenFrame VOS3
```

## 共通ルール
- 回答はマニュアルの記載内容に基づくこと
- 出典（ファイル名、セクション）を必ず明記すること
- マニュアルに記載がない場合は「記載なし」と明示すること
- 推測での回答は禁止
- 回答言語は質問の言語に合わせること（日本語/韓国語/英語）
