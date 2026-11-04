# -*- coding: utf-8 -*-
"""界面公用：透明悬浮窗、像素图加载与绘制、星露谷风格的方框和文字。"""
import os

import Cocoa
from Cocoa import (NSBackingStoreBuffered, NSBezierPath, NSColor, NSFont,
                   NSFontAttributeName, NSForegroundColorAttributeName,
                   NSGraphicsContext, NSImage, NSImageInterpolationNone,
                   NSMakeRect, NSMutableParagraphStyle,
                   NSPanel, NSParagraphStyleAttributeName, NSSound, NSString,
                   NSWindowCollectionBehaviorCanJoinAllSpaces,
                   NSWindowCollectionBehaviorFullScreenAuxiliary,
                   NSWindowCollectionBehaviorIgnoresCycle,
                   NSWindowCollectionBehaviorStationary,
                   NSWindowStyleMaskBorderless, NSZeroRect)

from .. import gamecontent
from . import bitfont
from . import layout

FLOATING_LEVEL = 3          # NSFloatingWindowLevel
SOURCE_OVER = 2             # NSCompositingOperationSourceOver
SOURCE_IN = 3               # NSCompositingOperationSourceIn：只在已有像素上染色
NONACTIVATING_PANEL = 1 << 7   # NSWindowStyleMaskNonactivatingPanel：点它不会把你正在用的 App 切走

# 星露谷对话框的配色（取自原版贴图）
C_FILL = (255, 198, 153)
C_EDGE_INNER = (198, 137, 99)
C_EDGE_GOLD = (188, 103, 0)
C_EDGE_MID = (132, 51, 22)
C_EDGE_OUTER = (93, 26, 47)
C_TEXT = (86, 22, 12)

_images = {}


def color(rgb, alpha=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(
        rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, alpha)


def image(path):
    """读 PNG 成 NSImage，带缓存。文件不存在返回 None（调用方要能退化）。"""
    if path in _images:
        return _images[path]
    img = None
    if path and os.path.isfile(path):
        img = NSImage.alloc().initWithContentsOfFile_(path)
    _images[path] = img
    return img


def clear_image_cache():
    _images.clear()


def pixel_mode():
    """像素画用最近邻插值，放大后不糊。"""
    ctx = NSGraphicsContext.currentContext()
    if ctx is not None:
        ctx.setImageInterpolation_(NSImageInterpolationNone)


def draw(img, x, y, w, h, fraction=1.0):
    """在翻转坐标（y 向下）的视图里画整张图。"""
    if img is None:
        return
    img.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        NSMakeRect(x, y, w, h), NSZeroRect, SOURCE_OVER, fraction, True, None)


def draw_part(img, sx, sy, sw, sh, x, y, w, h, fraction=1.0):
    """画图的一部分。(sx, sy) 按图片左上角算，内部换成 NSImage 的左下角坐标。"""
    if img is None:
        return
    ih = img.size().height
    img.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        NSMakeRect(x, y, w, h), NSMakeRect(sx, ih - sy - sh, sw, sh),
        SOURCE_OVER, fraction, True, None)


def fill_rect(x, y, w, h, rgb, alpha=1.0):
    color(rgb, alpha).setFill()
    NSBezierPath.fillRect_(NSMakeRect(x, y, w, h))


def fill_oval(x, y, w, h, rgb, alpha=1.0):
    color(rgb, alpha).setFill()
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x, y, w, h)).fill()


def stroke_oval(x, y, w, h, rgb, alpha=1.0, width=1.0):
    path = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x, y, w, h))
    path.setLineWidth_(width)
    color(rgb, alpha).setStroke()
    path.stroke()


def draw_box9(img, x, y, w, h, scale=3.0, fallback_step=3.0):
    """原版的九宫格框（drawTextureBox）：四角按原样放大，边和中间拉伸。没有贴图就画代码版方框。"""
    if img is None:
        stardew_box(NSMakeRect(x, y, w, h), step=fallback_step)
        return
    sw, sh = img.size().width, img.size().height
    c = int(sw // 3)
    cs = c * scale
    xs = [(0, c, x, cs), (c, sw - 2 * c, x + cs, w - 2 * cs), (sw - c, c, x + w - cs, cs)]
    ys = [(0, c, y, cs), (c, sh - 2 * c, y + cs, h - 2 * cs), (sh - c, c, y + h - cs, cs)]
    for sx, sww, dx, dw in xs:
        for sy, shh, dy, dh in ys:
            if dw > 0 and dh > 0:
                draw_part(img, sx, sy, sww, shh, dx, dy, dw, dh)


def fill_star(cx, cy, r, rgb, alpha=1.0):
    """五角星（品质星）。"""
    import math
    path = NSBezierPath.bezierPath()
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = -math.pi / 2 + i * math.pi / 5
        pt = (cx + rr * math.cos(a), cy + rr * math.sin(a))
        if i == 0:
            path.moveToPoint_(pt)
        else:
            path.lineToPoint_(pt)
    path.closePath()
    color((60, 30, 20), alpha).setStroke()
    color(rgb, alpha).setFill()
    path.fill()
    path.setLineWidth_(1.0)
    path.stroke()


_sounds = {}
sound_enabled = True


def play(name):
    """系统自带音效（游戏音效打包在 XACT 声音库里，不去读）。"""
    if not sound_enabled or not name:
        return
    snd = _sounds.get(name)
    if snd is None:
        snd = NSSound.soundNamed_(name)
        _sounds[name] = snd
    if snd is not None:
        snd.stop()
        snd.play()


def overlay_window(rect, click_through=True):
    """透明、无边框、浮在最上层、所有桌面空间都可见的窗口。

    用不抢焦点的 NSPanel：点水面钓鱼时，你正在写的文档/代码编辑器仍然是当前 App。
    """
    win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, NSWindowStyleMaskBorderless | NONACTIVATING_PANEL, NSBackingStoreBuffered, False)
    win.setFloatingPanel_(True)
    win.setHidesOnDeactivate_(False)
    win.setBecomesKeyOnlyIfNeeded_(True)
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setHasShadow_(False)
    win.setLevel_(FLOATING_LEVEL)
    win.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorStationary
        | NSWindowCollectionBehaviorFullScreenAuxiliary
        | NSWindowCollectionBehaviorIgnoresCycle)
    win.setIgnoresMouseEvents_(click_through)
    win.setReleasedWhenClosed_(False)
    return win


FULL_SIZE_CONTENT = 1 << 15     # NSWindowStyleMaskFullSizeContentView


def game_window(width, height, title):
    """图鉴、农田这类窗口：没有底色，原版的框直接浮在桌面上；保留左上角的红黄绿按钮。

    空白处按住就能拖动窗口（视图里调 performWindowDragWithEvent_）。
    """
    from Cocoa import (NSWindow, NSWindowStyleMaskClosable, NSWindowStyleMaskMiniaturizable,
                       NSWindowStyleMaskTitled)
    style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
             | NSWindowStyleMaskMiniaturizable | FULL_SIZE_CONTENT)
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, width, height), style, NSBackingStoreBuffered, False)
    win.setTitle_(title)
    win.setTitlebarAppearsTransparent_(True)
    win.setTitleVisibility_(1)              # NSWindowTitleHidden
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setHasShadow_(True)
    win.setReleasedWhenClosed_(False)
    # 系统的红黄绿按钮藏起来，用原版菜单右上角的红叉（视图里画）；Esc 和 ⌘W 也能关
    for i in (0, 1, 2):
        try:
            btn = win.standardWindowButton_(i)
            if btn is not None:
                btn.setHidden_(True)
        except Exception:
            pass
    return win


CLOSE_SIZE = 36                   # 红叉 12×12，放大 3 倍
KEY_ESC, KEY_W = 53, 13
CMD = 1 << 20


def draw_close(x, y):
    """画原版的关闭按钮，返回它的矩形（给点击判断用）。"""
    img = image(_ui("close"))
    if img is not None:
        draw(img, x, y, CLOSE_SIZE, CLOSE_SIZE)
    else:
        stardew_box(NSMakeRect(x, y, CLOSE_SIZE, CLOSE_SIZE), step=2)
        draw_text("✕", x, y + 7, CLOSE_SIZE, 22, text_attrs(16, (200, 40, 30), bold=True,
                                                          align="center"))
    return (x, y, CLOSE_SIZE, CLOSE_SIZE)


def in_rect(p, r):
    return r is not None and r[0] <= p.x <= r[0] + r[2] and r[1] <= p.y <= r[1] + r[3]


def close_window(view):
    win = view.window()
    if win is not None:
        win.orderOut_(None)


def is_close_key(event):
    """Esc 或 ⌘W。"""
    try:
        code = event.keyCode()
        return code == KEY_ESC or (code == KEY_W and event.modifierFlags() & CMD)
    except Exception:
        return False


def _ui(name):
    from ..gamecontent import ui_path
    return ui_path(name)


def drag_window(view, event):
    win = view.window()
    if win is not None:
        try:
            win.performWindowDragWithEvent_(event)
        except Exception:
            pass


def stardew_box(rect, step=3.0):
    """星露谷风格的方框：四圈描边 + 切角，中间奶橘色。"""
    rings = [C_EDGE_OUTER, C_EDGE_MID, C_EDGE_GOLD, C_EDGE_INNER, C_FILL]
    for i, rgb in enumerate(rings):
        inset = i * step
        x0, y0 = rect.origin.x + inset, rect.origin.y + inset
        x1, y1 = rect.origin.x + rect.size.width - inset, rect.origin.y + rect.size.height - inset
        if x1 <= x0 or y1 <= y0:
            break
        cut = max(0.0, 6.0 - i * 1.5)
        path = NSBezierPath.bezierPath()
        path.moveToPoint_((x0 + cut, y0))
        path.lineToPoint_((x1 - cut, y0))
        path.lineToPoint_((x1, y0 + cut))
        path.lineToPoint_((x1, y1 - cut))
        path.lineToPoint_((x1 - cut, y1))
        path.lineToPoint_((x0 + cut, y1))
        path.lineToPoint_((x0, y1 - cut))
        path.lineToPoint_((x0, y0 + cut))
        path.closePath()
        color(rgb).setFill()
        path.fill()


def text_attrs(size=13.0, rgb=C_TEXT, bold=False, align=None, exact=False):
    if not exact:
        size = layout.readable(size)
    style = NSMutableParagraphStyle.alloc().init()
    style.setLineSpacing_(2.0)
    raw_align = align
    if align is not None:
        # 用系统常量：Apple 芯片和 Intel 上「居中」的编号不一样（1 和 2），不能写死
        if align == "center":
            align = getattr(Cocoa, "NSTextAlignmentCenter", 1)
        elif align == "right":
            align = getattr(Cocoa, "NSTextAlignmentRight", 2)
        style.setAlignment_(align)
    font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    # moyu.* 是给原版位图字体用的（AppKit 会忽略不认识的属性）
    return {NSFontAttributeName: font,
            NSForegroundColorAttributeName: color(rgb),
            NSParagraphStyleAttributeName: style,
            "moyu.size": float(size), "moyu.rgb": tuple(rgb), "moyu.bold": bool(bold),
            "moyu.align": raw_align}


def _bitmap(text, attrs):
    """这段字用不用原版位图字体画：返回 BitFont 或 None。"""
    if "moyu.size" not in attrs:
        return None
    bf = bitfont.get()
    return bf if bf is not None and bf.covers(text) else None


def _sys_measure(attrs):
    plain = text_attrs(attrs["moyu.size"], attrs["moyu.rgb"], attrs["moyu.bold"], exact=True)
    return lambda t, s: NSString.stringWithString_(t).sizeWithAttributes_(plain).width


_glyphs = {}


def _glyph(page, sx, sy, sw, sh, rgb):
    """一个字形染成 rgb 色的小图（字体贴图是白字，按需染色、缓存）。"""
    key = (page, sx, sy, rgb)
    if key in _glyphs:
        return _glyphs[key]
    src = image(gamecontent.font_page_path(page))
    img = None
    if src is not None:
        img = NSImage.alloc().initWithSize_((sw, sh))
        img.lockFocus()
        pixel_mode()
        ih = src.size().height
        src.drawInRect_fromRect_operation_fraction_(NSMakeRect(0, 0, sw, sh),
                                                    NSMakeRect(sx, ih - sy - sh, sw, sh), SOURCE_OVER, 1.0)
        color(rgb).set()
        Cocoa.NSRectFillUsingOperation(NSMakeRect(0, 0, sw, sh), SOURCE_IN)
        img.unlockFocus()
    _glyphs[key] = img
    return img


def draw_text(text, x, y, w, h, attrs):
    bf = _bitmap(text, attrs)
    if bf is None:
        NSString.stringWithString_(text).drawInRect_withAttributes_(NSMakeRect(x, y, w, h), attrs)
        return
    size, rgb = attrs["moyu.size"], attrs["moyu.rgb"]
    plain = None
    for op in bf.layout(text, size, width=w, align=attrs["moyu.align"], measure=_sys_measure(attrs)):
        if op[0] == "g":
            _, page, sx, sy, sw, sh, dx, dy, dw, dh = op
            draw(_glyph(page, sx, sy, sw, sh, rgb), x + dx, y + dy, dw, dh)
        elif op[0] == "icon":
            _, path, dx, dy, s = op
            draw(image(path), x + dx, y + dy, s, s)
        else:
            _, run, dx, dy, rw, rh = op
            plain = plain or text_attrs(size, rgb, attrs["moyu.bold"], exact=True)
            NSString.stringWithString_(run).drawInRect_withAttributes_(
                NSMakeRect(x + dx, y + dy, rw + 4, rh + 4), plain)


def text_height(text, attrs, width):
    """排进 width 宽（自动换行）一共多高：说明框按它算高度，字就不会跑出框。"""
    bf = _bitmap(text, attrs)
    if bf is not None:
        return bf.wrapped_height(text, attrs["moyu.size"], width, _sys_measure(attrs))
    r = NSString.stringWithString_(text).boundingRectWithSize_options_attributes_(
        (width, 10000), 1, attrs)          # 1 = NSStringDrawingUsesLineFragmentOrigin
    return r.size.height


def text_size(text, attrs):
    bf = _bitmap(text, attrs)
    if bf is not None:
        w, h = bf.measure(text, attrs["moyu.size"], _sys_measure(attrs))
        return Cocoa.NSMakeSize(w, h)
    return NSString.stringWithString_(text).sizeWithAttributes_(attrs)



def draw_fit(text, x, y, w, size, rgb, bold=False, align="center", min_size=7.5):
    """单行文字：放不下就把字号一点点缩小（作物名这种不能换行的地方用）。"""
    while size > min_size and text_size(text, text_attrs(size, rgb, bold)).width > w:
        size -= 0.5
    attrs = text_attrs(size, rgb, bold, align)
    draw_text(text, x, y, w, text_size(text, attrs).height + 4, attrs)
