# -*- coding: utf-8 -*-
"""摸鱼图鉴：照原版「收藏」菜单的样子做。

    - 原版菜单大框，左边一列标签：鱼 / 杂物与宝物 / 作物 / 浮漂
    - 格子里只有图标，没有格子框；没收集到的是深色剪影
    - 鼠标停在图标上弹出原版的说明框：名字、游戏里的描述、钓到几条、最大多大
    - 一页放不下就翻页（左右箭头）
鱼的那一页另有筛选：现在能钓 / 全部 / 本季 / 当前钓点；浮漂那一页点一下就换上。
"""
import objc
from Cocoa import NSApplication, NSMakeRect, NSTrackingArea, NSView

from .. import farm as farmlib
from .. import fishdata, progression, world
from ..gamecontent import fish_icon_path, junk_icon_path, ui_path
from . import common as C

WIN_W, WIN_H = 830, 556
BOX_X, BOX_Y, BOX_W, BOX_H = 88, 10, 732, 536
TAB_X, TAB_Y0, TAB_SIZE, TAB_STEP = 26, 54, 64, 74
COLS, ROWS, CELL, ICON = 10, 5, 64, 48
GRID_X, GRID_Y = BOX_X + 46, 148
ARROW_W, ARROW_H = 48, 44
ARROW_Y = BOX_Y + BOX_H - 58
FILTER_Y, FILTER_H = 98, 32
TIP_W = 300

TRACKING = 0x01 | 0x02 | 0x80 | 0x200          # 进出 + 移动 + 一直生效 + 跟随可见区域

from .album_model import (FISH_FILTERS, MILESTONES, PAGES, Album, Bobber,  # noqa: E402,F401
                          milestone_names)


class CollectionView(NSView):

    def initWithFrame_(self, frame):
        self = objc.super(CollectionView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.album = None
        self.entries = []
        self.now_ids = set()
        self.page_no = 0
        self.hover = None
        self.selected = None
        self.hits = []             # [(kind, value, (x, y, w, h))]
        self.close_rect = None
        self.menubox = C.image(ui_path("menubox"))
        self.textbox = C.image(ui_path("textbox"))
        self.tab_img = C.image(ui_path("tab"))
        self.arrows = (C.image(ui_path("arrow_l")), C.image(ui_path("arrow_r")))
        self.stars = [None] + [C.image(ui_path("star_%d" % q)) for q in (1, 2, 3)]
        area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            frame, TRACKING, self, None)
        self.addTrackingArea_(area)
        return self

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def acceptsFirstResponder(self):
        return True

    def keyDown_(self, event):
        if C.is_close_key(event):
            C.close_window(self)

    # MARK: 交互

    @objc.python_method
    def _hit(self, p):
        for kind, value, (x, y, w, h) in reversed(self.hits):
            if x <= p.x <= x + w and y <= p.y <= y + h:
                return kind, value
        return None, None

    def mouseMoved_(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        kind, value = self._hit(p)
        hover = value if kind == "cell" else None
        if hover is not self.hover:
            self.hover = hover
            self.setNeedsDisplay_(True)

    def mouseExited_(self, event):
        if self.hover is not None:
            self.hover = None
            self.setNeedsDisplay_(True)

    def mouseDown_(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        if C.in_rect(p, self.close_rect):
            C.close_window(self)
            return
        kind, value = self._hit(p)
        a = self.album
        if kind == "page":
            a.page, self.page_no, self.selected = value, 0, None
        elif kind == "filter":
            a.filter, self.page_no, self.selected = value, 0, None
        elif kind == "arrow":
            self.page_no = max(0, min(self.pages() - 1, self.page_no + value))
        elif kind == "random" and a.on_bobber:
            a.on_bobber("random")
        elif kind == "cell":
            self.selected = value
            if isinstance(value, Bobber) and a.got(value) and a.on_bobber:
                a.on_bobber(value.index)
        else:
            C.drag_window(self, event)       # 空白处按住拖动窗口
            return
        self.reload()

    @objc.python_method
    def reload(self):
        if self.album is not None:
            self.entries = self.album.entries()
            self.now_ids = self.album.available_now() if self.album.page == "fish" else set()
            self.page_no = max(0, min(self.page_no, self.pages() - 1))
        self.setNeedsDisplay_(True)

    @objc.python_method
    def pages(self):
        per = COLS * ROWS
        return max(1, (len(self.entries) + per - 1) // per)

    # MARK: 绘制

    def drawRect_(self, rect):
        C.pixel_mode()
        a = self.album
        self.hits = []
        if a is None:
            return
        self._draw_tabs(a)
        if self.menubox is not None:
            C.draw_box9(self.menubox, BOX_X, BOX_Y, BOX_W, BOX_H, scale=1)
        else:
            C.draw_box9(self.textbox, BOX_X, BOX_Y, BOX_W, BOX_H, scale=4)
        self._draw_header(a)
        self.close_rect = C.draw_close(BOX_X + BOX_W - C.CLOSE_SIZE - 14, BOX_Y + 14)
        self._draw_grid(a)
        self._draw_arrows()
        tip = self.hover or self.selected
        if tip is not None:
            self._draw_tooltip(a, tip)

    @objc.python_method
    def _draw_tabs(self, a):
        """左边一列标签：原版空白标签 + 物品图标。"""
        for i, (key, title) in enumerate(PAGES):
            active = key == a.page
            x = TAB_X + (8 if active else 0)
            y = TAB_Y0 + i * TAB_STEP
            if self.tab_img is not None:
                C.draw(self.tab_img, x, y, TAB_SIZE, TAB_SIZE)
            else:
                C.stardew_box(NSMakeRect(x, y, TAB_SIZE, TAB_SIZE), step=3)
            icon = self._tab_icon(key)
            if icon is not None:
                C.draw(icon, x + 14, y + 14, 36, 36)
            self.hits.append(("page", key, (x, y, TAB_SIZE, TAB_SIZE)))

    @objc.python_method
    def _tab_icon(self, key):
        if key == "fish":
            return C.image(fish_icon_path("145"))     # 太阳鱼（原版那张鱼标签带红叉，不用）
        if key == "items":
            return C.image(junk_icon_path("168"))
        if key == "crops":
            return C.image(junk_icon_path("24"))
        return C.image(ui_path("bobber_icon_0"))

    @objc.python_method
    def _draw_header(self, a):
        col = a.collection
        x0, w = BOX_X + 44, BOX_W - 88
        big = C.text_attrs(19, C.C_TEXT, bold=True)
        small = C.text_attrs(12, C.C_TEXT)
        title = dict(PAGES)[a.page]
        if a.page == "fish":
            title = "鱼  %d / %d" % (a.caught(), a.total)
        elif a.page == "bobbers":
            title = "浮漂  %d / %d" % (a.bobber_count(), a.bobber_total)
        C.draw_text(title, x0, 40, 300, 26, big)

        if a.page == "fish":
            lv, have, need = progression.level_progress(col.xp)
            week = col.week_stats()
            info = "钓鱼等级 %d" % lv
            C.draw_text(info, x0 + 252, 46, 90, 18, C.text_attrs(12.5, C.C_TEXT, bold=True))
            bx, by, bw, bh = x0 + 340, 50, 120, 10
            C.fill_rect(bx, by, bw, bh, C.C_EDGE_MID)
            C.fill_rect(bx + 1, by + 1, (bw - 2) * (float(have) / need if need else 1), bh - 2,
                        (120, 200, 60))
            C.draw_text("本周 %d 条 · %sg" % (week["caught"], format(col.gold, ",")),
                        bx + bw + 10, 46, 150, 18, small)
            titles = milestone_names(a.caught(), a.total)
            if titles:
                C.draw_text("🏆 " + "、".join(titles), x0 + 252, 66, 300, 18, small)
            fx = x0
            for key, label in FISH_FILTERS:
                fw = C.text_size(label, C.text_attrs(12.5, C.C_TEXT, bold=True)).width + 34
                self._button(fx, FILTER_Y, fw, FILTER_H, label, key == a.filter)
                self.hits.append(("filter", key, (fx, FILTER_Y, fw, FILTER_H)))
                fx += fw + 8
        elif a.page == "bobbers":
            C.draw_text("和钓鱼店的浮漂机一样：每多钓到 2 种不同的鱼解锁一种。点一下换上。",
                        x0, 70, w, 18, small)
            rw = 160
            self._button(x0, FILTER_Y, rw, FILTER_H, "随机（每次抛竿换一个）",
                         a.bobber_pref() == "random")
            self.hits.append(("random", None, (x0, FILTER_Y, rw, FILTER_H)))
        elif a.page == "crops":
            C.draw_text("每完成一个番茄，农田过一天；成熟自动收获，换 1 个鱼饵。", x0, 70, w, 18, small)
        else:
            C.draw_text("钓上来的杂物、宝箱里开出的东西。", x0, 70, w, 18, small)

    @objc.python_method
    def _button(self, x, y, w, h, label, active):
        C.draw_box9(self.textbox, x, y, w, h, scale=2, fallback_step=2)
        if active:
            C.fill_rect(x + 5, y + 5, w - 10, h - 10, C.C_EDGE_INNER, 0.5)
        attrs = C.text_attrs(12.5, C.C_TEXT, bold=True, align="center")
        C.draw_text(label, x, y + (h - 17) / 2.0, w, 18, attrs)

    @objc.python_method
    def _draw_grid(self, a):
        per = COLS * ROWS
        shown = self.entries[self.page_no * per:(self.page_no + 1) * per]
        if not shown:
            C.draw_text("这里还没有东西。换个筛选，或者换个时间、钓点再来。", GRID_X, GRID_Y + 8,
                        COLS * CELL, 20, C.text_attrs(12.5, C.C_TEXT))
        pref = a.bobber_pref()
        for i, e in enumerate(shown):
            x, y = GRID_X + (i % COLS) * CELL, GRID_Y + (i // COLS) * CELL
            off = (CELL - ICON) / 2.0
            got = a.got(e)
            if e is self.hover or e is self.selected:
                C.fill_rect(x + 4, y + 4, CELL - 8, CELL - 8, C.C_EDGE_INNER, 0.35)
            if isinstance(e, Bobber):
                name = "bobber_icon_%d%s" % (e.index, "" if got else "_s")
                C.draw(C.image(ui_path(name)), x + off, y + off, ICON, ICON)
                if got and str(pref) == str(e.index):
                    C.draw_box9(self.textbox, x + 2, y + 2, CELL - 4, CELL - 4, scale=2,
                                fallback_step=2)
                    C.draw(C.image(ui_path(name)), x + off, y + off, ICON, ICON)
            elif isinstance(e, fishdata.Junk):
                C.draw(C.image(junk_icon_path(e.id, shadow=not got)), x + off, y + off, ICON, ICON)
            else:
                entry = a.collection.fish.get(e.id)
                C.draw(C.image(fish_icon_path(e.id, shadow=entry is None)), x + off, y + off,
                       ICON, ICON)
                q = (entry or {}).get("best_quality", 0)
                if q:
                    star = self.stars[q]
                    if star is not None:
                        C.draw(star, x + off - 2, y + off + ICON - 18, 20, 20)
                    else:
                        C.fill_star(x + off + 8, y + off + ICON - 8, 7, progression.QUALITY_COLORS[q])
                if e.id in self.now_ids and a.filter != "now":
                    C.fill_oval(x + CELL - 14, y + 8, 8, 8, (80, 200, 90))
            self.hits.append(("cell", e, (x, y, CELL, CELL)))

    @objc.python_method
    def _draw_arrows(self):
        n = self.pages()
        if n <= 1:
            return
        left, right = self.arrows
        lx, rx = BOX_X + 34, BOX_X + BOX_W - 34 - ARROW_W
        if self.page_no > 0:
            self._arrow(left, lx, -1)
        if self.page_no < n - 1:
            self._arrow(right, rx, 1)
        C.draw_text("%d / %d" % (self.page_no + 1, n), BOX_X, ARROW_Y + 12, BOX_W, 18,
                    C.text_attrs(12.5, C.C_TEXT, bold=True, align="center"))

    @objc.python_method
    def _arrow(self, img, x, step):
        if img is not None:
            C.draw(img, x, ARROW_Y, ARROW_W, ARROW_H)
        else:
            C.draw_text("◀" if step < 0 else "▶", x, ARROW_Y, ARROW_W, ARROW_H,
                        C.text_attrs(26, C.C_EDGE_GOLD, bold=True))
        self.hits.append(("arrow", step, (x, ARROW_Y, ARROW_W, ARROW_H)))

    @objc.python_method
    def _tip_lines(self, a, e):
        """说明框里的内容：(名字, 描述, [其余几行])。"""
        col = a.collection
        if isinstance(e, Bobber):
            if a.got(e):
                state = "正在用" if str(a.bobber_pref()) == str(e.index) else "点一下换上"
                return "浮漂 · 样式 %d" % (e.index + 1), None, [state]
            need = progression.species_for_style(e.index) - col.caught_species()
            return "？？？", None, ["再钓到 %d 种新鱼解锁" % max(1, need)]
        if isinstance(e, fishdata.Junk):
            if not a.got(e):
                if e.id in farmlib.CROP_NAMES:
                    return "？？？", None, ["还没种出来过"]
                return "？？？", None, ["还没见过"]
            if e.id in col.crops:
                seed = [s for s, v in farmlib.CROPS.items() if v[1] == e.id]
                days = sum(farmlib.CROPS[seed[0]][3]) if seed else 0
                return e.display_name, None, ["种出来 %d 个" % col.crops[e.id],
                                              "从播种到成熟要 %d 个番茄" % days]
            if e.id in col.items:
                return e.display_name, None, ["钓上来 %d 个" % col.items[e.id]]
            return e.display_name, None, ["宝箱开出 %d 个 · 手上还有 %d 个" % (
                col.treasure.get(e.id, 0), col.count(e.id))]
        entry = col.fish.get(e.id)
        spots = [world.spot_name(k) for k in world.spots_of(e.id)]
        hint = fishdata.hint(e, spots)
        if entry is None:
            return "？？？", None, [hint]
        lines = ["钓到 %d 条 · 最大 %d 英寸" % (entry["count"], entry["max_size"]),
                 "最高品质：%s%s" % (progression.QUALITY_NAMES[entry.get("best_quality", 0)],
                                   " · 完美 %d 次" % entry["perfect"] if entry.get("perfect") else ""),
                 hint]
        return e.display_name, e.desc, lines

    @objc.python_method
    def _draw_tooltip(self, a, e):
        name, desc, lines = self._tip_lines(a, e)
        tw = TIP_W - 40
        big = C.text_attrs(15, C.C_TEXT, bold=True)
        body = C.text_attrs(11.5, C.C_TEXT)
        small = C.text_attrs(11.5, C.C_EDGE_MID)
        # 高度按真正排出来的字算（会自动换行），字就不会跑出框
        name_h = C.text_height(name, big, tw)
        desc_h = C.text_height(desc, body, tw) if desc else 0
        line_h = [C.text_height(line, small, tw) for line in lines]
        h = 18 + name_h + 10 + (desc_h + 12 if desc else 0) + sum(line_h) + 4 * len(lines) + 20
        cell = [r for kind, v, r in self.hits if kind == "cell" and v is e]
        if not cell:
            return
        cx, cy, _, _ = cell[0]
        x = cx + CELL + 6
        if x + TIP_W > WIN_W - 6:
            x = cx - TIP_W - 6
        y = max(6, min(WIN_H - h - 6, cy))
        C.draw_box9(self.textbox, x, y, TIP_W, h, scale=3)
        C.draw_text(name, x + 20, y + 18, tw, name_h + 4, big)
        ty = y + 18 + name_h + 10
        if desc:
            C.draw_text(desc, x + 20, ty, tw, desc_h + 4, body)
            ty += desc_h + 12
        for line, lh in zip(lines, line_h):
            C.draw_text(line, x + 20, ty, tw, lh + 4, small)
            ty += lh + 4


class CollectionWindow(object):

    def __init__(self, fish_list, collection, items=None, spot_fn=None, weather_fn=None):
        self.album = Album(fish_list, collection, items, spot_fn, weather_fn)
        self.fish = self.album.all_fish          # 菜单里显示「图鉴 x / 总数」用
        self.collection = collection
        self.window = None
        self.view = None

    def _create(self):
        win = C.game_window(WIN_W, WIN_H, "摸鱼图鉴")
        win.setAcceptsMouseMovedEvents_(True)
        self.view = CollectionView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, WIN_H))
        self.view.album = self.album
        win.setContentView_(self.view)
        win.center()
        self.window = win

    def set_page(self, page, filt=None):
        self.album.page = page
        if filt:
            self.album.filter = filt
        if self.view is not None:
            self.view.page_no, self.view.selected = 0, None
        self.refresh()

    def show(self, page=None):
        if self.window is None:
            self._create()
        if page:
            self.set_page(page)
        self.refresh()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
        self.window.makeFirstResponder_(self.view)

    def refresh(self):
        if self.view is not None:
            self.view.reload()
