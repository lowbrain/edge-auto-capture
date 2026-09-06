# このコードを触る人へ

「知らないと壊す仕掛け・作業環境・検証手順」に絞った恒久メモ。**変更前に §1 を読むこと。**

- **これから作る / 直すもの（残タスクと優先順）は Issue [#78](https://github.com/lowbrain/edge-auto-capture/issues/78)（ピン留め）が正。**
- ツールの仕組み・設定リファレンス・ビルド・配布は [`README.md`](README.md)。
- 過去の完了作業の実装内容は git 履歴を参照。

## 課題タグ（`A-` / `B-` / `D-` / `E-` / `F-` / `R`）— 退役語彙

`A-3` / `B-1` / `D-C1` / `E-6` / `F-D3` / `R5b` のような ID は**退役済み。新たに使わない。**
作業ツリー（コード・ドキュメント・スキル）からは外してあるが、git のコミットメッセージと
過去の Issue・PR のタイトルには残っているため、**それらを読むときにだけ要る。**

由来は `A-` / `B-` / `E-` が `IMPROVEMENTS.md`、`D-` が `DISTRIBUTION.md`、
`F-` が `FEATURES.md`、`R` が `REFACTORING.md`（いずれも退役済みの旧文書）。本文は git 履歴に
丸ごと残っていて、`git log --all --diff-filter=D --name-only --oneline -- 'docs/*'` で
退役コミットを辿り、その親から `git show <コミット>^:docs/IMPROVEMENTS.md` のように読める。

**個々のタグの語釈一覧はここに作らない**（二重管理になる。§4 末尾の方針）。この節は
「どこを `git show` すれば読めるか」だけを持つ索引で、語釈そのものは持たない。

---

## 1. コードベース固有の落とし穴（必ず読む）

知らないと壊す仕掛け。

1. **`badge.js` は「設定を 1 個受け取る関数式」** — ファイル全体が `(C) => { … }` で、
   `badge.py` の `build_badge_script()` が `f"({src})({json.dumps(config)});"` の形で
   呼び出す完成スクリプトを作る（#99）。設定は JS の引数として入るので、固定名が
   `globalThis` に一度も載らない（§1-6 の存在検知の防止と噛み合う）。
   **`badge.js` の末尾はセミコロン無しの `}` で終えること**（`(…)(…);` で包むため、
   ここに `;` があると構文エラーになる）。
   **テンプレートリテラルの `${...}` 補間は使ってよい。** かつては設定を目印の単純置換で
   差し込んでいたため補間を禁じていたが、**この制約は無い**。CSS の時間も JS の定数から
   `${...}` で差し込む（`.bar` の transition は `BAR_MOVE_MS`、`.frame.flash` は `FLASH_MS`）。
   **手動で整合を取る必要はない** — JS の定数が唯一の出所。

2. **Python は 3.9+**（`pyproject.toml` の `requires-python = ">=3.9"`、ruff の `target-version = "py39"`）。
   PEP 585 の `dict[...]` / `set[...]` / `tuple[...]` を**素で書いてよい**。
   ただし `X | Y` 記法は 3.10 以降なので使わないこと。`Optional[Path]` は `typing` から import。

   > **かつては 3.8 だったため注釈を文字列で書く決まりがあった。** `ruff --fix` がその引用符を
   > 外して黙って互換を壊す罠だったので 3.9 へ上げて根治した。
   > **古いコミットのコメントに「文字列で書くこと」とあっても、もう従わなくてよい。**

3. **例外の握り潰しは意図的** — `try_eval` / `_step` / `infra` の各 `except: pass` は
   堅牢性のための設計で、各所にコメントがある。**「握り潰しを直す」方向の一括リファクタはしない。**
   利用者に伝わらない握り潰し（無言終了・嘘のログ）への対処は済んでいるが、
   握り潰しそのものを消す作業ではない。`ruff` も `B008` を意図的に ignore している。

4. **`USAGE.txt` は Shift-JIS** — 編集する場合は文字コードを維持すること
   （`README.md` / `CONTRIBUTING.md` は UTF-8）。

   > **実務上の注意**: `iconv` で UTF-8 へ出して編集し、`iconv -f UTF-8 -t SHIFT_JIS` で戻すのが安全。
   > このとき、**ASCII のバックスラッシュ `\` は Shift-JIS へ変換できずエラーになる**ので、
   > パス区切りは既存記述と同じ `¥`（U+00A5）で書く。**絵文字も Shift-JIS には入らない**ので、
   > バーのラベルを引用するときは絵文字を落として「保存先」のように書く。
   > 書き戻したら往復変換して元と一致するか確かめること。
   >
   > **上は `iconv` を使う場合の話。** Python の `shift_jis` コーデックは同じ `\` を
   > `0x5C` として**素通しする**ので、Python で書き戻すとこの警告は当たらない。
   > **`iconv` で取り出した UTF-8 に見える `¥` は、著者が円記号を書いたのではなく `0x5C` の描画。**
   > Windows のパスだからと `\` へ「直す」と書き戻しがエラーになる。
   > **経路を混ぜず `iconv` で統一する** — 厳しい側なので、間違えても黙って壊れずエラーで止まる。
   > 実測値と手順の詳細はスキル [`.claude/skills/usage-txt/SKILL.md`](.claude/skills/usage-txt/SKILL.md)。

5. **バインディング名の出所は `badge.py` の `BIND_*` 1 箇所。`badge.js` に名前は無い**（#100）。
   名前は `badge.py` の `_BIND_NAMES`（キー＝JS 側の呼び名、値＝`BIND_*`）に載って設定 JSON の
   `bind` キーで配られ、`badge.js` 側は `Object.values(C.bind)` を退避＋削除の対象にし、
   呼び出しは `callBinding(C.bind.toggle, TOK, …)` の形で行う。
   **`badge.js` に `__eac_` で始まる文字列リテラルを書き戻さないこと**（二重管理が復活する。
   `tests/test_badge.py` が落とす）。
   バインディングを増やすときは (1) `BIND_*` を足し (2) `_BIND_NAMES` に載せ
   (3) `app.py` で `expose_binding` し (4) `badge.js` で `C.bind.<キー>` を呼ぶ。
   **どれを忘れても無言失敗する**（`callBinding` が `BOUND` から引けず `undefined` を返して終わり。
   例外もログも出ず、ボタンだけが効かなくなる）ので、(1)〜(3) の食い違いは
   `tests/test_badge.py` が、実際の発火は `tests/smoke_badge.py` が見る。

   > **§1-6 の呼び出し例について**: 同節に `callBinding('__eac_toggle', TOK, ...)` と
   > 名前を直に書いた例が残っているが、いまの正しい形は `callBinding(C.bind.toggle, TOK, ...)`。
   > 「`callBinding` 経由で呼ぶ」という §1-6 の趣旨は変わらない。

6. **`badge.js` のシャドウは `closed`・呼び出しは `callBinding` 経由**。
   - `host.shadowRoot` は `null` を返す。中を触るテストは
     `window.__eac_debugRoot()`（token 無しビルドでのみ公開）を使う
   - `window.__eac_toggle(...)` のような**直接呼び出しを新たに書かないこと**。
     必ず `callBinding('__eac_toggle', TOK, ...)` を使う（サイト側が差し替えた関数へ token を渡さないため）
   - `mode: 'open'` に戻すとスモークテストが失敗する（回帰チェックを入れてある）
   - **固定名を `window` に生やさない**（サイト側からの存在検知の防止）:
     - Python→ページのヘルパは固定名（`window.__eacApplyState` 等）ではなく、起動ごとの
       ランダム名 `ns`（`badge.new_namespace()`）の**非列挙**プロパティ `window[ns]` に
       まとめて公開する。呼び出し式は `badge.*_call(ns, ...)`（`body_text_call` / `sig_call` /
       `capture_start_call` / `capture_end_call` / `apply_state_call` / `set_count_call` /
       `set_history_call`）が `ns` 込みで組み立てる。**`ns` を第1引数に取る**ので、呼び出し側
       （`edge_auto_capture` の `self.ns`・`capture` の `runner.ns`）から必ず渡すこと。
       このうち **`sig_call` だけは本番経路では使わない**（`tests/smoke_badge.py` 専用。
       理由は `badge.py` の `sig_call` の docstring 参照）。
     - ページ→Python の `expose_binding` 固定名（`__eac_toggle` 等）は、`badge.js` 冒頭で本物の
       参照を `BOUND` へ退避したうえで `delete window[name]` して消す。この退避＋削除は
       **最上位フレームの早期 `return` より前**で全フレーム分行う（iframe にも生えるため）。
       token 無し（スモーク）ビルドは削除せず `callBinding` の実行時フォールバックに任せる。
     - `window.__eacApplyState` 等の**固定名代入を復活させない**こと（存在検知の防止が無効になる）。
       スモークテストの手順 13 が `'__eacApplyState' in window` / `'__eac_toggle' in window` を
       回帰チェックしている。

7. **`ruff check` / `mypy` は緑（終了コード 0）が正常** — **指摘が出たらそれは新しく入れた問題**なので直すこと。

8. **`[tool.mypy] python_version = "3.10"` と `requires-python = ">=3.9"` の食い違いは意図的** —
   mypy 2.3.0 が 3.9 ターゲットを廃止したため引き上げた。**これは mypy の型検査ターゲット設定であって、
   実行系の要件ではない**（実行時は 3.9 のままで、macOS の Python 3.9 でも緑）。
   知らずに 3.9 へ戻すと mypy が動かなくなる。

9. **`infra._message_box_windows` の `ctypes.windll` は `Any` 経由の属性アクセスが正** —
   `# type: ignore[attr-defined]` は macOS スタブでは必要・Windows スタブでは不要で、
   `warn_unused_ignores = true` ゆえ **OS 次第で必ず片方が落ちる**。だから ignore を撤去して
   `Any` 経由に変えてある。`getattr` は ruff の `B009` と衝突するため不採用。

10. **コメントは資産。関数を移動するときは一緒に運ぶ** — 各所の日本語コメントは
    落とし穴回避の記録。リファクタで関数を移すときも**コメントを削らない・要約しない。**

11. **`infra.BASE_DIR`（＝ `config.ini` / `output/` / `log.txt` の基準フォルダ）は
    非 frozen 実行では「カレントディレクトリ」であって「パッケージフォルダ」ではない**（#81）。
    `_base_dir()` はかつて `Path(__file__).parent`（このモジュールのあるフォルダ）を
    使っていたが、`src/` レイアウト化（パッケージ化）すると `__file__` はインストール先の
    パッケージフォルダを指すようになり、`pip install` したコマンドを実行した場所とは
    無関係な場所で `config.ini` を探し・`output/` を作ろうとして壊れる。それを避けるため
    非 frozen 側は `Path.cwd()` を返す（frozen 側＝exe 実行は無変更で `sys.executable` の親）。

> **行番号について**: このファイルは意図的に行番号ではなく**シンボル名**で場所を指している。
> 過去に行番号で書いた参照はコードの成長で軒並みずれた。

---

## 2. 作業環境の注意

開発ホストは **macOS (darwin)**、本ツールは **Windows 専用**。

| 事項 | 状況 |
|------|------|
| `pytest` / `ruff` / `mypy` | `pip install -e ".[dev]"` を先に。`ruff check` / `mypy` は緑（終了コード 0）が正常 |
| `tests/smoke_badge.py` | 実 Edge/Chrome が要る。**Edge → Chrome の順にフォールバックするので、Edge の無い macOS でも Chrome があれば実際に走って通る**（同じ Chromium 系でバー JS の検証としては等価）。どちらも無ければ `SKIP`（終了コード 0）で抜けるので **PASS 表示を鵜呑みにしない**（`--strict` で FAIL 化） |
| `infra._message_box` | Windows は `ctypes.windll`、macOS は `osascript`（開発機での確認用に分岐追加済み） |
| `build.ps1` | PowerShell / Windows 専用。macOS では実行検証できない |
| `%LOCALAPPDATA%` | 書き込み不可時の退避先。macOS には存在せず `tempfile.gettempdir()` へフォールバック |
| バイトコードキャッシュ | Apple 版 python は `__pycache__` を作らず `~/Library/Caches/com.apple.python/` へ退避する。**壊れたコードで `pytest` が緑になる罠がある**（下記） |

**両 OS でカバレッジが相補的**な点に注意。Windows では `test_resolve_writable_dir_*` 2 件
（書き込み不可時の退避ロジック）が POSIX chmod の効かなさゆえ self-skip され、macOS では実行されて通る。
片方の OS だけで「全部通った」と判断しないこと。

### macOS: 古いバイトコードで `pytest` が偽の緑を出す

**発火条件は「同じバイト長の書き換えを同一秒内に行う」の 1 点。** Python の `.pyc` は
「ソースの mtime（秒）とサイズ」で有効性を判定するので、**両方とも変わらない書き換えは
古いバイトコードのまま走る**。実際にこれで、壊した `app.py` に対し `pytest` が
`202 passed` と緑を出した（正しくは 4 件 FAIL）。

手で書くぶんには長さがまず変わるので踏まない。**踏むのは `sed` などで同じ長さの識別子を
入れ替えたときと、「わざと壊して FAIL することを確かめる」検証**で、後者はこのリポジトリで
実際にやる作業なので当たる。

厄介なのは置き場所で、この機の `.venv` は Apple の Command Line Tools 同梱 python3 を
土台にしており、`sys.pycache_prefix` が設定されている。**`.pyc` はリポジトリ内ではなく
`~/Library/Caches/com.apple.python/<リポジトリの絶対パス>/` に置かれる**ため、
`find . -name __pycache__ -delete` では消えない（そもそもリポジトリ内に作られない）。

自分の環境が該当するかは次で分かる（空文字なら無関係）:

```bash
python -c "import sys; print(sys.pycache_prefix)"
```

**対処は「走らせる前にリポジトリぶんのキャッシュを消す」。**

```bash
rm -rf ~/Library/Caches/com.apple.python"$PWD" && pytest
```

以下は**効かない**ので注意（いずれも実測で確認済み）:

| やりがちなこと | 結果 |
|---|---|
| `find . -name __pycache__ -delete` | **無効**。リポジトリ内に `__pycache__` は作られない |
| 途中から `python -B` に切り替える | **無効**。`-B` は「書かない」だけで、既にあるキャッシュは読む |
| `PYTHONPYCACHEPREFIX=` （空）を渡す | **無効**。空は未設定扱いになり Apple の既定が残る |
| 最初からずっと `python -B` | 有効。ただしキャッシュが空の状態から徹底する必要がある |

---

## 3. 検証手順（4 点セット）

変更のたびに **pytest / smoke / ruff / mypy の 4 点**を全部緑にする。

```bash
pip install -e ".[dev]"
pytest                                 # 速い純粋関数・token 照合・DL の回帰
python tests/smoke_badge.py --strict   # 実 Edge/Chrome。バー構築・SPA検知・写り込み防止・固定名の検知不能化・JS エラー無し
ruff check .
mypy .
```

- **smoke は実 Edge/Chrome 必須**（**Chrome があれば macOS でも走る**。CI は Windows + 実 Edge）。
  どちらも手元に無ければ `SKIP`（終了コード 0）で抜けるので
  **PASS 表示を鵜呑みにしない**。CI・検証では **`--strict`** を付けて FAIL 化する（付けないと
  ブラウザ不在環境で「何も検証せず緑」になる）。SKIP されたら報告では「未検証」と明記する。
- **smoke が緑でも Windows 実機検証の代わりにはならない。** smoke が見るのは操作バーの JS で、
  `build.ps1` / `infra._message_box_windows` の `ctypes.windll` / `%LOCALAPPDATA%` 退避 /
  実 Edge 固有の挙動は対象外。実機検証の現在地は Issue
  [#78](https://github.com/lowbrain/edge-auto-capture/issues/78) の「検証状況」が正。
- **新モジュールを足すときは `src/edge_auto_capture/` へ置くだけでよい**（`packages.find` が自動検出する。#81）。
  `[tool.mypy]` は `files = ["."]` + `exclude` 方式なので追記不要。列挙方式へ戻さないこと。
- リファクタでは**新規テストを足せる場所は足す**（純粋関数・判定ロジック・レジストリ等はブラウザ無しで単体化できる）。
- `ruff` は `line-length = 120`、`select = ["E", "F", "I", "UP", "B"]`。

CI（GitHub Actions）でも同じ 4 点が回る（[`.github/workflows/ci.yml`](.github/workflows/ci.yml)）。
ジョブは 3 本に分かれていて、`ruff` + `mypy` と `pytest` は Linux、**smoke は実 Edge が要るので Windows runner** で
`--strict` 付きで回す（`pytest` は 3.9 / 3.12 のマトリクスなので、**実行されるチェックは 4 つ**になる）。

---

## 4. コミット・報告の慣習

- **1 件ずつ 1 コミット**。まとめない。
- コミットメッセージは既存の慣習（日本語・`種別: 内容` 形式）に合わせる。
  例: `修正: ダウンロードの保存先を output 配下へ明示する（#59）`
  末尾の括弧には対象の Issue 番号を書く（課題タグは退役済み。冒頭の「退役語彙」）。
- **push / タグ付けは利用者に確認**してから。
- ドキュメント（`README.md` / `CONTRIBUTING.md` / `USAGE.txt`）を直したら、その旨を報告に含める。
- **未検証の項目は必ず「未検証」と明記する。** 憶測で「動作を確認しました」と書かない。
- 残タスクの状態は Issue 側が正。**ドキュメントに残タスクの一覧を作らない**
  （二重管理になり、実際に食い違いが起きた。経緯は [#38](https://github.com/lowbrain/edge-auto-capture/issues/38) 冒頭）。
- **ドキュメント・スキルに「いつ時点」を持たせない。** 「〜時点で未検証」「最終確認: YYYY-MM-DD」の
  ような日付・コミットハッシュ入りの現在地を本文へ書かない（書いた瞬間から古びるが、
  何のチェックにも掛からない）。現在地は Issue
  [#78](https://github.com/lowbrain/edge-auto-capture/issues/78) が正で、ドキュメント側は
  そこを指すにとどめる。**Issue 本文へ書く検証結果は逆で、「いつ・どのコミットを」検証したかを明記する**
  （そちらは記録なので日付が要る）。
