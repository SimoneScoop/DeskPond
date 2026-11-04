# -*- coding: utf-8 -*-
"""Windows 版星露谷风格对话框：原版说明框 + 原版箭头 + 原版按钮框，代替 QMessageBox / QDialog。

内容和输入逻辑在 ui/dialog_model（和 Mac 版共用）。
"""
from PySide6.QtCore import Qt

from ..ui import dialog_model as D
from . import qtdraw as C
from .base import GameWindow

KEY_NAMES = {Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Up: "up", Qt.Key_Down: "down",
             Qt.Key_Tab: "tab", Qt.Key_Backtab: "tab", Qt.Key_Return: "enter", Qt.Key_Enter: "enter",
             Qt.Key_Escape: "esc", Qt.Key_Backspace: "backspace"}


class DialogWidget(GameWindow):

    def __init__(self, model, on_button):
        h, self.rects = model.layout(
            lambda text, width: C.text_height(text, C.text_attrs(12.5, C.C_TEXT), width))
        super(DialogWidget, self).__init__(D.W, h, model.title)
        self.model = model
        self.on_button = on_button
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, e):
        name = KEY_NAMES.get(e.key(), "")
        if e.key() == Qt.Key_W and e.modifiers() & Qt.ControlModifier:
            name = "esc"
        shift = bool(e.modifiers() & Qt.ShiftModifier) or e.key() == Qt.Key_Backtab
        key = self.model.key(name, e.text()[:1], shift)
        self.update()
        if key:
            self.on_button(key)

    def focusNextPrevChild(self, nxt):
        return False                  # Tab 留给对话框自己换行

    def mousePressEvent(self, e):
        p = e.position()
        if C.in_rect(p.x(), p.y(), self.close_rect):
            self.on_button(self.model.cancel_key())
            return
        super(DialogWidget, self).mousePressEvent(e)

    def on_click(self, x, y):
        from PySide6.QtGui import QGuiApplication
        shift = bool(QGuiApplication.keyboardModifiers() & Qt.ShiftModifier)
        key = self.model.click(self.rects, x, y, shift)
        self.update()
        if key:
            self.on_button(key)
            return True
        return self.model.hit(self.rects, x, y) is not None

    def paintEvent(self, e):
        m, r = self.model, self.rects
        tb = C.ui("textbox")
        arrows = (C.ui("arrow_l"), C.ui("arrow_r"))
        with C.painting(self):
            C.draw_box9(tb, 0, 0, self.width(), self.height(), scale=4)
            self.close_rect = C.draw_close(self.width() - C.CLOSE_SIZE - 14, 14)
            x, y, w, h = r["title"]
            C.draw_text(m.title, x, y, w, h, C.text_attrs(18, C.C_TEXT, True))
            if "text" in r:
                x, y, w, h = r["text"]
                C.draw_text(m.text, x, y, w, h, C.text_attrs(12.5, C.C_TEXT))
            for i, f in enumerate(m.fields):
                x, y, w, h = r["label%d" % i]
                C.draw_text("%s  %d–%d" % (f.label, f.lo, f.hi), x, y, w, h, C.text_attrs(13, C.C_TEXT))
                for name, img in (("prev", arrows[0]), ("next", arrows[1])):
                    ax, ay, aw, ah = r["%s%d" % (name, i)]
                    if img is not None:
                        C.draw(img, ax, ay, aw, ah)
                    else:
                        C.draw_text("◀" if name == "prev" else "▶", ax, ay + 4, aw, ah,
                                    C.text_attrs(18, C.C_TEXT, align="center"))
                vx, vy, vw, vh = r["value%d" % i]
                C.draw_box9(tb, vx, vy, vw, vh, scale=2, fallback_step=2)
                focused = i == m.focus
                C.draw_text(f.shown() + ("_" if focused and f.typed is not None else ""), vx, vy + 11, vw, 20,
                            C.text_attrs(15, C.C_TEXT, True, "center"))
                if focused:
                    C.fill_rect(vx + 14, vy + vh - 9, vw - 28, 2, C.C_EDGE_GOLD)
            if "hint" in r:
                x, y, w, h = r["hint"]
                C.draw_text(D.FIELD_HINT, x, y, w, h, C.text_attrs(10.5, C.C_EDGE_MID))
            primary = m.default_key()
            for label, key in m.buttons:
                bx, by, bw, bh = r["btn:" + key]
                C.draw_box9(tb, bx, by, bw, bh, scale=3, fallback_step=2)
                C.draw_text(label, bx, by + 12, bw, 22, C.text_attrs(
                    14, C.C_TEXT if key == primary else C.C_EDGE_MID, key == primary, "center"))


class GameDialog(object):
    """弹一个原版风格的对话框。点了按钮（或回车 / Esc）就关掉，回调 on_done(按钮 key, [数值…])。"""

    def __init__(self, model, on_done=None):
        self.model = model
        self.on_done = on_done
        self.view = None

    @property
    def window(self):
        return self.view

    def show(self):
        self.view = DialogWidget(self.model, self._done)
        self.view.center()
        self.view.present()
        self.view.setFocus()
        return self

    def _done(self, key):
        if self.view is not None:
            self.view.hide()
        if self.on_done:
            self.on_done(key, self.model.values())

    @property
    def visible(self):
        return self.view is not None and self.view.isVisible()
