# -*- coding: utf-8 -*-
"""Mac 版星露谷风格对话框：原版说明框 + 原版箭头 + 原版按钮框，代替系统的 NSAlert。

内容和输入逻辑在 dialog_model（和 Windows 版共用）。
"""
import objc
from Cocoa import NSApplication, NSMakeRect, NSView

from ..gamecontent import ui_path
from . import common as C
from . import dialog_model as D

KEY_NAMES = {123: "left", 124: "right", 125: "down", 126: "up", 48: "tab", 36: "enter",
             76: "enter", 53: "esc", 51: "backspace"}
SHIFT = 1 << 17


class DialogView(NSView):

    def initWithFrame_(self, frame):
        self = objc.super(DialogView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.model = None
        self.rects = {}
        self.on_button = None
        self.close_rect = None
        self.textbox = C.image(ui_path("textbox"))
        self.arrows = (C.image(ui_path("arrow_l")), C.image(ui_path("arrow_r")))
        return self

    def isFlipped(self):
        return True

    def acceptsFirstResponder(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def keyDown_(self, event):
        name = KEY_NAMES.get(event.keyCode(), "")
        if C.is_close_key(event) and name != "esc":
            name = "esc"
        chars = event.characters() or ""
        key = self.model.key(name, chars[:1], bool(event.modifierFlags() & SHIFT))
        self.setNeedsDisplay_(True)
        if key and self.on_button:
            self.on_button(key)

    def mouseDown_(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        if C.in_rect(p, self.close_rect):
            if self.on_button:
                self.on_button(self.model.cancel_key())
            return
        key = self.model.click(self.rects, p.x, p.y, bool(event.modifierFlags() & SHIFT))
        self.setNeedsDisplay_(True)
        if key:
            if self.on_button:
                self.on_button(key)
            return
        if self.model.hit(self.rects, p.x, p.y) is None:
            C.drag_window(self, event)

    def drawRect_(self, rect):
        C.pixel_mode()
        b = self.bounds()
        m = self.model
        C.draw_box9(self.textbox, 0, 0, b.size.width, b.size.height, scale=4)
        self.close_rect = C.draw_close(b.size.width - C.CLOSE_SIZE - 14, 14)
        r = self.rects
        x, y, w, h = r["title"]
        C.draw_text(m.title, x, y, w, h, C.text_attrs(18, C.C_TEXT, bold=True))
        if "text" in r:
            x, y, w, h = r["text"]
            C.draw_text(m.text, x, y, w, h, C.text_attrs(12.5, C.C_TEXT))
        for i, f in enumerate(m.fields):
            x, y, w, h = r["label%d" % i]
            C.draw_text("%s  %d–%d" % (f.label, f.lo, f.hi), x, y, w, h, C.text_attrs(13, C.C_TEXT))
            for name, img in (("prev", self.arrows[0]), ("next", self.arrows[1])):
                ax, ay, aw, ah = r["%s%d" % (name, i)]
                if img is not None:
                    C.draw(img, ax, ay, aw, ah)
                else:
                    C.draw_text("◀" if name == "prev" else "▶", ax, ay + 4, aw, ah,
                                C.text_attrs(18, C.C_TEXT, align="center"))
            vx, vy, vw, vh = r["value%d" % i]
            C.draw_box9(self.textbox, vx, vy, vw, vh, scale=2, fallback_step=2)
            focused = i == m.focus
            C.draw_text(f.shown() + ("_" if focused and f.typed is not None else ""), vx, vy + 11, vw, 20,
                        C.text_attrs(15, C.C_TEXT, bold=True, align="center"))
            if focused:
                C.fill_rect(vx + 14, vy + vh - 9, vw - 28, 2, C.C_EDGE_GOLD)
        if "hint" in r:
            x, y, w, h = r["hint"]
            C.draw_text(D.FIELD_HINT, x, y, w, h, C.text_attrs(10.5, C.C_EDGE_MID))
        primary = m.default_key()
        for label, key in m.buttons:
            bx, by, bw, bh = r["btn:" + key]
            C.draw_box9(self.textbox, bx, by, bw, bh, scale=3, fallback_step=2)
            # 字要待在框的内边里（边框 18 像素宽），放不下就缩小字号
            C.draw_fit(label, bx + 20, by + 12, bw - 40, 14,
                       C.C_TEXT if key == primary else C.C_EDGE_MID, key == primary, "center")


class GameDialog(object):
    """弹一个原版风格的对话框。点了按钮（或回车 / Esc）就关掉，回调 on_done(按钮 key, [数值…])。"""

    def __init__(self, model, on_done=None):
        self.model = model
        self.on_done = on_done
        self.window = None
        self.view = None

    def show(self):
        h, rects = self.model.layout(
            lambda text, width: C.text_height(text, C.text_attrs(12.5, C.C_TEXT), width))
        win = C.game_window(D.W + 24, h + 24, self.model.title)
        self.view = DialogView.alloc().initWithFrame_(NSMakeRect(12, 6, D.W, h))
        self.view.model = self.model
        self.view.rects = rects
        self.view.on_button = self._done
        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, D.W + 24, h + 24))
        content.addSubview_(self.view)
        win.setContentView_(content)
        win.center()
        self.window = win
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        win.makeKeyAndOrderFront_(None)
        win.makeFirstResponder_(self.view)
        return self

    def _done(self, key):
        if self.window is not None:
            self.window.orderOut_(None)
        if self.on_done:
            self.on_done(key, self.model.values())

    @property
    def visible(self):
        return self.window is not None and self.window.isVisible()
