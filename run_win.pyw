#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 版启动：双击这个文件（用 pythonw 运行，不弹黑窗口），或在命令行里 python run_win.pyw 看日志。

打包版 / pythonw 没有控制台：输出写到 %APPDATA%\\DeskPond\\deskpond.log；
启动时出错会弹一个系统提示框，告诉你出了什么错、日志在哪。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _log_to_file():
    """没有控制台时 sys.stdout / sys.stderr 是 None：改成写日志文件，返回日志路径。"""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    try:
        from src.paths import DATA_DIR
        os.makedirs(DATA_DIR, exist_ok=True)
        path = os.path.join(DATA_DIR, "deskpond.log")
        fh = open(path, "w", encoding="utf-8", buffering=1)
    except Exception:
        fh, path = open(os.devnull, "w"), None
    if sys.stdout is None:
        sys.stdout = fh
    if sys.stderr is None:
        sys.stderr = fh
    return path


def _fatal(text):
    """Qt 都可能没起来，用 Windows 自己的提示框（置顶）。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "桌面摸鱼 启动失败", 0x10 | 0x10000 | 0x40000)
    except Exception:
        pass


if __name__ == "__main__":
    log_path = _log_to_file()
    try:
        from src.win.app import main
        code = main()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        sys.stderr.write(tb)
        _fatal("桌面摸鱼启动时出错了：\n\n%s\n日志：%s\n\n可以把这个日志发到 GitHub 的 Issues 里。"
               % (tb[-1200:], log_path or "（见命令行输出）"))
        code = 1
    sys.exit(code)
