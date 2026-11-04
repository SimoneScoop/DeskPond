# -*- coding: utf-8 -*-
"""读游戏自带的 .xnb 贴图（Texture2D），纯 Python。

只实现桌宠用得到的部分：
    - 文件头：XNB + 平台 + 版本 + flags（0x80 = LZX，0x40 = LZ4，都不置 = 未压缩）
    - 主对象是 Texture2D、SurfaceFormat.Color（星露谷的所有贴图都是这种）

XNB 里的颜色是预乘 alpha 的（XNA 内容管线的默认行为），读出来要还原成直通 alpha，
否则半透明像素会偏暗。像素画大多只有 0/255 两档 alpha，但头像的抗锯齿边缘不是。
"""
import struct

from . import lzx

FLAG_HIDEF = 0x01
FLAG_LZ4 = 0x40
FLAG_LZX = 0x80
HEADER_SIZE = 10            # "XNB" + platform + version + flags + uint32 文件大小
COMPRESSED_PROLOGUE = 14    # 再加 uint32 解压后大小

SURFACE_COLOR = 0


class XnbError(ValueError):
    pass


class Texture(object):
    """直通 alpha 的 RGBA8 像素，行优先、第 0 行是图像顶部。"""

    __slots__ = ("width", "height", "rgba")

    def __init__(self, width, height, rgba):
        self.width = width
        self.height = height
        self.rgba = rgba   # bytes，长度 = width * height * 4

    def to_numpy(self):
        import numpy as np
        return np.frombuffer(self.rgba, dtype=np.uint8).reshape(
            self.height, self.width, 4).copy()


# MARK: 解压

def lz4_block_decompress(src, out_len):
    """LZ4 块格式（安卓版的 XNB 用这个）。"""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0:
            raise XnbError("LZ4 偏移为 0")
        mlen = token & 0x0F
        if mlen == 15:
            while True:
                b = src[i]
                i += 1
                mlen += b
                if b != 255:
                    break
        mlen += 4
        start = len(out) - offset
        if start < 0:
            raise XnbError("LZ4 偏移越界")
        if offset >= mlen:
            out += out[start:start + mlen]
        else:
            for k in range(mlen):
                out.append(out[start + k])
    if len(out) != out_len:
        raise XnbError("LZ4 解压后长度不符: %d != %d" % (len(out), out_len))
    return bytes(out)


def read_payload(data):
    """校验文件头并返回解压后的内容区（从读取器列表开始）。"""
    if len(data) < HEADER_SIZE or data[:3] != b"XNB":
        raise XnbError("不是 XNB 文件")
    flags = data[5]
    file_size = struct.unpack_from("<I", data, 6)[0]
    if file_size != len(data):
        raise XnbError("XNB 文件被截断（头部声明 %d 字节，实际 %d）"
                       % (file_size, len(data)))
    if flags & FLAG_LZX:
        out_len = struct.unpack_from("<I", data, 10)[0]
        return lzx.decompress_xnb_payload(
            data, COMPRESSED_PROLOGUE, file_size - COMPRESSED_PROLOGUE, out_len)
    if flags & FLAG_LZ4:
        out_len = struct.unpack_from("<I", data, 10)[0]
        return lz4_block_decompress(data[COMPRESSED_PROLOGUE:], out_len)
    return bytes(data[HEADER_SIZE:])


# MARK: 内容区

class _Cursor(object):
    __slots__ = ("buf", "pos")

    def __init__(self, buf):
        self.buf = buf
        self.pos = 0

    def u8(self):
        v = self.buf[self.pos]
        self.pos += 1
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.buf, self.pos)[0]
        self.pos += 4
        return v

    def u32(self):
        v = struct.unpack_from("<I", self.buf, self.pos)[0]
        self.pos += 4
        return v

    def varint(self):
        result = shift = 0
        while True:
            b = self.u8()
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7

    def string(self):
        n = self.varint()
        s = self.buf[self.pos:self.pos + n].decode("utf-8")
        self.pos += n
        return s

    def take(self, n):
        if self.pos + n > len(self.buf):
            raise XnbError("数据不足")
        v = self.buf[self.pos:self.pos + n]
        self.pos += n
        return v


def read_readers(payload):
    """返回 (读取器类型名列表, 游标)，游标停在共享资源计数之后、主对象之前。"""
    cur = _Cursor(payload)
    count = cur.varint()
    readers = []
    for _ in range(count):
        readers.append(cur.string())
        cur.i32()   # 读取器版本
    cur.varint()    # 共享资源数
    return readers, cur


def unpremultiply(rgba):
    """预乘 alpha -> 直通 alpha。alpha 为 0 或 255 的像素不动。"""
    try:
        import numpy as np
    except ImportError:
        out = bytearray(rgba)
        for i in range(0, len(out), 4):
            a = out[i + 3]
            if 0 < a < 255:
                for k in range(3):
                    out[i + k] = min(255, (out[i + k] * 255 + a // 2) // a)
        return bytes(out)
    arr = np.frombuffer(rgba, dtype=np.uint8).reshape(-1, 4).astype(np.uint32)
    a = arr[:, 3]
    partial = (a > 0) & (a < 255)
    if partial.any():
        ap = a[partial]
        for k in range(3):
            c = arr[partial, k]
            arr[partial, k] = np.minimum(255, (c * 255 + ap // 2) // ap)
    return arr.astype(np.uint8).tobytes()


def read_texture(data):
    """从 .xnb 的原始字节读出 Texture2D。"""
    payload = read_payload(data)
    readers, cur = read_readers(payload)
    idx = cur.varint()
    if idx == 0:
        raise XnbError("主对象为空")
    type_name = readers[idx - 1]
    if "Texture2DReader" not in type_name:
        raise XnbError("这个 XNB 不是贴图（读取器: %s）" % type_name.split(",")[0])
    return _texture_body(cur)


SURFACE_BGRA4444, SURFACE_DXT1, SURFACE_DXT3, SURFACE_DXT5 = 3, 4, 5, 6


def _texture_body(cur):
    """Texture2D 的内容：格式、宽、高、mip 数、第一层 mip 的数据（后面的 mip 跳过）。"""
    fmt = cur.i32()
    width = cur.u32()
    height = cur.u32()
    mips = cur.u32()
    if mips < 1:
        raise XnbError("贴图没有数据")
    size = cur.u32()
    pixels = bytes(cur.take(size))
    for _ in range(mips - 1):
        cur.take(cur.u32())
    if fmt == SURFACE_COLOR:
        if size != width * height * 4:
            raise XnbError("贴图数据长度不符")
        rgba = pixels
    elif fmt == SURFACE_BGRA4444:
        rgba = _from_bgra4444(pixels, width, height)
    elif fmt in (SURFACE_DXT1, SURFACE_DXT3, SURFACE_DXT5):
        rgba = _from_dxt(pixels, width, height, fmt)
    else:
        raise XnbError("暂不支持的贴图格式 %d" % fmt)
    return Texture(width, height, unpremultiply(rgba))


def _from_bgra4444(px, w, h):
    out = bytearray(w * h * 4)
    for i in range(w * h):
        v = px[i * 2] | (px[i * 2 + 1] << 8)
        b, g, r, a = v & 15, (v >> 4) & 15, (v >> 8) & 15, (v >> 12) & 15
        out[i * 4:i * 4 + 4] = bytes((r * 17, g * 17, b * 17, a * 17))
    return bytes(out)


def _rgb565(v):
    return (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def _from_dxt(px, w, h, fmt):
    """DXT1/3/5 解码（字体贴图常用 DXT3）。纯 Python，字体贴图只解一次再缓存成 PNG。"""
    out = bytearray(w * h * 4)
    bw, bh = (w + 3) // 4, (h + 3) // 4
    step = 8 if fmt == SURFACE_DXT1 else 16
    pos = 0
    for by in range(bh):
        for bx in range(bw):
            blk = px[pos:pos + step]
            pos += step
            alpha = [255] * 16
            cbase = 0
            if fmt == SURFACE_DXT3:
                for i in range(16):
                    nib = (blk[i // 2] >> (4 * (i % 2))) & 15
                    alpha[i] = nib * 17
                cbase = 8
            elif fmt == SURFACE_DXT5:
                a0, a1 = blk[0], blk[1]
                bits = int.from_bytes(blk[2:8], "little")
                if a0 > a1:
                    pal = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
                else:
                    pal = [a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]
                for i in range(16):
                    alpha[i] = pal[(bits >> (3 * i)) & 7]
                cbase = 8
            c0 = blk[cbase] | (blk[cbase + 1] << 8)
            c1 = blk[cbase + 2] | (blk[cbase + 3] << 8)
            p0, p1 = _rgb565(c0), _rgb565(c1)
            if c0 > c1 or fmt != SURFACE_DXT1:
                p2 = tuple((2 * a + b) // 3 for a, b in zip(p0, p1))
                p3 = tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))
                cols = [p0, p1, p2, p3]
                transparent = None
            else:
                cols = [p0, p1, tuple((a + b) // 2 for a, b in zip(p0, p1)), (0, 0, 0)]
                transparent = 3
            idx = int.from_bytes(blk[cbase + 4:cbase + 8], "little")
            for i in range(16):
                x, y = bx * 4 + i % 4, by * 4 + i // 4
                if x >= w or y >= h:
                    continue
                k = (idx >> (2 * i)) & 3
                r, g, b = cols[k]
                a = 0 if k == transparent else alpha[i]
                o = (y * w + x) * 4
                out[o:o + 4] = bytes((r, g, b, a))
    return bytes(out)


# MARK: SpriteFont（Fonts/SmallFont、SpriteFont1 及其 .zh-CN 版）

class SpriteFont(object):
    """glyphs: {字符: (x, y, w, h, 画的时候的 x 偏移, y 偏移, 前进宽度)}，都是贴图像素。"""

    def __init__(self, texture, glyphs, line_spacing, default_char=None):
        self.texture = texture
        self.glyphs = glyphs
        self.line_spacing = line_spacing
        self.default_char = default_char


def _read_utf8_char(cur):
    b0 = cur.u8()
    if b0 < 0x80:
        return chr(b0)
    n = 2 if b0 < 0xE0 else (3 if b0 < 0xF0 else 4)
    rest = bytes(cur.take(n - 1))
    return (bytes([b0]) + rest).decode("utf-8")


def read_sprite_font(data):
    payload = read_payload(data)
    readers, cur = read_readers(payload)
    idx = cur.varint()
    if idx == 0 or "SpriteFontReader" not in readers[idx - 1]:
        raise XnbError("这个 XNB 不是 SpriteFont")
    cur.varint()                       # Texture2DReader
    tex = _texture_body(cur)

    def rects():
        cur.varint()                   # List<Rectangle>
        return [struct.unpack_from("<iiii", bytes(cur.take(16))) for _ in range(cur.i32())]
    glyph_rects = rects()
    crops = rects()
    cur.varint()                       # List<char>
    chars = [_read_utf8_char(cur) for _ in range(cur.i32())]
    line_spacing = cur.i32()
    spacing = struct.unpack_from("<f", bytes(cur.take(4)))[0]
    cur.varint()                       # List<Vector3>
    kerning = [struct.unpack_from("<fff", bytes(cur.take(12))) for _ in range(cur.i32())]
    default = None
    try:
        if cur.varint() and cur.u8():
            default = _read_utf8_char(cur)
    except (IndexError, XnbError):
        pass
    glyphs = {}
    for ch, (x, y, w, h), (cx, cy, _cw, _ch), (kl, kw, kr) in zip(chars, glyph_rects, crops, kerning):
        glyphs[ch] = (x, y, w, h, kl + cx, cy, kl + kw + kr + spacing)
    return SpriteFont(tex, glyphs, line_spacing, default)


def load_sprite_font(path):
    with open(path, "rb") as fh:
        return read_sprite_font(fh.read())


def read_xml_source(data):
    """BmFont.XmlSource（Fonts/Chinese 这类 BMFont 描述文件）：就是一段 XML 文本。"""
    payload = read_payload(data)
    readers, cur = read_readers(payload)
    if cur.varint() == 0:
        raise XnbError("主对象为空")
    return cur.string()


def load_texture(path):
    with open(path, "rb") as fh:
        return read_texture(fh.read())


# MARK: Dictionary<string, string>（Data/Fish、Strings/Objects 这类数据表）

def read_string_dict(data):
    """从 .xnb 读出 Dictionary<string, string>。"""
    payload = read_payload(data)
    readers, cur = read_readers(payload)
    idx = cur.varint()
    if idx == 0:
        raise XnbError("主对象为空")
    if "DictionaryReader" not in readers[idx - 1]:
        raise XnbError("这个 XNB 不是字典（读取器: %s）" % readers[idx - 1].split(",")[0])
    count = cur.u32()
    out = {}
    for _ in range(count):
        key = _read_nullable_string(cur)
        value = _read_nullable_string(cur)
        out[key] = value
    return out


def _read_nullable_string(cur):
    # string 是引用类型：先是读取器编号（0 = null），再是 7 位编码长度 + UTF-8
    if cur.varint() == 0:
        return None
    return cur.string()


def load_string_dict(path):
    with open(path, "rb") as fh:
        return read_string_dict(fh.read())
