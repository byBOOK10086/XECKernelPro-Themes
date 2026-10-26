#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schema 3 索引生成的离线单测（不联网、不写真实仓库）。

跑法：python _scratch/themes_repo/test_build_index_v3.py

覆盖 build_index.py 的 v3 契约：对象形态、THEME_FIELDS、elements/types/category 派生、
previews/screenshots 排序、stats.json、meta.json、samples/ 预览兜底、banners/sections
（catalog.json 优先 + 自动派生）、UTF-8 无 BOM + LF，以及同一输入两次运行字节一致。
"""
import hashlib
import json
import pathlib
import sys
import tempfile
import zipfile

SCRIPTS = pathlib.Path(__file__).resolve().parent / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import build_index as B  # noqa: E402

checks = 0
problems = []


def check(label, condition, detail=''):
    global checks
    checks += 1
    if not condition:
        problems.append('%s %s' % (label, detail))


def make_package(path, meta, extra=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('theme.json', json.dumps(meta, ensure_ascii=False, indent=2))
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    blob = path.read_bytes()
    return blob


def base_meta(theme_id, **overrides):
    meta = {
        'schema': 1,
        'id': theme_id,
        'name': '主题 %s' % theme_id,
        'author': 'tester',
        'version': '1.0',
        'versionCode': 1,
        'summary': 'summary %s' % theme_id,
        'description': 'description %s' % theme_id,
        'createdAt': '2026-10-01T00:00:00Z',
    }
    meta.update(overrides)
    return meta


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='xec-index-v3-'))
    B.ROOT = tmp
    B.REPO = 'owner/repo'

    hosted = []
    alpha_meta = base_meta(
        'alpha-theme',
        colors={'dark': {'backdrop': '#101010', 'accent': '#11AA22'},
                'light': {'backdrop': '#F5F5F5', 'accent': '#0A7A11'}},
        tags=['暗色', '国风'],
    )
    alpha_blob = make_package(
        tmp / 'themes' / 'alpha-theme' / 'alpha-theme-1.xectheme',
        alpha_meta,
        {'preview.jpg': b'preview-bytes', 'background-dark.jpg': b'bg',
         'background-light.png': b'bg2', 'font/xec.ttf': b'font'},
    )
    alpha_dir = tmp / 'themes' / 'alpha-theme'
    (alpha_dir / 'alpha-theme-1.preview.png').write_bytes(b'png-preview')
    (alpha_dir / 'screenshot-2.jpg').write_bytes(b'shot2')
    (alpha_dir / 'screenshot-1.jpg').write_bytes(b'shot1')
    (alpha_dir / 'banner.jpg').write_bytes(b'banner')
    (alpha_dir / 'stats.json').write_text(json.dumps({
        'downloads': 42, 'rating': 4.5, 'ratingCount': 7, 'priceCents': 199,
    }), encoding='utf-8')
    (alpha_dir / 'meta.json').write_text(json.dumps({
        'featured': True,
        'changelog': 'v1 首版',
        'minManagerVersion': 30000,
        'publishedAt': '2026-10-02T00:00:00Z',
        'updatedAt': '2026-10-20T00:00:00Z',
        'bannerUrl': 'themes/alpha-theme/banner.jpg',
    }, ensure_ascii=False), encoding='utf-8')
    hosted.append({'id': 'alpha-theme',
                   'path': 'themes/alpha-theme/alpha-theme-1.xectheme',
                   'versionCode': 1,
                   'sha256': hashlib.sha256(alpha_blob).hexdigest(),
                   'size': len(alpha_blob)})

    beta_meta = base_meta(
        'beta-badge',
        createdAt='2026-10-05T00:00:00Z',
        modeBadge={'prefix': 'XEC'},
    )
    beta_blob = make_package(
        tmp / 'themes' / 'beta-badge' / 'beta-badge-1.xectheme', beta_meta)
    (tmp / 'samples').mkdir(parents=True, exist_ok=True)
    (tmp / 'samples' / 'beta-badge-1.preview.jpg').write_bytes(b'beta-preview')
    hosted.append({'id': 'beta-badge',
                   'path': 'themes/beta-badge/beta-badge-1.xectheme',
                   'versionCode': 1,
                   'sha256': hashlib.sha256(beta_blob).hexdigest(),
                   'size': len(beta_blob)})

    gamma_meta = base_meta('gamma-plain', createdAt='2026-10-03T00:00:00Z')
    gamma_blob = make_package(
        tmp / 'themes' / 'gamma-plain' / 'gamma-plain-1.xectheme', gamma_meta)
    hosted.append({'id': 'gamma-plain',
                   'path': 'themes/gamma-plain/gamma-plain-1.xectheme',
                   'versionCode': 1,
                   'sha256': hashlib.sha256(gamma_blob).hexdigest(),
                   'size': len(gamma_blob)})

    (tmp / 'hosted.json').write_bytes(
        (json.dumps({'themes': hosted}, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    (tmp / 'sources.json').write_bytes(b'{"themes": []}\n')

    code = B.main()
    check('build_index 退出码 0', code == 0, str(code))
    out_path = tmp / 'themes.json'
    first = out_path.read_bytes()
    check('无 BOM', not first.startswith(b'\xef\xbb\xbf'))
    check('LF 换行', b'\r' not in first)
    document = json.loads(first.decode('utf-8'))
    check('v3 对象', isinstance(document, dict) and document.get('schema') == 3, str(document))
    check('顶层键 = CATALOG_FIELDS', set(document) == set(B.CATALOG_FIELDS), sorted(document))
    check('generatedAt 可复现', document.get('generatedAt') == '2026-10-20T00:00:00Z',
          document.get('generatedAt'))

    themes = document.get('themes') or []
    check('主题数量', len(themes) == 3, str(len(themes)))
    by_id = {theme['themeId']: theme for theme in themes}
    check('主题顺序（updatedAt 倒序）', [t['themeId'] for t in themes] ==
          ['alpha-theme', 'beta-badge', 'gamma-plain'],
          [t['themeId'] for t in themes])
    for theme in themes:
        check('%s 字段 = THEME_FIELDS' % theme.get('themeId'),
              set(theme) == set(B.THEME_FIELDS),
              sorted(set(theme) ^ set(B.THEME_FIELDS)))
        check('%s 不输出 createdAt/schema' % theme.get('themeId'),
              'createdAt' not in theme and 'schema' not in theme)

    alpha = by_id['alpha-theme']
    check('alpha elements 派生', alpha['elements'] == ['colors', 'wallpaper', 'font'],
          alpha['elements'])
    check('alpha category = theme', alpha['category'] == 'theme', alpha['category'])
    check('alpha types 老口径', alpha['types'] == ['colors'], alpha['types'])
    check('alpha tags 来自包内', alpha['tags'] == ['暗色', '国风'], alpha['tags'])
    check('alpha stats.downloads', alpha['downloads'] == 42, alpha['downloads'])
    check('alpha stats.rating', alpha['rating'] == 4.5, alpha['rating'])
    check('alpha stats.ratingCount', alpha['ratingCount'] == 7, alpha['ratingCount'])
    check('alpha stats.priceCents', alpha['priceCents'] == 199, alpha['priceCents'])
    check('alpha preview 主题目录优先',
          alpha['previews'] == [B.jsdelivr('themes/alpha-theme/alpha-theme-1.preview.png')],
          alpha['previews'])
    check('alpha previewUrl = previews[0]', alpha['previewUrl'] == alpha['previews'][0])
    check('alpha screenshots 排序',
          alpha['screenshots'] == [B.jsdelivr('themes/alpha-theme/screenshot-1.jpg'),
                                   B.jsdelivr('themes/alpha-theme/screenshot-2.jpg')],
          alpha['screenshots'])
    check('alpha bannerUrl 来自 meta.json',
          alpha['bannerUrl'] == B.jsdelivr('themes/alpha-theme/banner.jpg'), alpha['bannerUrl'])
    check('alpha changelog 来自 meta.json', alpha['changelog'] == 'v1 首版', alpha['changelog'])
    check('alpha minManagerVersion', alpha['minManagerVersion'] == 30000,
          alpha['minManagerVersion'])
    check('alpha publishedAt', alpha['publishedAt'] == '2026-10-02T00:00:00Z',
          alpha['publishedAt'])
    check('alpha size 真实字节', alpha['size'] == len(alpha_blob), alpha['size'])
    check('alpha sha256 真实字节',
          alpha['sha256'] == hashlib.sha256(alpha_blob).hexdigest(), alpha['sha256'])
    check('alpha colors 三色', alpha['colors'] == {
        'accent': '#11AA22', 'backdropDark': '#101010', 'backdropLight': '#F5F5F5',
    }, alpha['colors'])

    beta = by_id['beta-badge']
    check('beta elements = modeBadge', beta['elements'] == ['modeBadge'], beta['elements'])
    check('beta category = badge', beta['category'] == 'badge', beta['category'])
    check('beta types = modeBadge', beta['types'] == ['modeBadge'], beta['types'])
    check('beta samples 预览兜底',
          beta['previews'] == [B.jsdelivr('samples/beta-badge-1.preview.jpg')], beta['previews'])
    check('beta bannerUrl 默认 previewUrl', beta['bannerUrl'] == beta['previewUrl'])
    check('beta stats 缺省 0', (beta['downloads'], beta['rating'], beta['ratingCount'],
                              beta['priceCents']) == (0, 0.0, 0, 0), str(beta))

    gamma = by_id['gamma-plain']
    check('gamma elements 兜底 colors', gamma['elements'] == ['colors'], gamma['elements'])
    check('gamma category = colors', gamma['category'] == 'colors', gamma['category'])
    check('gamma 无预览', gamma['previews'] == [] and gamma['previewUrl'] == '', gamma['previews'])

    banners = document.get('banners') or []
    check('自动合成 banner', len(banners) == 1 and banners[0]['themeId'] == 'alpha-theme',
          str(banners))
    check('自动 banner 字段', set(banners[0]) == set(B.BANNER_FIELDS), sorted(banners[0]))
    check('自动 banner 用 bannerUrl', banners[0]['imageUrl'] == alpha['bannerUrl'],
          banners[0]['imageUrl'])
    sections = document.get('sections') or []
    check('派生 latest/hot', [s['id'] for s in sections] == ['latest', 'hot'], str(sections))
    check('latest 取全部（≤5）', sections[0]['themeIds'] ==
          ['alpha-theme', 'beta-badge', 'gamma-plain'], sections[0]['themeIds'])
    check('hot 按 downloads 倒序取 5（存在 >0 才生成）',
          sections[1]['themeIds'] == ['alpha-theme', 'beta-badge', 'gamma-plain'],
          sections[1]['themeIds'])
    check('hot 标题', sections[1]['title'] == '本周热门', sections[1]['title'])

    second = (B.main(), out_path.read_bytes())[1]
    check('两次运行字节一致（自动派生）', second == first,
          '%s vs %s' % (hashlib.md5(first).hexdigest(), hashlib.md5(second).hexdigest()))

    # ---- catalog.json 优先 ---------------------------------------------------
    catalog = {
        'banners': [{
            'imageUrl': 'samples/beta-badge-1.preview.jpg',
            'themeId': 'beta-badge',
            'title': '运营横幅',
            'subtitle': '副标题',
        }],
        'sections': [
            {'id': 'editors', 'title': '编辑精选',
             'themeIds': ['beta-badge', 'alpha-theme', 'missing-theme']},
            {'id': 'empty', 'title': '空分区', 'themeIds': ['missing-theme']},
        ],
    }
    (tmp / 'catalog.json').write_bytes(
        (json.dumps(catalog, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    check('catalog 构建退出码 0', B.main() == 0)
    catalog_bytes = out_path.read_bytes()
    catalog_doc = json.loads(catalog_bytes.decode('utf-8'))
    catalog_banners = catalog_doc.get('banners') or []
    check('catalog banners 优先', len(catalog_banners) == 1 and
          catalog_banners[0]['title'] == '运营横幅', str(catalog_banners))
    check('catalog banner image 转仓库 URL',
          catalog_banners[0]['imageUrl'] == B.jsdelivr('samples/beta-badge-1.preview.jpg'),
          catalog_banners[0]['imageUrl'])
    catalog_sections = catalog_doc.get('sections') or []
    check('catalog sections 优先且过滤未知 id',
          len(catalog_sections) == 1 and catalog_sections[0]['id'] == 'editors' and
          catalog_sections[0]['themeIds'] == ['beta-badge', 'alpha-theme'],
          str(catalog_sections))
    check('catalog 构建两次一致', (B.main(), out_path.read_bytes())[1] == catalog_bytes)

    if problems:
        for line in problems:
            print('  FAIL %s' % line)
        print('FAIL %d checks, %d problems' % (checks, len(problems)))
        return 1
    print('OK %d checks' % checks)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
