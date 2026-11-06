# -*- coding: utf-8 -*-
"""Windows 版农田：完成番茄时的小卡片、「我的农田」窗口、桌面上的农田摆件。画法和 Mac 版一样。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QWidget

from .. import farm as farmlib
from ..gamecontent import crop_sprite_path, junk_icon_path
from . import platform as P
from . import qtdraw as C
from ..ui.farm_window_model import CHOOSER_H, ICON, PLAN_H, WIN_W, chooser_items, plan_label  # noqa: F401
from .base import GameWindow

from ..ui.farm_window_model import (CARD_PITCH, CARD_W, GAP, PAD, PLOT, S,  # noqa: E402
                                    WIN_PITCH, card_h, lines_y, plot_rect, win_h)

CARD_SECONDS = 5.0


def paint_farm(view, closable):
    """卡片和「我的农田」窗口共用的画法：3 块地 + 作物 + 几行字。"""
    W, H = view.width(), view.height()
    C.draw_box9(C.ui("textbox"), 0, 0, W, H, scale=4)
    if closable:
        view.close_rect = C.draw_close(W - C.CLOSE_SIZE - 12, 12)
    if view.title:
        C.draw_text(view.title, PAD, 24, W - PAD * 2 - 44, 22,
                    C.text_attrs(13.5, C.C_TEXT, bold=True))
    if view.farm is None:
        return
    dirt = C.ui("dirt")
    harvested = dict(view.report.harvested) if view.report else {}
    pitch = getattr(view, "pitch", CARD_PITCH)
    for i in range(view.farm.size):
        x, y, w, h = plot_rect(i, getattr(view, "ox", 0), pitch)
        if dirt is not None:
            C.draw(dirt, x, y, w, h)
        else:
            C.fill_rect(x, y + 6, w, h - 6, (96, 58, 30))
            C.fill_rect(x + 3, y + 9, w - 6, h - 12, (122, 76, 40))
        info = view.farm.info(i)
        label = "空地"
        if info is not None:
            img = C.image(crop_sprite_path(info["seed"]))
            cx, cy = x, y + PLOT - 10 - 32 * S
            if img is not None:
                C.draw_part(img, info["frame"] * 16, 0, 16, 32, cx, cy, 16 * S, 32 * S)
            else:
                hh = 8 + info["frame"] * 9
                C.fill_rect(cx + 8 * S - 2, cy + 32 * S - hh, 4, hh, (70, 160, 60))
            label = "%s %d/%d" % (view.name_of(info["harvest"]), info["days"], info["total"])
        if i in harvested:
            C.draw(C.image(junk_icon_path(harvested[i])), x + 8, y - 38, 28, 28)
            C.draw_text("+1", x + 34, y - 34, 30, 16, C.text_attrs(12, (40, 120, 30), True))
            if info is None:
                label = "收获了"
        C.draw_fit(label, x - GAP / 2.0 + 2, y + h + 6, w + GAP - 4, 10.5, C.C_TEXT)   # 一行放下，长名字缩小
    ty = lines_y(view.farm.rows, pitch)
    collection = getattr(view, "collection", None)
    view.hits = []
    if collection is not None:
        _paint_plans(view, collection)
        ty += PLAN_H
    small = C.text_attrs(11.5, C.C_TEXT)
    for line in view.lines:                      # 长的会自动换行，按真正的高度往下排
        lh = C.text_height(line, small, W - PAD * 2)
        C.draw_text(line, PAD, ty, W - PAD * 2, lh + 4, small)
        ty += lh + 2
    if collection is not None:
        _paint_chooser(view, collection, W, H - CHOOSER_H)


def _paint_plans(view, collection):
    """每块地下面：「下次：自动 / 防风草」，点地或点它都能选。"""
    for i in range(view.farm.size):
        x, y, w, h = plot_rect(i, getattr(view, "ox", 0), getattr(view, "pitch", CARD_PITCH))
        bx, by, bw, bh = x - GAP / 2.0 + 2, y + h + 22, w + GAP - 4, 22
        on = view.choosing == i
        if on:
            C.fill_rect(bx + 8, by + bh - 2, bw - 16, 2, C.C_EDGE_GOLD)
        C.draw_fit(plan_label(collection, i, view.name_of), bx - 8, by + 3, bw + 16, 10.5,
                   C.C_EDGE_GOLD if on else C.C_EDGE_MID, bold=on)
        view.hits.append((("plot", i), (x - 6, y - 60, w + 12, h + 60 + PLAN_H + 16)))


def _paint_chooser(view, collection, width, top):
    tb = C.ui("textbox")
    C.fill_rect(PAD, top, width - PAD * 2, 1, C.C_EDGE_INNER)
    if view.choosing is None:
        C.draw_text("点一块地，选它下次种什么（不选就自动，当季优先）", PAD, top + 12, width - PAD * 2, 36,
                    C.text_attrs(11.5, C.C_EDGE_MID))
        return
    C.draw_text("第 %d 块地下次种：" % (view.choosing + 1), PAD, top + 10, width - PAD * 2, 18,
                C.text_attrs(12, C.C_TEXT, bold=True))
    cur = collection.farm_plan[view.choosing]
    per_row = max(1, int((width - PAD * 2 + 8) // (ICON + 8)))
    for k, seed in enumerate(chooser_items(collection)):
        x = PAD + (k % per_row) * (ICON + 8)
        y = top + 34 + (k // per_row) * (ICON + 8)
        if seed == cur:
            C.draw_box9(tb, x - 3, y - 3, ICON + 6, ICON + 6, scale=2, fallback_step=2)
        if seed is None:
            C.draw_text("自动", x, y + 10, ICON, 16, C.text_attrs(11, C.C_TEXT, bold=True, align="center"))
        else:
            C.draw(C.image(junk_icon_path(seed)), x + 2, y + 2, ICON - 4, ICON - 4)
            n = str(collection.count(seed))
            for dx, dy in ((1, 0), (0, 1), (1, 1)):          # 原版物品数量：白字 + 深色描边
                C.draw_text(n, x + ICON - 16 + dx, y + ICON - 14 + dy, 16, 14,
                            C.text_attrs(10, (60, 30, 20), bold=True, align="right"))
            C.draw_text(n, x + ICON - 16, y + ICON - 14, 16, 14,
                        C.text_attrs(10, (255, 255, 255), bold=True, align="right"))
        view.hits.append((("seed", seed), (x, y, ICON, ICON)))


class FarmCardWidget(QWidget):

    def __init__(self):
        super(FarmCardWidget, self).__init__()
        P.make_overlay(self, click_through=True)
        self.resize(WIN_W, card_h(1))               # 和「我的农田」一样宽，标题和作物名放得下
        self.ox = (WIN_W - CARD_W) / 2.0
        self.farm, self.report, self.title, self.lines = None, None, "", []
        self.name_of = str
        self.close_rect = None

    def paintEvent(self, e):
        with C.painting(self):
            paint_farm(self, closable=False)


class FarmCard(object):
    """有收获 / 播种 / 送种子时，右上角弹出来几秒的小卡片。不抢焦点、点击穿透。"""

    def __init__(self, name_of):
        self.name_of = name_of
        self.view = None
        self.until = 0.0

    @property
    def window(self):
        return self.view

    def show(self, farm, report, now, round_no=None):
        if self.view is None:
            self.view = FarmCardWidget()
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.view.move(g.x() + g.width() - WIN_W - 16, g.y() + 8)
        self.view.resize(WIN_W, card_h(farm.rows))
        v = self.view
        v.farm, v.report, v.name_of = farm, report, self.name_of
        v.title = "🍅 完成%s个番茄 · 农田过了一天" % ("第 %d " % round_no if round_no else "一")
        v.lines = farmlib.describe(report, self.name_of)
        v.show()
        v.update()
        self.until = now + CARD_SECONDS

    def update(self, now):
        if self.visible and now >= self.until:
            self.view.hide()

    @property
    def visible(self):
        return self.view is not None and self.view.isVisible()


class FarmWindowWidget(GameWindow):

    def __init__(self):
        super(FarmWindowWidget, self).__init__(WIN_W, win_h(1), "我的农田")
        self.ox = (WIN_W - CARD_W) / 2.0     # 窗口比卡片宽：地居中
        self.pitch = WIN_PITCH
        self.farm, self.report, self.title, self.lines = None, None, "我的农田", []
        self.name_of = str
        self.collection = None
        self.choosing = None
        self.on_pick = None
        self.hits = []

    def on_click(self, x, y):
        for (kind, key), r in self.hits:
            if r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]:
                if kind == "plot":
                    self.choosing = None if self.choosing == key else key
                elif kind == "seed" and self.choosing is not None:
                    if self.on_pick:
                        self.on_pick(self.choosing, key)
                    self.choosing = None
                self.update()
                return True
        return False

    def paintEvent(self, e):
        with C.painting(self):
            paint_farm(self, closable=True)


class FarmWindow(object):
    """托盘菜单 →「我的农田…」。"""

    def __init__(self, farm, collection, name_of, season=None, on_change=None):
        self.farm, self.collection, self.name_of = farm, collection, name_of
        self.season, self.on_change = season, on_change
        self.view = None

    @property
    def window(self):
        return self.view

    def refresh(self):
        if self.view is None:
            return
        v = self.view
        if v.height() != win_h(self.farm.rows):      # 刚扩建：窗口跟着变高
            v.setFixedSize(WIN_W, win_h(self.farm.rows))
        v.farm, v.name_of = self.farm, self.name_of
        n = sum(self.collection.count(s) for s in farmlib.CROPS)
        v.lines = ["每完成一个番茄长一天，成熟自动收获 · 手上 %d 包种子" % n]
        v.update()

    def pick(self, plot, seed):
        """给一块地选好种子（None = 自动）；空地马上种下。"""
        farmlib.set_plan(self.farm, self.collection, plot, seed, self.season() if self.season else "spring")
        self.refresh()
        if self.on_change:
            self.on_change()

    def show(self):
        if self.view is None:
            self.view = FarmWindowWidget()
            self.view.collection = self.collection
            self.view.on_pick = self.pick
            self.view.center()
        self.refresh()
        self.view.present()


# MARK: 桌面摆件（和 Mac 版一样：没有底、没有框，只有原版物件）

from ..ui.farm_window_model import (CAPTION_H, DESK_COLS, DESK_PAD_X, DESK_TILE, DESK_W, POP_SECONDS,  # noqa: E402
                                    SOIL_Y, caption_y, desk_h, desk_plot_xy, desk_tiles)

DESK_H = desk_h(1)


class FarmDeskWidget(QWidget):

    def __init__(self, on_top=True):
        super(FarmDeskWidget, self).__init__()
        self.on_top = None
        # 透明背景必须在原生窗口创建之前设好（set_level 里会创建），不然 Windows 上是黑底
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.set_level(on_top)
        self.resize(DESK_W, DESK_H)
        self.farm = None
        self.caption = ""
        self.watered = False
        self.now = 0.0
        self.pops = []
        self.on_moved = None
        self.on_menu = None        # 右键：返回一个 QMenu
        self._drag = None

    def set_level(self, on_top):
        """浮在所有窗口上面（和钓鱼一样），或压在普通窗口下面（只在露出桌面时看得到）。"""
        on_top = bool(on_top)
        if on_top == self.on_top:
            return
        self.on_top = on_top
        shown = self.isVisible()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                            | Qt.NoDropShadowWindowHint
                            | (Qt.WindowStaysOnTopHint if on_top else Qt.WindowStaysOnBottomHint))
        self.setAttribute(Qt.WA_TranslucentBackground, True)   # 改标志会重建原生窗口：透明要跟着
        P.set_no_activate(self)           # 改标志会重建原生窗口，样式要重新设
        if shown:                         # 改窗口标志会把窗口藏起来，重新显示
            self.show()

    def enterEvent(self, e):
        self.setCursor(Qt.OpenHandCursor)          # 能拖动

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = QCursor.pos() - self.pos()
            self.setCursor(Qt.ClosedHandCursor)
        elif e.button() == Qt.RightButton and self.on_menu is not None:
            self.on_menu().exec(QCursor.pos())

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(QCursor.pos() - self._drag)

    def mouseReleaseEvent(self, e):
        self.setCursor(Qt.OpenHandCursor)
        if self._drag is not None:
            self._drag = None
            if self.on_moved:
                self.on_moved()

    def paintEvent(self, e):
        t, ox = DESK_TILE, DESK_PAD_X
        with C.painting(self):
            fence = [C.ui(k) for k in ("fence_l", "fence_m", "fence_r")]
            for c in range(DESK_COLS):
                piece = fence[0 if c == 0 else (2 if c == DESK_COLS - 1 else 1)]
                if piece is not None:
                    C.draw(piece, ox + c * t, SOIL_Y - int(t * 1.7), t, t * 2)
                else:
                    C.fill_rect(ox + c * t + t * 0.4, SOIL_Y - t * 1.2, t * 0.2, t * 1.1, (120, 70, 40))
                    C.fill_rect(ox + c * t, SOIL_Y - t * 0.9, t, t * 0.15, (150, 95, 50))
            rows = self.farm.rows if self.farm is not None else 1
            for i, (dry, wet) in enumerate(desk_tiles(rows)):
                x, y = desk_plot_xy(i)
                img = C.ui(dry)
                if img is not None:
                    C.draw(img, x, y, t, t)
                    if self.watered:                     # 原版：浇水是半透明的一层盖在干地上
                        C.draw(C.ui(wet), x, y, t, t)
                else:
                    C.fill_rect(x + 2, y + 4, t - 4, t - 8, (122, 76, 40))
            if self.farm is not None:
                for i in range(self.farm.size):          # 后排先画，前排的作物挡住后排
                    info = self.farm.info(i)
                    if info is None:
                        continue
                    img = C.image(crop_sprite_path(info["seed"]))
                    x, sy = desk_plot_xy(i)
                    if img is not None:
                        C.draw_part(img, info["frame"] * 16, 0, 16, 32, x, sy - t - 6, t, 2 * t)
                    else:
                        hh = 8 + info["frame"] * 9
                        C.fill_rect(x + t / 2.0 - 2, sy + t - 6 - hh, 4, hh, (70, 160, 60))
            for plot, item, start in self.pops:
                k = (self.now - start) / POP_SECONDS
                if 0 <= k <= 1:
                    x, sy = desk_plot_xy(plot)
                    C.draw(C.image(junk_icon_path(item)), x + t * 0.15, sy - 12 - k * 40,
                           t * 0.7, t * 0.7, 1.0 - k * k)
            # 进度：原版说明框做底的一行字（只一行，放不下就缩小字号），后面的窗口不会透上来
            if self.caption:
                self._draw_caption(caption_y(rows))

    def _draw_caption(self, cy):
        pad, size = 14, 12.0
        avail = DESK_W - 4 - pad * 2
        while size > 9 and C.text_size(self.caption, C.text_attrs(size, C.C_TEXT, True)).width > avail:
            size -= 0.5
        attrs = C.text_attrs(size, C.C_TEXT, True)
        ts = C.text_size(self.caption, attrs)
        tw = min(ts.width, avail)
        bw, bh = tw + pad * 2, CAPTION_H
        bx = (DESK_W - bw) / 2.0
        C.draw_box9(C.ui("textbox"), bx, cy, bw, bh, scale=2)
        C.draw_text(self.caption, bx + pad, cy + (bh - ts.height) / 2.0, tw + 4, ts.height + 2, attrs)


class FarmDesk(object):
    """番茄钟期间的农田摆件（可选）：浮在所有窗口上面（默认），或压在桌面上。拖动可以换位置。"""

    def __init__(self, farm, name_of, load_pos=None, save_pos=None):
        self.farm = farm
        self.name_of = name_of
        self.load_pos = load_pos or (lambda: None)
        self.save_pos = save_pos or (lambda pos: None)
        self.view = None
        self.on_top = True
        self.on_menu = None

    def contains(self, pos):
        """鼠标（屏幕坐标）在不在摆件上：在的话下面那行字展开成完整版。"""
        return self.visible and self.view.frameGeometry().contains(pos)

    @property
    def window(self):
        return self.view

    def set_on_top(self, on_top):
        self.on_top = bool(on_top)
        if self.view is not None:
            self.view.set_level(self.on_top)

    def _create(self):
        self.view = FarmDeskWidget(self.on_top)
        self.view.on_menu = self.on_menu
        g = QGuiApplication.primaryScreen().availableGeometry()
        pos = self.load_pos()
        if pos:
            self.view.move(int(pos[0]), int(pos[1]))
        else:
            self.view.move(g.x() + g.width() - DESK_W - 60, g.y() + 200)
        self.view.on_moved = lambda: self.save_pos([self.view.x(), self.view.y()])

    def refresh(self, season=None, caption=None, watered=None):
        if self.view is None:
            return
        h = desk_h(self.farm.rows)
        if self.view.height() != h:              # 刚扩建：往下长一排
            self.view.resize(DESK_W, h)
        self.view.farm = self.farm
        if watered is not None:
            self.view.watered = bool(watered)
        if caption is not None and caption != self.view.caption:
            self.view.caption = caption
        self.view.update()

    def pop(self, harvested, now):
        if self.view is not None:
            self.view.pops = [(i, item, now) for i, item in harvested]
            self.view.now = now
            self.view.update()

    def update(self, now):
        v = self.view
        if v is not None and v.pops and self.visible:
            v.now = now
            if all(now - start > POP_SECONDS for _, _, start in v.pops):
                v.pops = []
            v.update()

    def set_visible(self, show):
        if show:
            if self.view is None:
                self._create()
                self.refresh()
            if not self.view.isVisible():
                self.view.show()
        elif self.visible:
            self.view.hide()

    @property
    def visible(self):
        return self.view is not None and self.view.isVisible()
