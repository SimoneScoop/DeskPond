# -*- coding: utf-8 -*-
"""第三期：番茄钟里的简易种田。纯逻辑。

规则（策划案「番茄钟里加种田」一节，10 月 24 日改为跟着番茄钟走、全自动）：
    - 只有 3 块地，不扩建；不出现在鱼塘里
    - 每完整做完一个专注 = 农田过一天：作物长一天（天数照游戏的 Data/Crops，不用浇水），
      成熟的自动收获（进图鉴，每个换 1 个鱼饵），空地自动种上手里的种子（优先当季）
    - 完成的那一刻右上角弹一张农田小卡片，几秒后自己消失；菜单里能打开「我的农田」看全貌
    - 不惩罚：专注中途停下这一轮不算，作物不枯萎，跨季节也照常长完
    - 种子来自宝箱；第一次种田送 3 包当季种子，之后每天第一个番茄送一包（冬天原版没有作物种子，不送）
    - 开始专注时空地就播种（专注期间就能看到地里有东西），做完这个专注再长一天

作物表优先从游戏的 Data/Crops 读（1.5 是字符串，1.6 解包后是 JSON 对象）；
读不到（1.6 原生 .xnb 是对象结构）就用下面这张手工表，只有编号和天数，不含游戏素材。
"""
import random

PLOTS = 3                      # 一排 3 块
MAX_PLOTS = 6                  # 扩建后 2 排 6 块（只有这一档，不开放随意改大小）
EXPAND_LEVEL, EXPAND_PRICE = 3, 2500      # 扩建条件：钓鱼 3 级 + 2,500g（在钓具店「种子」里买）

# 种子 id -> 英文名, 收获物 id, crops.png 里的行号, 各阶段天数
CROPS = {
    "472": ("Parsnip", "24", 0, [1, 1, 1, 1]),
    "474": ("Cauliflower", "190", 2, [1, 2, 4, 4, 1]),
    "475": ("Potato", "192", 3, [1, 1, 1, 2, 1]),
    "477": ("Kale", "250", 5, [1, 2, 2, 1]),
    "479": ("Melon", "254", 7, [1, 2, 3, 3, 3]),
    "480": ("Tomato", "256", 8, [2, 2, 2, 2, 3]),
    "482": ("Hot Pepper", "260", 10, [1, 1, 1, 1, 1]),
    "483": ("Wheat", "262", 11, [1, 1, 1, 1]),
    "487": ("Corn", "270", 15, [2, 3, 3, 3, 3]),
    "488": ("Eggplant", "272", 16, [1, 1, 1, 1, 1]),
    "490": ("Pumpkin", "276", 18, [1, 2, 3, 4, 3]),
    "491": ("Bok Choy", "278", 19, [1, 1, 1, 1]),
}
CROP_NAMES = {v[1]: v[0] for v in CROPS.values()}      # 收获物 id -> 英文名（图鉴用）
SEED_SEASON = {"472": "spring", "474": "spring", "475": "spring", "477": "spring",
               "479": "summer", "480": "summer", "482": "summer", "483": "summer",
               "487": "fall", "488": "fall", "490": "fall", "491": "fall"}
CROP_FRAME_W, CROP_FRAME_H = 16, 32

# 皮埃尔杂货店的种子价格（原版，普通难度）
SEED_PRICES = {"472": 20, "474": 80, "475": 50, "477": 70, "479": 80, "480": 50, "482": 40,
               "483": 10, "487": 150, "488": 20, "490": 100, "491": 50}


def seeds_for_sale(season):
    """皮埃尔这一季卖的种子（冬天原版不卖作物种子）。按价格排。"""
    return sorted((s for s, se in SEED_SEASON.items() if se == season),
                  key=lambda s: (SEED_PRICES[s], s))


def buy_seed(collection, seed):
    """买一包种子。钱不够或不是能买的种子返回 False。"""
    price = SEED_PRICES.get(str(seed))
    if price is None or collection.gold < price:
        return False
    collection.gold -= price
    collection.inventory[str(seed)] = collection.inventory.get(str(seed), 0) + 1
    collection.save()
    return True


def days_to_grow(seed):
    return sum(CROPS[str(seed)][3])


def parse_crops(table):
    """游戏的 Data/Crops -> {种子 id: (英文名, 收获物 id, 行号, [天数])}，只取我们认识的种子。

    1.5：`"472": "1 1 1 1/spring/0/24/-1/0/false/false/false"`（天数/季节/行号/收获物/…）
    1.6 解包 JSON：`"472": {"DaysInPhase": [1,1,1,1], "SpriteIndex": 0, "HarvestItemId": "24", …}`
    """
    out = {}
    if not isinstance(table, dict):
        return out
    for seed, raw in table.items():
        seed = str(seed)
        if seed not in CROPS:
            continue
        name = CROPS[seed][0]
        try:
            if isinstance(raw, str):
                parts = raw.split("/")
                days = [int(x) for x in parts[0].split()]
                row, harvest = int(parts[2]), str(int(parts[3]))
            else:
                days = [int(x) for x in raw.get("DaysInPhase", [])]
                row = int(raw.get("SpriteIndex", CROPS[seed][2]))
                harvest = str(raw.get("HarvestItemId", CROPS[seed][1])).replace("(O)", "")
        except (ValueError, IndexError, AttributeError, TypeError):
            continue
        if days and all(d > 0 for d in days):
            out[seed] = (name, harvest, row, days)
    return out


def crop_table(game_table=None):
    table = dict(CROPS)
    table.update(parse_crops(game_table) if game_table else {})
    return table


def frame_of(phases, days):
    """已经长了 days 天 -> (crops.png 里的第几帧, 是否成熟)。

    原版：第 p 个生长阶段画第 p+1 帧；最后一个阶段之后是成熟，画第「阶段数+1」帧。
    """
    total = sum(phases)
    if days >= total:
        return min(7, len(phases) + 1), True
    acc = 0
    for p, d in enumerate(phases):
        acc += d
        if days < acc:
            return p + 1, False
    return min(7, len(phases) + 1), True


def expand_state(collection):
    """扩建农田：(状态, 说明)。done 已扩建 / locked 等级不够 / poor 钱不够 / buy 可以买。"""
    if len(collection.farm) >= MAX_PLOTS:
        return "done", "已经是 2 排 6 块地"
    if collection.level < EXPAND_LEVEL:
        return "locked", "钓鱼 %d 级解锁" % EXPAND_LEVEL
    if collection.gold < EXPAND_PRICE:
        return "poor", "%sg" % format(EXPAND_PRICE, ",")
    return "buy", "%sg" % format(EXPAND_PRICE, ",")


def expand(collection):
    """买扩建：再开一排 3 块地。成功返回 True。"""
    if expand_state(collection)[0] != "buy":
        return False
    collection.gold -= EXPAND_PRICE
    while len(collection.farm) < MAX_PLOTS:
        collection.farm.append(None)
    collection.save()
    return True


class Farm(object):
    """3 块地（扩建后 6 块）。plots 直接就是存档里的列表（每块 None 或 {"seed", "days"}），改它就是改存档。"""

    def __init__(self, plots, crops=None):
        while len(plots) < PLOTS:
            plots.append(None)
        self.plots = plots
        self.crops = crops or dict(CROPS)

    @property
    def size(self):
        return min(MAX_PLOTS, len(self.plots))

    @property
    def rows(self):
        return (self.size + PLOTS - 1) // PLOTS

    def info(self, i):
        """第 i 块地的状态：None（空地）或 dict(seed, name, harvest, frame, mature, days, total)。"""
        p = self.plots[i]
        if not p or p.get("seed") not in self.crops:
            return None
        name, harvest, row, phases = self.crops[p["seed"]]
        frame, mature = frame_of(phases, p.get("days", 0))
        return {"seed": p["seed"], "name": name, "harvest": harvest, "row": row,
                "frame": frame, "mature": mature, "days": min(p.get("days", 0), sum(phases)),
                "total": sum(phases)}

    def empty(self, i):
        return self.info(i) is None

    def plant(self, i, seed):
        if not self.empty(i) or seed not in self.crops:
            return False
        self.plots[i] = {"seed": seed, "days": 0}
        return True

    def grow(self, days=1):
        """完成一个专注：每块地上的作物长一天。返回这次刚成熟的格子。"""
        ripe = []
        for i, p in enumerate(self.plots):
            if not p or p.get("seed") not in self.crops:
                continue
            was = self.info(i)["mature"]
            p["days"] = p.get("days", 0) + days
            if not was and self.info(i)["mature"]:
                ripe.append(i)
        return ripe

    def harvest(self, i):
        info = self.info(i)
        if info is None or not info["mature"]:
            return None
        self.plots[i] = None
        return info["harvest"]

    def summary(self):
        """菜单里的一行：防风草 2/4 · 土豆 成熟 · 空地。"""
        parts = []
        for i in range(self.size):
            info = self.info(i)
            if info is None:
                parts.append("空地")
            elif info["mature"]:
                parts.append("%s 成熟" % info["name"])
            else:
                parts.append("%s %d/%d" % (info["name"], info["days"], info["total"]))
        return parts


def pick_seed(inventory, season):
    """种哪颗：手上有的种子里优先当季的。没有返回 None。"""
    have = [s for s in CROPS if inventory.get(s, 0) > 0]
    if not have:
        return None
    have.sort(key=lambda s: (SEED_SEASON.get(s) != season, s))
    return have[0]


def daily_seed(season, rng=None):
    """每天第一次摸鱼送的种子；冬天没有。"""
    rng = rng or random.Random()
    pool = [s for s, se in SEED_SEASON.items() if se == season]
    return rng.choice(sorted(pool)) if pool else None


class DayReport(object):
    """完成一个番茄后农田发生了什么（给小卡片显示）。"""
    __slots__ = ("gift", "grew", "ripe", "harvested", "planted", "gold")

    def __init__(self):
        self.gift = None          # 今天送的种子 id
        self.grew = []            # 长了一天的格子
        self.ripe = []            # 这次刚成熟的格子
        self.harvested = []       # [(格子, 收获物 id)]
        self.planted = []         # [(格子, 种子 id)]
        self.gold = 0             # 收获卖了多少钱

    @property
    def changed(self):
        return bool(self.gift or self.grew or self.harvested or self.planted)


STARTER_SEEDS = 3


def _gifts(collection, season, rng=None):
    """新手种子包（第一次，3 包）+ 每天第一个番茄送一包。返回送了哪颗（没送返回 None）。"""
    first = None
    if not collection.farm_started:
        collection.farm_started = True
        for _ in range(STARTER_SEEDS):
            seed = daily_seed(season, rng)
            if seed:
                collection.inventory[seed] = collection.inventory.get(seed, 0) + 1
                first = first or seed
    today = collection.today()
    if collection.farm_gift != today:
        collection.farm_gift = today
        seed = daily_seed(season, rng)
        if seed:
            collection.inventory[seed] = collection.inventory.get(seed, 0) + 1
            first = first or seed
    return first


def next_seed(collection, plot, season):
    """这块地下次种什么：选了的种子手上还有就种它，否则自动挑（当季优先）。"""
    plan = collection.farm_plan[plot] if plot < len(collection.farm_plan) else None
    if plan and collection.inventory.get(plan, 0) > 0:
        return plan
    return pick_seed(collection.inventory, season)


def plant_now(farm, collection, plot, season):
    """空地马上种下（按选好的或者自动）。种了返回种子 id。"""
    if not farm.empty(plot):
        return None
    seed = next_seed(collection, plot, season)
    if seed is None:
        return None
    collection.inventory[seed] -= 1
    farm.plant(plot, seed)
    return seed


def set_plan(farm, collection, plot, seed, season):
    """「我的农田」里给一块地选种子（None = 自动）。空地会马上种下。返回种下的种子 id。"""
    collection.farm_plan[plot] = str(seed) if seed else None
    planted = plant_now(farm, collection, plot, season)
    collection.save()
    return planted


def _plant_empty(farm, collection, season, rep):
    for i in range(farm.size):
        seed = plant_now(farm, collection, i, season)
        if seed is not None:
            rep.planted.append((i, seed))


def focus_start(farm, collection, season, rng=None):
    """开始一个专注：送种子（新手包 / 每天一次）→ 空地马上播种。"""
    rep = DayReport()
    rep.gift = _gifts(collection, season, rng)
    _plant_empty(farm, collection, season, rep)
    collection.save()
    return rep


def focus_done(farm, collection, season, rng=None):
    """完整做完一个专注：送种子（每天一次）→ 作物长一天 → 收获成熟的 → 空地播种。"""
    rep = DayReport()
    rep.gift = _gifts(collection, season, rng)
    rep.grew = [i for i in range(farm.size) if not farm.empty(i) and not farm.info(i)["mature"]]
    rep.ripe = farm.grow()
    for i in range(farm.size):
        info = farm.info(i)
        if info is not None and info["mature"]:
            crop = farm.harvest(i)
            from . import gear
            price = gear.crop_price(crop)
            collection.record_harvest(crop, gold=price)
            rep.gold += price
            rep.harvested.append((i, crop))
    _plant_empty(farm, collection, season, rep)
    collection.save()
    return rep


def progress_caption(farm, name_of, phase, secs_left, season):
    """农田下面那一行字：番茄钟还剩多久、这一轮做完地里会怎样。

    phase：pomodoro 的阶段（"focus" / "break" / "long_break" / "idle"）。
    """
    infos = [farm.info(i) for i in range(farm.size)]
    growing = [i for i in infos if i and not i["mature"]]
    empty = None
    if not any(infos):
        empty = "冬天不长作物，春天再种" if season == "winter" else "没有种子（宝箱会开出，每天第一个番茄也送）"
    soon = min(growing, key=lambda i: i["total"] - i["days"]) if growing else None
    what = "作物长一天"
    if soon is not None:
        nxt = soon["days"] + 1
        what = "%s → %d/%d" % (name_of(soon["harvest"]), nxt, soon["total"])
        if nxt >= soon["total"]:
            what = "%s 可以收了" % name_of(soon["harvest"])
    elif any(i and i["mature"] for i in infos):
        what = "收获"
    if phase == "focus":
        mm, ss = divmod(int(max(0, secs_left) + 0.999), 60)
        return "🍅 %d:%02d 后 · %s" % (mm, ss, empty or what)
    if phase in ("break", "long_break"):
        return "🐟 摸鱼中 · " + (empty or "下个番茄做完：%s" % what)
    return empty or "下个番茄做完：%s" % what


def short_caption(phase, secs_left, paused=False):
    """农田下面平时只显示这么短的一行：图标 + 剩余时间。鼠标移上去才换成 progress_caption 的完整版。"""
    mm, ss = divmod(int(max(0, secs_left) + 0.999), 60)
    if paused:
        return "⏸ %d:%02d" % (mm, ss)
    if phase == "focus":
        return "🍅 %d:%02d" % (mm, ss)
    if phase in ("break", "long_break"):
        return "🐟 %d:%02d" % (mm, ss)
    return ""


def describe(report, name_of):
    """把这次的变化写成两三行字。"""
    lines = []
    if report.harvested:
        lines.append("收获 %s：+%dg，鱼饵 +%d" % (
            "、".join(name_of(c) for _, c in report.harvested), report.gold,
            len(report.harvested)))
    if report.planted:
        lines.append("种下 %s" % "、".join(name_of(s) for _, s in report.planted))
    if report.gift:
        lines.append("今天送了一包%s" % name_of(report.gift))
    if not lines:
        lines.append("作物都长了一天" if report.grew else "没有种子：宝箱里会开出来，每天第一个番茄也送一包")
    return lines
