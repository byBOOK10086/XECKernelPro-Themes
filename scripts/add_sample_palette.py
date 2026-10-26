# -*- coding: utf-8 -*-
"""生成 3 个纯色板的示例主题（青瓷 / 琥珀 / 墨白），写进 themes/<id>/。

只做两件事：按调色板推整套令牌 → 打包成 .xectheme + 预览图 + 背景图。
不做随机、不编造下载量/评分（stats.json 一个都不写）。
"""
import json
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from make_sample_theme import tiny_jpeg  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent


def hex_to_rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def mix(color, other, ratio):
    c = hex_to_rgb(color)
    o = hex_to_rgb(other)
    return '#%02X%02X%02X' % tuple(
        int(round(c[i] + (o[i] - c[i]) * ratio)) for i in range(3)
    )


def alpha(color, a):
    return '#%02X%s' % (a, color.lstrip('#'))


def tokens(accent, dark_bg, light_bg, light_accent=None):
    light_accent = light_accent or mix(accent, '#000000', 0.35)
    return {
        'dark': {
            'backdrop': dark_bg,
            'backdropScrim': alpha(dark_bg, 0xCC),
            'surface': mix(dark_bg, '#FFFFFF', 0.06),
            'surfaceMuted': mix(dark_bg, '#FFFFFF', 0.11),
            'glassTint': alpha(mix(dark_bg, '#FFFFFF', 0.08), 0x8C),
            'glassRim': alpha(accent, 0x3A),
            'text': '#F5F2F8',
            'textSecondary': '#CFC7D8',
            'textMuted': '#9A93A6',
            'accent': accent,
            'accentSoft': mix(dark_bg, accent, 0.22),
            'water': alpha(accent, 0x6B),
        },
        'light': {
            'backdrop': light_bg,
            'backdropScrim': alpha(light_bg, 0xE6),
            'surface': '#FFFFFF',
            'surfaceMuted': mix(light_bg, '#000000', 0.05),
            'glassTint': '#8CFFFFFF',
            'glassRim': mix(light_bg, '#000000', 0.12),
            'text': '#141018',
            'textSecondary': '#4A4453',
            'textMuted': '#7A7484',
            'accent': light_accent,
            'accentSoft': mix(light_bg, light_accent, 0.14),
            'water': alpha(light_accent, 0x6B),
        },
    }


THEMES = [
    {
        'id': 'xecpro-celadon',
        'name': '青瓷',
        'accent': '#4FD1A5',
        'dark_bg': '#08120F',
        'light_bg': '#F3FBF8',
        'tags': ['示例', '冷色', '低饱和'],
        'summary': '青瓷示例主题：冷调青绿强调色，暗色像上釉的深青，亮色是干净的瓷白。',
        'description': (
            '示例主题之三。整包主题：配色 + 明暗两张背景。\n'
            '· 暗色：深青黑底 + 青瓷绿强调；\n'
            '· 亮色：瓷白底 + 墨绿强调；\n'
            '· 圆角偏小、玻璃偏实，页面看着更"器物"。\n'
            '想改就用管理器「主题编辑器」改完导出，商城上传即可。'
        ),
        'shapes': {'sm': 8, 'md': 12, 'lg': 18, 'xl': 24},
        'glass': {'tintAlpha': 0.66, 'refraction': 0.8, 'blurRadius': 1.1},
        'featured': True,
        'changelog': '首次上架：青瓷绿整套令牌 + 明暗双背景。',
    },
    {
        'id': 'xecpro-ember',
        'name': '琥珀',
        'accent': '#FF8A4C',
        'dark_bg': '#140F0D',
        'light_bg': '#FFF7F1',
        'tags': ['示例', '暖色', '高对比'],
        'summary': '琥珀示例主题：暖橙强调色，暗色暖黑底像灯下的木桌，亮色是米白纸感。',
        'description': (
            '示例主题之四。整包主题：配色 + 明暗两张背景。\n'
            '· 暗色：暖黑底 + 琥珀橙强调；\n'
            '· 亮色：米白底 + 赤陶强调；\n'
            '· 圆角与玻璃居中，暖色页面更"重"。'
        ),
        'shapes': {'sm': 10, 'md': 15, 'lg': 20, 'xl': 26},
        'glass': {'tintAlpha': 0.72, 'refraction': 0.9, 'blurRadius': 1.2},
        'featured': True,
        'changelog': '首次上架：琥珀橙整套令牌 + 明暗双背景。',
    },
    {
        'id': 'xecpro-mono',
        'name': '墨白',
        'accent': '#D8D8DC',
        'dark_bg': '#0A0A0B',
        'light_bg': '#FAFAFA',
        'light_accent': '#111114',
        'tags': ['示例', '无彩色', '极简'],
        'summary': '墨白示例主题：纯灰阶无彩色主题，靠形状和留白拉开层次，不抢任何内容色。',
        'description': (
            '示例主题之五。整包主题：配色 + 明暗两张背景。\n'
            '· 暗色：近黑底 + 浅灰强调；\n'
            '· 亮色：纸白底 + 墨黑强调；\n'
            '· 全套中性色，适合配截图/看文字。'
        ),
        'shapes': {'sm': 6, 'md': 10, 'lg': 14, 'xl': 18},
        'glass': {'tintAlpha': 0.6, 'refraction': 0.7, 'blurRadius': 1.0},
        'featured': False,
        'changelog': '首次上架：灰阶整套令牌 + 明暗双背景。',
    },
]


def build(theme):
    outdir = REPO / 'themes' / theme['id']
    outdir.mkdir(parents=True, exist_ok=True)
    stem = '%s-%d' % (theme['id'], 1)
    palette = tokens(
        theme['accent'],
        theme['dark_bg'],
        theme['light_bg'],
        theme.get('light_accent'),
    )
    meta = {
        'schema': 1,
        'id': theme['id'],
        'name': theme['name'],
        'author': 'XECKernelPro',
        'version': '1.0',
        'versionCode': 1,
        'summary': theme['summary'],
        'description': theme['description'],
        'tags': theme['tags'],
        'changelog': theme['changelog'],
        'createdAt': '2026-10-26T00:00:00Z',
        'colors': palette,
        'shapes': theme['shapes'],
        'glass': theme['glass'],
        'background': {},
    }
    preview = tiny_jpeg(540, 960, hex_to_rgb(theme['dark_bg']))
    bg_dark = tiny_jpeg(1080, 2400, hex_to_rgb(theme['dark_bg']))
    bg_light = tiny_jpeg(1080, 2400, hex_to_rgb(theme['light_bg']))
    pkg = outdir / (stem + '.xectheme')
    with zipfile.ZipFile(pkg, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('theme.json', json.dumps(meta, ensure_ascii=False, indent=2))
        zf.writestr('preview.jpg', preview)
        zf.writestr('background-dark.jpg', bg_dark)
        zf.writestr('background-light.jpg', bg_light)
    (outdir / (stem + '.preview.jpg')).write_bytes(preview)
    (outdir / 'meta.json').write_text(
        json.dumps(
            {'featured': theme['featured'], 'publishedAt': '2026-10-26T00:00:00Z'},
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    print('wrote %s (%d bytes)' % (pkg, pkg.stat().st_size))


def main():
    for theme in THEMES:
        build(theme)


if __name__ == '__main__':
    main()
