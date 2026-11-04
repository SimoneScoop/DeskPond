# -*- coding: utf-8 -*-
"""鱼的数据：解析游戏的 Data/Fish 表，按现实的季节和时间段挑一条鱼。

Data/Fish 每条是
    `id -> "名字/难度/行为/最小尺寸/最大尺寸/时间段/季节/天气/(旧位置字段)/最大水深/生成倍率/水深倍率/最低钓鱼等级/..."`，
蟹笼类的第二个字段是 "trap"，钓竿钓不到，跳过。

挑鱼按原版的规则：对钓点里的候选鱼打乱顺序，逐条按「上钩概率」掷骰子，第一条掷中的
就是这次的鱼；一条都没中就钓上杂物。概率公式来自社区对 1.5/1.6 的整理：
    P = min(0.9, 生成倍率 - max(0, 最大水深 - 水深) × 水深倍率 × 生成倍率 + 钓鱼等级 / 50)
"""
import random
import time

SEASONS = ("spring", "summer", "fall", "winter")
SEASON_ZH = {"spring": "春", "summer": "夏", "fall": "秋", "winter": "冬"}

# 传说之鱼和它们的子代：一辈子钓一次的东西，不该在摸鱼时随便上钩
LEGENDARY = {"159", "160", "163", "682", "775", "898", "899", "900", "901", "902"}

# 杂物：藻类在钓点里和鱼一起掷骰子；垃圾是一条鱼都没掷中时的结果。只存编号和英文名，
# 中文名、图标从本机游戏读。
ALGAE = {"152": "Seaweed", "153": "Green Algae", "157": "White Algae"}
TRASH = {"167": "Joja Cola", "168": "Trash", "169": "Driftwood", "170": "Broken Glasses",
         "171": "Broken CD", "172": "Soggy Newspaper"}
JUNK_NAMES = dict(ALGAE, **TRASH)
ALGAE_CHANCE = 0.1

# Data/Fish 缺字段（老缓存、mod 加的鱼）时用的默认值
DEFAULT_MAX_DEPTH = 4
DEFAULT_SPAWN = 0.3
DEFAULT_DEPTH_MULT = 0.1
MAX_CHANCE = 0.9


class Fish(object):
    __slots__ = ("id", "name", "name_zh", "difficulty", "behavior", "min_size",
                 "max_size", "times", "seasons", "weather",
                 "max_depth", "spawn_mult", "depth_mult", "min_level", "desc",
                 "price")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    @property
    def display_name(self):
        return self.name_zh or self.name

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def active_at(self, game_time):
        for start, end in self.times:
            if start <= game_time < end:
                return True
        return False

    def __repr__(self):
        return "Fish(%s %s d=%s %s)" % (self.id, self.name, self.difficulty, self.behavior)


class Junk(object):
    """杂物：海草、绿藻、垃圾……不进小游戏，直接拉上来。"""
    __slots__ = ("id", "name", "name_zh")
    junk = True

    def __init__(self, id, name=None, name_zh=None):
        self.id = str(id)
        self.name = name or JUNK_NAMES.get(self.id, "Junk")
        self.name_zh = name_zh

    @property
    def display_name(self):
        return self.name_zh or self.name

    def to_dict(self):
        return {"id": self.id, "name": self.name, "name_zh": self.name_zh}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("id"), d.get("name"), d.get("name_zh"))

    def __repr__(self):
        return "Junk(%s %s)" % (self.id, self.name)


def _num(parts, i, cast, default):
    try:
        return cast(parts[i])
    except (IndexError, ValueError):
        return default


def parse_entry(fid, raw):
    """解析一条 Data/Fish。不是钓竿鱼、或格式不对时返回 None。"""
    parts = raw.split("/")
    if len(parts) < 8 or parts[1] == "trap" or str(fid) in JUNK_NAMES:
        return None
    try:
        nums = [int(x) for x in parts[5].split()]
        times = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
        fish = Fish(
            id=str(fid), name=parts[0], name_zh=None,
            difficulty=int(parts[1]), behavior=parts[2],
            min_size=int(parts[3]), max_size=int(parts[4]),
            times=times or [(600, 2600)],
            seasons=[s for s in parts[6].split() if s in SEASONS],
            weather=parts[7],
            max_depth=_num(parts, 9, int, DEFAULT_MAX_DEPTH),
            spawn_mult=_num(parts, 10, float, DEFAULT_SPAWN),
            depth_mult=_num(parts, 11, float, DEFAULT_DEPTH_MULT),
            min_level=_num(parts, 12, int, 0))
    except (ValueError, IndexError):
        return None
    return fish


def parse_table(table, names_zh=None):
    """Data/Fish 整张表 -> [Fish]。names_zh: 英文名 -> 中文名。"""
    out = []
    for fid, raw in table.items():
        f = parse_entry(fid, raw)
        if f is None:
            continue
        if names_zh:
            f.name_zh = names_zh.get(f.name)
        out.append(f)
    out.sort(key=lambda f: (int(f.id) if f.id.isdigit() else 10 ** 6, f.id))
    return out


# MARK: 现实时间 -> 游戏时间

def season_of(t=None):
    """现实月份 -> 季节（北半球：3-5 春 / 6-8 夏 / 9-11 秋 / 12-2 冬）。"""
    month = (t or time.localtime()).tm_mon
    return SEASONS[((month - 3) % 12) // 3]


def game_time_of(t=None):
    """现实钟点 -> 游戏时间（600–2600，凌晨 0-2 点算 2400-2600，2-6 点按 2600 处理）。"""
    t = t or time.localtime()
    h, m = t.tm_hour, t.tm_min
    if h < 2:
        h += 24
    elif h < 6:
        return 2550
    return h * 100 + m


def candidates(fish_list, season=None, game_time=None, weather="any",
               include_legendary=False, ids=None, level=None):
    """当下能上钩的鱼。ids = 钓点里的鱼（None 表示不限钓点）；level = 钓鱼等级（None 不限）。"""
    season = season or season_of()
    game_time = game_time if game_time is not None else game_time_of()
    allowed = set(ids) if ids is not None else None
    out = []
    for f in fish_list:
        if allowed is not None and f.id not in allowed:
            continue
        if not include_legendary and f.id in LEGENDARY:
            continue
        if f.seasons and season not in f.seasons:
            continue
        if not f.active_at(game_time):
            continue
        if weather != "any" and f.weather not in ("both", weather):
            continue
        if level is not None and (f.min_level or 0) > level:
            continue
        out.append(f)
    return out


def catch_chance(fish, depth, level=0):
    """原版的上钩概率：水比这条鱼喜欢的浅，概率按水深倍率往下掉。"""
    spawn = fish.spawn_mult if fish.spawn_mult is not None else DEFAULT_SPAWN
    max_depth = fish.max_depth if fish.max_depth is not None else DEFAULT_MAX_DEPTH
    dmult = fish.depth_mult if fish.depth_mult is not None else DEFAULT_DEPTH_MULT
    chance = spawn - max(0, max_depth - depth) * dmult * spawn + level / 50.0
    return max(0.0, min(MAX_CHANCE, chance))


def roll_once(pool, algae=(), depth=5, level=0, rng=None):
    """掷一轮：返回 Fish，或者杂物的 ID（字符串）。"""
    rng = rng or random.Random()
    entries = [(f, catch_chance(f, depth, level)) for f in pool]
    entries += [(a, ALGAE_CHANCE) for a in algae]
    rng.shuffle(entries)
    for obj, chance in entries:
        if rng.random() < chance:
            return obj
    return rng.choice(sorted(TRASH))


def roll(fish_list, rng=None, ids=None, algae=(), depth=5, level=0, rerolls=0, **kw):
    """按钓点 / 季节 / 时段 / 天气 / 水深挑这一竿钓上来的东西。

    返回 Fish 或杂物 ID。rerolls：钓到杂物时再掷几轮（轻松模式给 1 次）。
    """
    rng = rng or random.Random()
    pool = candidates(fish_list, ids=ids, level=level, **kw)
    got = None
    for _ in range(1 + max(0, rerolls)):
        got = roll_once(pool, algae, depth, level, rng)
        if isinstance(got, Fish):
            return got
    return got


def size_ratio(rng, perfect=False, depth=5, level=0):
    """尺寸在这条鱼范围里的位置 0..1。

    原版里抛得越远（水越深）、钓鱼等级越高，鱼越大；完美钓起偏大一点。
    这里用一个近似：深水 5 不打折，浅水 1 打到 0.68；每级 +2%。
    """
    base = rng.random() ** (0.6 if perfect else 1.2)
    depth = max(1, min(5, depth))
    return max(0.0, min(1.0, base * (0.6 + 0.4 * depth / 5.0) + level * 0.02))


def roll_size(fish, rng=None, perfect=False, depth=5, level=0):
    """尺寸（英寸）。"""
    rng = rng or random.Random()
    lo, hi = fish.min_size, max(fish.min_size, fish.max_size)
    return int(round(lo + (hi - lo) * size_ratio(rng, perfect, depth, level)))


BEHAVIOR_ZH = {"mixed": "混合", "dart": "飞窜", "smooth": "平稳", "sinker": "下沉", "floater": "上浮"}


def _fmt_time(v):
    h, m = divmod(int(v), 100)
    return "%d:%02d" % (h % 24, m)


def hint(f, spots=None):
    """图鉴里的出没提示：钓点 · 季节 · 时间 · 天气 · 难度 · 行为。spots 是钓点名字列表。"""
    seasons = " ".join(SEASON_ZH.get(s, s) for s in SEASONS
                       if s in (f.seasons or [])) or "全年"
    times = "、".join("%s–%s" % (_fmt_time(a), _fmt_time(b)) for a, b in (f.times or []))
    stars = "★" * max(1, min(5, int(round(f.difficulty / 22.0)))) if f.difficulty else ""
    weather = {"sunny": "晴天", "rainy": "雨天"}.get(f.weather, "")
    parts = (["、".join(spots)] if spots else []) + [seasons, times or "全天"]
    if weather:
        parts.append(weather)
    parts.append("难度 %s" % stars)
    parts.append(BEHAVIOR_ZH.get(f.behavior, f.behavior or ""))
    return " · ".join(p for p in parts if p)
