# -*- coding: utf-8 -*-
"""番茄钟：专注 → 休息（摸鱼时间）→ 专注 …，每 4 轮一次长休息。纯逻辑，时间由调用方传入。"""

IDLE, FOCUS, BREAK, LONG_BREAK = "idle", "focus", "break", "long_break"

# update() 返回的事件
EV_FOCUS_START = "focus_start"
EV_BREAK_START = "break_start"       # 开始摸鱼
EV_BREAK_END = "break_end"           # 摸鱼结束，回去干活


class Pomodoro(object):

    def __init__(self, focus_min=25, break_min=5, long_break_min=15, rounds=4):
        self.focus = focus_min * 60.0
        self.short_break = break_min * 60.0
        self.long_break = long_break_min * 60.0
        self.rounds = rounds
        self.phase = IDLE
        self.round = 0              # 已完成的专注轮数
        self.ends_at = 0.0
        self.paused_left = None     # 暂停时剩余秒数
        self.free_fishing = False   # 「现在就摸一会儿」：不算进番茄钟的临时摸鱼

    # MARK: 状态

    @property
    def paused(self):
        return self.paused_left is not None

    @property
    def fishing(self):
        return self.phase in (BREAK, LONG_BREAK)

    def remaining(self, now):
        if self.phase == IDLE:
            return 0.0
        if self.paused:
            return self.paused_left
        return max(0.0, self.ends_at - now)

    def menu_title(self, now):
        if self.phase == IDLE:
            return "🎣"
        secs = int(self.remaining(now) + 0.999)
        mm, ss = divmod(secs, 60)
        icon = "⏸" if self.paused else ("🍅" if self.phase == FOCUS else "🐟")
        return "%s %02d:%02d" % (icon, mm, ss)

    # MARK: 操作

    def start_focus(self, now):
        self.phase = FOCUS
        self.ends_at = now + self.focus
        self.paused_left = None
        self.free_fishing = False
        return EV_FOCUS_START

    def start_break(self, now, minutes=None, free=False):
        """进入摸鱼时间。free=True 表示临时摸鱼，结束后回到空闲而不是下一轮专注。"""
        long_ = (not free) and self.round > 0 and self.round % self.rounds == 0
        self.phase = LONG_BREAK if long_ else BREAK
        dur = minutes * 60.0 if minutes else (self.long_break if long_ else self.short_break)
        self.ends_at = now + dur
        self.paused_left = None
        self.free_fishing = free
        return EV_BREAK_START

    def stop(self):
        was_fishing = self.fishing
        self.phase = IDLE
        self.paused_left = None
        self.free_fishing = False
        return EV_BREAK_END if was_fishing else None

    def pause(self, now):
        if self.phase != IDLE and not self.paused:
            self.paused_left = self.remaining(now)

    def resume(self, now):
        if self.paused:
            self.ends_at = now + self.paused_left
            self.paused_left = None

    # MARK: 推进

    def update(self, now):
        """到点就切阶段，返回事件列表。"""
        if self.phase == IDLE or self.paused or now < self.ends_at:
            return []
        if self.phase == FOCUS:
            self.round += 1
            return [self.start_break(now)]
        # 休息结束
        if self.free_fishing:
            self.stop()
            return [EV_BREAK_END]
        self.start_focus(now)
        return [EV_BREAK_END, EV_FOCUS_START]
