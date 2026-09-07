# edge-auto-capture

Microsoft Edge（無ければ Google Chrome）で開いたページを、**記録ONの間だけ**、フルページのスクリーンショット(`.png`)と
ページ全文テキスト(`.txt`)へ自動保存するツール。CSS セレクタを指定すれば、ページの一部だけを
抜き出したテキスト(`_part.txt`)も保存でき、URL が変わらず中身だけ変わる SPA も検知して撮れる。

> **利用者向けの使い方**（操作バーの操作、SPA検知の使い方、CSSセレクタの入れ方・調べ方、
> トラブル対処など）は **[USAGE.txt](USAGE.txt)** に一本化している。
> この README は**開発向け**の情報（仕組み・構成・設定リファレンス・テスト）をまとめる。
> **配布用 exe のビルド・署名・配布・IT への許可依頼**は [BUILD.md](BUILD.md)。
> **このコードを触るときの落とし穴・作業環境・検証手順**は [CONTRIBUTING.md](CONTRIBUTING.md)。
> **これから作る / 直すもの（残タスクと優先順）**は
> Issue [#78](https://github.com/lowbrain/edge-auto-capture/issues/78)（ピン留め）が正。

## 仕組み（概要）

- 記録ON中、Playwright が各ページの URL/タブ変化を**イベント駆動**で検知し（URL変化は
  `page.on("framenavigated")`、新規タブは `context.on("page")`、ページ消滅は `page.on("close")`）、
  変化ごとに capture（`png` / `txt`、セレクタ指定時は `_part.txt`）を走らせる。ポーリング間隔
  （旧 `poll_interval`）は廃止し、変化から撮影までの遅延も無くした。Edge の起動・監視・終了・
  一時プロファイルの後始末までを一括で行う（毎回まっさらな一時プロファイルで起動）。
- **撮影のたびに索引 CSV（`index.csv`）へ 1 行追記する**。列は 時刻 / URL / タイトル /
  ファイル名接頭辞 / 撮影契機（手動・URL変化・SPA） / セレクタ / 成否。時刻は ISO 8601（オフセット付き）、
  Excel で開く前提なので **BOM 付き（`utf-8-sig`）で新規作成し、追記は `utf-8`**（BOM の二重付与を避ける）。
  全系譜ぶんを 1 本にまとめる粒度は `log.txt` と同じ。
- **タブ系譜（グループ）ごとの独立制御**: 記録ON/OFF・SPA検知・セレクタは、セッション全体で
  共有せず「タブ系譜」ごとに独立して持つ。系譜とは、起動時の最初のタブ（または手動で開いた別タブ）と、
  そこから `window.open` / `target="_blank"` で派生したポップアップ/ウィンドウの一族で、
  `page.opener()` の連鎖で判定する。系譜内のページは操作バーの状態を共有し、別系譜には影響しない。
  手動で開いた別タブ（`Ctrl+T` 等、opener が無いページ）は**初期OFF**の独立グループになり、
  そのタブの操作バーで ON にするまで撮影されない（起動時の最初のグループだけ `start_recording` に従う）。
- **保存先は「起動ごと」→「系譜ごと」の 2 段**: `output_dir` の直下に起動 1 回分の
  **セッションフォルダ**（`YYYY-MM-DD_HHMMSS`。`config.session_stamp()`）を 1 段挟み、
  その中を系譜ごとの `lineage-<id>/`（ダウンロードは `lineage-<id>/downloads/`）に分ける。
  **`log.txt` と `index.csv` もセッションフォルダ直下**に置かれる（`output_dir` 直下ではない）。

  ```
  output/2026-08-16_143025/          # 起動 1 回分。受け渡しはこのフォルダを丸ごと渡せば済む
  ├─ log.txt / index.csv
  └─ lineage-20260814101105674/      # タブ系譜ごと
     ├─ *.png / *.txt / *_part.txt
     └─ downloads/
  ```

  `<id>` はその系譜を作った時刻（ミリ秒まで・区切りなし）で、ログの `lineage-<id>`
  表記＝保存フォルダ名と一致するため、ログから保存先をそのまま辿れる。フォルダは保存時に必要に応じて作成する。
  セッション粒度は秒までで、同一秒に二重起動するとまれにフォルダを共有するが、`mkdir` の `exist_ok` と
  同じ許容範囲として扱っている。
- **SPA検知**: 中身変化の検出はページ側（`badge.js`）がイベント駆動で行う。`MutationObserver` で
  DOM 変化を捉え、`settle_delay` ぶん変化が止まって「落ち着いた」ら対象の innerText を短いハッシュ
  （コンテンツ署名）にし、前回保存時と署名が異なるときだけ Python へ通知して保存する（重複除外＋
  描画途中の撮影回避）。監視対象はセレクタ指定時はその要素、未指定時はページ主要部（`main`/`article`、
  無ければ本文全体）。`history.pushState` 等のルート変化はフックして基準を取り直すだけにし、URL変化
  側の1枚と二重に撮らない。記録ONがマスタースイッチで、SPA検知は記録ON中のみ動く。従来の「Python が
  毎 tick 全ページの署名を評価するポーリング」を廃したので、変化が無い間は署名計算が走らない。
- 操作バーは各ページへ `add_init_script` で注入し、**Shadow DOM** の中に作る。サイト側 CSS の
  影響を受けず、`document.querySelectorAll` にも紛れ込まないため、全文/一部抜き出しにバーの
  文言が混ざらない。スクリーンショット撮影の瞬間だけバーを隠すので、保存物（png/txt/_part.txt）
  にも写り込まない。保存が終わるとバーを一瞬フラッシュして「保存した」ことを知らせる。
- バー右端の**「透過」トグル**（枠なしの目アイコン）で、バーを一時的に半透明にして下に隠れた
  ページ内容を確認できる（見た目だけのローカル状態で、記録状態や保存物には影響しない）。
- バーはこのほかに次を持つ。文言は `badge.py` の `_BADGE_CONFIG` に集約してある。
  - **撮影カウンタ**（`本セッション N 枚`）… 保存できた枚数だけを数える（全滅した回は数えない）。
    動作している実感と、意図しない連写の早期発見のために常時表示する。保存に失敗した回は
    フラッシュを失敗色にして成功と区別する。
  - **「保存先」ボタン** … セッションフォルダを OS のファイルマネージャで開く。
    撮り終わったフォルダをそのまま渡せる導線。
  - **セレクタ履歴** … 確定したセレクタを `datalist` の候補として入力欄に出す（最近使った順・上限あり）。

## 動作条件

- Windows
- Microsoft Edge または Google Chrome がインストール済み（既定は Edge 優先→無ければ Chrome。`config.ini` の `browser` で片方に固定も可能。`channel="msedge"` / `"chrome"` でシステムのブラウザを使う）
- 開発・ビルド時のみ Python 3.10+（配布した exe の実行に Python は不要）

## 既知の制限（非 HTML ページ）

Edge 実機で確認した挙動（Edge 152）。クラッシュはせず、処理は握られて続行する。

- **PDF（Edge 内蔵ビューア）はテキストが保存されない**。`.png` は表示中ページが画像として
  保存されるが、`.txt` / `_part.txt` は**空**になる（ビューアが本文 DOM を持たないため）。
  `page.title()` も空を返すので、ファイル名末尾の識別名は URL 由来のフォールバックになる。
  → **PDF の証跡は画像（.png）でのみ残る**と理解しておくこと。テキストが要るなら別途 PDF を保存する。
- **Excel / Word など Edge が描画しない形式はダウンロードされる**ため、この制限は当てはまらない。
  タブ内では開かず download イベントが飛び、`downloads/` へ**元ファイルのまま保存**される。
- **`edge://` 系（`edge://settings` 等）の特権ページには操作バーが注入されない**
  （ブラウザが外部スクリプト注入を禁止する領域のため）。スクリーンショット自体は撮れる。

## リポジトリ構成

`src/` レイアウトのパッケージ（`edge_auto_capture`）。役割ごとに分割している。
依存方向は下向きの一方向で循環なし:
`app →（capture / config / badge）→ infra`、`capture → badge`、`config → infra`。
`infra` は Playwright 非依存で、`config`（設定読み込み）も同様なので実 Edge 無しでテストできる。
ページ側 JS は実ファイル `badge.js` に置き、エディタ/リンタで構文検査できるようにしてある。

```
edge-auto-capture/
├─ src/
│  └─ edge_auto_capture/
│     ├─ __init__.py      __version__ の再エクスポートのみ（重い import を置かない）
│     ├─ __main__.py      python -m edge_auto_capture の入口（cli() を呼ぶだけ）
│     ├─ app.py           エントリ＋監視セッション（CaptureSession・cli()）
│     ├─ capture.py       1ページ分の保存処理（撮影実行器 CaptureRunner）・ページ操作ヘルパ
│     ├─ config.py        設定（Config / config.ini の load_config）
│     ├─ infra.py         基盤ユーティリティ（パス・ログ・致命エラー通知・一時プロファイル掃除）
│     ├─ lineage.py       タブ系譜（lineage）の識別・保存先規約と解決レジストリ
│     ├─ browser.py       Edge/Chrome の起動候補と起動オプションの組み立て
│     ├─ badge.py         操作バーのページ側JS組み立て（表示文言・バインディング名を設定JSONへ）
│     ├─ badge.js         操作バーのページ側JS本体（実ファイル・package-data）
│     ├─ default_config.ini  既定の設定テンプレート（実ファイル・package-data）
│     └─ downloads.py     ダウンロードの保存先解決とファイル退避
├─ tests/                 テストと conftest.py（構成は下の「テスト」節）
├─ .github/workflows/ci.yml  CI（ruff+mypy / pytest / smoke --strict）
├─ pyproject.toml         依存とパッケージ設定
├─ README.md              このファイル（開発者向け）
├─ BUILD.md               配布用 exe のビルド・署名・配布の手順
├─ CONTRIBUTING.md        触る人向けの落とし穴・作業環境・検証手順
├─ USAGE.txt              配布物(exe)に同梱する利用者向けの使い方（Shift-JIS）
├─ LICENSE                MIT License
└─ build.ps1              配布用 exe のビルド（PyInstaller）
```

`USAGE.txt` / `build.ps1` は配布素材・スクリプトなのでルート据え置き
（`src/` へは入れない）。生成物（`build/` `dist/` `output/` `__pycache__/` `*.spec`・
`src/edge_auto_capture.egg-info/`・実行時に生成される `config.ini`）は Git 管理外。

既定の設定テンプレートは `src/edge_auto_capture/default_config.ini` に 1 つだけ置き、
`badge.js` と同じ package-data として配る。`config.py` が自己修復（`config.ini` の欠落・
破損時）に書き出す原本もこれで、`build.ps1` が配布フォルダへ置く `config.ini` もこれの写し。
**中身を `config.py` の文字列リテラルとして持たないこと**（二重管理になり、設定項目を
足すたびに 2 箇所を直すことになる）。

## 開発時の実行

```bash
pip install -e .
python -m edge_auto_capture
```

`src/` レイアウト化（#81）により `python edge_auto_capture.py` は使えなくなった。
`pip install -e .` 済みなら `edge-auto-capture` コマンドでも同じものが起動する。

挙動は実行時のカレントディレクトリの `config.ini` で設定する（下表）。
**この `config.ini` はリポジトリに無く、初回起動時にカレントディレクトリへ自動生成される**
（同梱テンプレート `src/edge_auto_capture/default_config.ini` の写し。`.gitignore` 済み）。
実際の操作方法は `USAGE.txt` を参照。停止は Ctrl+C かブラウザのウィンドウを閉じる。

### 設定（config.ini）

| キー | 意味 |
|------|------|
| `start_url` | 起動時に最初に開くページ（空なら about:blank） |
| `browser` | 使うブラウザ（`edge` / `chrome`）。指定するとそのブラウザだけを起動。空なら Edge→Chrome の順で自動選択 |
| `edge_path` | Edge 実行ファイルのパス（空なら自動検出。非標準インストール時のみ） |
| `chrome_path` | Chrome 実行ファイルのパス（空なら自動検出。非標準インストール時のみ） |
| `output_dir` | 保存先。相対なら本体/exe と同じ場所基準、絶対パスも可 |
| `settle_delay` | 変化検知後、描画が落ち着くまで待つ秒数。SPA 検知経由の撮影ではページ側で既に待っているため、撮影前の sleep は省く（二重待ち回避） |
| `load_timeout` | ページ読み込み待ちの上限（ミリ秒） |
| `eval_timeout` | ページ側 JS（本文取得・撮影の合図）の実行を待つ上限（ミリ秒）。重い処理で固まったページを打ち切って次へ進むための保険 |
| `skip_urls` | 撮らない URL（カンマ区切り）。前方一致で判定（クエリ付きでも効く）。`* ? [` を含めるとワイルドカード（fnmatch）扱い |
| `allow_urls` | 撮る URL をこれだけに絞る（カンマ区切り・空なら無効）。指定すると合致しない URL は全スキップ。`skip_urls` も併用可（合致しても `skip_urls` に当たれば撮らない）。判定は `skip_urls` と同じ前方一致/ワイルドカード |
| `target_selector` | 一部抜き出し／SPA検知の対象 CSS セレクタの初期値（バーで実行時に変更可・空可） |
| `hide_selectors` | 撮影中だけ隠す要素の CSS セレクタ（カンマ区切り・空可）。同意バナーや追従ヘッダが証跡に被るのを防ぐ。撮影の瞬間だけ `visibility:hidden` にして撮影後に戻す |
| `start_recording` | 起動直後に記録を開始するか（`false`=待機で起動、`true`=起動時から記録ON） |
| `profile_dir` | 再利用するブラウザプロファイルの場所（空なら毎回まっさらな使い捨て＝既定）。指定するとログイン状態などを保存し次回へ引き継ぐ。相対なら本体/exe と同じ場所基準。指定フォルダに Cookie・認証情報がディスク保存される点に注意 |

### CSSセレクタ（実装上の注意）

`target_selector`（＝バーの入力値）は 2 か所で使う。用途で参照する API が違う点に注意する。

- **`_part.txt` の抽出**: Playwright の `page.locator(sel)` → CSS に加え Playwright 独自記法
  （`text=` / `:has-text()` / `xpath=` など）も使える。
- **SPA検知の署名**: ページ側 `document.querySelectorAll(sel)` → **標準 CSS のみ**。
  セレクタ未入力のときは主要部（`main`/`article`/本文）を自動監視するので、SPA検知にセレクタは必須ではない。

したがって SPA検知でセレクタを使うなら**標準 CSS**にすること（独自記法は SPA検知では無反応になる）。
書き方・調べ方・確認方法（一致件数）など利用者向けの説明は `USAGE.txt` にまとめている。

### テスト

テストは 2 系統ある。**回し方と合否の見方は [CONTRIBUTING.md](CONTRIBUTING.md) §3「検証手順（4 点セット）」が正**
（`--strict` の要否、ブラウザ不在時の `SKIP` の扱い、CI のジョブ構成を含む）。ここでは何を守っているかだけを書く。

**1. ユニットテスト（pytest・速い／実 Edge 不要）**

実 Edge を使わずに、間違えやすいロジックと「微妙な仕様」を回帰から守る。
守っている範囲は大きく 4 つ。

- **純粋関数と判定ロジック** — ファイル名の安全化、URL 判定（`should_capture`）、
  設定の既定値・自己修復、タブ系譜の解決、起動候補の組み立て
- **「微妙な仕様」の固定** — 保存ステップの集約（`_step`）、ページ側 JS のハング保護（`try_eval`）、
  撮影キューの合流、書き込み先の退避（`resolve_writable_dir`）、多重起動抑止、
  操作バー以外からの呼び出しを弾く合言葉(token)照合
- **言語境界・パッケージ境界の一致** — バインディング名の出所が `badge.py` の `BIND_*` 1 箇所で
  あること（`badge.js` 側に名前のリテラルが無いこと）、`badge.js` と `default_config.ini` が
  package-data として宣言・同梱されていること、`USAGE.txt` の Shift-JIS 往復一致。
  **どれも壊れても他の 3 点セットが落ちない**ので、テストだけが守っている
- **起動シーケンスと入口** — `cli()` の起動ログの順序・終了コード

**テストファイルはソース側のモジュール構成に合わせてある**（どこに足すか迷わないように）。
一覧は `ls tests/` で見られるので、ここには書かない（増減のたびにこの節が腐るため）。

SPA検知の落ち着き判定はページ側（`badge.js`）へ移したため、その回帰確認はスモークテストが担う。

**2. スモークテスト（実 Edge/Chrome・遅い）**

操作バーの JS（`badge.js`）が実際に構築でき、ページ側ヘルパ（署名/本文取得/バー隠し）と
SPA検知の監視（本文を変えると `__eac_spa_changed` が発火する一連）が例外なく動くかを確認する。
**`badge.js` を守るのはこれだけで、pytest では守れない。**

**変更時に踏みやすい落とし穴（知らないと無言で壊す言語境界・文字コード・バージョン境界）は
[CONTRIBUTING.md](CONTRIBUTING.md) §1 にまとめてある。触る前にそちらを読むこと。**
一覧はここへ写さない（根治して消えた項目を警告し続ける状態になる）。

## 配布用 exe のビルド・配布

手順は **[BUILD.md](BUILD.md)** に分けてある（ビルド・コードサイニング署名・配布方法・
配布前の確認・配布先 IT への許可依頼テンプレート）。読む人が別なのでここには写さない。

## ライセンス

本ツールは [MIT License](LICENSE)（著作権表示: 2026 lowbrain）で公開する。

同梱する [Playwright](https://playwright.dev/) は Apache-2.0。再配布時のライセンス表記は
`build.ps1` が生成する `THIRD-PARTY-NOTICES.txt` に含めて配布物へ同梱する。
