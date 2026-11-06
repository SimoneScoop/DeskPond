# -*- coding: utf-8 -*-
"""桌面摸鱼 Windows 版入口：托盘图标番茄钟 + 休息时屏幕底部（任务栏上方）变成鱼塘。

和 Mac 版的区别只在「壳」上：
    菜单栏图标 → 右下角托盘图标（左键、右键都能打开菜单；鼠标停上去看倒计时）
    ⌥⌘F / ⌥⌘M → Ctrl+Alt+F（老板键）/ Ctrl+Alt+M（在鼠标处打开菜单），Windows 上不用授权
钓鱼、番茄钟、图鉴、种田、钓具这些逻辑和 Mac 版是同一份代码。
"""
import os
import sys
import time
import traceback

from PySide6.QtCore import QLockFile, QObject, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMenu, QMessageBox, QSystemTrayIcon

from .. import collection as col
from .. import farm as farmlib
from .. import fishdata, gamecontent, pomodoro, prefs, progression, world
from .. import session as S
from ..paths import DATA_DIR
from ..ui import layout as L
from ..ui import dialog_model
from ..ui import menu_model as MM
from ..ui.album_model import MILESTONES
from . import platform as P
from . import qtdraw as C
from .album import AlbumWindow
from .dialog import GameDialog
from .farm import FarmCard, FarmDesk, FarmWindow
from .pond import Panel, Pond, Toast
from .shop import ShopWindow

APP_NAME = "桌面摸鱼"
TICK_MS = 16
DURATIONS, FOCUS_RANGE, BREAK_RANGE = MM.DURATIONS, MM.FOCUS_RANGE, MM.BREAK_RANGE
DEFAULT_MODE = "original"
MODES = [("original", "原版手感"), ("casual", "轻松")]
BOSS_KEY_LABEL = "Ctrl+Alt+F"
MENU_KEY_LABEL = "Ctrl+Alt+M"
SELFTEST = "--selftest" in sys.argv     # 打包后自检（GitHub Actions 用）：启动成功 3 秒后自己退出，不弹任何框
CATCH_HOLD = 0.5                        # 钓到后进度条满格停留几秒
TRAY_HINT = "图标在屏幕右下角托盘里；看不到的话点任务栏右边的 ^ 小箭头。"

SOUNDS = {"break_start": "start", "break_end": "end", S.EV_CAST: "cast", S.EV_BITE: "bite",
          "caught": "caught", "new_fish": "new", S.EV_ESCAPED: "escaped", S.EV_JUNK: "junk"}


class App(QObject):

    BOSS_KEY_LABEL = BOSS_KEY_LABEL

    def __init__(self, qapp):
        super(App, self).__init__()
        self.qapp = qapp
        self.tray = None
        self.menu = None
        self.timer = None
        self.last_tick = 0.0
        self.last_title = 0.0
        self.boss_hidden = False
        self.esc_was_down = False
        self.hotkeys = None
        self.hotkeys_ok = False

    # MARK: 启动

    def start(self):
        if not self._load_game_assets():
            return False
        P.sound_enabled = bool(prefs.get("sound", False))      # 上班场合，默认安静
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
                                  load_pos=lambda: prefs.get("farm_desk_pos_win"),
                                  save_pos=lambda pos: prefs.set("farm_desk_pos_win", pos))
        self.farm_desk.on_menu = lambda: self._context_menu(MM.farm_context(self))
        self.farm_desk_snooze = None      # 右键「这一轮先收起来」记下的是哪一轮
        self.farm_desk_hover = False
        self.pond = Pond(self._on_pond_click, self._on_pond_resize,
                         on_menu=lambda: self._context_menu(MM.pond_context(self)))
        self.pond.configure(height=prefs.get("pond_height", L.POND_HEIGHT),
                            width_mode=prefs.get("pond_width", "full"),
                            alpha=prefs.get("pond_alpha", 1.0))
        self.panel = Panel()
        self.toast = Toast(self.session.junk)
        self.album = AlbumWindow(self.fish_list, self.collection, self.session.junk,
                                 spot_fn=self._current_spot)
        self.album.album.bobber_total = self.bobber_total
        self.album.album.bobber_pref = lambda: self.session.bobber_pref
        self.album.album.on_bobber = self._set_bobber

        self._setup_tray()
        self._install_hotkeys()
        self.last_tick = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._safe_tick)
        self.timer.start(TICK_MS)
        print("[桌面摸鱼] 已就绪：%d 种鱼，图鉴已收集 %d 种"
              % (len(self.fish_list), self.collection.caught_species()))
        if not prefs.get("welcomed"):
            prefs.set("welcomed", True)
            QTimer.singleShot(300, self._welcome)
        return True

    def _load_game_assets(self):
        """素材不随仓库分发：从本机安装的《星露谷物语》读取并缓存（和 mod 一样）。"""
        message = None
        try:
            gamecontent.ensure_cache(game_dir=prefs.get("game_dir"), log=self._loading_log)
        except gamecontent.GameNotFound:
            message = ("桌面摸鱼不自带游戏图片，需要从你电脑上安装的《星露谷物语》里读取"
                       "（和游戏 mod 的做法一样）。\n\n没有在常见位置找到游戏，请选择游戏文件夹。\n"
                       "Steam 版通常在 C:\\Program Files (x86)\\Steam\\steamapps\\common\\Stardew Valley")
        except Exception as exc:
            traceback.print_exc()
            message = "读取游戏素材时出错：\n%s\n\n可以换一个游戏目录，或选择解包后的「Content (unpacked)」文件夹。" % exc
        self._loading_done()
        if message is not None and SELFTEST:
            print("[桌面摸鱼] 自检失败：" + message)
            return False
        while message is not None:
            box = QMessageBox(QMessageBox.Information, "需要读取《星露谷物语》的游戏素材", message)
            box.setWindowFlag(Qt.WindowStaysOnTopHint)
            pick = box.addButton("选择游戏文件夹…", QMessageBox.AcceptRole)
            box.addButton("退出", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not pick:
                return False
            chosen = QFileDialog.getExistingDirectory(None, "选择 Stardew Valley 游戏目录，或解包后的 Content (unpacked) 文件夹")
            if not chosen:
                continue
            try:
                gamecontent.ensure_cache(game_dir=chosen, force=True, log=self._loading_log)
            except gamecontent.GameNotFound:
                message = "这个文件夹里没找到游戏素材（需要有 Content\\LooseSprites、Content\\Data）：\n%s" % chosen
                continue
            except Exception as exc:
                traceback.print_exc()
                message = "读取失败：%s" % exc
                continue
            finally:
                self._loading_done()
            prefs.set("game_dir", chosen)
            message = None
        self.fish_list = gamecontent.load_fish_list()
        if not self.fish_list:
            QMessageBox.warning(None, "没读到鱼的数据", "Data/Fish 里没有可以钓的鱼，可能是游戏版本太旧或文件损坏。")
            return False
        return True

    def _loading_log(self, line):
        """第一次启动要从游戏里解出素材（几十秒到一两分钟）：这期间显示一个提示窗，不然像没反应。"""
        print(line)
        if getattr(self, "loading", None) is None:
            self.loading = QLabel("桌面摸鱼：第一次启动，正在从《星露谷物语》读取素材…\n"
                                  "大约需要半分钟到两分钟，读完会自动打开，请稍等。")
            self.loading.setWindowTitle(APP_NAME)
            self.loading.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
            self.loading.setAlignment(Qt.AlignCenter)
            self.loading.setMargin(28)
            f = self.loading.font()
            f.setPointSize(11)
            self.loading.setFont(f)
            self.loading.show()
            self.loading.raise_()
            self.loading.activateWindow()
        self.qapp.processEvents()

    def _loading_done(self):
        if getattr(self, "loading", None) is not None:
            self.loading.close()
            self.loading = None

    def _welcome(self):
        text = (dialog_model.WELCOME_TEXT % (self.pomo.focus / 60, BOSS_KEY_LABEL)
                + "\n\n之后都在右下角托盘的 🎣 图标里操作（左键右键都行）。")

        def done(key, values):
            if key == "focus":
                self.start_focus()
            elif key == "fish":
                self.fish_now()
        if self.tray is not None:
            self.tray.showMessage("桌面摸鱼已经在运行", TRAY_HINT, QSystemTrayIcon.Information, 8000)
        self.dialog = GameDialog(dialog_model.Dialog("桌面摸鱼", text, dialog_model.WELCOME_BUTTONS),
                                 done).show()

    def _message(self, title, text):
        """只有一个「好」按钮的原版风格提示框。"""
        self.dialog = GameDialog(dialog_model.Dialog(title, text, [("好", "ok")])).show()

    # MARK: 主循环

    def _safe_tick(self):
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
        pos = QCursor.pos()
        if sess.state != S.HIDDEN:
            for ev in sess.update(now, dt, P.left_button_down()):
                self._on_session_event(ev, now)
            if sess.state != S.RESULT:
                self.toast.hide()
            self.pond.update(now, self._status_line(now, full=self.pond.contains(pos)), pos)
            self.panel.update(now)
            # 鼠标在水面上按 Esc = 老板键（鱼塘不抢焦点，所以直接看按键状态）
            esc = P.esc_down()
            if esc and not self.esc_was_down and self.pond.contains(pos):
                self.boss_toggle()
            self.esc_was_down = esc
        self.farm_card.update(now)
        self.farm_desk.update(now)
        if self.farm_desk.visible:
            hover = self.farm_desk.contains(QCursor.pos())
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
            self._update_tray(now)

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

    # MARK: 托盘图标

    def _setup_tray(self):
        self.qapp.setStyleSheet(C.menu_stylesheet())     # 托盘菜单、右键菜单都用原版说明框的样子
        self.tray = QSystemTrayIcon(self)
        self.menu = C.game_menu(QMenu())
        self.menu.aboutToShow.connect(self._build_menu)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray)
        self._update_tray(time.monotonic())
        self.tray.show()

    def _on_tray(self, reason):
        if reason == QSystemTrayIcon.Trigger:          # 左键也打开菜单
            self.popup_menu()

    def popup_menu(self):
        self.menu.popup(QCursor.pos())

    def _tray_icon(self, now):
        """托盘图标：空闲时是浮漂（随图鉴里程碑换成鱼）；专注是红圈 + 剩余分钟，摸鱼是蓝圈。"""
        pm = QPixmap(32, 32)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        phase = self.pomo.phase
        if phase == pomodoro.IDLE:
            n = self.collection.caught_species()
            icon = C.ui("bobber_icon_0")
            if n >= MILESTONES[0][0]:
                icon = C.image(gamecontent.fish_icon_path("128" if n >= MILESTONES[1][0] else "145"))
            if icon is not None:
                p.drawPixmap(0, 0, 32, 32, icon)
            else:
                p.setBrush(QColor(220, 50, 40))
                p.setPen(Qt.NoPen)
                p.drawEllipse(6, 6, 20, 20)
        else:
            mins = int(self.pomo.remaining(now) + 59.999) // 60
            bg = QColor(214, 64, 52) if phase == pomodoro.FOCUS else QColor(60, 120, 200)
            if self.pomo.paused:
                bg = QColor(130, 130, 130)
            p.setBrush(bg)
            p.setPen(Qt.NoPen)
            p.drawEllipse(1, 1, 30, 30)
            f = QFont()
            f.setPixelSize(17 if mins < 100 else 12)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(255, 255, 255))
            p.drawText(pm.rect(), int(Qt.AlignCenter), str(min(mins, 999)))
        p.end()
        return QIcon(pm)

    def _update_tray(self, now):
        if self.tray is None:
            return
        key = (self.pomo.phase, self.pomo.paused, int(self.pomo.remaining(now) + 59.999) // 60,
               self.collection.caught_species() >= MILESTONES[0][0])
        if key != getattr(self, "_tray_key", None):
            self._tray_key = key
            self.tray.setIcon(self._tray_icon(now))
        title = self.pomo.menu_title(now)
        self.tray.setToolTip("%s %s\n（图标找不到时按 %s 打开菜单）" % (
            APP_NAME, "空闲" if self.pomo.phase == pomodoro.IDLE else title, MENU_KEY_LABEL))

    # MARK: 菜单（和 Mac 版同样的结构：状态 → 当下能做的事 → 三个窗口 → 设置 → 退出）

    def _act(self, menu, text, fn=None, checked=None, enabled=True):
        a = QAction(text, menu)
        if checked is not None:
            a.setCheckable(True)
            a.setChecked(bool(checked))
        a.setEnabled(bool(enabled) and fn is not None)
        if fn is not None:
            a.triggered.connect(lambda _=False, f=fn: self._safe(f))
        menu.addAction(a)
        return a

    def _safe(self, fn):
        try:
            fn()
        except Exception:
            traceback.print_exc()

    def _build_menu(self):
        """菜单内容来自 ui/menu_model（和 Mac 版共用）。"""
        self.menu.clear()
        self._fill_menu(self.menu, MM.main(self))

    def _fill_menu(self, menu, items):
        for it in items:
            if it is None:
                menu.addSeparator()
            elif it.children is not None:
                self._fill_menu(C.game_menu(menu.addMenu(it.title)), it.children)
            else:
                fn = (lambda a=it.action, v=it.arg: self.menu_do(a, v)) if it.action else None
                a = self._act(menu, it.title, fn, checked=it.checked, enabled=it.enabled)
                if it.icon:
                    icon = C.ui(it.icon)
                    if icon is not None:
                        a.setIcon(QIcon(icon))

    def _context_menu(self, items):
        """右键菜单（水面、农田摆件）。"""
        menu = C.game_menu(QMenu())
        self._fill_menu(menu, items)
        return menu

    def menu_do(self, action, arg=None):
        """菜单项 → 动作（名字和 Mac 版一样）。"""
        table = {
            "start_focus": self.start_focus, "fish_now": self.fish_now,
            "pause_resume": self.pause_resume, "skip_to_break": self.skip_to_break,
            "stop_timer": self.stop_timer, "boss_toggle": self.boss_toggle,
            "show_album": self.album.show, "show_shop": self.shop.show,
            "show_farm": self.farm_window.show,
            "show_bobbers": lambda: self.album.show(page="bobbers"),
            "set_spot": lambda: self.set_spot(arg), "set_bobber": lambda: self._set_bobber(arg),
            "set_mode": lambda: self.set_mode(arg), "set_durations": lambda: self.set_durations(*arg),
            "custom_durations": self.custom_durations,
            "set_pond_height": lambda: self._on_pond_resize(float(arg), True),
            "set_pond_width": lambda: self.set_pond_width(arg),
            "set_pond_alpha": lambda: self.set_pond_alpha(arg),
            "toggle_farm": self.toggle_farm, "toggle_farm_desktop": self.toggle_farm_desktop,
            "set_farm_top": lambda: self.set_farm_top(arg), "hide_farm_once": self.hide_farm_once,
            "toggle_sound": self.toggle_sound, "rebuild_assets": self.rebuild_assets,
            "quit": self.quit,
        }
        table[action]()
        self.last_title = 0.0

    def _menu_notes(self):
        if self.hotkeys_ok:
            return []
        return [MM.label("快捷键 %s / %s 被别的软件占用了" % (BOSS_KEY_LABEL, MENU_KEY_LABEL))]

    def _sound_on(self):
        return bool(P.sound_enabled)

    def _break_minutes(self):
        return int(prefs.get("durations", [25, 5])[1])

    # MARK: 快捷键

    def _install_hotkeys(self):
        self.hotkeys = P.HotkeyWindow()
        ok1 = self.hotkeys.register(1, "F", self.boss_toggle)
        ok2 = self.hotkeys.register(2, "M", self.popup_menu)
        self.hotkeys_ok = (ok1 and ok2) or not P.IS_WIN

    def boss_toggle(self):
        now = time.monotonic()
        if self.session.state != S.HIDDEN:
            self.session.boss_hide(now)
            self.pond.hide()
            self.panel.hide()
            self.toast.hide()
            self.boss_hidden = self.pomo.fishing
            if self.farm_card.visible:
                self.farm_card.view.hide()
        elif self.boss_hidden and self.pomo.fishing:
            self._open_pond(now, quiet=True)

    # MARK: 钓点 / 浮漂

    def _current_spot(self):
        key = prefs.get("spot", world.DEFAULT_SPOT)
        if not world.is_unlocked(key, self.collection.caught_species()):
            key = world.DEFAULT_SPOT
        return key

    def _refresh_bobbers(self):
        self.session.bobber_count = progression.bobbers_unlocked(
            self.collection.caught_species(), self.bobber_total)

    def _set_bobber(self, value):
        pref = "random" if value == "random" else int(value)
        prefs.set("bobber", pref)
        self.session.bobber_pref = pref
        self.album.refresh()

    # MARK: 番茄钟 / 摸鱼流程

    def _on_pomodoro_event(self, ev, now):
        if ev == pomodoro.EV_BREAK_START:
            self._open_pond(now)
            self._farm_day(now)       # 走到这里说明专注是完整做完的
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
            P.play(SOUNDS["break_start"])

    def _close_pond(self, now):
        self.boss_hidden = False
        if self.session.state == S.HIDDEN:
            return
        self.session.hide(now)
        self.pond.flash("摸鱼时间到，回去干活啦 🍅", now, 3.0)
        P.play(SOUNDS["break_end"])

    def _on_pond_click(self, x, depth=None, y=None):
        now = time.monotonic()
        for ev in self.session.click(now, x, depth, y):
            self._on_session_event(ev, now)

    def _on_pond_resize(self, height, final):
        h = L.clamp_height(height)
        self.pond.configure(height=h)
        if final:
            prefs.set("pond_height", h)

    def _on_session_event(self, ev, now):
        sess, pond = self.session, self.pond
        if ev == S.EV_START_GAME:
            scale = L.panel_scale(pond.column.height(), pond.height)
            self.panel.show(sess.game, sess.cast_x, pond.column, pond.water_top_y(), scale)
        elif ev in (S.EV_CAUGHT, S.EV_ESCAPED):
            r = sess.result
            hold = CATCH_HOLD if r.caught else 0.0
            self.panel.finish(now, hold)       # 钓到时进度条先停在满格一会儿，再出结果
            before = self.collection.caught_species() - (1 if r.is_new else 0)

            def show_toast(r=r, x=sess.cast_x):
                if sess.result is r and sess.state == S.RESULT:
                    self.toast.show_result(r, x, pond.column, pond.water_top_y())
            if hold > 0:
                QTimer.singleShot(int(hold * 1000), show_toast)
            else:
                show_toast()
            if r.caught:
                P.play(SOUNDS["new_fish"] if r.is_new else SOUNDS["caught"])
                print("[桌面摸鱼] 钓到 %s %d 英寸%s" % (r.fish.display_name, r.size,
                                                   "（新鱼种）" if r.is_new else ""))
            else:
                P.play(SOUNDS[S.EV_ESCAPED])
            self.album.refresh()
            self._announce_unlocks(before, now)
        elif ev == S.EV_JUNK:
            self.toast.show_result(sess.result, sess.cast_x, pond.column, pond.water_top_y())
            P.play(SOUNDS[S.EV_JUNK])
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
            P.play(SOUNDS.get(ev))

    def _announce_unlocks(self, before, now):
        after = self.collection.caught_species()
        total = len(self.album.fish)
        old = self.session.bobber_count
        self._refresh_bobbers()
        if self.session.bobber_count > old:
            self.pond.flash("🎣 解锁新浮漂（托盘菜单 → 钓鱼 → 浮漂）", now, 3.0)
        for need, name in MILESTONES + [(total, "钓鱼大师")]:
            if need and before < need <= after:
                self.pond.flash("🏆 图鉴收集 %d 种：%s" % (need, name), now, 4.0)
        for key in world.SPOT_KEYS:
            need = world.unlock_need(key)
            if before < need <= after:
                self.pond.flash("🔓 解锁新钓点：%s（托盘菜单 → 钓鱼）" % world.spot_name(key), now, 4.0)

    # MARK: 种田

    def _farm_on(self):
        return bool(prefs.get("farm", True))

    def _farm_desktop_on(self):
        return bool(prefs.get("farm_desktop", True))

    def _farm_top(self):
        return prefs.get("farm_desk_level", "top") == "top"

    def _item_name(self, item_id):
        it = self.session.junk.get(str(item_id)) if getattr(self, "session", None) else None
        return it.display_name if it is not None else str(item_id)

    def _update_farm_desktop(self):
        show = (self._farm_on() and self._farm_desktop_on() and self.pomo.phase != pomodoro.IDLE
                and self.farm_desk_snooze != self._farm_round())
        was = self.farm_desk.visible
        self.farm_desk.set_visible(show)
        if show and not was:
            self._refresh_farm_desk()

    def _farm_round(self):
        p = self.pomo
        return (p.phase, p.round, p.free_fishing)

    def hide_farm_once(self):
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

    def _farm_day(self, now):
        if not self._farm_on():
            return
        report = farmlib.focus_done(self.farm, self.collection, fishdata.season_of())
        if self.farm_desk.visible:
            self.farm_desk.pop(report.harvested, now)
        elif report.harvested or report.planted or report.gift:
            self.farm_card.show(self.farm, report, now, self.pomo.round)
        self.farm_window.refresh()
        self._refresh_farm_desk()
        self.album.refresh()

    def _gear_changed(self):
        """买了东西 / 选了种子：菜单、农田摆件、我的农田跟着刷新。"""
        self.last_title = 0.0
        if getattr(self, "farm_desk", None) is not None and self.farm_desk.visible:
            self._refresh_farm_desk()
        if getattr(self, "farm_window", None) is not None:
            self.farm_window.refresh()

    # MARK: 菜单动作

    def start_focus(self):
        now = time.monotonic()
        if self.pomo.fishing:
            self._close_pond(now)
        self.pomo.start_focus(now)
        self._farm_focus_start(now)
        self.last_title = 0.0

    def fish_now(self):
        now = time.monotonic()
        self.pomo.start_break(now, minutes=self._break_minutes(), free=True)
        self._open_pond(now)
        self.last_title = 0.0

    def skip_to_break(self):
        now = time.monotonic()
        self.pomo.round += 1
        self.pomo.start_break(now)
        self._open_pond(now)
        self.last_title = 0.0

    def end_break(self):
        now = time.monotonic()
        free = self.pomo.free_fishing
        self._close_pond(now)
        if free:
            self.pomo.stop()
        else:
            self.pomo.start_focus(now)
            self._farm_focus_start(now)
        self.last_title = 0.0

    def pause_resume(self):
        now = time.monotonic()
        self.pomo.resume(now) if self.pomo.paused else self.pomo.pause(now)
        self.last_title = 0.0

    def stop_timer(self):
        now = time.monotonic()
        if self.pomo.fishing:
            self._close_pond(now)
        self.pomo.stop()
        self.last_title = 0.0

    def set_mode(self, mode):
        prefs.set("mode", mode)
        if self.session.state != S.PLAYING:
            self.session.mode = mode

    def set_durations(self, focus, brk):
        """设定时长（超出范围的收回来），返回实际用的 (专注, 摸鱼) 分钟。"""
        focus, brk = MM.clamp_durations(focus, brk)
        prefs.set("durations", [focus, brk])
        self.pomo.focus = focus * 60.0
        self.pomo.short_break = brk * 60.0
        self.pomo.long_break = max(brk * 3, 2) * 60.0
        self.last_title = 0.0
        return focus, brk

    def custom_durations(self, accept=None):
        """自己填专注和摸鱼各几分钟（原版风格的对话框：◀ ▶ 加减，也能直接打数字）。

        accept 给测试用：拿到对话框内容（dialog_model.Dialog）直接填，返回 True 就当点了「好」。"""
        focus, brk = prefs.get("durations", [25, 5])
        model = dialog_model.durations_dialog(focus, brk, FOCUS_RANGE, BREAK_RANGE)
        if accept is not None:
            return self.set_durations(*model.values()) if accept(model) else None

        def done(key, values):
            if key == "ok":
                self.set_durations(*values)
        self.dialog = GameDialog(model, done).show()
        return None

    def set_spot(self, key):
        if world.is_unlocked(key, self.collection.caught_species()):
            prefs.set("spot", key)
            self.session.spot = key
            if self.pond.visible:
                self.pond.flash("换到「%s」" % world.spot_name(key), time.monotonic())

    def set_pond_width(self, mode):
        prefs.set("pond_width", mode)
        self.pond.configure(width_mode=mode)

    def set_pond_alpha(self, value):
        prefs.set("pond_alpha", value)
        self.pond.configure(alpha=value)

    def toggle_farm(self):
        prefs.set("farm", not self._farm_on())

    def set_farm_top(self, on_top):
        prefs.set("farm_desk_level", "top" if on_top else "desktop")
        self.farm_desk.set_on_top(on_top)

    def toggle_farm_desktop(self):
        prefs.set("farm_desktop", not self._farm_desktop_on())
        self._update_farm_desktop()
        self._refresh_farm_desk()

    def toggle_sound(self):
        P.sound_enabled = not P.sound_enabled
        prefs.set("sound", P.sound_enabled)

    def rebuild_assets(self):
        try:
            gamecontent.ensure_cache(game_dir=prefs.get("game_dir"), force=True)
        except Exception as exc:
            self._message("重新读取失败", str(exc))
            return
        from PySide6.QtCore import QProcess
        _release_lock()                              # 不然新进程会以为「已经在运行」
        if getattr(sys, "frozen", False):            # 打包成 exe 时
            QProcess.startDetached(sys.executable, sys.argv[1:])
        else:
            QProcess.startDetached(sys.executable, [os.path.abspath(sys.argv[0])] + sys.argv[1:])
        self.quit()

    def quit(self):
        if self.hotkeys is not None:
            self.hotkeys.unregister_all()
        if self.tray is not None:
            self.tray.hide()
        self.qapp.quit()


def _pick_font():
    families = set(QFontDatabase.families())
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC",
                 "Noto Serif CJK SC"):
        if name in families:
            C.FONT_FAMILY = name
            return


_lock = []


def _single_instance():
    """只允许开一个：重复双击时提示它已经在托盘里了（托盘图标常被 Windows 收进 ^ 里）。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    lock = QLockFile(os.path.join(DATA_DIR, "deskpond.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(200):
        return False
    _lock.append(lock)
    return True


def _release_lock():
    while _lock:
        _lock.pop().unlock()


def main():
    qapp = QApplication.instance() or QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setQuitOnLastWindowClosed(False)       # 关掉图鉴窗口不退出，托盘里还在
    if not SELFTEST and not _single_instance():
        box = QMessageBox(QMessageBox.Information, APP_NAME, "桌面摸鱼已经在运行了。\n\n" + TRAY_HINT)
        box.setWindowFlag(Qt.WindowStaysOnTopHint)
        box.exec()
        return 0
    _pick_font()
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("[桌面摸鱼] 这个系统没有托盘区，只能用快捷键 %s 打开菜单" % MENU_KEY_LABEL)
    app = App(qapp)
    if not app.start():
        return 1
    if SELFTEST:
        print("[桌面摸鱼] 自检通过")
        QTimer.singleShot(3000, app.quit)
    return qapp.exec()
