# -*- coding: utf-8 -*-
"""成长：钓鱼等级、鱼的品质、宝箱。纯逻辑。

数字参照原版（社区整理的近似值）：
    经验 = max(1, (品质+1)×3 + 难度/3)，完美钓起 ×2.4；杂物 3 点
    升级门槛 100 / 380 / 770 / 1300 / 2150 / 3300 / 4800 / 6900 / 10000 / 15000
    品质按尺寸在这条鱼范围里的位置：<33% 普通、<66% 银星、其余金星；完美钓起再升一档（金 → 铱）
"""
import random

LEVEL_XP = [100, 380, 770, 1300, 2150, 3300, 4800, 6900, 10000, 15000]
MAX_LEVEL = len(LEVEL_XP)
JUNK_XP = 3
PERFECT_MULT = 2.4

QUALITY_NAMES = ["普通", "银星", "金星", "铱星"]
QUALITY_COLORS = [None, (178, 190, 205), (240, 190, 40), (170, 90, 230)]
GAME_QUALITY = [0, 1, 2, 4]        # 原版的品质编号（铱星是 4），经验公式用这个


def level_for(xp):
    lv = 0
    for need in LEVEL_XP:
        if xp >= need:
            lv += 1
    return lv


def level_progress(xp):
    """(当前等级, 本级已有经验, 本级需要经验)。满级时后两个相等。"""
    lv = level_for(xp)
    if lv >= MAX_LEVEL:
        return lv, 1, 1
    base = LEVEL_XP[lv - 1] if lv > 0 else 0
    return lv, xp - base, LEVEL_XP[lv] - base


def quality_of(fish, size, perfect=False):
    lo, hi = fish.min_size or 0, fish.max_size or 0
    ratio = 1.0 if hi <= lo else (size - lo) / float(hi - lo)
    q = 0 if ratio < 0.33 else (1 if ratio < 0.66 else 2)
    if perfect:
        q = min(3, q + 1)
    return q


def catch_xp(difficulty, quality, perfect=False):
    xp = max(1, (GAME_QUALITY[quality] + 1) * 3 + int(difficulty or 0) // 3)
    if perfect:
        xp = int(xp * PERFECT_MULT)
    return xp


# MARK: 浮漂样式

def bobbers_unlocked(species, total_styles):
    """原版浮漂机：一开始只有默认样式，每多钓到 2 种不同的鱼解锁下一种（按顺序）。"""
    if total_styles <= 0:
        return 0
    return max(1, min(total_styles, 1 + species // 2))


def species_for_style(index):
    """解锁第 index 种样式（从 0 数）需要钓到几种鱼。"""
    return index * 2


# MARK: 宝箱

BAIT = "685"
SEEDS = {      # 当季种子（给第三期种田用）；冬天原版没有种子，换成别的
    "spring": ["472", "474", "475", "477"],     # 防风草、花椰菜、土豆、甘蓝
    "summer": ["479", "480", "482", "483"],     # 甜瓜、番茄、辣椒、小麦
    "fall":   ["487", "488", "490", "491"],     # 玉米、茄子、南瓜、小白菜
    "winter": [],
}
MINERALS = ["80", "86", "84", "82", "66", "62", "60", "64", "68", "70", "72", "378", "380", "384"]
TREASURE_NAMES = {
    "685": "Bait",
    "472": "Parsnip Seeds", "474": "Cauliflower Seeds", "475": "Potato Seeds", "477": "Kale Seeds",
    "479": "Melon Seeds", "480": "Tomato Seeds", "482": "Pepper Seeds", "483": "Wheat Seeds",
    "487": "Corn Seeds", "488": "Eggplant Seeds", "490": "Pumpkin Seeds", "491": "Bok Choy Seeds",
    "80": "Quartz", "86": "Earth Crystal", "84": "Frozen Tear", "82": "Fire Quartz",
    "66": "Amethyst", "62": "Aquamarine", "60": "Emerald", "64": "Ruby", "68": "Topaz",
    "70": "Jade", "72": "Diamond", "378": "Copper Ore", "380": "Iron Ore", "384": "Gold Ore",
}


def roll_treasure(season, rng=None):
    """宝箱内容：[(物品 id, 数量)]。没有金币和商店，只给鱼饵、种子、小物件。"""
    rng = rng or random.Random()
    out = []
    r = rng.random()
    seeds = SEEDS.get(season) or []
    if r < 0.45 or (r < 0.8 and not seeds):
        out.append((BAIT, rng.randint(2, 5)))
    elif r < 0.8:
        out.append((rng.choice(seeds), rng.randint(1, 3)))
    else:
        out.append((rng.choice(MINERALS), 1))
    if rng.random() < 0.25:                      # 偶尔多送几个鱼饵
        out.append((BAIT, rng.randint(1, 2)))
    merged = {}
    for item, n in out:
        merged[item] = merged.get(item, 0) + n
    return sorted(merged.items())
