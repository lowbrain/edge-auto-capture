"""`python -m edge_auto_capture` の入口。cli() を呼ぶだけ。"""

import sys

from .app import cli

if __name__ == "__main__":
    sys.exit(cli())
