"""リポジトリ内の GitHub リンク（スラグと Issue 番号）の一貫性を固定するユニットテスト。

test_packaging.py と同じ「漏れても 4 点セットのどれも落ちないが、後で効いてくる
不変条件をテストで固定する」型。ドキュメントとスキルは CI にもテストにも掛からないので、
指し先が半分だけ書き換わった状態が誰にも気づかれない（#85）。

実際に一度起きている。ロードマップ Issue の差し替え（#38 → #78）では 5 ファイル
15 箇所を手作業で掃除し、歴史的な言及として #38 のまま残す 2 箇所との判別も手作業だった。

縛るもの:

- 本文が名指しする `*.py` が実在すること（改名・移動の取り残しを落とす）
- GitHub URL のスラグが 1 つであること（旧スラグのコピペ混入を落とす）
- `[#N](.../issues/M)` の N と M が一致すること（「番号だけ」「URL だけ」直した半端な
  書き換えを落とす）
- Issue の URL リンクがロードマップ Issue を指していること（例外は下の許可リストへ
  理由付きで置く）
- 退役したロードマップ Issue 番号が、歴史的言及として許可した場所にしか出ないこと

**指し先を差し替えるときの手順**: 下の ROADMAP_ISSUE を新番号にし、旧番号を
RETIRED_ROADMAP_ISSUES へ足す。すると残った旧番号の参照が URL・素の `#N` の両方とも
テストの失敗として一覧で出る。歴史的言及としてそのまま残すものだけを
HISTORICAL_MENTIONS へ移す（＝「引用元でない場所を出典として指さない」の機械側）。

ネットワークには触らない（Issue の実在確認はしない。オフライン CI で落ちるため）。
標準ライブラリのみ。

実行:
    pip install -e ".[dev]"
    pytest
"""

import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 正しいリポジトリスラグ。ここ 1 箇所だけが定義で、リポジトリ内の全 URL がこれと一致する。
CANONICAL_SLUG = "lowbrain/edge-auto-capture"

# 「これが正」として指しているロードマップ Issue（ピン留め・CONTRIBUTING 冒頭）。
ROADMAP_ISSUE = 78

# 退役したロードマップ Issue。ここへ入れると「残っていないこと」が縛られる。
RETIRED_ROADMAP_ISSUES = {38}

# 歴史的言及として残してよい場所（パス, Issue 番号）→ 理由。
# ロードマップの指し先ではなく、そこで起きた出来事の出典なので差し替えない。
HISTORICAL_MENTIONS = {
    ("CLAUDE.md", 38): "docs/ROADMAP.md と Issue の二重管理で実害が出た経緯の出典",
    ("CONTRIBUTING.md", 38): "§4「ドキュメントに残タスクの一覧を作らない」の経緯の出典",
}

# 本文に出てよい「実在しない .py」→ 理由。
# 退役した名前を歴史として語る場合だけ許可する。現在形で指してはいけない
# （読み手が今あるファイルだと思い込む。実際 app.py の docstring が #81 の改名後も
# 「python edge_auto_capture.py（開発時）」と動かない手順を指示し続けていた）。
RETIRED_MODULE_MENTIONS = {
    ("README.md", "edge_auto_capture.py"):
        "「src/ レイアウト化で python edge_auto_capture.py は使えなくなった」の告知",
}
# このファイル自身は SELF として走査から外れるので、ここへ自分を足す必要はない。

# 走査対象は git の追跡対象だけ。output/ や log.txt（成果物）、.venv、
# .claude/worktrees/（作業用ワークツリー）は .gitignore 済みなので自動的に外れる。
# ファイルシステムを直接歩くと、手元に残った古いワークツリーの中身で落ちる。
SUFFIXES = {".md", ".py", ".js", ".txt", ".toml", ".ini", ".yml", ".yaml", ".ps1", ".json"}

# このファイル自身は定義の置き場所（上の定数とコメントに旧番号が出る）なので走査しない。
SELF = Path(__file__).resolve()

# 本文に「ファイル名として」現れる .py を拾う。パス付き（src/edge_auto_capture/app.py）も
# 素の名前（badge.py）も対象。前後がパス文字・英数字のときは切り出さない
# （`edge_auto_capture.app` のようなモジュール参照や URL の一部を誤検出しないため）。
PY_FILE = re.compile(r"(?<![\w./-])(?P<name>[\w./-]*[\w-]\.py)\b")

GITHUB_URL = re.compile(r"https://github\.com/(?P<slug>[\w.-]+/[\w.-]+)(?P<rest>[\w./#-]*)")
ISSUE_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/issues/(?P<num>\d+)")
ISSUE_LINK = re.compile(r"\[#(?P<label>\d+)\]\((?P<url>https://github\.com/[^)]+)\)")
BARE_REF = re.compile(r"(?<![\w#])#(?P<num>\d+)\b")


def _tracked() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:  # git 無し / 非 git チェックアウト
        pytest.skip(f"git の追跡対象を列挙できないため走査できない: {exc}")
    return [name for name in out.decode("utf-8").split("\0") if name]


def _files() -> Iterator[Path]:
    for name in _tracked():
        path = ROOT / name
        if not path.is_file() or path.resolve() == SELF:
            continue
        if path.suffix.lower() in SUFFIXES:
            yield path


def _read(path: Path) -> str:
    # USAGE.txt は Shift-JIS（CONTRIBUTING §1-4）。ここで見るのは ASCII の URL と
    # `#N` だけなので、デコードできないバイトは潰して読み飛ばす。
    return path.read_bytes().decode("utf-8", errors="replace")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_scan_actually_finds_the_documents():
    # 走査条件を絞りすぎて「0 件だから緑」になっていないことの担保。
    names = {_rel(p) for p in _files()}
    assert {"README.md", "CONTRIBUTING.md", "CLAUDE.md"} <= names


def test_all_github_urls_use_the_canonical_slug():
    wrong = [
        f"{_rel(p)}: {m.group('slug')}"
        for p in _files()
        for m in GITHUB_URL.finditer(_read(p))
        if m.group("slug") != CANONICAL_SLUG
    ]
    assert wrong == [], f"GitHub URL のスラグが {CANONICAL_SLUG} と違う: {wrong}"


def test_issue_link_label_matches_its_url():
    # `[#78](.../issues/38)` のような半端な書き換えを落とす。
    mismatched = []
    for path in _files():
        for m in ISSUE_LINK.finditer(_read(path)):
            url = ISSUE_URL.search(m.group("url"))
            if url and url.group("num") != m.group("label"):
                mismatched.append(f"{_rel(path)}: [#{m.group('label')}] → {m.group('url')}")
    assert mismatched == [], f"リンクの表示番号とリンク先が食い違っている: {mismatched}"


def test_issue_urls_point_at_the_roadmap_issue():
    # 「これが正」として URL で指す先はロードマップ Issue だけ。歴史的言及は許可リストへ。
    unexpected = []
    for path in _files():
        for m in ISSUE_URL.finditer(_read(path)):
            num = int(m.group("num"))
            if num == ROADMAP_ISSUE or (_rel(path), num) in HISTORICAL_MENTIONS:
                continue
            unexpected.append(f"{_rel(path)}: #{num}")
    assert unexpected == [], (
        f"ロードマップ Issue（#{ROADMAP_ISSUE}）以外への URL リンク: {unexpected}。"
        " 歴史的言及なら HISTORICAL_MENTIONS へ理由付きで足す"
    )


def test_retired_roadmap_issues_are_not_referenced():
    # 素の `#38` も対象。差し替えで消し忘れた参照をここで一覧にする。
    leftovers = []
    for path in _files():
        text = _read(path)
        for m in BARE_REF.finditer(text):
            num = int(m.group("num"))
            if num in RETIRED_ROADMAP_ISSUES and (_rel(path), num) not in HISTORICAL_MENTIONS:
                leftovers.append(f"{_rel(path)}: #{num}")
    assert leftovers == [], (
        f"退役したロードマップ Issue への参照が残っている: {leftovers}。"
        " 歴史的言及として残すなら HISTORICAL_MENTIONS へ理由付きで足す"
    )


def test_mentioned_python_files_exist():
    """本文が名指しする `*.py` が実在すること（改名・移動の取り残しを落とす）。

    上の Issue 参照と同じ型の不変条件で、**漏れても 4 点セットのどれも落ちない**。
    実際に #81 の `src/` レイアウト化（改名）で取り残しが出ていた。`app.py` の docstring は
    自分自身を `edge_auto_capture.py` と呼び続け、`起動方法` として
    `python edge_auto_capture.py` という**動かないコマンドを指示していた**。README には
    「それは使えなくなった」と書いてあるのに、である（CLAUDE.md 冒頭が名指しする #51 の
    「解消済みの罠を踏み直せと指示する」状態の再発）。

    パス付き（`src/edge_auto_capture/app.py`）は実パスとして、素の名前（`badge.py`）は
    追跡対象のどれかの basename として照合する。退役した名前を歴史として語る場所だけは
    RETIRED_MODULE_MENTIONS へ理由付きで置く。
    """
    tracked = {name for name in _tracked() if name.endswith(".py")}
    basenames = {Path(name).name for name in tracked}

    missing = []
    for path in _files():
        rel = _rel(path)
        for m in PY_FILE.finditer(_read(path)):
            name = m.group("name")
            if (rel, name) in RETIRED_MODULE_MENTIONS:
                continue
            found = name in tracked if "/" in name else name in basenames
            if not found:
                missing.append(f"{rel}: {name}")

    assert missing == [], (
        f"実在しない .py を名指ししている: {sorted(set(missing))}。"
        " 改名・移動したなら参照側も直す。退役した名前を歴史として語るなら"
        " RETIRED_MODULE_MENTIONS へ理由付きで足す"
    )


def test_retired_module_mentions_are_all_still_needed():
    """RETIRED_MODULE_MENTIONS に用済みのエントリが残っていないこと。

    この辞書は「実在しない .py を名指ししてよい場所」の免除リストで、**免除は当たらなく
    なっても誰も気づかない**。参照側の文が消えた（例: 経緯コメントを git へ返した）あとも
    エントリが残ると、次に同じ場所へ同じ名前を書いたときに黙って見逃す穴になる。

    上の test_mentioned_python_files_exist と対で、免除の過不足を両側から縛る。
    """
    stale = []
    for (rel, name), why in RETIRED_MODULE_MENTIONS.items():
        path = ROOT / rel
        if not path.exists():
            stale.append(f"{rel}: ファイルが無い（{why}）")
            continue
        if not any(m.group("name") == name for m in PY_FILE.finditer(_read(path))):
            stale.append(f"{rel}: {name} をもう名指ししていない（{why}）")

    assert stale == [], (
        f"用済みの免除が残っている: {sorted(stale)}。"
        " 参照側の文が消えたなら RETIRED_MODULE_MENTIONS からも外す"
    )
