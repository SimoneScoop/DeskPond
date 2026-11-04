# -*- coding: utf-8 -*-
"""星露谷风格的小对话框（自定义时长、欢迎、提示）：内容、排版和输入逻辑，Mac / Windows 共用。

没有系统输入框：数字用原版左右箭头 ◀ ▶ 加减（按住 Shift 一次 5），也可以直接打数字；
Tab / ↑↓ 换行，回车 = 第一个（主要）按钮，Esc = 取消。
"""

W = 440
PAD = 32
TITLE_Y = 28
TITLE_H = 30
ROW_H = 50
ARROW_W, ARROW_H = 36, 33          # Cursors 里的箭头 12×11，放大 3 倍
VALUE_W = 84
BTN_H = 44
BTN_GAP = 12


class Field(object):
    __slots__ = ("label", "value", "lo", "hi", "typed")

    def __init__(self, label, value, lo, hi):
        self.label, self.lo, self.hi = label, int(lo), int(hi)
        self.value = max(self.lo, min(self.hi, int(value)))
        self.typed = None            # 正在打的数字（还没确认），None = 没在打

    def shown(self):
        return self.typed if self.typed is not None else str(self.value)

    def commit(self):
        if self.typed is not None:
            try:
                self.value = max(self.lo, min(self.hi, int(self.typed)))
            except ValueError:
                pass
            self.typed = None


class Dialog(object):
    """buttons: [(文字, key)]，第一个是主要按钮（回车）；带 "cancel" key 的那个是 Esc。"""

    def __init__(self, title, text="", buttons=(("好", "ok"),), fields=()):
        self.title = title
        self.text = text
        self.buttons = list(buttons)
        self.fields = list(fields)
        self.focus = 0

    # MARK: 输入

    def step(self, i, delta):
        f = self.fields[i]
        f.commit()
        f.value = max(f.lo, min(f.hi, f.value + delta))
        self.focus = i

    def type_digit(self, d):
        if not self.fields:
            return
        f = self.fields[self.focus]
        f.typed = ((f.typed or "") + str(d))[-3:]

    def backspace(self):
        if self.fields:
            f = self.fields[self.focus]
            f.typed = (f.typed if f.typed is not None else str(f.value))[:-1]

    def move_focus(self, delta):
        if self.fields:
            self.fields[self.focus].commit()
            self.focus = (self.focus + delta) % len(self.fields)

    def values(self):
        for f in self.fields:
            f.commit()
        return [f.value for f in self.fields]

    def default_key(self):
        return self.buttons[0][1]

    def cancel_key(self):
        for _, key in self.buttons:
            if key == "cancel":
                return key
        return self.buttons[-1][1]

    # MARK: 排版

    def layout(self, text_height):
        """text_height(文字, 宽) -> 高。返回 (总高, {名字: (x, y, w, h)})。"""
        r = {"title": (PAD, TITLE_Y, W - PAD * 2 - 40, TITLE_H)}
        y = TITLE_Y + TITLE_H + 10
        if self.text:
            th = text_height(self.text, W - PAD * 2)
            r["text"] = (PAD, y, W - PAD * 2, th + 4)
            y += th + 18
        for i, _ in enumerate(self.fields):
            right = W - PAD
            r["label%d" % i] = (PAD, y + 14, W - PAD * 2 - (ARROW_W * 2 + VALUE_W + 16), 22)
            r["next%d" % i] = (right - ARROW_W, y + 8, ARROW_W, ARROW_H)
            r["value%d" % i] = (right - ARROW_W - 8 - VALUE_W, y + 4, VALUE_W, 42)
            r["prev%d" % i] = (right - ARROW_W * 2 - 16 - VALUE_W, y + 8, ARROW_W, ARROW_H)
            y += ROW_H
        if self.fields:
            r["hint"] = (PAD, y + 2, W - PAD * 2, 18)
            y += 26
        y += 8
        n = len(self.buttons)
        bw = (W - PAD * 2 - BTN_GAP * (n - 1)) / float(n)
        # 主要按钮放最右边（和 macOS / 原版菜单一样，「好」在右）
        for k, (_, key) in enumerate(reversed(self.buttons)):
            r["btn:" + key] = (PAD + k * (bw + BTN_GAP), y, bw, BTN_H)
        return y + BTN_H + 30, r

    def hit(self, rects, x, y):
        """点到了什么：("btn", key) / ("prev", i) / ("next", i) / ("value", i) / None。"""
        for name, (rx, ry, rw, rh) in rects.items():
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                if name.startswith("btn:"):
                    return "btn", name[4:]
                for kind in ("prev", "next", "value"):
                    if name.startswith(kind) and name[len(kind):].isdigit():
                        return kind, int(name[len(kind):])
        return None

    def click(self, rects, x, y, big_step=False):
        """处理一次点击，点了按钮就返回它的 key，否则 None。"""
        h = self.hit(rects, x, y)
        if h is None:
            return None
        kind, v = h
        if kind == "btn":
            return v
        if kind == "value":
            self.fields[self.focus].commit()
            self.focus = v
        else:
            self.step(v, (5 if big_step else 1) * (1 if kind == "next" else -1))
        return None

    def key(self, name, char="", shift=False):
        """键盘：name 是 left/right/up/down/tab/enter/esc/backspace，char 是打的字。返回要触发的按钮 key。"""
        if char and char.isdigit():
            self.type_digit(char)
        elif name == "backspace":
            self.backspace()
        elif name in ("left", "right") and self.fields:
            self.step(self.focus, (5 if shift else 1) * (1 if name == "right" else -1))
        elif name in ("up", "down", "tab"):
            self.move_focus(-1 if name == "up" or (name == "tab" and shift) else 1)
        elif name == "enter":
            return self.default_key()
        elif name == "esc":
            return self.cancel_key()
        return None


def durations_dialog(focus, brk, focus_range, break_range):
    return Dialog("自定义时长", "做完一轮专注，就进入摸鱼时间。",
                  buttons=[("好", "ok"), ("取消", "cancel")],
                  fields=[Field("专注（分钟）", focus, *focus_range),
                          Field("摸鱼（分钟）", brk, *break_range)])


FIELD_HINT = "点 ◀ ▶ 加减（按住 Shift 一次 5），也可以直接打数字"

WELCOME_TEXT = ("专注 %d 分钟后，屏幕底部会变成鱼塘：点水面抛竿，看到「！」就点，"
                "然后按住鼠标让绿条罩住小鱼。钓到的鱼会存进图鉴。\n\n"
                "点得越靠上水越深，越容易钓到好鱼；拖水面顶边能调高度。"
                "有人走过来就按 %s，水面立刻消失。")
# 第一个是主要按钮（回车），「稍后」是 Esc
WELCOME_BUTTONS = [("开始专注 🍅", "focus"), ("先摸一会儿 🐟", "fish"), ("稍后", "cancel")]
