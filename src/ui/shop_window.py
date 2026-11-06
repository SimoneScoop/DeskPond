# -*- coding: utf-8 -*-
"""钓具店：照原版威利钓具店的升级路线买鱼竿、鱼饵、浮漂配件。金币来自卖鱼和作物。"""
import objc
from Cocoa import NSApplication, NSMakeRect, NSView

from .. import farm as farmlib
from .. import fishdata
from .. import gear as gearlib
from ..gamecontent import junk_icon_path, ui_path
from . import common as C
from .shop_model import (EXPAND_DESC, EXPAND_NAME, PAGES, SEED_HINT, TAB_H, TAB_W, WINTER_NOTE,
                         expand_button, seed_desc, title as page_title)

W = 600
ROW_H = 56
HEAD_H = 92
ITEMS = [("rod", "bamboo"), ("rod", "fiberglass"), ("rod", "iridium"), ("bait", "bait")] + \
        [("tackle", k) for k in ("686", "694", "695", "693")]
H = HEAD_H + ROW_H * len(ITEMS) + 30
BTN_W, BTN_H = 132, 34

ROD_DESC = {"bamboo": "最初的鱼竿。不能挂鱼饵。",
            "fiberglass": "能挂鱼饵：等鱼咬钩的时间减半。",
            "iridium": "能挂鱼饵，还能装 1 个浮漂配件。"}
LABEL = {"buy": "买", "poor": "钱不够", "locked": "", "owned": "装上", "equipped": "正在用"}

class ShopView(NSView):

    def initWithFrame_(self, frame):
        self = objc.super(ShopView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.collection = None
        self.name_of = lambda i: str(i)
        self.on_change = None
        self.flash = ""
        self.page = "gear"
        self.season = fishdata.season_of
        self.hits = []
        self.close_rect = None
        self.textbox = C.image(ui_path("textbox"))
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

    @objc.python_method
    def gear(self):
        return gearlib.Gear(self.collection.gear)

    def mouseDown_(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        if C.in_rect(p, self.close_rect):
            C.close_window(self)
            return
        for (kind, key), (x, y, w, h) in self.hits:
            if x <= p.x <= x + w and y <= p.y <= y + h:
                self._act(kind, key)
                self.setNeedsDisplay_(True)
                return
        C.drag_window(self, event)

    @objc.python_method
    def _act(self, kind, key):
        col = self.collection
        if kind == "page":
            self.page, self.flash = key, ""
            return
        if kind == "expand":
            if farmlib.expand(col):
                self.flash = "农田扩建好了：现在有 6 块地"
                if self.on_change:
                    self.on_change()
            return
        if kind == "seed":
            if farmlib.buy_seed(col, key):
                self.flash = "买好了：%s（手上 %d 包）" % (self.name_of(key), col.count(key))
                if self.on_change:
                    self.on_change()
            return
        g = self.gear()
        state, _ = g.shop_state(key, col.level, col.gold)
        if state == "buy":
            g.buy(key, col)
            self.flash = "买好了：%s" % self._name(kind, key)
        elif state == "owned":
            if kind == "rod":
                g.equip_rod(key)
            else:
                g.equip_tackle(key)
            col.save()
            self.flash = "换上了：%s" % self._name(kind, key)
        elif state == "equipped" and kind == "tackle":
            g.equip_tackle(key)
            col.save()
            self.flash = "卸下了：%s" % self._name(kind, key)
        else:
            return
        if self.on_change:
            self.on_change()

    @objc.python_method
    def _name(self, kind, key):
        if kind == "rod":
            return gearlib.rod_name(key)
        if kind == "bait":
            return self.name_of("685")
        return self.name_of(key)

    def drawRect_(self, rect):
        C.pixel_mode()
        b = self.bounds()
        C.draw_box9(self.textbox, 0, 0, b.size.width, b.size.height, scale=4)
        col = self.collection
        if col is None:
            return
        g = self.gear()
        self.hits = []
        C.draw_text(page_title(self.page), 32, 24, 260, 26, C.text_attrs(19, C.C_TEXT, bold=True))
        C.draw_text("金币 %sg · 钓鱼等级 %d · 鱼饵 %d" % (format(col.gold, ","), col.level,
                                                    col.count("685")),
                    32, 56, W - 64, 18, C.text_attrs(12.5, C.C_TEXT))
        self.close_rect = C.draw_close(W - C.CLOSE_SIZE - 16, 16)
        for i, (key, label) in enumerate(PAGES):          # 两个标签：钓具 / 种子
            tx = W - 64 - (len(PAGES) - i) * (TAB_W + 6)
            C.draw_box9(self.textbox, tx, 18, TAB_W, TAB_H, scale=2, fallback_step=2)
            active = key == self.page
            C.draw_text(label, tx, 26, TAB_W, 18, C.text_attrs(
                13, C.C_TEXT if active else (150, 110, 90), bold=active, align="center"))
            if active:
                C.fill_rect(tx + 14, 18 + TAB_H - 7, TAB_W - 28, 2, C.C_EDGE_GOLD)
            self.hits.append((("page", key), (tx, 18, TAB_W, TAB_H)))
        if self.flash:
            C.draw_text(self.flash, W - 330, 58, 290, 18,
                        C.text_attrs(12, (40, 120, 30), bold=True, align="right"))
        y = HEAD_H
        if self.page == "seeds":
            C.fill_rect(28, y, W - 56, 1, C.C_EDGE_INNER)
            self._expand_row(y + 6)
            y += ROW_H
            seeds = farmlib.seeds_for_sale(self.season())
            if not seeds:
                C.draw_text(WINTER_NOTE, 36, y + 20, W - 72, 40,
                            C.text_attrs(13, C.C_TEXT))
            for seed in seeds:
                C.fill_rect(28, y, W - 56, 1, C.C_EDGE_INNER)
                self._seed_row(seed, y + 6)
                y += ROW_H
            C.draw_text(SEED_HINT,
                        36, H - 40, W - 72, 18, C.text_attrs(11.5, C.C_EDGE_MID))
            return
        for kind, key in ITEMS:
            C.fill_rect(28, y, W - 56, 1, C.C_EDGE_INNER)
            self._row(g, kind, key, y + 6)
            y += ROW_H

    @objc.python_method
    def _expand_row(self, y):
        C.draw(C.image(ui_path("dirt2_tm")), 38, y + 4, 36, 36)
        C.draw_text(EXPAND_NAME, 90, y + 2, 300, 20, C.text_attrs(14, C.C_TEXT, bold=True))
        C.draw_fit(EXPAND_DESC % farmlib.EXPAND_LEVEL, 90, y + 24, 340, 11.5, C.C_EDGE_MID, align=None)
        label, ok = expand_button(self.collection)
        bx = W - 36 - BTN_W
        if ok:
            C.draw_box9(self.textbox, bx, y + 4, BTN_W, BTN_H, scale=2, fallback_step=2)
            self.hits.append((("expand", "farm"), (bx, y + 4, BTN_W, BTN_H)))
        C.draw_text(label, bx, y + 12, BTN_W, 18,
                    C.text_attrs(12, C.C_TEXT if ok else (150, 110, 90), bold=True, align="center"))

    @objc.python_method
    def _seed_row(self, seed, y):
        col = self.collection
        icon = C.image(junk_icon_path(seed))
        if icon is not None:
            C.draw(icon, 36, y + 2, 40, 40)
        C.draw_text(self.name_of(seed), 90, y + 2, 300, 20, C.text_attrs(14, C.C_TEXT, bold=True))
        C.draw_fit(seed_desc(seed, col), 90, y + 24, 340, 11.5, C.C_EDGE_MID, align=None)
        price = farmlib.SEED_PRICES[seed]
        bx = W - 36 - BTN_W
        ok = col.gold >= price
        if ok:
            C.draw_box9(self.textbox, bx, y + 4, BTN_W, BTN_H, scale=2, fallback_step=2)
            self.hits.append((("seed", seed), (bx, y + 4, BTN_W, BTN_H)))
        C.draw_text("%s · %dg" % ("买一包" if ok else "钱不够", price), bx, y + 12, BTN_W, 18,
                    C.text_attrs(12, C.C_TEXT if ok else (150, 110, 90), bold=True, align="center"))

    @objc.python_method
    def _row(self, g, kind, key, y):
        col = self.collection
        if kind == "rod":
            icon, desc = C.image(ui_path("rod_" + key)), ROD_DESC[key]
        elif kind == "bait":
            icon, desc = C.image(junk_icon_path("685")), "等鱼咬钩的时间减半（抛竿时自动挂上）。"
        else:
            icon, desc = C.image(junk_icon_path(key)), gearlib.TACKLE[key][2] + "。只有铱金钓竿能装。"
        if icon is not None:
            C.draw(icon, 36, y + 2, 40, 40)
        else:
            C.draw_text("🎣", 40, y + 6, 40, 30, C.text_attrs(24, C.C_TEXT))
        C.draw_text(self._name(kind, key), 90, y + 2, 300, 20, C.text_attrs(14, C.C_TEXT, bold=True))
        C.draw_fit(desc, 90, y + 24, 340, 11.5, C.C_EDGE_MID, align=None)
        state, note = g.shop_state(key, col.level, col.gold)
        bx = W - 36 - BTN_W
        label = LABEL[state]
        if state in ("buy", "poor"):
            label = "%s · %s" % (label, note)
        elif state == "locked":
            label = note
        if state in ("buy", "owned") or (state == "equipped" and kind == "tackle"):
            C.draw_box9(self.textbox, bx, y + 4, BTN_W, BTN_H, scale=2, fallback_step=2)
            self.hits.append(((kind, key), (bx, y + 4, BTN_W, BTN_H)))
        if state == "equipped":
            label = "正在用" + ("（再点卸下）" if kind == "tackle" else "")
        color = C.C_TEXT if state in ("buy", "owned", "equipped") else (150, 110, 90)
        C.draw_fit(label, bx + 6, y + 12, BTN_W - 12, 12, color, True, "center")


class ShopWindow(object):

    def __init__(self, collection, name_of, on_change=None):
        self.collection = collection
        self.name_of = name_of
        self.on_change = on_change
        self.window = None
        self.view = None

    def _create(self):
        win = C.game_window(W + 24, H + 36, "钓具店")
        self.view = ShopView.alloc().initWithFrame_(NSMakeRect(12, 6, W, H))
        self.view.collection = self.collection
        self.view.name_of = self.name_of
        self.view.on_change = self.on_change
        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, W + 24, H + 36))
        content.addSubview_(self.view)
        win.setContentView_(content)
        win.center()
        self.window = win

    def show(self, page=None):
        if self.window is None:
            self._create()
        self.view.flash = ""
        if page:
            self.view.page = page
        self.view.setNeedsDisplay_(True)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
        self.window.makeFirstResponder_(self.view)

    def refresh(self):
        if self.view is not None:
            self.view.setNeedsDisplay_(True)
