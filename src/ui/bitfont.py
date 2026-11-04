# -*- coding: utf-8 -*-
"""用游戏自带的位图字体排字（Mac / Windows 共用的排版部分，真正画由平台层做）。

字体是缓存里的 font.json + font_<页>.png（从 Fonts/SmallFont.zh-CN 等读出来的）。
字体里没有的字：几个 emoji 换成游戏图标（🍅 → 番茄、🐟 → 太阳鱼），其余交给系统字体画。

layout() 返回一串绘制指令（坐标都相对文字框左上角）：
    ("g", 页, sx, sy, sw, sh, dx, dy, dw, dh)   一个字形
    ("icon", 图片路径, dx, dy, 边长)             一个游戏图标
    ("sys", 文字, dx, dy, 宽, 高)                交给系统字体的一段
"""
from .. import gamecontent

LINE_FACTOR = 1.3             # 字号 → 行高（和系统字体差不多）
EM_FACTOR = 1.0               # 字号 → 汉字的高度：和系统字体一样大，不按字体自带的行距算（那样会小一圈）
SNAP = 0.04                   # 离 0.5 的整数倍很近才对齐过去（游戏的中文字体本身是平滑的，不用硬对齐）
BEST_K = 0.5                  # Retina 上 0.5 倍 = 一个字体像素对一个屏幕像素，最清楚


def _icons():
    return {"🍅": gamecontent.ui_path("tomato"), "🐟": gamecontent.fish_icon_path("145")}


class BitFont(object):

    def __init__(self, info, icon_exists=None):
        self.system = not info.get("glyphs")     # 没有原版字体：字全交给系统，只把 emoji 换成游戏图标
        self.line = float(info["line"])
        self.glyphs = {k: v for k, v in info["glyphs"].items()}
        # 以「中」字的高度当一个字号（字体自带的行距里有很多空白）
        ref = self.glyphs.get("中") or self.glyphs.get("鱼")
        self.em = float(ref[4]) if ref else self.line * 0.68
        self.top = float(ref[6]) if ref else 0.0
        self.icons = {}
        exists = icon_exists or (lambda p: True)
        for ch, path in _icons().items():
            if exists(path):
                self.icons[ch] = path

    # 字号 → 缩放
    def scale(self, size):
        if self.system:
            return size * LINE_FACTOR / self.line
        raw = size * EM_FACTOR / self.em
        half = round(raw * 2) / 2.0
        if half > 0 and abs(raw - half) / half <= SNAP:
            return half
        return raw

    def covers(self, text):
        """这段字要不要走这里：有字体里的字，或者有要换成游戏图标的 emoji。"""
        return any(ch in self.glyphs or ch in self.icons for ch in text)

    def _advance(self, ch, k, size, measure):
        g = self.glyphs.get(ch)
        if g is not None:
            return g[7] * k
        if ch in self.icons:
            return icon_size(line_h(size)) + 2
        if ch == " ":
            sp = self.glyphs.get(" ")
            return sp[7] * k if sp else size * 0.35
        return measure(ch, size)

    def measure(self, text, size, measure=None):
        measure = measure or _rough
        k = self.scale(size)
        lines = text.split("\n")
        w = max(sum(self._advance(ch, k, size, measure) for ch in ln) for ln in lines)
        return w, len(lines) * line_h(size)

    def wrapped_height(self, text, size, width, measure=None):
        """排进 width 宽以后一共多高（自动换行算进去）。"""
        measure = measure or _rough
        k = self.scale(size)
        return len(self._wrap(text, width, k, size, measure)) * line_h(size)

    def _wrap(self, text, width, k, size, measure):
        out = []
        for para in text.split("\n"):
            if width is None:
                out.append(para)
                continue
            cur, cw, last_space = "", 0.0, -1
            for ch in para:
                a = self._advance(ch, k, size, measure)
                if cw + a > width and cur:
                    if last_space > 0:                      # 英文按空格断，中文随便断
                        out.append(cur[:last_space])
                        cur = cur[last_space + 1:]
                    else:
                        out.append(cur)
                        cur = ""
                    cw = sum(self._advance(c, k, size, measure) for c in cur)
                    last_space = -1
                if ch == " ":
                    last_space = len(cur)
                cur += ch
                cw += a
            out.append(cur)
        return out

    def layout(self, text, size, width=None, align=None, measure=None):
        measure = measure or _rough
        k = self.scale(size)
        lh = line_h(size)
        # 汉字在一行里竖直居中；其他字形按字体里的相对位置跟着走（基线一致）
        y0 = (lh - self.em * k) / 2.0 - self.top * k
        ops = []
        for row, ln in enumerate(self._wrap(text, width, k, size, measure)):
            lw = sum(self._advance(ch, k, size, measure) for ch in ln)
            x = 0.0
            if width is not None and align == "center":
                x = (width - lw) / 2.0
            elif width is not None and align == "right":
                x = width - lw
            y = row * lh
            sys_run, sys_x = "", 0.0
            for ch in ln:
                g = self.glyphs.get(ch)
                a = self._advance(ch, k, size, measure)
                if g is None and ch not in self.icons and ch != " ":
                    if not sys_run:
                        sys_x = x
                    sys_run += ch
                    x += a
                    continue
                if sys_run:
                    ops.append(("sys", sys_run, sys_x, y, x - sys_x, lh))
                    sys_run = ""
                if g is not None:
                    page, sx, sy, sw, sh, ox, oy, _adv = g
                    if sw > 0 and sh > 0:
                        ops.append(("g", page, sx, sy, sw, sh, x + ox * k, y + y0 + oy * k, sw * k, sh * k))
                elif ch in self.icons:
                    s = icon_size(lh)
                    ops.append(("icon", self.icons[ch], x + (a - s) / 2.0, y + (lh - s) / 2.0, s))
                x += a
            if sys_run:
                ops.append(("sys", sys_run, sys_x, y, x - sys_x, lh))
        return ops


def line_h(size):
    return size * LINE_FACTOR


def icon_size(line_h):
    """游戏图标是 16 像素的，按整数倍画才不糊：一行字高附近最近的 16 的倍数（至少 16）。"""
    return 16 * max(1, int(round(line_h * 1.1 / 16)))


def _rough(text, size):
    """没有平台量字函数时的估计：中文 / emoji 一个字号宽，其余半个。"""
    return sum(size if ord(ch) > 0x2E80 else size * 0.55 for ch in text)


class FontSet(object):
    """游戏有一小一大两套中文字体（SmallFont / SpriteFont1）：每个字号挑缩放最接近 0.5 的那套，
    小字用小字体、标题用大字体，都尽量一个字体像素对一个屏幕像素。接口和 BitFont 一样。"""

    def __init__(self, fonts):
        self.fonts = sorted(fonts, key=lambda f: f.line)
        self.system = all(f.system for f in self.fonts)
        self.icons = self.fonts[0].icons

    def pick(self, size):
        return min(self.fonts, key=lambda f: abs(f.scale(size) - BEST_K))

    def covers(self, text):
        return self.fonts[0].covers(text)

    def scale(self, size):
        return self.pick(size).scale(size)

    def measure(self, text, size, measure=None):
        return self.pick(size).measure(text, size, measure)

    def wrapped_height(self, text, size, width, measure=None):
        return self.pick(size).wrapped_height(text, size, width, measure)

    def layout(self, text, size, width=None, align=None, measure=None):
        return self.pick(size).layout(text, size, width, align, measure)


_font = []


def get():
    """缓存里的原版字体（FontSet）；没有的话是一个「系统字体 + 游戏图标」的。"""
    if not _font:
        import os
        infos = [i for i in (gamecontent.font_info() or []) if i.get("glyphs")]
        if not infos:
            infos = [{"line": 1.0, "glyphs": {}}]
        _font.append(FontSet([BitFont(i, os.path.isfile) for i in infos]))
    return _font[0]


def reset():
    del _font[:]
