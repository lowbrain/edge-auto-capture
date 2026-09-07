# 配布用 exe のビルドと配布

ビルド・コードサイニング署名・配布・配布先 IT への許可依頼の手順。
**ツールの仕組み・設定リファレンス・テストは [README.md](README.md)**、
**コードを触るときの落とし穴・検証手順は [CONTRIBUTING.md](CONTRIBUTING.md)。**

## ビルド

Python 未導入の Windows PC でも動く、単一 EXE（フォルダ形式）を作る。

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

PyInstaller が `dist\edge-auto-capture\` を生成し、`config.ini`（同梱テンプレート
`src/edge_auto_capture/default_config.ini` の写し）/ `USAGE.txt` /
依存ライセンス表記（`THIRD-PARTY-NOTICES.txt`）/ `LICENSE`（あれば）を exe の隣へ同梱する。
ページ側 JS の `badge.js` と既定設定の `default_config.ini` は `--add-data` で `_internal\` に
同梱され、実行時は `sys._MEIPASS` から読み込まれる（解決は `infra.package_data_path` の
1 か所。`badge.py` `capture.py` は import から自動で辿られる）。
最後に配布用の `dist\edge-auto-capture.zip` と、その `*.zip.sha256`（完全性確認用）を作る。

### コードサイニング署名（任意）

証明書を持っている場合はビルド時に署名できる。指定が無ければ署名ステップは素通りし、
現状どおり未署名で配布される。

```bash
# PFX ファイルで署名
powershell -ExecutionPolicy Bypass -File build.ps1 -CertPath cert.pfx -CertPassword ****
# 証明書ストア上の証明書を拇印で指定（EV トークン等）
powershell -ExecutionPolicy Bypass -File build.ps1 -CertThumbprint <THUMBPRINT>
```

> **受け口は実装済み、証明書の取得は保留（組織判断）。** 企業環境では SmartScreen の「警告」ではなく
> **「ブロック」**（AppLocker / WDAC / Intune）になることがあり、「詳細情報 → 実行」では回避できない。
> 本格配布ならコードサイニング証明書が最も効く（OV で警告軽減、EV なら SmartScreen 評価が即付く）。
> 年額コストと発行手続きが要るため、技術判断ではなく組織判断として保留している。
> 取得できない間は下の「配布先 IT へ許可登録を依頼する連絡テンプレート」を使う。

## 配布方法

生成された `dist\edge-auto-capture.zip` を配る（中身は `dist\edge-auto-capture\`）。フォルダ構成:

```
edge-auto-capture\
├─ edge-auto-capture.exe      ダブルクリックで起動
├─ config.ini                 利用者が編集可能
├─ USAGE.txt                  利用者向けの使い方
├─ THIRD-PARTY-NOTICES.txt    同梱依存（Playwright 等）のライセンス表記
├─ LICENSE.txt                本体のライセンス（LICENSE がある場合）
├─ _internal\                 ランタイム + playwright ドライバ + badge.js + default_config.ini（必須・触らない）
└─ output\                    実行後に生成される保存先
```

配布物の完全性は同梱の `edge-auto-capture.zip.sha256` で確認できる:

```powershell
(Get-FileHash -Algorithm SHA256 edge-auto-capture.zip).Hash
```

> `_internal\` は動作に必須。exe だけ取り出しても動かない。
> 未署名 exe のため初回に Windows SmartScreen 警告が出る場合がある
> （「詳細情報」→「実行」で起動可能）。企業環境では警告ではなくブロックに
> なることがある（AppLocker / WDAC / Intune）。その場合は下の依頼テンプレートで
> 配布先 IT へ許可登録を依頼する。

## 配布前の確認

- **アンチウイルスの誤検知** — PyInstaller 製バイナリはヒューリスティックで誤検知されやすい。
  `--onedir`（`--onefile` より誤検知しにくい）は採用済み。**配布前に主要な AV で一度確認**しておく。
  出る場合は署名するかベンダーへ誤検知報告。技術改修ではなく都度対応の運用事項。
- **配布物のサイズ実測** — `--collect-all playwright` は Node ドライバごと同梱するため
  100MB 超になる可能性がある。配布経路（メール添付の可否等）に影響するので実測する。
- `output\` の同梱は `build.ps1` が自動で行う。空の `output\` を作り、展開時点で書き込み可否が
  分かるようにしている（`Compress-Archive` は空フォルダを ZIP に含めないため、フォルダ保持と
  利用者案内を兼ねた説明ファイルを 1 つ置く）。狙いは権限問題に早く気づけること。

## 配布先 IT へ許可登録を依頼する連絡テンプレート

証明書を取得しない間、企業環境でブロックされる場合はこれで許可登録を依頼する。
`< >` は配布ごとに埋める。SHA256 は `build.ps1` が出力する `*.zip.sha256` の値を使う。

```
件名: 業務ツール「edge-auto-capture」の実行許可のお願い

<IT 部門ご担当者> 様

業務調査で使用するツール「edge-auto-capture」を配布します。
現時点でコードサイニング署名が無いため、SmartScreen / AppLocker / WDAC / Intune の
ポリシーによってはブロックされる可能性があります。以下の実行ファイルの許可登録
（許可リストへの追加）をご検討いただけますでしょうか。

- ツール名 : edge-auto-capture
- 用途     : Web ページのスクリーンショット・テキストの自動保存（社内調査用）
- 配布物   : edge-auto-capture.zip（PyInstaller onedir 形式・未署名）
- 実行ファイル: edge-auto-capture.exe
- SHA256(zip): <build.ps1 が出力した SHA256 値>
- 依存      : Microsoft Edge / Google Chrome（同梱の Playwright ドライバ経由）
- 配布元    : <配布者名・連絡先>

ご不明点があればお知らせください。よろしくお願いいたします。
```
