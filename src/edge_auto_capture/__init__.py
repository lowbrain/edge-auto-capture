"""edge-auto-capture パッケージ。

ここに `from .app import cli` のような再エクスポートを置かないこと。
`infra` / `config` は Playwright 非依存で実 Edge 無しでもテストできる設計
（README・CONTRIBUTING 参照）だが、`app` は Playwright に依存する。
`__init__.py` で app を import してしまうと、`edge_auto_capture.config` を
import しただけで Playwright まで引きずられ、この性質が壊れる。
`[project.scripts]` は `edge_auto_capture.app:cli` を直接指す。
"""

from .infra import __version__

__all__ = ["__version__"]
