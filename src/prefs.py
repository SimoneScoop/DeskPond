"""用户偏好。

存在用户目录而不是 .app 里 —— 重新打包不会把设置冲掉。
"""
import json
import os
import sys

from .paths import DATA_DIR as PREFS_DIR, load_json
PREFS_PATH = os.path.join(PREFS_DIR, "prefs.json")

_cache = None


def load(force=False):
    global _cache
    if _cache is None or force:
        try:
            _cache = load_json(PREFS_PATH)
        except (IOError, ValueError):
            _cache = {}
    return _cache


def save(prefs=None):
    global _cache
    if prefs is not None:
        _cache = prefs
    try:
        if not os.path.isdir(PREFS_DIR):
            os.makedirs(PREFS_DIR)
        with open(PREFS_PATH, "w", encoding="utf-8") as fh:
            json.dump(_cache or {}, fh, ensure_ascii=False, indent=2)
    except IOError as exc:
        sys.stderr.write("[Prefs] 写入 %s 失败: %s\n" % (PREFS_PATH, exc))


def get(key, default=None):
    return load().get(key, default)


def set(key, value):
    load()[key] = value
    save()
