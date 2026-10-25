#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 hosted.json（我们托管的 .xectheme）与 sources.json（作者自己托管的直链）生成 themes.json。

索引 schema（管理器 `data/themestore/ThemeStoreModels.kt` 按这个解析）：

  [
    {
      "themeId": "aurora-glass",
      "name": "极光玻璃",
      "author": "byBOOK10086",
      "version": "1.0",
      "versionCode": 1,
      "description": "……",
      "summary": "短描述（卡片上那一行）",
      "schema": 1,
      "updatedAt": "2026-10-15T00:00:00Z",
      "createdAt": "2026-10-15T00:00:00Z",
      "size": 123456,
      "sha256": "…64 位…",
      "downloadUrl": "https://cdn.jsdelivr.net/gh/…/themes/<id>/<file>.xectheme",
      "previewUrl": "https://cdn.jsdelivr.net/gh/…/themes/<id>/<file>.preview.jpg",
      "colors": {"accent": "#12B886", "backdropDark": "#0B0F10", "backdropLight": "#F2F5F6"},
      "previews": ["…多张预览图直链（v2，首图=previewUrl）…"],
      "types": ["colors" | "modeBadge"],
      "featured": true
    }
  ]

`colors` 是给商店卡片画缩略色块用的（管理器不下载整个包就能预览）：
  * accent       —— 主题强调色
  * backdropDark / backdropLight —— 深/浅两档页面底色
只有这三个是商店必需的，缺了就当未知（卡片退回默认灰）。

索引里出现的每一条都必须能下载、sha256 必须与实际字节一致 —— 宁可少一条，也不要写一条假的。
"""
import hashlib
import io
import json
import os
import pathlib
import re
import sys
import urllib.request
import zipfile

TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or ''
REPO = os.environ.get('GITHUB_REPOSITORY', 'byBOOK10086/XECKernelPro-Themes')
API = 'https://api.github.com'
ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = 'xeckernelpro-themerepo'

ID_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9._-]{1,63}$')
HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$')
MAX_PACKAGE_BYTES = 24 * 1024 * 1024
MAX_ENTRIES = 24


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
    if meta.get('schema') not in (1, 2):
        raise ValueError('schema 必须是 1 或 2（当前：%r）' % meta.get('schema'))
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
    import subprocess
    from datetime import datetime, timezone
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
    return 'https://cdn.jsdelivr.net/gh/%s@main/%s' % (REPO, path)


def entry_from_hosted(item):
    rel = item['path']
    # 读**本地工作树**里的包，而不是回头去 jsDelivr 下载：刚 push 上去的文件 CDN 还没缓存，
    # 下载会 404/拿到旧内容，索引就会把刚收下的主题整条跳过（第一次部署就踩了）。
    local = ROOT / rel
    if local.is_file():
        blob = local.read_bytes()
    else:
        blob = download(jsdelivr(rel))
    meta, _names = read_theme_json(blob)
    digest = hashlib.sha256(blob).hexdigest()
    if item.get('sha256') and item['sha256'] != digest:
        raise ValueError('%s: hosted.json 记的 sha256 与仓库里的字节不一致' % rel)
    updated = git_last_commit_time(rel) or item.get('updatedAt') or ''
    colors = accent_of(meta)
    base = rel.rsplit('.', 1)[0]
    preview = base + '.preview.jpg'
    # v2 字段：previews = 主题目录里所有预览图（首图与 previewUrl 一致），
    # types 供商城分类（模式牌主题单列一类）。
    previews = []
    theme_dir = ROOT / rel.rsplit('/', 1)[0]
    if theme_dir.is_dir():
        for img in sorted(theme_dir.glob('*.preview.jpg')):
            previews.append(jsdelivr(str(img.relative_to(ROOT)).replace(os.sep, '/')))
    if not previews:
        previews = [jsdelivr(preview)]
    badge = meta.get('modeBadge')
    types = ['modeBadge'] if isinstance(badge, dict) and any(
        isinstance(v, (str, dict)) and v for v in badge.values()) else ['colors']
    return {
        'themeId': meta['id'],
        'name': str(meta.get('name')),
        'author': str(meta.get('author') or ''),
        'version': str(meta.get('version')),
        'versionCode': int(meta['versionCode']),
        'description': str(meta.get('description') or ''),
        'summary': str(meta.get('summary') or meta.get('description') or '')[:120],
        'schema': int(meta['schema']),
        'size': len(blob),
        'sha256': digest,
        'updatedAt': updated,
        'createdAt': str(meta.get('createdAt') or updated),
        'downloadUrl': jsdelivr(rel),
        'previewUrl': jsdelivr(preview),
        'previews': previews,
        'types': types,
        'colors': colors,
    }


def entry_from_source(item):
    """作者自己托管：sources.json 给的是 .xectheme 直链。"""
    url = item['url']
    blob = download(url)
    meta, _names = read_theme_json(blob)
    digest = hashlib.sha256(blob).hexdigest()
    updated = str(meta.get('createdAt') or '')
    return {
        'themeId': meta['id'],
        'name': str(meta.get('name')),
        'author': str(meta.get('author') or ''),
        'version': str(meta.get('version')),
        'versionCode': int(meta['versionCode']),
        'description': str(meta.get('description') or ''),
        'summary': str(meta.get('summary') or meta.get('description') or '')[:120],
        'schema': int(meta['schema']),
        'size': len(blob),
        'sha256': digest,
        'updatedAt': updated,
        'createdAt': updated,
        'downloadUrl': url,
        'previewUrl': str(item.get('preview') or ''),
        'colors': accent_of(meta),
    }


def main():
    seen = {}
    hosted = load_json('hosted.json', {'themes': []})
    for item in hosted.get('themes', []):
        try:
            entry = entry_from_hosted(item)
        except Exception as exc:                                   # noqa: BLE001
            print('skip hosted %s: %s' % (item.get('path'), exc))
            continue
        seen[entry['themeId']] = entry
        print('  hosted  %-24s v%-8s %s' % (entry['themeId'], entry['versionCode'], entry['sha256'][:12]))

    sources = load_json('sources.json', {'themes': []})
    for item in sources.get('themes', []):
        try:
            entry = entry_from_source(item)
        except Exception as exc:                                   # noqa: BLE001
            print('skip source %s: %s' % (item.get('url'), exc))
            continue
        old = seen.get(entry['themeId'])
        if old and old['versionCode'] >= entry['versionCode']:
            continue
        seen[entry['themeId']] = entry
        print('  source  %-24s v%-8s %s' % (entry['themeId'], entry['versionCode'], entry['sha256'][:12]))

    # 精选位：featured.json 的 {"ids": [...]} 决定商城轮播横幅放谁（运营手工维护）。
    featured_ids = set(load_json('featured.json', {'ids': []}).get('ids', []))
    ordered = sorted(seen.values(), key=lambda e: (e['updatedAt'] or '', e['themeId']), reverse=True)
    for entry in ordered:
        entry['featured'] = entry['themeId'] in featured_ids
    out = ROOT / 'themes.json'
    text = json.dumps(ordered, ensure_ascii=False, indent=2) + '\n'
    old_text = out.read_text(encoding='utf-8') if out.is_file() else ''
    out.write_text(text, encoding='utf-8')
    print('themes.json: %d entries %s' % (len(ordered), '(changed)' if text != old_text else '(unchanged)'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
