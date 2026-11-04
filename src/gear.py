# -*- coding: utf-8 -*-
"""钓具和金币：照原版威利钓具店的升级路线，轻量化。

    竹竿 → 玻璃纤维钓竿（钓鱼 2 级，1800g，能挂鱼饵）→ 铱金钓竿（钓鱼 6 级，7500g，能装 1 个浮漂配件）
    鱼饵 5g 一个（10 个一包）；浮漂配件：旋转亮片、陷阱浮标、软木浮标、寻宝者
    金币从哪来：钓到的鱼、种出的作物自动按原版售价卖掉（品质越高越值钱：银 ×1.25、金 ×1.5、铱 ×2）

和原版不同、为了轻量化的地方：配件不会磨损；不用自己去卖东西。
鱼的售价读不到时按难度估一个（原版 1.6 的 Data/Objects 是对象结构，纯 Python 读不了）。
"""

# key, 中文名, 价格, 需要的钓鱼等级, 能不能挂鱼饵, 配件槽数
RODS = [
    ("bamboo", "竹竿", 0, 0, False, 0),
    ("fiberglass", "玻璃纤维钓竿", 1800, 2, True, 0),
    ("iridium", "铱金钓竿", 7500, 6, True, 1),
]
ROD_KEYS = [r[0] for r in RODS]
_ROD = {r[0]: r for r in RODS}

BAIT_PACK, BAIT_PACK_PRICE = 10, 50

# 物品 id -> 英文名, 价格, 效果说明（中文名从游戏读）
TACKLE = {
    "686": ("Spinner", 500, "鱼咬钩更快"),
    "694": ("Trap Bobber", 500, "鱼跑出绿条时，进度掉得慢三分之一"),
    "695": ("Cork Bobber", 750, "绿条变长"),
    "693": ("Treasure Hunter", 750, "宝箱进度不会往回掉"),
}
TACKLE_NAMES = {k: v[0] for k, v in TACKLE.items()}

SPINNER_WAIT = 0.75          # 旋转亮片：等待时间 ×0.75
TRAP_LOSS = 2.0 / 3.0        # 陷阱浮标：掉进度 ×2/3
CORK_BAR = 6                 # 软木浮标：绿条 +6 贴图像素（原版 +24 游戏单位）

QUALITY_PRICE = [1.0, 1.25, 1.5, 2.0]

# 作物原版售价（普通品质）
CROP_PRICES = {"24": 35, "190": 175, "192": 80, "250": 110, "254": 250, "256": 60, "260": 40,
               "262": 25, "270": 50, "272": 60, "276": 320, "278": 80}


def rod_info(key):
    return _ROD.get(key, _ROD["bamboo"])


def rod_name(key):
    return rod_info(key)[1]


def can_bait(key):
    return rod_info(key)[4]


def tackle_slots(key):
    return rod_info(key)[5]


def fish_price(fish, quality=0, prices=None):
    """一条鱼卖多少钱。prices 是从游戏读到的 {id: 售价}；没有就按难度估。"""
    base = (prices or {}).get(fish.id) or getattr(fish, "price", None)
    if not base:
        d = fish.difficulty or 30
        base = max(20, int(round((d * 2.5 - 30) / 5.0)) * 5)
    return int(base * QUALITY_PRICE[max(0, min(3, quality))])


def crop_price(crop_id):
    return CROP_PRICES.get(str(crop_id), 30)


class Gear(object):
    """钓具状态，直接读写存档里的 dict：{"rod", "rods", "tackle", "tackles"}。"""

    def __init__(self, data):
        data.setdefault("rod", "bamboo")
        data.setdefault("rods", ["bamboo"])
        data.setdefault("tackle", None)
        data.setdefault("tackles", [])
        self.data = data

    @property
    def rod(self):
        return self.data["rod"]

    @property
    def tackle(self):
        t = self.data.get("tackle")
        return t if t and tackle_slots(self.rod) > 0 else None

    def owns(self, key):
        return key in self.data["rods"] or key in self.data["tackles"]

    def equip_rod(self, key):
        if key in self.data["rods"]:
            self.data["rod"] = key
            return True
        return False

    def equip_tackle(self, item_id):
        """装上 / 卸下配件（再点一次已装的就卸下）。只有铱金钓竿有槽。"""
        if tackle_slots(self.rod) <= 0 or item_id not in self.data["tackles"]:
            return False
        self.data["tackle"] = None if self.data.get("tackle") == item_id else item_id
        return True

    # MARK: 效果

    def wait_mult(self, baited):
        m = 0.5 if baited else 1.0
        if self.tackle == "686":
            m *= SPINNER_WAIT
        return m

    def bar_bonus(self):
        return CORK_BAR if self.tackle == "695" else 0

    def loss_mult(self):
        return TRAP_LOSS if self.tackle == "694" else 1.0

    def keeps_treasure(self):
        return self.tackle == "693"

    # MARK: 商店

    def shop_state(self, item, level, gold):
        """(状态, 说明)：owned / equipped / buy / locked / poor。"""
        if item in _ROD:
            need, price = rod_info(item)[3], rod_info(item)[2]
            if item in self.data["rods"]:
                return ("equipped" if self.rod == item else "owned"), ""
            if level < need:
                return "locked", "钓鱼 %d 级解锁" % need
            return ("buy" if gold >= price else "poor"), "%dg" % price
        if item == "bait":
            if not can_bait(self.rod):
                return "locked", "要玻璃纤维钓竿才能挂"
            return ("buy" if gold >= BAIT_PACK_PRICE else "poor"), "%dg / %d 个" % (
                BAIT_PACK_PRICE, BAIT_PACK)
        if item in TACKLE:
            price = TACKLE[item][1]
            if item in self.data["tackles"]:
                return ("equipped" if self.tackle == item else "owned"), ""
            if "iridium" not in self.data["rods"]:
                return "locked", "要铱金钓竿才能装"
            return ("buy" if gold >= price else "poor"), "%dg" % price
        return "locked", ""

    def buy(self, item, collection):
        """买东西：扣金币、入手（鱼竿和配件买了就装上）。成功返回 True。"""
        state, _ = self.shop_state(item, collection.level, collection.gold)
        if state != "buy":
            return False
        if item in _ROD:
            collection.gold -= rod_info(item)[2]
            self.data["rods"].append(item)
            self.data["rod"] = item
        elif item == "bait":
            collection.gold -= BAIT_PACK_PRICE
            collection.inventory["685"] = collection.inventory.get("685", 0) + BAIT_PACK
        else:
            collection.gold -= TACKLE[item][1]
            self.data["tackles"].append(item)
            self.data["tackle"] = item
        collection.save()
        return True
