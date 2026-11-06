# -*- coding: utf-8 -*-
"""小音效：用代码合成几段很短的 WAV（不读游戏的声音库，也不用系统提示音）。

Windows 版用这些；Mac 版用系统自带的 Glass / Pop 等，已经够轻了。
第一次需要时生成到数据目录的 sounds/ 里，之后直接播放文件。
"""
import math
import os
import random
import struct
import wave

RATE = 22050
VERSION = 1


def _env(i, n, attack=0.005, decay=None):
    """简单包络：极短的起音，然后指数衰减。"""
    t = i / float(RATE)
    a = min(1.0, t / attack) if attack else 1.0
    if decay:
        a *= math.exp(-t / decay)
    # 末尾 5ms 淡出，避免「啪」的一声
    tail = (n - i) / float(RATE)
    return a * min(1.0, tail / 0.005)


def _tone(freq, secs, vol=0.35, decay=0.12, shape="sine", sweep_to=None):
    n = int(RATE * secs)
    out = []
    phase = 0.0
    for i in range(n):
        f = freq if sweep_to is None else freq + (sweep_to - freq) * (i / float(n))
        phase += 2 * math.pi * f / RATE
        if shape == "tri":
            v = 2 / math.pi * math.asin(math.sin(phase))
        else:
            v = math.sin(phase) + 0.25 * math.sin(2 * phase)      # 带一点泛音，像木琴
        out.append(v * vol * _env(i, n, decay=decay))
    return out


def _noise(secs, vol=0.15, decay=0.04, seed=1):
    rng = random.Random(seed)
    n = int(RATE * secs)
    out, prev = [], 0.0
    for i in range(n):
        prev = prev * 0.6 + rng.uniform(-1, 1) * 0.4                # 低通一下，像水花不像沙沙声
        out.append(prev * vol * _env(i, n, decay=decay))
    return out


def _mix(*parts):
    n = max(len(p) for p in parts)
    return [sum(p[i] for p in parts if i < len(p)) for i in range(n)]


def _seq(*parts, gap=0.0):
    out = []
    for p in parts:
        out += p + [0.0] * int(RATE * gap)
    return out


def _notes(freqs, each=0.09, vol=0.3, decay=0.14, shape="tri"):
    return _seq(*[_tone(f, each + 0.06, vol, decay, shape)[:int(RATE * each)] for f in freqs[:-1]]
                + [_tone(freqs[-1], each * 3, vol, decay * 1.8, shape)])


C6, E6, G6, C7, A5, F5, D5 = 1046.5, 1318.5, 1568.0, 2093.0, 880.0, 698.5, 587.3

RECIPES = {
    # 抛竿：一声「噗通」——往下滑的音 + 一点水花
    "cast": lambda: _mix(_tone(700, 0.16, 0.4, 0.05, sweep_to=220), _noise(0.12, 0.12, 0.03)),
    # 咬钩：两下短促的高音
    "bite": lambda: _seq(_tone(1500, 0.05, 0.28, 0.03), _tone(1500, 0.07, 0.28, 0.04), gap=0.03),
    # 钓到：上行三个音
    "caught": lambda: _notes([C6, E6, G6]),
    # 新的鱼：多一个更高的音
    "new": lambda: _notes([C6, E6, G6, C7], each=0.085),
    # 跑了：下行两个音
    "escaped": lambda: _notes([E6, A5], each=0.12, decay=0.1),
    # 杂物：一声闷响
    "junk": lambda: _mix(_tone(260, 0.18, 0.4, 0.06, sweep_to=160), _noise(0.08, 0.08, 0.02, 3)),
    # 摸鱼开始 / 结束：轻轻的铃
    "start": lambda: _notes([G6, C7], each=0.12, vol=0.22, decay=0.25, shape="sine"),
    "end": lambda: _notes([C7, G6], each=0.12, vol=0.22, decay=0.25, shape="sine"),
}


def write_wav(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32000))
                               for s in samples))


def ensure(directory):
    """把所有音效生成到 directory（已经有了就跳过）。返回 名字 -> 文件路径。"""
    os.makedirs(directory, exist_ok=True)
    out = {}
    for name, make in RECIPES.items():
        path = os.path.join(directory, "%s_v%d.wav" % (name, VERSION))
        if not os.path.isfile(path):
            tmp = path + ".tmp"
            write_wav(tmp, make())
            os.replace(tmp, path)
        out[name] = path
    return out
