#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把几张原版贴图复制到 _game_ref/，方便开发时核对像素位置。

    python3 tools/copy_ref.py

用和 App 一样的方式找游戏目录（也认 DESKPOND_GAME_DIR 和偏好里选过的目录）。
_game_ref/ 在 .gitignore 里，也不会被 export_clean.py 导出，不会上传。
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src import gamecontent, prefs   # noqa: E402

WANTED = ["LooseSprites/Cursors", "TileSheets/bobbers", "TileSheets/crops",
          "Data/Crops", "Maps/springobjects", "TerrainFeatures/hoeDirt",
          "LooseSprites/Fence1", "TileSheets/tools"]


def main():
    dirs = gamecontent.find_content_dirs(prefs.get("game_dir"))
    if not dirs:
        print("没找到游戏目录。可以这样指定：DESKPOND_GAME_DIR=/path/to/Stardew\\ Valley python3 tools/copy_ref.py")
        return 1
    out = os.path.join(ROOT, "_game_ref")
    os.makedirs(out, exist_ok=True)
    print("游戏素材目录：%s" % dirs[0])
    for name in WANTED:
        path = gamecontent.resolve(name, dirs, (".png", ".xnb", ".json"))
        if not path:
            print("  - 没有 %s（这个版本可能没有）" % name)
            continue
        dest = os.path.join(out, name.replace("/", "_") + os.path.splitext(path)[1])
        shutil.copy2(path, dest)
        print("  ✓ %s" % os.path.basename(path))
    # 原版位图字体：整个 Fonts 目录（中文字体是 Chinese + Chinese_0..N 几页贴图）
    for d in dirs:
        fdir = os.path.join(d, "Fonts")
        if os.path.isdir(fdir):
            n = 0
            for fn in sorted(os.listdir(fdir)):
                if fn.lower().endswith((".xnb", ".fnt", ".png")):
                    shutil.copy2(os.path.join(fdir, fn), os.path.join(out, "Fonts_" + fn))
                    n += 1
            print("  ✓ Fonts（%d 个文件）" % n)
            break
    print("已复制到 %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
