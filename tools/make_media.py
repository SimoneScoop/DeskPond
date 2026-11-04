#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""录 README 用的演示动图：离屏跑一遍 Windows 版（Qt），用 _game_ref/ 里的原版贴图和字体。

    python3 tools/copy_ref.py          # 先把用到的原版素材复制到 _game_ref/
    python3 tools/make_media.py        # -> docs/media/*.gif

需要 PySide6 和 Pillow。动图里有游戏画面，只用来在 README 里展示；仓库里不放任何游戏素材文件本身。
"""
import os
import random
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
SCREEN = (1280, 860)        # 离屏「显示器」的大小：图鉴、钓具店 + 我的农田要放得下
_cfg = os.path.join(tempfile.gettempdir(), "deskpond_media_screens.json")
with open(_cfg, "w") as _fh:
    _fh.write('{"screens": [{"name": "main", "x": 0, "y": 0, "width": %d, "height": %d, '
              '"logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}' % SCREEN)
os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=" + _cfg

from PIL import Image, ImageDraw   # noqa: E402

import test_qt_smoke as T          # noqa: E402  复用测试里搭假游戏目录的那一套

OUT = os.path.join(ROOT, "docs", "media")
FPS = 12
STEP = 1.0 / 60.0

# 动图里用中文名
T.ZH.update({"Cauliflower": "花椰菜", "Potato": "土豆", "Kale": "甘蓝", "Melon": "甜瓜", "Tomato": "番茄",
             "Hot Pepper": "辣椒", "Wheat": "小麦", "Corn": "玉米", "Eggplant": "茄子", "Pumpkin": "南瓜",
             "Bok Choy": "小白菜", "Parsnip Seeds": "防风草种子", "Cauliflower Seeds": "花椰菜种子",
             "Potato Seeds": "土豆种子", "Kale Seeds": "甘蓝种子", "Eggplant Seeds": "茄子种子",
             "Pumpkin Seeds": "南瓜种子", "Bok Choy Seeds": "小白菜种子", "Corn Seeds": "玉米种子",
             "Quartz": "石英", "Amethyst": "紫水晶", "Seaweed": "海草", "Green Algae": "绿藻"})


# MARK: 画面

def desktop(w, h):
    """假桌面：渐变底 + 一个「正在上班」的表格窗口，让人一眼看出这是工作时的屏幕。"""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        k = y / float(h)
        d.line([(0, y), (w, y)], fill=(int(58 + 30 * k), int(78 + 34 * k), int(120 + 30 * k)))
    x0, y0, x1, y1 = 40, 40, w - 60, h - 230
    d.rounded_rectangle([x0 + 6, y0 + 8, x1 + 6, y1 + 8], 12, fill=(30, 40, 70))
    d.rounded_rectangle([x0, y0, x1, y1], 12, fill=(250, 250, 252))
    d.rounded_rectangle([x0, y0, x1, y0 + 34], 12, fill=(232, 234, 240))
    d.rectangle([x0, y0 + 20, x1, y0 + 34], fill=(232, 234, 240))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([x0 + 14 + i * 20, y0 + 11, x0 + 26 + i * 20, y0 + 23], fill=c)
    gx, gy = x0 + 16, y0 + 50
    for r in range(int((y1 - gy - 16) // 26)):
        for c in range(6):
            cx = gx + c * ((x1 - x0 - 32) / 6.0)
            d.rectangle([cx, gy + r * 26, cx + (x1 - x0 - 32) / 6.0 - 4, gy + r * 26 + 20],
                        fill=(236, 240, 246) if r == 0 else (246, 247, 250))
            if r and (r * 7 + c * 3) % 5:
                d.rectangle([cx + 6, gy + r * 26 + 8, cx + 6 + ((r * 13 + c * 29) % 60) + 20, gy + r * 26 + 12],
                            fill=(205, 210, 222))
    return img


def to_pil(pixmap):
    from PySide6.QtGui import QImage
    img = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
    return Image.frombuffer("RGBA", (img.width(), img.height()), bytes(img.constBits()), "raw", "RGBA", 0, 1)


def cursor(img, x, y, down=False):
    """画一个鼠标指针（按下时缩一点）。"""
    s = 0.85 if down else 1.0
    pts = [(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12)]
    pts = [(x + px * s, y + py * s) for px, py in pts]
    d = ImageDraw.Draw(img)
    d.polygon(pts, fill=(255, 255, 255), outline=(20, 20, 20))


class Recorder(object):
    def __init__(self, qapp, size):
        self.qapp = qapp
        self.bg = desktop(*size)
        self.frames = []

    def snap(self, widgets, mouse=None, down=False):
        self.qapp.processEvents()
        img = self.bg.copy().convert("RGBA")
        for w in widgets:
            if w is not None and w.isVisible():
                g = w.frameGeometry()
                img.alpha_composite(to_pil(w.grab()), (g.x(), g.y()))
        if mouse is not None:
            cursor(img, mouse.x(), mouse.y(), down)
        self.frames.append(img)

    def save(self, name, box=None, scale=1.0, hold_last=1.2):
        frames = self.frames
        if box:
            frames = [f.crop(box) for f in frames]
        if scale != 1.0:
            frames = [f.resize((int(f.width * scale), int(f.height * scale)), Image.LANCZOS) for f in frames]
        # 所有帧共用一个调色板（从几帧拼起来取色），没变的像素前后帧一样，GIF 才压得小
        rgb = [f.convert("RGB") for f in frames]
        picks = rgb[::max(1, len(rgb) // 6)][:8]
        strip = Image.new("RGB", (picks[0].width, picks[0].height * len(picks)))
        for i, f in enumerate(picks):
            strip.paste(f, (0, i * f.height))
        pal = strip.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE)
        frames = [f.quantize(palette=pal, dither=Image.NONE) for f in rgb]
        durations = [int(1000 / FPS)] * len(frames)
        durations[-1] = int(hold_last * 1000)
        path = os.path.join(OUT, name)
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=0,
                       optimize=True, disposal=1)
        print("  %s  %d 帧  %.0f KB" % (name, len(frames), os.path.getsize(path) / 1024.0))
        self.frames = []


# MARK: 场景

def main():
    if not os.path.isfile(os.path.join(ROOT, "_game_ref", "LooseSprites_Cursors.xnb")):
        print("先运行 python3 tools/copy_ref.py，把原版素材复制到 _game_ref/")
        return 1
    os.makedirs(OUT, exist_ok=True)
    from src import gamecontent as gc, prefs, collection as colmod
    from src import session as S
    from src import minigame
    tmp = tempfile.mkdtemp(prefix="deskpond_media_")
    try:
        gc.CACHE_ROOT = os.path.join(tmp, "cache")
        prefs.PREFS_DIR = tmp
        prefs.PREFS_PATH = os.path.join(tmp, "prefs.json")
        prefs.save({"welcomed": True, "sound": False})
        colmod.DEFAULT_PATH = os.path.join(tmp, "collection.json")
        game, _ = T.make_game(tmp)
        os.environ["DESKPOND_GAME_DIR"] = game

        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        from src.win import app as appmod
        from src.win import platform as P
        qapp = QApplication.instance() or QApplication([])
        appmod._pick_font()
        clock = {"t": 1000.0}
        appmod.time.monotonic = lambda: clock["t"]
        mouse = {"down": False, "pos": QPoint(600, 300)}
        P.left_button_down = lambda: mouse["down"]
        appmod.QCursor.pos = staticmethod(lambda: mouse["pos"])

        a = appmod.App(qapp)
        if not a.start():
            print("启动失败")
            return 1
        size = SCREEN
        rec = Recorder(qapp, size)

        def run(seconds, widgets, press=None, every=None):
            every = every or max(1, int(round(1.0 / (FPS * STEP))))
            n = int(seconds / STEP)
            for i in range(n):
                mouse["down"] = bool(press and press())
                clock["t"] += STEP
                a._on_tick()
                if i % every == 0:
                    rec.snap(widgets(), mouse["pos"], mouse["down"])

        def glide(to, seconds, widgets):
            """鼠标平滑移过去。"""
            start = QPoint(mouse["pos"])
            n = max(1, int(seconds * FPS))
            for i in range(1, n + 1):
                k = i / float(n)
                k = k * k * (3 - 2 * k)
                mouse["pos"] = QPoint(int(start.x() + (to.x() - start.x()) * k),
                                      int(start.y() + (to.y() - start.y()) * k))
                clock["t"] += 1.0 / FPS
                a._on_tick()
                rec.snap(widgets(), mouse["pos"])

        print("== 录制")
        # ---------- 1. 钓鱼 ----------
        a.collection.give("685", 0)
        a.set_durations(25, 5)
        prefs.set("farm_desktop", False)
        pond = lambda: [a.pond.widget, a.panel.widget, a.toast.widget]
        a.fish_now()
        run(1.6, pond)
        geo = a.pond.widget.geometry()
        target = QPoint(geo.x() + int(geo.width() * 0.72), geo.y() + geo.height() - 60)
        glide(target, 0.6, pond)
        a.session.rng = random.Random(5)
        mouse["down"] = True
        rec.snap(pond(), mouse["pos"], True)
        a._on_pond_click(0.72, None, 0.45)
        mouse["down"] = False
        a.session.bite_at = min(a.session.bite_at, clock["t"] + 1.5)   # 动图不拖沓：1.5 秒内咬钩
        while a.session.state == S.WAITING:
            run(0.1, pond)
        run(0.35, pond)
        a._on_pond_click(0.72)
        a.session.game.treasure, a.session.game.treasure_at = True, 0.4

        def good():
            g = a.session.game
            if g is None:
                return False
            c = g.fish_pos + minigame.FISH_SIZE / 2
            m = g.bar_pos + g.bar_height / 2
            return (c - m) - (g.bar_vel - g.fish_vel) * 0.25 < 0
        t0 = clock["t"]
        top = a.panel.widget.geometry().y() - 16
        while a.session.state == S.PLAYING and clock["t"] - t0 < 14:
            run(0.2, pond, press=good)
        run(1.8, pond)
        rec.save("fishing.gif", box=(400, max(0, top), SCREEN[0], SCREEN[1]), scale=0.8)

        # 钓完再塞几条，图鉴和农田好看些
        for fid, cnt, size_, q in (("128", 2, 22, 2), ("137", 5, 17, 1), ("145", 9, 12, 3), ("143", 1, 40, 0)):
            a.collection.fish[fid] = {"count": cnt, "max_size": size_, "best_quality": q, "perfect": 1}
        for item in ("152", "153", "80", "66", "685"):
            a.collection.items[item] = a.collection.items.get(item, 0) + 1
        a.collection.crops.update({"24": 3, "190": 1, "276": 1})
        a.boss_toggle() if a.session.state != S.HIDDEN else None
        a.stop_timer()
        run(0.3, lambda: [])

        # ---------- 2. 桌面农田 ----------
        prefs.set("farm_desktop", True)
        a.collection.farm_started = True
        a.collection.farm[:] = [{"seed": "474", "days": 3}, {"seed": "472", "days": 2}, {"seed": "490", "days": 9}]
        a.set_durations(25, 5)
        a.start_focus()
        farm = lambda: [a.farm_desk.view]
        mouse["pos"] = QPoint(120, SCREEN[1] - 80)       # 先别在农田上：平时只显示倒计时
        run(0.4, farm)
        for _ in range(16):                       # 倒计时快进
            clock["t"] += 15
            run(0.13, farm)
        g = a.farm_desk.view.frameGeometry()
        glide(QPoint(g.center().x() + 10, g.center().y() + 20), 0.7, farm)
        run(1.6, farm)
        glide(QPoint(120, SCREEN[1] - 80), 0.5, farm)
        for _ in range(3):                         # 连做几个番茄：作物一天天长，成熟的收获、冒出来
            a._farm_day(clock["t"])
            a.pomo.phase = "break"
            run(0.9, farm)
            a.pomo.phase = "focus"
            run(0.5, farm)
        box = (g.x() - 10, g.y() - 10, g.x() + g.width() + 10, g.y() + g.height() + 10)
        rec.save("farm.gif", box=box, scale=1.0, hold_last=1.5)
        a.stop_timer()
        run(0.2, lambda: [])

        # ---------- 3. 图鉴 ----------
        a.album.show()
        v = a.album.view
        v.move(40, 30)
        win = lambda: [a.album.view]
        rec.snap(win(), mouse["pos"])

        def hits(kind):
            v.repaint()
            v.grab()
            return [(k, val, r) for k, val, r in v.hits if k == kind]

        def at(r):
            return QPoint(v.x() + int(r[0] + r[2] / 2), v.y() + int(r[1] + r[3] / 2))
        a.album.set_page("fish", "all")
        cells = hits("cell")
        if cells:
            glide(at(cells[2][2] if len(cells) > 2 else cells[0][2]), 0.7, win)
            v.hover = cells[2][1] if len(cells) > 2 else cells[0][1]
            v.update()
            run(1.4, win)
        for page in ("items", "crops", "bobbers"):
            tab = [r for k, val, r in hits("page") if val == page]
            if tab:
                glide(at(tab[0]), 0.5, win)
                v.on_click(tab[0][0] + 5, tab[0][1] + 5)
                v.hover = None
                run(0.9, win)
        gw = v.frameGeometry()
        rec.save("album.gif", box=(gw.x() - 10, gw.y() - 10, gw.right() + 10, gw.bottom() + 10), scale=0.9)
        a.album.view.hide()

        # ---------- 4. 买种子 → 选种 ----------
        a.collection.xp, a.collection.gold = 900, 1200
        a.shop.show(page="seeds")
        sv = a.shop.view
        sv.season = lambda: "fall"
        sv.move(30, 40)
        shopw = lambda: [a.shop.view, a.farm_window.view]
        run(0.4, shopw)

        def shop_hit(kind, key):
            sv.repaint()
            sv.grab()
            for (k, val), r in sv.hits:
                if k == kind and val == key:
                    return r
        r = shop_hit("seed", "490")
        if r:
            glide(QPoint(sv.x() + int(r[0] + r[2] / 2), sv.y() + int(r[1] + r[3] / 2)), 0.7, shopw)
            sv.on_click(r[0] + 5, r[1] + 5)
            run(0.8, shopw)
        a.collection.farm[0] = None
        a.farm_window.show()
        fv = a.farm_window.view
        fv.move(sv.x() + sv.width() + 24, 60)
        a.farm_window.refresh()
        run(0.4, shopw)
        fv.repaint()
        fv.grab()
        pr = [r for (k, val), r in fv.hits if k == "plot" and val == 0]
        if pr:
            p = pr[0]
            glide(QPoint(fv.x() + int(p[0] + p[2] / 2), fv.y() + int(p[1] + p[3] - 30)), 0.6, shopw)
            fv.on_click(p[0] + p[2] / 2, p[1] + p[3] - 30)
            run(0.6, shopw)
            fv.repaint()
            fv.grab()
            sr = [r for (k, val), r in fv.hits if k == "seed" and val == "490"]
            if sr:
                s_ = sr[0]
                glide(QPoint(fv.x() + int(s_[0] + s_[2] / 2), fv.y() + int(s_[1] + s_[3] / 2)), 0.6, shopw)
                fv.on_click(s_[0] + 5, s_[1] + 5)
                run(1.4, shopw)
        x0 = min(sv.x(), fv.x()) - 10
        y0 = min(sv.y(), fv.y()) - 10
        x1 = max(sv.frameGeometry().right(), fv.frameGeometry().right()) + 10
        y1 = max(sv.frameGeometry().bottom(), fv.frameGeometry().bottom()) + 10
        rec.save("shop.gif", box=(max(0, x0), max(0, y0), min(SCREEN[0], x1), min(SCREEN[1], y1)), scale=0.75)

        # ---------- 5. 原版风格的对话框 ----------
        a.custom_durations()
        dv = a.dialog.view
        dv.move(400, 260)
        dlg = lambda: [a.dialog.view]
        run(0.5, dlg)
        nx = dv.rects["next0"]
        glide(QPoint(dv.x() + int(nx[0] + nx[2] / 2), dv.y() + int(nx[1] + nx[3] / 2)), 0.6, dlg)
        for _ in range(5):
            dv.on_click(nx[0] + 5, nx[1] + 5)
            run(0.25, dlg)
        dg = dv.frameGeometry()
        rec.save("dialog.gif", box=(dg.x() - 10, dg.y() - 10, dg.right() + 10, dg.bottom() + 10), scale=1.0)
        a.dialog.view.hide()
        a.quit()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("动图在 %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
