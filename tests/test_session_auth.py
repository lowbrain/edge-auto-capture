"""CaptureSession の合言葉（token）照合のユニットテスト。

公開バインディング（__eac_* 群）は全ページの window に出るため、閲覧中サイトの
スクリプトからも呼べてしまう。各コールバックが token を照合し、一致しない呼び出しを
無視する（＝記録状態・セレクタを勝手に変えさせない・状態を漏らさない）ことを守る。

実 Edge は不要（コールバックを直接呼ぶ純粋なロジックの検証）。
"""

import asyncio
import inspect

import pytest
from conftest import RecRunner

from edge_auto_capture import app as app_mod
from edge_auto_capture import badge
from edge_auto_capture.app import CaptureSession, GroupState, _url_key
from edge_auto_capture.config import Config


def _session() -> CaptureSession:
    # context はここでは使わない（コールバックが token 照合で早期 return する経路のみ検証）。
    return CaptureSession(context=None, config=Config())


class _Page:
    """opener() を持つ最小のページ代役（グループ解決・撮影経路の検証用）。

    setup() を通す総当たり（下の _ExposingContext）では監視配線も走るため、page.on を
    受け取れるようにしてある（記録はしない。配線そのものは test_session.py が見ている）。
    """

    url = "https://example.test/"

    async def opener(self):
        return None

    def on(self, event, handler) -> None:
        pass


def _seeded_session(**state) -> tuple[CaptureSession, _Page]:
    """1 ページを root として seed 済みのセッションと、その root ページを返す。

    state は GroupState の初期値（on / spa_on / selector）。runner は記録用スタブへ差し替える。
    種入れは setup() と同じくレジストリの seed_root で行う（#48 以降、session.groups /
    session.page_root は読み取り専用ビューなので外から書けない）。
    """
    s = _session()
    s.runner = RecRunner()
    page = _Page()
    s._lineage.seed_root(
        page,
        GroupState(
            on=state.get("on", False),
            spa_on=state.get("spa_on", False),
            selector=state.get("selector", ""),
        ),
    )
    return s, page


def test_token_is_random_per_session():
    a, b = _session(), _session()
    assert a.token and b.token
    assert a.token != b.token


def test_authorized_matches_only_exact_token():
    s = _session()
    assert s._authorized(s.token) is True
    assert s._authorized("wrong") is False
    assert s._authorized(None) is False
    assert s._authorized("") is False


def test_toggle_ignored_without_token():
    # 合言葉不一致では source も触らず早期 return する（グループを作りも変えもしない）。
    s = _session()
    asyncio.run(s.on_toggle(None, token="wrong"))
    assert s.groups == {}  # 何のグループ状態も生まれない


def test_set_selector_ignored_without_token():
    s = _session()
    asyncio.run(s.on_set_selector(None, token="wrong", value=".evil"))
    assert s.groups == {}  # 外部からセレクタを書き換えられない


def test_spa_changed_ignored_without_token():
    # 合言葉不一致（操作バー以外）からの変化通知は無視する（source を触らず早期 return）。
    s = _session()
    asyncio.run(s.on_spa_changed(None, token="wrong", sig="x"))  # 例外なく無視される
    assert s.groups == {}


def test_spa_changed_ignored_when_not_recording():
    # 正規 token でも、そのページのグループが記録OFF なら撮らない（記録ON がマスタースイッチ）。
    s, page = _seeded_session(on=False, spa_on=True)
    asyncio.run(s.on_spa_changed({"page": page}, token=s.token, sig="x"))
    assert s.runner.calls == []  # 記録OFF なので撮らない


@pytest.mark.parametrize("token", ["wrong", None, ""])
def test_get_state_hides_real_state_without_token(token):
    # 不一致には実際の状態を返さず既定値を返す（外部への情報漏れを防ぐ）。source も触らない。
    s, page = _seeded_session(on=True, spa_on=True, selector=".secret")
    state = asyncio.run(s.get_state(None, token=token))
    # 記録状態やセレクタは伏せるが、撮影カウンタ（count）は秘匿情報ではないので返す。
    # セレクタ履歴は利用者が入れた候補なので非正規呼び出しには返さない（空）。
    assert state == {
        "recording": False, "spa": False, "selector": "", "count": 0, "history": [],
    }


def test_get_state_returns_real_state_with_token():
    # 正規 token では、問い合わせ元ページが属するグループの実状態を返す（撮影カウンタも同梱）。
    # セレクタ履歴も同梱する（遷移後のバーが datalist 候補を失わない）。
    s, page = _seeded_session(on=True, spa_on=False, selector=".ok")
    state = asyncio.run(s.get_state({"page": page}, token=s.token))
    assert state == {
        "recording": True, "spa": False, "selector": ".ok", "count": 0, "history": [],
    }


# --------------------------------------------------------------------------- #
# 公開バインディング全部の総当たり（#124）
#
# 上の 4 本は 8 個のうち 4 個を名指しで見に行く形だった。名指しなのでバインディングが
# 増えても検査対象は増えず、実際に on_shot / on_open_folder / on_spa_toggle /
# on_commit_selector は照合の 2 行を消しても 4 点セットが全部緑で通る状態だった。
#
# ここでは setup() を実際に通して「何が公開されたか」を採り、その全部を不正な token で
# 叩いて何も動かないことを見る。tests/test_badge.py の
# test_setup_exposes_exactly_the_declared_bindings が「公開のし忘れ」に対して取っている
# のと同じ形（宣言ではなく実挙動を見る）を、認可の側へ適用したもの。
# --------------------------------------------------------------------------- #


class _ExposingContext:
    """setup() を通し、公開されたバインディングを {名前: ハンドラ} で捕まえる代役。

    test_badge.py の _BindingContext（名前だけ）・test_session.py の _SetupContext
    （名前とイベント名）と役が違う。こちらは**ハンドラ本体**が要る（実際に呼んで照合を
    確かめるため）ので別に持つ。4 つ目の用途が出たら conftest.py へ寄せること。
    """

    def __init__(self, pages) -> None:
        self.pages = list(pages)
        self.handlers: dict[str, object] = {}

    async def expose_binding(self, name, callback) -> None:
        self.handlers[name] = callback

    async def add_init_script(self, script) -> None:
        pass

    def on(self, event, handler) -> None:
        pass


def _snapshot(session, page) -> dict:
    """照合が効いているかを判定するための、外から見える状態一式。

    不正な token での呼び出しの前後でこれが一致すれば「無視された」と言える。
    **判定材料を減らさないこと** — 例えば runner.calls を外すと on_shot の照合欠落が
    素通りする（記録状態を変えずに撮るだけのコールバックなので、他の欄は動かない）。
    """
    grp = session.groups[page]
    return {
        "on": grp.on,
        "spa_on": grp.spa_on,
        "selector": grp.selector,
        "shots": session.shots,
        "history": list(session.selector_history),
        "spawned": list(session.runner.calls),
        "last_url_key": dict(session.last_url_key),
        "groups": len(session.groups),
    }


def _extra_args(handler) -> tuple:
    """ハンドラが source / token の後に取る引数へ、それらしい文字列を詰める。

    値の中身に意味は無く、「照合が無ければ状態が動く」呼び方にするためだけのもの。
    引数の数は署名から採るので、**引数を増やしたコールバックを足しても表を直す必要は無い**
    （固定の対応表にすると、そこが新しい書き忘れの置き場所になる）。
    現在の追加引数は value: str と sig: object のどちらかで、文字列で両方を満たす。
    """
    params = list(inspect.signature(handler).parameters)   # source / token / 追加分
    return (".evil",) * max(0, len(params) - 2)


@pytest.mark.parametrize("bad_token", ["wrong", None, "", "x" * 32])
def test_every_exposed_binding_ignores_a_wrong_token(bad_token, monkeypatch):
    """setup() が公開した**全ての**バインディングが、token 不一致では何も変えない。

    照合を書き忘れても、例外もログも出ず見た目も変わらないまま、そのボタンだけが
    閲覧中サイトから自由に押せる状態になる（記録の開始/停止・連写・セレクタ書き換え・
    保存先フォルダを開く）。型でも lint でも落ちないので、ここで縛る。

    **公開の一覧を BIND_* から読まず setup() の実挙動から採る。** 宣言を用意しても
    それを使わない実装に変われば同じ穴が空くため（test_badge.py の
    test_setup_exposes_exactly_the_declared_bindings と同じ理由）。バインディングを
    増やせば、このテストの対象も自動で増える。

    グループは記録ON・SPA検知ON・セレクタ設定済みで始める。**どれかを OFF にしないこと** —
    on_spa_changed は記録OFF か SPA検知OFF なら照合を通っても撮らないので、
    照合の欠落が見えなくなる。
    """
    opened: list = []
    # 照合が抜けていれば実際に OS のファイルマネージャが開く。差し替えて呼び出しを記録する。
    monkeypatch.setattr(app_mod, "open_in_file_manager", lambda path: opened.append(path) or True)

    async def scenario() -> list[str]:
        page = _Page()
        ctx = _ExposingContext([page])
        session = CaptureSession(ctx, Config(start_recording=True, target_selector=".seed"))
        session.runner = RecRunner()
        await session.setup()
        # setup() の種入れは spa_on=False 固定なので、ここで ON にしておく（docstring 参照）。
        session.groups[page].spa_on = True

        before = _snapshot(session, page)
        leaks = []
        for name, handler in ctx.handlers.items():
            result = await handler({"page": page}, bad_token, *_extra_args(handler))
            if _snapshot(session, page) != before:
                leaks.append(f"{name}: 状態が変わった")
            if opened:
                leaks.append(f"{name}: 保存先フォルダを開いた")
                opened.clear()
            # 状態を返すのは get_state だけ。不一致には実状態を伏せた既定値を返す。
            if name == badge.BIND_GETSTATE:
                if result != {
                    "recording": False, "spa": False, "selector": "",
                    "count": session.shots, "history": [],
                }:
                    leaks.append(f"{name}: 実状態を返した（{result}）")
            elif result is not None:
                leaks.append(f"{name}: 値を返した（{result}）")
        return leaks

    leaks = asyncio.run(scenario())
    assert leaks == [], (
        f"token 照合が効いていないバインディング: {leaks}。"
        " 各コールバック冒頭の `if not self._authorized(token): return` を確認する"
    )


def test_the_roundup_actually_covers_every_binding():
    """総当たりが空振りしていないこと（公開が 0 個ならテストは無条件に緑になる）。

    上のテストは「公開された全部を回す」形なので、公開の採取に失敗して 0 個になっても
    leaks が空のまま緑になる。番人が番をしていない状態を落とすための 1 本。
    """
    async def scenario() -> set:
        ctx = _ExposingContext([_Page()])
        await CaptureSession(ctx, Config()).setup()
        return set(ctx.handlers)

    exposed = asyncio.run(scenario())
    assert exposed == {v for k, v in vars(badge).items() if k.startswith("BIND_")}


# --------------------------------------------------------------------------- #
# _url_key … URL変化の「同じページか」判定キー（フラグメント #... を除く）
# --------------------------------------------------------------------------- #


def test_url_key_strips_fragment():
    # scroll-spy で付くハッシュ違いは同じページとみなす（Vuetify等の二重撮り防止）。
    base = "https://vuetifyjs.com/ja/getting-started/installation/"
    assert _url_key(base) == base
    assert _url_key(base + "#vite309") == base
    assert _url_key(base + "#section-624b") == base
    # ハッシュだけ違う2URLは同一キーになる（＝撮り直さない）。
    assert _url_key(base + "#nuxt") == _url_key(base + "#vite")


def test_url_key_keeps_path_and_query():
    # パスやクエリの違いは別ページとして残す（#以降だけを落とす）。
    assert _url_key("https://a.com/p?q=1#frag") == "https://a.com/p?q=1"
    assert _url_key("https://a.com/x") != _url_key("https://a.com/y")
    assert _url_key("about:blank") == "about:blank"
