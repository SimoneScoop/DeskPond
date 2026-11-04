# -*- coding: utf-8 -*-
"""Windows 专属的几件事（ctypes 直接调 Win32），其他系统上退化成 Qt 自带的做法，方便开发调试。

    - 点击穿透：鱼塘窗口只有水那一块接收点击，其余地方点下去是后面的窗口
    - 不抢焦点：点水面钓鱼时，你正在用的软件还是当前窗口
    - 全局按住鼠标：溜鱼时不管鼠标在哪按住都算（和 Mac 版一样）
    - 全局快捷键：Ctrl+Alt+F 老板键、Ctrl+Alt+M 在鼠标处打开菜单
    - 系统提示音
"""
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

IS_WIN = sys.platform.startswith("win")

if IS_WIN:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_LAYERED = 0x00080000
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOOLWINDOW = 0x00000080
    WM_HOTKEY = 0x0312
    MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
    VK_LBUTTON, VK_ESCAPE = 0x01, 0x1B
    try:
        _get_long = user32.GetWindowLongPtrW
        _set_long = user32.SetWindowLongPtrW
    except AttributeError:          # 32 位 Python
        _get_long = user32.GetWindowLongW
        _set_long = user32.SetWindowLongW
    _get_long.restype = ctypes.c_ssize_t
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _set_long.restype = ctypes.c_ssize_t
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

OVERLAY_FLAGS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                 | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)


def _hwnd(widget):
    return int(widget.winId())


def _set_ex(widget, bits, on):
    hwnd = _hwnd(widget)
    ex = _get_long(hwnd, GWL_EXSTYLE)
    new = (ex | bits) if on else (ex & ~bits)
    if new != ex:
        _set_long(hwnd, GWL_EXSTYLE, new)


def make_overlay(widget, click_through=True):
    """透明、无边框、置顶、不进任务栏、不抢焦点的浮层窗口。"""
    widget.setWindowFlags(OVERLAY_FLAGS)
    widget.setAttribute(Qt.WA_TranslucentBackground, True)
    widget.setAttribute(Qt.WA_ShowWithoutActivating, True)
    widget._click_through = None
    if IS_WIN:
        widget.winId()                    # 先把原生窗口建出来
        _set_ex(widget, WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_LAYERED, True)
    set_click_through(widget, click_through)


def set_no_activate(widget):
    """点它不抢焦点、不进任务栏（Windows 扩展样式；其他系统靠 Qt 标志已经够了）。"""
    if IS_WIN:
        widget.winId()
        _set_ex(widget, WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, True)


def set_click_through(widget, on):
    """切换点击穿透。Windows 上直接改扩展样式，不闪；其他系统用 Qt 的标志（要重新显示一下）。"""
    on = bool(on)
    if getattr(widget, "_click_through", None) == on:
        return
    widget._click_through = on
    if IS_WIN:
        widget.winId()
        _set_ex(widget, WS_EX_TRANSPARENT, on)
    else:
        visible = widget.isVisible()
        widget.setWindowFlag(Qt.WindowTransparentForInput, on)
        if visible:
            widget.show()


def left_button_down():
    if IS_WIN:
        return bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
    return bool(QGuiApplication.mouseButtons() & Qt.LeftButton)


def esc_down():
    if IS_WIN:
        return bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)
    return False


class _HotkeyFilter(QAbstractNativeEventFilter):
    """应用级的消息过滤：WM_HOTKEY 不管发到哪个窗口、还是发到线程队列，都在这里接住。"""

    def __init__(self, owner):
        super(_HotkeyFilter, self).__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        return self.owner.handle_native(event_type, message)


class HotkeyWindow(QWidget):
    """一个看不见的窗口，专门接 RegisterHotKey 发来的 WM_HOTKEY。"""

    def __init__(self):
        super(HotkeyWindow, self).__init__()
        self.callbacks = {}
        self.registered = []
        self._filter = None
        if IS_WIN:
            from PySide6.QtCore import QCoreApplication
            self._filter = _HotkeyFilter(self)
            QCoreApplication.instance().installNativeEventFilter(self._filter)

    def register(self, hid, key, callback):
        """key 是字母，比如 "F"：注册 Ctrl+Alt+<key>。成功返回 True。"""
        if not IS_WIN:
            return False
        ok = bool(user32.RegisterHotKey(wintypes.HWND(_hwnd(self)), hid,
                                        MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord(key.upper())))
        if ok:
            self.callbacks[hid] = callback
            self.registered.append(hid)
        return ok

    def unregister_all(self):
        if IS_WIN:
            for hid in self.registered:
                user32.UnregisterHotKey(wintypes.HWND(_hwnd(self)), hid)
        self.registered = []

    def nativeEvent(self, event_type, message):
        return self.handle_native(event_type, message)

    def handle_native(self, event_type, message):
        if IS_WIN and event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam in self.callbacks:
                try:
                    self.callbacks[msg.wParam]()
                except Exception:
                    import traceback
                    traceback.print_exc()
                return True, 0
        return False, 0


# MARK: 声音

SOUND_ALIASES = {"start": "SystemAsterisk", "end": "SystemNotification", "cast": "SystemDefault",
                 "bite": "SystemExclamation", "caught": "SystemAsterisk", "new": "SystemHand",
                 "escaped": "SystemDefault", "junk": "SystemDefault"}
sound_enabled = False


def play(kind):
    if not sound_enabled or not kind:
        return
    if IS_WIN:
        try:
            import winsound
            winsound.PlaySound(SOUND_ALIASES.get(kind, "SystemDefault"),
                               winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass
    else:
        QGuiApplication.beep() if hasattr(QGuiApplication, "beep") else None
