# -*- coding: utf-8 -*-
"""Qt 版的绘图小工具，接口和 Mac 版 src/ui/common.py 对齐，所以各个界面的绘制代码几乎能原样搬过来。

坐标都是左上角原点、y 向下（和 Mac 版里翻转过的视图一样），单位是逻辑像素。
用法：在 paintEvent 里 `with painting(self):`，里面直接调 draw / fill_rect / draw_text ……
"""
import os
from contextlib import contextmanager

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF)

from ..gamecontent import font_page_path, ui_path
from ..ui import bitfont, layout

# 星露谷对话框的配色（和 Mac 版一样）
C_FILL = (255, 198, 153)
C_EDGE_INNER = (198, 137, 99)
C_EDGE_GOLD = (188, 103, 0)
C_EDGE_MID = (132, 51, 22)
C_EDGE_OUTER = (93, 26, 47)
C_TEXT = (86, 22, 12)

FONT_FAMILY = None          # 由 app 按系统设置（Windows 用微软雅黑）

_p = None                   # 当前的 QPainter
_images = {}


@contextmanager
def painting(widget):
    global _p
    p = QPainter(widget)
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)   # 像素画用最近邻，放大不糊
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    prev, _p = _p, p
    try:
        yield p
    finally:
        _p = prev
        p.end()


def color(rgb, alpha=1.0):
    c = QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def image(path):
    """读 PNG 成 QPixmap，带缓存。文件不存在返回 None（调用方要能退化）。"""
    if path in _images:
        return _images[path]
    img = None
    if path and os.path.isfile(path):
        pm = QPixmap(path)
        img = None if pm.isNull() else pm
    _images[path] = img
    return img


def ui(name):
    return image(ui_path(name))


def clear_image_cache():
    _images.clear()


def draw(img, x, y, w, h, fraction=1.0):
    if img is None or _p is None:
        return
    _p.setOpacity(fraction)
    _p.drawPixmap(QRectF(x, y, w, h), img, QRectF(0, 0, img.width(), img.height()))
    _p.setOpacity(1.0)


def draw_part(img, sx, sy, sw, sh, x, y, w, h, fraction=1.0):
    """画图的一部分，(sx, sy) 按图片左上角算。"""
    if img is None or _p is None:
        return
    _p.setOpacity(fraction)
    _p.drawPixmap(QRectF(x, y, w, h), img, QRectF(sx, sy, sw, sh))
    _p.setOpacity(1.0)


def fill_rect(x, y, w, h, rgb, alpha=1.0):
    if _p is not None:
        _p.fillRect(QRectF(x, y, w, h), color(rgb, alpha))


def fill_oval(x, y, w, h, rgb, alpha=1.0):
    if _p is None:
        return
    _p.setPen(Qt.NoPen)
    _p.setBrush(color(rgb, alpha))
    _p.drawEllipse(QRectF(x, y, w, h))
    _p.setBrush(Qt.NoBrush)


def stroke_oval(x, y, w, h, rgb, alpha=1.0, width=1.0):
    if _p is None:
        return
    pen = QPen(color(rgb, alpha))
    pen.setWidthF(width)
    _p.setPen(pen)
    _p.setBrush(Qt.NoBrush)
    _p.drawEllipse(QRectF(x, y, w, h))
    _p.setPen(Qt.NoPen)


def fill_star(cx, cy, r, rgb, alpha=1.0):
    import math
    if _p is None:
        return
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = -math.pi / 2 + i * math.pi / 5
        pts.append(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    _p.fillPath(path, color(rgb, alpha))
    pen = QPen(color((60, 30, 20), alpha))
    pen.setWidthF(1.0)
    _p.strokePath(path, pen)


# MARK: 文字

def text_attrs(size=13.0, rgb=C_TEXT, bold=False, align=None, exact=False):
    if not exact:
        size = layout.readable(size)
    font = QFont(FONT_FAMILY) if FONT_FAMILY else QFont()
    font.setPixelSize(max(1, int(round(size))))
    font.setBold(bool(bold))
    flags = Qt.TextWordWrap | Qt.AlignTop
    if align == "center":
        flags |= Qt.AlignHCenter
    elif align == "right":
        flags |= Qt.AlignRight
    else:
        flags |= Qt.AlignLeft
    return {"font": font, "color": color(rgb), "flags": flags,
            "size": float(size), "rgb": tuple(rgb), "bold": bool(bold), "align": align}


def _bitmap(text, attrs):
    """这段字用不用原版位图字体画：返回 BitFont 或 None。"""
    if "size" not in attrs:
        return None
    bf = bitfont.get()
    return bf if bf is not None and bf.covers(text) else None


def _sys_measure(attrs):
    fm = QFontMetricsF(attrs["font"])
    return lambda t, s: fm.horizontalAdvance(t)


_glyphs = {}


def _glyph(page, sx, sy, sw, sh, rgb):
    """一个字形染成 rgb 色的小图（字体贴图是白字，按需染色、缓存）。"""
    key = (page, sx, sy, rgb)
    if key not in _glyphs:
        src = image(font_page_path(page))
        img = None
        if src is not None:
            img = src.toImage().copy(int(sx), int(sy), int(sw), int(sh)).convertToFormat(
                QImage.Format_ARGB32_Premultiplied)
            q = QPainter(img)
            q.setCompositionMode(QPainter.CompositionMode_SourceIn)
            q.fillRect(img.rect(), color(rgb))
            q.end()
        _glyphs[key] = img
    return _glyphs[key]


def draw_text(text, x, y, w, h, attrs):
    if _p is None:
        return
    bf = _bitmap(text, attrs)
    if bf is None:
        _p.setFont(attrs["font"])
        _p.setPen(attrs["color"])
        _p.drawText(QRectF(x, y, w, h), int(attrs["flags"]), text)
        _p.setPen(Qt.NoPen)
        return
    size, rgb = attrs["size"], attrs["rgb"]
    k = bf.scale(size)
    try:
        dpr = _p.device().devicePixelRatioF()
    except Exception:
        dpr = 1.0
    smooth = k * dpr < 0.99           # 缩小显示时最近邻会丢笔画，改成平滑
    _p.setRenderHint(QPainter.SmoothPixmapTransform, smooth)
    for op in bf.layout(text, size, width=w, align=attrs["align"], measure=_sys_measure(attrs)):
        if op[0] == "g":
            _, page, sx, sy, sw, sh, dx, dy, dw, dh = op
            img = _glyph(page, sx, sy, sw, sh, rgb)
            if img is not None:
                _p.drawImage(QRectF(x + dx, y + dy, dw, dh), img)
        elif op[0] == "icon":
            _, path, dx, dy, sz = op
            _p.setRenderHint(QPainter.SmoothPixmapTransform, False)
            draw(image(path), x + dx, y + dy, sz, sz)
            _p.setRenderHint(QPainter.SmoothPixmapTransform, smooth)
        else:
            _, run, dx, dy, rw, rh = op
            _p.setFont(attrs["font"])
            _p.setPen(attrs["color"])
            _p.drawText(QRectF(x + dx, y + dy, rw + 4, rh + 4), int(Qt.AlignLeft | Qt.AlignTop), run)
            _p.setPen(Qt.NoPen)
    _p.setRenderHint(QPainter.SmoothPixmapTransform, False)


class _Size(object):
    __slots__ = ("width", "height")

    def __init__(self, w, h):
        self.width, self.height = w, h


def text_height(text, attrs, width):
    """排进 width 宽（自动换行）一共多高：说明框按它算高度，字就不会跑出框。"""
    bf = _bitmap(text, attrs)
    if bf is not None:
        return bf.wrapped_height(text, attrs["size"], width, _sys_measure(attrs))
    fm = QFontMetricsF(attrs["font"])
    return fm.boundingRect(QRectF(0, 0, width, 10000), int(Qt.TextWordWrap), text).height()


def text_size(text, attrs):
    bf = _bitmap(text, attrs)
    if bf is not None:
        return _Size(*bf.measure(text, attrs["size"], _sys_measure(attrs)))
    fm = QFontMetricsF(attrs["font"])
    return _Size(fm.horizontalAdvance(text), fm.height())

def draw_fit(text, x, y, w, size, rgb, bold=False, align="center", min_size=7.5):
    """单行文字：放不下就把字号一点点缩小（作物名这种不能换行的地方用）。"""
    while size > min_size and text_size(text, text_attrs(size, rgb, bold)).width > w:
        size -= 0.5
    attrs = text_attrs(size, rgb, bold, align)
    draw_text(text, x, y, w, text_size(text, attrs).height + 4, attrs)



# MARK: 原版的框

def stardew_box(x, y, w, h, step=3.0):
    """没有贴图时的备用框：四圈描边，中间奶橘色。"""
    rings = [C_EDGE_OUTER, C_EDGE_MID, C_EDGE_GOLD, C_EDGE_INNER, C_FILL]
    for i, rgb in enumerate(rings):
        inset = i * step
        if w - 2 * inset <= 0 or h - 2 * inset <= 0:
            break
        fill_rect(x + inset, y + inset, w - 2 * inset, h - 2 * inset, rgb)


def draw_box9(img, x, y, w, h, scale=3.0, fallback_step=3.0):
    """原版的九宫格框（drawTextureBox）：四角按原样放大，边和中间拉伸。"""
    if img is None:
        stardew_box(x, y, w, h, step=fallback_step)
        return
    sw, sh = img.width(), img.height()
    c = sw // 3
    cs = c * scale
    xs = [(0, c, x, cs), (c, sw - 2 * c, x + cs, w - 2 * cs), (sw - c, c, x + w - cs, cs)]
    ys = [(0, c, y, cs), (c, sh - 2 * c, y + cs, h - 2 * cs), (sh - c, c, y + h - cs, cs)]
    for sx, sww, dx, dw in xs:
        for sy, shh, dy, dh in ys:
            if dw > 0 and dh > 0:
                draw_part(img, sx, sy, sww, shh, dx, dy, dw, dh)


CLOSE_SIZE = 36


def draw_close(x, y):
    """原版菜单右上角的红叉，返回它的矩形。"""
    img = ui("close")
    if img is not None:
        draw(img, x, y, CLOSE_SIZE, CLOSE_SIZE)
    else:
        stardew_box(x, y, CLOSE_SIZE, CLOSE_SIZE, step=2)
        draw_text("✕", x, y + 7, CLOSE_SIZE, 22, text_attrs(16, (200, 40, 30), True, "center"))
    return (x, y, CLOSE_SIZE, CLOSE_SIZE)


def in_rect(px, py, r):
    return r is not None and r[0] <= px <= r[0] + r[2] and r[1] <= py <= r[1] + r[3]
