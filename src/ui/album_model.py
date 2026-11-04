# -*- coding: utf-8 -*-
"""图鉴的数据部分（纯逻辑，Mac 和 Windows 两个界面共用）：哪一页、哪个筛选、显示哪些东西。"""
from .. import farm as farmlib
from .. import fishdata, progression, world

PAGES = [("fish", "鱼"), ("items", "杂物与宝物"), ("crops", "作物"), ("bobbers", "浮漂")]
FISH_FILTERS = [("now", "现在能钓"), ("all", "全部"), ("season", "本季"), ("spot", "当前钓点")]
MILESTONES = [(10, "渔夫"), (24, "老水手")]      # 再加上「全部」= 钓鱼大师


def milestone_names(caught, total):
    out = [name for need, name in MILESTONES if caught >= need]
    if total and caught >= total:
        out.append("钓鱼大师")
    return out


class Bobber(object):
    __slots__ = ("id", "index")

    def __init__(self, index):
        self.index = index
        self.id = "bobber_%d" % index


class Album(object):
    """图鉴的数据：哪一页、哪个筛选、显示哪些东西。纯逻辑，方便测试。"""

    def __init__(self, fish_list, collection, items=None, spot_fn=None, weather_fn=None):
        self.all_fish = sorted([f for f in fish_list if f.id not in fishdata.LEGENDARY],
                               key=lambda f: (len(f.id), f.id))
        self.collection = collection
        self.items = items or {}
        self.spot_fn = spot_fn or (lambda: world.DEFAULT_SPOT)
        self.weather_fn = weather_fn or world.today_weather
        self.page = "fish"
        self.filter = "now"
        self.bobber_total = 0
        self.bobber_pref = lambda: 0
        self.on_bobber = None          # on_bobber(0..38 或 "random")

    @property
    def total(self):
        return len(self.all_fish)

    def caught(self):
        return sum(1 for f in self.all_fish if f.id in self.collection.fish)

    def bobber_count(self):
        return progression.bobbers_unlocked(self.collection.caught_species(), self.bobber_total)

    def available_now(self):
        """此刻在已解锁的钓点、今天的天气下能钓到的鱼。"""
        species = self.collection.caught_species()
        ids = set()
        for key in world.SPOT_KEYS:
            if world.is_unlocked(key, species):
                ids.update(world.spot_fish(key))
        pool = fishdata.candidates(self.all_fish, ids=ids,
                                   weather=world.fish_weather(self.weather_fn()))
        return set(f.id for f in pool)

    def entries(self, page=None, filt=None):
        page = page or self.page
        filt = filt or self.filter
        if page == "bobbers":
            return [Bobber(i) for i in range(self.bobber_total)]
        if page == "crops":
            crops = sorted(farmlib.CROPS.items(),
                           key=lambda kv: (["spring", "summer", "fall"].index(
                               farmlib.SEED_SEASON.get(kv[0], "spring")), kv[0]))
            return [self.items[v[1]] for _, v in crops if v[1] in self.items]
        if page == "items":
            crop_ids = set(farmlib.CROP_NAMES)
            ids = [i for i in self.items if i not in crop_ids]
            ids.sort(key=lambda i: (i not in fishdata.JUNK_NAMES, int(i) if i.isdigit() else 0))
            return [self.items[i] for i in ids]
        if filt == "now":
            now = self.available_now()
            return [f for f in self.all_fish if f.id in now]
        if filt == "season":
            season = fishdata.season_of()
            return [f for f in self.all_fish if not f.seasons or season in f.seasons]
        if filt == "spot":
            ids = set(world.spot_fish(self.spot_fn()))
            return [f for f in self.all_fish if f.id in ids]
        return list(self.all_fish)

    def item_count(self, item_id):
        col = self.collection
        return (col.items.get(item_id, 0) + col.treasure.get(item_id, 0)
                + col.crops.get(item_id, 0))

    def got(self, e):
        if isinstance(e, Bobber):
            return e.index < self.bobber_count()
        if isinstance(e, fishdata.Junk):
            return self.item_count(e.id) > 0
        return e.id in self.collection.fish


