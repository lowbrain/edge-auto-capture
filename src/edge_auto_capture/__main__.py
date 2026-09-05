"""`python -m edge_auto_capture` の入口。cli() を呼ぶだけ。

配布 exe（build.ps1・PyInstaller）はこのファイルをスクリプトとして直接実行する
（`python -m` を経由しない）ため、`__package__` が設定されず相対 import
（`from .app import cli`）は `ImportError` になる。パッケージが（`pip install -e`
済みで）import 可能な前提で、絶対 import にしておく。
"""

import sys

from edge_auto_capture.app import cli

if __name__ == "__main__":
    sys.exit(cli())
