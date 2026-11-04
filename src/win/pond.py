# -*- coding: utf-8 -*-
"""Windows 版：屏幕底部的水面、钓鱼竖条、钓完的结果提示。画法和 Mac 版 src/ui/pond.py、
minigame_window.py 一样，只是窗口换成 Qt，坐标换成左上角原点。"""
import math

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QWidget

from .. import progression
from .. import session as S
from .. import world
from ..gamecontent import bobber_styles, fish_icon_path, junk_icon_path
from ..ui import layout as L
from . import platform as P
from . import qtdraw as C

WATER_BASE = (60, 110, 200)
FOAM = (230, 245, 255)
TRACK_BLUE = (150, 190, 240)
BAR_GREEN = (120, 220, 40)
FISH_FALLBACK = (240, 150, 60)


def _can_resize(sess):
    """只在没抛竿 / 看结果时能拖高度：溜鱼时按住鼠标是在控制绿条。"""
    return sess is not None and sess.level >= 1.0 and sess.state in (S.IDLE, S.RESULT)


def _default_hint(sess):
    return L.default_hint(sess)


def _bobber_pixels():
    rows = ["...ooo...", "..orrro..", ".orrrrro.", ".orrrrro.", ".owwwwwo.",
            ".owwwwwo.", "..owwwo..", "...ooo...", "........."]
    colors = {"o": (60, 30, 30), "r": (220, 50, 40), "w": (250, 250, 245)}
    return [(cx, cy, colors[ch]) for cy, row in enumerate(rows)
            for cx, ch in enumerate(row) if ch in colors]


_BOBBER_PIXELS = _bobber_pixels()


class PondWidget(QWidget):

    def __init__(self):
        super(PondWidget, self).__init__()
        P.make_overlay(self, click_through=True)
        self.session = None
        self.now = 0.0
        self.status_line = ""
        self.hint = ""
        self.hint_until = 0.0
        self.on_click = None
        self.on_menu = None         # 右键：返回一个 QMenu
        self.on_resize = None
        self.pond_h = L.POND_HEIGHT
        self.hover_handle = False
        self.dragging = False
        self.drag_y0 = 0
        self.drag_h0 = L.POND_HEIGHT
        self.water = C.ui("water")
        self.exclaim = C.ui("exclaim")
        self.textbox = C.ui("textbox")
        self.bobber_styles = bobber_styles()

    # MARK: 交互

    def _top(self):
        sess = self.session
        return L.POND_HEADROOM + L.water_top(sess.level if sess else 1.0, self.pond_h)

    def mousePressEvent(self, e):
        p = e.position()
        sess = self.session
        if e.button() == Qt.RightButton:
            if self.on_menu is not None and (sess is None or sess.state != S.PLAYING):
                self.on_menu().exec(QCursor.pos())
            return
        top = self._top()
        if _can_resize(sess) and self.on_resize and L.near_handle(p.y(), top):
            # 用屏幕坐标算拖动距离：拖的时候窗口自己在变高
            self.dragging = True
            self.drag_y0 = QCursor.pos().y()
            self.drag_h0 = self.pond_h
            return
        if self.on_click and e.button() == Qt.LeftButton:
            rel = L.depth_rel(p.y(), top, self.height())
            w = self.width()
            self.on_click(p.x() / w if w else 0.5, world.depth_from_rel(rel), rel)

    def mouseDoubleClickEvent(self, e):
        if _can_resize(self.session) and self.on_resize and L.near_handle(e.position().y(),
                                                                         self._top()):
            self.dragging = False
            self.on_resize(L.POND_HEIGHT, True)

    def mouseMoveEvent(self, e):
        if self.dragging and self.on_resize:
            self.on_resize(self.drag_h0 + (self.drag_y0 - QCursor.pos().y()), False)

    def mouseReleaseEvent(self, e):
        if self.dragging:
            self.dragging = False
            if self.on_resize:
                self.on_resize(self.pond_h, True)

    # MARK: 绘制

    def paintEvent(self, e):
        sess = self.session
        if sess is None or sess.state == S.HIDDEN:
            return
        with C.painting(self):
            w, bottom = self.width(), self.height()
            top = L.POND_HEADROOM + L.water_top(sess.level, self.pond_h)
            self._draw_water(w, top, bottom)
            if _can_resize(sess) and (self.hover_handle or self.dragging):
                x = w - 64
                for dy in (-3, 2):
                    C.fill_rect(x + 1, top + dy + 1, 28, 2, (20, 40, 90), 0.5)
                    C.fill_rect(x, top + dy, 28, 2, FOAM, 0.95)
            if sess.state in (S.WAITING, S.BITE, S.PLAYING):
                self._draw_bobber(sess, w, top, bottom)
            if sess.level >= 1.0:
                self._draw_labels(sess, w, top, bottom)

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
        x = 0
        while x < w:
            dy = math.sin(x * 0.05 + t * 2.0) * 2.0
            C.fill_rect(x, top + dy - 1, 8, 3, FOAM, 0.75)
            x += 8
        C.fill_rect(0, top + 4, w, 2, (20, 40, 90), 0.25)

    def _draw_bobber(self, sess, w, top, bottom):
        t = self.now
        bite = sess.state == S.BITE
        x, y = L.bobber_pos(sess.cast_x, w, top, t, bite=bite, cast_y=sess.cast_y, bottom=bottom)
        img = C.ui("bobber_%d" % sess.bobber) if self.bobber_styles else None
        if img is not None:
            size = 16 * L.BOBBER_SCALE
            C.draw(img, x - size / 2.0, y - size * 0.4, size, size)
            head = y - size * 0.4
        else:
            r = 10 + (t * 14) % 14
            C.stroke_oval(x - r, y + 6 - r / 3.0, r * 2, r * 2 / 3.0, FOAM,
                          0.6 * (1 - (r - 10) / 14.0), 1.5)
            px = L.BOBBER_SCALE
            for (cx, cy, rgb) in _BOBBER_PIXELS:
                C.fill_rect(x + (cx - 4.5) * px, y + (cy - 4.5) * px, px, px, rgb)
            head = y - 4.5 * px
        if bite:
            size = L.EXCLAIM_FRAME * L.EXCLAIM_SCALE
            ex, ey = x - size / 2.0, head - 6 - size
            if self.exclaim is not None:
                f = L.exclaim_frame(t - sess.state_at)
                C.draw_part(self.exclaim, f * L.EXCLAIM_FRAME, 0, L.EXCLAIM_FRAME, L.EXCLAIM_FRAME,
                            ex, ey, size, size)
            else:
                C.draw_text("！", ex, ey, size, size, C.text_attrs(34, (255, 230, 60), True))

    def _draw_labels(self, sess, w, top, bottom):
        if self.status_line:
            attrs = C.text_attrs(12.5, C.C_TEXT, bold=True)
            size = C.text_size(self.status_line, attrs)
            bw, bh = size.width + 30, 30
            C.draw_box9(self.textbox, 14, bottom - bh - 12, bw, bh, scale=2)
            C.draw_text(self.status_line, 28, bottom - bh - 12 + 7, size.width + 6, 18, attrs)
        hint = self.hint if self.now < self.hint_until else _default_hint(sess)
        if hint:
            attrs = C.text_attrs(15, (255, 255, 255), bold=True)
            shadow = C.text_attrs(15, (20, 30, 70), bold=True)
            size = C.text_size(hint, attrs)
            x = (w - size.width) / 2.0
            y = top + min(54, max(14, (bottom - top) / 2.0 - 11))
            C.draw_text(hint, x + 1.5, y + 1.5, size.width + 6, 22, shadow)
            C.draw_text(hint, x, y, size.width + 6, 22, attrs)


class Pond(object):
    """水面窗口：贴在任务栏上沿。只有水的那一块接收点击，其余地方点击穿透。"""

    def __init__(self, on_click, on_resize=None, on_menu=None):
        self.widget = None
        self.on_click = on_click
        self.on_resize = on_resize
        self.on_menu = on_menu
        self.column = None          # 水面这一列在屏幕上的范围（QRect，高 = 可用屏幕高）
        self.height = L.POND_HEIGHT
        self.width_mode = "full"
        self.alpha = 1.0

    @property
    def view(self):
        return self.widget

    def configure(self, height=None, width_mode=None, alpha=None):
        if height is not None:
            self.height = L.clamp_height(height)
        if width_mode is not None:
            self.width_mode = width_mode
        if alpha is not None:
            self.alpha = max(0.3, min(1.0, float(alpha)))
        if self.widget is not None:
            self._layout()

    def _layout(self):
        avail = QGuiApplication.primaryScreen().availableGeometry()   # 已经去掉了任务栏
        x, w = L.pond_span(avail.x(), avail.width(), self.width_mode)
        self.column = QRect(int(x), avail.y(), int(w), avail.height())
        h = int(self.height + L.POND_HEADROOM)
        if self.widget is None:
            self.widget = PondWidget()
            self.widget.on_click = self.on_click
            self.widget.on_menu = self.on_menu
            self.widget.on_resize = self.on_resize
        self.widget.setGeometry(int(x), avail.y() + avail.height() - h, int(w), h)
        self.widget.pond_h = self.height
        self.widget.setWindowOpacity(self.alpha)

    def attach(self, sess):
        self._layout()
        self.widget.session = sess
        self.widget.show()

    def hide(self):
        if self.widget is not None:
            self.widget.hide()
            P.set_click_through(self.widget, True)
            self.widget.dragging = False

    @property
    def visible(self):
        return self.widget is not None and self.widget.isVisible()

    def flash(self, text, now, seconds=1.8):
        if self.widget is not None:
            self.widget.hint = text
            self.widget.hint_until = now + seconds

    def _water_h(self):
        sess = self.widget.session if self.widget is not None else None
        return self.height * L.ease_out(sess.level) if sess else 0.0

    def contains(self, pos):
        """全局坐标的点是不是在水面（含顶边手柄）上。"""
        if not self.visible:
            return False
        c = self.column
        bottom = c.y() + c.height()
        return (c.x() <= pos.x() <= c.x() + c.width()
                and bottom - self._water_h() - L.HANDLE_ZONE <= pos.y() <= bottom)

    def update(self, now, status_line, pos):
        if not self.visible:
            return
        v = self.widget
        v.now = now
        v.status_line = status_line
        sess = v.session
        ready = sess is not None and sess.level >= 1.0
        over = self.contains(pos)
        top_y = self.column.y() + self.column.height() - self._water_h()
        v.hover_handle = _can_resize(sess) and over and abs(pos.y() - top_y) <= L.HANDLE_ZONE
        P.set_click_through(v, not ((over and ready) or v.dragging))
        v.update()

    def water_top_y(self):
        """水面顶端的全局 y（Qt 坐标，向下为正）。"""
        return self.column.y() + self.column.height() - self.height


# MARK: 钓鱼竖条

class PanelWidget(QWidget):

    def __init__(self):
        super(PanelWidget, self).__init__()
        P.make_overlay(self, click_through=False)
        self.game = None
        self.scale = 3
        self.now = 0.0
        self.panel = C.ui("panel")
        self.bar_top, self.bar_mid, self.bar_bot = C.ui("bar_top"), C.ui("bar_mid"), C.ui("bar_bot")
        self.fish = C.ui("fish")
        self.chest = C.ui("chest")

    def paintEvent(self, e):
        g, s = self.game, self.scale
        with C.painting(self):
            if self.panel is not None:
                C.draw(self.panel, 0, 0, L.PANEL_W * s, L.PANEL_H * s)
            else:
                C.stardew_box(8 * s, 0, 30 * s, L.PANEL_H * s, step=s)
                C.fill_rect(L.TRACK_X * s, 3 * s, L.TRACK_W * s, 139 * s, TRACK_BLUE)
            if g is None:
                return
            t = self.now
            x, y, w, h = L.bar_rect(g, s)
            alpha = L.bar_alpha(g.fish_in_bar(), t)
            if self.bar_mid is not None:
                cap = 2 * s
                C.draw(self.bar_top, x, y, w, cap, alpha)
                C.draw(self.bar_mid, x, y + cap, w, h - cap * 2, alpha)
                C.draw(self.bar_bot, x, y + h - cap, w, cap, alpha)
            else:
                C.fill_rect(x, y, w, h, BAR_GREEN, alpha)
            shake = math.sin(t * 40) * 0.5 if g.fish_in_bar() else 0.0
            fx, fy, fw, fh = L.fish_rect(g, s, shake)
            if self.fish is not None:
                C.draw(self.fish, fx, fy, fw, fh)
            else:
                C.fill_oval(fx, fy, fw, fh, FISH_FALLBACK)
            if g.treasure_visible:
                cx, cy, cw, ch = L.treasure_rect(g, s)
                if self.chest is not None:
                    C.draw(self.chest, cx, cy, cw, ch)
                else:
                    C.fill_rect(cx, cy + ch * 0.35, cw, ch * 0.65, (150, 90, 40))
                    C.fill_rect(cx, cy, cw, ch * 0.4, (190, 120, 50))
                px, py, pw, ph = L.treasure_progress_rect(g, s)
                if pw > 0:
                    C.fill_rect(px, py, pw, ph, (250, 200, 60))
            px, py, pw, ph = L.progress_rect(g.progress, s)
            if ph > 0:
                C.fill_rect(px, py, pw, ph, L.progress_color(g.progress))


class Panel(object):

    def __init__(self):
        self.widget = None

    @property
    def view(self):
        return self.widget

    def show(self, game, cast_x, column, water_top_y, scale):
        w, h = L.PANEL_W * scale, L.PANEL_H * scale
        x = column.x() + L.panel_origin(cast_x, column.width(), scale)
        y = water_top_y - 18 - h
        if self.widget is None:
            self.widget = PanelWidget()
        self.widget.setGeometry(int(x), int(y), int(w), int(h))
        self.widget.scale = scale
        self.widget.game = game
        self.widget.show()

    def hide(self):
        if self.widget is not None:
            self.widget.hide()
            self.widget.game = None

    @property
    def visible(self):
        return self.widget is not None and self.widget.isVisible()

    def update(self, now):
        if self.visible:
            self.widget.now = now
            self.widget.update()


# MARK: 结果提示

TOAST_W, TOAST_H = 320, 128


class ToastWidget(QWidget):

    def __init__(self):
        super(ToastWidget, self).__init__()
        P.make_overlay(self, click_through=True)
        self.result = None
        self.message = None
        self.items = {}

    def _item_name(self, item_id):
        it = self.items.get(item_id)
        return it.display_name if it is not None else item_id

    def paintEvent(self, e):
        with C.painting(self):
            W, H = self.width(), self.height()
            C.draw_box9(C.ui("textbox"), 0, 0, W, H, scale=3)
            r = self.result
            if r is None:
                if self.message:
                    C.draw_text(self.message, 22, 20, W - 44, H - 30,
                                C.text_attrs(15, C.C_TEXT, bold=True))
                return
            if r.junk:
                C.draw(C.image(junk_icon_path(r.fish.id)), 20, 20, 64, 64)
                C.draw_text(r.fish.display_name, 100, 22, 200, 24, C.text_attrs(18, C.C_TEXT, True))
                C.draw_text("钓上来一个杂物……", 100, 50, 200, 20, C.text_attrs(12.5, C.C_TEXT))
                xp = "+%d 经验" % r.xp + ("  ⬆ 钓鱼等级 %d！" % r.level_up if r.level_up else "")
                C.draw_text(xp, 100, 70, 210, 20, C.text_attrs(12, C.C_EDGE_MID))
                C.draw_text("点水面再来一竿", 100, 90, 200, 20, C.text_attrs(12, C.C_EDGE_MID))
                return
            if not r.caught:
                C.draw(C.image(fish_icon_path(r.fish.id, shadow=True)), 20, 20, 64, 64)
                C.draw_text("鱼跑掉了……", 100, 26, 200, 24, C.text_attrs(17, C.C_TEXT, True))
                C.draw_text("点水面再来一竿", 100, 56, 200, 20, C.text_attrs(12.5, C.C_TEXT))
                return
            C.draw(C.image(fish_icon_path(r.fish.id)), 20, 20, 64, 64)
            if r.quality:
                star = C.ui("star_%d" % r.quality)
                if star is not None:
                    C.draw(star, 14, 62, 24, 24)
                else:
                    C.fill_star(26, 74, 9, progression.QUALITY_COLORS[r.quality])
            C.draw_text(r.fish.display_name, 100, 14, 210, 24, C.text_attrs(18, C.C_TEXT, True))
            line = "%d 英寸（约 %d 厘米）" % (r.size, round(r.size * 2.54))
            if r.quality:
                line += " · %s" % progression.QUALITY_NAMES[r.quality]
            C.draw_text(line, 100, 41, 210, 20, C.text_attrs(12.5, C.C_TEXT))
            tags = [t for t, on in (("✨ 新鱼种", r.is_new), ("🏆 破纪录", r.is_record),
                                    ("完美！", r.perfect)) if on]
            if tags:
                C.draw_text("  ".join(tags), 100, 61, 210, 20,
                            C.text_attrs(12.5, C.C_EDGE_GOLD, bold=True))
            xp = "+%d 经验 · +%dg" % (r.xp, r.gold)
            if r.level_up:
                xp += "  ⬆ 钓鱼等级 %d！" % r.level_up
            C.draw_text(xp, 100, 81, 210, 18, C.text_attrs(12, C.C_EDGE_MID, bool(r.level_up)))
            if r.treasure:
                names = "、".join("%s ×%d" % (self._item_name(i), n) for i, n in r.treasure)
                C.draw_text("🎁 宝箱：" + names, 20, 100, W - 40, 18, C.text_attrs(12, C.C_TEXT))


class Toast(object):

    def __init__(self, items=None):
        self.widget = None
        self.items = items or {}

    @property
    def view(self):
        return self.widget

    def _show(self, cast_x, column, water_top_y):
        x = column.x() + cast_x * column.width() - TOAST_W / 2.0
        x = max(column.x() + 12, min(column.x() + column.width() - TOAST_W - 12, x))
        if self.widget is None:
            self.widget = ToastWidget()
            self.widget.items = self.items
        self.widget.setGeometry(int(x), int(water_top_y - 24 - TOAST_H), TOAST_W, TOAST_H)
        self.widget.show()
        self.widget.update()

    def show_result(self, result, cast_x, column, water_top_y):
        self._show(cast_x, column, water_top_y)
        self.widget.result, self.widget.message = result, None

    def show_message(self, text, column, water_top_y):
        self._show(0.5, column, water_top_y)
        self.widget.result, self.widget.message = None, text

    def hide(self):
        if self.widget is not None and self.widget.isVisible():
            self.widget.hide()

    @property
    def visible(self):
        return self.widget is not None and self.widget.isVisible()
