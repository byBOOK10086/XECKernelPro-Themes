#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成一个示例主题包（用来验证索引/商店链路是通的，也当格式模板）。

用法：python3 scripts/make_sample_theme.py [输出目录]
产物：<输出目录>/xecpro-aurora-1.xectheme
      <输出目录>/xecpro-aurora-1.preview.jpg
"""
import io
import json
import pathlib
import struct
import sys
import zipfile

THEME = {
    'schema': 1,
    'id': 'xecpro-aurora',
    'name': '极光示例主题',
    'author': 'XECKernelPro',
    'version': '1.0',
    'versionCode': 1,
    'summary': '示例/模板主题：青绿极光配色，用来验证主题商城与换肤链路是通的。',
    'description': (
        '这是主题仓库自带的示例主题，可以直接照这个结构改成你自己的：\n'
        '1) 在管理器「主题编辑器」里改配色/背景，保存；\n'
        '2) 导出 .xectheme；\n'
        '3) 到主题仓库开 issue 提交直链。'
    ),
    'createdAt': '2026-10-15T00:00:00Z',
    'colors': {
        'dark': {
            'backdrop': '#04100C',
            'backdropScrim': '#CC04100C',
            'surface': '#0A1A15',
            'surfaceMuted': '#10241D',
            'glassTint': '#8C0A1A15',
            'glassRim': '#1E3A31',
            'text': '#E6F5EF',
            'textSecondary': '#B4CFC5',
            'textMuted': '#7E9C92',
            'accent': '#2BE3A4',
            'accentSoft': '#0F2A21',
            'water': '#6B2BE3A4',
        },
        'light': {
            'backdrop': '#F1F7F5',
            'backdropScrim': '#E6F1F7F5',
            'surface': '#FFFFFF',
            'surfaceMuted': '#E7F2EE',
            'glassTint': '#8CFFFFFF',
            'glassRim': '#D5E5DF',
            'text': '#0C1A16',
            'textSecondary': '#3F5750',
            'textMuted': '#6E837C',
            'accent': '#0FA47A',
            'accentSoft': '#DFF5EC',
            'water': '#6B0FA47A',
        },
    },
    'shapes': {'sm': 10, 'md': 16, 'lg': 22, 'xl': 30},
    'glass': {'tintAlpha': 0.55, 'refraction': 1.0, 'blurRadius': 1.0},
    'background': {},
}


def tiny_jpeg(w, h, rgb):
    """不依赖 Pillow 的最小 JPEG：给预览图用（纯色块）。"""
    # 极简基线 JPEG 编码器：一个 DC-only 的 8x8 块重复，够画纯色预览。
    import math
    qt = [16] * 64

    def seg(marker, payload):
        return struct.pack('>BBH', 0xFF, marker, len(payload) + 2) + payload

    out = bytearray(b'\xff\xd8')
    out += seg(0xDB, bytes([0]) + bytes(qt))
    sof = struct.pack('>BHHB', 8, h, w, 3) + bytes([1, 0x11, 0, 2, 0x11, 1, 3, 0x11, 1])
    out += seg(0xC0, sof)
    out += seg(0xC4, bytes([0]) + bytes([0] * 16))
    y = int(0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2])
    cb = int(128 - 0.168736 * rgb[0] - 0.331264 * rgb[1] + 0.5 * rgb[2])
    cr = int(128 + 0.5 * rgb[0] - 0.418688 * rgb[1] - 0.081312 * rgb[2])
    # DC 系数：把差分编码的起点直接给到目标亮度
    dc_y = max(-1023, min(1023, (y - 128) * 8))
    dc_c = max(-1023, min(1023, (cb - 128) * 8))
    dc_r = max(-1023, min(1023, (cr - 128) * 8))

    def cat(value):
        size = 0
        v = abs(value)
        while v:
            size += 1
            v >>= 1
        return size

    bits = []
    for _ in range(0, w * h // 64 + 1):
        for val in (dc_y, dc_c, dc_r):
            size = cat(val)
            bits.append((size, val if val >= 0 else val + (1 << size) - 1, size))

    stream = bytearray()
    acc = 0
    nbits = 0

    def put(code, length):
        nonlocal acc, nbits
        acc = (acc << length) | (code & ((1 << length) - 1))
        nbits += length
        while nbits >= 8:
            nbits -= 8
            stream.append((acc >> nbits) & 0xFF)

    for size, val, ln in bits:
        put(size, 4)
        if size:
            put(val, size)
    put(0, 2)
    put(0, 2)
    put(0, 2)
    if nbits:
        put((1 << (8 - nbits)) - 1, 8 - nbits)
    payload = bytes(stream).replace(b'\xff', b'\xff\x00')
    out += seg(0xDA, bytes([3, 1, 0, 2, 0x11, 3, 0x11, 0, 63, 0])) + payload
    out += b'\xff\xd9'
    return bytes(out)


def main():
    outdir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'samples')
    outdir.mkdir(parents=True, exist_ok=True)
    preview = tiny_jpeg(320, 180, (0x0A, 0x1A, 0x15))
    pkg = outdir / 'xecpro-aurora-1.xectheme'
    with zipfile.ZipFile(pkg, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('theme.json', json.dumps(THEME, ensure_ascii=False, indent=2))
        zf.writestr('preview.jpg', preview)
    (outdir / 'xecpro-aurora-1.preview.jpg').write_bytes(preview)
    print('wrote %s (%d bytes)' % (pkg, pkg.stat().st_size))
    print('wrote %s' % (outdir / 'xecpro-aurora-1.preview.jpg'))


if __name__ == '__main__':
    main()
