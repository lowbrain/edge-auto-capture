# CLAUDE.md

Claude Code 向けの**導線**。ここは内容の出所ではない。

> **このファイルに知識をコピーしないこと。** このリポジトリは過去に
> `docs/ROADMAP.md` と Issue の二重管理で実害を出し（#38 冒頭）、
> CONTRIBUTING の手順が実態からズレて「解消済みの罠を踏み直せ」と
> 指示する状態にもなった（#51）。**CLAUDE.md を 4 枚目の drift 源にしない。**
> ここに書いてよいのは「どこを見るか」だけで、「何が正しいか」は書かない。

## 出所

| 知りたいこと | 出所 |
|---|---|
| **触る前に知るべき落とし穴** | [`CONTRIBUTING.md`](CONTRIBUTING.md) §1「コードベース固有の落とし穴」 |
| 作業環境（macOS 開発 / Windows 専用ツール） | [`CONTRIBUTING.md`](CONTRIBUTING.md) §2「作業環境の注意」 |
| 検証手順 | [`CONTRIBUTING.md`](CONTRIBUTING.md) §3「検証手順（4 点セット）」／スキル `/verify` |
| コミット・報告の慣習 | [`CONTRIBUTING.md`](CONTRIBUTING.md) §4「コミット・報告の慣習」 |
| 課題タグ（`A-` / `B-` / `D-` / `E-` / `F-` / `R`）— 退役済み。git 履歴を読むときだけ要る | [`CONTRIBUTING.md`](CONTRIBUTING.md) 冒頭「退役語彙」 |
| 仕組み・設定・テスト | [`README.md`](README.md) |
| 配布用 exe のビルド・署名・配布・IT への許可依頼 | [`BUILD.md`](BUILD.md) |
| 利用者向けの使い方（Shift-JIS） | [`USAGE.txt`](USAGE.txt) |
| **残タスクと現在地・個々のタグの状態** | Issue [#78](https://github.com/lowbrain/edge-auto-capture/issues/78)（ピン留め・これが正） |
| 過去の完了作業の実装内容 | git 履歴 |

**ドキュメントに残タスクの一覧を作らない**（#78 の運用ルール）。

## 変更前に読む場所（ファイル → 節）

「知らないと無言で壊れる」箇所は変更対象ごとに違う。**着手前に該当節を読む。**

| 触るもの | 読む節 | 一言 |
|---|---|---|
| `badge.js` / `badge.py`（`src/edge_auto_capture/` 配下） | §1-1, §1-5, §1-6 | 言語境界。設定は関数式の引数・名前の出所は `BIND_*`・`closed` シャドウ・固定名禁止 |
| `USAGE.txt` | §1-4 | Shift-JIS。往復変換で確認する |
| 型注釈 | §1-2 | Python 3.10+。`X \| Y` を書いてよい |
| 例外処理まわり | §1-3 | 握り潰しは意図的な設計。消す方向の一括リファクタをしない |
| 関数の移動・リファクタ | §1-9 | コメントに残すのは罠。経緯は git へ返す（判定基準は §1-9） |
| `infra._message_box_windows` | §1-8 | `ctypes.windll` は `Any` 経由が正 |
| `infra._base_dir` / `BASE_DIR` | §1-10 | 非 frozen 実行の基準は cwd。パッケージフォルダではない |

## 検証

変更のたびに 4 点セット（§3）。**スキル `/verify` がこれを扱う** —
`--strict` 必須、smoke の FAIL 切り分け、全部緑でも残る未検証領域、報告フォーマットを含む。

**未検証の項目は必ず「未検証」と明記する**（§4）。4 点が緑なのは自動検査であって実機動作ではない。
