# -*- coding: utf-8 -*-
"""农田：完成一个番茄时右上角弹出的小卡片，以及菜单里「我的农田」窗口。

画面素材来自本机游戏：锄过的地（TerrainFeatures/hoeDirt）、作物生长图（TileSheets/crops）、
说明框（Cursors 里的九宫格）。读不到时退回代码画的样子。
"""
import objc
from Cocoa import NSApplication, NSMakeRect, NSMenu, NSScreen, NSView

from .. import farm as farmlib
from ..gamecontent import crop_sprite_path, junk_icon_path, ui_path
from . import common as C

from .farm_window_model import (CARD_PITCH, CARD_W, CHOOSER_H, GAP, ICON, PAD, PLAN_H, PLOT, S,
                                WIN_PITCH, WIN_W, card_h, chooser_items, lines_y, plan_label,
                                plot_rect, win_h)

CARD_SECONDS = 5.0
WIN_H = win_h(1)


class FarmView(NSView):

    def initWithFrame_(self, frame):
        self = objc.super(FarmView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.farm = None
        self.report = None        # farmlib.DayReport：卡片上标出这次的变化
        self.name_of = lambda item_id: str(item_id)
        self.lines = []
        self.title = ""
        self.textbox = C.image(ui_path("textbox"))
        self.dirt = C.image(ui_path("dirt"))
        self.closable = False      # 「我的农田」窗口里才有红叉；弹出的小卡片没有
        self.close_rect = None
        self.ox = 0                # 窗口比卡片宽：地往右挪这么多，居中
        self.pitch = CARD_PITCH    # 扩建成两排后两排地的间距
        self.collection = None     # 有它 = 「我的农田」窗口：可以点地选下次种什么
        self.choosing = None       # 正在给哪块地选
        self.on_pick = None        # on_pick(格子, 种子 id 或 None)
        self.hits = []
        return self

    def isFlipped(self):
        return True

    def acceptsFirstResponder(self):
        return self.closable

    def keyDown_(self, event):
        if self.closable and C.is_close_key(event):
            C.close_window(self)

    def mouseDown_(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        if self.closable and C.in_rect(p, self.close_rect):
            C.close_window(self)
            return
        for (kind, key), r in self.hits:
            if C.in_rect(p, r):
                self._click(kind, key)
                self.setNeedsDisplay_(True)
                return
        C.drag_window(self, event)

    @objc.python_method
    def _click(self, kind, key):
        if kind == "plot":
            self.choosing = None if self.choosing == key else key
        elif kind == "seed" and self.choosing is not None:
            if self.on_pick:
                self.on_pick(self.choosing, key)
            self.choosing = None

    def drawRect_(self, rect):
        C.pixel_mode()
        b = self.bounds()
        C.draw_box9(self.textbox, 0, 0, b.size.width, b.size.height, scale=4)
        if self.closable:
            self.close_rect = C.draw_close(b.size.width - C.CLOSE_SIZE - 12, 12)
        bold = C.text_attrs(13.5, C.C_TEXT, bold=True)
        small = C.text_attrs(11.5, C.C_TEXT)
        if self.title:
            C.draw_text(self.title, PAD, 24, b.size.width - PAD * 2 - 44, 20, bold)
        if self.farm is None:
            return
        harvested = dict(self.report.harvested) if self.report else {}
        for i in range(self.farm.size):
            x, y, w, h = plot_rect(i, self.ox, self.pitch)
            if self.dirt is not None:
                C.draw(self.dirt, x, y, w, h)
            else:
                C.fill_rect(x, y + 6, w, h - 6, (96, 58, 30))
                C.fill_rect(x + 3, y + 9, w - 6, h - 12, (122, 76, 40))
            info = self.farm.info(i)
            label = "空地"
            if info is not None:
                self._draw_crop(info["seed"], info["frame"], x, y)
                label = "%s %d/%d" % (self.name_of(info["harvest"]), info["days"], info["total"])
            if i in harvested:
                # 收获的那一下：作物图标往上冒，带「+1」
                C.draw(C.image(junk_icon_path(harvested[i])), x + 8, y - 38, 28, 28)
                C.draw_text("+1", x + 34, y - 34, 30, 16, C.text_attrs(12, (40, 120, 30), bold=True))
                if info is None:
                    label = "收获了"
            C.draw_fit(label, x - GAP / 2.0 + 2, y + h + 6, w + GAP - 4, 10.5, C.C_TEXT)   # 一行放下，长名字缩小
        ty = lines_y(self.farm.rows, self.pitch)
        self.hits = []
        if self.collection is not None:
            self._draw_plans(b.size.width)
            ty += PLAN_H
        for line in self.lines:                  # 长的会自动换行，按真正的高度往下排
            lh = C.text_height(line, small, b.size.width - PAD * 2)
            C.draw_text(line, PAD, ty, b.size.width - PAD * 2, lh + 4, small)
            ty += lh + 2
        if self.collection is not None:
            self._draw_chooser(b.size.width, b.size.height - CHOOSER_H)

    @objc.python_method
    def _draw_plans(self, width):
        """每块地下面：「下次：自动 / 防风草」，点地或点它都能选。"""
        for i in range(self.farm.size):
            x, y, w, h = plot_rect(i, self.ox, self.pitch)
            bx, by, bw, bh = x - GAP / 2.0 + 2, y + h + 22, w + GAP - 4, 22
            if self.choosing == i:
                C.fill_rect(bx + 8, by + bh - 2, bw - 16, 2, C.C_EDGE_GOLD)
            C.draw_fit(plan_label(self.collection, i, self.name_of), bx - 8, by + 3, bw + 16, 10.5,
                       C.C_EDGE_GOLD if self.choosing == i else C.C_EDGE_MID, bold=self.choosing == i)
            self.hits.append((("plot", i), (x - 6, y - 60, w + 12, h + 60 + PLAN_H + 16)))

    @objc.python_method
    def _draw_chooser(self, width, top):
        C.fill_rect(PAD, top, width - PAD * 2, 1, C.C_EDGE_INNER)
        if self.choosing is None:
            C.draw_text("点一块地，选它下次种什么（不选就自动，当季优先）", PAD, top + 12, width - PAD * 2, 36,
                        C.text_attrs(11.5, C.C_EDGE_MID))
            return
        C.draw_text("第 %d 块地下次种：" % (self.choosing + 1), PAD, top + 10, width - PAD * 2, 18,
                    C.text_attrs(12, C.C_TEXT, bold=True))
        cur = self.collection.farm_plan[self.choosing]
        per_row = max(1, int((width - PAD * 2 + 8) // (ICON + 8)))
        for k, seed in enumerate(chooser_items(self.collection)):
            x = PAD + (k % per_row) * (ICON + 8)
            y = top + 34 + (k // per_row) * (ICON + 8)
            if seed == cur:
                C.draw_box9(self.textbox, x - 3, y - 3, ICON + 6, ICON + 6, scale=2, fallback_step=2)
            if seed is None:
                C.draw_text("自动", x, y + 10, ICON, 16, C.text_attrs(11, C.C_TEXT, bold=True, align="center"))
            else:
                C.draw(C.image(junk_icon_path(seed)), x + 2, y + 2, ICON - 4, ICON - 4)
                n = str(self.collection.count(seed))
                for dx, dy in ((1, 0), (0, 1), (1, 1)):      # 原版物品数量：白字 + 深色描边
                    C.draw_text(n, x + ICON - 16 + dx, y + ICON - 14 + dy, 16, 14,
                                C.text_attrs(10, (60, 30, 20), bold=True, align="right"))
                C.draw_text(n, x + ICON - 16, y + ICON - 14, 16, 14,
                            C.text_attrs(10, (255, 255, 255), bold=True, align="right"))
            self.hits.append((("seed", seed), (x, y, ICON, ICON)))

    @objc.python_method
    def _draw_crop(self, seed, frame, x, y):
        img = C.image(crop_sprite_path(seed))
        cw, ch = 16 * S, 32 * S
        cx, cy = x, y + PLOT - 10 - ch
        if img is not None:
            C.draw_part(img, frame * 16, 0, 16, 32, cx, cy, cw, ch)
        else:
            hh = 8 + frame * 9
            C.fill_rect(cx + cw / 2.0 - 2, cy + ch - hh, 4, hh, (70, 160, 60))


describe = farmlib.describe       # 共用：把这次的变化写成两三行字（在 farm.py）


class FarmCard(object):
    """完成一个番茄时，右上角菜单栏下面弹出来几秒的小卡片。不抢焦点、点击穿透。"""

    def __init__(self, name_of):
        self.window = None
        self.view = None
        self.name_of = name_of
        self.until = 0.0

    def show(self, farm, report, now, round_no=None):
        vf = NSScreen.mainScreen().visibleFrame()
        x = vf.origin.x + vf.size.width - WIN_W - 16
        h = card_h(farm.rows)
        y = vf.origin.y + vf.size.height - h - 8
        rect = NSMakeRect(x, y, WIN_W, h)            # 和「我的农田」一样宽，标题和作物名放得下
        if self.window is None:
            self.window = C.overlay_window(rect, click_through=True)
            self.view = FarmView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, h))
            self.view.ox = (WIN_W - CARD_W) / 2.0
            self.window.setContentView_(self.view)
        else:
            self.window.setFrame_display_(rect, False)
            self.view.setFrame_(NSMakeRect(0, 0, WIN_W, h))
        v = self.view
        v.farm, v.report, v.name_of = farm, report, self.name_of
        v.title = "🍅 完成%s个番茄 · 农田过了一天" % ("第 %d " % round_no if round_no else "一")
        v.lines = describe(report, self.name_of)
        v.setNeedsDisplay_(True)
        self.window.orderFrontRegardless()
        self.until = now + CARD_SECONDS

    def update(self, now):
        if self.window is not None and self.window.isVisible() and now >= self.until:
            self.window.orderOut_(None)

    @property
    def visible(self):
        return self.window is not None and self.window.isVisible()


class FarmWindow(object):
    """菜单 →「我的农田…」：看看地里长到哪了、手上有什么种子。"""

    W = WIN_W + 24

    def __init__(self, farm, collection, name_of, season=None, on_change=None):
        self.farm = farm
        self.collection = collection
        self.name_of = name_of
        self.season = season
        self.on_change = on_change
        self.window = None
        self.view = None
        self.rows = 0

    def _create(self):
        self.rows = self.farm.rows
        h = win_h(self.rows)
        win = C.game_window(self.W, h + 36, "我的农田")
        self.view = FarmView.alloc().initWithFrame_(NSMakeRect(12, 6, WIN_W, h))
        self.view.closable = True
        self.view.pitch = WIN_PITCH
        self.view.ox = (WIN_W - CARD_W) / 2.0
        self.view.collection = self.collection
        self.view.on_pick = self.pick
        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, self.W, h + 36))
        content.addSubview_(self.view)
        win.setContentView_(content)
        win.center()
        self.window = win

    def refresh(self):
        if self.view is None:
            return
        if self.farm.rows != self.rows:          # 刚扩建：窗口跟着变高
            self.rows = self.farm.rows
            h = win_h(self.rows)
            self.window.setContentSize_((self.W, h + 36))
            self.window.contentView().setFrame_(NSMakeRect(0, 0, self.W, h + 36))
            self.view.setFrame_(NSMakeRect(12, 6, WIN_W, h))
        v = self.view
        v.farm, v.report, v.name_of = self.farm, None, self.name_of
        v.title = "我的农田"
        n = sum(self.collection.count(s) for s in farmlib.CROPS)
        v.lines = ["每完成一个番茄长一天，成熟自动收获 · 手上 %d 包种子" % n]
        v.setNeedsDisplay_(True)

    def pick(self, plot, seed):
        """给一块地选好种子（None = 自动）；空地马上种下。"""
        season = self.season() if self.season else "spring"
        farmlib.set_plan(self.farm, self.collection, plot, seed, season)
        self.refresh()
        if self.on_change:
            self.on_change()

    def show(self):
        if self.window is None:
            self._create()
        self.refresh()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
        self.window.makeFirstResponder_(self.view)


# MARK: 桌面摆件

from .farm_window_model import (DESK_COLS, DESK_PAD_X, DESK_TILE, DESK_W, POP_SECONDS,  # noqa: E402
                                SOIL_Y, caption_y, desk_h, desk_plot_xy, desk_tiles)

DESK_H = desk_h(1)


def _desktop_level():
    """比桌面图标高一层、比所有普通窗口低：只在露出桌面的地方看得到，不挡工作。"""
    try:
        from Quartz import CGWindowLevelForKey, kCGDesktopIconWindowLevelKey
        return int(CGWindowLevelForKey(kCGDesktopIconWindowLevelKey)) + 1
    except Exception:
        return -1


class FarmDeskView(NSView):
    """番茄钟期间的一小块地：没有底、没有框，只有原版的物件——后排木栅栏、连成一条的锄地、
    作物；专注的时候地是浇过水的深色（和游戏里浇完水一样），摸鱼时是干的。下面一行字是倒计时。"""

    def initWithFrame_(self, frame):
        self = objc.super(FarmDeskView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.farm = None
        self.now = 0.0
        self.caption = ""
        self.pops = []             # [(格子, 物品 id, 开始时间)]：收获时往上冒的图标
        self.on_moved = None
        self.on_menu = None        # 右键：返回一个 NSMenu
        self.watered = False
        self.fence = [C.image(ui_path(k)) for k in ("fence_l", "fence_m", "fence_r")]
        return self

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def rightMouseDown_(self, event):
        if self.on_menu is not None:
            NSMenu.popUpContextMenu_withEvent_forView_(self.on_menu(), event, self)

    def mouseDown_(self, event):
        C.drag_window(self, event)          # 拖着挪位置；松手后记住
        if self.on_moved:
            self.on_moved()

    def drawRect_(self, rect):
        C.pixel_mode()
        t, ox = DESK_TILE, DESK_PAD_X
        rows = self.farm.rows if self.farm is not None else 1
        for c in range(DESK_COLS):
            piece = self.fence[0 if c == 0 else (2 if c == DESK_COLS - 1 else 1)]
            if piece is not None:
                C.draw(piece, ox + c * t, SOIL_Y - int(t * 1.7), t, t * 2)
            else:
                C.fill_rect(ox + c * t + t * 0.4, SOIL_Y - t * 1.2, t * 0.2, t * 1.1, (120, 70, 40))
                C.fill_rect(ox + c * t, SOIL_Y - t * 0.9, t, t * 0.15, (150, 95, 50))
        for i, (dry, wet) in enumerate(desk_tiles(rows)):
            x, y = desk_plot_xy(i)
            img = C.image(ui_path(dry))
            if img is not None:
                C.draw(img, x, y, t, t)
                if self.watered:                     # 原版：浇水是半透明的一层盖在干地上
                    C.draw(C.image(ui_path(wet)), x, y, t, t)
            else:
                C.fill_rect(x + 2, y + 4, t - 4, t - 8, (96, 60, 34) if self.watered else (122, 76, 40))
        if self.farm is not None:
            for i in range(self.farm.size):          # 后排先画，前排的作物挡住后排
                info = self.farm.info(i)
                if info is None:
                    continue
                img = C.image(crop_sprite_path(info["seed"]))
                x, sy = desk_plot_xy(i)
                y = sy + t - 2 * t - 6
                if img is not None:
                    C.draw_part(img, info["frame"] * 16, 0, 16, 32, x, y, t, t * 2)
                else:
                    hh = 8 + info["frame"] * 9
                    C.fill_rect(x + t / 2.0 - 2, sy + t - 6 - hh, 4, hh, (70, 160, 60))
        # 收获：作物图标从地里往上冒、慢慢变淡（和游戏里捡起东西时一样）
        for plot, item, start in self.pops:
            k = (self.now - start) / POP_SECONDS
            if 0 <= k <= 1:
                x, sy = desk_plot_xy(plot)
                C.draw(C.image(junk_icon_path(item)), x + t * 0.15, sy - 12 - k * 40,
                       t * 0.7, t * 0.7, 1.0 - k * k)
        # 进度：白字 + 深色描边，没有底框
        if self.caption:
            cy = caption_y(rows)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
                C.draw_text(self.caption, dx, cy + dy, DESK_W, 18,
                            C.text_attrs(12, (60, 30, 20), bold=True, align="center"))
            C.draw_text(self.caption, 0, cy, DESK_W, 18,
                        C.text_attrs(12, (255, 248, 230), bold=True, align="center"))


class FarmDesk(object):
    """番茄钟期间的农田摆件（可选）：浮在所有窗口上面（默认），或压在桌面上。拖动可以换位置。"""

    def __init__(self, farm, name_of, load_pos=None, save_pos=None):
        self.farm = farm
        self.name_of = name_of
        self.load_pos = load_pos or (lambda: None)
        self.save_pos = save_pos or (lambda pos: None)
        self.window = None
        self.view = None
        self.on_top = True
        self.on_menu = None

    def contains(self, mouse):
        """鼠标（屏幕坐标）在不在摆件上：在的话下面那行字展开成完整版。"""
        if not self.visible:
            return False
        f = self.window.frame()
        return (f.origin.x <= mouse.x <= f.origin.x + f.size.width
                and f.origin.y <= mouse.y <= f.origin.y + f.size.height)

    def _create(self):
        vf = NSScreen.mainScreen().visibleFrame()
        pos = self.load_pos()
        if pos:
            x, y = pos
        else:
            x = vf.origin.x + vf.size.width - DESK_W - 40
            y = vf.origin.y + vf.size.height - DESK_H - 260
        h = desk_h(self.farm.rows)
        self.window = C.overlay_window(NSMakeRect(x, y + DESK_H - h, DESK_W, h), click_through=False)
        self.window.setHasShadow_(False)
        self._apply_level()
        self.view = FarmDeskView.alloc().initWithFrame_(NSMakeRect(0, 0, DESK_W, h))
        self.view.on_moved = self._moved
        self.view.on_menu = self.on_menu
        self.window.setContentView_(self.view)

    def _apply_level(self):
        if self.window is not None:
            self.window.setLevel_(C.FLOATING_LEVEL if self.on_top else _desktop_level())

    def set_on_top(self, on_top):
        self.on_top = bool(on_top)
        self._apply_level()

    def _moved(self):
        o = self.window.frame().origin
        self.save_pos([float(o.x), float(o.y)])

    def refresh(self, season=None, caption=None, watered=None):
        if self.view is None:
            return
        h = desk_h(self.farm.rows)
        f = self.window.frame()
        if f.size.height != h:                   # 刚扩建：往下长一排，上沿不动
            self.window.setFrame_display_(NSMakeRect(f.origin.x, f.origin.y + f.size.height - h, DESK_W, h), True)
            self.view.setFrame_(NSMakeRect(0, 0, DESK_W, h))
        self.view.farm = self.farm
        if watered is not None:
            self.view.watered = bool(watered)
        if caption is not None and caption != self.view.caption:
            self.view.caption = caption
        self.view.setNeedsDisplay_(True)

    def pop(self, harvested, now):
        """收获的那一下：每个收获的格子冒出作物图标。"""
        if self.view is not None:
            self.view.pops = [(i, item, now) for i, item in harvested]
            self.view.now = now
            self.view.setNeedsDisplay_(True)

    def update(self, now):
        v = self.view
        if v is not None and v.pops and self.visible:
            v.now = now
            if all(now - start > POP_SECONDS for _, _, start in v.pops):
                v.pops = []
            v.setNeedsDisplay_(True)

    def set_visible(self, show):
        if show:
            if self.window is None:
                self._create()
                self.refresh()
            if not self.window.isVisible():
                self.window.orderFrontRegardless()
        elif self.window is not None and self.window.isVisible():
            self.window.orderOut_(None)

    @property
    def visible(self):
        return self.window is not None and self.window.isVisible()
