#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""游戏素材读取测试：用合成的 XNB / PNG 搭一个假游戏目录，不需要装游戏。

    python3 tests/test_assets.py

装了游戏时，额外用真实文件跑一遍（读 Data/Fish、中文名、切图）。
"""
import json
import os
import shutil
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import gamecontent as gc   # noqa: E402
from src.gamecontent import png, xnb   # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    print("  %s %s%s" % ("✅" if ok else "❌", name, "" if ok else "  (得到 %r，期望 %r)" % (got, want)))
    if not ok:
        FAILED.append(name)


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _s(s):
    raw = s.encode("utf-8")
    return _varint(len(raw)) + raw


def dict_xnb(d):
    readers = ["Microsoft.Xna.Framework.Content.DictionaryReader`2[[System.String],[System.String]]",
               "Microsoft.Xna.Framework.Content.StringReader"]
    body = _varint(len(readers))
    for r in readers:
        body += _s(r) + struct.pack("<i", 0)
    body += _varint(0) + _varint(1) + struct.pack("<I", len(d))
    for k, v in d.items():
        body += _varint(2) + _s(k) + _varint(2) + _s(v)
    return b"XNBw" + bytes([5, 0]) + struct.pack("<I", 10 + len(body)) + body


def sprite_font_xnb(glyphs, tex_w=32, tex_h=16, line=26, spacing=1.0, fmt=0, pixels=None):
    """合成一个 SpriteFont XNB。glyphs: [(字, (x,y,w,h), (cx,cy,cw,ch), (kl,kw,kr))]。"""
    readers = ["Microsoft.Xna.Framework.Content.SpriteFontReader",
               "Microsoft.Xna.Framework.Content.Texture2DReader",
               "Microsoft.Xna.Framework.Content.ListReader`1[[Microsoft.Xna.Framework.Rectangle]]",
               "Microsoft.Xna.Framework.Content.ListReader`1[[System.Char]]",
               "Microsoft.Xna.Framework.Content.ListReader`1[[Microsoft.Xna.Framework.Vector3]]",
               "Microsoft.Xna.Framework.Content.NullableReader`1[[System.Char]]"]
    body = _varint(len(readers))
    for r in readers:
        body += _s(r) + struct.pack("<i", 0)
    body += _varint(0) + _varint(1)
    px = pixels if pixels is not None else bytes((255, 255, 255, 255)) * (tex_w * tex_h)
    body += _varint(2) + struct.pack("<iIII", fmt, tex_w, tex_h, 1) + struct.pack("<I", len(px)) + px
    for part in (1, 2):
        body += _varint(3) + struct.pack("<i", len(glyphs))
        for g in glyphs:
            body += struct.pack("<iiii", *g[part])
    body += _varint(4) + struct.pack("<i", len(glyphs))
    for g in glyphs:
        body += g[0].encode("utf-8")
    body += struct.pack("<i", line) + struct.pack("<f", spacing)
    body += _varint(5) + struct.pack("<i", len(glyphs))
    for g in glyphs:
        body += struct.pack("<fff", *g[3])
    body += _varint(6) + b"\x01" + "?".encode("utf-8")
    return b"XNBw" + bytes([5, 0]) + struct.pack("<I", 10 + len(body)) + body


def solid_png(path, w, h, rgba=(10, 120, 200, 255)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    png.write_rgba(path, w, h, bytes(rgba) * (w * h))


def main():
    tmp = tempfile.mkdtemp(prefix="moyu_test_")
    old_root = gc.CACHE_ROOT
    gc.CACHE_ROOT = os.path.join(tmp, "cache")
    try:
        run(tmp)
    finally:
        gc.CACHE_ROOT = old_root
        shutil.rmtree(tmp, ignore_errors=True)
    real_game_check()
    print()
    if FAILED:
        print("失败 %d 项: %s" % (len(FAILED), "、".join(FAILED)))
        return 1
    print("素材读取测试全部通过 ✅")
    return 0


def run(tmp):
    print("== Dictionary XNB")
    d = {"128": "Pufferfish/80/floater/1/36/1200 1600/summer/sunny/x/4",
         "中文": "值/含/斜杠"}
    check("往返一致", xnb.read_string_dict(dict_xnb(d)), d)

    print("== SpriteFont XNB（原版位图字体）")
    glyphs = [("鱼", (0, 0, 12, 13), (0, 2, 12, 13), (1.0, 12.0, 1.0)),
              ("A", (12, 0, 7, 13), (0, 3, 7, 13), (0.0, 7.0, 1.0)),
              (" ", (19, 0, 0, 0), (0, 0, 0, 0), (0.0, 0.0, 6.0))]
    f = xnb.read_sprite_font(sprite_font_xnb(glyphs))
    check("字数、行高", (sorted(f.glyphs), f.line_spacing), ([" ", "A", "鱼"], 26))
    check("字形位置和前进宽度", f.glyphs["鱼"], (0, 0, 12, 13, 1.0, 2, 15.0))
    check("默认字符", f.default_char, "?")
    # DXT3：一个 4x4 块，颜色 0 = 白、alpha 全 15
    blk = bytes([0xFF] * 8) + struct.pack("<HH", 0xFFFF, 0) + bytes(4)
    t = xnb.read_sprite_font(sprite_font_xnb(glyphs[:1], 4, 4, fmt=5, pixels=blk)).texture
    check("DXT3 解码", t.rgba[:4], bytes((255, 255, 255, 255)))

    from src.ui import bitfont
    bf = bitfont.BitFont({"line": 26, "glyphs": {k: [0] + list(v) for k, v in f.glyphs.items()}})
    check("按汉字高度定缩放：12 号字的汉字高 12", round(bf.scale(12) * 13, 2), 12.0)
    check("很接近 0.5 倍就对齐过去", bf.scale(6.6), 0.5)
    big = bitfont.BitFont({"line": 52, "glyphs": {k: ["fontL_0", v[1], v[2], v[3], v[4] * 2, v[5], v[6] * 2, v[7] * 2]
                                                  for k, v in bf.glyphs.items()}})
    fs = bitfont.FontSet([big, bf])
    check("小字用小字体、大字用大字体", (fs.pick(6).line, fs.pick(13).line), (26, 52))
    ops = bf.layout("鱼A🍅", 12)
    check("字形 + 图标", [o[0] for o in ops], ["g", "g", "icon"])
    check("图标按 16 的整数倍画", ops[-1][4], 16)
    ops = bf.layout("鱼鱼鱼鱼", 12, width=30)
    check("超宽自动换行（一行两个字）", len({round(o[7], 1) for o in ops}), 2)
    check("字体里没有的字交给系统字体", [o[0] for o in bf.layout("鱼⏸", 12)], ["g", "sys"])
    sysbf = bitfont.BitFont({"line": 1.0, "glyphs": {}})
    check("没有原版字体时也把 🍅 换成番茄图标", [o[0] for o in sysbf.layout("🍅 1:00", 12)],
          ["icon", "sys"])

    print("== 搭一个解包格式的假游戏（PNG 图 + XNB 数据混用）")
    game = os.path.join(tmp, "Stardew Valley")
    content = os.path.join(game, "Contents", "Resources", "Content")
    solid_png(os.path.join(content, "LooseSprites", "Cursors.png"), 704, 2256)
    solid_png(os.path.join(content, "Maps", "springobjects.png"), 384, 624, (200, 80, 40, 255))
    solid_png(os.path.join(content, "TileSheets", "emotes.png"), 64, 256)
    os.makedirs(os.path.join(content, "Data"))
    os.makedirs(os.path.join(content, "Strings"))
    fish_table = {
        "128": "Pufferfish/80/floater/1/36/1200 1600/summer/sunny/690 .4/4/.3/.5/0/true",
        "137": "Smallmouth Bass/28/mixed/12/24/600 2600/spring fall/both/685 .2/1/.45/.1/0/false",
        "715": "Lobster/trap/.05/688 .45/ocean/2/20",
        "Goby": "Goby/55/dart/2/9/600 2600/spring summer fall/both/x/1",
    }
    open(os.path.join(content, "Data", "Fish.xnb"), "wb").write(dict_xnb(fish_table))
    open(os.path.join(content, "Strings", "Objects.xnb"), "wb").write(dict_xnb(
        {"Pufferfish_Name": "Pufferfish", "SmallmouthBass_Name": "Smallmouth Bass",
         "Pufferfish_Description": "Inflates when threatened."}))
    with open(os.path.join(content, "Strings", "Objects.zh-CN.json"), "w") as fh:
        json.dump({"Pufferfish_Name": "河豚", "SmallmouthBass_Name": "小嘴鲈鱼"}, fh, ensure_ascii=False)

    dirs = gc.normalize(game)
    check("找到 Content", dirs, [content])
    check("中文名（英文表反查 key）", gc.chinese_names(dirs),
          {"Pufferfish": "河豚", "Smallmouth Bass": "小嘴鲈鱼"})

    print("== 生成缓存")
    gc.build_cache(dirs, log=lambda m: None)
    for key, (_x, _y, w, h) in gc.CURSOR_RECTS.items():
        got = png.read_rgba(gc.ui_path(key))[:2]
        if got != (w, h):
            check("ui/%s 尺寸" % key, got, (w, h))
    check("钓鱼界面切图齐全", all(os.path.isfile(gc.ui_path(k)) for k in gc.CURSOR_RECTS), True)
    check("「！」表情", png.read_rgba(gc.ui_path("exclaim"))[:2], (64, 16))
    fish = gc.load_fish_list()
    check("钓竿鱼：河豚和小嘴鲈鱼（蟹笼、非数字 id 跳过）", [f.id for f in fish], ["128", "137"])
    check("中文名进了缓存", [f.display_name for f in fish], ["河豚", "小嘴鲈鱼"])
    check("鱼图标 16x16", png.read_rgba(gc.fish_icon_path("128"))[:2], (16, 16))
    check("图鉴剪影", os.path.isfile(gc.fish_icon_path("128", shadow=True)), True)
    check("水面 10 帧", png.read_rgba(gc.ui_path("water"))[:2], (640, 64))
    check("缓存新鲜", gc.cache_is_fresh(dirs), True)

    print("== 没装游戏")
    old = gc.CANDIDATE_GAME_DIRS
    gc.CANDIDATE_GAME_DIRS = []
    try:
        shutil.rmtree(gc.CACHE_ROOT)
        try:
            gc.ensure_cache(game_dir=os.path.join(tmp, "nope"))
            check("抛 GameNotFound", "没抛", True)
        except gc.GameNotFound:
            check("抛 GameNotFound", True, True)
    finally:
        gc.CANDIDATE_GAME_DIRS = old


def real_game_check():
    print("== 本机真实游戏文件（可选）")
    dirs = gc.find_content_dirs()
    if not dirs:
        print("  ⚪️ 没探测到游戏，跳过")
        return
    table, src = gc.load_dict("Data/Fish", dirs)
    print("  Data/Fish %d 条 <- %s" % (len(table), src))
    check("Data/Fish 里有河豚(128)", "128" in table, True)
    names = gc.chinese_names(dirs)
    print("  中文名 %d 个，例：%s" % (len(names), names.get("Pufferfish")))
    check("能读到中文名", len(names) > 50, True)
    tmp = tempfile.mkdtemp()
    old = gc.CACHE_ROOT
    gc.CACHE_ROOT = os.path.join(tmp, "cache")
    try:
        gc.build_cache(dirs, log=lambda m: print("   " + m))
        n = len(gc.load_fish_list())
        check("可钓的鱼至少 40 种", n >= 40, True)
    finally:
        gc.CACHE_ROOT = old
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
