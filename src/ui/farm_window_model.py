# -*- coding: utf-8 -*-
"""「我的农田」窗口里选种子的部分（Mac / Windows 共用，和平台无关）。"""
from .. import farm as farmlib

S = 3                         # 像素放大倍数
PLOT = 16 * S                 # 一块地 48 点
GAP = 28
PAD = 26
PLOTS_W = farmlib.PLOTS * PLOT + (farmlib.PLOTS - 1) * GAP
CARD_W = PLOTS_W + PAD * 2
CARD_H = 230                  # 一排地时卡片的高度
DIRT_Y = 86
CARD_PITCH = 124              # 扩建成两排后：卡片里两排地的间距（作物比地高一截）
WIN_PITCH = 150               # 「我的农田」窗口里两排地的间距（多一行「下次：…」）

PLAN_H = 26                   # 每块地下面的「下次：自动」
CHOOSER_H = 140               # 窗口底部选种子的那一块（最多两排）
WIN_W = 360                   # 「我的农田」窗口比弹出的小卡片宽，选种子那一排放得下
ICON = 36


def plan_label(collection, plot, name_of):
    seed = collection.farm_plan[plot]
    if not seed or seed not in farmlib.CROPS:
        return "下次：自动"
    return "下次：%s" % name_of(farmlib.CROPS[seed][1])


def chooser_items(collection):
    """可以选的：自动 + 手上有的种子。"""
    return [None] + [s for s in sorted(farmlib.CROPS) if collection.count(s) > 0]


def plot_rect(i, ox=0, pitch=CARD_PITCH):
    """第 i 块地在卡片 / 窗口里的位置：一排 3 块，扩建后第二排在下面。"""
    row, col = divmod(i, farmlib.PLOTS)
    return ox + PAD + col * (PLOT + GAP), DIRT_Y + row * pitch, PLOT, PLOT


def card_h(rows):
    return CARD_H + (rows - 1) * CARD_PITCH


def win_h(rows):
    return CARD_H + PLAN_H + CHOOSER_H + (rows - 1) * WIN_PITCH


def lines_y(rows, pitch):
    """地下面那几行字从哪里开始。"""
    return DIRT_Y + (rows - 1) * pitch + PLOT + 28


# MARK: 桌面农田摆件（没有底、没有框：后排木栅栏 + 连成一片的锄地 + 作物）

DESK_SCALE = 3
DESK_TILE = 16 * DESK_SCALE
DESK_COLS = 3                        # 和游戏里一样：三块连着的锄地，后面一排木栅栏
SOIL_Y = int(DESK_TILE * 1.7)        # 第一排锄地的上沿（栅栏在它后面）
FARM_W = DESK_COLS * DESK_TILE
DESK_PAD_X = 70                      # 左右留点地方，下面那行进度字放得下
DESK_W = FARM_W + DESK_PAD_X * 2
CAPTION_H = 24
POP_SECONDS = 2.2                    # 收获时作物图标往上冒的时间


def desk_h(rows):
    return SOIL_Y + rows * DESK_TILE + 4 + CAPTION_H


def desk_plot_xy(i):
    """第 i 块地在摆件里的左上角（锄地那一格）。"""
    row, col = divmod(i, DESK_COLS)
    return DESK_PAD_X + col * DESK_TILE, SOIL_Y + row * DESK_TILE


def desk_tiles(rows):
    """每块地用哪张锄地贴图：[(干的, 浇过水的)]。一排是横条，两排是 3×2 连成一片。"""
    cols = ("l", "m", "r")
    if rows <= 1:
        return [("dirt_" + c, "dirt_w" + c) for c in cols]
    return [("dirt2_%s%s" % (r, c), "dirt2_w%s%s" % (r, c)) for r in ("t", "b") for c in cols]


def caption_y(rows):
    return SOIL_Y + rows * DESK_TILE + 6
