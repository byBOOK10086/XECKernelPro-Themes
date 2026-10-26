#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 hosted.json（我们托管的 .xectheme）与 sources.json（作者自己托管的直链）生成 themes.json。

索引 schema 3（管理器 `data/theme/StoreThemeModel.kt` / `StoreCatalog.kt` 按这个解析）：

  {
    "schema": 3,
    "generatedAt": "2026-10-26T12:00:00Z",
    "banners": [{"imageUrl": "...", "themeId": "...", "title": "...", "subtitle": "..."}],
    "sections": [{"id": "hot", "title": "本周热门", "themeIds": ["..."]}],
    "themes": [ { ...THEME_FIELDS... } ]
  }

v3 一律输出**对象形态**；管理器同样认识 v1 裸数组、v2 `{"themes":[...]}`，所以老索引不用回填。
`themes` 里每条主题的字段名逐字对应 Kotlin `StoreTheme`，字段表就是下面的 THEME_FIELDS
（`_scratch/check_theme_contract.py` 会把这份表与 Kotlin 模型、实际输出三方比对）。

派生规则（**不许编造数据**）：
  * elements：从包内 theme.json + zip 条目推断；推不出就当 ["colors"]；
  * types：老口径，含 modeBadge → ["modeBadge"]，否则 ["colors"]；
  * category：elements ≥2 种 → theme，否则按单元素映射；
  * previews/screenshots：只列仓库里真实存在的图（主题目录优先，samples/ 兜底）；
  * downloads/rating/ratingCount/priceCents：只读主题目录可选 stats.json，缺省 0；
  * changelog/minManagerVersion/publishedAt/bannerUrl：主题包 theme.json 或目录 meta.json；
  * sha256/size：对真实包字节计算。

输出确定性：同一份输入连跑两次字节一致。`generatedAt` 不取墙钟时间，而是取索引里最新的
真实时间戳（可用 SOURCE_DATE_EPOCH 覆盖），否则 CI 每 6 小时的例行重建会因为时间戳不同
而永远产生 diff。输出固定 UTF-8 无 BOM、LF、indent=2、ensure_ascii=False。
"""
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone

TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or ''
REPO = os.environ.get('GITHUB_REPOSITORY', 'byBOOK10086/XECKernelPro-Themes')
API = 'https://api.github.com'
ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = 'xeckernelpro-themerepo'

ID_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9._-]{1,63}$')
HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')
MAX_PACKAGE_BYTES = 24 * 1024 * 1024
MAX_ENTRIES = 24

# ---- schema 3 字段表（与 Kotlin `StoreTheme` 逐字对齐） --------------------
# JSON `colors` 映射 Kotlin `accentHex/backdropDarkHex/backdropLightHex`；
# JSON `category` 映射 Kotlin `categoryRaw`；Kotlin 的 `installedVersionCode` 是本地字段，不在索引里。
THEME_FIELDS = (
    'themeId', 'name', 'author', 'version', 'versionCode', 'summary',
    'description', 'size', 'sha256', 'downloadUrl', 'previewUrl', 'previews',
    'updatedAt', 'publishedAt', 'category', 'elements', 'tags', 'screenshots',
    'types', 'featured', 'downloads', 'rating', 'ratingCount', 'priceCents',
    'changelog', 'minManagerVersion', 'bannerUrl', 'colors',
)
BANNER_FIELDS = ('imageUrl', 'themeId', 'title', 'subtitle')
SECTION_FIELDS = ('id', 'title', 'themeIds')
CATALOG_FIELDS = ('schema', 'generatedAt', 'themes', 'banners', 'sections')

ELEMENTS = ('colors', 'modeBadge', 'wallpaper', 'font')
CATEGORIES = ('theme', 'colors', 'badge', 'font', 'wallpaper')
CATEGORY_OF_ELEMENT = {
    'colors': 'colors',
    'modeBadge': 'badge',
    'font': 'font',
    'wallpaper': 'wallpaper',
}
MAX_BANNERS = 5
SECTION_SIZE = 5
DEFAULT_TIMESTAMP = '1970-01-01T00:00:00Z'

ISO_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$')
BACKGROUND_RE = re.compile(r'^background-(?:dark|light)\.[^/]+$', re.I)
FONT_RE = re.compile(r'^font/[^/]+\.(?:ttf|otf)$', re.I)


def api(path, method='GET', body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', UA)
    if TOKEN:
        req.add_header('Authorization', 'Bearer ' + TOKEN)
    with urllib.request.urlopen(req, timeout=90) as resp:
        blob = resp.read()
    return json.loads(blob) if blob else None


def download(url):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UA)
    if TOKEN and url.startswith(API):
        req.add_header('Authorization', 'Bearer ' + TOKEN)
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


def read_theme_json(blob):
    """校验一个 .xectheme（zip）并返回 (metadata, 包内条目列表)。

    不是 zip、没有 theme.json、或者 theme.json 不合法都抛 ValueError —— 调用方据此拒绝。
    """
    if len(blob) > MAX_PACKAGE_BYTES:
        raise ValueError('包太大：%d 字节（上限 %d）' % (len(blob), MAX_PACKAGE_BYTES))
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise ValueError('不是 zip：%s' % exc)
    names = zf.namelist()
    if len(names) > MAX_ENTRIES:
        raise ValueError('条目太多：%d（上限 %d）' % (len(names), MAX_ENTRIES))
    for name in names:
        if name.startswith('/') or '..' in name.split('/') or '\\' in name:
            raise ValueError('条目名非法：%r' % name)
        low = name.lower()
        if low.endswith(('.sh', '.so', '.apk', '.dex', '.jar', '.bin', '.elf')):
            raise ValueError('主题包里不允许放可执行文件：%r' % name)
    if 'theme.json' not in names:
        raise ValueError('包里没有 theme.json')
    try:
        meta = json.loads(zf.read('theme.json').decode('utf-8'))
    except Exception as exc:                                       # noqa: BLE001
        raise ValueError('theme.json 解析失败：%s' % exc)
    if not isinstance(meta, dict):
        raise ValueError('theme.json 顶层必须是对象')
    if meta.get('schema') != 1:
        raise ValueError('schema 必须是 1（当前：%r）' % meta.get('schema'))
    theme_id = str(meta.get('id') or '')
    if not ID_RE.match(theme_id):
        raise ValueError('id 不合法：%r（要求 ^[a-zA-Z][a-zA-Z0-9._-]{1,63}$）' % theme_id)
    for key in ('name', 'version', 'versionCode'):
        if meta.get(key) in (None, ''):
            raise ValueError('theme.json 缺少 %s' % key)
    try:
        int(meta['versionCode'])
    except (TypeError, ValueError):
        raise ValueError('versionCode 不是整数：%r' % meta.get('versionCode'))
    # 颜色字段（有就校验形状，没有不算错 —— 老包可能只带背景图）
    colors = meta.get('colors') or {}
    if isinstance(colors, dict):
        for key, value in list(colors.items())[:64]:
            if isinstance(value, dict):
                for sub, subvalue in list(value.items())[:64]:
                    if isinstance(subvalue, str) and subvalue.startswith('#') and not HEX_RE.match(subvalue):
                        raise ValueError('颜色 %s.%s 不是 #RRGGBB[AA]：%r' % (key, sub, subvalue))
            elif isinstance(value, str) and value.startswith('#') and not HEX_RE.match(value):
                raise ValueError('颜色 %s 不是 #RRGGBB[AA]：%r' % (key, value))
    return meta, names


def accent_of(meta):
    """从 theme.json 里挑出商店卡片要用的三个颜色（缺就返回空串）。

    深/浅两档要各取各的 `backdrop`：写成一个 pick() 会让浅色档拿到深色档的底色，
    商店卡片的预览色块就永远是一块黑（第一次部署就是这么错的）。
    """
    colors = meta.get('colors') or {}
    dark = colors.get('dark') if isinstance(colors.get('dark'), dict) else {}
    light = colors.get('light') if isinstance(colors.get('light'), dict) else {}
    flat = {k: v for k, v in colors.items() if isinstance(v, str)}

    def first(source, *keys):
        for key in keys:
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, str) and value.startswith('#'):
                return value
        return ''

    return {
        'accent': (first(dark, 'accent') or first(light, 'accent')
                   or first(flat, 'accent') or first(colors, 'accent')),
        'backdropDark': first(dark, 'backdrop') or first(flat, 'backdropDark'),
        'backdropLight': first(light, 'backdrop') or first(flat, 'backdropLight'),
    }


def load_json(name, default):
    path = ROOT / name
    if not path.is_file():
        return default
    # utf-8-sig：Windows 上用记事本/PowerShell 存过的 JSON 会带 BOM，直接 json.loads 会炸在
    # 第一个字符上（第一次部署就踩了这一下）。BOM 对 JSON 没有意义，读的时候吃掉它。
    return json.loads(path.read_text(encoding='utf-8-sig'))


def git_last_commit_time(rel):
    try:
        out = subprocess.check_output(
            ['git', '-C', str(ROOT), 'log', '-1', '--format=%cI', '--', rel],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if not out:
            return ''
        return datetime.fromisoformat(out).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:                                              # noqa: BLE001
        return ''


def jsdelivr(path):
    text = path.as_posix() if isinstance(path, pathlib.PurePath) else str(path).replace('\\', '/')
    return 'https://cdn.jsdelivr.net/gh/%s@main/%s' % (REPO, text.lstrip('/'))


def _repo_relative(path):
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        raise ValueError('资源不在主题仓库目录里：%s' % path)


def asset_url(value, base_dir=None):
    """把 meta.json/catalog.json 里的图路径变成索引 URL。

    * http(s) 原样保留；
    * 相对路径依次按 base_dir、仓库根解析，必须真实存在（不写 404 链接）。
    """
    text = str(value or '').strip()
    if not text:
        return ''
    if re.match(r'^https?://', text, re.I):
        return text
    candidates = []
    if base_dir is not None:
        candidates.append(pathlib.Path(base_dir) / text)
    candidates.append(ROOT / text)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return jsdelivr(_repo_relative(candidate))
        except OSError:
            continue
    raise ValueError('资源路径在仓库里不存在：%r' % text)


def _list_files(directory):
    if directory is None or not pathlib.Path(directory).is_dir():
        return []
    return sorted((p for p in pathlib.Path(directory).iterdir() if p.is_file()),
                  key=lambda p: p.name)


def _is_preview_name(name):
    low = name.lower()
    if low.endswith('.preview.jpg') or low.endswith('.preview.png'):
        return True
    return low.startswith('preview-') and (low.endswith('.jpg') or low.endswith('.png'))


def _is_screenshot_name(name):
    low = name.lower()
    return low.startswith('screenshot-') and (low.endswith('.jpg') or low.endswith('.png'))


def _sample_previews(theme_id, extra_stems=()):
    """samples/ 兜底：本地骨架仓库里预览图可能只放在 samples/ 而没抽进 themes/<id>/。

    先按包文件名 stem 精确匹配（`<id>-<versionCode>.preview.jpg`），再退回按主题 id
    前缀匹配。两步都只认本主题相关文件名，避免把 `abc-def` 的预览挂到 `abc` 上。
    """
    exact = []
    for stem in extra_stems:
        for name in ('%s.preview.jpg' % stem, '%s.preview.png' % stem,
                     'preview-%s.jpg' % stem, 'preview-%s.png' % stem):
            path = ROOT / 'samples' / name
            if path.is_file():
                exact.append(path)
    if exact:
        return sorted(exact, key=lambda p: p.name)

    tid = theme_id.lower()
    out = []
    for path in _list_files(ROOT / 'samples'):
        low = path.name.lower()
        if not _is_preview_name(low):
            continue
        if (low.startswith(tid + '-') or low.startswith(tid + '.')
                or low.startswith('preview-' + tid)):
            out.append(path)
    return out


def preview_urls(theme_id, theme_dir, extra_stems=()):
    selected = _list_files(theme_dir)
    selected = [p for p in selected if _is_preview_name(p.name)]
    if not selected:
        selected = _sample_previews(theme_id, extra_stems)
    return [jsdelivr(_repo_relative(p)) for p in selected]


def screenshot_urls(theme_dir):
    return [jsdelivr(_repo_relative(p)) for p in _list_files(theme_dir)
            if _is_screenshot_name(p.name)]


def infer_elements(meta, names):
    """按包内 theme.json + zip 条目推断元素；推不出就退化成 ["colors"]。"""
    found = set()
    colors = meta.get('colors')
    dark = colors.get('dark') if isinstance(colors, dict) else meta.get('dark')
    light = colors.get('light') if isinstance(colors, dict) else meta.get('light')
    if dark or light:
        found.add('colors')
    for name in names:
        if BACKGROUND_RE.match(name):
            found.add('wallpaper')
        elif FONT_RE.match(name):
            found.add('font')
    if 'modeBadge' in meta or 'badge' in meta:
        found.add('modeBadge')
    if not found:
        found.add('colors')
    return [element for element in ELEMENTS if element in found]


def legacy_types(elements):
    """v2 的 types 口径：只分「模式牌」与「配色」两类，保留给老 UI。"""
    return ['modeBadge'] if 'modeBadge' in elements else ['colors']


def derive_category(elements):
    if len(elements) >= 2:
        return 'theme'
    if elements:
        return CATEGORY_OF_ELEMENT.get(elements[0], 'colors')
    return 'colors'


def _number(value, key):
    if isinstance(value, bool):
        raise ValueError('%s 必须是数字（当前 %r）' % (key, value))
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            pass
    raise ValueError('%s 必须是数字（当前 %r）' % (key, value))


def read_stats(theme_dir):
    stats = {'downloads': 0, 'rating': 0.0, 'ratingCount': 0, 'priceCents': 0}
    if theme_dir is None:
        return stats
    path = pathlib.Path(theme_dir) / 'stats.json'
    if not path.is_file():
        return stats
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('stats.json 顶层必须是对象')
    downloads = int(_number(data.get('downloads', 0), 'downloads'))
    rating = float(_number(data.get('rating', 0), 'rating'))
    rating_count = int(_number(data.get('ratingCount', 0), 'ratingCount'))
    price_cents = int(_number(data.get('priceCents', 0), 'priceCents'))
    if downloads < 0 or rating_count < 0 or price_cents < 0:
        raise ValueError('stats.json 里的 downloads/ratingCount/priceCents 不能为负')
    if not 0.0 <= rating <= 5.0:
        raise ValueError('stats.json 里的 rating 必须在 0~5（当前 %r）' % rating)
    stats.update(downloads=downloads, rating=rating, ratingCount=rating_count,
                 priceCents=price_cents)
    return stats


def read_meta(theme_dir):
    if theme_dir is None:
        return {}
    path = pathlib.Path(theme_dir) / 'meta.json'
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('meta.json 顶层必须是对象')
    return data


def _optional_int(*values):
    for value in values:
        if value in (None, ''):
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            raise ValueError('minManagerVersion 不是整数：%r' % value)
    return 0


def build_entry(meta, names, blob, download_url, theme_dir, updated_at='',
                preview_override='', sample_stems=()):
    """把一个已校验的包变成索引条目（hosted 与 sources 共用，字段口径只有这一份）。"""
    theme_id = str(meta['id'])
    created = str(meta.get('createdAt') or '')
    aux = read_meta(theme_dir)
    created = str(aux.get('createdAt') or created)
    updated = str(updated_at or aux.get('updatedAt') or meta.get('updatedAt') or created)

    previews = preview_urls(theme_id, theme_dir, sample_stems)
    if not previews and preview_override:
        previews = [asset_url(preview_override, theme_dir)]
    preview_url = previews[0] if previews else ''

    banner_value = aux.get('bannerUrl') or meta.get('bannerUrl') or ''
    banner_url = asset_url(banner_value, theme_dir) if banner_value else preview_url

    tags_value = meta.get('tags')
    if tags_value is None:
        tags = []
    elif isinstance(tags_value, list):
        tags = [item.strip() for item in tags_value if isinstance(item, str) and item.strip()]
    else:
        raise ValueError('theme.json 的 tags 必须是字符串数组')

    elements = infer_elements(meta, names)
    stats = read_stats(theme_dir)
    featured_value = aux.get('featured', meta.get('featured', False))
    return {
        'themeId': theme_id,
        'name': str(meta.get('name')),
        'author': str(meta.get('author') or ''),
        'version': str(meta.get('version')),
        'versionCode': int(meta['versionCode']),
        'summary': str(meta.get('summary') or meta.get('description') or '')[:120],
        'description': str(meta.get('description') or ''),
        'size': len(blob),
        'sha256': hashlib.sha256(blob).hexdigest(),
        'downloadUrl': download_url,
        'previewUrl': preview_url,
        'previews': previews,
        'updatedAt': updated,
        'publishedAt': str(aux.get('publishedAt') or meta.get('publishedAt') or created),
        'category': derive_category(elements),
        'elements': elements,
        'tags': tags,
        'screenshots': screenshot_urls(theme_dir),
        'types': legacy_types(elements),
        'featured': featured_value is True,
        'downloads': stats['downloads'],
        'rating': stats['rating'],
        'ratingCount': stats['ratingCount'],
        'priceCents': stats['priceCents'],
        'changelog': str(aux.get('changelog') or meta.get('changelog') or ''),
        'minManagerVersion': _optional_int(aux.get('minManagerVersion'),
                                           meta.get('minManagerVersion')),
        'bannerUrl': banner_url,
        'colors': accent_of(meta),
    }


def entry_from_hosted(item):
    rel = item['path']
    # 读**本地工作树**里的包，而不是回头去 jsDelivr 下载：刚 push 上去的文件 CDN 还没缓存，
    # 下载会 404/拿到旧内容，索引就会把刚收下的主题整条跳过（第一次部署就踩了）。
    local = ROOT / rel
    if local.is_file():
        blob = local.read_bytes()
    else:
        blob = download(jsdelivr(rel))
    meta, names = read_theme_json(blob)
    digest = hashlib.sha256(blob).hexdigest()
    if item.get('sha256') and item['sha256'] != digest:
        raise ValueError('%s: hosted.json 记的 sha256 与仓库里的字节不一致' % rel)
    if item.get('size') not in (None, '') and int(item['size']) != len(blob):
        raise ValueError('%s: hosted.json 记的 size 与仓库里的字节不一致' % rel)
    theme_id = str(meta['id'])
    theme_dir = ROOT / 'themes' / theme_id
    if not theme_dir.is_dir() and local.parent.is_dir():
        theme_dir = local.parent
    updated = git_last_commit_time(rel) or str(item.get('updatedAt') or '')
    stem = pathlib.PurePosixPath(rel).stem
    return build_entry(meta, names, blob, jsdelivr(rel), theme_dir, updated_at=updated,
                       sample_stems=(stem,))


def entry_from_source(item):
    """作者自己托管：sources.json 给的是 .xectheme 直链。"""
    url = item['url']
    blob = download(url)
    meta, names = read_theme_json(blob)
    theme_id = str(meta['id'])
    theme_dir = ROOT / 'themes' / theme_id
    if not theme_dir.is_dir():
        theme_dir = None
    return build_entry(meta, names, blob, url, theme_dir,
                       updated_at=str(item.get('updatedAt') or ''),
                       preview_override=str(item.get('preview') or ''))


def synth_banners(themes):
    """没有 catalog.json 时：featured 且带预览图的主题，最多 5 个。"""
    out = []
    for theme in themes:
        if not theme['featured']:
            continue
        if not theme['previewUrl'] and not theme['previews']:
            continue
        image = theme['bannerUrl'] or theme['previewUrl']
        if not image:
            continue
        out.append({
            'imageUrl': image,
            'themeId': theme['themeId'],
            'title': theme['name'],
            'subtitle': theme['author'],
        })
        if len(out) >= MAX_BANNERS:
            break
    return out


def derive_sections(themes):
    """没有 catalog.json 时：派生 latest；有 downloads>0 时再派生 hot。"""
    out = []
    ordered = sorted(themes, key=lambda item: item['themeId'])
    ordered.sort(key=lambda item: item['updatedAt'] or item['publishedAt'] or '', reverse=True)
    latest = ordered[:SECTION_SIZE]
    if latest:
        out.append({
            'id': 'latest',
            'title': '最新上架',
            'themeIds': [item['themeId'] for item in latest],
        })
    if any(item['downloads'] > 0 for item in themes):
        hot = sorted(themes, key=lambda item: (-item['downloads'], item['themeId']))[:SECTION_SIZE]
        out.append({
            'id': 'hot',
            'title': '本周热门',
            'themeIds': [item['themeId'] for item in hot],
        })
    return out


def load_catalog():
    path = ROOT / 'catalog.json'
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('catalog.json 顶层必须是对象')
    return data


def catalog_banners(catalog):
    raw = catalog.get('banners')
    if not isinstance(raw, list):
        raise ValueError('catalog.json 的 banners 必须是数组')
    out = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError('catalog.json banners[%d] 必须是对象' % index)
        banner = {key: str(item.get(key) or '').strip() for key in BANNER_FIELDS}
        if banner['imageUrl']:
            banner['imageUrl'] = asset_url(banner['imageUrl'], ROOT)
        if not banner['imageUrl'] and not banner['themeId']:
            continue
        out.append(banner)
    return out


def catalog_sections(catalog):
    raw = catalog.get('sections')
    if not isinstance(raw, list):
        raise ValueError('catalog.json 的 sections 必须是数组')
    out = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError('catalog.json sections[%d] 必须是对象' % index)
        section_id = str(item.get('id') or '').strip()
        if not section_id:
            raise ValueError('catalog.json sections[%d] 缺少 id' % index)
        ids_raw = item.get('themeIds')
        if not isinstance(ids_raw, list):
            raise ValueError('catalog.json sections[%d] 的 themeIds 必须是数组' % index)
        out.append({
            'id': section_id,
            'title': str(item.get('title') or '').strip() or section_id,
            'themeIds': [str(value).strip() for value in ids_raw
                         if isinstance(value, str) and value.strip()],
        })
    return out


def generated_at(themes):
    """可复现的 generatedAt：优先 SOURCE_DATE_EPOCH，否则取索引里最新的真实时间戳。

    不取 `datetime.now()`：同一输入两次运行必须字节一致，而且 CI 每 6 小时例行重建
    不应该仅仅因为"现在几点"就产生 diff。
    """
    epoch = os.environ.get('SOURCE_DATE_EPOCH', '').strip()
    if epoch.isdigit():
        return datetime.fromtimestamp(int(epoch), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    stamps = [item['updatedAt'] for item in themes] + [item['publishedAt'] for item in themes]
    stamps = [stamp for stamp in stamps if isinstance(stamp, str) and ISO_RE.match(stamp)]
    return max(stamps) if stamps else DEFAULT_TIMESTAMP


def main():
    entries = {}
    hosted = load_json('hosted.json', {'themes': []})
    if not isinstance(hosted, dict) or not isinstance(hosted.get('themes', []), list):
        print('hosted.json: 顶层必须是 {"themes": [...]}')
        return 2
    for item in hosted.get('themes', []):
        try:
            entry = entry_from_hosted(item)
        except Exception as exc:                                   # noqa: BLE001
            print('skip hosted %s: %s' % (item.get('path'), exc))
            continue
        entries[entry['themeId']] = entry
        print('  hosted  %-24s v%-8s %s' % (entry['themeId'], entry['versionCode'],
                                            entry['sha256'][:12]))

    sources = load_json('sources.json', {'themes': []})
    if not isinstance(sources, dict) or not isinstance(sources.get('themes', []), list):
        print('sources.json: 顶层必须是 {"themes": [...]}')
        return 2
    for item in sources.get('themes', []):
        try:
            entry = entry_from_source(item)
        except Exception as exc:                                   # noqa: BLE001
            print('skip source %s: %s' % (item.get('url'), exc))
            continue
        old = entries.get(entry['themeId'])
        if old and old['versionCode'] >= entry['versionCode']:
            continue
        entries[entry['themeId']] = entry
        print('  source  %-24s v%-8s %s' % (entry['themeId'], entry['versionCode'],
                                            entry['sha256'][:12]))

    themes = sorted(entries.values(), key=lambda item: item['themeId'])
    themes.sort(key=lambda item: item['updatedAt'] or item['publishedAt'] or '', reverse=True)

    try:
        catalog = load_catalog()
        if catalog is None:
            banners = synth_banners(themes)
            sections = derive_sections(themes)
        else:
            known = set(entries)
            banners = None
            sections = None
            if 'banners' in catalog:
                banners = []
                for banner in catalog_banners(catalog):
                    if banner['themeId'] and banner['themeId'] not in known:
                        print('  catalog banner -> unknown theme %s, skip' % banner['themeId'])
                        continue
                    banners.append(banner)
            if 'sections' in catalog:
                sections = []
                for section in catalog_sections(catalog):
                    theme_ids = [theme_id for theme_id in section['themeIds']
                                 if theme_id in known]
                    missed = len(section['themeIds']) - len(theme_ids)
                    if missed:
                        print('  catalog section %s: %d unknown theme id(s), skip'
                              % (section['id'], missed))
                    if theme_ids:
                        sections.append({'id': section['id'], 'title': section['title'],
                                         'themeIds': theme_ids})
            if banners is None:
                banners = synth_banners(themes)
            if sections is None:
                sections = derive_sections(themes)
    except Exception as exc:                                       # noqa: BLE001
        print('catalog.json invalid: %s' % exc)
        return 2

    document = {
        'schema': 3,
        'generatedAt': generated_at(themes),
        'banners': banners,
        'sections': sections,
        'themes': themes,
    }
    out = ROOT / 'themes.json'
    text = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
    old_bytes = out.read_bytes() if out.is_file() else b''
    new_bytes = text.encode('utf-8')
    out.write_bytes(new_bytes)
    print('themes.json: %d entries %s' % (len(themes), '(changed)' if new_bytes != old_bytes
                                          else '(unchanged)'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
