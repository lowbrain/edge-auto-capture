"""配布物の体裁を守るユニットテスト。

「漏れても pytest / ruff / mypy / smoke のどれも落ちないが、配布した先で壊れる」
種類の不変条件をここへ集める。開発中は pip install -e . で動いてしまうため、
気づくのが配布 exe を作った後（しかも --noconsole なら無言死）になる。

- badge.js が package-data として宣言され、実在すること（#68・#81）
- USAGE.txt が Shift-JIS として健全であること（#69）

どちらも標準ライブラリだけで完結させる。CI は 3.9 と 3.12 の両方で pytest を回すので、
tomllib（3.11+）は使えない（pyproject は正規表現で読む）。

実行:
    pip install -e ".[dev]"
    pytest
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- #
# badge.js の同梱（#68・#81）
# --------------------------------------------------------------------------- #
# py-modules（トップレベル・モジュール群）時代は package-data が使えず、
# pip install .（非 editable）で badge.js が wheel に入らず起動不能になっていた
# （#81・src/ レイアウト化で根治）。ここでは「宣言されていること」と「実在すること」の
# 2 本で縛る。wheel を実ビルドして中身を見る形の方が強いが、CI の 3.9/3.12 マトリクスで
# 毎回回すには重いので、まずは宣言テストから始める。


def test_badge_js_is_declared_as_package_data():
    src = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"^\[tool\.setuptools\.package-data\]\s*$(.*?)^\[", src, re.MULTILINE | re.DOTALL)
    assert m, "pyproject.toml に [tool.setuptools.package-data] セクションが見つからない"
    assert re.search(r'edge_auto_capture\s*=\s*\[[^\]]*"badge\.js"', m.group(1))


def test_badge_js_exists_next_to_badge_py():
    # badge.py の _badge_js_path() は Path(__file__).parent / "badge.js" を見る前提。
    package_dir = ROOT / "src" / "edge_auto_capture"
    assert (package_dir / "badge.py").is_file()
    assert (package_dir / "badge.js").is_file()


# --------------------------------------------------------------------------- #
# USAGE.txt の Shift-JIS 妥当性（#69・CONTRIBUTING §1-4）
# --------------------------------------------------------------------------- #
# USAGE.txt はリポジトリ内で唯一 Shift-JIS（他は UTF-8）。UTF-8 で保存し直す・
# 絵文字が混入する、といった事故はどのチェックにも掛からず、配布先の利用者が
# 開くまで気づけない。バーのラベルには絵文字（📂 / 📸）が入っているので、
# 文言を USAGE.txt へ引用するときに持ち込みやすい。
#
# 注意: ASCII のバックスラッシュ `\` の混入はここでは検出できない。Python の
# shift_jis コーデックは 0x5C として素通しするため（iconv は同じ入力でエラーにする）。
# 詳細と使い分けは CONTRIBUTING §1-4 とスキル .claude/skills/usage-txt/ を参照。


def _usage_bytes() -> bytes:
    return (ROOT / "USAGE.txt").read_bytes()


def test_usage_txt_decodes_as_shift_jis():
    # デコードできなければ例外で落ちる（＝文字コードが変わった）。
    assert _usage_bytes().decode("shift_jis")


def test_usage_txt_roundtrips_byte_identical():
    # デコード → 再エンコードで元のバイト列に戻ること。CONTRIBUTING §1-4 が
    # 編集後に手でやれと言っている往復確認を、そのままテストにしたもの。
    raw = _usage_bytes()
    assert raw.decode("shift_jis").encode("shift_jis") == raw


def test_usage_txt_has_no_non_bmp_characters():
    # 絵文字（BMP 外）は Shift-JIS に無い。混入していれば上のデコードか往復で
    # 落ちるはずだが、原因が「絵文字」だと分かる形でも縛っておく。
    text = _usage_bytes().decode("shift_jis")
    assert [c for c in text if ord(c) > 0xFFFF] == []
