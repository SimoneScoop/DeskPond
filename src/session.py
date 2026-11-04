# -*- coding: utf-8 -*-
"""一次摸鱼的流程：水面升起 → 点水抛竿 → 等咬钩 → 「！」时点击 → 小游戏 → 结果 → 再来。

纯逻辑状态机，界面只负责画和把点击传进来，所以整套流程能用假时钟测。
"""
import random

_cosmetic = random.Random()      # 浮漂样式这类纯外观的随机，不占用挑鱼的随机数序列

from . import fishdata, gear, minigame, progression, world

HIDDEN, RISING, IDLE, WAITING, BITE, PLAYING, RESULT, FALLING = (
    "hidden", "rising", "idle", "waiting", "bite", "playing", "result", "falling")

RISE_SECONDS = 1.2
FALL_SECONDS = 1.0
WAIT_RANGE = (1.5, 6.0)      # 抛竿后多久咬钩
BITE_WINDOW = 1.4            # 「！」出现后多久内要点
RESULT_SECONDS = 3.0
BAIT_WAIT = 0.5              # 挂鱼饵时等待时间乘这个数

# 事件（给界面播音效、弹提示用）
EV_CAST, EV_BITE, EV_TOO_EARLY, EV_MISSED, EV_START_GAME = (
    "cast", "bite", "too_early", "missed", "start_game")
EV_CAUGHT, EV_ESCAPED, EV_SHOWN, EV_HIDDEN = "caught", "escaped", "shown", "hidden"
EV_JUNK = "junk"             # 钓上来杂物：不进小游戏，直接出结果
EV_BAIT = "bait"             # 抛竿时自动用了一个鱼饵


class Result(object):
    __slots__ = ("fish", "caught", "size", "perfect", "is_new", "is_record", "junk",
                 "quality", "xp", "level_up", "treasure", "depth", "gold")

    def __init__(self, fish, caught, size=0, perfect=False, is_new=False, is_record=False,
                 junk=False, quality=0, xp=0, level_up=None, treasure=None, depth=0):
        self.fish, self.caught, self.size = fish, caught, size
        self.perfect, self.is_new, self.is_record = perfect, is_new, is_record
        self.junk = junk
        self.quality, self.xp, self.level_up = quality, xp, level_up
        self.treasure = treasure or []      # [(物品 id, 数量)]
        self.depth = depth
        self.gold = 0                       # 这条鱼卖了多少钱


class Session(object):

    def __init__(self, fish_list, collection=None, mode="casual", rng=None, junk=None):
        self.fish_list = fish_list
        self.junk = junk or {}    # 杂物 id -> fishdata.Junk（带中文名）
        self.spot = world.DEFAULT_SPOT
        self.weather = None       # None = 按日期取今天的虚拟天气；测试里可以直接指定
        self.depth = 3            # 这一竿的水深 1..5
        self.cast_y = 0.4         # 浮漂在水里的相对高度（0 = 水面上沿，1 = 屏幕底边）
        self.baited = False       # 这一竿挂了鱼饵（等待时间减半）
        self.bobber_pref = 0      # 选的浮漂样式（从 0 数），或 "random"：每次抛竿随机一种已解锁的
        self.bobber_count = 0     # 已解锁几种（0 = 没有原版浮漂表，用代码画）
        self.bobber = 0           # 这一竿实际用的样式
        self.collection = collection
        self.mode = mode
        self.rng = rng or random.Random()
        self.state = HIDDEN
        self.state_at = 0.0
        self.level = 0.0          # 水面高度 0..1（升起/退下动画）
        self.cast_x = 0.0         # 浮漂位置（0..1，相对屏幕宽）
        self.bite_at = 0.0
        self.fish = None
        self.game = None
        self.result = None
        self.closing = False      # 摸鱼时间到了，但正在钓的这条要钓完

    @property
    def gear(self):
        return gear.Gear(self.collection.gear if self.collection is not None else {})

    @property
    def fishing_level(self):
        return self.collection.level if self.collection is not None else 0

    # MARK: 外部调用

    def show(self, now):
        if self.state in (HIDDEN, FALLING):
            self._set(RISING, now)
            self.closing = False
            return [EV_SHOWN]
        return []

    def hide(self, now):
        """摸鱼时间到。正在溜鱼就等这条结束，其余情况直接收起。"""
        if self.state in (HIDDEN, FALLING):
            return []
        if self.state in (PLAYING, RESULT):
            self.closing = True
            return []
        self._set(FALLING, now)
        return []

    def boss_hide(self, now):
        """老板键：立刻收起，不播动画。正在溜的鱼算跑了，但不记进今天的战绩。"""
        if self.state == HIDDEN:
            return []
        self.game = None
        self.fish = None
        self.result = None
        self.closing = False
        self._set(HIDDEN, now)
        self.level = 0.0
        return [EV_HIDDEN]

    def click(self, now, x=None, depth=None, y=None):
        """点水面。x 是相对水面宽的 0..1；y 是在水里的相对高度 0..1（0 = 上沿）；
        depth 是这一竿的水深 1..5（不给就由 y 换算）。浮漂落在点的位置。"""
        if self.state == IDLE:
            self.cast_x = 0.5 if x is None else max(0.03, min(0.97, x))
            if y is not None:
                self.cast_y = max(0.0, min(1.0, y))
                if depth is None:
                    depth = world.depth_from_rel(self.cast_y)
            if depth is not None:
                self.depth = max(1, min(world.MAX_DEPTH, int(depth)))
            self.bobber = self.pick_bobber()
            wait = self.rng.uniform(*WAIT_RANGE)
            events = [EV_CAST]
            g = self.gear
            # 原版：竹竿挂不了鱼饵，要玻璃纤维钓竿以上
            self.baited = bool(self.collection is not None and gear.can_bait(g.rod)
                               and self.collection.use_item(progression.BAIT))
            if self.baited:
                events.append(EV_BAIT)
            wait *= g.wait_mult(self.baited)
            self.bite_at = now + wait
            self._set(WAITING, now)
            return events
        if self.state == WAITING:
            self._set(IDLE, now)
            return [EV_TOO_EARLY]
        if self.state == BITE:
            got = self.roll()
            if not isinstance(got, fishdata.Fish):
                return self._land_junk(now, got)
            self.fish = got
            g = self.gear
            self.game = minigame.Minigame(self.fish.difficulty, self.fish.behavior,
                                          mode=self.mode, rng=self.rng,
                                          level=self.fishing_level, bar_bonus=g.bar_bonus(),
                                          loss_mult=g.loss_mult(),
                                          keep_treasure=g.keeps_treasure())
            self._set(PLAYING, now)
            return [EV_START_GAME]
        if self.state == RESULT:
            return self._after_result(now)
        return []

    def update(self, now, dt, pressed=False):
        events = []
        s = self.state
        if s == RISING:
            self.level = min(1.0, (now - self.state_at) / RISE_SECONDS)
            if self.level >= 1.0:
                self._set(IDLE, now)
        elif s == FALLING:
            self.level = max(0.0, 1.0 - (now - self.state_at) / FALL_SECONDS)
            if self.level <= 0.0:
                self._set(HIDDEN, now)
                events.append(EV_HIDDEN)
        elif s == WAITING and now >= self.bite_at:
            self._set(BITE, now)
            events.append(EV_BITE)
        elif s == BITE and now - self.state_at > BITE_WINDOW:
            self._set(IDLE, now)
            events.append(EV_MISSED)
        elif s == PLAYING:
            st = self.game.update(dt, pressed)
            if st != minigame.RUNNING:
                events.append(self._finish(now, st == minigame.CAUGHT))
        elif s == RESULT and now - self.state_at > RESULT_SECONDS:
            events += self._after_result(now)
        return events

    def pick_bobber(self):
        n = self.bobber_count
        if n <= 0:
            return 0
        if self.bobber_pref == "random":
            return _cosmetic.randrange(n)
        try:
            i = int(self.bobber_pref)
        except (TypeError, ValueError):
            i = 0
        return i if 0 <= i < n else 0

    def current_weather(self):
        return self.weather or world.today_weather()

    def roll(self):
        """按钓点、天气、水深挑这一竿上来的东西：Fish 或杂物 ID。"""
        return fishdata.roll(
            self.fish_list, rng=self.rng,
            ids=world.spot_fish(self.spot), algae=world.spot_algae(self.spot),
            depth=self.depth, level=self.fishing_level,
            weather=world.fish_weather(self.current_weather()),
            rerolls=1 if self.mode == "casual" else 0)

    # MARK: 内部

    def _land_junk(self, now, item_id):
        item = self.junk.get(str(item_id)) or fishdata.Junk(item_id)
        self.fish = None
        self.game = None
        level_up = None
        if self.collection is not None:
            level_up = self.collection.add_xp(progression.JUNK_XP)
            self.collection.record_junk(item.id)
        self.result = Result(item, True, junk=True, xp=progression.JUNK_XP, level_up=level_up,
                             depth=self.depth)
        self._set(RESULT, now)
        return [EV_JUNK]

    def _set(self, state, now):
        self.state = state
        self.state_at = now
        if state in (IDLE, WAITING, BITE, PLAYING, RESULT):
            self.level = 1.0

    def _finish(self, now, caught):
        f = self.fish
        if caught:
            g = self.game
            level = self.fishing_level
            size = fishdata.roll_size(f, self.rng, perfect=g.perfect, depth=self.depth,
                                      level=level)
            quality = progression.quality_of(f, size, g.perfect)
            xp = progression.catch_xp(f.difficulty, quality, g.perfect)
            treasure = []
            if g.treasure_caught:
                treasure = progression.roll_treasure(fishdata.season_of(), self.rng)
            is_new = is_record = False
            level_up = None
            price = gear.fish_price(f, quality)
            if self.collection is not None:
                self.collection.gold += price
                level_up = self.collection.add_xp(xp)
                if treasure:
                    self.collection.record_treasure(treasure)
                is_new, is_record = self.collection.record_catch(
                    f.id, size, g.perfect, quality=quality, spot=self.spot)
            self.result = Result(f, True, size, g.perfect, is_new, is_record, quality=quality,
                                 xp=xp, level_up=level_up, treasure=treasure, depth=self.depth)
            self.result.gold = price
        else:
            if self.collection is not None:
                self.collection.record_escape()
            self.result = Result(f, False)
        self._set(RESULT, now)
        return EV_CAUGHT if caught else EV_ESCAPED

    def _after_result(self, now):
        self.game = None
        if self.closing:
            self._set(FALLING, now)
        else:
            self._set(IDLE, now)
        return []
