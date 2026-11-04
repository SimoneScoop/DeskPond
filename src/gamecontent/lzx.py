# -*- coding: utf-8 -*-
"""LZX 解压（XNA/XNB 变体），纯 Python，无第三方依赖。

星露谷 PC/Mac 版的 .xnb 文件用 LZX 压缩（文件头 flags 的 0x80 位）。

------------------------------------------------------------------------
This file is a Python port of MonoGame's LzxDecoder.cs, which itself was
derived from libmspack:

    (C) 2003-2004 Stuart Caie.
    (C) 2011 Ali Scissons.
    (C) 2026 SebastianPet contributors (Python port).

The LZX method was created by Jonathan Forbes and Tomi Poutanen, adapted
by Microsoft Corporation.

This source file is dual licensed: the end-user of this source file may
redistribute/modify it under the LGPL 2.1 or MS-PL licenses.

MICROSOFT PUBLIC LICENSE
This source code is subject to the terms of the Microsoft Public License
(Ms-PL). Redistribution and use in source and binary forms, with or without
modification, is permitted provided that redistributions of the source code
retain the above copyright notices and this file header. Additional copyright
notices should be appended to the list above.
For details, see <http://www.opensource.org/licenses/ms-pl.html>.
------------------------------------------------------------------------

和 C# 原版的主要区别：哈夫曼表一律展开成 16 位直查表（每个码长 ≤16），
省掉了原版那套「短码直查 + 长码二叉树」的两级结构，Python 里更快也更好读。
"""

MIN_MATCH = 2
NUM_CHARS = 256
NUM_PRIMARY_LENGTHS = 7
NUM_SECONDARY_LENGTHS = 249
PRETREE_NUM_ELEMENTS = 20
ALIGNED_NUM_ELEMENTS = 8

BLOCK_VERBATIM = 1
BLOCK_ALIGNED = 2
BLOCK_UNCOMPRESSED = 3

LOOKUP_BITS = 16

# 位置槽的静态表
EXTRA_BITS = []
_j = 0
for _i in range(0, 52, 2):
    EXTRA_BITS += [_j, _j]
    if _i != 0 and _j < 17:
        _j += 1
POSITION_BASE = []
_j = 0
for _i in range(51):
    POSITION_BASE.append(_j)
    _j += 1 << EXTRA_BITS[_i]
del _i, _j


class LzxError(ValueError):
    pass


class _BitReader(object):
    """LZX 的位流：16 位小端字为单位读入，从高位往低位消费。"""

    __slots__ = ("data", "pos", "end", "buf", "left")

    def __init__(self, data, pos, end):
        self.data = data
        self.pos = pos
        self.end = end
        self.buf = 0
        self.left = 0

    def reset(self):
        self.buf = 0
        self.left = 0

    def _byte(self):
        p = self.pos
        self.pos = p + 1
        if p < len(self.data):
            return self.data[p]
        return 0xFF   # 和 C# 版一致：读过头时 ReadByte() 的 -1 被截成 0xFF

    def ensure(self, n):
        while self.left < n:
            lo = self._byte()
            hi = self._byte()
            self.buf = (self.buf << 16) | (hi << 8) | lo
            self.left += 16

    def peek(self, n):
        return (self.buf >> (self.left - n)) & ((1 << n) - 1)

    def drop(self, n):
        self.left -= n
        self.buf &= (1 << self.left) - 1

    def read(self, n):
        if n == 0:
            return 0
        self.ensure(n)
        v = self.peek(n)
        self.drop(n)
        return v


def _make_table(lengths, nsyms):
    """规范哈夫曼码长 -> 16 位直查表。全零（空树）返回 None，用到时才报错。"""
    table = [-1] * (1 << LOOKUP_BITS)
    code = 0
    any_symbol = False
    for bit_len in range(1, LOOKUP_BITS + 1):
        span = 1 << (LOOKUP_BITS - bit_len)
        for sym in range(nsyms):
            if lengths[sym] == bit_len:
                start = code
                code += span
                if code > (1 << LOOKUP_BITS):
                    raise LzxError("哈夫曼表溢出（码长不合法）")
                table[start:code] = [sym] * span
                any_symbol = True
    if not any_symbol:
        return None
    return table


def _read_symbol(bits, table, lengths):
    if table is None:
        raise LzxError("用到了空的哈夫曼树")
    bits.ensure(LOOKUP_BITS)
    sym = table[bits.peek(LOOKUP_BITS)]
    if sym < 0:
        raise LzxError("哈夫曼表里没有这个码")
    bits.drop(lengths[sym])
    return sym


class LzxDecoder(object):

    def __init__(self, window_bits=16):
        if not 15 <= window_bits <= 21:
            raise LzxError("窗口大小超出范围: %d" % window_bits)
        self.window_size = 1 << window_bits
        self.window = bytearray(b"\xDC" * self.window_size)
        self.window_posn = 0
        if window_bits == 20:
            posn_slots = 42
        elif window_bits == 21:
            posn_slots = 50
        else:
            posn_slots = window_bits << 1
        self.main_elements = NUM_CHARS + (posn_slots << 3)
        self.R0 = self.R1 = self.R2 = 1
        self.header_read = False
        self.block_type = 0
        self.block_remaining = 0
        self.block_length = 0
        self.main_len = [0] * (self.main_elements + 64)
        self.length_len = [0] * (NUM_SECONDARY_LENGTHS + 64)
        self.aligned_len = [0] * ALIGNED_NUM_ELEMENTS
        self.main_table = None
        self.length_table = None
        self.aligned_table = None

    # MARK: 码长表

    def _read_lengths(self, bits, lens, first, last):
        pre_len = [bits.read(4) for _ in range(PRETREE_NUM_ELEMENTS)]
        pre_table = _make_table(pre_len, PRETREE_NUM_ELEMENTS)
        i = first
        while i < last:
            sym = _read_symbol(bits, pre_table, pre_len)
            if sym == 17:
                n = bits.read(4) + 4
                for _ in range(n):
                    lens[i] = 0
                    i += 1
            elif sym == 18:
                n = bits.read(5) + 20
                for _ in range(n):
                    lens[i] = 0
                    i += 1
            elif sym == 19:
                n = bits.read(1) + 4
                sym = _read_symbol(bits, pre_table, pre_len)
                v = lens[i] - sym
                if v < 0:
                    v += 17
                for _ in range(n):
                    lens[i] = v
                    i += 1
            else:
                v = lens[i] - sym
                if v < 0:
                    v += 17
                lens[i] = v
                i += 1

    # MARK: 解一帧

    def decompress(self, data, start, in_len, out_len):
        """从 data[start:start+in_len] 解出 out_len 字节（一帧）。"""
        bits = _BitReader(data, start, start + in_len)
        win = self.window
        wsize = self.window_size
        posn = self.window_posn
        R0, R1, R2 = self.R0, self.R1, self.R2

        if not self.header_read:
            if bits.read(1):
                bits.read(16)
                bits.read(16)   # intel E8 文件大小，XNB 里用不到
            self.header_read = True

        togo = out_len
        while togo > 0:
            if self.block_remaining == 0:
                if self.block_type == BLOCK_UNCOMPRESSED:
                    if self.block_length & 1:
                        bits.pos += 1
                    bits.reset()
                self.block_type = bits.read(3)
                hi = bits.read(16)
                lo = bits.read(8)
                self.block_remaining = self.block_length = (hi << 8) | lo

                bt = self.block_type
                if bt == BLOCK_ALIGNED or bt == BLOCK_VERBATIM:
                    if bt == BLOCK_ALIGNED:
                        for k in range(8):
                            self.aligned_len[k] = bits.read(3)
                        self.aligned_table = _make_table(self.aligned_len,
                                                         ALIGNED_NUM_ELEMENTS)
                    self._read_lengths(bits, self.main_len, 0, 256)
                    self._read_lengths(bits, self.main_len, 256, self.main_elements)
                    self.main_table = _make_table(self.main_len, self.main_elements)
                    self._read_lengths(bits, self.length_len, 0, NUM_SECONDARY_LENGTHS)
                    self.length_table = _make_table(self.length_len,
                                                    NUM_SECONDARY_LENGTHS + 1)
                elif bt == BLOCK_UNCOMPRESSED:
                    bits.ensure(16)
                    if bits.left > 16:
                        bits.pos -= 2
                    d, p = data, bits.pos
                    R0 = d[p] | d[p + 1] << 8 | d[p + 2] << 16 | d[p + 3] << 24
                    R1 = d[p + 4] | d[p + 5] << 8 | d[p + 6] << 16 | d[p + 7] << 24
                    R2 = d[p + 8] | d[p + 9] << 8 | d[p + 10] << 16 | d[p + 11] << 24
                    bits.pos = p + 12
                    bits.reset()
                else:
                    raise LzxError("非法的块类型: %d" % bt)

            while self.block_remaining > 0 and togo > 0:
                this_run = min(self.block_remaining, togo)
                togo -= this_run
                self.block_remaining -= this_run
                posn &= wsize - 1
                if posn + this_run > wsize:
                    raise LzxError("解压越过了窗口边界")

                bt = self.block_type
                if bt == BLOCK_UNCOMPRESSED:
                    p = bits.pos
                    if p + this_run > len(data):
                        raise LzxError("未压缩块越过了数据末尾")
                    win[posn:posn + this_run] = data[p:p + this_run]
                    bits.pos = p + this_run
                    posn += this_run
                    continue

                aligned = bt == BLOCK_ALIGNED
                main_table, main_len = self.main_table, self.main_len
                while this_run > 0:
                    elem = _read_symbol(bits, main_table, main_len)
                    if elem < NUM_CHARS:
                        win[posn] = elem
                        posn += 1
                        this_run -= 1
                        continue

                    elem -= NUM_CHARS
                    match_length = elem & NUM_PRIMARY_LENGTHS
                    if match_length == NUM_PRIMARY_LENGTHS:
                        match_length += _read_symbol(bits, self.length_table,
                                                     self.length_len)
                    match_length += MIN_MATCH

                    slot = elem >> 3
                    if slot > 2:
                        extra = EXTRA_BITS[slot]
                        offset = POSITION_BASE[slot] - 2
                        if aligned:
                            if extra > 3:
                                offset += bits.read(extra - 3) << 3
                                offset += _read_symbol(bits, self.aligned_table,
                                                       self.aligned_len)
                            elif extra == 3:
                                offset += _read_symbol(bits, self.aligned_table,
                                                       self.aligned_len)
                            elif extra > 0:
                                offset += bits.read(extra)
                            else:
                                offset = 1
                        else:
                            if slot != 3:
                                offset += bits.read(extra)
                            else:
                                offset = 1
                        R2, R1, R0 = R1, R0, offset
                    elif slot == 0:
                        offset = R0
                    elif slot == 1:
                        offset = R1
                        R1, R0 = R0, offset
                    else:
                        offset = R2
                        R2, R0 = R0, offset

                    this_run -= match_length
                    dest = posn
                    if posn >= offset:
                        src = dest - offset
                    else:
                        src = dest + (wsize - offset)
                        copy_length = offset - posn
                        if copy_length < match_length:
                            match_length -= copy_length
                            posn += copy_length
                            for _ in range(copy_length):
                                win[dest] = win[src]
                                dest += 1
                                src += 1
                            src = 0
                    posn += match_length
                    if dest - src >= match_length:
                        # 源和目标不重叠：整段切片拷贝
                        win[dest:dest + match_length] = win[src:src + match_length]
                    else:
                        for _ in range(match_length):
                            win[dest] = win[src]
                            dest += 1
                            src += 1

        if togo != 0:
            raise LzxError("帧数据不完整")

        start_pos = posn if posn != 0 else wsize
        start_pos -= out_len
        out = bytes(win[start_pos:start_pos + out_len])
        self.window_posn = posn
        self.R0, self.R1, self.R2 = R0, R1, R2
        return out


def decompress_xnb_payload(data, start, compressed_len, decompressed_len):
    """解压 XNB 文件头之后的 LZX 数据流（帧头 + 块）。"""
    dec = LzxDecoder(16)
    out = bytearray()
    pos = start
    end = start + compressed_len
    while pos < end:
        hi = data[pos]
        lo = data[pos + 1]
        block_size = (hi << 8) | lo
        frame_size = 0x8000
        if hi == 0xFF:
            frame_size = (lo << 8) | data[pos + 2]
            block_size = (data[pos + 3] << 8) | data[pos + 4]
            pos += 5
        else:
            pos += 2
        if block_size == 0 or frame_size == 0:
            break
        if block_size > 0x10000 or frame_size > 0x10000:
            raise LzxError("帧/块大小不合法")
        out += dec.decompress(data, pos, block_size, frame_size)
        pos += block_size
        if len(out) >= decompressed_len:
            break
    if len(out) < decompressed_len:
        raise LzxError("解压后长度不足: %d < %d" % (len(out), decompressed_len))
    return bytes(out[:decompressed_len])
