# -*- coding: utf-8 -*-
"""从本机安装的《星露谷物语》读取钓鱼要用的素材（和游戏 mod 一样的做法）。

仓库里不带任何游戏图片或数据。首次启动时从游戏读取：
    LooseSprites/Cursors     钓鱼竖条框、绿条、鱼图标、水面纹理
    Maps/springobjects       每种鱼的物品图标
    TileSheets/emotes        咬钩时的「！」
    Data/Fish                鱼的难度、行为、尺寸、出没时段和季节
    Strings/Objects(.zh-CN)  鱼的中文名（1.6+）；老版本用 Data/ObjectInformation.zh-CN
切好后缓存到数据目录下的 game_cache/（见 paths.py），之后只校验是否过期。

两种来源都支持，优先解包后的文件：StardewXnbHack 导出的「Content (unpacked)」
（图片是 .png、数据是 .json），或游戏原生的 .xnb（纯 Python 解 LZX）。
"""
import json
import os
import shutil
import sys

from . import png, xnb

CACHE_VERSION = 13         # 12：一小一大两套中文字体；13：缓存统一 UTF-8（老缓存在中文 Windows 上可能是 GBK）
                           # 11：两排连着的锄地（农田扩建后）
                           # 10：浇过水的锄地（桌面农田专注时用）
                           # 9：原版位图字体（Fonts）、番茄图标
                           # 8：桌面农田（草地/栅栏/稻草人）、鱼竿图标、关闭按钮、配件图标和中文名
from .. import paths as _paths
from ..paths import DATA_DIR as APP_SUPPORT
CACHE_ROOT = os.path.join(APP_SUPPORT, "game_cache")
ENV_GAME_DIR = "DESKPOND_GAME_DIR"
OLD_ENV_GAME_DIR = "MOYU_GAME_DIR"      # 改名前（摸鱼钓鱼 / MoyuFishing）的环境变量，仍然认

CANDIDATE_GAME_DIRS = [
    "~/Library/Application Support/Steam/steamapps/common/Stardew Valley",
    "/Applications/Stardew Valley.app",
    "~/Applications/Stardew Valley.app",
    "~/Library/Application Support/GOG.com/Games/Stardew Valley",
    "~/.local/share/Steam/steamapps/common/Stardew Valley",
    # Windows：Steam / GOG / Xbox App 的常见位置（其他盘的 Steam 库由 _steam_libraries() 补上）
    "C:/Program Files (x86)/Steam/steamapps/common/Stardew Valley",
    "C:/Program Files/Steam/steamapps/common/Stardew Valley",
    "C:/Program Files (x86)/GOG Galaxy/Games/Stardew Valley",
    "C:/GOG Games/Stardew Valley",
    "C:/XboxGames/Stardew Valley/Content",
]


def _steam_libraries():
    """Windows 上 Steam 可以把游戏装在别的盘：读 libraryfolders.vdf 找出所有库。"""
    if not sys.platform.startswith("win"):
        return []
    roots = []
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            roots.append(os.path.join(base, "Steam"))
    out = []
    for steam in roots:
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except (IOError, OSError):
            continue
        import re
        for path in re.findall(r'"path"\s+"([^"]+)"', text):
            out.append(os.path.join(path.replace("\\\\", "\\"), "steamapps", "common",
                                    "Stardew Valley"))
    return out

# Cursors 里钓鱼界面的位置（x, y, w, h），对照 1.5 / 1.6 贴图量过
CURSOR_RECTS = {
    "panel":    (644, 1999, 38, 150),   # 竖条框
    "bar_top":  (682, 2078, 9, 2),      # 绿条上端
    "bar_mid":  (682, 2081, 9, 1),      # 绿条中段（纵向拉伸）
    "bar_bot":  (682, 2085, 9, 2),      # 绿条下端
    "fish":     (614, 1840, 20, 20),    # 竖条里游动的小鱼
    "water":    (0, 2064, 640, 64),     # 水面动画：10 帧 64x64，每帧都能无缝平铺
}
# 可选的贴图：切不到（版本不同、格子是空的）就退回代码画的样子。坐标对照 1.6 原图量过
OPTIONAL_RECTS = {
    "chest":    (639, 1865, 20, 24),    # 溜鱼时的宝箱
    # 图鉴用的原版菜单零件（对照 1.6 Cursors 量过）
    "textbox":  (384, 373, 18, 18),     # 悬停说明框（九宫格，四角各 6 像素）
    "tab":      (16, 368, 16, 16),      # 菜单标签（空白）
    "tab_fish": (32, 384, 16, 16),      # 收藏「鱼」标签
    "tab_vase": (80, 368, 16, 16),      # 收藏标签（罐子）
    "star_1":   (338, 400, 8, 8),       # 银星
    "star_2":   (346, 400, 8, 8),       # 金星
    "star_3":   (346, 392, 8, 8),       # 铱星
    "arrow_l":  (352, 495, 12, 11),     # 翻页箭头
    "arrow_r":  (365, 495, 12, 11),
    "close":    (337, 494, 12, 12),     # 原版菜单右上角的关闭按钮（红叉）
}
# 其他贴图里的零件：(贴图名, x, y, w, h)
EXTRA_SPRITES = {
    "tomato":   ("Maps/springobjects", 256, 160, 16, 16),   # 番茄（物品 256）：番茄钟的图标
    "dirt":     ("TerrainFeatures/hoeDirt", 0, 0, 16, 16),  # 锄过的地（单独一块，对照 1.6 原图）
    "dirt_l":   ("TerrainFeatures/hoeDirt", 16, 48, 16, 16), # 横着连成一条：左端
    "dirt_m":   ("TerrainFeatures/hoeDirt", 32, 48, 16, 16), #                中间
    "dirt_r":   ("TerrainFeatures/hoeDirt", 48, 48, 16, 16), #                右端
    "dirt_wl":  ("TerrainFeatures/hoeDirt", 80, 48, 16, 16), # 浇过水的（hoeDirt 第二块 64x64）
    "dirt_wm":  ("TerrainFeatures/hoeDirt", 96, 48, 16, 16),
    "dirt_wr":  ("TerrainFeatures/hoeDirt", 112, 48, 16, 16),
    # 扩建后 2 排 × 3 块连成一片：取 3×3 那块的上一行和下一行（干的 / 浇过水的 +64）
    **{"dirt2_%s%s%s" % (w, r, c): ("TerrainFeatures/hoeDirt", sx + (64 if w else 0), sy, 16, 16)
       for w in ("", "w") for r, sy in (("t", 0), ("b", 32)) for c, sx in (("l", 16), ("m", 32), ("r", 48))},
    # 以下都对照 1.6 原图量过
    "fence_l":  ("LooseSprites/Fence1", 0, 64, 16, 32),       # 木栅栏：横着连起来的左端
    "fence_m":  ("LooseSprites/Fence1", 16, 64, 16, 32),      #          中间
    "fence_r":  ("LooseSprites/Fence1", 32, 64, 16, 32),      #          右端
    "rod_bamboo": ("TileSheets/tools", 128, 0, 16, 16),       # 竹竿
    "rod_fiberglass": ("TileSheets/tools", 160, 0, 16, 16),   # 玻璃纤维钓竿
    "rod_iridium": ("TileSheets/tools", 176, 0, 16, 16),      # 铱金钓竿
}
# 1.6 的浮漂样式表 TileSheets/bobbers：每格 16x32，上半是空中的浮漂，下半是浮在水里的（带倒影）。
# 原版共 39 种，每多钓到 2 种鱼解锁一种（钓鱼店的浮漂机）。1.5 没有这张表，用代码画的浮漂。
BOBBER_CELL_W, BOBBER_CELL_H = 16, 32
BOBBER_STYLES = 39
WATER_FRAMES = 10
EMOTE_ROW_EXCLAIM = 4        # emotes 表第 4 行是「！」，4 帧弹出动画
OBJECT_TILE = 16
OBJECT_COLS = 24             # springobjects 每行 24 格


class GameNotFound(Exception):
    pass


class AssetMissing(Exception):
    pass


# MARK: 找游戏

def _looks_like_content(path):
    return os.path.isdir(os.path.join(path, "LooseSprites")) and \
        os.path.isdir(os.path.join(path, "Data"))


def normalize(path):
    if not path:
        return []
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        return []
    found = []
    for base in (path, os.path.join(path, "Contents", "Resources")):
        for sub in ("Content (unpacked)", "Content", ""):
            cand = os.path.join(base, sub) if sub else base
            if cand not in found and _looks_like_content(cand):
                found.append(cand)
    return found


def find_content_dirs(explicit=None):
    sources = []
    if explicit:
        sources.append(explicit)
    for env in (ENV_GAME_DIR, OLD_ENV_GAME_DIR):
        if os.environ.get(env):
            sources.append(os.environ[env])
    sources += CANDIDATE_GAME_DIRS + _steam_libraries()
    dirs = []
    for src in sources:
        for d in normalize(src):
            if d not in dirs:
                dirs.append(d)
    return dirs


def resolve(name, content_dirs, exts):
    rel = name.replace("\\", "/").strip("/").split("/")
    for d in content_dirs:
        for ext in exts:
            p = os.path.join(d, *rel) + ext
            if os.path.isfile(p):
                return p
    return None


# MARK: 读贴图 / 数据

def load_texture(name, content_dirs):
    path = resolve(name, content_dirs, (".png", ".xnb"))
    if not path:
        raise AssetMissing("找不到贴图 %s" % name)
    if path.endswith(".xnb"):
        t = xnb.load_texture(path)
        return t.width, t.height, t.rgba, path
    w, h, rgba = png.read_rgba(path)
    return w, h, rgba, path


def load_dict(name, content_dirs, required=True):
    """数据表：解包目录里是 .json，原生是 .xnb。"""
    path = resolve(name, content_dirs, (".json", ".xnb"))
    if not path:
        if required:
            raise AssetMissing("找不到数据 %s" % name)
        return None, None
    if path.endswith(".json"):
        with open(path, "rb") as fh:
            return json.loads(fh.read().decode("utf-8-sig")), path
    return xnb.load_string_dict(path), path


def crop(rgba, width, x, y, w, h):
    out = bytearray()
    for row in range(y, y + h):
        start = (row * width + x) * 4
        out += rgba[start:start + w * 4]
    return bytes(out)


def silhouette(rgba, shade=(52, 38, 50), alpha=0.75):
    """没钓到的鱼在图鉴里显示成剪影。"""
    out = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        a = rgba[i + 3]
        if a:
            out[i:i + 4] = bytes((shade[0], shade[1], shade[2], int(a * alpha)))
    return bytes(out)


def chinese_names(content_dirs):
    """英文名 -> 中文名。

    1.6+：Strings/Objects 里是 `Pufferfish_Name -> Pufferfish`，中文版同 key。
          先用英文表反查 key，再去中文表取，不依赖 key 的拼法规律。
    1.5 及以前：Data/ObjectInformation(.zh-CN)，第 0 段英文名、第 4 段显示名。
    """
    en, _ = load_dict("Strings/Objects", content_dirs, required=False)
    zh, _ = load_dict("Strings/Objects.zh-CN", content_dirs, required=False)
    names = {}
    if en and zh:
        for key, value in en.items():
            if key.endswith("_Name") and key in zh and value:
                names.setdefault(value, zh[key])
        if names:
            return names
    info, _ = load_dict("Data/ObjectInformation", content_dirs, required=False)
    info_zh, _ = load_dict("Data/ObjectInformation.zh-CN", content_dirs, required=False)
    if info and info_zh:
        for oid, raw in info.items():
            zraw = info_zh.get(oid)
            if not zraw:
                continue
            en_name = raw.split("/")[0]
            parts = zraw.split("/")
            if len(parts) > 4 and parts[4]:
                names.setdefault(en_name, parts[4])
    return names


def descriptions(content_dirs):
    """英文名 -> 游戏里的中文物品描述（图鉴详情用，钓到后才显示）。"""
    en, _ = load_dict("Strings/Objects", content_dirs, required=False)
    zh, _ = load_dict("Strings/Objects.zh-CN", content_dirs, required=False)
    out = {}
    if en and zh:
        for key, value in en.items():
            if key.endswith("_Name") and value:
                d = zh.get(key[:-5] + "_Description")
                if d:
                    out.setdefault(value, d)
        if out:
            return out
    info, _ = load_dict("Data/ObjectInformation", content_dirs, required=False)
    info_zh, _ = load_dict("Data/ObjectInformation.zh-CN", content_dirs, required=False)
    if info and info_zh:
        for oid, raw in info.items():
            parts = (info_zh.get(oid) or "").split("/")
            if len(parts) > 5 and parts[5]:
                out.setdefault(raw.split("/")[0], parts[5])
    return out


def sell_prices(content_dirs):
    """物品 id -> 原版售价。1.5 的 Data/ObjectInformation 第 2 段；1.6 解包后的 Data/Objects 的 Price。
    1.6 原生 .xnb 读不了就返回空，售价按难度估。"""
    out = {}
    for name in ("Data/ObjectInformation", "Data/Objects"):
        try:
            table, _ = load_dict(name, content_dirs, required=False)
        except Exception:
            table = None
        if not table:
            continue
        for oid, raw in table.items():
            try:
                price = int(raw.split("/")[1]) if isinstance(raw, str) else int(raw.get("Price", 0))
            except (ValueError, IndexError, AttributeError, TypeError):
                continue
            if price > 0:
                out[str(oid)] = price
        if out:
            break
    return out


# MARK: 缓存

def cache_dir():
    return CACHE_ROOT


def _stamp_path():
    return os.path.join(CACHE_ROOT, "stamp.json")


def _sources(content_dirs):
    fp = {}
    for name, exts in (("LooseSprites/Cursors", (".png", ".xnb")),
                       ("Maps/springobjects", (".png", ".xnb")),
                       ("TileSheets/emotes", (".png", ".xnb")),
                       ("TileSheets/bobbers", (".png", ".xnb")),
                       ("TileSheets/crops", (".png", ".xnb")),
                       ("Data/Crops", (".json", ".xnb")),
                       ("Maps/MenuTiles", (".png", ".xnb")),
                       ("TerrainFeatures/hoeDirt", (".png", ".xnb")),
                       ("LooseSprites/Fence1", (".png", ".xnb")),
                       ("TileSheets/tools", (".png", ".xnb")),
                       ("Data/Fish", (".json", ".xnb")),
                       ("Strings/Objects.zh-CN", (".json", ".xnb"))) + tuple(
                           (n, (".xnb",)) for n in FONT_CANDIDATES):
        p = resolve(name, content_dirs, exts)
        if p:
            st = os.stat(p)
            fp[name] = [p, int(st.st_mtime), st.st_size]
        else:
            fp[name] = None
    return fp


def cache_is_fresh(content_dirs=None):
    try:
        stamp = _paths.load_json(_stamp_path())
    except (IOError, OSError, ValueError):
        return False
    if stamp.get("version") != CACHE_VERSION:
        return False
    if content_dirs and stamp.get("sources") != _sources(content_dirs):
        return False
    return os.path.isfile(os.path.join(CACHE_ROOT, "fish.json"))


def build_cache(content_dirs, log=None):
    from .. import fishdata
    log = log or print          # 不用 sys.stdout.write：Windows 打包版（无控制台）里 sys.stdout 是 None
    log("[素材] 读取自: %s" % content_dirs[0])
    tmp = CACHE_ROOT + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "ui"))
    os.makedirs(os.path.join(tmp, "fish"))
    os.makedirs(os.path.join(tmp, "junk"))

    w, h, rgba, src = load_texture("LooseSprites/Cursors", content_dirs)
    log("  Cursors %dx%d <- %s" % (w, h, src))
    for key, (x, y, cw, ch) in CURSOR_RECTS.items():
        if x + cw > w or y + ch > h:
            raise AssetMissing("Cursors 贴图尺寸不对，找不到 %s" % key)
        png.write_rgba(os.path.join(tmp, "ui", key + ".png"), cw, ch, crop(rgba, w, x, y, cw, ch))
    for key, (x, y, cw, ch) in OPTIONAL_RECTS.items():
        if x + cw > w or y + ch > h:
            log("  ⚠️  Cursors 里没有 %s，用代码画" % key)
            continue
        part = crop(rgba, w, x, y, cw, ch)
        if not any(part[3::4]):
            log("  ⚠️  Cursors 的 %s 位置是空的，用代码画" % key)
            continue
        png.write_rgba(os.path.join(tmp, "ui", key + ".png"), cw, ch, part)

    for key, (tex, x, y, cw, ch) in EXTRA_SPRITES.items():
        try:
            tw, th, trgba, _ = load_texture(tex, content_dirs)
        except AssetMissing:
            log("  ⚠️  没有 %s，%s 用代码画" % (tex, key))
            continue
        if x + cw <= tw and y + ch <= th:
            part = crop(trgba, tw, x, y, cw, ch)
            if any(part[3::4]):
                png.write_rgba(os.path.join(tmp, "ui", key + ".png"), cw, ch, part)

    styles = 0
    try:
        bw, bh, brgba, src = load_texture("TileSheets/bobbers", content_dirs)
        cols = bw // BOBBER_CELL_W
        for i in range(min(BOBBER_STYLES, cols * (bh // BOBBER_CELL_H))):
            x, y = (i % cols) * BOBBER_CELL_W, (i // cols) * BOBBER_CELL_H
            air = crop(brgba, bw, x, y, BOBBER_CELL_W, 16)
            water = crop(brgba, bw, x, y + 16, BOBBER_CELL_W, 16)
            if not any(water[3::4]):
                break
            png.write_rgba(os.path.join(tmp, "ui", "bobber_%d.png" % i), 16, 16, water)
            png.write_rgba(os.path.join(tmp, "ui", "bobber_icon_%d.png" % i), 16, 16, air)
            png.write_rgba(os.path.join(tmp, "ui", "bobber_icon_%d_s.png" % i), 16, 16,
                           silhouette(air))
            styles = i + 1
        log("  浮漂样式 %d 种 <- %s" % (styles, src))
    except AssetMissing:
        log("  ⚠️  没有 TileSheets/bobbers（1.5 及以前），浮漂用代码画")

    _cache_crops(tmp, content_dirs, log)
    _cache_font(tmp, content_dirs, log)

    try:
        ew, eh, erga, _ = load_texture("TileSheets/emotes", content_dirs)
        y = EMOTE_ROW_EXCLAIM * 16
        png.write_rgba(os.path.join(tmp, "ui", "exclaim.png"), 64, 16, crop(erga, ew, 0, y, 64, 16))
    except AssetMissing:
        log("  ⚠️  没有 emotes，咬钩时用文字「！」代替")

    table, src = load_dict("Data/Fish", content_dirs)
    log("  Data/Fish %d 条 <- %s" % (len(table), src))
    names = chinese_names(content_dirs)
    log("  中文名 %d 个" % len(names))
    fish = fishdata.parse_table(table, names_zh=names)
    descs = descriptions(content_dirs)
    prices = sell_prices(content_dirs)
    for f in fish:
        f.desc = descs.get(f.name)
        f.price = prices.get(f.id)

    sw, sh, srgba, src = load_texture("Maps/springobjects", content_dirs)
    kept = []
    for f in fish:
        if not f.id.isdigit():
            continue          # 1.6 新增的非数字 id 鱼，图标不在 springobjects 里
        idx = int(f.id)
        x, y = (idx % OBJECT_COLS) * OBJECT_TILE, (idx // OBJECT_COLS) * OBJECT_TILE
        if y + OBJECT_TILE > sh:
            continue
        tile = crop(srgba, sw, x, y, OBJECT_TILE, OBJECT_TILE)
        if not any(tile[3::4]):
            continue          # 空格子，说明这个版本的贴图布局不一样
        png.write_rgba(os.path.join(tmp, "fish", f.id + ".png"), OBJECT_TILE, OBJECT_TILE, tile)
        png.write_rgba(os.path.join(tmp, "fish", f.id + "_s.png"), OBJECT_TILE, OBJECT_TILE,
                       silhouette(tile))
        kept.append(f)
    with open(os.path.join(tmp, "fish.json"), "w", encoding="utf-8") as fh:
        json.dump([f.to_dict() for f in kept], fh, ensure_ascii=False, indent=1)
    log("  可钓的鱼 %d 种" % len(kept))

    items = []
    for jid, en in sorted(item_names().items()):
        idx = int(jid)
        x, y = (idx % OBJECT_COLS) * OBJECT_TILE, (idx // OBJECT_COLS) * OBJECT_TILE
        if y + OBJECT_TILE <= sh:
            tile = crop(srgba, sw, x, y, OBJECT_TILE, OBJECT_TILE)
            png.write_rgba(os.path.join(tmp, "junk", jid + ".png"), OBJECT_TILE, OBJECT_TILE, tile)
            png.write_rgba(os.path.join(tmp, "junk", jid + "_s.png"), OBJECT_TILE, OBJECT_TILE,
                           silhouette(tile))
        items.append(fishdata.Junk(jid, en, names.get(en)).to_dict())
    with open(os.path.join(tmp, "junk.json"), "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)

    with open(os.path.join(tmp, "stamp.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": CACHE_VERSION, "sources": _sources(content_dirs),
                   "bobber_styles": styles}, fh, indent=1)
    shutil.rmtree(CACHE_ROOT, ignore_errors=True)
    os.rename(tmp, CACHE_ROOT)
    log("[素材] 已缓存到 %s" % CACHE_ROOT)
    from ..ui import bitfont          # 字体可能换了：下次画字时重新读
    bitfont.reset()
    return CACHE_ROOT


def ensure_cache(game_dir=None, force=False, log=None):
    dirs = find_content_dirs(game_dir)
    if not force and cache_is_fresh(dirs):
        return CACHE_ROOT
    if not dirs:
        if not force and os.path.isfile(os.path.join(CACHE_ROOT, "fish.json")):
            return CACHE_ROOT
        raise GameNotFound("没找到《星露谷物语》的游戏目录")
    return build_cache(dirs, log=log)


def load_fish_list():
    from .. import fishdata
    with open(os.path.join(CACHE_ROOT, "fish.json"), encoding="utf-8") as fh:
        return [fishdata.Fish.from_dict(d) for d in json.load(fh)]


def item_names():
    """杂物和宝物：id -> 英文名（中文名、图标从游戏读）。"""
    from .. import farm, fishdata, progression
    names = dict(fishdata.JUNK_NAMES)
    names.update(progression.TREASURE_NAMES)
    names.update(farm.CROP_NAMES)
    from .. import gear
    names.update(gear.TACKLE_NAMES)
    return names


def load_junk():
    """杂物和宝物 id -> Junk（带中文名）。老缓存里没有就只用英文名。"""
    from .. import fishdata
    try:
        with open(os.path.join(CACHE_ROOT, "junk.json"), encoding="utf-8") as fh:
            items = [fishdata.Junk.from_dict(d) for d in json.load(fh)]
    except (IOError, OSError, ValueError):
        items = []
    out = {j.id: j for j in items}
    for jid, en in item_names().items():
        out.setdefault(jid, fishdata.Junk(jid, en))
    return out


load_items = load_junk


def junk_icon_path(item_id, shadow=False):
    return os.path.join(CACHE_ROOT, "junk", str(item_id) + ("_s.png" if shadow else ".png"))


def _cache_crops(tmp, content_dirs, log):
    """作物表 + 每种作物的 8 帧生长图（TileSheets/crops 里一行两种作物，每帧 16x32）。"""
    from .. import farm
    raw = None
    try:
        raw, _ = load_dict("Data/Crops", content_dirs, required=False)
    except Exception as exc:          # 1.6 原生 .xnb 是对象结构，纯 Python 读不了，用手工表
        log("  Data/Crops 读不了（%s），用内置作物表" % exc.__class__.__name__)
    table = farm.crop_table(raw)
    os.makedirs(os.path.join(tmp, "crops"))
    with open(os.path.join(tmp, "crops.json"), "w", encoding="utf-8") as fh:
        json.dump({k: list(v) for k, v in table.items()}, fh, ensure_ascii=False, indent=1)
    try:
        cw, ch, crgba, src = load_texture("TileSheets/crops", content_dirs)
    except AssetMissing:
        log("  ⚠️  没有 TileSheets/crops，作物用代码画")
        return
    n = 0
    for seed, (_, _, row, _) in table.items():
        x = 128 if row % 2 else 0
        y = (row // 2) * farm.CROP_FRAME_H
        if x + 128 > cw or y + farm.CROP_FRAME_H > ch:
            continue
        png.write_rgba(os.path.join(tmp, "crops", seed + ".png"), 128, farm.CROP_FRAME_H,
                       crop(crgba, cw, x, y, 128, farm.CROP_FRAME_H))
        n += 1
    log("  作物 %d 种 <- %s" % (n, src))


# MARK: 原版位图字体

# 菜单 / 说明框用的中文 SpriteFont：小的（SmallFont）给正文，大的（SpriteFont1）给标题。
# 都没有（很老的版本）再用对话框标题的中文 BMFont（SpriteText）
FONT_CANDIDATES = ("Fonts/SmallFont.zh-CN", "Fonts/SpriteFont1.zh-CN", "Fonts/Chinese")


def _cache_font(tmp, content_dirs, log):
    """把游戏的中文字体存成 <名字>_<页>.png + font.json，界面上的字用它画。"""
    fonts = []
    for key, name in (("font", "Fonts/SmallFont.zh-CN"), ("fontL", "Fonts/SpriteFont1.zh-CN")):
        path = resolve(name, content_dirs, (".xnb",))
        if not path:
            continue
        try:
            f = xnb.load_sprite_font(path)
        except Exception as exc:
            log("  ⚠️  字体 %s 读不了（%s）" % (name, exc))
            continue
        page = key + "_0"
        png.write_rgba(os.path.join(tmp, page + ".png"), f.texture.width, f.texture.height, f.texture.rgba)
        fonts.append({"line": f.line_spacing, "source": name,
                      "glyphs": {ch: [page] + list(g) for ch, g in f.glyphs.items()}})
        log("  字体 %s：%d 个字" % (name, len(f.glyphs)))
    if not fonts:
        path = resolve("Fonts/Chinese", content_dirs, (".xnb",))
        if path:
            try:
                info = _bmfont(path, content_dirs, tmp)
                info["source"] = "Fonts/Chinese"
                fonts.append(info)
                log("  字体 Fonts/Chinese：%d 个字" % len(info["glyphs"]))
            except Exception as exc:
                log("  ⚠️  字体 Fonts/Chinese 读不了（%s）" % exc)
    if not fonts:
        log("  ⚠️  没找到游戏的中文字体，文字用系统字体")
        return
    with open(os.path.join(tmp, "font.json"), "w", encoding="utf-8") as fh:
        json.dump({"fonts": fonts}, fh, ensure_ascii=False)


def _bmfont(path, content_dirs, tmp):
    import xml.etree.ElementTree as ET
    with open(path, "rb") as fh:
        root = ET.fromstring(xnb.read_xml_source(fh.read()))
    common = root.find("common")
    for pg in root.iter("page"):
        stem = os.path.splitext(pg.get("file"))[0]
        w, h, rgba, _ = load_texture("Fonts/" + stem, content_dirs)
        png.write_rgba(os.path.join(tmp, "font_%d.png" % int(pg.get("id"))), w, h, rgba)
    glyphs = {}
    for c in root.iter("char"):
        g = [int(c.get(k)) for k in ("page", "x", "y", "width", "height", "xoffset", "yoffset", "xadvance")]
        g[0] = "font_%d" % g[0]
        glyphs[chr(int(c.get("id")))] = g
    return {"line": int(common.get("lineHeight")), "glyphs": glyphs}


def font_info():
    """缓存里的原版字体（没有就是 None）：[{"line", "glyphs"}, …]，一小一大。"""
    try:
        with open(os.path.join(CACHE_ROOT, "font.json"), encoding="utf-8") as fh:
            data = json.load(fh)
    except (IOError, OSError, ValueError):
        return None
    return data.get("fonts") if isinstance(data, dict) and "fonts" in data else [data]


def font_page_path(page):
    if isinstance(page, int):
        page = "font_%d" % page
    return os.path.join(CACHE_ROOT, "%s.png" % page)


def load_crop_table():
    from .. import farm
    try:
        with open(os.path.join(CACHE_ROOT, "crops.json"), encoding="utf-8") as fh:
            return {k: (v[0], str(v[1]), int(v[2]), list(v[3])) for k, v in json.load(fh).items()}
    except (IOError, OSError, ValueError, IndexError, TypeError):
        return dict(farm.CROPS)


def crop_sprite_path(seed):
    return os.path.join(CACHE_ROOT, "crops", str(seed) + ".png")


def bobber_styles():
    """缓存里有几种浮漂样式（0 = 没有原版浮漂表）。"""
    try:
        return int(_paths.load_json(_stamp_path()).get("bobber_styles", 0))
    except (IOError, OSError, ValueError, TypeError):
        return 0


def ui_path(name):
    return os.path.join(CACHE_ROOT, "ui", name + ".png")


def fish_icon_path(fish_id, shadow=False):
    return os.path.join(CACHE_ROOT, "fish", str(fish_id) + ("_s.png" if shadow else ".png"))
