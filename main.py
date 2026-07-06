#!/usr/bin/env python3
"""Entry point: chạy GUI nếu không có tham số, chạy CLI nếu có subcommand."""

import sys


def main():
    if len(sys.argv) == 1:
        from gui import launch_gui

        launch_gui()
    else:
        from cli import main as cli_main

        sys.exit(cli_main())


if __name__ == "__main__":
    main()
