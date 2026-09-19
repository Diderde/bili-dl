# SPDX-License-Identifier: GPL-3.0-only
"""命令行入口：python -m bili_dl（或安装后的 bili-dl 命令）。"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    from bili_dl import __version__

    parser = argparse.ArgumentParser(prog="bili-dl", description="B站音视频下载工具")
    parser.add_argument("--version", action="version", version=f"bili-dl {__version__}")
    parser.parse_args(argv)

    try:
        from bili_dl.gui import run
    except ImportError as exc:
        print(f"依赖未安装完整，无法启动界面：{exc}", file=sys.stderr)
        print("请在项目目录执行：python -m pip install -e .", file=sys.stderr)
        print("或直接双击 run.bat 自动修复环境。", file=sys.stderr)
        return 1

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
