# -*- coding: utf-8 -*-
"""钓鱼竖条（小游戏界面）和钓完的结果提示。"""
import math

import objc
from Cocoa import NSMakeRect, NSView

from .. import progression
from ..gamecontent import fish_icon_path, junk_icon_path, ui_path
from . import common as C
from . import layout as L

TRACK_BLUE = (150, 190, 240)
BAR_GREEN = (120, 220, 40)
FISH_FALLBACK = (240, 150, 60)


class PanelView(NSView):
    """竖条框 + 绿条 + 小鱼 + 右侧进度。按住鼠标由 app 轮询，这里只负责画。"""

    def initWithFrame_(self, frame):
        self = objc.super(PanelView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.game = None
        self.scale = 3
        self.now = 0.0
        self.panel = C.image(ui_path("panel"))
        self.bar_top = C.image(ui_path("bar_top"))
        self.bar_mid = C.image(ui_path("bar_mid"))
        self.bar_bot = C.image(ui_path("bar_bot"))
        self.fish = C.image(ui_path("fish"))
        self.chest = C.image(ui_path("chest"))
        return self

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        pass        # 按住与否由 NSEvent.pressedMouseButtons() 统一判断

    def drawRect_(self, rect):
        g = self.game
        s = self.scale
        C.pixel_mode()
        if self.panel is not None:
            C.draw(self.panel, 0, 0, L.PANEL_W * s, L.PANEL_H * s)
        else:
            C.stardew_box(NSMakeRect(8 * s, 0, 30 * s, L.PANEL_H * s), step=s)
            C.fill_rect(L.TRACK_X * s, 3 * s, L.TRACK_W * s, 139 * s, TRACK_BLUE)
        if g is None:
            return
        t = self.now
        # 绿条
        x, y, w, h = L.bar_rect(g, s)
        alpha = L.bar_alpha(g.fish_in_bar(), t)
        if self.bar_mid is not None:
            cap = 2 * s
            C.draw(self.bar_top, x, y, w, cap, alpha)
            C.draw(self.bar_mid, x, y + cap, w, h - cap * 2, alpha)
            C.draw(self.bar_bot, x, y + h - cap, w, cap, alpha)
        else:
            C.fill_rect(x, y, w, h, BAR_GREEN, alpha)
        # 小鱼：在绿条里时轻轻抖
        shake = math.sin(t * 40) * 0.5 if g.fish_in_bar() else 0.0
        fx, fy, fw, fh = L.fish_rect(g, s, shake)
        if self.fish is not None:
            C.draw(self.fish, fx, fy, fw, fh)
        else:
            C.fill_oval(fx, fy, fw, fh, FISH_FALLBACK)
        # 宝箱：罩住一会儿就拿到，下面一条小进度
        if g.treasure_visible:
            cx, cy, cw, ch = L.treasure_rect(g, s)
            if self.chest is not None:
                C.draw(self.chest, cx, cy, cw, ch)
            else:
                C.fill_rect(cx, cy + ch * 0.35, cw, ch * 0.65, (150, 90, 40))
                C.fill_rect(cx, cy, cw, ch * 0.4, (190, 120, 50))
                C.fill_rect(cx + cw * 0.4, cy + ch * 0.3, cw * 0.2, ch * 0.2, (250, 210, 60))
            px, py, pw, ph = L.treasure_progress_rect(g, s)
            if pw > 0:
                C.fill_rect(px, py, pw, ph, (250, 200, 60))
        # 右侧进度：红 → 绿
        px, py, pw, ph = L.progress_rect(g.progress, s)
        if ph > 0:
            C.fill_rect(px, py, pw, ph, L.progress_color(g.progress))


class PanelWindow(object):

    def __init__(self):
        self.window = None
        self.view = None
        self.hide_at = None

    def finish(self, now, hold):
        """小游戏结束：进度条停在最后的样子再留 hold 秒（钓到时能看到进度条走满），然后收起。"""
        if hold <= 0:
            self.hide()
        else:
            self.hide_at = now + hold

    def show(self, game, cast_x, screen_frame, water_top_y, scale):
        self.hide_at = None
        w, h = L.PANEL_W * scale, L.PANEL_H * scale
        x = screen_frame.origin.x + L.panel_origin(cast_x, screen_frame.size.width, scale)
        y = water_top_y + 18
        rect = NSMakeRect(x, y, w, h)
        if self.window is None:
            self.window = C.overlay_window(rect, click_through=False)
            self.view = PanelView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
            self.window.setContentView_(self.view)
        else:
            self.window.setFrame_display_(rect, False)
            self.view.setFrame_(NSMakeRect(0, 0, w, h))
        self.view.scale = scale
        self.view.game = game
        self.window.orderFrontRegardless()

    def hide(self):
        self.hide_at = None
        if self.window is not None:
            self.window.orderOut_(None)
            self.view.game = None

    def update(self, now):
        if self.hide_at is not None and now >= self.hide_at:
            self.hide()
        if self.window is not None and self.window.isVisible():
            self.view.now = now
            self.view.setNeedsDisplay_(True)


# MARK: 结果提示

TOAST_W, TOAST_H = 320, 128


class ToastView(NSView):

    def initWithFrame_(self, frame):
        self = objc.super(ToastView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.result = None
        self.message = None
        self.items = {}         # 物品 id -> Junk（宝箱内容的中文名）
        return self

    def isFlipped(self):
        return True

    def drawRect_(self, rect):
        C.pixel_mode()
        b = self.bounds()
        C.draw_box9(C.image(ui_path("textbox")), 0, 0, b.size.width, b.size.height, scale=3)
        r = self.result
        if r is None:
            if self.message:
                C.draw_text(self.message, 22, 20, b.size.width - 44, b.size.height - 30,
                            C.text_attrs(15, C.C_TEXT, bold=True))
            return
        if r.junk:
            C.draw(C.image(junk_icon_path(r.fish.id)), 20, 20, 64, 64)
            C.draw_text(r.fish.display_name, 100, 22, 190, 24, C.text_attrs(18, C.C_TEXT, bold=True))
            C.draw_text("钓上来一个杂物……", 100, 50, 190, 20, C.text_attrs(12.5, C.C_TEXT))
            xp = "+%d 经验" % r.xp + ("  ⬆ 钓鱼等级 %d！" % r.level_up if r.level_up else "")
            C.draw_text(xp, 100, 70, 210, 20, C.text_attrs(12, C.C_EDGE_MID))
            C.draw_text("点水面再来一竿", 100, 90, 190, 20, C.text_attrs(12, C.C_EDGE_MID))
            return
        if not r.caught:
            icon = C.image(fish_icon_path(r.fish.id, shadow=True))
            C.draw(icon, 20, 20, 64, 64)
            C.draw_text("鱼跑掉了……", 100, 26, 190, 24, C.text_attrs(17, C.C_TEXT, bold=True))
            C.draw_text("点水面再来一竿", 100, 56, 190, 20, C.text_attrs(12.5, C.C_TEXT))
            return
        C.draw(C.image(fish_icon_path(r.fish.id)), 20, 20, 64, 64)
        if r.quality:
            star = C.image(ui_path("star_%d" % r.quality))     # 原版品质星
            if star is not None:
                C.draw(star, 14, 62, 24, 24)
            else:
                C.fill_star(26, 74, 9, progression.QUALITY_COLORS[r.quality])
        name_attrs = C.text_attrs(18, C.C_TEXT, bold=True)
        C.draw_text(r.fish.display_name, 100, 14, 210, 24, name_attrs)
        line = "%d 英寸（约 %d 厘米）" % (r.size, round(r.size * 2.54))
        if r.quality:
            line += " · %s" % progression.QUALITY_NAMES[r.quality]
        C.draw_text(line, 100, 41, 210, 20, C.text_attrs(12.5, C.C_TEXT))
        tags = []
        if r.is_new:
            tags.append("✨ 新鱼种")
        if r.is_record:
            tags.append("🏆 破纪录")
        if r.perfect:
            tags.append("完美！")
        if tags:
            C.draw_text("  ".join(tags), 100, 61, 210, 20,
                        C.text_attrs(12.5, C.C_EDGE_GOLD, bold=True))
        xp = "+%d 经验 · +%dg" % (r.xp, r.gold)
        if r.level_up:
            xp += "  ⬆ 钓鱼等级 %d！" % r.level_up
        C.draw_text(xp, 100, 81, 210, 18, C.text_attrs(12, C.C_EDGE_MID, bold=bool(r.level_up)))
        if r.treasure:
            names = "、".join("%s ×%d" % (self._item_name(i), n) for i, n in r.treasure)
            C.draw_text("🎁 宝箱：" + names, 20, 100, TOAST_W - 40, 18, C.text_attrs(12, C.C_TEXT))

    @objc.python_method
    def _item_name(self, item_id):
        it = self.items.get(item_id)
        return it.display_name if it is not None else item_id


class Toast(object):

    def __init__(self, items=None):
        self.window = None
        self.view = None
        self.items = items or {}

    def _show(self, cast_x, screen_frame, water_top_y):
        x = screen_frame.origin.x + cast_x * screen_frame.size.width - TOAST_W / 2.0
        x = max(screen_frame.origin.x + 12,
                min(screen_frame.origin.x + screen_frame.size.width - TOAST_W - 12, x))
        rect = NSMakeRect(x, water_top_y + 24, TOAST_W, TOAST_H)
        if self.window is None:
            self.window = C.overlay_window(rect, click_through=True)
            self.view = ToastView.alloc().initWithFrame_(NSMakeRect(0, 0, TOAST_W, TOAST_H))
            self.view.items = self.items
            self.window.setContentView_(self.view)
        else:
            self.window.setFrame_display_(rect, False)
        self.window.orderFrontRegardless()
        self.view.setNeedsDisplay_(True)

    def show_result(self, result, cast_x, screen_frame, water_top_y):
        self._show(cast_x, screen_frame, water_top_y)
        self.view.result = result
        self.view.message = None

    def show_message(self, text, screen_frame, water_top_y):
        self._show(0.5, screen_frame, water_top_y)
        self.view.result = None
        self.view.message = text

    def hide(self):
        if self.window is not None and self.window.isVisible():
            self.window.orderOut_(None)
