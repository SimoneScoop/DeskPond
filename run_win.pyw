#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 版启动：双击这个文件（用 pythonw 运行，不弹黑窗口），或在命令行里 python run_win.pyw 看日志。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.win.app import main   # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
