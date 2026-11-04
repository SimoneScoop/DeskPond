# -*- coding: utf-8 -*-
"""钓鱼小游戏的纯逻辑：绿条物理、鱼的运动、收线进度。不依赖任何界面，可以用假时钟测试。

坐标单位是「贴图像素」：竖条框里蓝色轨道高 TRACK_HEIGHT 像素，0 在顶部。
手感参照原版：按住鼠标绿条加速上升，松开受重力下落，撞到底会弹一下；
鱼在轨道里按自己的行为模式（mixed / dart / smooth / sinker / floater）游动；
绿条罩住鱼时进度上涨，罩不住时下降，满了算钓到，归零算跑了。
钓鱼等级越高绿条越长（原版：每级 +2 贴图像素）。有 15% 的概率出现宝箱：
绿条罩住宝箱一会儿就拿到，但只有鱼也钓上来才算数。
实现是自己写的近似，参数可调，不是原版代码。
"""
import random

TRACK_TOP = 3          # 轨道在竖条框贴图里的起点（像素）
TRACK_HEIGHT = 139     # 轨道高度（像素）
FISH_SIZE = 10         # 鱼图标在轨道里的显示高度（原图 20px，按半倍画）

# 难度档位：摸鱼本来就该轻松一点，默认用「轻松」。
# 用「0.2 秒反应延迟 + 15% 手抖」的模拟玩家测过（tests/test_core.py）：
#   轻松：简单鱼 ~100%，最难的鱼 ~80%，一局 6–15 秒
#   原版：简单鱼 ~70%，最难的鱼 ~30%
#   原版手感的绿条 0 级 24 像素、10 级 44 像素；进度 +0.12/秒、-0.18/秒（原版每帧 +0.002 / -0.003）
MODES = {
    "casual":   {"bar": 38, "gain": 0.16, "loss": 0.11, "fish_speed": 0.8},
    "original": {"bar": 24, "gain": 0.12, "loss": 0.18, "fish_speed": 1.0},
}
BAR_PER_LEVEL = 2

TREASURE_CHANCE = 0.15
TREASURE_SIZE = 10           # 宝箱在轨道里的显示高度（贴图像素）
TREASURE_APPEAR = (1.0, 3.0) # 开局后多久出现（秒）
TREASURE_GAIN = 0.55         # 罩住宝箱时它的进度每秒涨多少
TREASURE_LOSS = 0.4

GRAVITY = 220.0        # 像素/秒²：松开时往下掉
LIFT = 220.0           # 像素/秒²：按住时往上加速
MAX_BAR_SPEED = 150.0  # 像素/秒
BOUNCE = 0.5           # 撞底反弹系数
START_PROGRESS = 0.3
GRACE = 0.8            # 开局这么多秒内鱼跑出绿条不扣进度（人有反应时间）

RUNNING, CAUGHT, ESCAPED = "running", "caught", "escaped"


class Minigame(object):

    def __init__(self, difficulty=50, behavior="mixed", mode="casual", rng=None, level=0,
                 treasure=None, bar_bonus=0, loss_mult=1.0, keep_treasure=False):
        cfg = MODES.get(mode, MODES["casual"])
        self.rng = rng or random.Random()
        self.difficulty = max(1.0, min(110.0, float(difficulty)))
        self.behavior = behavior if behavior in (
            "mixed", "dart", "smooth", "sinker", "floater") else "mixed"
        self.level = max(0, min(10, int(level or 0)))
        self.bar_height = float(cfg["bar"] + BAR_PER_LEVEL * self.level + bar_bonus)
        self.keep_treasure = keep_treasure      # 寻宝者：宝箱进度不往回掉
        self.gain = cfg["gain"]
        self.loss = cfg["loss"] * loss_mult     # 陷阱浮标：掉得慢
        self.fish_speed = cfg["fish_speed"]

        self.bar_pos = TRACK_HEIGHT - self.bar_height   # 绿条顶端位置，开局在底部
        self.bar_vel = 0.0
        # 和原版一样，开局鱼在绿条里面（底部），给玩家反应的时间
        self.fish_pos = self.bar_pos + self.bar_height / 2.0 - FISH_SIZE / 2.0
        self.fish_vel = 0.0
        self.fish_target = self.fish_pos
        self.progress = START_PROGRESS
        self.state = RUNNING
        self.perfect = True           # 全程没让鱼离开过绿条
        self.elapsed = 0.0

        # 宝箱：treasure=None 时按概率掷，True/False 用来测试
        self.treasure = (self.rng.random() < TREASURE_CHANCE) if treasure is None else bool(treasure)
        self.treasure_at = self.rng.uniform(*TREASURE_APPEAR)
        self.treasure_pos = self.rng.uniform(TRACK_HEIGHT * 0.1, TRACK_HEIGHT * 0.8)
        self.treasure_progress = 0.0
        self.treasure_caught = False

    @property
    def treasure_visible(self):
        return self.treasure and not self.treasure_caught and self.elapsed >= self.treasure_at

    def treasure_in_bar(self):
        center = self.treasure_pos + TREASURE_SIZE / 2.0
        return self.bar_pos <= center <= self.bar_pos + self.bar_height

    # MARK: 判定

    def fish_in_bar(self):
        center = self.fish_pos + FISH_SIZE / 2.0
        return self.bar_pos <= center <= self.bar_pos + self.bar_height

    # MARK: 推进

    def update(self, dt, pressed):
        """推进 dt 秒。pressed = 鼠标是否按住。返回当前状态。"""
        if self.state != RUNNING:
            return self.state
        dt = max(0.0, min(dt, 0.1))   # 卡顿时别一步跳太远
        self.elapsed += dt
        self._update_bar(dt, pressed)
        self._update_fish(dt)
        if self.treasure_visible:
            if self.treasure_in_bar():
                self.treasure_progress += TREASURE_GAIN * dt
                if self.treasure_progress >= 1.0:
                    self.treasure_progress = 1.0
                    self.treasure_caught = True
            elif not self.keep_treasure:
                self.treasure_progress = max(0.0, self.treasure_progress - TREASURE_LOSS * dt)

        if self.fish_in_bar():
            self.progress += self.gain * dt
        elif self.elapsed > GRACE:
            self.progress -= self.loss * dt
            self.perfect = False
        if self.progress >= 1.0:
            self.progress = 1.0
            self.state = CAUGHT
        elif self.progress <= 0.0:
            self.progress = 0.0
            self.state = ESCAPED
        return self.state

    def _update_bar(self, dt, pressed):
        self.bar_vel += (-LIFT if pressed else GRAVITY) * dt
        self.bar_vel = max(-MAX_BAR_SPEED, min(MAX_BAR_SPEED, self.bar_vel))
        self.bar_pos += self.bar_vel * dt
        bottom = TRACK_HEIGHT - self.bar_height
        if self.bar_pos > bottom:
            self.bar_pos = bottom
            self.bar_vel = -self.bar_vel * BOUNCE if self.bar_vel > 20 else 0.0
        if self.bar_pos < 0:
            self.bar_pos = 0.0
            self.bar_vel = 0.0

    def _update_fish(self, dt):
        d = self.difficulty
        lo, hi = 0.0, TRACK_HEIGHT - FISH_SIZE
        # 换目标的频率：越难越频繁
        rate = {"smooth": 0.35, "dart": 1.6, "mixed": 0.9,
                "sinker": 0.8, "floater": 0.8}[self.behavior] * (0.3 + d / 60.0)
        if self.rng.random() < rate * dt:
            span = (hi - lo) * min(1.0, 0.25 + d / 120.0)
            if self.behavior == "dart":
                span *= 1.3
            target = self.fish_pos + self.rng.uniform(-span, span)
            if self.behavior == "sinker":
                target += span * 0.35
            elif self.behavior == "floater":
                target -= span * 0.35
            self.fish_target = max(lo, min(hi, target))

        # 弹簧 + 阻尼：越难越快
        stiffness = (2.0 + d / 12.0) * self.fish_speed
        if self.behavior == "dart":
            stiffness *= 1.8
        elif self.behavior == "smooth":
            stiffness *= 0.6
        damping = 2.0 * (stiffness ** 0.5) * 0.7
        accel = (self.fish_target - self.fish_pos) * stiffness - self.fish_vel * damping
        self.fish_vel += accel * dt
        self.fish_pos += self.fish_vel * dt
        if self.fish_pos < lo:
            self.fish_pos, self.fish_vel = lo, 0.0
        elif self.fish_pos > hi:
            self.fish_pos, self.fish_vel = hi, 0.0
