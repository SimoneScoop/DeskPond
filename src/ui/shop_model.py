# -*- coding: utf-8 -*-
"""钓具店里「种子」那一栏的文字（Mac / Windows 共用）。"""
from .. import farm as farmlib
from .. import gear as gearlib

PAGES = [("gear", "钓具"), ("seeds", "种子")]
TAB_W, TAB_H = 84, 34
SEASON_ZH = {"spring": "春季", "summer": "夏季", "fall": "秋季", "winter": "冬季"}
WINTER_NOTE = "冬天皮埃尔不卖作物种子。春天再来，或者等宝箱开出来。"
SEED_HINT = "买来的种子会自动种进空地；想指定种哪块，去「我的农田」点那块地。"


def title(page):
    return "钓具店" if page == "gear" else "种子 · 皮埃尔杂货店"


def seed_desc(seed, collection):
    """种子那一行的小字：几天成熟、能卖多少、手上有几包。"""
    harvest = farmlib.CROPS[seed][1]
    return "%s · %d 天成熟 · 收获卖 %dg · 手上 %d 包" % (
        SEASON_ZH[farmlib.SEED_SEASON[seed]], farmlib.days_to_grow(seed),
        gearlib.crop_price(harvest), collection.count(seed))


EXPAND_NAME = "扩建农田"
EXPAND_DESC = "再开一排，变成 2 排 6 块地 · 要钓鱼 %d 级"


def expand_button(collection):
    """(按钮上的字, 能不能点)。"""
    state, note = farmlib.expand_state(collection)
    return {"done": ("已扩建", False), "locked": (note, False),
            "poor": ("钱不够 · " + note, False), "buy": ("扩建 · " + note, True)}[state]
