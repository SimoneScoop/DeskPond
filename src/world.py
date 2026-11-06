# -*- coding: utf-8 -*-
"""钓点、天气、水深：决定「这一竿」在什么环境下钓。

钓点只记鱼的 ID（游戏里的物品编号），鱼的难度、时段、季节、天气等属性仍然从
本机游戏的 Data/Fish 读取。1.6 的 Data/Locations 是嵌套对象结构，纯 Python 的
XNB 解码器读不了，所以这张「钓点 → 鱼」的对照表手工维护，只含编号，不含任何游戏素材。
"""
import random
import time

from . import fishdata

# key, 名字, 鱼的 ID, 会钓到的藻类（算杂物）, 解锁要求（图鉴收集多少种）
SPOTS = [
    ("town_river", "镇上河流",
     ("132", "137", "138", "139", "140", "141", "143", "144", "145", "699", "706", "707"),
     ("153",), 0),
    ("mountain_lake", "山顶湖",
     ("136", "140", "141", "142", "269", "698", "700", "702", "707"),
     ("153",), 0),
    ("ocean", "海边",
     ("128", "129", "130", "131", "146", "147", "148", "149", "150", "151", "154", "155",
      "267", "701", "705", "708"),
     ("152",), 0),
    ("forest_river", "煤矿森林河",
     ("132", "137", "138", "139", "140", "141", "142", "143", "144", "145", "269", "699",
      "702", "704", "706", "707"),
     ("153",), 0),
    ("secret_woods", "秘密森林",
     ("142", "734"),
     ("153",), 10),
    ("desert", "沙漠",
     ("164", "165"),
     (), 20),
]
SPOT_KEYS = [s[0] for s in SPOTS]
DEFAULT_SPOT = "town_river"
_BY_KEY = {s[0]: s for s in SPOTS}


def spot_name(key):
    return _BY_KEY.get(key, _BY_KEY[DEFAULT_SPOT])[1]


def spot_fish(key):
    return _BY_KEY.get(key, _BY_KEY[DEFAULT_SPOT])[2]


def spot_algae(key):
    return _BY_KEY.get(key, _BY_KEY[DEFAULT_SPOT])[3]


def unlock_need(key):
    return _BY_KEY.get(key, _BY_KEY[DEFAULT_SPOT])[4]


def is_unlocked(key, caught_species):
    return key in _BY_KEY and caught_species >= unlock_need(key)


def spots_of(fish_id):
    """这条鱼在哪些钓点出没（给图鉴提示用）。"""
    return [s[0] for s in SPOTS if str(fish_id) in s[2]]


# MARK: 天气

# 每天一个虚拟天气，按日期定种子：同一天里重开 App 天气不变。不联网。
RAIN_CHANCE = {"spring": 0.2, "summer": 0.15, "fall": 0.2, "winter": 0.0}
SNOW_CHANCE = 0.3
WEATHER_ZH = {"sunny": "☀️ 晴天", "rainy": "🌧 雨天", "snow": "❄️ 下雪"}


def today_weather(t=None):
    t = t or time.localtime()
    rng = random.Random("moyu-weather-" + time.strftime("%Y-%m-%d", t))
    season = fishdata.season_of(t)
    r = rng.random()
    if season == "winter":
        return "snow" if r < SNOW_CHANCE else "sunny"
    return "rainy" if r < RAIN_CHANCE[season] else "sunny"


def fish_weather(weather):
    """鱼只分晴/雨：下雪不算雨天（和原版一样）。"""
    return "rainy" if weather == "rainy" else "sunny"


# MARK: 水深

MAX_DEPTH = 5


def depth_from_rel(rel):
    """点击位置在水里的相对高度 -> 水深 1..5。

    rel = 0 是水面最上沿（岸边、最浅），1 是屏幕底边（最深）：往下看是往水底看。
    按相对位置算，所以把水面调低不吃亏。
    """
    rel = max(0.0, min(1.0, rel))
    return max(1, min(MAX_DEPTH, 1 + int(rel * MAX_DEPTH)))
