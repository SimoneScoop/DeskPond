#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心逻辑测试：钓鱼小游戏、挑鱼、番茄钟、图鉴。不需要 macOS。

    python3 tests/test_core.py
"""
import os
import random
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import collection, farm, fishdata, gear, minigame, pomodoro, progression   # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    print("  %s %s%s" % ("✅" if ok else "❌", name, "" if ok else "  (得到 %r，期望 %r)" % (got, want)))
    if not ok:
        FAILED.append(name)


def autopilot(game, dt=1 / 60.0, limit=60.0, skill=0.85, delay=0.2, rng=None):
    """模拟真人：按鱼和绿条的相对位置/速度决定按不按，带 0.2 秒反应延迟，skill 概率手抖。"""
    import collections
    rng = rng or random.Random(1)
    t, hist, pressed = 0.0, collections.deque(), False
    while game.state == minigame.RUNNING and t < limit:
        center = game.fish_pos + minigame.FISH_SIZE / 2
        mid = game.bar_pos + game.bar_height / 2
        hist.append((center - mid) - (game.bar_vel - game.fish_vel) * 0.25)
        err = hist.popleft() if len(hist) > int(delay / dt) else 0
        pressed = err < 0 if rng.random() < skill else pressed
        game.update(dt, pressed)
        t += dt
    return game.state, t


SAMPLE_TABLE = {
    "128": "Pufferfish/80/floater/1/36/1200 1600/summer/sunny/690 .4 685 .1/4/.3/.5/0/true",
    "129": "Anchovy/30/dart/1/16/600 2600/spring fall/both/682 .2/1/.25/.3/0/false",
    "131": "Sardine/30/dart/1/12/600 1900/spring fall winter/both/685 .15/1/.65/.1/0/false",
    "137": "Smallmouth Bass/28/mixed/12/24/600 2600/spring fall/both/685 .2/1/.45/.1/0/false",
    "143": "Catfish/75/mixed/12/72/600 2400/spring fall/rainy/689 .4 680 .1/4/.4/.1/0/false",
    "151": "Squid/75/sinker/12/48/1800 2600/winter/both/690 .35 685 .1/3/.35/.3/0/false",
    "163": "Legend/110/mixed/50/50/600 2000/spring/rainy/688 .5/9/.1/0/10/false",
    "715": "Lobster/trap/.05/688 .45 689 .35 690 .35/ocean/2/20",
}


def main():
    print("== 钓鱼小游戏：基础物理")
    g = minigame.Minigame(difficulty=30, behavior="smooth", rng=random.Random(3))
    start = g.bar_pos
    for _ in range(30):
        g.update(1 / 60.0, True)
    check("按住时绿条往上走", g.bar_pos < start, True)
    for _ in range(240):
        g.update(1 / 60.0, False)
    check("松开后落回底部", round(g.bar_pos, 3), round(minigame.TRACK_HEIGHT - g.bar_height, 3))
    check("绿条不会超出轨道", 0 <= g.bar_pos <= minigame.TRACK_HEIGHT - g.bar_height, True)
    check("鱼不会超出轨道",
          0 <= g.fish_pos <= minigame.TRACK_HEIGHT - minigame.FISH_SIZE, True)

    print("== 什么都不做：鱼会跑")
    g = minigame.Minigame(difficulty=50, rng=random.Random(5))
    g.fish_pos = 0; g.fish_target = 0          # 鱼在最上面，绿条在最下面
    state, t = None, 0
    while g.state == minigame.RUNNING and t < 30:
        g.update(1 / 60.0, False); t += 1 / 60.0
    check("挂机会让鱼跑掉", g.state, minigame.ESCAPED)

    print("== 认真玩：大多数鱼能钓上来（轻松模式）")
    wins = 0
    for seed in range(40):
        rng = random.Random(seed)
        g = minigame.Minigame(difficulty=rng.choice([20, 40, 60, 80]),
                              behavior=rng.choice(["mixed", "dart", "smooth", "sinker", "floater"]),
                              mode="casual", rng=rng)
        state, t = autopilot(g, rng=random.Random(seed + 100))
        wins += state == minigame.CAUGHT
    print("    40 局赢了 %d 局" % wins)
    check("普通玩家胜率 ≥ 80%", wins >= 32, True)

    print("== 原版难度比轻松模式难")
    def winrate(mode, skill):
        w = 0
        for seed in range(40):
            rng = random.Random(seed)
            g = minigame.Minigame(difficulty=85, behavior="dart", mode=mode, rng=rng)
            w += autopilot(g, skill=skill, rng=random.Random(seed + 7))[0] == minigame.CAUGHT
        return w
    easy, hard = winrate("casual", 0.85), winrate("original", 0.85)
    print("    高难度鱼：轻松 %d/40，原版 %d/40" % (easy, hard))
    check("原版明显更难", hard < easy, True)
    check("轻松模式最难的鱼也有一半以上能钓到", easy >= 20, True)

    print("== 一局的时长合理（不会秒结束，也不会拖太久）")
    g = minigame.Minigame(difficulty=40, behavior="mixed", rng=random.Random(9))
    state, t = autopilot(g, rng=random.Random(9))
    print("    %s 用时 %.1f 秒" % (state, t))
    check("3–25 秒内结束", 3 <= t <= 25, True)

    print("== 解析 Data/Fish")
    fish = fishdata.parse_table(SAMPLE_TABLE, names_zh={"Pufferfish": "河豚"})
    ids = [f.id for f in fish]
    check("蟹笼鱼（trap）被跳过", "715" in ids, False)
    puffer = [f for f in fish if f.id == "128"][0]
    check("河豚难度", puffer.difficulty, 80)
    check("河豚时段", puffer.times, [(1200, 1600)])
    check("河豚中文名", puffer.display_name, "河豚")
    check("没中文名时用英文", [f for f in fish if f.id == "129"][0].display_name, "Anchovy")
    check("鱿鱼凌晨也在", [f for f in fish if f.id == "151"][0].active_at(2500), True)

    print("== 现实时间 -> 游戏")
    def lt(mon, h, m=0):
        return time.struct_time((2026, mon, 15, h, m, 0, 0, 1, 0))
    check("4 月是春天", fishdata.season_of(lt(4, 10)), "spring")
    check("12 月是冬天", fishdata.season_of(lt(12, 10)), "winter")
    check("2 月是冬天", fishdata.season_of(lt(2, 10)), "winter")
    check("下午 3 点 = 1500", fishdata.game_time_of(lt(5, 15)), 1500)
    check("凌晨 1 点 = 2500", fishdata.game_time_of(lt(5, 1)), 2500)

    print("== 按季节/时间挑鱼")
    c = fishdata.candidates(fish, season="summer", game_time=1300)
    check("夏天中午：河豚在", "128" in [f.id for f in c], True)
    c = fishdata.candidates(fish, season="summer", game_time=1700)
    check("夏天傍晚：河豚不在", "128" in [f.id for f in c], False)
    c = fishdata.candidates(fish, season="spring", game_time=1000)
    check("传说之鱼不会在摸鱼时上钩", "163" in [f.id for f in c], False)
    check("指定钓点：只出钓点里的鱼",
          sorted(f.id for f in fishdata.candidates(fish, season="spring", game_time=1000,
                                                    ids=("137", "143"))), ["137", "143"])
    check("天气：雨天鱼晴天不出",
          "143" in [f.id for f in fishdata.candidates(fish, season="spring", game_time=1000,
                                                       weather="sunny")], False)
    check("天气：雨天鱼雨天出",
          "143" in [f.id for f in fishdata.candidates(fish, season="spring", game_time=1000,
                                                       weather="rainy")], True)

    print("== 原版上钩概率")
    bass = [f for f in fish if f.id == "137"][0]
    check("解析出水深 / 倍率", (puffer.max_depth, puffer.spawn_mult, puffer.depth_mult,
                            puffer.min_level), (4, 0.3, 0.5, 0))
    check("够深时 = 生成倍率", round(fishdata.catch_chance(puffer, 5), 3), 0.3)
    check("浅一格掉 水深倍率×生成倍率", round(fishdata.catch_chance(puffer, 3), 3), 0.15)
    check("太浅就是 0", round(fishdata.catch_chance(puffer, 1), 3), 0.0)
    check("钓鱼等级加成", round(fishdata.catch_chance(bass, 5, level=10), 3), 0.65)
    check("上限 0.9", fishdata.catch_chance(bass, 5, level=50), 0.9)
    old = fishdata.Fish(id="1", difficulty=10, times=[(600, 2600)], seasons=[])
    check("老缓存缺字段也能算", 0 < fishdata.catch_chance(old, 5) <= 0.9, True)

    print("== 挑鱼：鱼或杂物")
    got = fishdata.roll(fish, rng=random.Random(1), ids=("128",), season="summer", game_time=300)
    check("当下没鱼时钓上垃圾（原版）", got in fishdata.TRASH, True)
    counts = {"fish": 0, "junk": 0}
    deep = {}
    rng = random.Random(2)
    for _ in range(3000):
        g = fishdata.roll(fish, rng=rng, ids=("137", "131"), season="spring", game_time=1000,
                          depth=5)
        if isinstance(g, fishdata.Fish):
            counts["fish"] += 1
            deep[g.id] = deep.get(g.id, 0) + 1
        else:
            counts["junk"] += 1
    print("    深水 3000 竿：鱼 %d，杂物 %d，%s" % (counts["fish"], counts["junk"], deep))
    check("大部分是鱼", counts["fish"] > counts["junk"], True)
    check("杂物也会有", counts["junk"] > 0, True)
    check("生成倍率高的沙丁鱼比小嘴鲈鱼多", deep.get("131", 0) > deep.get("137", 0), True)
    shallow = sum(isinstance(fishdata.roll(fish, rng=random.Random(i), ids=("128",),
                                           season="summer", game_time=1300, depth=1),
                             fishdata.Fish) for i in range(300))
    check("河豚在浅水几乎钓不到", shallow, 0)
    j1 = sum(not isinstance(fishdata.roll(fish, rng=random.Random(i), ids=("137",),
                                          season="spring", game_time=1000), fishdata.Fish)
             for i in range(1000))
    j2 = sum(not isinstance(fishdata.roll(fish, rng=random.Random(i), ids=("137",),
                                          season="spring", game_time=1000, rerolls=1),
                            fishdata.Fish) for i in range(1000))
    print("    杂物率：原版 %d/1000，轻松（重抽一次）%d/1000" % (j1, j2))
    check("轻松模式重抽后杂物更少", j2 < j1, True)
    algae = sum(fishdata.roll(fish, rng=random.Random(i), ids=(), algae=("153",),
                              season="spring", game_time=1000) == "153" for i in range(1000))
    check("钓点的藻类会被钓上来", 50 < algae < 200, True)
    check("Data/Fish 里的藻类不当鱼", fishdata.parse_entry("153", "Green Algae/5/floater/1/2/600 2600/spring/both/x/1/.5/.1/0") is None, True)

    print("== 钓点 / 天气 / 水深")
    from src import world
    check("默认钓点已解锁", world.is_unlocked("town_river", 0), True)
    check("秘密森林要 10 种", (world.is_unlocked("secret_woods", 9), world.is_unlocked("secret_woods", 10)), (False, True))
    check("沙漠要 20 种", (world.is_unlocked("desert", 19), world.is_unlocked("desert", 20)), (False, True))
    check("不存在的钓点", world.is_unlocked("moon", 999), False)
    check("沙漠有沙鱼", "164" in world.spot_fish("desert"), True)
    check("鲶鱼的钓点", world.spots_of("143"), ["town_river", "forest_river"])
    ws = [world.today_weather(time.struct_time((2026, 4, d, 10, 0, 0, 0, 1, 0))) for d in range(1, 31)]
    check("春天有晴有雨", set(ws) == {"sunny", "rainy"}, True)
    check("同一天天气不变", world.today_weather(time.struct_time((2026, 4, 3, 9, 0, 0, 0, 1, 0))),
          world.today_weather(time.struct_time((2026, 4, 3, 17, 0, 0, 0, 1, 0))))
    wi = {world.today_weather(time.struct_time((2026, 1, d, 10, 0, 0, 0, 1, 0))) for d in range(1, 31)}
    check("冬天不下雨", "rainy" in wi, False)
    check("下雪不算雨天", world.fish_weather("snow"), "sunny")
    check("点水面最上沿 = 最浅", world.depth_from_rel(0.0), 1)
    check("点屏幕底边 = 最深", world.depth_from_rel(1.0), 5)
    check("中间 = 3", world.depth_from_rel(0.5), 3)
    sizes = [fishdata.roll_size(puffer, random.Random(i)) for i in range(200)]
    check("尺寸在范围内", min(sizes) >= 1 and max(sizes) <= 36, True)

    print("== 钓鱼等级 / 品质 / 经验")
    check("0 经验 0 级", progression.level_for(0), 0)
    check("100 经验 1 级", progression.level_for(100), 1)
    check("15000 经验满级", progression.level_for(15000), 10)
    check("等级进度", progression.level_progress(240), (1, 140, 280))
    check("满级进度", progression.level_progress(99999), (10, 1, 1))
    check("小尺寸普通", progression.quality_of(puffer, 3), 0)
    check("中尺寸银星", progression.quality_of(puffer, 18), 1)
    check("大尺寸金星", progression.quality_of(puffer, 34), 2)
    check("金星 + 完美 = 铱星", progression.quality_of(puffer, 34, perfect=True), 3)
    check("经验：难度 80 普通", progression.catch_xp(80, 0), 29)
    check("经验：铱星按原版编号 4 算", progression.catch_xp(80, 3), 41)
    check("经验：完美 ×2.4", progression.catch_xp(80, 0, perfect=True), 69)
    bar0 = minigame.Minigame(mode="original", level=0).bar_height
    bar10 = minigame.Minigame(mode="original", level=10).bar_height
    check("原版绿条 0 级 24、10 级 44", (bar0, bar10), (24.0, 44.0))
    check("轻松模式绿条也随等级变长", minigame.Minigame(level=5).bar_height, 48.0)

    def wr(level):
        w = 0
        for seed in range(40):
            rng = random.Random(seed)
            g = minigame.Minigame(difficulty=60, behavior="mixed", mode="original", rng=rng,
                                  level=level)
            w += autopilot(g, skill=0.85, rng=random.Random(seed + 3))[0] == minigame.CAUGHT
        return w
    lo_, hi_ = wr(0), wr(10)
    print("    原版手感、难度 60 的鱼：0 级 %d/40，10 级 %d/40" % (lo_, hi_))
    check("等级越高越好钓", hi_ > lo_, True)

    print("== 浮漂解锁（原版浮漂机：每 2 种新鱼一种）")
    check("0 种鱼：只有默认", progression.bobbers_unlocked(0, 39), 1)
    check("18 种鱼：第 10 种", progression.bobbers_unlocked(18, 39), 10)
    check("76 种鱼：全部 39 种", progression.bobbers_unlocked(76, 39), 39)
    check("没有浮漂表", progression.bobbers_unlocked(30, 0), 0)

    print("== 水深影响尺寸")
    deep = sum(fishdata.roll_size(puffer, random.Random(i), depth=5) for i in range(500))
    shallow = sum(fishdata.roll_size(puffer, random.Random(i), depth=1) for i in range(500))
    check("深水的鱼平均更大", deep > shallow, True)
    big = sum(fishdata.roll_size(puffer, random.Random(i), level=10) for i in range(500))
    check("等级高的鱼平均更大", big > deep, True)

    print("== 宝箱")
    g = minigame.Minigame(difficulty=10, behavior="smooth", rng=random.Random(1), treasure=True)
    check("开局宝箱还没出现", g.treasure_visible, False)
    g.treasure_pos = g.bar_pos + g.bar_height / 2 - minigame.TREASURE_SIZE / 2
    t = 0
    while not g.treasure_caught and t < 10 and g.state == minigame.RUNNING:
        g.update(1 / 60.0, False); t += 1 / 60.0
    check("绿条罩住宝箱一会儿就拿到", g.treasure_caught, True)
    print("    用时 %.1f 秒（含出现前的等待）" % t)
    g = minigame.Minigame(difficulty=10, rng=random.Random(1), treasure=True)
    g.treasure_pos = 0
    for _ in range(600):
        g.update(1 / 60.0, False)
    check("罩不住就拿不到", g.treasure_caught, False)
    n = sum(minigame.Minigame(rng=random.Random(i)).treasure for i in range(2000))
    check("约 15% 出宝箱", 220 < n < 380, True)
    loot = [progression.roll_treasure("spring", random.Random(i)) for i in range(400)]
    kinds = {i for l in loot for i, _ in l}
    check("春天会开出种子", any(k in progression.SEEDS["spring"] for k in kinds), True)
    check("会开出鱼饵", progression.BAIT in kinds, True)
    wloot = {i for k in range(400) for i, _ in progression.roll_treasure("winter", random.Random(k))}
    check("冬天没有种子", any(k in sum(progression.SEEDS.values(), []) for k in wloot), False)
    check("宝物都有名字", all(k in progression.TREASURE_NAMES for k in kinds | wloot), True)

    print("== 种田")
    check("防风草 0 天是种子（第 1 帧）", farm.frame_of([1, 1, 1, 1], 0), (1, False))
    check("防风草 2 天第 3 帧", farm.frame_of([1, 1, 1, 1], 2), (3, False))
    check("防风草 4 天成熟（第 5 帧）", farm.frame_of([1, 1, 1, 1], 4), (5, True))
    check("花椰菜第 3 天还在第 2 阶段", farm.frame_of([1, 2, 4, 4, 1], 3), (3, False))
    check("1.5 字符串格式", farm.parse_crops({"472": "1 1 1 2/spring/0/24/-1/0/false"})["472"],
          ("Parsnip", "24", 0, [1, 1, 1, 2]))
    check("1.6 解包 JSON 格式", farm.parse_crops({"474": {"DaysInPhase": [1, 2], "SpriteIndex": 2,
                                                       "HarvestItemId": "(O)190"}})["474"],
          ("Cauliflower", "190", 2, [1, 2]))
    check("坏数据跳过", farm.parse_crops({"472": "abc", "999": "1/x"}), {})
    plots = []
    f = farm.Farm(plots)
    check("3 块空地", (len(plots), f.empty(0), f.summary()), (3, True, ["空地", "空地", "空地"]))
    check("种下", f.plant(1, "472"), True)
    check("不能重复种", f.plant(1, "474"), False)
    check("不认识的种子种不了", f.plant(0, "999"), False)
    check("没成熟收不了", f.harvest(1), None)
    check("长 3 天", (f.grow(), f.grow(), f.grow()), ([], [], []))
    check("第 4 天成熟", f.grow(), [1])
    check("成熟后再长也不会枯", (f.grow(), f.info(1)["mature"]), ([], True))
    check("存档里就是这块地", plots[1]["seed"], "472")
    check("收获防风草", f.harvest(1), "24")
    check("收完变空地", f.empty(1), True)
    check("挑当季种子", farm.pick_seed({"487": 2, "472": 1}, "fall"), "487")
    check("没当季的就用别的", farm.pick_seed({"472": 1}, "fall"), "472")
    check("没种子", farm.pick_seed({"685": 3}, "spring"), None)
    check("春天送春天的种子", farm.SEED_SEASON[farm.daily_seed("spring", random.Random(1))], "spring")
    check("冬天不送", farm.daily_seed("winter"), None)

    print("== 种田：完成一个番茄")
    c3 = collection.Collection(os.path.join(tempfile.mkdtemp(), "c.json"))
    f3 = farm.Farm(c3.farm)
    r = farm.focus_done(f3, c3, "spring", random.Random(1))
    check("第一次：新手种子包 + 每日种子，三块地都种上", (r.gift is not None, len(r.planted)), (True, 3))
    check("新手包只送一次", c3.farm_started, True)
    r = farm.focus_done(f3, c3, "spring", random.Random(1))
    check("同一天不再送", r.gift, None)
    check("三块地都长了一天", sorted(r.grew), [0, 1, 2])

    print("== 种田：买种子 / 自己选种什么")
    c6 = collection.Collection(os.path.join(tempfile.mkdtemp(), "c.json"))
    f6 = farm.Farm(c6.farm)
    check("春天皮埃尔卖的种子（按价格排）", farm.seeds_for_sale("spring"), ["472", "475", "477", "474"])
    check("冬天不卖", farm.seeds_for_sale("winter"), [])
    check("没钱买不了", farm.buy_seed(c6, "472"), False)
    c6.gold = 100
    check("买一包防风草 20g", (farm.buy_seed(c6, "472"), c6.gold, c6.count("472")), (True, 80, 1))
    farm.buy_seed(c6, "474")
    check("花椰菜 80g", (c6.gold, c6.count("474")), (0, 1))
    check("给第 2 块地选花椰菜：空地马上种下", farm.set_plan(f6, c6, 1, "474", "spring"), "474")
    check("第 2 块地种的是花椰菜", f6.info(1)["seed"], "474")
    check("选择记进存档", c6.farm_plan[:3], [None, "474", None])
    c7 = collection.Collection(c6.path)
    check("重新读存档还在", c7.farm_plan[:3], [None, "474", None])
    c6.give("490", 2)
    farm.set_plan(f6, c6, 0, None, "fall")
    check("选「自动」：秋天优先当季的南瓜", f6.info(0)["seed"], "490")
    c6.give("472", 1)
    farm.set_plan(f6, c6, 2, "472", "fall")
    check("选了非当季的也照种", f6.info(2)["seed"], "472")
    c6.farm_plan[2] = "479"
    check("选的种子手上没有：退回自动", farm.next_seed(c6, 2, "fall"), "490")

    print("== 种田：扩建到 2 排 6 块")
    c8 = collection.Collection(os.path.join(tempfile.mkdtemp(), "c.json"))
    f8 = farm.Farm(c8.farm)
    check("一开始 3 块地", (f8.size, f8.rows), (3, 1))
    c8.gold = 5000
    check("等级不够：锁着", farm.expand_state(c8)[0], "locked")
    c8.xp = 770
    check("钓鱼 3 级：可以买", farm.expand_state(c8), ("buy", "2,500g"))
    check("买扩建", (farm.expand(c8), c8.gold), (True, 2500))
    check("变成 6 块地", (f8.size, f8.rows), (6, 2))
    check("不能再扩", farm.expand_state(c8)[0], "done")
    check("扩建记进存档", len(collection.Collection(c8.path).farm), 6)
    c8.give("472", 6)
    r = farm.focus_start(f8, c8, "spring", random.Random(1))
    check("6 块地都种上", sum(1 for k in range(6) if not f8.empty(k)), 6)

    print("== 种田：开始专注就播种 / 进度字")
    c4 = collection.Collection(os.path.join(tempfile.mkdtemp(), "c.json"))
    f4 = farm.Farm(c4.farm)
    r = farm.focus_start(f4, c4, "spring", random.Random(1))
    check("开始专注就把地种上", len(r.planted), 3)
    check("开始专注不算长一天", r.grew, [])
    name = lambda i: {"24": "防风草"}.get(str(i), str(i))
    cap = farm.progress_caption(f4, name, "focus", 61, "spring")
    check("专注中：倒计时 + 下一步", cap.startswith("🍅 1:01 后 · "), True)
    check("摸鱼中", farm.progress_caption(f4, name, "break", 0, "spring").startswith("🐟 摸鱼中 · 下个番茄做完："), True)
    c5 = collection.Collection(os.path.join(tempfile.mkdtemp(), "c.json"))
    cap = farm.progress_caption(farm.Farm(c5.farm), name, "focus", 30, "winter")
    check("没作物也显示倒计时", cap, "🍅 0:30 后 · 冬天不长作物，春天再种")
    c3.give("472", 5)
    r = farm.focus_done(f3, c3, "spring")
    check("空地全部种上", sum(1 for k in range(3) if not f3.empty(k)), 3)
    for _ in range(12):
        r = farm.focus_done(f3, c3, "spring")
    check("成熟自动收获、换鱼饵", (sum(c3.crops.values()) >= 3, c3.count("685") >= 3), (True, True))

    print("== 钓具和金币（原版威利钓具店路线）")
    c4 = collection.Collection(os.path.join(tempfile.mkdtemp(), "g.json"))
    g = gear.Gear(c4.gear)
    check("一开始是竹竿", (g.rod, g.tackle), ("bamboo", None))
    check("竹竿不能挂鱼饵", gear.can_bait("bamboo"), False)
    check("玻璃纤维要钓鱼 2 级", g.shop_state("fiberglass", 1, 99999), ("locked", "钓鱼 2 级解锁"))
    check("钱不够", g.shop_state("fiberglass", 2, 100)[0], "poor")
    c4.xp, c4.gold = 380, 2000
    check("买玻璃纤维钓竿", (g.buy("fiberglass", c4), g.rod, c4.gold), (True, "fiberglass", 200))
    check("再买一次不行", g.buy("fiberglass", c4), False)
    check("买鱼饵", (g.buy("bait", c4), c4.count("685"), c4.gold), (True, 10, 150))
    check("配件要铱金钓竿", g.shop_state("695", 6, 9999)[0], "locked")
    c4.xp, c4.gold = 3300, 9000
    check("铱金要 6 级，5 级买不了", g.shop_state("iridium", 5, 9999)[0], "locked")
    check("买铱金钓竿", (g.buy("iridium", c4), gear.tackle_slots(g.rod)), (True, 1))
    check("买软木浮标并装上", (g.buy("695", c4), g.tackle, g.bar_bonus()), (True, "695", 6))
    check("绿条更长", minigame.Minigame(mode="original", level=6, bar_bonus=g.bar_bonus()).bar_height,
          24 + 12 + 6.0)
    check("买陷阱浮标、换上", (g.buy("694", c4), round(g.loss_mult(), 2)), (True, 0.67))
    check("陷阱浮标让进度掉得慢",
          minigame.Minigame(mode="original", loss_mult=g.loss_mult()).loss < minigame.MODES["original"]["loss"],
          True)
    g.equip_tackle("694")
    check("再点一次卸下", g.tackle, None)
    g.data["tackles"].append("686"); g.equip_tackle("686")
    check("旋转亮片 + 鱼饵：等待 ×0.375", g.wait_mult(True), 0.375)
    g.equip_rod("fiberglass")
    check("换回玻璃纤维，配件不生效", (g.tackle, g.wait_mult(False)), (None, 1.0))
    g.equip_rod("iridium"); g.data["tackles"].append("693"); g.equip_tackle("693")
    m = minigame.Minigame(rng=random.Random(1), treasure=True, keep_treasure=g.keeps_treasure())
    m.treasure_at, m.treasure_progress, m.treasure_pos = 0, 0.5, 0
    for _ in range(60):
        m.update(1 / 60.0, False)
    check("寻宝者：宝箱进度不往回掉", m.treasure_progress, 0.5)
    check("售价：读到原版价格就用", gear.fish_price(fishdata.Fish(id="1", difficulty=10, price=200), 0), 200)
    check("售价：铱星 ×2", gear.fish_price(fishdata.Fish(id="1", difficulty=10, price=200), 3), 400)
    check("售价：读不到按难度估", gear.fish_price(fishdata.Fish(id="1", difficulty=80), 0), 170)
    check("作物售价", gear.crop_price("276"), 320)

    print("== 番茄钟")
    p = pomodoro.Pomodoro(focus_min=25, break_min=5, long_break_min=15, rounds=4)
    check("初始标题", p.menu_title(0), "🎣")
    p.start_focus(0)
    check("专注中标题", p.menu_title(0), "🍅 25:00")
    check("专注没结束不切换", p.update(100), [])
    check("专注结束 -> 开始摸鱼", p.update(25 * 60), [pomodoro.EV_BREAK_START])
    check("短休息 5 分钟", round(p.remaining(25 * 60)), 300)
    check("摸鱼中", p.fishing, True)
    check("摸鱼结束 -> 回去专注", p.update(30 * 60), [pomodoro.EV_BREAK_END, pomodoro.EV_FOCUS_START])
    now = 30 * 60
    for _ in range(2):                       # 第 2、3 轮
        now += 25 * 60; p.update(now)
        now += p.remaining(now); p.update(now)
    now += 25 * 60
    p.update(now)                            # 第 4 轮专注结束
    check("第 4 轮后是长休息", p.phase, pomodoro.LONG_BREAK)
    check("长休息 15 分钟", round(p.remaining(now)), 900)
    p.pause(now + 60)
    check("暂停后时间不走", round(p.remaining(now + 500)), 840)
    p.resume(now + 500)
    check("继续后接着走", round(p.remaining(now + 500)), 840)

    q = pomodoro.Pomodoro()
    q.start_break(0, minutes=5, free=True)
    check("临时摸鱼结束后回到空闲", q.update(300), [pomodoro.EV_BREAK_END])
    check("回到空闲", q.phase, pomodoro.IDLE)

    print("== 图鉴存档")
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "c.json")
    col = collection.Collection(path)
    check("第一次钓到是新鱼种", col.record_catch("128", 20), (True, False))
    check("再钓更大的是破纪录", col.record_catch("128", 30), (False, True))
    check("更小的不算破纪录", col.record_catch("128", 10), (False, False))
    col.record_escape()
    col2 = collection.Collection(path)
    check("重新读取后数量还在", col2.fish["128"]["count"], 3)
    check("最大尺寸", col2.fish["128"]["max_size"], 30)
    check("今日战绩", col2.today_stats(), {"caught": 3, "escaped": 1, "junk": 0})
    col2.days["2026-10-19"] = {"caught": 5, "escaped": 0, "junk": 1}    # 周一
    col2.days["2026-10-18"] = {"caught": 9, "escaped": 0, "junk": 0}    # 上周日，不算
    col2.days.setdefault("2026-10-21", {"caught": 2, "escaped": 1})
    wk = col2.week_stats(time.struct_time((2026, 10, 21, 10, 0, 0, 2, 294, 0)))
    check("本周只算周一到今天", (wk["caught"] >= 7, wk["caught"] < 16), (True, True))
    check("鱼种数", col2.caught_species(), 1)

    print("== 改名：旧数据目录（MoyuFishing）搬到 DeskPond")
    from src import paths
    base = tempfile.mkdtemp()
    os.makedirs(os.path.join(base, "MoyuFishing"))
    with open(os.path.join(base, "MoyuFishing", "collection.json"), "w") as fh:
        fh.write("{}")
    check("搬过去", paths.migrate_old_dir(base), True)
    check("存档跟着走", os.path.isfile(os.path.join(base, "DeskPond", "collection.json")), True)
    os.makedirs(os.path.join(base, "MoyuFishing"))
    check("新目录已经有了就不动", paths.migrate_old_dir(base), False)

    print()
    if FAILED:
        print("失败 %d 项: %s" % (len(FAILED), "、".join(FAILED)))
        return 1
    print("核心逻辑测试全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
