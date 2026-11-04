# -*- coding: utf-8 -*-
"""界面布局的纯计算（不依赖 Cocoa），macOS 界面和 tools/preview.py 共用，方便测试和出预览图。

坐标都是翻转坐标（y 向下），单位是屏幕点。竖条框内的位置按贴图像素量过：
    蓝色轨道 x 17–25、y 3–141；右侧进度槽 x 32–35、y 4–145。
"""
from .. import minigame

PANEL_W, PANEL_H = 38, 150
TRACK_X, TRACK_W = 17, 9
FISH_DRAW = 10                   # 鱼图标 20px，按半倍画
PROG_X, PROG_W, PROG_TOP, PROG_BOTTOM = 32, 4, 4, 145

POND_HEIGHT = 110                # 水面默认高度（点）
POND_MIN, POND_MAX = 60, 240     # 拖动手柄能调的范围
POND_HEADROOM = 64               # 水面上方留给「！」的透明空间
HANDLE_ZONE = 10                 # 水面顶边上下这么多点内按下 = 拖动调高度
HEIGHT_PRESETS = [("低", 70), ("中", 110), ("高", 180)]
WIDTH_MODES = [("full", "通栏"), ("half", "半屏（靠右）"), ("corner", "角落（右下）")]
CORNER_W = 420
OPACITIES = [(1.0, "100%"), (0.8, "80%"), (0.6, "60%")]
WATER_TILE = 64                  # 水面每帧 64x64
WATER_SCALE = 2
WATER_FRAME_SECONDS = 0.15
WATER_DRIFT = 10.0               # 水面每秒漂移多少点

EXCLAIM_FRAME = 16
EXCLAIM_SCALE = 3


def clamp_height(h):
    try:
        h = float(h)
    except (TypeError, ValueError):
        return POND_HEIGHT
    return max(POND_MIN, min(POND_MAX, h))


def pond_span(x, width, mode):
    """水面在屏幕上的横向范围 (x, 宽)。半屏和角落都靠右，不挡左边常用的窗口。"""
    if mode == "half":
        w = width / 2.0
    elif mode == "corner":
        w = min(width, CORNER_W)
    else:
        w = width
    return x + width - w, w


def depth_rel(y, top, bottom):
    """翻转坐标里点击的 y -> 在水里的相对高度（0 = 水面上沿，1 = 屏幕底边）。"""
    if bottom <= top:
        return 0.5
    return max(0.0, min(1.0, (y - top) / float(bottom - top)))


def near_handle(y, top):
    return abs(y - top) <= HANDLE_ZONE


def panel_scale(screen_height, pond_height=POND_HEIGHT):
    """竖条框放大倍数：屏幕够高用 3 倍（450 点），否则 2 倍。"""
    need = PANEL_H * 3 + pond_height + 40
    return 3 if screen_height >= need else 2


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def water_top(level, height=POND_HEIGHT):
    """水面顶端在水面区域里的 y（0 = 完全升起）。"""
    return height * (1.0 - ease_out(level))


def water_frame(t):
    return int(t / WATER_FRAME_SECONDS) % 10


def water_tiles(width, t):
    """横向铺水面：返回每块的 x（会慢慢漂）。"""
    size = WATER_TILE * WATER_SCALE
    offset = (t * WATER_DRIFT) % size
    xs = []
    x = -offset
    while x < width:
        xs.append(x)
        x += size
    return xs


BOBBER_SCALE = 3                 # 原版浮漂 16x16（1.6 浮漂表），放大 3 倍


def bobber_y(cast_y, top, bottom):
    """浮漂落点的 y：点在水里哪个高度，浮漂就落在哪（上下各留一点边）。"""
    lo, hi = top + 20, bottom - 14
    if hi < lo:
        hi = lo
    return lo + (hi - lo) * max(0.0, min(1.0, cast_y))


def bobber_pos(cast_x, width, top, t, bite=False, cast_y=0.0, bottom=None):
    """浮漂位置：落在点击处，随波上下晃，咬钩时往下沉。"""
    import math
    x = cast_x * width
    y = bobber_y(cast_y, top, bottom if bottom is not None else top + POND_HEIGHT)
    y += math.sin(t * 2.2) * 1.5
    if bite:
        y += 4 + math.sin(t * 30) * 2.0
    return x, y


def exclaim_frame(since):
    return min(3, int(since / 0.08))


def bar_rect(game, s):
    y = (minigame.TRACK_TOP + game.bar_pos) * s
    return TRACK_X * s, y, TRACK_W * s, game.bar_height * s


def fish_rect(game, s, shake=0.0):
    x = (TRACK_X + TRACK_W / 2.0 - FISH_DRAW / 2.0 + shake) * s
    y = (minigame.TRACK_TOP + game.fish_pos) * s
    return x, y, FISH_DRAW * s, FISH_DRAW * s


CHEST_DRAW_W, CHEST_DRAW_H = 10, 12   # 宝箱贴图 20x24，按半倍画进轨道


def treasure_rect(game, s):
    """宝箱在竖条里的位置（翻转坐标）。"""
    cy = minigame.TRACK_TOP + game.treasure_pos + minigame.TREASURE_SIZE / 2.0
    x = TRACK_X + TRACK_W / 2.0 - CHEST_DRAW_W / 2.0
    return x * s, (cy - CHEST_DRAW_H / 2.0) * s, CHEST_DRAW_W * s, CHEST_DRAW_H * s


def treasure_progress_rect(game, s):
    x, y, w, h = treasure_rect(game, s)
    return x, y + h + 1 * s, w * max(0.0, min(1.0, game.treasure_progress)), 1.5 * s


def progress_rect(progress, s):
    full = PROG_BOTTOM - PROG_TOP
    h = full * max(0.0, min(1.0, progress))
    return PROG_X * s, (PROG_BOTTOM - h) * s, PROG_W * s, h * s


def progress_color(progress):
    """红 → 黄 → 绿，和原版一样。"""
    p = max(0.0, min(1.0, progress))
    return (int(255 * min(1.0, 2 * (1 - p))), int(255 * min(1.0, 2 * p)), 0)


def bar_alpha(in_bar, t):
    """鱼不在绿条里时绿条变淡、闪烁。"""
    import math
    if in_bar:
        return 1.0
    return 0.45 + 0.25 * math.sin(t * 10)


def panel_origin(cast_x, screen_w, s, margin=12):
    """竖条框在屏幕上的 x：对准浮漂，但不出屏。"""
    w = PANEL_W * s
    x = cast_x * screen_w - w / 2.0
    return max(margin, min(screen_w - w - margin, x))


# MARK: 字号

TEXT_BOOST = 1.5            # 小字统一放大一点（13 号以下 +1.5，大字 +1），上班时扫一眼也看得清


def readable(size):
    return size + (TEXT_BOOST if size < 14 else 1.0)


# MARK: 水面中间的操作提示（渐进式：新手时完整，熟了只留水深这类有用信息）

NOVICE_SPECIES = 3          # 图鉴收集到这么多种之前算新手


def default_hint(sess):
    from .. import session as S
    novice = getattr(sess, "novice", True)
    if sess.state == S.IDLE:
        return "点一下水面抛竿 · 越靠上水越深" if novice else ""
    if sess.state == S.WAITING:
        extra = " · 挂了鱼饵" if sess.baited else ""
        if novice:
            return "等鱼咬钩……看到「！」再点 · 水深 %d%s" % (sess.depth, extra)
        return "水深 %d%s" % (sess.depth, extra)
    if sess.state == S.PLAYING:
        return "按住鼠标，让绿条罩住小鱼" if novice else ""
    return ""
