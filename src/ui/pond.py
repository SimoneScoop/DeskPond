# -*- coding: utf-8 -*-
"""屏幕底部的水面：升起/退下动画、浮漂、咬钩的「！」、状态提示。

水面高度可以拖动顶边调整（双击顶边恢复默认），宽度和透明度在菜单里选。
点水面的横向位置决定浮漂落点，纵向位置决定水深：越靠上离岸越远、水越深。
"""
import math

import objc
from Cocoa import NSEvent, NSMakeRect, NSMenu, NSScreen, NSView

from .. import session as S
from .. import world
from ..gamecontent import bobber_styles, ui_path
from . import common as C
from . import layout as L

WATER_BASE = (60, 110, 200)         # 没有水面贴图时的底色
FOAM = (230, 245, 255)


class PondView(NSView):

    def initWithFrame_(self, frame):
        self = objc.super(PondView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.session = None
        self.now = 0.0
        self.status_line = ""
        self.hint = ""
        self.hint_until = 0.0
        self.on_click = None
        self.on_menu = None         # 右键：返回一个 NSMenu
        self.on_resize = None       # on_resize(高度, 是否松手)
        self.pond_h = L.POND_HEIGHT
        self.hover_handle = False
        self.dragging = False
        self.drag_y0 = 0.0
        self.drag_h0 = L.POND_HEIGHT
        self.water = C.image(ui_path("water"))
        self.exclaim = C.image(ui_path("exclaim"))
        self.textbox = C.image(ui_path("textbox"))
        self.bobber_styles = bobber_styles()   # 缓存里有几种原版浮漂（0 = 用代码画）
        return self

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        b = self.bounds()
        w = b.size.width
        sess = self.session
        top = L.POND_HEADROOM + L.water_top(sess.level if sess else 1.0, self.pond_h)
        if _can_resize(sess) and self.on_resize and L.near_handle(p.y, top):
            if event.clickCount() == 2:
                self.on_resize(L.POND_HEIGHT, True)
                return
            # 用屏幕坐标算拖动距离：拖的时候窗口自己在变高，视图坐标会跟着跑
            self.dragging = True
            self.drag_y0 = NSEvent.mouseLocation().y
            self.drag_h0 = self.pond_h
            return
        if self.on_click:
            rel = L.depth_rel(p.y, top, b.size.height)
            self.on_click(p.x / w if w else 0.5, world.depth_from_rel(rel), rel)

    def rightMouseDown_(self, event):
        if self.on_menu is not None and (self.session is None or self.session.state != S.PLAYING):
            NSMenu.popUpContextMenu_withEvent_forView_(self.on_menu(), event, self)

    def mouseDragged_(self, event):
        if self.dragging and self.on_resize:
            self.on_resize(self.drag_h0 + NSEvent.mouseLocation().y - self.drag_y0, False)

    def mouseUp_(self, event):
        if self.dragging:
            self.dragging = False
            if self.on_resize:
                self.on_resize(self.pond_h, True)

    # MARK: 绘制

    def drawRect_(self, rect):
        sess = self.session
        if sess is None or sess.state == S.HIDDEN:
            return
        C.pixel_mode()
        b = self.bounds()
        w = b.size.width
        top = L.POND_HEADROOM + L.water_top(sess.level, self.pond_h)
        self._draw_water(w, top, b.size.height)
        if _can_resize(sess) and (self.hover_handle or self.dragging):
            self._draw_handle(w, top)
        if sess.state in (S.WAITING, S.BITE, S.PLAYING):
            self._draw_bobber(sess, w, top, b.size.height)
        if sess.level >= 1.0:
            self._draw_labels(sess, w, top, b.size.height)

    @objc.python_method
    def _draw_water(self, w, top, bottom):
        t = self.now
        size = L.WATER_TILE * L.WATER_SCALE
        if self.water is not None:
            frame = L.water_frame(t)
            y = top
            while y < bottom:
                for x in L.water_tiles(w, t):
                    C.draw_part(self.water, frame * L.WATER_TILE, 0, L.WATER_TILE, L.WATER_TILE,
                                x, y, size, size)
                y += size
        else:
            C.fill_rect(0, top, w, bottom - top, WATER_BASE)
        # 岸边的浪花：一条起伏的亮边
        seg = 8
        x = 0
        while x < w:
            dy = math.sin(x * 0.05 + t * 2.0) * 2.0
            C.fill_rect(x, top + dy - 1, seg, 3, FOAM, 0.75)
            x += seg
        C.fill_rect(0, top + 4, w, 2, (20, 40, 90), 0.25)

    @objc.python_method
    def _draw_handle(self, w, top):
        """顶边右侧的拖动手柄：两道短横线。"""
        x = w - 64
        for dy in (-3, 2):
            C.fill_rect(x + 1, top + dy + 1, 28, 2, (20, 40, 90), 0.5)
            C.fill_rect(x, top + dy, 28, 2, FOAM, 0.95)

    @objc.python_method
    def _draw_bobber(self, sess, w, top, bottom):
        t = self.now
        bite = sess.state == S.BITE
        x, y = L.bobber_pos(sess.cast_x, w, top, t, bite=bite, cast_y=sess.cast_y, bottom=bottom)
        img = C.image(ui_path("bobber_%d" % sess.bobber)) if self.bobber_styles else None
        if img is None:
            # 代码画的浮漂没有倒影，补一圈往外扩的波纹
            r = 10 + (t * 14) % 14
            C.stroke_oval(x - r, y + 6 - r / 3.0, r * 2, r * 2 / 3.0, FOAM,
                          0.6 * (1 - (r - 10) / 14.0), 1.5)
        if img is not None:
            # 原版浮漂表的「水里」那一半：上面是浮漂，下面是倒影
            size = 16 * L.BOBBER_SCALE
            C.draw(img, x - size / 2.0, y - size * 0.4, size, size)
            head = y - size * 0.4
        else:
            # 没切到贴图：用方块拼一个像素风浮漂（红顶白底）
            px = L.BOBBER_SCALE
            for (cx, cy, rgb) in _BOBBER_PIXELS:
                C.fill_rect(x + (cx - 4.5) * px, y + (cy - 4.5) * px, px, px, rgb)
            head = y - 4.5 * px
        if bite:
            since = t - sess.state_at
            size = L.EXCLAIM_FRAME * L.EXCLAIM_SCALE
            ex, ey = x - size / 2.0, head - 6 - size
            if self.exclaim is not None:
                f = L.exclaim_frame(since)
                C.draw_part(self.exclaim, f * L.EXCLAIM_FRAME, 0, L.EXCLAIM_FRAME, L.EXCLAIM_FRAME,
                            ex, ey, size, size)
            else:
                C.draw_text("！", ex, ey, size, size, C.text_attrs(34, (255, 230, 60), bold=True))

    @objc.python_method
    def _draw_labels(self, sess, w, top, bottom):
        # 左下角：剩余时间和今日战绩
        if self.status_line:
            attrs = C.text_attrs(12.5, C.C_TEXT, bold=True)
            size = C.text_size(self.status_line, attrs)
            bw, bh = size.width + 28, 30
            bx = 14
            box = NSMakeRect(bx, bottom - bh - 12, bw, bh)
            C.draw_box9(self.textbox, box.origin.x, box.origin.y, bw, bh, scale=2)
            C.draw_text(self.status_line, bx + 14, bottom - bh - 12 + 7, size.width + 4, 18, attrs)
        # 中间：操作提示
        hint = self.hint if self.now < self.hint_until else _default_hint(sess)
        if hint:
            attrs = C.text_attrs(15, (255, 255, 255), bold=True)
            shadow = C.text_attrs(15, (20, 30, 70), bold=True)
            size = C.text_size(hint, attrs)
            x = (w - size.width) / 2.0
            y = top + min(54, max(14, (bottom - top) / 2.0 - 11))
            C.draw_text(hint, x + 1.5, y + 1.5, size.width + 4, 22, shadow)
            C.draw_text(hint, x, y, size.width + 4, 22, attrs)


def _bobber_pixels():
    """9x9 的备用浮漂：深色描边、红色上半、白色下半。"""
    rows = ["...ooo...",
            "..orrro..",
            ".orrrrro.",
            ".orrrrro.",
            ".owwwwwo.",
            ".owwwwwo.",
            "..owwwo..",
            "...ooo...",
            "........."]
    colors = {"o": (60, 30, 30), "r": (220, 50, 40), "w": (250, 250, 245)}
    return [(cx, cy, colors[ch]) for cy, row in enumerate(rows)
            for cx, ch in enumerate(row) if ch in colors]


_BOBBER_PIXELS = _bobber_pixels()


def _can_resize(sess):
    """只在没抛竿 / 看结果时能拖高度：溜鱼时按住鼠标是在控制绿条。"""
    return sess is not None and sess.level >= 1.0 and sess.state in (S.IDLE, S.RESULT)


def _default_hint(sess):
    return L.default_hint(sess)


class Pond(object):
    """水面窗口。只有水的那一块接收点击，上方留给「！」的空间和其余屏幕都穿透。"""

    def __init__(self, on_click, on_resize=None, on_menu=None):
        self.window = None
        self.view = None
        self.on_click = on_click
        self.on_menu = on_menu
        self.on_resize = on_resize
        self.screen_frame = None     # 水面这一列在屏幕上的范围（宽 = 水面宽，高 = 可见屏幕高）
        self.height = L.POND_HEIGHT
        self.width_mode = "full"
        self.alpha = 1.0
        self._ignoring = True

    def configure(self, height=None, width_mode=None, alpha=None):
        if height is not None:
            self.height = L.clamp_height(height)
        if width_mode is not None:
            self.width_mode = width_mode
        if alpha is not None:
            self.alpha = max(0.3, min(1.0, float(alpha)))
        if self.window is not None:
            self._layout()

    def _layout(self):
        vf = NSScreen.mainScreen().visibleFrame()      # 已经去掉了 Dock 和菜单栏
        x, w = L.pond_span(vf.origin.x, vf.size.width, self.width_mode)
        self.screen_frame = NSMakeRect(x, vf.origin.y, w, vf.size.height)
        h = self.height + L.POND_HEADROOM
        rect = NSMakeRect(x, vf.origin.y, w, h)
        if self.window is None:
            self.window = C.overlay_window(rect, click_through=True)
            self.view = PondView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
            self.view.on_click = self.on_click
            self.view.on_menu = self.on_menu
            self.view.on_resize = self.on_resize
            self.window.setContentView_(self.view)
        else:
            self.window.setFrame_display_(rect, True)
            self.view.setFrame_(NSMakeRect(0, 0, w, h))
        self.view.pond_h = self.height
        self.window.setAlphaValue_(self.alpha)

    def attach(self, sess):
        self._layout()
        self.view.session = sess
        self.window.orderFrontRegardless()

    def hide(self):
        if self.window is not None:
            self.window.orderOut_(None)
            self.window.setIgnoresMouseEvents_(True)
            self._ignoring = True
            self.view.dragging = False

    @property
    def visible(self):
        return self.window is not None and self.window.isVisible()

    def width(self):
        return self.screen_frame.size.width if self.screen_frame else 1440.0

    def flash(self, text, now, seconds=1.8):
        if self.view is not None:
            self.view.hint = text
            self.view.hint_until = now + seconds

    def _water_h(self):
        sess = self.view.session if self.view is not None else None
        return self.height * L.ease_out(sess.level) if sess else 0.0

    def contains(self, mouse):
        """鼠标是否在水面（含顶边手柄）上。"""
        if not self.visible:
            return False
        vf = self.screen_frame
        return (vf.origin.x <= mouse.x <= vf.origin.x + vf.size.width
                and vf.origin.y <= mouse.y <= vf.origin.y + self._water_h() + L.HANDLE_ZONE)

    def update(self, now, status_line, mouse):
        """每帧调用：刷新画面，并按鼠标是否在水上决定窗口穿不穿透。"""
        if not self.visible:
            return
        v = self.view
        v.now = now
        v.status_line = status_line
        sess = v.session
        ready = sess is not None and sess.level >= 1.0
        over = self.contains(mouse)
        top_y = self.screen_frame.origin.y + self._water_h()
        v.hover_handle = _can_resize(sess) and over and abs(mouse.y - top_y) <= L.HANDLE_ZONE
        ignore = not ((over and ready) or v.dragging)
        if ignore != self._ignoring:
            self._ignoring = ignore
            self.window.setIgnoresMouseEvents_(ignore)
        v.setNeedsDisplay_(True)

    def water_top_screen_y(self):
        """水面顶端在屏幕坐标（左下原点）里的 y。"""
        return self.screen_frame.origin.y + self.height
