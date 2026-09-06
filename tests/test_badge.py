"""操作バー（badge.py / badge.js）の言語境界を守るユニットテスト。

CONTRIBUTING §1-5 がかつて「バインディング名は 2 箇所に存在し、片方だけ変えると
**無言失敗する**」と名指ししていた箇所を機械的に固定する（#67）。文章としての
警告はあったが、忘れたことを検出する仕組みが無かった。

**二重管理そのものは #100 で解消した。** 名前の出所は badge.py の BIND_* 1 箇所で、
設定 JSON の bind キーに載って badge.js へ配られる（JS 側に名前のリテラルは無い）。
それでも一致テストは保険として残す — 縛るのは次の 3 つ:

- badge.py の BIND_* 定数群（Python → expose_binding で公開する名前）
- badge.py の _BIND_NAMES（badge.js へ実際に配られる名前。載せ忘れると JS 側が引けない）
- app.py の CaptureSession.setup() が実際に expose_binding する名前

ずれても例外もログも出ず、操作バーのボタンが黙って効かなくなるだけなので、ここで縛る。
あわせて §1-6 の「callBinding 経由で呼ぶ」も、呼び出しが C.bind の既知のキーを
使っていることとして固定する（直接呼び出し・名前のリテラルを書かせないための担保）。

実 Edge 不要。setup() を通す最後の 1 本だけは app.py（Playwright 依存）を
import するので、他を巻き込まないよう関数内 import にしてある。

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


def _shipped_binding_names() -> set:
    """badge.js へ実際に配られるバインディング名（設定 JSON の bind キーの値）。

    #100 より前は badge.js 側の BINDING_NAMES 配列から拾っていた。いまは JS に名前が
    無く、Python から配られた値をそのまま使うので、「配られる側」をここで見る。
    """
    return set(badge._BIND_NAMES.values())


def _js_bind_keys() -> set:
    """badge.js が参照している C.bind のキー（callBinding の第1引数など）。"""
    return set(re.findall(r"C\.bind\.([A-Za-z0-9_]+)", _badge_js_source()))


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
# BIND_* と JS へ配られる名前の一致（#67 / #100・CONTRIBUTING §1-5）
# --------------------------------------------------------------------------- #


def test_binding_names_match_between_python_and_js():
    # BIND_* を足しても _BIND_NAMES に載せ忘れれば、JS 側は名前を引けず無言失敗する
    # （callBinding が undefined を返して終わり。例外もログも出ない）。集合として
    # 完全一致であることを縛る。#100 より前は badge.js 側の配列と突き合わせていた。
    assert _py_binding_names() == _shipped_binding_names()


def test_binding_names_are_not_empty():
    # 上の比較は「両方とも空」でも通ってしまう。抽出が壊れた（BIND_* の命名を変えた・
    # _BIND_NAMES を消した）ときに気づけるよう、非空であることも見る。
    assert _py_binding_names()


def test_badge_js_has_no_binding_name_literals():
    """badge.js にバインディング名のリテラルが 1 つも無いこと（#100 の受入基準）。

    名前を JS 側にも書くと二重管理が復活し、片方だけ変えたときに無言で壊れる。
    退避＋削除の対象（BINDING_NAMES）も呼び出しの第1引数も、Python から配られた
    C.bind を使うこと。__eac_ で始まる文字列リテラルが無いことまで見て、書き戻しを止める。
    """
    src = _badge_js_source()
    for name in _py_binding_names():
        assert name not in src, f"badge.js にバインディング名のリテラルが残っている: {name}"
    assert not re.search(r"""['"]__eac_""", src), (
        "badge.js に __eac_ で始まる文字列リテラルが残っている（名前は C.bind から取ること）"
    )
    assert "Object.values(C.bind)" in src, (
        "badge.js の BINDING_NAMES は C.bind から導くこと（名前を書き戻さない）"
    )


# --------------------------------------------------------------------------- #
# callBinding の呼び出し名（CONTRIBUTING §1-6）
# --------------------------------------------------------------------------- #


def test_call_binding_targets_are_all_declared():
    # §1-6 は固定名の直接呼び出しを禁じ、callBinding(C.bind.<キー>, TOK, ...) を使うと
    # 定めている。callBinding は BOUND から引くので、配られていないキー（undefined）を
    # 渡すと退避を引けず黙って何も起きない。使っているキーが Python 側の _BIND_NAMES に
    # 全て存在することを縛る。
    called = set(re.findall(r"callBinding\(C\.bind\.([A-Za-z0-9_]+)", _badge_js_source()))
    assert called, "badge.js に callBinding(C.bind.*) の呼び出しが見つからない"
    assert called <= set(badge._BIND_NAMES)
    # C.bind の参照（コメント中の例も含む）が全て実在のキーであること。綴り違いは
    # undefined になり、やはり無言で効かなくなる。
    assert _js_bind_keys() <= set(badge._BIND_NAMES)


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
