#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摸鱼流程测试：升起、抛竿、咬钩、溜鱼、结果、收起。假时钟，不需要 macOS。

    python3 tests/test_session.py
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import collection, fishdata, session as S   # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    print("  %s %s%s" % ("✅" if ok else "❌", name, "" if ok else "  (得到 %r，期望 %r)" % (got, want)))
    if not ok:
        FAILED.append(name)


FISH = fishdata.parse_table({
    "137": "Smallmouth Bass/28/mixed/12/24/0 2600/spring summer fall winter/both/x/1/.9/.1/0",
    "143": "Catfish/75/mixed/12/72/0 2600/spring summer fall winter/rainy/x/4/.9/.1/0",
    "128": "Pufferfish/80/floater/1/36/0 2600/spring summer fall winter/sunny/x/4/.9/.5/0",
})


def run_until(sess, now, state, pressed_fn=None, limit=60.0, dt=1 / 60.0):
    t = now
    events = []
    while sess.state != state and t - now < limit:
        pressed = pressed_fn(sess) if pressed_fn else False
        events += sess.update(t, dt, pressed)
        t += dt
    return t, events


def good_player(sess):
    g = sess.game
    from src import minigame
    center = g.fish_pos + minigame.FISH_SIZE / 2
    mid = g.bar_pos + g.bar_height / 2
    return (center - mid) - (g.bar_vel - g.fish_vel) * 0.25 < 0


def main():
    tmp = tempfile.mkdtemp()
    col = collection.Collection(os.path.join(tmp, "c.json"))
    sess = S.Session(FISH, col, rng=random.Random(8))
    sess.spot = "town_river"      # 小嘴鲈鱼、鲶鱼在这里；河豚不在
    sess.weather = "sunny"

    print("== 水面升起")
    check("开始是隐藏的", sess.state, S.HIDDEN)
    check("show 触发", sess.show(0.0), [S.EV_SHOWN])
    t, _ = run_until(sess, 0.0, S.IDLE)
    check("升起后等待抛竿", sess.state, S.IDLE)
    check("水位满", sess.level, 1.0)
    check("升起用时约 1.2 秒", round(t, 1) in (1.2, 1.3), True)

    print("== 抛竿后太早收竿")
    check("抛竿", sess.click(t, 0.3), [S.EV_CAST])
    check("浮漂位置", sess.cast_x, 0.3)
    check("太早收竿", sess.click(t + 0.2), [S.EV_TOO_EARLY])
    check("回到等待抛竿", sess.state, S.IDLE)

    print("== 咬钩了但没点")
    sess.click(t, 0.5)
    t, ev = run_until(sess, t, S.BITE)
    check("咬钩事件", S.EV_BITE in ev, True)
    t, ev = run_until(sess, t, S.IDLE)
    check("错过了", S.EV_MISSED in ev, True)

    print("== 正常钓一条")
    sess.click(t, 0.5)
    t, _ = run_until(sess, t, S.BITE)
    check("点击开始小游戏", sess.click(t), [S.EV_START_GAME])
    check("进入小游戏", sess.state, S.PLAYING)
    check("挑了一条鱼", sess.fish is not None, True)
    t, ev = run_until(sess, t, S.RESULT, pressed_fn=good_player)
    check("有结果", S.EV_CAUGHT in ev or S.EV_ESCAPED in ev, True)
    if sess.result.caught:
        check("钓到的记进图鉴", col.fish[sess.result.fish.id]["count"], 1)
        check("第一次是新鱼种", sess.result.is_new, True)
    t, _ = run_until(sess, t, S.IDLE)
    check("结果显示完回到等待抛竿", sess.state, S.IDLE)

    print("== 摸鱼时间到：正在溜鱼时等这条钓完再收")
    sess.click(t, 0.5)
    t, _ = run_until(sess, t, S.BITE)
    sess.click(t)
    sess.hide(t + 0.1)
    check("溜鱼时不立刻收起", sess.state, S.PLAYING)
    t, _ = run_until(sess, t, S.RESULT, pressed_fn=good_player)
    t, ev = run_until(sess, t, S.HIDDEN)
    check("钓完之后水面退下", sess.state, S.HIDDEN)
    check("收起事件", S.EV_HIDDEN in ev, True)

    print("== 摸鱼时间到：空闲时直接收起")
    sess.show(t); t, _ = run_until(sess, t, S.IDLE)
    sess.hide(t)
    check("开始退下", sess.state, S.FALLING)
    t, _ = run_until(sess, t, S.HIDDEN)
    check("退完隐藏", sess.level, 0.0)

    print("== 钓点和天气决定上钩的鱼")
    got = set()
    for i in range(200):
        sess.rng = random.Random(i)
        f = sess.roll()
        got.add(f.id if isinstance(f, fishdata.Fish) else "junk")
    check("晴天的镇上河流只有小嘴鲈鱼（河豚不在钓点，鲶鱼要下雨）", got - {"junk"}, {"137"})
    sess.weather = "rainy"
    got = {getattr(sess.roll(), "id", "junk") for _ in range(200)}
    check("下雨了鲶鱼出现", "143" in got, True)
    sess.spot, sess.weather = "ocean", "sunny"
    got = {getattr(sess.roll(), "id", "junk") for _ in range(200)}
    check("海边能钓河豚", "128" in got, True)
    sess.spot = "town_river"

    print("== 点得越靠下水越深")
    sess.show(t); t, _ = run_until(sess, t, S.IDLE)
    sess.click(t, 0.5, depth=5)
    check("记下水深", sess.depth, 5)
    sess.click(t)

    print("== 钓上杂物：不进小游戏")
    sess.rng = random.Random(1)
    sess.spot = "desert"           # 测试表里没有沙漠的鱼，只会钓上垃圾
    sess.click(t, 0.5)
    t, _ = run_until(sess, t, S.BITE)
    ev = sess.click(t)
    check("直接出杂物结果", ev, [S.EV_JUNK])
    check("结果是杂物", (sess.state, sess.result.junk), (S.RESULT, True))
    check("杂物记进存档", col.items.get(sess.result.fish.id), 1)
    check("今天的杂物数", col.today_stats()["junk"], 1)
    check("杂物有名字", bool(sess.result.fish.display_name), True)
    sess.spot = "town_river"
    t, _ = run_until(sess, t, S.IDLE)

    print("== 老板键：立刻收起，溜鱼中的不记战绩")
    escaped = col.today_stats()["escaped"]
    sess.rng = random.Random(4)
    sess.click(t, 0.5)
    t, _ = run_until(sess, t, S.BITE)
    sess.click(t)
    check("在溜鱼", sess.state, S.PLAYING)
    check("老板键", sess.boss_hide(t), [S.EV_HIDDEN])
    check("立刻隐藏", (sess.state, sess.level), (S.HIDDEN, 0.0))
    check("没记成跑了", col.today_stats()["escaped"], escaped)
    check("再按一次没反应", sess.boss_hide(t), [])
    sess.show(t); t, _ = run_until(sess, t, S.IDLE)
    check("还能重新升起来钓", sess.state, S.IDLE)
    sess.boss_hide(t)

    print("== 浮漂落在点的位置，高度决定水深")
    sess.show(t); t, _ = run_until(sess, t, S.IDLE)
    sess.click(t, 0.3, y=0.9)
    check("浮漂高度", sess.cast_y, 0.9)
    check("靠下 = 深水", sess.depth, 5)
    sess.click(t)
    sess.click(t, 0.3, y=0.05)
    check("靠上（岸边）= 浅水", sess.depth, 1)
    sess.click(t)

    print("== 经验、品质、宝箱、鱼饵")
    xp0 = col.xp
    col.inventory["685"] = 1
    sess.rng = random.Random(11)
    ev = sess.click(t, 0.5, y=0.1)
    check("竹竿挂不了鱼饵（原版）", (S.EV_BAIT in ev, col.count("685")), (False, 1))
    sess.click(t)
    col.gear = {"rod": "fiberglass", "rods": ["bamboo", "fiberglass"]}
    sess.rng = random.Random(11)
    ev = sess.click(t, 0.5, y=0.1)
    check("有鱼饵自动挂上", (S.EV_BAIT in ev, col.count("685")), (True, 0))
    check("挂饵后等得更短", sess.bite_at - t <= S.WAIT_RANGE[1] * S.BAIT_WAIT, True)
    t, _ = run_until(sess, t, S.BITE)
    sess.click(t)
    sess.game.treasure = True
    sess.game.treasure_caught = True       # 直接当作已经拿到宝箱
    t, ev = run_until(sess, t, S.RESULT, pressed_fn=good_player)
    r = sess.result
    if r.caught:
        check("钓到加经验", col.xp - xp0, r.xp)
        check("经验 > 0", r.xp > 0, True)
        check("鱼自动卖掉换金币", (r.gold > 0, col.gold >= r.gold), (True, True))
        check("品质 0..3", 0 <= r.quality <= 3, True)
        check("记下最高品质", col.fish[r.fish.id]["best_quality"] >= r.quality, True)
        check("记下钓点", "town_river" in col.fish[r.fish.id]["spots"], True)
        check("拿到宝箱内容", len(r.treasure) > 0, True)
        check("宝物进背包", all(col.treasure.get(i, 0) >= n for i, n in r.treasure), True)
    t, _ = run_until(sess, t, S.IDLE)
    ev = sess.click(t, 0.5)
    check("没鱼饵就不挂", S.EV_BAIT in ev, False)
    sess.click(t)

    print("== 升级")
    col.xp = 95
    sess.spot = "desert"
    sess.rng = random.Random(2)
    sess.click(t, 0.5)
    t, _ = run_until(sess, t, S.BITE)
    sess.click(t)
    check("钓杂物 +3 经验", (col.xp, sess.result.xp), (98, 3))
    t, _ = run_until(sess, t, S.IDLE)
    sess.click(t, 0.5); t, _ = run_until(sess, t, S.BITE); sess.click(t)
    check("跨过 100 经验升到 1 级", (sess.result.level_up, col.level), (1, 1))
    sess.spot = "town_river"
    t, _ = run_until(sess, t, S.IDLE)
    sess.boss_hide(t)

    print("== 老存档兼容")
    import json
    old = os.path.join(tmp, "old.json")
    with open(old, "w") as fh:
        json.dump({"fish": {"137": {"count": 2, "max_size": 20, "first": "2026-10-01 10:00"}},
                   "days": {}}, fh)
    c2 = collection.Collection(old)
    check("老存档补齐字段", (c2.fish["137"]["best_quality"], c2.fish["137"]["spots"], c2.xp,
                         c2.inventory), (0, [], 0, {}))
    check("老记录还在", c2.fish["137"]["count"], 2)

    print("== 隐藏时点击无效")
    check("隐藏时点击", sess.click(t), [])

    print()
    if FAILED:
        print("失败 %d 项: %s" % (len(FAILED), "、".join(FAILED)))
        return 1
    print("摸鱼流程测试全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
