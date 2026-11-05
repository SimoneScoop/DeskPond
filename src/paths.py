# -*- coding: utf-8 -*-
"""数据放哪：偏好、图鉴存档、游戏素材缓存。按系统区分。

    macOS    ~/Library/Application Support/DeskPond
    Windows  %APPDATA%\\DeskPond        （通常是 C:\\Users\\你\\AppData\\Roaming\\DeskPond）
    其他     ~/.local/share/DeskPond

改名前叫「摸鱼钓鱼 / MoyuFishing」：第一次启动时如果只有旧目录，会整个搬过来，存档不丢。
"""
import os
import sys

NAME = "DeskPond"
OLD_NAME = "MoyuFishing"


def _base():
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support")
    if sys.platform.startswith("win"):
        return os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    return os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")


def data_dir():
    return os.path.join(_base(), NAME)


def migrate_old_dir(base=None):
    """旧名字的数据目录搬到新名字下（只在新目录还不存在时搬）。搬了返回 True。"""
    base = base or _base()
    old, new = os.path.join(base, OLD_NAME), os.path.join(base, NAME)
    if os.path.isdir(old) and not os.path.exists(new):
        try:
            os.rename(old, new)
            return True
        except OSError:
            return False
    return False


migrate_old_dir()
DATA_DIR = data_dir()


def load_json(path):
    """读 JSON：统一按 UTF-8；老版本在中文 Windows 上可能按系统编码（GBK）写过，读不了 UTF-8 就退回系统编码。"""
    import json
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except UnicodeDecodeError:
        with open(path) as fh:
            return json.load(fh)
