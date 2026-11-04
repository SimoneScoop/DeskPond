#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出一份「干净」的工程副本，用来上传 GitHub。

    python3 tools/export_clean.py              # -> build/github/DeskPond/
    python3 tools/export_clean.py ~/Desktop/DeskPond-github

为什么需要：网页端「Upload files」拖整个文件夹时**不看 .gitignore**，
会把 _game_ref/、snapshots/ 里的游戏素材一起传上去。用这个脚本导出的目录只含
代码、配置、文档（白名单），会拒绝任何图片 / .xnb / 压缩包——只有 docs/media/ 里 README 用的演示动图例外。
用 git 命令行或 GitHub Desktop 提交时 .gitignore 生效，不需要这一步。
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 白名单：只导出这些顶层条目
INCLUDE = [
    ".gitignore", ".github", "LICENSE", "NOTICE.md", "README.md", "README.en.md", "CHANGELOG.md",
    "requirements.txt", "requirements-windows.txt", "run.py", "run_win.pyw", "selfcheck.sh",
    "src", "tests", "tools", "docs",
]
MEDIA_DIR = os.path.join("docs", "media")      # README 用的演示动图：只有这里允许 .gif
SKIP_DIRS = {"__pycache__", "image", ".DS_Store"}
ALLOWED_EXT = {".py", ".pyw", ".json", ".md", ".sh", ".bat", ".plist", ".txt", ".yml", ""}
FORBIDDEN_EXT = {".png", ".jpg", ".jpeg", ".gif", ".xnb", ".zip", ".webp", ".psd"}


def main():
    dest = os.path.abspath(os.path.expanduser(
        sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "github", "DeskPond")))
    if os.path.exists(dest):
        shutil.rmtree(dest)
    copied, skipped = 0, []
    for item in INCLUDE:
        src = os.path.join(ROOT, item)
        if not os.path.exists(src):
            continue
        paths = []
        if os.path.isdir(src):
            for root, dirs, files in os.walk(src):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and (not d.startswith(".") or d == ".github")]
                paths += [os.path.join(root, f) for f in files]
        else:
            paths = [src]
        for p in paths:
            name = os.path.basename(p)
            ext = os.path.splitext(name)[1].lower()
            rel = os.path.relpath(p, ROOT)
            if name.startswith(".") and name != ".gitignore":
                continue
            if ext == ".gif" and os.path.dirname(rel) == MEDIA_DIR:
                out = os.path.join(dest, rel)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                shutil.copy2(p, out)
                copied += 1
                continue
            if ext in FORBIDDEN_EXT or ext not in ALLOWED_EXT:
                skipped.append(rel)
                continue
            out = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(p, out)
            copied += 1
    print("已导出 %d 个文件 -> %s" % (copied, dest))
    if skipped:
        print("跳过（图片/压缩包/未知类型，不会上传）:")
        for s in skipped:
            print("  " + s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
