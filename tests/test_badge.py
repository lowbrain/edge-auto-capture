"""操作バー（badge.py / badge.js）の言語境界を守るユニットテスト。

CONTRIBUTING §1-5 が「バインディング名は 2 箇所に存在し、片方だけ変えると
**無言失敗する**」と名指ししている箇所を機械的に固定する（#67）。文章としての
警告はあったが、忘れたことを検出する仕組みが無かった。

- badge.py の BIND_* 定数群（Python → expose_binding で公開する名前）
- badge.js の BINDING_NAMES 配列（ページ側で BOUND へ退避し、存在検知の防止のため window から消す名前）
- app.py の CaptureSession.setup() が実際に expose_binding する名前

この 3 つは 1:1 で一致していなければならない。ずれても例外もログも出ず、
操作バーのボタンが黙って効かなくなるだけなので、ここで縛る。
あわせて §1-6 の「callBinding 経由で呼ぶ」も、呼び出し名が BINDING_NAMES に
含まれることとして固定する（直接呼び出しを新たに書かせないための担保）。

実 Edge 不要。setup() を通す最後の 1 本だけは app.py（Playwright 依存）を
import するので、他の 3 本を巻き込まないよう関数内 import にしてある。

実行:
    pip install -e ".[dev]"
    pytest
"""

import re

from edge_auto_capture import badge

# --------------------------------------------------------------------------- #
# badge.js の読み出し（場所の解決は badge.py 自身に任せる）
# --------------------------------------------------------------------------- #


def _badge_js_source() -> str:
    # _badge_js_path() は凍結（PyInstaller）時の _MEIPASS も見るので、パスを
    # ここで組み立て直さず badge 側の解決をそのまま使う。
    return badge._badge_js_path().read_text(encoding="utf-8")


def _js_binding_names() -> set:
    """badge.js の BINDING_NAMES 配列に並ぶ名前を取り出す。

    配列は複数行に分かれているので DOTALL で括弧の中をまとめて取り、
    その中のシングルクォート文字列を拾う（badge.js は引用符に ' を使う）。
    """
    src = _badge_js_source()
    m = re.search(r"BINDING_NAMES\s*=\s*\[(.*?)\]", src, re.DOTALL)
    assert m, "badge.js に BINDING_NAMES の配列が見つからない（定義の書き方を変えたらこの抽出も直す）"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def _py_binding_names() -> set:
    # badge.py 側は BIND_* という命名に集約されている（モジュール docstring と
    # 定数群のコメント参照）。名前で拾うので、新しい BIND_* を足せば自動で対象に入る。
    return {v for k, v in vars(badge).items() if k.startswith("BIND_")}


# --------------------------------------------------------------------------- #
# 設定の渡し方（#99・CONTRIBUTING §1-1）
# --------------------------------------------------------------------------- #


def test_badge_js_is_a_function_expression_without_trailing_semicolon():
    """badge.js は「設定を 1 個受け取る関数式」で、末尾は `}`（セミコロン無し）。

    build_badge_script が `(<badge.js>)(<設定 JSON>);` の形で包むので、末尾に `;` が
    あるだけで構文エラーになる。しかもその失敗はページ側でしか現れず、気づけるのは
    実ブラウザを起こす smoke だけ（ブラウザ不在なら SKIP）なので、形はここで縛る。
    """
    src = _badge_js_source().strip()
    assert src.endswith("}"), "badge.js の末尾は `}`（セミコロン無し）であること"
    assert re.search(r"^\(C\)\s*=>\s*\{", src, re.MULTILINE), (
        "badge.js の本体は `(C) => {` で始まる関数式であること"
    )


def test_badge_js_has_no_config_placeholder():
    """かつての単純置換の目印（$CONFIG）が残っていないこと（#99 の受入基準）。

    残っていると「置換されない目印」がそのままページへ流れ、参照時に ReferenceError で
    バーが出なくなる。目印が消えたことで badge.js では `${...}` 補間を使ってよくなった
    （実際に CSS の時間を JS 定数から差し込んでいる）。
    """
    assert "$CONFIG" not in _badge_js_source()


def test_build_badge_script_wraps_source_as_a_call():
    """完成スクリプトが `(<badge.js>)(<設定 JSON>);` の形になっていること。

    設定は JS の引数として入るので、固定名は globalThis に一度も載らない（§1-6）。
    """
    script = badge.build_badge_script("tok", 300, ("#x",), "nABC")
    assert script.startswith("(")
    assert script.endswith(");")
    assert _badge_js_source().strip() in script
    # 設定が JSON リテラルとして末尾の呼び出し引数に載る（値は json.dumps 済み）。
    assert '"tok": "tok"' in script
    assert '"ns": "nABC"' in script


# --------------------------------------------------------------------------- #
# BIND_* と BINDING_NAMES の一致（#67・CONTRIBUTING §1-5）
# --------------------------------------------------------------------------- #


def test_binding_names_match_between_python_and_js():
    # 片方だけ足す/直すと無言失敗する（JS 側は try/catch で握るため例外も出ない）。
    # 集合として完全一致であることを縛る。
    assert _py_binding_names() == _js_binding_names()


def test_binding_names_are_not_empty():
    # 上の比較は「両方とも空」でも通ってしまう。抽出が壊れた（badge.js の書き方を
    # 変えた・BIND_* の命名を変えた）ときに気づけるよう、非空であることも見る。
    assert _py_binding_names()


# --------------------------------------------------------------------------- #
# callBinding の呼び出し名（CONTRIBUTING §1-6）
# --------------------------------------------------------------------------- #


def test_call_binding_targets_are_all_declared():
    # §1-6 は window.__eac_toggle(...) のような直接呼び出しを禁じ、
    # callBinding('__eac_*', TOK, ...) を使うと定めている。callBinding は BOUND から
    # 引くので、BINDING_NAMES に無い名前を呼ぶと（退避されておらず）黙って何も起きない。
    called = set(re.findall(r"callBinding\('([^']+)'", _badge_js_source()))
    assert called, "badge.js に callBinding の呼び出しが見つからない"
    assert called <= _js_binding_names()


# --------------------------------------------------------------------------- #
# BIND_* と setup() が実際に公開する名前の一致（CONTRIBUTING §1-5）
# --------------------------------------------------------------------------- #


class _BindingContext:
    """setup() が呼ぶ context 側 API の最小代役。公開されたバインディング名だけを記録する。

    tests/test_session.py の _SetupContext が同じ役を厚く演じている（種入れ・監視配線まで
    検証する）が、ここで見たいのは「どの名前が expose_binding されたか」の 1 点だけなので、
    それに要る最小限にとどめる。ページは 0 枚（種入れを走らせない）で足りる。
    """

    def __init__(self) -> None:
        self.pages: list = []
        self.bindings: list = []

    async def expose_binding(self, name, callback) -> None:
        self.bindings.append(name)

    async def add_init_script(self, script) -> None:
        pass

    def on(self, event, handler) -> None:
        pass


def test_setup_exposes_exactly_the_declared_bindings():
    """setup() を実際に通し、公開された名前が BIND_* と過不足なく一致することを見る。

    上の 2 本は badge.py ↔ badge.js の言語境界を縛るが、**そこを通っても
    app.py 側で expose_binding し忘れれば同じように無言失敗する**。ページ側は
    callBinding が BOUND[name] を引けず typeof チェックで undefined を返して終わりなので、
    例外もログも出ずボタンだけが効かなくなる（§1-5 が名指しする失敗の仕方）。

    公開の一覧を宣言（定数・対応表など）から読み取るのではなく setup() を実際に通すのは、
    宣言を用意してもそれを使わない実装に変われば同じ穴が空くため。公開の書き方が
    どう変わっても効くように、外から見える結果（何が公開されたか）だけを見る。
    """
    import asyncio

    from edge_auto_capture.app import CaptureSession
    from edge_auto_capture.config import Config

    async def scenario() -> list:
        ctx = _BindingContext()
        await CaptureSession(ctx, Config()).setup()
        return ctx.bindings

    exposed = asyncio.run(scenario())
    # 同じ名前を 2 度公開していない（Playwright は 2 度目で例外を投げる＝起動できない）。
    assert len(exposed) == len(set(exposed)), f"バインディングの二重公開: {exposed}"
    # 落ちも余りも無い。差分はそのまま「直すべき側」の一覧になる。
    assert set(exposed) == _py_binding_names()
