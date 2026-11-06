#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""界面冒烟测试：用一个假的 Cocoa 模块把 App 跑一整轮（启动 → 专注 → 摸鱼 → 钓鱼 → 图鉴 → 收起）。

    python3 tests/test_ui_smoke.py

不需要 macOS。假 Cocoa 只记录调用、不画任何东西，用来抓 Python 层面的错误
（拼错属性名、参数个数不对、某个分支没走到就崩）。真正的绘制效果要在 Mac 上看。
在 Mac 上跑时也用假模块，不会弹出窗口。
"""
import os
import random
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILED = []


def check(name, got, want):
    ok = got == want
    print("  %s %s%s" % ("✅" if ok else "❌", name, "" if ok else "  (得到 %r，期望 %r)" % (got, want)))
    if not ok:
        FAILED.append(name)


# MARK: 假 Cocoa

class Any(object):
    """接受任何调用、返回自己的占位对象。"""

    def __init__(self, name="any"):
        self._name = name

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return Any(self._name + "." + name)

    def __call__(self, *a, **kw):
        return Any(self._name + "()")

    def __or__(self, other):
        return self

    __ror__ = __or__

    def __bool__(self):
        return True

    # 量出来的尺寸也是占位对象：能参与比较和加减乘除（比较一律当「放得下」）
    def __gt__(self, other):
        return False

    __lt__ = __ge__ = __le__ = __gt__

    def _arith(self, other):
        return self

    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _arith
    __truediv__ = __rtruediv__ = __floordiv__ = __rfloordiv__ = _arith

    def __round__(self, n=None):
        return 0

    def __int__(self):
        return 0

    __float__ = __int__


class P(object):
    def __init__(self, x, y):
        self.x, self.y = x, y


class Sz(object):
    def __init__(self, w, h):
        self.width, self.height = w, h


class R(object):
    def __init__(self, x, y, w, h):
        self.origin, self.size = P(x, y), Sz(w, h)


class FakeObj(object):
    """NSObject / NSView / NSWindow 的替身。"""

    @classmethod
    def alloc(cls):
        return cls.__new__(cls)

    def init(self):
        return self

    def initWithFrame_(self, frame):
        self._frame = frame
        self._needs = False
        return self

    def initWithContentRect_styleMask_backing_defer_(self, rect, *a):
        self._frame = rect
        self._visible = False
        self._ignores = False
        self._content = None
        return self

    def initWithTitle_action_keyEquivalent_(self, title, action, key):
        self._title, self._action = title, action
        self._submenu = None
        return self

    # 视图
    def bounds(self):
        return R(0, 0, self._frame.size.width, self._frame.size.height)

    def setFrame_(self, f):
        self._frame = f

    def setNeedsDisplay_(self, v):
        self._needs = v

    def convertPoint_fromView_(self, p, v):
        return p

    def addSubview_(self, v):
        v.__dict__["_parent"] = self

    def window(self):
        if self.__dict__.get("_win") is not None:
            return self._win
        parent = self.__dict__.get("_parent")
        return parent.window() if parent is not None else None

    # 窗口
    def setFrame_display_(self, f, d):
        self._frame = f

    def frame(self):
        return self._frame

    def setContentView_(self, v):
        self._content = v
        v.__dict__["_win"] = self

    def orderFrontRegardless(self):
        self._visible = True

    def makeKeyAndOrderFront_(self, s):
        self._visible = True

    def orderOut_(self, s):
        self._visible = False

    def isVisible(self):
        return self._visible

    def setIgnoresMouseEvents_(self, v):
        self._ignores = v

    # 菜单
    def removeAllItems(self):
        self._items = []

    def addItem_(self, item):
        self.__dict__.setdefault("_items", []).append(item)

    def setSubmenu_(self, m):
        self._submenu = m

    def title(self):
        return self._title

    def setRepresentedObject_(self, v):
        self._obj = v

    def representedObject(self):
        return self.__dict__.get("_obj")

    def setState_(self, v):
        self._state = v

    def setEnabled_(self, v):
        self._enabled = v

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return Any(name)


class FakeImage(FakeObj):
    @classmethod
    def alloc(cls):
        return cls.__new__(cls)

    def initWithContentsOfFile_(self, path):
        self.path = path
        return self

    def size(self):
        return Sz(16, 16)


class FakeMenuItem(FakeObj):
    @staticmethod
    def separatorItem():
        return FakeMenuItem.alloc().initWithTitle_action_keyEquivalent_("---", None, "")


class FakeScreen(object):
    @staticmethod
    def mainScreen():
        s = Any("screen")
        s.visibleFrame = lambda: R(0, 25, 1440, 875)
        return s


MOUSE = {"pressed": 0, "loc": P(500, 60)}
MONITORS = {"global": [], "local": [], "removed": 0}


class FakeEvent(object):
    @staticmethod
    def pressedMouseButtons():
        return MOUSE["pressed"]

    @staticmethod
    def mouseLocation():
        return MOUSE["loc"]

    @staticmethod
    def addGlobalMonitorForEventsMatchingMask_handler_(mask, handler):
        MONITORS["global"].append(handler)
        return handler

    @staticmethod
    def addLocalMonitorForEventsMatchingMask_handler_(mask, handler):
        MONITORS["local"].append(handler)
        return handler

    @staticmethod
    def removeMonitor_(m):
        MONITORS["removed"] += 1


class FakeKey(object):
    def __init__(self, code, flags=0, chars=""):
        self.code, self.flags, self.chars = code, flags, chars

    def characters(self):
        return self.chars

    def keyCode(self):
        return self.code

    def modifierFlags(self):
        return self.flags


class FakeMouse(object):
    def __init__(self, x, y, clicks=1):
        self.p, self.clicks = P(x, y), clicks

    def locationInWindow(self):
        return self.p

    def clickCount(self):
        return self.clicks

    def modifierFlags(self):
        return 0


class FakeString(object):
    def __init__(self, s):
        self.s = s

    @staticmethod
    def stringWithString_(s):
        return FakeString(s)

    def drawInRect_withAttributes_(self, r, a):
        pass

    def sizeWithAttributes_(self, a):
        return Sz(len(self.s) * 7.0, 16)

    def boundingRectWithSize_options_attributes_(self, size, opts, a):
        w = max(1.0, size[0])
        return R(0, 0, w, 16 * max(1, -(-len(self.s) * 7.0 // w)))


class FakeStatusBar(object):
    @staticmethod
    def systemStatusBar():
        bar = Any("bar")
        item = FakeObj()
        item._title = ""
        btn = Any("button")
        btn.setTitle_ = lambda t: setattr(item, "_title", t)
        item.button = lambda: btn
        item.setMenu_ = lambda m: setattr(item, "_menu", m)
        item.menu = lambda: item._menu
        bar.statusItemWithLength_ = lambda n: item
        return bar


class FakeApp(object):
    _shared = None

    @classmethod
    def sharedApplication(cls):
        if cls._shared is None:
            cls._shared = Any("app")
        return cls._shared


def install_fake_cocoa():
    cocoa = types.ModuleType("Cocoa")

    def module_getattr(name):
        return Any(name)

    cocoa.__getattr__ = module_getattr
    for n in ("NSObject", "NSView", "NSWindow", "NSPanel", "NSScrollView", "NSMenu",
              "NSBezierPath", "NSAlert", "NSOpenPanel"):
        setattr(cocoa, n, type(n, (FakeObj,), {}))
    cocoa.NSMenu.popUpContextMenu_withEvent_forView_ = staticmethod(
        lambda m, e, v: POPUPS.append(m))
    cocoa.NSBezierPath.fillRect_ = staticmethod(lambda r: None)
    cocoa.NSBezierPath.bezierPath = staticmethod(lambda: Any("path"))
    cocoa.NSBezierPath.bezierPathWithOvalInRect_ = staticmethod(lambda r: Any("oval"))
    cocoa.NSImage = FakeImage
    cocoa.NSMenuItem = FakeMenuItem
    cocoa.NSScreen = FakeScreen
    cocoa.NSEvent = FakeEvent
    cocoa.NSString = FakeString
    cocoa.NSStatusBar = FakeStatusBar
    cocoa.NSApplication = FakeApp
    cocoa.NSMakeRect = lambda x, y, w, h: R(x, y, w, h)
    cocoa.NSZeroRect = R(0, 0, 0, 0)
    cocoa.NSGraphicsContext = Any("ctx")
    cocoa.NSColor = Any("color")
    cocoa.NSFont = Any("font")
    cocoa.NSSound = Any("sound")
    cocoa.NSTimer = Any("timer")
    cocoa.NSRunLoop = Any("runloop")
    cocoa.NSMutableParagraphStyle = Any("style")
    for n in ("NSWindowStyleMaskBorderless", "NSWindowStyleMaskTitled", "NSWindowStyleMaskClosable",
              "NSWindowStyleMaskMiniaturizable", "NSBackingStoreBuffered", "NSAlertFirstButtonReturn",
              "NSAlertSecondButtonReturn", "NSModalResponseOK", "NSVariableStatusItemLength",
              "NSApplicationActivationPolicyAccessory", "NSImageInterpolationNone",
              "NSWindowCollectionBehaviorCanJoinAllSpaces", "NSWindowCollectionBehaviorStationary",
              "NSWindowCollectionBehaviorFullScreenAuxiliary", "NSWindowCollectionBehaviorIgnoresCycle"):
        setattr(cocoa, n, 1)
    sys.modules["Cocoa"] = cocoa

    objc = types.ModuleType("objc")
    objc.python_method = lambda f: f

    class _Super(object):
        def __init__(self, cls, obj):
            self.obj = obj

        def __getattr__(self, name):
            return getattr(FakeObj, name).__get__(self.obj)

    objc.super = _Super
    sys.modules["objc"] = objc


# MARK: 测试

POPUPS = []      # 弹出过的右键菜单


def submenu(menu, *path):
    """按标题开头一层层找子菜单：submenu(menu, "设置", "时长")。"""
    for prefix in path:
        found = None
        for i in getattr(menu, "_items", []) if menu is not None else []:
            if i._title.startswith(prefix) and getattr(i, "_submenu", None) is not None:
                found = i._submenu
                break
        menu = found
    return menu


def item(menu, prefix):
    for i in getattr(menu, "_items", []) if menu is not None else []:
        if i._title.startswith(prefix):
            return i
    return None


def main():
    install_fake_cocoa()
    import test_assets   # 复用它造假游戏的工具
    from src import gamecontent as gc, prefs, collection as colmod, minigame
    from src import session as S

    tmp = tempfile.mkdtemp(prefix="moyu_ui_")
    try:
        # 假游戏 + 隔离的缓存/存档/偏好
        gc.CACHE_ROOT = os.path.join(tmp, "cache")
        prefs.PREFS_DIR = tmp
        prefs.PREFS_PATH = os.path.join(tmp, "prefs.json")
        prefs.save({"welcomed": True})
        colmod.DEFAULT_PATH = os.path.join(tmp, "collection.json")
        game = os.path.join(tmp, "Stardew Valley")
        content = os.path.join(game, "Contents", "Resources", "Content")
        test_assets.solid_png(os.path.join(content, "LooseSprites", "Cursors.png"), 704, 2256)
        test_assets.solid_png(os.path.join(content, "Maps", "springobjects.png"), 384, 624)
        test_assets.solid_png(os.path.join(content, "TileSheets", "emotes.png"), 64, 256)
        test_assets.solid_png(os.path.join(content, "TileSheets", "bobbers.png"), 128, 160)
        os.makedirs(os.path.join(content, "Data"))
        with open(os.path.join(content, "Data", "Fish.xnb"), "wb") as fh:
            fh.write(test_assets.dict_xnb({
                "128": "Pufferfish/80/floater/1/36/0 2600/spring summer fall winter/both/x/4/.9/.5/0",
                "137": "Smallmouth Bass/28/mixed/12/24/0 2600/spring summer fall winter/both/x/1/.9/.1/0"}))
        os.environ["DESKPOND_GAME_DIR"] = game

        from src import app as appmod
        from src.ui import common as C
        clock = {"t": 1000.0}
        appmod.time.monotonic = lambda: clock["t"]
        C.play = lambda name: None

        print("== 启动")
        d = appmod.AppDelegate.alloc().init()
        d.applicationDidFinishLaunching_(None)
        check("读到了鱼", len(d.fish_list), 2)
        check("菜单栏标题", d.status_item.button() is not None, True)

        def tick(seconds, pressed_fn=None):
            end = clock["t"] + seconds
            while clock["t"] < end:
                MOUSE["pressed"] = 1 if (pressed_fn and pressed_fn()) else 0
                clock["t"] += 1 / 60.0
                d._on_tick()

        print("== 菜单（空闲）")
        menu = d.status_item.menu()
        d.menuNeedsUpdate_(menu)
        titles = [i._title for i in menu._items]
        check("有开始专注", "开始专注 🍅" in titles, True)
        check("有图鉴（带收集进度）", any(t.startswith("摸鱼图鉴…（0/2）") for t in titles), True)
        check("还没钱时不露出钓具店", any(t.startswith("钓具店") for t in titles), False)
        check("第一层不再堆状态行", any(t.startswith(("钓鱼 ", "今天 ", "🌱")) for t in titles), False)
        check("设置收进一个「设置」", [i._title.split(" ")[0] for i in submenu(menu, "设置")._items
                                   if getattr(i, "_submenu", None) is not None], ["钓鱼", "时长", "水面", "农田"])
        check("空闲时：开始专注 / 摸鱼一会儿", any(t.startswith("摸鱼一会儿") for t in titles), True)
        d.menuPick_(item(menu, "摸鱼图鉴"))
        check("点菜单项能打开图鉴", d.album.window is not None and d.album.window.isVisible(), True)
        d.album.window.orderOut_(None)
        tsub = submenu(menu, "设置", "时长")
        check("时长：三个固定搭配 + 自定义", [i._title.split("（")[0] for i in tsub._items if i._title != "---"],
              ["专注 25 分钟 + 摸鱼 5 分钟", "专注 45 分钟 + 摸鱼 10 分钟", "专注 50 分钟 + 摸鱼 10 分钟",
               "自定义…"])
        check("自定义时长：超出范围会被收回来", d._apply_durations(500, 0), (180, 1))
        d._apply_durations(1, 1)
        d.menuNeedsUpdate_(menu)
        check("自定义的时长显示在菜单上", submenu(menu, "设置", "时长 · 专注 1 + 摸鱼 1") is not None, True)
        d.menuPick_(item(submenu(menu, "设置", "时长"), "专注 45"))
        check("在菜单里选 45+10", prefs.get("durations"), [45, 10])

        print("== 专注 → 自动开始摸鱼")
        prefs.set("durations", [1, 1])
        d.setDurations_(type("S", (), {"representedObject": lambda self: "1,1"})())
        d.startFocus_(None)
        d.menuNeedsUpdate_(menu)
        ftitles = [i._title for i in menu._items]
        check("专注中：暂停 / 提前结束 / 放弃", all(t in ftitles for t in ("暂停专注", "提前结束专注，去摸鱼",
                                                                  "放弃这个番茄")), True)
        check("专注中没有「结束摸鱼」", "结束摸鱼" in ftitles, False)
        check("开始专注时就播种（新手种子包）", any(not d.farm.empty(k) for k in range(3)), True)
        check("农田摆件默认显示、浮在窗口上面", (d.farm_desk.visible, d.farm_desk.on_top), (True, True))
        tick(0.6)
        check("农田下面有番茄钟倒计时", d.farm_desk.view.caption.startswith("🍅"), True)
        d.farm_desk.view.drawRect_(None)
        d.collection.farm[2] = {"seed": "472", "days": 0}
        tick(61)
        check("专注结束后水面出现", d.pond.visible, True)
        check("做完一个番茄，作物长一天", d.collection.farm[2]["days"], 1)
        check("农田摆着时不另弹卡片", d.farm_card.visible, False)
        d.menuNeedsUpdate_(menu)
        btitles = [i._title for i in menu._items]
        check("摸鱼中：暂停 / 开始专注 / 结束摸鱼", all(t in btitles for t in ("暂停摸鱼", "不摸了，开始专注 🍅",
                                                                     "结束摸鱼")), True)
        check("摸鱼中没有「停止番茄钟」", any("番茄钟" in t and "停止" in t for t in btitles), False)
        d.collection.farm[2] = None
        tick(1.5)
        check("水面升起后等待抛竿", d.session.state, S.IDLE)

        print("== 鼠标在水上才接收点击")
        MOUSE["loc"] = P(500, 60)
        tick(0.05)
        check("鼠标在水上：接收点击", d.pond.window._ignores, False)
        MOUSE["loc"] = P(500, 600)
        tick(0.05)
        check("鼠标在别处：穿透", d.pond.window._ignores, True)

        print("== 抛竿 → 咬钩 → 溜鱼")
        d.session.rng = random.Random(3)
        d._on_pond_click(0.4)
        check("抛竿", d.session.state, S.WAITING)
        while d.session.state == S.WAITING:
            tick(0.1)
        check("咬钩", d.session.state, S.BITE)
        d._on_pond_click(0.4)
        check("开始小游戏", d.session.state, S.PLAYING)
        check("竖条窗口出现", d.panel.window.isVisible(), True)
        d.panel.view.drawRect_(None)
        g = d.session.game
        g.treasure, g.treasure_at = True, 0.0
        check("宝箱出现在竖条里", g.treasure_visible, True)
        d.panel.view.drawRect_(None)
        from src.ui import layout as L
        x, y, w, h = L.treasure_rect(g, 3)
        check("宝箱画在轨道中间", round(x + w / 2, 1), round((L.TRACK_X + L.TRACK_W / 2) * 3, 1))

        def good():
            g = d.session.game
            if g is None:
                return False
            c = g.fish_pos + minigame.FISH_SIZE / 2
            m = g.bar_pos + g.bar_height / 2
            return (c - m) - (g.bar_vel - g.fish_vel) * 0.25 < 0
        while d.session.state == S.PLAYING:
            tick(0.1, good)
        check("出结果", d.session.state, S.RESULT)
        if d.session.result.caught:
            check("钓到时竖条先停在满格", d.panel.view.game.progress, 1.0)
            tick(0.6)                          # 半秒后才收起竖条、出结果
        check("竖条收起", d.panel.window.isVisible(), False)
        check("结果提示出现", d.toast.window.isVisible(), True)
        d.toast.view.drawRect_(None)
        d.pond.view.drawRect_(None)
        r = d.session.result
        if r.caught:
            r.quality, r.level_up, r.treasure = 3, 2, [("685", 3), ("472", 1)]
            d.toast.view.drawRect_(None)
            check("结果提示能查到宝物中文名", d.toast.view._item_name("685") != "", True)
        d.menuNeedsUpdate_(menu)
        if d.collection.gold:
            check("有了钱，菜单里出现钓具店", any(i._title.startswith("钓具店…") for i in menu._items), True)
        check("空闲图标", d._idle_icon(), "🎣")

        print("== 图鉴（原版收藏菜单风格）")
        d.showCollection_(None)
        v = d.album.view
        check("图鉴窗口", d.album.window.isVisible(), True)
        check("默认：鱼 · 现在能钓", (d.album.album.page, d.album.album.filter), ("fish", "now"))
        v.drawRect_(None)
        kinds = [k for k, _, _ in v.hits]
        check("左边四个标签", kinds.count("page"), 4)
        check("鱼页有四个筛选", kinds.count("filter"), 4)

        def click(kind, value):
            for k, val, (x, y, w, h) in v.hits:
                if k == kind and (val == value or val is value):
                    v.mouseDown_(FakeMouse(x + w / 2, y + h / 2))
                    v.drawRect_(None)
                    return True
            return False
        check("点「全部」筛选", (click("filter", "all"), d.album.album.filter), (True, "all"))
        first = v.entries[0]
        check("点第一个格子选中", (click("cell", first), v.selected is first), (True, True))
        caught_e = [e for e in v.entries if e.id in d.collection.fish]
        if caught_e:
            name, desc, lines = v._tip_lines(d.album.album, caught_e[0])
            check("说明框：钓到的鱼有名字和条数", (name != "？？？", lines[0].startswith("钓到")),
                  (True, True))
        unseen = [e for e in v.entries if e.id not in d.collection.fish]
        if unseen:
            check("没钓到的显示？？？", v._tip_lines(d.album.album, unseen[0])[0], "？？？")
        mv = FakeMouse(*[c + 5 for c in [r for k, val, r in v.hits if k == "cell"][0][:2]])
        v.mouseMoved_(mv)
        check("鼠标停在图标上就弹说明", v.hover is v.entries[0], True)
        v.drawRect_(None)
        v.mouseExited_(None)
        check("移开就收起", v.hover, None)
        for page in ("items", "crops", "bobbers", "fish"):
            check("切到「%s」页" % page, (click("page", page), d.album.album.page), (True, page))
        click("page", "items")
        check("杂物与宝物页有东西", len(v.entries) > 0, True)
        click("page", "crops")
        check("作物页 12 种", len(v.entries), 12)
        v._tip_lines(d.album.album, v.entries[0])
        click("page", "bobbers")
        check("浮漂页 39 种", len(v.entries), 39)
        check("第 2 种还锁着", d.album.album.got(v.entries[1]), False)
        click("cell", v.entries[1])
        check("锁着的点了不换", d.session.bobber_pref in (0, "0"), True)
        check("锁着的说明", v._tip_lines(d.album.album, v.entries[1])[0], "？？？")
        click("random", None)
        check("图鉴里选随机", d.session.bobber_pref, "random")
        click("cell", v.entries[0])
        check("图鉴里点默认样式换上", d.session.bobber_pref, 0)
        click("page", "fish")
        click("filter", "all")
        per = 60
        if len(v.entries) > per:
            check("翻页", click("arrow", 1), True)
        d.album.set_page("fish", "now")
        check("系统红黄绿按钮藏起来了，有原版红叉", v.close_rect is not None, True)
        x, y, w, h = v.close_rect
        v.mouseDown_(FakeMouse(x + 5, y + 5))
        check("点红叉关掉图鉴", d.album.window.isVisible(), False)
        d.showCollection_(None)
        v.keyDown_(FakeKey(53))
        check("按 Esc 关掉图鉴", d.album.window.isVisible(), False)
        d.showCollection_(None)
        v.keyDown_(FakeKey(13, 1 << 20))
        check("按 ⌘W 关掉图鉴", d.album.window.isVisible(), False)

        print("== 钓上杂物")
        tick(4)
        d.session.spot = "desert"            # 假游戏里没有沙漠的鱼，只会钓上垃圾
        d._on_pond_click(0.6, 2)
        check("记下水深", d.session.depth, 2)
        while d.session.state == S.WAITING:
            tick(0.1)
        d._on_pond_click(0.6)
        check("杂物直接出结果", (d.session.state, d.session.result.junk), (S.RESULT, True))
        check("杂物提示", d.toast.window.isVisible(), True)
        d.toast.view.drawRect_(None)
        d.menuNeedsUpdate_(menu)
        check("今天的杂物数", d.collection.today_stats()["junk"] >= 1, True)
        d.session.spot = "town_river"
        tick(3.5)

        print("== 拖动水面顶边调高度")
        check("回到等待抛竿", d.session.state, S.IDLE)
        v = d.pond.view
        top = 64 + 0                          # 水面完全升起时，顶边在视图 y = 预留空间
        MOUSE["loc"] = P(500, 25 + 110)
        tick(0.05)
        check("鼠标在顶边：显示手柄", v.hover_handle, True)
        v.mouseDown_(FakeMouse(500, top + 3))
        check("按下顶边开始拖动", v.dragging, True)
        MOUSE["loc"] = P(500, 25 + 110 + 60)
        v.mouseDragged_(None)
        check("往上拖 60 点，水面变高", d.pond.height, 170)
        tick(0.05)
        check("拖动时不穿透", d.pond.window._ignores, False)
        v.drawRect_(None)
        MOUSE["loc"] = P(500, 25 + 900)
        v.mouseDragged_(None)
        check("不超过最大高度", d.pond.height, 240)
        v.mouseUp_(None)
        check("松手保存", (v.dragging, prefs.get("pond_height")), (False, 240))
        v.mouseDown_(FakeMouse(500, 64 + 0, clicks=2))
        check("双击恢复默认", d.pond.height, 110)
        MOUSE["loc"] = P(500, 60)

        print("== 点水面：横向是落点，纵向是水深")
        clicks = []
        d.pond.view.on_click = lambda x, depth, rel: clicks.append((round(x, 2), depth))
        d.pond.view.mouseDown_(FakeMouse(720, 64 + 14))
        d.pond.view.dragging = False
        d.pond.view.mouseDown_(FakeMouse(144, 64 + 108))
        check("靠上 = 浅水，靠下 = 深水", clicks, [(0.5, 1), (0.1, 5)])
        d.pond.view.on_click = d._on_pond_click

        print("== 水面菜单：高度 / 宽度 / 不透明度")
        def sender(v):
            return type("S", (), {"representedObject": lambda self: v})()
        d.setPondHeight_(sender("70"))
        check("低", (d.pond.height, d.pond.window._frame.size.height), (70, 70 + 64))
        d.setPondWidth_(sender("corner"))
        check("角落：靠右 420 点", (d.pond.window._frame.origin.x, d.pond.window._frame.size.width),
              (1440 - 420, 420))
        d.setPondWidth_(sender("half"))
        check("半屏", d.pond.screen_frame.size.width, 720)
        d.setPondAlpha_(sender("0.6"))
        check("不透明度存进偏好", (d.pond.alpha, prefs.get("pond_alpha")), (0.6, 0.6))
        d.menuNeedsUpdate_(menu)
        sub = submenu(menu, "设置", "水面")
        check("水面子菜单：高度/宽度/不透明度各三档",
              sum(1 for i in sub._items if i._action is not None), 9)
        d.menuPick_(item(sub, "角落"))
        check("从菜单改宽度", d.pond.width_mode, "corner")
        fm = submenu(menu, "设置", "农田")
        check("农田子菜单：种田、显示农田、浮在上面、压在桌面", len(fm._items), 4)
        d.setPondWidth_(sender("full"))
        d.setPondHeight_(sender("110"))

        print("== 钓点")
        fsub = submenu(menu, "设置", "钓鱼")
        spots = [i for i in fsub._items if any(n in i._title for n in ("河", "湖", "海", "森林", "沙漠"))]
        check("四个基础钓点 + 下一个要解锁的", len(spots), 5)
        check("只露出秘密森林（沙漠先不露）", [i._title for i in spots if "🔒" in i._title],
              ["🔒 秘密森林（图鉴再收集 %d 种）" % (10 - d.collection.caught_species())])
        check("钓鱼菜单标题带钓点和天气", fsub is not None, True)
        d.setSpot_(sender("desert"))
        check("锁着的钓点选不了", prefs.get("spot", "town_river"), "town_river")
        d.setSpot_(sender("ocean"))
        check("换到海边", (d.session.spot, prefs.get("spot")), ("ocean", "ocean"))
        check("状态行显示钓点", "海边" in d._status_line(clock["t"]), True)
        d.setSpot_(sender("town_river"))

        print("== 浮漂样式")
        check("读到 39 种原版浮漂", d.bobber_total, 39)
        check("一开始只有默认样式", d.session.bobber_count, 1)
        d.menuNeedsUpdate_(menu)
        check("只有一种浮漂时不出现浮漂菜单", submenu(menu, "设置", "钓鱼", "浮漂"), None)
        d.showBobbers_(None)
        check("打开图鉴浮漂页", d.album.album.page, "bobbers")
        d.album.set_page("fish", "now")
        for k in range(6):
            d.collection.fish.setdefault("x%d" % k, {"count": 1, "max_size": 1})
        d._refresh_bobbers()
        check("钓到 6 种鱼解锁 4 种", d.session.bobber_count, 4)
        d.menuNeedsUpdate_(menu)
        bsub = submenu(menu, "设置", "钓鱼", "浮漂")._items
        check("浮漂菜单：随机在最上面", bsub[0]._title, "随机（每次抛竿换一个）")
        check("有解锁提示", any(i._title.startswith("再钓到") for i in bsub), True)
        check("能跳到图鉴浮漂页", bsub[-1]._title.startswith("在图鉴里看全部"), True)
        d.setBobber_(sender("3"))
        check("选第 4 种", (d.session.pick_bobber(), prefs.get("bobber")), (3, 3))
        d.setBobber_(sender("random"))
        picks = {d.session.pick_bobber() for _ in range(200)}
        check("随机只在已解锁里挑", picks, {0, 1, 2, 3})
        d.setBobber_(sender("0"))
        for k in range(6):
            d.collection.fish.pop("x%d" % k)
        d._refresh_bobbers()
        d.pond.view.drawRect_(None)

        print("== 种田：跟着番茄钟，不在鱼塘里")
        check("鱼塘里没有农田", "farm" in d.pond.view.__dict__, False)
        d.menuNeedsUpdate_(menu)
        titles = [i._title for i in menu._items]
        check("菜单有「我的农田…」", any(t.startswith("我的农田…") for t in titles), True)
        d.showFarm_(None)
        check("农田窗口", d.farm_window.window.isVisible(), True)
        d.farm_window.view.drawRect_(None)
        fx, fy, fw, fh = d.farm_window.view.close_rect
        d.farm_window.view.mouseDown_(FakeMouse(fx + 3, fy + 3))
        check("点红叉关掉农田窗口", d.farm_window.window.isVisible(), False)
        check("刚才那个番茄送的种子已经种下", any(not d.farm.empty(k) for k in range(3)), True)
        prefs.set("farm_desktop", False)         # 先关掉农田摆件，测卡片
        tick(0.6)
        for k in range(3):
            d.collection.farm[k] = None
        from src import farm as farmlib
        for seed in farmlib.CROPS:
            d.collection.inventory.pop(seed, None)
        d.collection.give("472", 2)
        d._farm_day(clock["t"])
        check("番茄完成：空地自动播种", [d.farm.info(k)["seed"] if d.farm.info(k) else None
                                  for k in range(2)], ["472", "472"])
        check("弹出农田卡片", d.farm_card.visible, True)
        d.farm_card.view.drawRect_(None)
        tick(6)
        check("几秒后卡片自己消失", d.farm_card.visible, False)
        bait = d.collection.count("685")
        for _ in range(4):
            d._farm_day(clock["t"])
        check("4 个番茄后自动收获、换鱼饵", (d.collection.crops.get("24", 0) >= 2,
                                       d.collection.count("685") >= bait + 2), (True, True))
        d.farm_card.view.drawRect_(None)
        from src.ui.farm_window import describe
        from src.farm import DayReport
        rep = DayReport()
        check("没变化时的说明", describe(rep, str)[0].startswith("没有种子"), True)
        d.toggleFarm_(None)
        check("可以关掉种田", d._farm_on(), False)
        before = [dict(p) if p else None for p in d.collection.farm]
        d._farm_day(clock["t"])
        check("关掉后番茄完成不动农田", [dict(p) if p else None for p in d.collection.farm], before)
        d.toggleFarm_(None)

        print("== 钓具店")
        d.showShop_(None)
        sv = d.shop.view
        sv.drawRect_(None)
        check("钓具店窗口", d.shop.window.isVisible(), True)
        d.collection.xp, d.collection.gold = 400, 5000
        sv.drawRect_(None)
        btn = [r for (kind, key), r in sv.hits if key == "fiberglass"]
        check("玻璃纤维钓竿可以买", len(btn), 1)
        x, y, w, h = btn[0]
        sv.mouseDown_(FakeMouse(x + 5, y + 5))
        check("点「买」：换上玻璃纤维、扣钱", (d.session.gear.rod, d.collection.gold), ("fiberglass", 3200))
        sv.drawRect_(None)
        bait = [r for (kind, key), r in sv.hits if key == "bait"][0]
        sv.mouseDown_(FakeMouse(bait[0] + 5, bait[1] + 5))
        check("买一包鱼饵", d.collection.gold, 3150)
        sv.drawRect_(None)
        check("配件还锁着（要铱金）", [k for (kind, k), _ in sv.hits if kind == "tackle"], [])
        d.menuNeedsUpdate_(menu)
        check("菜单里钓具店显示余额", item(menu, "钓具店…（3,150g）") is not None, True)
        sv.keyDown_(FakeKey(53))
        check("Esc 关掉钓具店", d.shop.window.isVisible(), False)

        print("== 种子栏 / 选种什么")
        from src import farm as farmlib
        d.shop.show()
        sv = d.shop.view
        sv.season = lambda: "spring"
        sv.drawRect_(None)
        r = [r for (kind, k), r in sv.hits if kind == "page" and k == "seeds"][0]
        sv.mouseDown_(FakeMouse(r[0] + 5, r[1] + 5))
        sv.drawRect_(None)
        check("切到种子栏", sv.page, "seeds")
        check("春天卖四种", sorted(k for (kind, k), _ in sv.hits if kind == "seed"), ["472", "474", "475", "477"])
        gold, n = d.collection.gold, d.collection.count("472")
        r = [r for (kind, k), r in sv.hits if k == "472"][0]
        sv.mouseDown_(FakeMouse(r[0] + 5, r[1] + 5))
        check("买一包防风草", (d.collection.gold, d.collection.count("472")), (gold - 20, n + 1))
        d.collection.farm[1] = None
        d.showFarm_(None)
        fv = d.farm_window.view
        fv.drawRect_(None)
        r = [r for (kind, k), r in fv.hits if kind == "plot" and k == 1][0]
        fv.mouseDown_(FakeMouse(r[0] + 10, r[1] + 10))
        fv.drawRect_(None)
        check("点地打开选种子", fv.choosing, 1)
        r = [r for (kind, k), r in fv.hits if kind == "seed" and k == "472"][0]
        fv.mouseDown_(FakeMouse(r[0] + 5, r[1] + 5))
        check("选防风草：空地马上种上", (d.farm.info(1)["seed"], d.collection.farm_plan[1]), ("472", "472"))
        print("== 农田扩建")
        d.shop.show(page="seeds")
        sv.drawRect_(None)
        d.collection.xp, d.collection.gold = 400, 3000          # 钓鱼 2 级：还不够
        sv.drawRect_(None)
        check("等级不够不能扩建", [k for (kind, k), _ in sv.hits if kind == "expand"], [])
        d.collection.xp = 770                                     # 3 级
        sv.drawRect_(None)
        r = [r for (kind, k), r in sv.hits if kind == "expand"][0]
        sv.mouseDown_(FakeMouse(r[0] + 5, r[1] + 5))
        check("扩建成 2 排 6 块", (d.farm.size, d.farm.rows, d.collection.gold), (6, 2, 500))
        fv.drawRect_(None)
        check("「我的农田」里能点第 6 块地", any(kind == "plot" and k == 5 for (kind, k), _ in fv.hits), True)
        check("窗口跟着变高", d.farm_window.view._frame.size.height > 400, True)
        d.farm_window.window.orderOut_(None)
        d.shop.window.orderOut_(None)

        print("== 原版风格对话框")
        d.customDurations_(None)
        dv = d.dialog.view
        check("自定义时长对话框", d.dialog.visible, True)
        dv.drawRect_(None)
        x, y, w, h = dv.rects["next0"]
        dv.mouseDown_(FakeMouse(x + 5, y + 5))
        dv.keyDown_(FakeKey(48))                                  # Tab → 摸鱼
        dv.keyDown_(FakeKey(18, chars="7"))
        dv.drawRect_(None)
        check("◀▶ 和打字", (dv.model.fields[0].value, dv.model.fields[1].shown()),
              (prefs.get("durations")[0] + 1, "7"))
        want = [prefs.get("durations")[0] + 1, 7]
        dv.keyDown_(FakeKey(36))                                  # 回车
        check("回车 = 好", (prefs.get("durations"), d.dialog.visible), (want, False))
        d.customDurations_(None)
        d.dialog.view.keyDown_(FakeKey(53))                       # Esc
        check("Esc = 取消", prefs.get("durations"), want)
        d._apply_durations(1, 1)
        d.enableBossKey_(None)
        d.dialog.view.drawRect_(None)
        check("提示框只有「好」", [k for _, k in d.dialog.model.buttons], ["ok"])
        d.dialog.view.keyDown_(FakeKey(36))

        print("== 农田摆件")
        check("关着的时候不显示", d.farm_desk.visible, False)
        d.toggleFarmDesktop_(None)
        check("番茄钟在跑（摸鱼中）时显示", (d.pomo.fishing, d.farm_desk.visible), (True, True))
        check("摸鱼中的进度字", d.farm_desk.view.caption.startswith("🐟"), True)
        d.setFarmTop_(type("S", (), {"representedObject": lambda self: "desktop"})())
        check("可以改成压在桌面上", d.farm_desk.on_top, False)
        d.setFarmTop_(type("S", (), {"representedObject": lambda self: "top"})())
        check("再改回浮在上面", d.farm_desk.on_top, True)
        tick(0.6)
        check("平时只显示短的一行", d.farm_desk.view.caption.count("·"), 0)
        f = d.farm_desk.window.frame()
        MOUSE["loc"] = P(f.origin.x + 10, f.origin.y + 10)
        tick(0.1)
        check("鼠标移上去展开完整进度", "·" in d.farm_desk.view.caption, True)
        MOUSE["loc"] = P(5, 900)
        tick(0.1)
        check("移开又收回去", d.farm_desk.view.caption.count("·"), 0)
        d.farm_desk.view.rightMouseDown_(FakeMouse(20, 20))
        cm = POPUPS[-1]
        check("农田右键菜单", [i._title for i in cm._items if i._title != "---"][:2],
              ["这一轮先收起来", "番茄钟期间不再显示（设置 → 农田 可以再打开）"])
        d.menuPick_(item(cm, "这一轮先收起来"))
        tick(0.6)
        check("右键收起：这一轮不显示", d.farm_desk.visible, False)
        check("但选项还开着", d._farm_desktop_on(), True)
        d.farm_desk_snooze = None
        tick(0.6)
        check("下一轮自己回来", d.farm_desk.visible, True)
        d.pond.view.rightMouseDown_(FakeMouse(100, 100))
        pm = POPUPS[-1]
        check("水面右键菜单有藏起来 / 结束摸鱼", (item(pm, "藏起来") is not None, item(pm, "结束摸鱼") is not None),
              (True, True))
        check("水面右键能换钓点", submenu(pm, "换钓点") is not None, True)
        d.farm_desk.view.drawRect_(None)
        d.farm_desk.view.mouseDown_(FakeMouse(10, 10))
        check("挪动后记住位置", prefs.get("farm_desk_pos") is not None, True)
        check("桌面摆件在普通窗口下面", d.farm_desk.window is not None, True)
        if d.farm_card.window is not None:
            d.farm_card.window.orderOut_(None)
        d.collection.farm[0] = {"seed": "472", "days": 3}
        d._farm_day(clock["t"])
        check("摆在桌面时：不再弹农田卡片", d.farm_card.visible, False)
        check("收获的作物在桌面上往上冒", len(d.farm_desk.view.pops) >= 1, True)
        d.farm_desk.view.drawRect_(None)
        tick(2.5)
        check("冒完就收起", d.farm_desk.view.pops, [])
        d.toggleFarmDesktop_(None)
        check("关掉选项就收起", d.farm_desk.visible, False)
        d.toggleFarmDesktop_(None)

        print("== 老板键")
        check("挂上了全局和本地键盘监听", (len(MONITORS["global"]) >= 1, len(MONITORS["local"]) >= 1),
              (True, True))
        opt_cmd = (1 << 19) | (1 << 20)
        MONITORS["global"][-1](FakeKey(3, opt_cmd))
        check("⌥⌘F：水面立刻消失", (d.session.state, d.pond.visible), (S.HIDDEN, False))
        popped = []
        d.status_item.menu().popUpMenuPositioningItem_atLocation_inView_ = lambda *a: popped.append(1)
        MONITORS["global"][-1](FakeKey(46, opt_cmd))
        check("⌥⌘M：在鼠标处弹出菜单", popped, [1])
        d.menuNeedsUpdate_(menu)
        check("菜单出现「继续摸」", any(i._title.startswith("继续摸") for i in menu._items), True)
        check("本地监听吞掉快捷键", MONITORS["local"][-1](FakeKey(3, opt_cmd)), None)
        check("再按一次：水面回来", d.pond.visible, True)
        tick(1.5)
        check("其他按键放行", MONITORS["local"][-1](FakeKey(3, 1 << 20)) is not None, True)
        MOUSE["loc"] = P(500, 600)
        MONITORS["global"][-1](FakeKey(53))
        check("鼠标不在水上时 Esc 不管", d.pond.visible, True)
        MOUSE["loc"] = P(500, 60)
        MONITORS["global"][-1](FakeKey(53))
        check("鼠标在水上按 Esc 也能藏", d.pond.visible, False)
        d.toggleBoss_(None)
        check("菜单「继续摸」", d.pond.visible, True)
        tick(1.5)

        print("== 农田摆件跟着番茄钟")
        tick(0.6)
        check("摸鱼中摆着", d.farm_desk.visible, True)

        print("== 摸鱼时间到 → 水面退下 → 下一轮专注")
        tick(65)
        check("水面收起", d.session.state, S.HIDDEN)
        check("窗口隐藏", d.pond.visible, False)
        d.menuNeedsUpdate_(menu)
        check("回到专注", d.pomo.phase, "focus")
        check("专注中也摆着", d.farm_desk.visible, True)

        print("== 临时摸鱼 / 难度 / 停止")
        d.stopTimer_(None)
        d.fishNow_(None)
        check("临时摸鱼开塘", d.pond.visible, True)
        d.setMode_(type("S", (), {"representedObject": lambda self: "original"})())
        check("难度存进偏好", prefs.get("mode"), "original")
        d.toggleSound_(None)
        d.endBreak_(None)
        tick(2)
        check("提前结束后收起", d.session.state, S.HIDDEN)
        check("临时摸鱼结束回到空闲", d.pomo.phase, "idle")
        tick(0.6)
        check("番茄钟停了农田摆件收起", d.farm_desk.visible, False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("失败 %d 项: %s" % (len(FAILED), "、".join(FAILED)))
        return 1
    print("界面冒烟测试全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
