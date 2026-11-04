# -*- coding: utf-8 -*-
"""图鉴、钓具店、我的农田这类窗口的共同部分：没有系统边框，原版的框直接浮在桌面上；
右上角原版红叉、Esc、Ctrl+W 都能关；空白处按住拖动。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from . import qtdraw as C


class GameWindow(QWidget):

    def __init__(self, width, height, title):
        super(GameWindow, self).__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle(title)
        self.setFixedSize(int(width), int(height))
        self.setMouseTracking(True)
        self.close_rect = None

    def center(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + (g.height() - self.height()) // 2)

    def present(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape or (e.key() == Qt.Key_W and e.modifiers() & Qt.ControlModifier):
            self.hide()
            return
        super(GameWindow, self).keyPressEvent(e)

    def mousePressEvent(self, e):
        p = e.position()
        if C.in_rect(p.x(), p.y(), self.close_rect):
            self.hide()
            return
        if not self.on_click(p.x(), p.y()) and e.button() == Qt.LeftButton:
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemMove()        # 空白处按住拖动窗口

    def on_click(self, x, y):
        """子类处理点击；处理了返回 True，没处理返回 False（就当拖动窗口）。"""
        return False
