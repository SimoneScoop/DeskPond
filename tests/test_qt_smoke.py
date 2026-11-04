#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 版（Qt）冒烟测试：离屏跑一整轮（启动 → 专注 → 摸鱼 → 钓鱼 → 图鉴 / 钓具店 / 农田 → 收起）。

    python3 tests/test_qt_smoke.py              # 没装 PySide6 时自动跳过
    python3 tests/test_qt_smoke.py --shots DIR  # 顺便把每个窗口截图存到 DIR（开发时看效果用）

不需要 Windows：Qt 用 offscreen 平台，Win32 那几样（点击穿透、全局快捷键）自动退化。
有 _game_ref/ 里的原版贴图时用原版贴图，没有就用纯色假图。
"""
import json
import os
import random
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FAILED = []


def check(name, got, want):
    ok = got == want
    print("  %s %s%s" % ("✅" if ok else "❌", name, "" if ok else "  (得到 %r，期望 %r)" % (got, want)))
    if not ok:
        FAILED.append(name)


FISH = {
    "128": "Pufferfish/80/floater/1/36/0 2600/spring summer fall winter/both/x/4/.9/.5/0",
    "137": "Smallmouth Bass/28/mixed/12/24/0 2600/spring summer fall winter/both/x/1/.9/.1/0",
    "145": "Sunfish/30/mixed/5/16/0 2600/spring summer fall winter/both/x/1/.9/.1/0",
    "143": "Catfish/75/mixed/12/72/0 2600/spring summer fall winter/both/x/4/.9/.1/0",
}
ZH = {"Pufferfish": "河豚", "Smallmouth Bass": "小嘴鲈鱼", "Sunfish": "太阳鱼", "Catfish": "鲶鱼",
      "Parsnip": "防风草", "Bait": "鱼饵", "Spinner": "旋转亮片", "Trash": "垃圾"}
REAL = {  # _game_ref 里的文件名 -> 游戏里的路径
    "LooseSprites_Cursors.xnb": "LooseSprites/Cursors.xnb",
    "Maps_springobjects.xnb": "Maps/springobjects.xnb",
    "TileSheets_bobbers.xnb": "TileSheets/bobbers.xnb",
    "TileSheets_crops.xnb": "TileSheets/crops.xnb",
    "TerrainFeatures_hoeDirt.xnb": "TerrainFeatures/hoeDirt.xnb",
    "LooseSprites_Fence1.xnb": "LooseSprites/Fence1.xnb",
    "TileSheets_tools.xnb": "TileSheets/tools.xnb",
    "Fonts_SmallFont.zh-CN.xnb": "Fonts/SmallFont.zh-CN.xnb",        # 原版中文字体（有就用）
    "Fonts_SpriteFont1.zh-CN.xnb": "Fonts/SpriteFont1.zh-CN.xnb",
}


def make_game(tmp):
    import test_assets
    content = os.path.join(tmp, "Stardew Valley", "Content")
    ref = os.path.join(ROOT, "_game_ref")
    real = os.path.isfile(os.path.join(ref, "LooseSprites_Cursors.xnb"))
    if real:
        for src, dst in REAL.items():
            if os.path.isfile(os.path.join(ref, src)):
                os.makedirs(os.path.dirname(os.path.join(content, dst)), exist_ok=True)
                shutil.copy(os.path.join(ref, src), os.path.join(content, dst))
    else:
        test_assets.solid_png(os.path.join(content, "LooseSprites", "Cursors.png"), 704, 2256)
        test_assets.solid_png(os.path.join(content, "Maps", "springobjects.png"), 384, 624)
        test_assets.solid_png(os.path.join(content, "TileSheets", "bobbers.png"), 128, 160)
    os.makedirs(os.path.join(content, "Data"), exist_ok=True)
    os.makedirs(os.path.join(content, "Strings"), exist_ok=True)
    with open(os.path.join(content, "Data", "Fish.json"), "w") as fh:
        json.dump(FISH, fh)
    with open(os.path.join(content, "Strings", "Objects.json"), "w") as fh:
        json.dump({k.replace(" ", "") + "_Name": k for k in ZH}, fh)
    with open(os.path.join(content, "Strings", "Objects.zh-CN.json"), "w", encoding="utf-8") as fh:
        json.dump({k.replace(" ", "") + "_Name": v for k, v in ZH.items()}, fh, ensure_ascii=False)
    return os.path.join(tmp, "Stardew Valley"), real


def main():
    try:
        from PySide6 import QtWidgets  # noqa: F401
    except ImportError as exc:
        print("PySide6 用不了（%s），跳过 Windows 版测试（pip install PySide6-Essentials）" % exc)
        return 0
    shots = None
    if "--shots" in sys.argv:
        shots = os.path.abspath(sys.argv[sys.argv.index("--shots") + 1])
        os.makedirs(shots, exist_ok=True)

    from src import gamecontent as gc, prefs, collection as colmod, minigame
    from src import session as S
    tmp = tempfile.mkdtemp(prefix="moyu_qt_")
    try:
        gc.CACHE_ROOT = os.path.join(tmp, "cache")
        prefs.PREFS_DIR = tmp
        prefs.PREFS_PATH = os.path.join(tmp, "prefs.json")
        prefs.save({"welcomed": True})
        colmod.DEFAULT_PATH = os.path.join(tmp, "collection.json")
        game, real = make_game(tmp)
        os.environ["DESKPOND_GAME_DIR"] = game
        print("== 素材：%s" % ("_game_ref 里的原版贴图" if real else "假贴图"))

        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        from src.win import app as appmod
        from src.win import platform as P
        from src.win import qtdraw as C
        qapp = QApplication.instance() or QApplication([])
        appmod._pick_font()
        clock = {"t": 1000.0}
        appmod.time.monotonic = lambda: clock["t"]
        mouse = {"down": False, "pos": QPoint(500, 860)}
        P.left_button_down = lambda: mouse["down"]
        appmod.QCursor.pos = staticmethod(lambda: mouse["pos"])

        def shot(widget, name):
            """画一遍（点击判断要用画出来的按钮位置），需要的话存截图。"""
            if widget is None:
                return
            qapp.processEvents()
            img = widget.grab()
            if shots:
                img.save(os.path.join(shots, name + ".png"))

        print("== 启动")
        a = appmod.App(qapp)
        check("启动成功", a.start(), True)
        check("读到了鱼", len(a.fish_list), 4)
        check("托盘图标", a.tray is not None, True)
        a._build_menu()
        titles = [x.text() for x in a.menu.actions()]
        check("菜单有开始专注", "开始专注 🍅" in titles, True)
        check("菜单有图鉴和农田", all(any(t.startswith(w) for t in titles) for w in ("摸鱼图鉴…", "我的农田…")), True)
        check("没钱时不露出钓具店", any(t.startswith("钓具店") for t in titles), False)

        def sub(menu, *path):
            for prefix in path:
                menu = [x.menu() for x in menu.actions() if x.menu() and x.text().startswith(prefix)][0]
            return menu
        check("设置收进一个子菜单", [x.text().split(" ")[0] for x in sub(a.menu, "设置").actions() if x.menu()],
              ["钓鱼", "时长", "水面", "农田"])
        check("空闲时可以单独摸鱼", any(t.startswith("摸鱼一会儿") for t in titles), True)
        tmenu = [sub(a.menu, "设置", "时长")]
        check("三个固定搭配 + 自定义", [x.text().split("（")[0] for x in tmenu[0].actions() if x.text()],
              ["专注 25 分钟 + 摸鱼 5 分钟", "专注 45 分钟 + 摸鱼 10 分钟", "专注 50 分钟 + 摸鱼 10 分钟",
               "自定义…"])
        check("超出范围收回来", a.set_durations(500, 0), (180, 1))

        def fill(dlg):
            dlg.fields[0].value = 2
            dlg.fields[1].value = 3
            return True
        check("自定义对话框填时长", a.custom_durations(fill), (2, 3))
        a.custom_durations()
        dv = a.dialog.view
        check("原版风格对话框弹出来", dv.isVisible(), True)
        dv.repaint()
        dv.grab()
        nx, ny, nw, nh = dv.rects["next0"]
        dv.on_click(nx + 5, ny + 5)
        check("点 ▶：专注 +1", dv.model.fields[0].value, 3)
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt as _Qt
        QTest.keyClick(dv, _Qt.Key_Down)
        QTest.keyClicks(dv, "12")
        check("Tab/↓ 换到摸鱼，直接打数字", (dv.model.focus, dv.model.fields[1].shown()), (1, "12"))
        shot(dv, "dialog_durations")
        QTest.keyClick(dv, _Qt.Key_Return)
        check("回车 = 好：时长生效", (prefs.get("durations"), dv.isVisible()), ([3, 12], False))
        a.custom_durations()
        QTest.keyClick(a.dialog.view, _Qt.Key_Escape)
        check("Esc = 取消：不改", prefs.get("durations"), [3, 12])
        a._message("重新读取失败", "测试一下很长很长的提示文字，看看会不会自动换行、框会不会跟着变高。" * 2)
        shot(a.dialog.view, "dialog_message")
        a.dialog.view.hide()
        a._build_menu()
        check("菜单显示自定义时长", any(x.text() == "时长 · 专注 3 + 摸鱼 12 分钟"
                                       for x in sub(a.menu, "设置").actions()), True)
        [x for x in sub(a.menu, "设置", "时长").actions() if x.text().startswith("专注 45")][0].trigger()
        check("在托盘菜单里选 45+10", prefs.get("durations"), [45, 10])

        def tick(seconds, press=None):
            end = clock["t"] + seconds
            while clock["t"] < end:
                mouse["down"] = bool(press and press())
                clock["t"] += 1 / 60.0
                a._on_tick()

        print("== 专注 → 摸鱼")
        a.set_durations(1, 1)
        a.collection.give("472", 3)
        a.start_focus()
        check("开始专注就播种", any(not a.farm.empty(k) for k in range(3)), True)
        check("农田默认显示、浮在窗口上面", (a.farm_desk.visible, a.farm_desk.view.on_top), (True, True))
        tick(0.6)
        check("农田下面有倒计时", a.farm_desk.view.caption.startswith("🍅"), True)
        check("专注时地是浇过水的", (a.farm_desk.view.watered, os.path.isfile(gc.ui_path("dirt_wl"))),
              (True, True))
        shot(a.farm_desk.view, "farm_desk_focus")
        a._build_menu()
        ft = [x.text() for x in a.menu.actions()]
        check("专注中：暂停 / 提前结束 / 放弃", all(t in ft for t in ("暂停专注", "提前结束专注，去摸鱼",
                                                                  "放弃这个番茄")), True)
        a.set_farm_top(False)
        check("可以改成压在桌面上", (a.farm_desk.view.on_top, a.farm_desk.visible), (False, True))
        a.set_farm_top(True)
        mouse["pos"] = QPoint(5, 5)
        tick(0.6)
        check("平时只显示倒计时", a.farm_desk.view.caption.count("·"), 0)
        mouse["pos"] = a.farm_desk.view.frameGeometry().center()
        tick(0.1)
        check("鼠标移上去展开完整进度", "·" in a.farm_desk.view.caption, True)
        shot(a.farm_desk.view, "farm_desk_hover")
        mouse["pos"] = QPoint(5, 5)
        tick(0.1)
        cm = a.farm_desk.on_menu()
        acts = [x for x in cm.actions() if x.text()]
        check("农田右键菜单", acts[0].text(), "这一轮先收起来")
        acts[0].trigger()
        tick(0.6)
        check("右键收起：这一轮不显示", (a.farm_desk.visible, a._farm_desktop_on()), (False, True))
        a.farm_desk_snooze = None
        tick(0.6)
        check("收起后下一轮自己回来", a.farm_desk.visible, True)
        tick(61)
        check("专注结束水面出现", a.pond.visible, True)
        tick(1.5)
        check("水面升起", a.session.state, S.IDLE)
        geo = a.pond.widget.geometry()
        check("水面贴着屏幕底部", geo.y() + geo.height(), a.pond.column.y() + a.pond.column.height())
        mouse["pos"] = QPoint(geo.x() + 400, geo.y() + geo.height() - 20)
        tick(0.05)
        check("鼠标在水上：接收点击", a.pond.widget._click_through, False)
        mouse["pos"] = QPoint(geo.x() + 400, geo.y() - 200)
        tick(0.05)
        check("鼠标在别处：穿透", a.pond.widget._click_through, True)
        shot(a.pond.widget, "pond_idle")
        a._build_menu()
        bt = [x.text() for x in a.menu.actions()]
        check("摸鱼中：暂停 / 开始专注 / 结束摸鱼", all(t in bt for t in ("暂停摸鱼", "不摸了，开始专注 🍅",
                                                                     "结束摸鱼")), True)
        check("摸鱼中没有「停止番茄钟」", any("停止" in t for t in bt), False)
        check("摸鱼中的进度字", a.farm_desk.view.caption.startswith("🐟"), True)
        pm = a.pond.widget.on_menu()
        pt = [x.text() for x in pm.actions()]
        check("水面右键：藏起来 / 开始专注 / 结束摸鱼",
              (pt[0].startswith("藏起来"), "不摸了，开始专注 🍅" in pt, "结束摸鱼" in pt), (True, True, True))

        print("== 抛竿 → 咬钩 → 溜鱼")
        a.session.rng = random.Random(3)
        a._on_pond_click(0.4, None, 0.3)
        check("抛竿", a.session.state, S.WAITING)
        tick(0.2)
        shot(a.pond.widget, "pond_waiting")
        while a.session.state == S.WAITING:
            tick(0.1)
        check("咬钩", a.session.state, S.BITE)
        tick(0.3)
        shot(a.pond.widget, "pond_bite")
        a._on_pond_click(0.4)
        check("开始小游戏", a.session.state, S.PLAYING)
        check("竖条出现在水面上方", a.panel.widget.geometry().bottom() < a.pond.water_top_y(), True)
        a.session.game.treasure, a.session.game.treasure_at = True, 0.0

        def good():
            g = a.session.game
            if g is None:
                return False
            c = g.fish_pos + minigame.FISH_SIZE / 2
            m = g.bar_pos + g.bar_height / 2
            return (c - m) - (g.bar_vel - g.fish_vel) * 0.25 < 0
        tick(1.0, good)
        shot(a.panel.widget, "panel")
        while a.session.state == S.PLAYING:
            tick(0.1, good)
        check("出结果", a.session.state, S.RESULT)
        check("结果提示出现", a.toast.visible, True)
        shot(a.toast.widget, "toast")

        print("== 窗口")
        used = []
        real_ui = C.ui
        C.ui = lambda k: (used.append(k), real_ui(k))[1]
        a.album.show()
        a.album.view.repaint()
        a.album.view.grab()
        C.ui = real_ui
        check("鱼标签不用带红叉的原图", "tab_fish" in used, False)
        check("图鉴打开", a.album.view.isVisible(), True)
        shot(a.album.view, "album_fish")
        a.album.set_page("fish", "all")
        a.album.view.selected = a.album.view.entries[0]
        a.album.view.update()
        shot(a.album.view, "album_fish_tip")
        for page in ("items", "crops", "bobbers"):
            a.album.set_page(page)
            shot(a.album.view, "album_" + page)
        check("浮漂页 39 种", len(a.album.view.entries), 39 if real else 39)
        a.album.view.on_click(*[v + 5 for v in [r for k, val, r in a.album.view.hits
                                                 if k == "random"][0][:2]])
        check("图鉴里选随机浮漂", a.session.bobber_pref, "random")
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        QTest.keyClick(a.album.view, Qt.Key_Escape)
        check("Esc 关掉图鉴", a.album.view.isVisible(), False)

        a.collection.xp, a.collection.gold = 400, 5000
        a.shop.show()
        shot(a.shop.view, "shop")
        btn = [r for (kind, key), r in a.shop.view.hits if key == "fiberglass"][0]
        a.shop.view.on_click(btn[0] + 5, btn[1] + 5)
        check("钓具店买玻璃纤维钓竿", (a.session.gear.rod, a.collection.gold), ("fiberglass", 3200))
        shot(a.shop.view, "shop_after")
        from src import farm as farmlib, fishdata
        tab = [r for (kind, key), r in a.shop.view.hits if kind == "page" and key == "seeds"][0]
        a.shop.view.on_click(tab[0] + 5, tab[1] + 5)
        a.shop.view.repaint()
        a.shop.view.grab()
        sale = farmlib.seeds_for_sale(fishdata.season_of())
        check("种子栏只卖当季的", sorted(k for (kind, k), _ in a.shop.view.hits if kind == "seed"),
              sorted(s for s in sale if farmlib.SEED_PRICES[s] <= a.collection.gold))
        if sale:
            seed = sale[0]
            before, n = a.collection.gold, a.collection.count(seed)
            btn = [r for (kind, k), r in a.shop.view.hits if k == seed][0]
            a.shop.view.on_click(btn[0] + 5, btn[1] + 5)
            check("买一包种子：扣钱、多一包", (a.collection.gold, a.collection.count(seed)),
                  (before - farmlib.SEED_PRICES[seed], n + 1))
        shot(a.shop.view, "shop_seeds")
        print("== 农田扩建")
        a.collection.xp, a.collection.gold = 1300, 3000      # 钓鱼 4 级
        a.shop.view.repaint()
        a.shop.view.grab()
        ex = [r for (kind, k), r in a.shop.view.hits if kind == "expand"]
        check("够等级够钱：能扩建", len(ex), 1)
        a.shop.view.on_click(ex[0][0] + 5, ex[0][1] + 5)
        check("扩建成 6 块地", (a.farm.size, a.farm.rows, a.collection.gold), (6, 2, 500))
        a.shop.view.repaint()
        a.shop.view.grab()
        check("扩建后按钮变成「已扩建」", [k for (kind, k), _ in a.shop.view.hits if kind == "expand"], [])
        a.collection.farm[4] = {"seed": "474", "days": 5}
        a.collection.farm[5] = {"seed": "472", "days": 1}
        a.shop.view.page = "gear"
        x, y, w, h = a.shop.view.close_rect
        QTest.mouseClick(a.shop.view, Qt.LeftButton, pos=QPoint(int(x + 5), int(y + 5)))
        check("红叉关掉钓具店", a.shop.view.isVisible(), False)

        a.farm_window.show()
        shot(a.farm_window.view, "farm_window")
        fw = a.farm_window.view
        a.collection.farm[0] = None
        a.collection.give("474", 1)
        a.farm_window.refresh()
        fw.repaint()
        fw.grab()
        r = [r for (kind, k), r in fw.hits if kind == "plot" and k == 0][0]
        fw.on_click(r[0] + r[2] / 2, r[1] + r[3] / 2)
        fw.repaint()
        fw.grab()
        check("点地打开选种子", fw.choosing, 0)
        shot(fw, "farm_window_choose")
        r = [r for (kind, k), r in fw.hits if kind == "seed" and k == "474"][0]
        fw.on_click(r[0] + 5, r[1] + 5)
        check("选花椰菜：空地马上种上", (a.farm.info(0)["seed"], a.collection.farm_plan[0]), ("474", "474"))
        fw.repaint()
        fw.grab()
        check("地下面显示「下次：…」", any(k == "plot" for (k, _), _ in fw.hits), True)
        check("种子已经种下", any(not a.farm.empty(k) for k in range(3)), True)
        n0 = sum(a.collection.count(s) for s in ("472", "474", "475", "477", "479", "480", "482",
                                                 "483", "487", "488", "490", "491"))
        a.collection.give("474", 5)
        tick(0.6)
        check("「我的农田」实时更新", any("手上 %d 包" % (n0 + 5) in l for l in a.farm_window.view.lines), True)

        print("== 农田卡片 / 桌面农田")
        a.toggle_farm_desktop()                # 先关掉农田摆件，测卡片
        check("关掉就收起", a.farm_desk.visible, False)
        a.collection.farm[1] = {"seed": "474", "days": 6}
        a.collection.farm[2] = {"seed": "472", "days": 3}
        a._farm_day(clock["t"])
        check("有收获：弹农田卡片", a.farm_card.visible, True)
        shot(a.farm_card.view, "farm_card")
        a.toggle_farm_desktop()
        check("番茄钟在跑时摆上桌面", a.farm_desk.visible, True)
        a.collection.farm[0] = {"seed": "472", "days": 3}
        a._farm_day(clock["t"])
        tick(0.3)
        shot(a.farm_desk.view, "farm_desk")
        check("摆在桌面时不弹卡片", a.farm_card.visible, True)  # 上一张卡片还没到 5 秒
        tick(6)
        check("卡片自己消失", a.farm_card.visible, False)

        print("== 老板键")
        a.boss_toggle()
        check("水面立刻消失", (a.session.state, a.pond.visible), (S.HIDDEN, False))
        a._build_menu()
        check("菜单出现「继续摸」", any(x.text().startswith("继续摸") for x in a.menu.actions()), True)
        a.boss_toggle()
        check("再按一次回来", a.pond.visible, True)

        print("== 托盘图标")
        icon = a._tray_icon(clock["t"])
        check("摸鱼时托盘图标有内容", icon.isNull(), False)
        if shots:
            icon.pixmap(32, 32).save(os.path.join(shots, "tray_break.png"))
        tick(70)
        check("摸鱼结束回去专注", a.pomo.phase, "focus")
        if shots:
            a._tray_icon(clock["t"]).pixmap(32, 32).save(os.path.join(shots, "tray_focus.png"))
        a.stop_timer()
        tick(1)
        check("停了番茄钟，桌面农田收起", a.farm_desk.visible, False)
        a.quit()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("失败 %d 项: %s" % (len(FAILED), "、".join(FAILED)))
        return 1
    print("Windows 版（Qt）冒烟测试全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
