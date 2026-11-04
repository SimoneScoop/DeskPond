# -*- coding: utf-8 -*-
"""最小的 PNG 读写（只用标准库 zlib），供缓存构建和测试使用。

写：RGBA8，不交错。
读：8 位深的灰度 / RGB / 调色板 / 灰度+alpha / RGBA，不交错 ——
    覆盖 StardewXnbHack 等解包工具导出的 PNG。读不了的格式交给调用方回退到系统解码。
"""
import struct
import zlib

_SIG = b"\x89PNG\r\n\x1a\n"


class PngError(ValueError):
    pass


def _chunk(tag, payload):
    body = tag + payload
    return (struct.pack(">I", len(payload)) + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))


def encode_rgba(width, height, rgba):
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (_SIG + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def write_rgba(path, width, height, rgba):
    with open(path, "wb") as fh:
        fh.write(encode_rgba(width, height, rgba))


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode(data):
    """返回 (width, height, rgba bytes)。"""
    if data[:8] != _SIG:
        raise PngError("不是 PNG")
    pos = 8
    idat = bytearray()
    palette = trns = None
    width = height = depth = ctype = interlace = None
    while pos < len(data):
        n = struct.unpack_from(">I", data, pos)[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if tag == b"IHDR":
            width, height, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
        elif tag == b"PLTE":
            palette = body
        elif tag == b"tRNS":
            trns = body
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    if depth != 8 or interlace:
        raise PngError("只支持 8 位深、不交错的 PNG")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if channels is None:
        raise PngError("未知颜色类型 %r" % ctype)
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    bpp = channels
    prev = bytearray(stride)
    rows = []
    p = 0
    for _ in range(height):
        ftype = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up_left = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], up_left)) & 0xFF
        elif ftype != 0:
            raise PngError("未知滤波类型 %d" % ftype)
        rows.append(line)
        prev = line

    out = bytearray(width * height * 4)
    o = 0
    for line in rows:
        for x in range(width):
            if ctype == 6:
                out[o:o + 4] = line[x * 4:x * 4 + 4]
            elif ctype == 2:
                r, g, b = line[x * 3:x * 3 + 3]
                a = 255
                if trns and len(trns) >= 6 and (r, g, b) == struct.unpack(">HHH", trns[:6]):
                    a = 0
                out[o:o + 4] = bytes((r, g, b, a))
            elif ctype == 3:
                i = line[x]
                r, g, b = palette[i * 3:i * 3 + 3]
                a = trns[i] if trns and i < len(trns) else 255
                out[o:o + 4] = bytes((r, g, b, a))
            elif ctype == 4:
                v, a = line[x * 2], line[x * 2 + 1]
                out[o:o + 4] = bytes((v, v, v, a))
            else:
                v = line[x]
                out[o:o + 4] = bytes((v, v, v, 255))
            o += 4
    return width, height, bytes(out)


def read_rgba(path):
    with open(path, "rb") as fh:
        return decode(fh.read())
