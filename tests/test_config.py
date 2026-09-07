"""設定読み込み（config.py）のユニットテスト。

config.ini のパース・既定値へのフォールバック・自己修復・保存先の解決と
セッションフォルダ・撮影対象 URL の判定（should_capture）を守る。
実 Edge 不要（config は infra だけに依存し Playwright を import しない）。

末尾に「設定キーの出所の一致」を縛る一群がある（#115）。こちらは他と毛色が違い、
tests/test_docs_refs.py や test_packaging.py と同じ「漏れても 4 点セットのどれも
落ちないが、後で効いてくる」型の不変条件。

実行:
    pip install -e ".[dev]"
    pytest
"""

import ast
import configparser
import re
from pathlib import Path

import pytest

from edge_auto_capture import capture, infra, lineage
from edge_auto_capture import config as config_mod
from edge_auto_capture.config import Config, ConfigFatalError, load_config, should_capture

# session_stamp の実装本体への参照（conftest の autouse フィクスチャが "" へ差し替える前に押さえる）。
# 差し替え後も本物の書式を検証できるようにするため。
_REAL_SESSION_STAMP = config_mod.session_stamp

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Config 既定値
# --------------------------------------------------------------------------- #


def test_config_defaults():
    c = Config()
    assert c.start_url == "about:blank"
    assert c.output_dir == Path("output")
    assert c.eval_timeout == 5000
    assert c.start_recording is False
    assert "" in c.skip_urls  # 空URLは常にスキップ対象
    assert c.allow_urls == ()  # 既定は無効（撮る URL を絞らない）


def test_eval_timeout_sec_converts_milliseconds_to_seconds():
    # config.ini はミリ秒、コード内（asyncio）は秒。換算点は Config へ 1 本化してある（#56）。
    assert Config().eval_timeout_sec == 5.0
    assert Config(eval_timeout=250).eval_timeout_sec == 0.25


# --------------------------------------------------------------------------- #
# should_capture（skip_urls / allow_urls / 前方一致・fnmatch）
# --------------------------------------------------------------------------- #


def test_should_capture_default_skips_blank_and_empty():
    # 既定（skip_urls=("about:blank","")）。about:blank と空URLは撮らない。
    c = Config()
    assert should_capture("https://example.com/", c) is True
    assert should_capture("about:blank", c) is False
    assert should_capture("", c) is False


def test_should_capture_empty_pattern_only_matches_empty_url():
    # skip_urls の "" 番兵は「空URL専用」。前方一致で全URLに化けてはいけない。
    c = Config(skip_urls=("",))
    assert should_capture("", c) is False
    assert should_capture("https://example.com/", c) is True


def test_should_capture_skip_is_prefix_match_so_query_still_skipped():
    # 完全一致だとクエリ付きで漏れていた。前方一致でクエリ付きも弾く。
    c = Config(skip_urls=("https://skip.me", ""))
    assert should_capture("https://skip.me", c) is False
    assert should_capture("https://skip.me?ref=1", c) is False
    assert should_capture("https://skip.me/logout", c) is False
    assert should_capture("https://keep.me/", c) is True


def test_should_capture_skip_supports_wildcards():
    # * ? [ を含むパターンは fnmatch 扱い（前方一致では書けない末尾一致など）。
    c = Config(skip_urls=("*://*/logout", ""))
    assert should_capture("https://a.example.com/logout", c) is False
    assert should_capture("http://b.test/logout", c) is False
    assert should_capture("https://a.example.com/home", c) is True


def test_should_capture_allow_urls_whitelist_skips_others():
    # allow_urls 指定時は、合致しない URL をすべてスキップ。
    c = Config(allow_urls=("https://example.com/",), skip_urls=("",))
    assert should_capture("https://example.com/page", c) is True
    assert should_capture("https://other.com/", c) is False


def test_should_capture_allow_urls_supports_wildcards():
    c = Config(allow_urls=("https://*.example.com/*",), skip_urls=("",))
    assert should_capture("https://docs.example.com/a", c) is True
    assert should_capture("https://example.org/a", c) is False


def test_should_capture_skip_urls_still_apply_within_allow():
    # allow を通っても skip に当たれば撮らない（ブラックリストが優先）。
    c = Config(
        allow_urls=("https://example.com",),
        skip_urls=("https://example.com/logout", ""),
    )
    assert should_capture("https://example.com/page", c) is True
    assert should_capture("https://example.com/logout", c) is False


# --------------------------------------------------------------------------- #
# load_config
# --------------------------------------------------------------------------- #


def _write_config(monkeypatch, tmp_path, body: str) -> Path:
    """一時 config.ini を作り、config.CONFIG_PATH をそこへ向ける。"""
    cfg = tmp_path / "config.ini"
    cfg.write_text(body, encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg)
    return cfg


def test_load_config_valid(monkeypatch, tmp_path):
    out = tmp_path / "out"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
start_url = https://example.com
output_dir = {out}
settle_delay = 0.4
load_timeout = 3000
eval_timeout = 4000
skip_urls = about:blank, https://skip.me
allow_urls = https://example.com/, https://*.example.com/*
target_selector = .price
hide_selectors = #cookie-banner, .sticky-header
start_recording = true
""",
    )
    c = load_config()
    assert c.start_url == "https://example.com"
    assert c.output_dir == out
    assert c.settle_delay == 0.4
    assert c.load_timeout == 3000
    assert c.eval_timeout == 4000
    # 指定した skip_urls ＋ 常に付く空URL。
    assert c.skip_urls == ("about:blank", "https://skip.me", "")
    # allow_urls は指定値のみ（空URL番兵は付けない）。
    assert c.allow_urls == ("https://example.com/", "https://*.example.com/*")
    assert c.target_selector == ".price"
    # カンマ区切りをタプル化（空要素は落とす）。
    assert c.hide_selectors == ("#cookie-banner", ".sticky-header")
    assert c.start_recording is True


def test_load_config_missing_lines_use_defaults(monkeypatch, tmp_path):
    # 項目行そのものが無い場合は Config の既定値へフォールバックする。
    out = tmp_path / "out"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
output_dir = {out}
""",
    )
    c = load_config()
    d = Config()
    assert c.settle_delay == d.settle_delay
    assert c.load_timeout == d.load_timeout
    assert c.eval_timeout == d.eval_timeout
    assert c.hide_selectors == d.hide_selectors == ()
    assert c.start_recording is d.start_recording
    assert c.start_url == "about:blank"


def test_load_config_relative_output_dir_resolves_under_base_dir(monkeypatch, tmp_path):
    # 相対パスは BASE_DIR 基準に固定される（exe 隣の output\ に確実に保存するため）。
    # load_config は config モジュールに import 済みの BASE_DIR を参照するのでそちらを差し替える。
    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    _write_config(
        monkeypatch,
        tmp_path,
        """[capture]
output_dir = mydata
""",
    )
    c = load_config()
    assert c.output_dir == tmp_path / "mydata"
    assert c.output_dir.is_absolute()


def test_load_config_empty_start_url_becomes_about_blank(monkeypatch, tmp_path):
    out = tmp_path / "out"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
start_url =
output_dir = {out}
""",
    )
    c = load_config()
    assert c.start_url == "about:blank"


def test_load_config_reads_bom_prefixed_file(monkeypatch, tmp_path):
    # メモ帳保存等で BOM が付いても読めること。utf-8 のままだと最初の見出しが
    # 壊れて MissingSectionHeaderError → 起動不能になっていた。
    out = tmp_path / "out"
    cfg = tmp_path / "config.ini"
    # utf-8-sig で書くと先頭に BOM が付く。
    cfg.write_text(
        f"[capture]\noutput_dir = {out}\nstart_url = https://example.com\n",
        encoding="utf-8-sig",
    )
    assert cfg.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM が付いていることを確認
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg)
    c = load_config()
    assert c.start_url == "https://example.com"
    assert c.output_dir == out


def test_load_config_missing_file_self_heals(monkeypatch, tmp_path):
    # config.ini が無ければ既定値で作り直して起動する（起動不能にしない）。
    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    cfg = tmp_path / "does-not-exist.ini"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg)
    assert not cfg.exists()
    c = load_config()
    # 既定ファイルが作られ、配布テンプレートと同一の内容になる。
    assert cfg.exists()
    assert cfg.read_text(encoding="utf-8") == config_mod._default_config_text()
    # 既定テンプレートの値で起動する（output は BASE_DIR 配下へ解決）。
    assert c.start_url == "https://www.google.com"
    assert c.output_dir == tmp_path / "output"


def test_load_config_missing_file_uses_defaults_when_unwritable(monkeypatch, tmp_path):
    # 書き出しに失敗しても（読み取り専用等）、メモリ上の既定値で起動する。
    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "does-not-exist.ini")
    monkeypatch.setattr(config_mod, "_write_default_config", lambda: False)
    c = load_config()
    assert c.start_url == "https://www.google.com"
    assert c.skip_urls == ("about:blank", "")
    assert c.output_dir == tmp_path / "output"


def test_load_config_broken_file_self_heals(monkeypatch, tmp_path):
    # [capture] が無い/破損した config.ini は .invalid へ退避し、既定で作り直す。
    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    cfg = _write_config(monkeypatch, tmp_path, "[wrong]\nfoo = bar\n")
    c = load_config()
    # 壊れた元ファイルは消さず退避される（利用者が中身を確認できる）。
    invalid = tmp_path / "config.ini.invalid"
    assert invalid.exists()
    assert invalid.read_text(encoding="utf-8").startswith("[wrong]")
    # 既定 config.ini を作り直し、既定値で起動する。
    assert cfg.read_text(encoding="utf-8") == config_mod._default_config_text()
    assert c.start_url == "https://www.google.com"
    assert c.output_dir == tmp_path / "output"


def test_load_config_corrupt_file_self_heals(monkeypatch, tmp_path):
    # パースできないゴミ（セクション見出しの前に本文）でも退避＆作り直しで起動する。
    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    cfg = _write_config(monkeypatch, tmp_path, "not a config at all\n= = =\n")
    c = load_config()
    assert (tmp_path / "config.ini.invalid").exists()
    assert cfg.read_text(encoding="utf-8") == config_mod._default_config_text()
    assert c.output_dir == tmp_path / "output"


def test_default_config_text_reads_package_data():
    # 既定テキストの出所はパッケージ同梱の default_config.ini ただ 1 つ（#101）。
    # かつては config.py の DEFAULT_CONFIG_TEXT とルートの config.ini が同内容で並び、
    # バイト一致テストで drift を押さえ込んでいた。いまは出所が 1 つなので、
    # 「同梱ファイルを実際に読めている」ことだけを縛る（読めなければ自己修復が空を書く）。
    package_ini = Path(config_mod.__file__).resolve().parent / config_mod.DEFAULT_CONFIG_NAME
    assert package_ini.is_file()
    text = config_mod._default_config_text()
    assert text == package_ini.read_text(encoding="utf-8")
    # 中身が既定テンプレートとして成立していること（空ファイルにすり替わっても気づける）。
    assert text.startswith("[capture]")
    assert "start_url" in text


def test_config_with_defaults_uses_template_values(monkeypatch, tmp_path):
    # 同梱テンプレート（default_config.ini）から作る既定 Config は配布テンプレートの値になる。
    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    c = config_mod._config_with_defaults(Config())
    assert c.start_url == "https://www.google.com"
    assert c.skip_urls == ("about:blank", "")
    assert c.output_dir == tmp_path / "output"


def test_config_with_defaults_survives_missing_package_data(monkeypatch, tmp_path):
    # 同梱テンプレートを読めない（配布物からの欠落・凍結時の同梱漏れ）ときも、
    # ここは「最後の砦」なので起動不能にしない。Config の初期値で組み立てて返す
    # （start_url は about:blank ＝ テンプレート値ではなくコード側の既定）。
    def _boom() -> str:
        raise OSError("default_config.ini が無い")

    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "_default_config_text", _boom)
    c = config_mod._config_with_defaults(Config())
    assert c.start_url == "about:blank"
    assert c.output_dir == tmp_path / "output"


def test_load_config_invalid_number_raises_fatal(monkeypatch, tmp_path):
    # 数値項目の値だけが空/不正だと変換に失敗し、ConfigFatalError で返る
    # （#49: ライブラリ層はプロセスを落とさない。通知と終了は入口 cli の仕事）。
    out = tmp_path / "out"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
output_dir = {out}
settle_delay = not-a-number
""",
    )
    with pytest.raises(ConfigFatalError) as e:
        load_config()
    # 利用者向けの文面（何が起きたか・どこを直すか・元の値）をそのまま載せる。
    msg = str(e.value)
    assert "config.ini の読み込みに失敗しました" in msg
    assert "not-a-number" in msg
    assert "[capture] セクションと各項目の値を確認してください。" in msg


def test_load_config_empty_output_dir_falls_back_to_default(monkeypatch, tmp_path):
    # output_dir が空でもカレントへ落とさず、既定（BASE_DIR/output）へ戻す。
    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    _write_config(
        monkeypatch,
        tmp_path,
        """[capture]
output_dir =
""",
    )
    c = load_config()
    assert c.output_dir == tmp_path / "output"


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("settle_delay = -0.5", "settle_delay は 0 以上にしてください（現在: -0.5）"),
        ("load_timeout = 0", "load_timeout は正の整数にしてください（現在: 0）"),
        ("load_timeout = -100", "load_timeout は正の整数にしてください（現在: -100）"),
        ("eval_timeout = 0", "eval_timeout は正の整数にしてください（現在: 0）"),
        ("eval_timeout = -100", "eval_timeout は正の整数にしてください（現在: -100）"),
    ],
)
def test_load_config_out_of_range_numbers_raise_fatal(monkeypatch, tmp_path, line, reason):
    # 範囲外の数値（0/負数）は暴走・無意味値になるため起動を止める（#49: ConfigFatalError）。
    # 「どの項目がどう不正か」まで文面に出ることを固定する（利用者はこれを見て config.ini を直す）。
    out = tmp_path / "out"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
output_dir = {out}
{line}
""",
    )
    with pytest.raises(ConfigFatalError) as e:
        load_config()
    assert str(e.value) == (
        f"config.ini の読み込みに失敗しました: {reason}\n"
        "[capture] セクションと各項目の値を確認してください。"
    )


def test_load_config_unwritable_output_dir_raises_fatal(monkeypatch, tmp_path):
    # 保存先がどこにも書けない（退避先も全滅）ときも、config は落とさず
    # ConfigFatalError で返す（#49）。文面には元の保存先と直し方を載せる。
    out = tmp_path / "out"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
output_dir = {out}
""",
    )
    monkeypatch.setattr(config_mod, "resolve_writable_dir", lambda p: None)

    with pytest.raises(ConfigFatalError) as e:
        load_config()
    assert str(e.value) == (
        f"保存先フォルダに書き込めませんでした: {out}\n"
        "書き込み可能な場所（例: ドキュメント配下）へ移して実行してください。"
    )


# --------------------------------------------------------------------------- #
# profile_dir（プロファイル永続化のオプトイン）
# --------------------------------------------------------------------------- #


def test_config_default_profile_dir_is_empty():
    # 既定は空＝毎回まっさらな使い捨てプロファイル（従来どおりの挙動）。
    assert Config().profile_dir == ""


def test_load_config_profile_dir_empty_stays_empty(monkeypatch, tmp_path):
    # 項目行はあるが値が空 → 使い捨て（空のまま）。
    out = tmp_path / "out"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
output_dir = {out}
profile_dir =
""",
    )
    assert load_config().profile_dir == ""


def test_load_config_profile_dir_relative_resolves_under_base_dir(monkeypatch, tmp_path):
    # 相対パスは BASE_DIR 基準の絶対パス文字列へ固定される（output_dir と同じ扱い）。
    monkeypatch.setattr(config_mod, "BASE_DIR", tmp_path)
    _write_config(
        monkeypatch,
        tmp_path,
        """[capture]
output_dir = out
profile_dir = myprofile
""",
    )
    c = load_config()
    assert c.profile_dir == str(tmp_path / "myprofile")
    assert Path(c.profile_dir).is_absolute()


def test_load_config_profile_dir_absolute_is_kept(monkeypatch, tmp_path):
    # 絶対パス指定はそのまま保持する。
    prof = tmp_path / "abs-profile"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
output_dir = {tmp_path / "out"}
profile_dir = {prof}
""",
    )
    assert load_config().profile_dir == str(prof)


# --------------------------------------------------------------------------- #
# セッションフォルダ（起動単位で output_dir の下に 1 段挟む）
# --------------------------------------------------------------------------- #


def test_session_stamp_format():
    # 起動時刻を「YYYY-MM-DD_HHMMSS」で表す（フォルダ名に使うので区切りは - と _ のみ）。
    # autouse フィクスチャが session_stamp を "" に固定するため、実装本体（_REAL_SESSION_STAMP）を呼ぶ。
    assert re.match(r"^\d{4}-\d{2}-\d{2}_\d{6}$", _REAL_SESSION_STAMP())


def test_load_config_inserts_session_folder(monkeypatch, tmp_path):
    # 確定した output_dir の直下へ、起動時刻のセッションフォルダを 1 段挟む。
    # 実時刻由来だとテストが不安定なので session_stamp を固定値へ差し替える
    #（autouse フィクスチャは "" にしているが、ここでは実挿入を検証するため上書きする）。
    monkeypatch.setattr(config_mod, "session_stamp", lambda: "2026-08-11_143025")
    out = tmp_path / "out"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
output_dir = {out}
""",
    )
    c = load_config()
    assert c.output_dir == out / "2026-08-11_143025"


def test_load_config_session_folder_redirects_log(monkeypatch, tmp_path):
    # log.txt もセッションフォルダへ寄る（set_log_dir が output_dir 直下ではなく
    # セッションフォルダを指す）。受け渡しが「このフォルダを渡す」で閉じる肝。
    monkeypatch.setattr(config_mod, "session_stamp", lambda: "2026-08-11_143025")
    out = tmp_path / "out"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
output_dir = {out}
""",
    )
    load_config()
    assert infra.LOG_PATH == out / "2026-08-11_143025" / "log.txt"


def test_session_folder_keeps_lineage_and_downloads_relative(monkeypatch, tmp_path):
    # lineage-<id> / downloads / index.csv は output_dir からの相対で決まるので、
    # output_dir がセッションフォルダになれば自動でその配下へ入る（相対関係は不変）。
    monkeypatch.setattr(config_mod, "session_stamp", lambda: "2026-08-11_143025")
    out = tmp_path / "out"
    _write_config(
        monkeypatch,
        tmp_path,
        f"""[capture]
output_dir = {out}
""",
    )
    c = load_config()
    session = out / "2026-08-11_143025"
    # 撮影物の系譜サブフォルダ（lineage.group_subdir）はセッションフォルダ配下。
    assert lineage.group_subdir(c.output_dir, "20260811143025000") == (
        session / "lineage-20260811143025000"
    )
    # ダウンロード退避先（downloads._downloads_dir）もセッションフォルダ配下。
    from edge_auto_capture.downloads import _downloads_dir

    assert _downloads_dir(c, "20260811143025000") == (
        session / "lineage-20260811143025000" / "downloads"
    )
    # 索引 CSV はセッションフォルダ直下（全系譜を 1 本にまとめる粒度は据え置き）。
    assert c.output_dir / capture.INDEX_CSV_NAME == session / "index.csv"


# --------------------------------------------------------------------------- #
# summarize_config（採用された設定値を 1 行で残す）
# --------------------------------------------------------------------------- #


def test_summarize_config_reports_key_values():
    from edge_auto_capture.config import summarize_config

    c = Config(
        browser="edge",
        output_dir=Path("/tmp/out"),
        target_selector=".price",
        hide_selectors=("#cookie-banner", ".sticky-header"),
        allow_urls=("https://example.com/",),
    )
    line = summarize_config(c)
    assert line.startswith("[config] ")
    assert "browser=edge" in line
    assert "output_dir=/tmp/out" in line or "output_dir=\\tmp\\out" in line
    assert "target_selector=.price" in line
    assert "hide_selectors=#cookie-banner,.sticky-header" in line
    assert "allow_urls=https://example.com/" in line


def test_summarize_config_marks_empty_values_readably():
    from edge_auto_capture.config import summarize_config

    line = summarize_config(Config())  # 既定（自動選択・使い捨て・セレクタ無し）
    assert "browser=自動(Edge→Chrome)" in line
    assert "edge_path=自動" in line
    assert "profile_dir=使い捨て" in line
    assert "target_selector=(無)" in line
    assert "hide_selectors=(無)" in line
    assert "allow_urls=(無)" in line



# --------------------------------------------------------------------------- #
# 設定キーの出所の一致（#115）
# --------------------------------------------------------------------------- #
# config.ini のキーは 3 箇所に載っている:
#   1. default_config.ini（配布・自己修復に使う既定テンプレート。package-data）
#   2. config.py の _build_config（実際に読むキー）
#   3. README.md §設定（config.ini）の表（開発者向けリファレンス）
# キーを 1 つ足して README に書き忘れても、あるいは README から消し忘れても、
# pytest / ruff / mypy / smoke はどれも緑のまま通る。test_docs_refs.py の
# 「*.py 参照」「Issue 番号」「節番号」と同じ型の不変条件で、番人がいなかった最後の 1 つ。
#
# **キーの一覧をここへ書き写さないこと**（番人自身が 4 つ目の出所になる）。
# 3 つとも出所から機械的に導出して突き合わせる。

# sec.get / getfloat / getint / getboolean の第1引数と、_csv_tuple(sec, "...") の第2引数。
_SECTION_READERS = {"get", "getfloat", "getint", "getboolean"}


def _keys_read_by_config_py() -> set[str]:
    """config.py のソースから「[capture] から読んでいるキー」を導出する。

    リテラルで書かれた読み出しだけを拾う。`_csv_tuple` 内部の `sec.get(key, "")` は
    キーが変数なので自然に外れる（拾ってしまうと偽のキーが混ざる）。
    """
    tree = ast.parse((ROOT / "src" / "edge_auto_capture" / "config.py").read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        # sec.get("key", ...) の形
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _SECTION_READERS
            and isinstance(func.value, ast.Name)
            and func.value.id == "sec"
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
        # _csv_tuple(sec, "key") の形
        elif (
            isinstance(func, ast.Name)
            and func.id == "_csv_tuple"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            keys.add(node.args[1].value)
    return keys


def _keys_in_default_template() -> set[str]:
    """同梱テンプレート（default_config.ini）の [capture] のキー。"""
    parser = configparser.ConfigParser()
    parser.read_string(config_mod._default_config_text())
    return set(parser["capture"].keys())


def _keys_in_readme_table() -> set[str]:
    """README の「設定（config.ini）」の表に並んでいるキー。

    表は `| \\`key\\` | 意味 |` の形。見出しから次の見出しまでを対象にする。
    """
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"^### 設定（config\.ini）$(.*?)^#{2,3} ", text, re.S | re.M)
    assert m, "README の「設定（config.ini）」節が見つからない（見出しを変えたなら追随する）"
    return set(re.findall(r"^\| `([a-z_]+)` \|", m.group(1), re.M))


def test_config_keys_agree_across_their_three_sources():
    read = _keys_read_by_config_py()
    template = _keys_in_default_template()
    readme = _keys_in_readme_table()

    # 走査条件を絞りすぎて「0 件だから緑」になっていないことの担保。
    assert len(read) >= 10, f"config.py から読み出しキーを導出できていない: {sorted(read)}"

    assert read == template, (
        "config.py が読むキーと default_config.ini の [capture] が食い違っている:"
        f" config.py にだけ={sorted(read - template)} /"
        f" テンプレートにだけ={sorted(template - read)}"
    )
    assert read == readme, (
        "config.py が読むキーと README の設定表が食い違っている:"
        f" config.py にだけ={sorted(read - readme)} /"
        f" README にだけ={sorted(readme - read)}"
    )
