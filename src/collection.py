# -*- coding: utf-8 -*-
"""图鉴存档：每种鱼钓了几条、最大多大、最高品质、在哪钓到，杂物和宝物，钓鱼经验，以及今天的摸鱼战绩。

老存档（第一期以前）读进来时缺的字段一律补默认值，不清空已有记录。
"""
import json
import os
import sys
import time

from . import progression

from .paths import DATA_DIR as APP_SUPPORT, load_json
DEFAULT_PATH = os.path.join(APP_SUPPORT, "collection.json")


class Collection(object):

    def __init__(self, path=None):
        self.path = path or DEFAULT_PATH
        self.fish = {}            # id -> {"count", "max_size", "first", "perfect"}
        self.days = {}            # "YYYY-MM-DD" -> {"caught", "escaped", "junk"}
        self.items = {}           # 杂物 id -> 条数
        self.treasure = {}        # 宝箱开出的东西 id -> 累计个数（图鉴展示用）
        self.inventory = {}       # 手上还有的 id -> 个数（鱼饵会被用掉；种子留给第三期）
        self.xp = 0
        self.crops = {}           # 收获过的作物 id -> 个数
        self.farm = [None, None, None]   # 3 块地：None 或 {"seed", "days"}
        self.farm_gift = ""       # 上次送种子的日期
        self.farm_started = False # 送过新手种子包没有
        self.farm_plan = [None] * 6   # 每块地下次种什么（None = 自动，当季优先）
        self.gold = 0             # 金币：鱼和作物自动按原版售价卖掉
        self.gear = {}            # 钓具：{"rod", "rods", "tackle", "tackles"}（见 gear.py）
        self.load()

    def load(self):
        try:
            data = load_json(self.path)
        except (IOError, OSError, ValueError):
            return
        self.fish = data.get("fish", {})
        self.days = data.get("days", {})
        self.items = data.get("items", {})
        self.treasure = data.get("treasure", {})
        self.inventory = data.get("inventory", {})
        self.xp = int(data.get("xp", 0))
        self.crops = data.get("crops", {})
        self.farm = data.get("farm") or [None, None, None]
        self.farm_gift = data.get("farm_gift", "")
        self.farm_started = bool(data.get("farm_started", False))
        plan = data.get("farm_plan") or []
        self.farm_plan = [(str(plan[i]) if i < len(plan) and plan[i] else None) for i in range(6)]
        self.gold = int(data.get("gold", 0))
        self.gear = data.get("gear") or {}
        for e in self.fish.values():
            e.setdefault("best_quality", 0)
            e.setdefault("spots", [])
            e.setdefault("perfect", 0)

    def save(self):
        try:
            d = os.path.dirname(self.path)
            if d and not os.path.isdir(d):
                os.makedirs(d)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"fish": self.fish, "days": self.days, "items": self.items,
                           "treasure": self.treasure, "inventory": self.inventory,
                           "xp": self.xp, "crops": self.crops, "farm": self.farm,
                           "farm_gift": self.farm_gift, "farm_started": self.farm_started, "farm_plan": self.farm_plan,
                           "gold": self.gold,
                           "gear": self.gear}, fh,
                          ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except (IOError, OSError) as exc:
            sys.stderr.write("[Collection] 保存失败: %s\n" % exc)

    @staticmethod
    def today(t=None):
        return time.strftime("%Y-%m-%d", t or time.localtime())

    def _day(self, t=None):
        day = self.days.setdefault(self.today(t), {"caught": 0, "escaped": 0})
        day.setdefault("junk", 0)
        return day

    # MARK: 等级

    @property
    def level(self):
        return progression.level_for(self.xp)

    def add_xp(self, n):
        """加经验，返回升到的新等级（没升级返回 None）。不单独存盘，跟着这一竿的记录一起存。"""
        before = self.level
        self.xp += max(0, int(n))
        after = self.level
        return after if after > before else None

    # MARK: 记录

    def record_catch(self, fish_id, size, perfect=False, t=None, quality=0, spot=None):
        """记录一条。返回 (是不是新鱼种, 是不是破纪录)。"""
        fish_id = str(fish_id)
        entry = self.fish.get(fish_id)
        is_new = entry is None
        if is_new:
            entry = {"count": 0, "max_size": 0, "perfect": 0, "best_quality": 0, "spots": [],
                     "first": time.strftime("%Y-%m-%d %H:%M", t or time.localtime())}
            self.fish[fish_id] = entry
        record = size > entry["max_size"] and not is_new
        entry["count"] += 1
        entry["max_size"] = max(entry["max_size"], size)
        if perfect:
            entry["perfect"] = entry.get("perfect", 0) + 1
        entry["best_quality"] = max(entry.get("best_quality", 0), int(quality))
        if spot and spot not in entry.setdefault("spots", []):
            entry["spots"].append(spot)
        self._day(t)["caught"] += 1
        self.save()
        return is_new, record

    def record_junk(self, item_id, t=None):
        item_id = str(item_id)
        self.items[item_id] = self.items.get(item_id, 0) + 1
        self._day(t)["junk"] += 1
        self.save()

    def record_treasure(self, items):
        for item_id, n in items:
            item_id = str(item_id)
            self.treasure[item_id] = self.treasure.get(item_id, 0) + n
            self.inventory[item_id] = self.inventory.get(item_id, 0) + n
        self.save()

    def give(self, item_id, n=1):
        item_id = str(item_id)
        self.inventory[item_id] = self.inventory.get(item_id, 0) + n
        self.save()

    def record_harvest(self, crop_id, bait=1, gold=0):
        """收获一个作物：记进图鉴，换鱼饵，按售价卖掉。"""
        crop_id = str(crop_id)
        self.crops[crop_id] = self.crops.get(crop_id, 0) + 1
        self.inventory[progression.BAIT] = self.inventory.get(progression.BAIT, 0) + bait
        self.gold += int(gold)
        self.save()

    def count(self, item_id):
        return self.inventory.get(str(item_id), 0)

    def use_item(self, item_id):
        """用掉一个（比如鱼饵）。没有就返回 False。"""
        item_id = str(item_id)
        if self.inventory.get(item_id, 0) <= 0:
            return False
        self.inventory[item_id] -= 1
        self.save()
        return True

    def record_escape(self, t=None):
        self._day(t)["escaped"] += 1
        self.save()

    def caught_species(self):
        return len(self.fish)

    def total_caught(self):
        return sum(e["count"] for e in self.fish.values())

    def week_stats(self, t=None):
        """本周（周一到今天）累计的钓到 / 跑了 / 杂物。"""
        import datetime
        t = t or time.localtime()
        today = datetime.date(t.tm_year, t.tm_mon, t.tm_mday)
        monday = today - datetime.timedelta(days=today.weekday())
        out = {"caught": 0, "escaped": 0, "junk": 0}
        for key, day in self.days.items():
            try:
                d = datetime.date(*[int(v) for v in key.split("-")])
            except (ValueError, TypeError):
                continue
            if monday <= d <= today:
                for k in out:
                    out[k] += day.get(k, 0)
        return out

    def today_stats(self, t=None):
        day = {"caught": 0, "escaped": 0, "junk": 0}
        day.update(self.days.get(self.today(t), {}))
        return day
