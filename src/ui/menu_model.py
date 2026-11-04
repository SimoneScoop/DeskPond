# -*- coding: utf-8 -*-
"""菜单的内容（Mac 菜单栏 / Windows 托盘 / 两个右键菜单共用），和平台无关。

渐进式披露：
    第一层只放「现在能做的事」和三个窗口；
    设置统一收进「设置 ▸」，二级里再按钓鱼 / 时长 / 水面 / 农田分组；
    还用不上的东西不出现（钓具店有钱了才出现、浮漂解锁第二种才出现、锁着的钓点只显示下一个）；
    依赖某个开关的子选项，开关打开了才出现，而不是灰着摆在那里。

每一项是 Item；None 是分隔线。点了之后平台层调用 app.menu_do(action, arg)。
"""
import time

from .. import pomodoro, prefs, progression, world
from .. import session as S
from . import layout as L

DURATIONS = [(25, 5), (45, 10), (50, 10)]
FOCUS_RANGE, BREAK_RANGE = (1, 180), (1, 60)
MODES = [("original", "原版手感"), ("casual", "轻松")]
DEFAULT_MODE = "original"


class Item(object):
    __slots__ = ("title", "action", "arg", "checked", "enabled", "key", "icon", "children")

    def __init__(self, title, action=None, arg=None, checked=None, enabled=None, key="",
                 icon=None, children=None):
        self.title = title
        self.action = action
        self.arg = arg
        self.checked = checked
        self.enabled = (action is not None or children is not None) if enabled is None else enabled
        self.key = key                # 快捷键字母（只有 Mac 菜单用）
        self.icon = icon              # 图标的 ui 名字，比如 bobber_icon_3
        self.children = children      # 子菜单

    def __repr__(self):
        return "Item(%r)" % self.title


def label(title):
    """灰字，只看不点。"""
    return Item(title, enabled=False)


def find(items, prefix):
    """按标题开头找一项（测试和平台层用）。"""
    for it in items or []:
        if it is not None and it.title.startswith(prefix):
            return it
    return None


def titles(items):
    return [it.title for it in items or [] if it is not None]


# MARK: 小工具

def durations():
    return tuple(int(v) for v in prefs.get("durations", [25, 5]))


def clamp_durations(focus, brk):
    focus = max(FOCUS_RANGE[0], min(FOCUS_RANGE[1], int(focus)))
    brk = max(BREAK_RANGE[0], min(BREAK_RANGE[1], int(brk)))
    return focus, brk


def shop_revealed(app):
    """钓具店：有钱了、或者已经买过东西、或者够等级买玻璃纤维竿了才出现。"""
    c = app.collection
    if c.gold > 0 or app.session.gear.rod != "bamboo":
        return True
    return progression.level_for(c.xp) >= 2


def status_line(app, now=None):
    p = app.pomo
    now = time.monotonic() if now is None else now
    if p.phase == pomodoro.IDLE:
        today = app.collection.today_stats()["caught"]
        text = "🎣 空闲" + (" · 今天钓到 %d 条" % today if today else "")
    elif p.phase == pomodoro.FOCUS:
        text = "🍅 专注中 %s · 第 %d 个番茄" % (_clock(p, now), p.round + 1)
    else:
        text = "🐟 摸鱼中 %s" % _clock(p, now)
    if p.paused:
        text += " · 已暂停"
    return text


def _clock(p, now):
    return "%d:%02d" % divmod(int(max(0, p.remaining(now)) + 0.999), 60)


# MARK: 主菜单

def main(app, now=None):
    p = app.pomo
    items = [label(status_line(app, now))]
    items += actions(app)
    items.append(None)

    c = app.collection
    total = len(app.album.fish) if getattr(app, "album", None) else 0
    items.append(Item("摸鱼图鉴…" + ("（%d/%d）" % (c.caught_species(), total) if total else ""),
                      "show_album", key="d"))
    if app._farm_on():
        ready = any(i and i["mature"] for i in (app.farm.info(k) for k in range(app.farm.size)))
        items.append(Item("我的农田…" + ("（有可以收的）" if ready else ""), "show_farm"))
    if shop_revealed(app):
        items.append(Item("钓具店…（%sg）" % format(c.gold, ","), "show_shop"))
    items.append(None)

    items.append(Item("设置", children=settings(app)))
    items += app._menu_notes()           # 平台自己的提示（老板键授权、快捷键冲突…）
    items.append(Item("退出", "quit", key="q"))
    del p
    return items


def actions(app):
    """当下能做的事：番茄钟和摸鱼是两件独立的事，各自有暂停 / 结束。"""
    p = app.pomo
    out = []
    if p.phase == pomodoro.IDLE:
        out.append(Item("开始专注 🍅", "start_focus", key="s"))
        out.append(Item("摸鱼一会儿 🐟（%d 分钟）" % durations()[1], "fish_now", key="f"))
    elif p.phase == pomodoro.FOCUS:
        out.append(Item("继续专注" if p.paused else "暂停专注", "pause_resume", key="p"))
        out.append(Item("提前结束专注，去摸鱼", "skip_to_break"))
        out.append(Item("放弃这个番茄", "stop_timer"))
    else:
        out.append(Item("继续摸鱼" if p.paused else "暂停摸鱼", "pause_resume", key="p"))
        out.append(Item("不摸了，开始专注 🍅", "start_focus"))
        out.append(Item("结束摸鱼", "stop_timer"))
    if app.session.state != S.HIDDEN:
        out.append(Item("藏起来（老板键 %s）" % app.BOSS_KEY_LABEL, "boss_toggle"))
    elif app.boss_hidden and p.fishing:
        out.append(Item("继续摸（%s）" % app.BOSS_KEY_LABEL, "boss_toggle"))
    return out


def settings(app):
    cur = durations()
    spot = app._current_spot()
    items = [
        Item("钓鱼 · %s %s" % (world.spot_name(spot), world.WEATHER_ZH[world.today_weather()]),
             children=fishing(app)),
        Item("时长 · 专注 %d + 摸鱼 %d 分钟" % cur, children=timer(app)),
        Item("水面", children=pond(app)),
        Item("农田", children=farm(app)),
        Item("音效", "toggle_sound", checked=app._sound_on()),
        None,
        Item("重新读取游戏素材", "rebuild_assets"),
    ]
    return items


def spots(app):
    """解锁了的钓点 + 下一个要解锁的（再远的先不露出来）。"""
    cur = app._current_spot()
    species = app.collection.caught_species()
    out, shown_lock = [], False
    for key in world.SPOT_KEYS:
        if world.is_unlocked(key, species):
            out.append(Item(world.spot_name(key), "set_spot", key, checked=key == cur))
        elif not shown_lock:
            shown_lock = True
            out.append(label("🔒 %s（图鉴再收集 %d 种）" % (
                world.spot_name(key), max(1, world.unlock_need(key) - species))))
    return out


def fishing(app):
    items = [label("钓点")] + spots(app)
    n = app.session.bobber_count
    if app.bobber_total and n > 1:           # 解锁第二种浮漂之前不出现
        items += [None, Item("浮漂", children=bobbers(app))]
    items += [None, label("难度")]
    mode = prefs.get("mode", DEFAULT_MODE)
    for key, title in MODES:
        items.append(Item(title, "set_mode", key, checked=key == mode))
    return items


def bobbers(app):
    pref = app.session.bobber_pref
    n = app.session.bobber_count
    items = [Item("随机（每次抛竿换一个）", "set_bobber", "random", checked=pref == "random"), None]
    for i in range(n):
        items.append(Item("样式 %d%s" % (i + 1, "（默认）" if i == 0 else ""), "set_bobber", i,
                          checked=str(pref) == str(i), icon="bobber_icon_%d" % i))
    items.append(None)
    if n < app.bobber_total:
        need = progression.species_for_style(n) - app.collection.caught_species()
        items.append(label("再钓到 %d 种新鱼解锁下一种（%d/%d）" % (max(1, need), n, app.bobber_total)))
    items.append(Item("在图鉴里看全部 %d 种…" % app.bobber_total, "show_bobbers"))
    return items


def timer(app):
    cur = durations()
    items = [Item("专注 %d 分钟 + 摸鱼 %d 分钟" % (f, b), "set_durations", (f, b), checked=cur == (f, b))
             for f, b in DURATIONS]
    custom = cur not in DURATIONS
    items += [None, Item("自定义…" + ("（现在：专注 %d + 摸鱼 %d）" % cur if custom else ""),
                         "custom_durations", checked=custom)]
    return items


def pond(app):
    po = app.pond
    items = [label("高度")]
    items += [Item(t, "set_pond_height", v, checked=abs(po.height - v) < 1) for t, v in L.HEIGHT_PRESETS]
    items += [None, label("宽度")]
    items += [Item(t, "set_pond_width", k, checked=k == po.width_mode) for k, t in L.WIDTH_MODES]
    items += [None, label("不透明度")]
    items += [Item(t, "set_pond_alpha", v, checked=abs(po.alpha - v) < 0.01) for v, t in L.OPACITIES]
    items += [None, label("也可以拖水面顶边调高度，双击恢复")]
    return items


def farm(app):
    on = app._farm_on()
    items = [Item("种田（每完成一个番茄，农田过一天）", "toggle_farm", checked=on)]
    if on:
        desk = app._farm_desktop_on()
        items.append(Item("番茄钟期间显示农田", "toggle_farm_desktop", checked=desk))
        if desk:
            top = app._farm_top()
            items.append(Item("    浮在所有窗口上面", "set_farm_top", True, checked=top))
            items.append(Item("    压在桌面上（只在露出桌面时看得到）", "set_farm_top", False, checked=not top))
    return items


# MARK: 右键菜单

def pond_context(app):
    """在水面上右键。"""
    p = app.pomo
    items = [Item("藏起来（%s 再叫出来）" % app.BOSS_KEY_LABEL, "boss_toggle")]
    if p.phase in (pomodoro.BREAK, pomodoro.LONG_BREAK) and not p.free_fishing:
        items.append(Item("不摸了，开始专注 🍅", "start_focus"))
    items.append(Item("结束摸鱼", "stop_timer"))
    items += [None, Item("换钓点", children=spots(app)), Item("水面", children=pond(app))]
    return items


def farm_context(app):
    """在农田摆件上右键。"""
    top = app._farm_top()
    return [
        Item("这一轮先收起来", "hide_farm_once"),
        Item("番茄钟期间不再显示（设置 → 农田 可以再打开）", "toggle_farm_desktop"),
        Item("改成压在桌面上" if top else "改成浮在窗口上面", "set_farm_top", not top),
        None,
        Item("打开我的农田…", "show_farm"),
    ]
