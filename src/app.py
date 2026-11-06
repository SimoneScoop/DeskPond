# -*- coding: utf-8 -*-
"""桌面摸鱼入口：菜单栏番茄钟 + 休息时屏幕底部变成鱼塘。"""
import os
import sys
import time
import traceback

import objc
from Cocoa import (NSAlert, NSAlertFirstButtonReturn,
                   NSApplication, NSApplicationActivationPolicyAccessory, NSEvent,
                   NSMenu, NSMenuItem, NSModalResponseOK, NSObject, NSOpenPanel,
                   NSRunLoop, NSRunLoopCommonModes, NSStatusBar, NSTimer,
                   NSVariableStatusItemLength)

from . import collection as col
from . import farm as farmlib
from . import fishdata, gamecontent, pomodoro, prefs, progression, world
from . import session as S
from .ui import common as C
from .ui import layout as L
from .ui import dialog_model
from .ui import menu_model as MM
from .ui.dialog_window import GameDialog
from .ui.collection_window import MILESTONES, CollectionWindow
from .ui.farm_window import FarmCard, FarmDesk, FarmWindow
from .ui.shop_window import ShopWindow
from .ui.minigame_window import PanelWindow, Toast
from .ui.pond import Pond

APP_NAME = "桌面摸鱼"
TICK = 1.0 / 60.0

DURATIONS, FOCUS_RANGE, BREAK_RANGE = MM.DURATIONS, MM.FOCUS_RANGE, MM.BREAK_RANGE
DEFAULT_MODE, MODES = MM.DEFAULT_MODE, MM.MODES

# 老板键：⌥⌘F 全局收起水面；鼠标在水上时按 Esc 也行
KEY_DOWN_MASK = 1 << 10          # NSEventMaskKeyDown
MOD_SHIFT, MOD_CTRL, MOD_OPTION, MOD_COMMAND = 1 << 17, 1 << 18, 1 << 19, 1 << 20
KEY_F, KEY_ESC, KEY_M = 3, 53, 46
BOSS_KEY_LABEL = "⌥⌘F"
CATCH_HOLD = 0.5                 # 钓到后进度条满格停留几秒，再出结果
MENU_KEY_LABEL = "⌥⌘M"           # 菜单栏图标被挤掉时，用它在鼠标处弹出菜单

SOUNDS = {
    "break_start": "Glass",
    "break_end": "Submarine",
    S.EV_CAST: "Pop",
    S.EV_BITE: "Ping",
    "caught": "Glass",
    "new_fish": "Hero",
    S.EV_ESCAPED: "Funk",
    S.EV_JUNK: "Bottle",
}


def _accessibility_trusted(prompt=False):
    """全局快捷键要「辅助功能」授权。查不到（没装 ApplicationServices）时返回 None。"""
    try:
        if prompt:
            from ApplicationServices import AXIsProcessTrustedWithOptions
            return bool(AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True}))
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return None


def _menu_item(title, action=None, target=None, key="", enabled=True, state=None, obj=None):
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
    if target is not None:
        item.setTarget_(target)
    if not enabled or action is None:
        item.setEnabled_(False)
    if state is not None:
        item.setState_(1 if state else 0)
    if obj is not None:
        item.setRepresentedObject_(obj)
    return item


class _Val(object):
    """把一个值包成「菜单项」的样子，复用按 sender.representedObject() 取值的动作。"""

    def __init__(self, value):
        self.value = value

    def representedObject(self):
        return self.value


class AppDelegate(NSObject):

    BOSS_KEY_LABEL = BOSS_KEY_LABEL

    def init(self):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self.status_item = None
        self.timer = None
        self.fish_list = []
        self.collection = None
        self.pomo = None
        self.session = None
        self.pond = None
        self.panel = None
        self.toast = None
        self.album = None
        self.last_tick = 0.0
        self.last_title = 0.0
        self.boss_hidden = False      # 被老板键藏起来了，摸鱼时间还没到
        self.pending_toast = None     # (什么时候出, 结果, 落点)：钓到时晚一点出结果
        self.monitors = []
        self.monitors_trusted = None
        return self

    # MARK: 启动

    def applicationDidFinishLaunching_(self, notification):
        if not self._load_game_assets():
            NSApplication.sharedApplication().terminate_(self)
            return
        C.sound_enabled = bool(prefs.get("sound", False))    # 上班场合，默认安静
        self.collection = col.Collection()
        focus, brk = prefs.get("durations", [25, 5])
        self.pomo = pomodoro.Pomodoro(focus_min=focus, break_min=brk,
                                      long_break_min=max(brk * 3, 2))
        self.session = S.Session(self.fish_list, self.collection,
                                 mode=prefs.get("mode", DEFAULT_MODE), junk=gamecontent.load_junk())
        self.session.spot = self._current_spot()
        self.bobber_total = gamecontent.bobber_styles()
        self.session.bobber_pref = prefs.get("bobber", 0)
        self._refresh_bobbers()
        self.farm = farmlib.Farm(self.collection.farm, gamecontent.load_crop_table())
        self.farm_card = FarmCard(self._item_name)
        self.farm_window = FarmWindow(self.farm, self.collection, self._item_name,
                                      season=fishdata.season_of, on_change=self._gear_changed)
        self.shop = ShopWindow(self.collection, self._item_name, on_change=self._gear_changed)
        self.farm_desk = FarmDesk(self.farm, self._item_name,
                                  load_pos=lambda: prefs.get("farm_desk_pos"),
                                  save_pos=lambda pos: prefs.set("farm_desk_pos", pos))
        self.farm_desk.on_menu = lambda: self._context_menu(MM.farm_context(self))
        self.farm_desk_snooze = None      # 右键「这一轮先收起来」记下的是哪一轮
        self.farm_desk_hover = False
        self.pond = Pond(self._on_pond_click, self._on_pond_resize,
                         on_menu=lambda: self._context_menu(MM.pond_context(self)))
        self.pond.configure(height=prefs.get("pond_height", L.POND_HEIGHT),
                            width_mode=prefs.get("pond_width", "full"),
                            alpha=prefs.get("pond_alpha", 1.0))
        self.panel = PanelWindow()
        self.toast = Toast(self.session.junk)
        self.album = CollectionWindow(self.fish_list, self.collection, self.session.junk,
                                      spot_fn=self._current_spot)
        self.album.album.bobber_total = self.bobber_total
        self.album.album.bobber_pref = lambda: self.session.bobber_pref
        self.album.album.on_bobber = self._set_bobber

        self._setup_status_item()
        self._install_boss_key()
        self.last_tick = time.monotonic()
        self.timer = NSTimer.timerWithTimeInterval_repeats_block_(
            TICK, True, lambda t: self._safe_tick())
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)
        print("[桌面摸鱼] 已就绪：%d 种鱼，图鉴已收集 %d 种"
              % (len(self.fish_list), self.collection.caught_species()))
        if not prefs.get("welcomed"):
            prefs.set("welcomed", True)
            self._welcome()

    def _load_game_assets(self):
        """素材不随仓库分发：从本机安装的《星露谷物语》读取并缓存（和 mod 一样）。"""
        game_dir = prefs.get("game_dir")
        message = None
        try:
            gamecontent.ensure_cache(game_dir=game_dir)
        except gamecontent.GameNotFound:
            message = ("桌面摸鱼不自带游戏图片，需要从你电脑上安装的《星露谷物语》里读取"
                       "（和游戏 mod 的做法一样）。\n\n没有在常见位置找到游戏，请选择游戏文件夹：\n"
                       "Steam 版通常在 ~/Library/Application Support/Steam/steamapps/common/Stardew Valley")
        except Exception as exc:
            traceback.print_exc()
            message = "读取游戏素材时出错：\n%s\n\n可以换一个游戏目录，或选择解包后的「Content (unpacked)」文件夹。" % exc

        app = NSApplication.sharedApplication()
        while message is not None:
            app.activateIgnoringOtherApps_(True)
            alert = NSAlert.alloc().init()
            alert.setMessageText_("需要读取《星露谷物语》的游戏素材")
            alert.setInformativeText_(message)
            alert.addButtonWithTitle_("选择游戏文件夹…")
            alert.addButtonWithTitle_("退出")
            if alert.runModal() != NSAlertFirstButtonReturn:
                return False
            panel = NSOpenPanel.openPanel()
            panel.setCanChooseDirectories_(True)
            panel.setCanChooseFiles_(True)
            panel.setAllowsMultipleSelection_(False)
            panel.setMessage_("选择 Stardew Valley 游戏目录、Stardew Valley.app，或解包后的 Content (unpacked) 文件夹")
            if panel.runModal() != NSModalResponseOK:
                continue
            chosen = panel.URLs()[0].path()
            try:
                gamecontent.ensure_cache(game_dir=chosen, force=True)
            except gamecontent.GameNotFound:
                message = "这个文件夹里没找到游戏素材（需要有 LooseSprites、Data 子目录）：\n%s" % chosen
                continue
            except Exception as exc:
                traceback.print_exc()
                message = "读取失败：%s" % exc
                continue
            prefs.set("game_dir", chosen)
            message = None

        self.fish_list = gamecontent.load_fish_list()
        if not self.fish_list:
            alert = NSAlert.alloc().init()
            alert.setMessageText_("没读到鱼的数据")
            alert.setInformativeText_("Data/Fish 里没有可以钓的鱼，可能是游戏版本太旧或文件损坏。")
            alert.runModal()
            return False
        return True

    def _welcome(self):
        text = (dialog_model.WELCOME_TEXT % (self.pomo.focus / 60, BOSS_KEY_LABEL)
                + "\n\n之后都在菜单栏的 🎣 里操作。")

        def done(key, values):
            if key == "focus":
                self.startFocus_(None)
            elif key == "fish":
                self.fishNow_(None)
        self.dialog = GameDialog(dialog_model.Dialog("桌面摸鱼", text, dialog_model.WELCOME_BUTTONS),
                                 done).show()

    # MARK: 主循环

    def _safe_tick(self):
        # PyObjC 会吞掉定时器回调里的异常，这里自己打全栈，免得「看着在跑其实挂了」
        try:
            self._on_tick()
        except Exception:
            traceback.print_exc()

    def _on_tick(self):
        now = time.monotonic()
        dt = now - self.last_tick
        self.last_tick = now

        for ev in self.pomo.update(now):
            self._on_pomodoro_event(ev, now)

        sess = self.session
        if sess.state != S.HIDDEN:
            pressed = bool(NSEvent.pressedMouseButtons() & 1)
            for ev in sess.update(now, dt, pressed):
                self._on_session_event(ev, now)
            if sess.state != S.RESULT:
                self.toast.hide()
                self.pending_toast = None
            self._show_pending_toast(now)
            mouse = NSEvent.mouseLocation()
            self.pond.update(now, self._status_line(now, full=self.pond.contains(mouse)), mouse)
            self.panel.update(now)
        self.farm_card.update(now)
        self.farm_desk.update(now)
        if self.farm_desk.visible:
            hover = self.farm_desk.contains(NSEvent.mouseLocation())
            if hover != self.farm_desk_hover:     # 鼠标移上去：那行字展开成完整版
                self.farm_desk_hover = hover
                self._refresh_farm_desk()

        if now - self.last_title >= 0.5:
            self.last_title = now
            self._update_farm_desktop()
            if self.farm_desk.visible:
                self._refresh_farm_desk()        # 倒计时每半秒走一下
            if self.farm_window.window is not None and self.farm_window.window.isVisible():
                self.farm_window.refresh()       # 「我的农田」开着就实时更新
            title = self.pomo.menu_title(now)
            if self.pomo.phase == pomodoro.IDLE:
                title = self._idle_icon()
            self.status_item.button().setTitle_(title)

    def _status_line(self, now, full=True):
        """水面左下角那一行。鼠标不在水上时只留倒计时，移上去才显示钓点、天气、今天的战绩。"""
        today = self.collection.today_stats()
        if self.pomo.fishing:
            secs = int(self.pomo.remaining(now) + 0.999)
            clock = "⏸ 已暂停" if self.pomo.paused else "摸鱼还剩 %d:%02d" % divmod(secs, 60)
        else:
            clock = "摸鱼时间到，钓完这条就收"
        if not full:
            return "🐟 " + clock
        weather = world.WEATHER_ZH[world.today_weather()].split(" ")[0]
        return "🐟 %s · %s %s · 今天钓到 %d 条" % (
            clock, world.spot_name(self.session.spot), weather, today["caught"])

    def _refresh_bobbers(self):
        self.session.bobber_count = progression.bobbers_unlocked(
            self.collection.caught_species(), self.bobber_total)

    def _idle_icon(self):
        """空闲时的菜单栏图标随图鉴里程碑升级：🎣 → 🐠（10 种）→ 🐡（24 种）→ 👑（全部）。"""
        n = self.collection.caught_species()
        total = len(self.album.fish)
        if total and n >= total:
            return "👑"
        if n >= MILESTONES[1][0]:
            return "🐡"
        if n >= MILESTONES[0][0]:
            return "🐠"
        return "🎣"

    # MARK: 钓点

    def _current_spot(self):
        key = prefs.get("spot", world.DEFAULT_SPOT)
        if not world.is_unlocked(key, self.collection.caught_species()):
            key = world.DEFAULT_SPOT
        return key

    # MARK: 番茄钟 / 摸鱼流程

    def _on_pomodoro_event(self, ev, now):
        if ev == pomodoro.EV_BREAK_START:
            self._open_pond(now)
            self._farm_day(now)      # 走到这里说明专注是完整做完的（跳过专注不经过这里）
        elif ev == pomodoro.EV_BREAK_END:
            self._close_pond(now)
        elif ev == pomodoro.EV_FOCUS_START:
            self._farm_focus_start(now)          # 摸鱼结束自动进入下一个番茄
        self.last_title = 0.0

    def _open_pond(self, now, quiet=False):
        self.boss_hidden = False
        self.session.novice = self.collection.caught_species() < L.NOVICE_SPECIES
        self.session.mode = prefs.get("mode", DEFAULT_MODE)
        self.session.spot = self._current_spot()
        self._refresh_bobbers()
        self.session.show(now)
        self.pond.attach(self.session)
        if not quiet:
            C.play(SOUNDS["break_start"])

    def _close_pond(self, now):
        self.boss_hidden = False
        if self.session.state == S.HIDDEN:
            return
        self.session.hide(now)
        self.pond.flash("摸鱼时间到，回去干活啦 🍅", now, 3.0)
        C.play(SOUNDS["break_end"])

    def _on_pond_click(self, x, depth=None, y=None):
        now = time.monotonic()
        for ev in self.session.click(now, x, depth, y):
            self._on_session_event(ev, now)

    def _on_pond_resize(self, height, final):
        h = L.clamp_height(height)
        self.pond.configure(height=h)
        if final:
            prefs.set("pond_height", h)

    # MARK: 种田（跟着番茄钟走：每完整做完一个专注，农田过一天）

    def _farm_on(self):
        return bool(prefs.get("farm", True))

    def _item_name(self, item_id):
        it = self.session.junk.get(str(item_id)) if self.session else None
        return it.display_name if it is not None else str(item_id)

    def _farm_desktop_on(self):
        return bool(prefs.get("farm_desktop", True))

    def _farm_top(self):
        return prefs.get("farm_desk_level", "top") == "top"

    def _update_farm_desktop(self):
        """桌面农田摆件：开了选项、开着种田、番茄钟在跑（专注或摸鱼）时显示。"""
        show = (self._farm_on() and self._farm_desktop_on() and self.pomo.phase != pomodoro.IDLE
                and self.farm_desk_snooze != self._farm_round())
        was = self.farm_desk.visible
        self.farm_desk.set_visible(show)
        if show and not was:
            self._refresh_farm_desk()

    @objc.python_method
    def _farm_round(self):
        p = self.pomo
        return (p.phase, p.round, p.free_fishing)

    @objc.python_method
    def _hide_farm_once(self):
        """右键「这一轮先收起来」：这段专注（或摸鱼）里不再显示，下一段自己回来。"""
        self.farm_desk_snooze = self._farm_round()
        self._update_farm_desktop()

    def _refresh_farm_desk(self):
        now = time.monotonic()
        if self.farm_desk_hover:
            cap = farmlib.progress_caption(self.farm, self._item_name, self.pomo.phase,
                                           self.pomo.remaining(now), fishdata.season_of())
            if self.pomo.paused:
                cap = "⏸ 已暂停 · " + cap.split(" · ", 1)[-1]
        else:
            cap = farmlib.short_caption(self.pomo.phase, self.pomo.remaining(now), self.pomo.paused)
        self.farm_desk.set_on_top(self._farm_top())
        self.farm_desk.refresh(fishdata.season_of(), cap,
                               watered=self.pomo.phase == pomodoro.FOCUS)   # 专注 = 今天浇过水了

    def _farm_focus_start(self, now):
        """开始专注：空地马上播种（第一次还会送新手种子包），专注期间就能看到地里有东西。"""
        if not self._farm_on():
            return
        self._update_farm_desktop()
        report = farmlib.focus_start(self.farm, self.collection, fishdata.season_of())
        if report.planted and not self.farm_desk.visible and report.gift:
            self.farm_card.show(self.farm, report, now)
        self.farm_window.refresh()
        self._refresh_farm_desk()

    def _gear_changed(self):
        """买了东西 / 选了种子：菜单、农田摆件、我的农田跟着刷新。"""
        self.last_title = 0.0
        if getattr(self, "farm_desk", None) is not None and self.farm_desk.visible:
            self._refresh_farm_desk()
        if getattr(self, "farm_window", None) is not None:
            self.farm_window.refresh()

    def _farm_day(self, now):
        if not self._farm_on():
            return
        report = farmlib.focus_done(self.farm, self.collection, fishdata.season_of())
        if self.farm_desk.visible:
            # 农田就摆在桌面上：直接在那儿长、冒出收获，不再另弹卡片
            self.farm_desk.pop(report.harvested, now)
        elif report.harvested or report.planted or report.gift:
            # 只长了一天这种小事不打扰；有收获、播种、送种子才弹卡片
            self.farm_card.show(self.farm, report, now, self.pomo.round)
        self.farm_window.refresh()
        self._refresh_farm_desk()
        self.album.refresh()

    # MARK: 老板键

    def _install_boss_key(self):
        for m in self.monitors:
            NSEvent.removeMonitor_(m)
        self.monitors = []
        self.monitors_trusted = _accessibility_trusted()

        def handle(ev):
            try:
                flags = ev.modifierFlags() & (MOD_SHIFT | MOD_CTRL | MOD_OPTION | MOD_COMMAND)
                code = ev.keyCode()
                if code == KEY_F and flags == MOD_OPTION | MOD_COMMAND:
                    self._boss_toggle()
                    return True
                if code == KEY_M and flags == MOD_OPTION | MOD_COMMAND:
                    self._popup_menu()
                    return True
                if (code == KEY_ESC and self.session.state != S.HIDDEN
                        and self.pond.contains(NSEvent.mouseLocation())):
                    self._boss_toggle()
                    return True
            except Exception:
                traceback.print_exc()
            return False

        def on_global(ev):
            handle(ev)

        def on_local(ev):
            return None if handle(ev) else ev

        for m in (NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(KEY_DOWN_MASK, on_global),
                  NSEvent.addLocalMonitorForEventsMatchingMask_handler_(KEY_DOWN_MASK, on_local)):
            if m is not None:
                self.monitors.append(m)

    def _boss_toggle(self):
        now = time.monotonic()
        if self.session.state != S.HIDDEN:
            self.session.boss_hide(now)
            self.pond.hide()
            self.panel.hide()
            self.toast.hide()
            self.boss_hidden = self.pomo.fishing
            if self.farm_card.window is not None:
                self.farm_card.window.orderOut_(None)
        elif self.boss_hidden and self.pomo.fishing:
            self._open_pond(now, quiet=True)

    def _show_pending_toast(self, now):
        p = self.pending_toast
        if p is None or now < p[0]:
            return
        self.pending_toast = None
        if self.session.result is p[1] and self.session.state == S.RESULT:
            self.toast.show_result(p[1], p[2], self.pond.screen_frame, self.pond.water_top_screen_y())

    def _on_session_event(self, ev, now):
        sess = self.session
        pond = self.pond
        if ev == S.EV_START_GAME:
            scale = L.panel_scale(pond.screen_frame.size.height, pond.height)
            self.panel.show(sess.game, sess.cast_x, pond.screen_frame,
                            pond.water_top_screen_y(), scale)
        elif ev in (S.EV_CAUGHT, S.EV_ESCAPED):
            r = sess.result
            hold = CATCH_HOLD if r.caught else 0.0
            self.panel.finish(now, hold)       # 钓到时进度条先停在满格一会儿，再出结果
            species_before = self.collection.caught_species() - (1 if r.is_new else 0)
            self.pending_toast = (now + hold, r, sess.cast_x)
            self._show_pending_toast(now)
            if r.caught:
                C.play(SOUNDS["new_fish"] if r.is_new else SOUNDS["caught"])
                print("[桌面摸鱼] 钓到 %s %d 英寸%s" % (r.fish.display_name, r.size,
                                                   "（新鱼种）" if r.is_new else ""))
            else:
                C.play(SOUNDS[S.EV_ESCAPED])
            self.album.refresh()
            self._announce_unlocks(species_before, now)
        elif ev == S.EV_JUNK:
            self.toast.show_result(sess.result, sess.cast_x, pond.screen_frame,
                                   pond.water_top_screen_y())
            C.play(SOUNDS[S.EV_JUNK])
            self.album.refresh()
        elif ev == S.EV_BAIT:
            pond.flash("挂上鱼饵，鱼会来得快一点（还剩 %d 个）"
                       % self.collection.count(progression.BAIT), now)
        elif ev == S.EV_TOO_EARLY:
            pond.flash("太早了！鱼被吓跑了", now)
        elif ev == S.EV_MISSED:
            pond.flash("没反应过来，鱼溜走了", now)
        elif ev == S.EV_HIDDEN:
            pond.hide()
            self.panel.hide()
            self.toast.hide()
        else:
            C.play(SOUNDS.get(ev))

    def _announce_unlocks(self, before, now):
        after = self.collection.caught_species()
        total = len(self.album.fish)
        old = self.session.bobber_count
        self._refresh_bobbers()
        if self.session.bobber_count > old:
            self.pond.flash("🎣 解锁新浮漂（菜单 → 浮漂）", now, 3.0)
        for need, name in MILESTONES + [(total, "钓鱼大师")]:
            if need and before < need <= after:
                self.pond.flash("🏆 图鉴收集 %d 种：%s" % (need, name), now, 4.0)
                self.last_title = 0.0
        for key in world.SPOT_KEYS:
            need = world.unlock_need(key)
            if before < need <= after:
                self.pond.flash("🔓 解锁新钓点：%s（菜单 → 钓点）" % world.spot_name(key), now, 4.0)

    # MARK: 菜单栏

    def _setup_status_item(self):
        """菜单栏图标。

        图标「时不时消失」通常是菜单栏放不下了：前台 App 的菜单很长时，macOS 会把靠左的状态栏图标藏起来。
        这里做三件事：数字用等宽字体，倒计时走字时宽度不跳；设 autosaveName，按住 ⌘ 把图标拖到靠右的
        位置后系统会记住；再加一个 ⌥⌘M，图标被挤掉时也能在鼠标处弹出同一个菜单。
        """
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength)
        try:
            self.status_item.setAutosaveName_("DeskPond")
        except Exception:
            pass
        btn = self.status_item.button()
        try:
            from Cocoa import NSFont
            btn.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(13.0, 0.0))
        except Exception:
            pass
        btn.setTitle_("🎣")
        btn.setToolTip_("桌面摸鱼（图标不见了可以按 %s 打开菜单）" % MENU_KEY_LABEL)
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        menu.setDelegate_(self)
        self.status_item.setMenu_(menu)

    def _popup_menu(self):
        """在鼠标处弹出菜单栏菜单（图标被系统藏起来时用）。"""
        menu = self.status_item.menu()
        menu.popUpMenuPositioningItem_atLocation_inView_(None, NSEvent.mouseLocation(), None)

    def menuNeedsUpdate_(self, menu):
        """菜单内容来自 ui/menu_model（和 Windows 版共用）：状态 → 当下能做的事 → 窗口 → 设置 → 退出。
        只有菜单栏主菜单设了 delegate，子菜单每次都是新建的。"""
        menu.removeAllItems()
        self._picks = {}
        self._fill_menu(menu, MM.main(self))

    @objc.python_method
    def _fill_menu(self, menu, items):
        for it in items:
            if it is None:
                menu.addItem_(NSMenuItem.separatorItem())
                continue
            if it.children is not None:
                item, sub = self._sub_menu(it.title)
                self._fill_menu(sub, it.children)
                menu.addItem_(item)
                continue
            obj = None
            if it.action:
                obj = str(len(self._picks))
                self._picks[obj] = (it.action, it.arg)
            entry = _menu_item(it.title, b"menuPick:" if it.action else None, self, it.key,
                               enabled=it.enabled, state=it.checked, obj=obj)
            if it.icon:
                icon = C.image(gamecontent.ui_path(it.icon))
                if icon is not None:
                    icon.setSize_((22, 22))
                    entry.setImage_(icon)
            menu.addItem_(entry)

    @objc.python_method
    def _context_menu(self, items):
        """右键菜单（水面、农田摆件）。"""
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        if not getattr(self, "_picks", None):
            self._picks = {}
        self._fill_menu(menu, items)
        return menu

    def menuPick_(self, sender):
        pick = self._picks.get(sender.representedObject())
        if pick:
            try:
                self.menu_do(*pick)
            except Exception:
                traceback.print_exc()

    @objc.python_method
    def menu_do(self, action, arg=None):
        """菜单项 → 动作（名字和 Windows 版一样）。"""
        v = _Val(arg)
        table = {
            "start_focus": lambda: self.startFocus_(None),
            "fish_now": lambda: self.fishNow_(None),
            "pause_resume": lambda: self.pauseResume_(None),
            "skip_to_break": lambda: self.skipToBreak_(None),
            "stop_timer": lambda: self.stopTimer_(None),
            "boss_toggle": lambda: self._boss_toggle(),
            "show_album": lambda: self.showCollection_(None),
            "show_shop": lambda: self.showShop_(None),
            "show_farm": lambda: self.showFarm_(None),
            "show_bobbers": lambda: self.showBobbers_(None),
            "set_spot": lambda: self.setSpot_(v),
            "set_bobber": lambda: self._set_bobber(arg),
            "set_mode": lambda: self.setMode_(v),
            "set_durations": lambda: self._apply_durations(*arg),
            "custom_durations": lambda: self.customDurations_(None),
            "set_pond_height": lambda: self._on_pond_resize(float(arg), True),
            "set_pond_width": lambda: self.setPondWidth_(v),
            "set_pond_alpha": lambda: self.setPondAlpha_(v),
            "toggle_farm": lambda: self.toggleFarm_(None),
            "toggle_farm_desktop": lambda: self.toggleFarmDesktop_(None),
            "set_farm_top": lambda: self.setFarmTop_(_Val("top" if arg else "desktop")),
            "hide_farm_once": lambda: self._hide_farm_once(),
            "toggle_sound": lambda: self.toggleSound_(None),
            "enable_boss_key": lambda: self.enableBossKey_(None),
            "rebuild_assets": lambda: self.rebuildAssets_(None),
            "quit": lambda: self.quitAction_(None),
        }
        table[action]()
        self.last_title = 0.0

    @objc.python_method
    def _menu_notes(self):
        notes = []
        trusted = _accessibility_trusted()
        if trusted is False:
            notes.append(MM.Item("开启老板键 %s（需要授权）…" % BOSS_KEY_LABEL, "enable_boss_key"))
        elif trusted and not self.monitors_trusted:
            self._install_boss_key()      # 刚授权：重新挂一次全局监听
        return notes

    @objc.python_method
    def _sound_on(self):
        return bool(C.sound_enabled)

    def _sub_menu(self, title):
        item = _menu_item(title, None)
        item.setEnabled_(True)
        sub = NSMenu.alloc().init()
        sub.setAutoenablesItems_(False)
        item.setSubmenu_(sub)
        return item, sub

    def _break_minutes(self):
        return int(prefs.get("durations", [25, 5])[1])

    # MARK: 菜单动作（这些名字会注册成 Objective-C selector，参数个数必须对上）

    def startFocus_(self, sender):
        now = time.monotonic()
        if self.pomo.fishing:
            self._close_pond(now)
        self.pomo.start_focus(now)
        self._farm_focus_start(now)
        self.last_title = 0.0

    def fishNow_(self, sender):
        now = time.monotonic()
        self.pomo.start_break(now, minutes=self._break_minutes(), free=True)
        self._open_pond(now)
        self.last_title = 0.0

    def skipToBreak_(self, sender):
        now = time.monotonic()
        self.pomo.round += 1
        self.pomo.start_break(now)
        self._open_pond(now)
        self.last_title = 0.0

    def endBreak_(self, sender):
        now = time.monotonic()
        free = self.pomo.free_fishing
        self._close_pond(now)
        if free:
            self.pomo.stop()
        else:
            self.pomo.start_focus(now)
            self._farm_focus_start(now)
        self.last_title = 0.0

    def pauseResume_(self, sender):
        now = time.monotonic()
        if self.pomo.paused:
            self.pomo.resume(now)
        else:
            self.pomo.pause(now)
        self.last_title = 0.0

    def stopTimer_(self, sender):
        now = time.monotonic()
        if self.pomo.fishing:
            self._close_pond(now)
        self.pomo.stop()
        self.last_title = 0.0

    def showCollection_(self, sender):
        self.album.show()

    def setMode_(self, sender):
        mode = sender.representedObject()
        prefs.set("mode", mode)
        if self.session.state != S.PLAYING:
            self.session.mode = mode

    def setDurations_(self, sender):
        focus, brk = [int(v) for v in sender.representedObject().split(",")]
        self._apply_durations(focus, brk)

    def _apply_durations(self, focus, brk):
        focus, brk = MM.clamp_durations(focus, brk)
        prefs.set("durations", [focus, brk])
        self.pomo.focus = focus * 60.0
        self.pomo.short_break = brk * 60.0
        self.pomo.long_break = max(brk * 3, 2) * 60.0
        self.last_title = 0.0
        return focus, brk

    def customDurations_(self, sender):
        """自己填专注和摸鱼各几分钟（原版风格的对话框：◀ ▶ 加减，也能直接打数字）。"""
        focus, brk = prefs.get("durations", [25, 5])
        model = dialog_model.durations_dialog(focus, brk, FOCUS_RANGE, BREAK_RANGE)

        def done(key, values):
            if key == "ok":
                self._apply_durations(*values)
        self.dialog = GameDialog(model, done).show()

    def setFarmTop_(self, sender):
        prefs.set("farm_desk_level", sender.representedObject())
        self._refresh_farm_desk()

    def setSpot_(self, sender):
        key = sender.representedObject()
        if world.is_unlocked(key, self.collection.caught_species()):
            prefs.set("spot", key)
            self.session.spot = key       # 下一次咬钩就按新钓点挑鱼
            if self.pond.visible:
                self.pond.flash("换到「%s」" % world.spot_name(key), time.monotonic())

    def setPondHeight_(self, sender):
        self._on_pond_resize(float(sender.representedObject()), True)

    def setPondWidth_(self, sender):
        mode = sender.representedObject()
        prefs.set("pond_width", mode)
        self.pond.configure(width_mode=mode)

    def setPondAlpha_(self, sender):
        value = float(sender.representedObject())
        prefs.set("pond_alpha", value)
        self.pond.configure(alpha=value)

    def setBobber_(self, sender):
        self._set_bobber(sender.representedObject())

    def _set_bobber(self, value):
        pref = "random" if value == "random" else int(value)
        prefs.set("bobber", pref)
        self.session.bobber_pref = pref

    def toggleBoss_(self, sender):
        self._boss_toggle()

    def enableBossKey_(self, sender):
        _accessibility_trusted(prompt=True)
        self._message("开启老板键",
                      "在「系统设置 → 隐私与安全性 → 辅助功能」里勾选运行桌面摸鱼的程序"
                      "（用终端启动的话是「终端」或你的 Python）。勾选后再点一次菜单就生效。\n\n"
                      "没授权时：鼠标在水面上按 Esc，或用菜单里的「藏起来」。")

    @objc.python_method
    def _message(self, title, text):
        """只有一个「好」按钮的原版风格提示框。"""
        self.dialog = GameDialog(dialog_model.Dialog(title, text, [("好", "ok")])).show()

    def toggleFarm_(self, sender):
        prefs.set("farm", not self._farm_on())

    def showFarm_(self, sender):
        self.farm_window.show()

    def showShop_(self, sender):
        self.shop.show()

    def showBobbers_(self, sender):
        self.album.show(page="bobbers")

    def toggleFarmDesktop_(self, sender):
        prefs.set("farm_desktop", not self._farm_desktop_on())
        self._update_farm_desktop()
        self._refresh_farm_desk()

    def toggleSound_(self, sender):
        C.sound_enabled = not C.sound_enabled
        prefs.set("sound", C.sound_enabled)

    def rebuildAssets_(self, sender):
        try:
            gamecontent.ensure_cache(game_dir=prefs.get("game_dir"), force=True)
        except Exception as exc:
            self._message("重新读取失败", str(exc))
            return
        sys.stdout.flush()
        if getattr(sys, "frozen", False):            # 打包成 DeskPond.app 时：直接重启自己
            os.execv(sys.executable, [sys.executable] + sys.argv[1:])
        script = os.path.abspath(sys.argv[0])
        os.execv(sys.executable, [sys.executable, "-u", script] + sys.argv[1:])

    def quitAction_(self, sender):
        NSApplication.sharedApplication().terminate_(self)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)   # 不占 Dock
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()
