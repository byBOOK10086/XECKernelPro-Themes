#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收下一个 .xectheme：校验 → 存进仓库 themes/<id>/ → 更新 hosted.json → 重建索引。

两种触发：
  * 手动 / workflow_dispatch：环境变量 INPUT_URL（zip 直链）、INPUT_ID（可留空）
  * issue 表单（用户填直链）：环境变量 ISSUE_BODY / ISSUE_NUMBER，脚本自己解析表单

校验不过就**不写任何东西**并把原因回帖（issue 会被自动关掉）。校验规则全部复用
build_index.read_theme_json：必须是 zip、≤24MB、条目 ≤24、不许有可执行文件、
不许有 `..`/绝对路径、theme.json 合法且 id/name/version/versionCode 齐备。

另外两件事：把包里的 preview.jpg 单独抽出来当作卡片预览（管理器不下载整包就能画卡片），
以及给 issue 回一条"怎么装"的说明。重建出来的 themes.json 是 schema 3（v3 对象形态），
预览图落盘名 `<id>-<versionCode>.preview.jpg` 正好能被 build_index 的预览扫描认出来。
"""
import base64
import hashlib
import io
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_index import (API, ID_RE, REPO, ROOT, TOKEN, api, download,  # noqa: E402
                         load_json, read_theme_json)

UA = 'xeckernelpro-themerepo'
PREVIEW_NAMES = ('preview.jpg', 'preview.jpeg', 'preview.png', 'preview.webp')
USAGE = """用法：
  python3 scripts/accept_theme.py --help
  INPUT_URL=<.xectheme 直链> [INPUT_ID=<期望 id>] python3 scripts/accept_theme.py
  ISSUE_NUMBER=<编号> ISSUE_BODY=<issue 模板正文> python3 scripts/accept_theme.py

收货后依次：校验包 → 写入 themes/<id>/<id>-<versionCode>.xectheme →
抽 preview 到同目录 → 更新 hosted.json → 调 build_index.py 重建 schema 3 索引。
"""


def fail(message):
    print('REJECT: %s' % message)
    comment = ('❌ 这个主题没有通过校验：\n\n```\n%s\n```\n\n'
               '修好之后重新开一个 issue 就行。主题包格式见 README。' % message)
    issue = os.environ.get('ISSUE_NUMBER')
    if issue:
        try:
            api('/repos/%s/issues/%s/comments' % (REPO, issue), 'POST', {'body': comment})
            api('/repos/%s/issues/%s' % (REPO, issue), 'PATCH', {'state': 'closed'})
        except Exception as exc:                                   # noqa: BLE001
            print('comment failed: %s' % exc)
    return 1


def comment(body):
    issue = os.environ.get('ISSUE_NUMBER')
    if not issue:
        return
    try:
        api('/repos/%s/issues/%s/comments' % (REPO, issue), 'POST', {'body': body})
        api('/repos/%s/issues/%s' % (REPO, issue), 'PATCH', {'state': 'closed'})
    except Exception as exc:                                       # noqa: BLE001
        print('comment failed: %s' % exc)


def parse_issue_body(body):
    fields = {}
    key = None
    for line in (body or '').splitlines():
        if line.startswith('### '):
            key = line[4:].strip()
            fields[key] = ''
        elif key is not None and line.strip() and not line.startswith('_No response_'):
            fields[key] = (fields[key] + '\n' + line).strip()
    return fields


def pick(fields, *needles):
    for name, value in fields.items():
        if any(needle in name for needle in needles):
            return (value or '').strip()
    return ''


def put_contents(path, blob, message):
    url_path = '/repos/%s/contents/%s' % (REPO, urllib.parse.quote(path))
    payload = {
        'message': message,
        'content': base64.b64encode(blob).decode('ascii'),
        'branch': 'main',
    }
    request = urllib.request.Request(API + url_path + '?ref=main')
    request.add_header('Authorization', 'Bearer ' + TOKEN)
    request.add_header('Accept', 'application/vnd.github+json')
    request.add_header('User-Agent', UA)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            payload['sha'] = json.loads(resp.read())['sha']
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    api(url_path, 'PUT', payload)


def extract_preview(blob, rel, theme_id):
    """把包里的 preview.jpg 单独抽一份出来：商店卡片只拉这张小图，不用下整个包。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        for name in zf.namelist():
            if name.lower() in PREVIEW_NAMES:
                data = zf.read(name)
                if len(data) > 2 * 1024 * 1024:
                    print('preview too large (%d bytes), skipped' % len(data))
                    return ''
                preview_rel = rel.rsplit('.', 1)[0] + '.preview.jpg'
                put_contents(preview_rel, data, 'theme preview: %s' % theme_id)
                print('stored preview %s (%d bytes)' % (preview_rel, len(data)))
                return preview_rel
    except Exception as exc:                                           # noqa: BLE001
        print('preview extraction failed: %s' % exc)
    return ''


def update_hosted(theme_id, rel, version_code, sha, size):
    # load_json 收的是**相对仓库根的文件名** + 默认值（不是路径）——ingest_pending 第一次跑
    # 就因为这里传了 Path 而 TypeError（2026-10-15 的 run 38752304428）。
    hosted = load_json('hosted.json', {'themes': []})
    entry = {
        'id': theme_id,
        'path': rel,
        'versionCode': version_code,
        'sha256': sha,
        'size': size,
    }
    themes = [t for t in hosted.get('themes', []) if t.get('id') != theme_id]
    themes.append(entry)
    hosted['themes'] = sorted(themes, key=lambda t: t['id'])
    (ROOT / 'hosted.json').write_bytes(
        (json.dumps(hosted, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print('hosted.json updated')


def store_theme(blob, expect_id=''):
    """校验并落盘一个主题包 —— **收货的唯一代码路径**。

    两条入口都走这里：issue 表单（accept_theme.main）与定时扫描网盘
    （ingest_pending.main）。只有一处实现，格式规则就不可能两边跑偏。

    返回 (theme_id, meta, rel, preview_rel)；包不合规（或 id 与调用方声明的不一致）
    抛 ValueError，调用方负责决定"回帖说原因"还是"只记一笔"。
    """
    meta, names = read_theme_json(blob)
    theme_id = str(meta['id'])
    if expect_id and expect_id != theme_id:
        raise ValueError('issue 里写的 ID（%s）与 theme.json 里的 id（%s）不一致'
                         % (expect_id, theme_id))
    version_code = int(meta['versionCode'])
    version = str(meta['version'])
    sha = hashlib.sha256(blob).hexdigest()
    rel = 'themes/%s/%s-%d.xectheme' % (theme_id, theme_id, version_code)
    put_contents(rel, blob, 'theme: %s v%s (versionCode %d)' % (theme_id, version, version_code))
    print('stored %s (%d bytes, sha256 %s, files: %s)' % (rel, len(blob), sha[:12], '、'.join(names[:12])))
    preview_rel = extract_preview(blob, rel, theme_id)
    update_hosted(theme_id, rel, version_code, sha, len(blob))
    return theme_id, meta, rel, preview_rel


def main():
    if '--help' in sys.argv or '-h' in sys.argv:
        print(USAGE)
        return 0
    fields = parse_issue_body(os.environ.get('ISSUE_BODY', ''))
    url = (os.environ.get('INPUT_URL') or pick(fields, '直链', 'url', 'URL', '链接')).strip()
    wanted_id = (os.environ.get('INPUT_ID') or pick(fields, 'ID', 'id')).strip()
    if not url.startswith('http'):
        return fail('没有拿到 .xectheme 的直链（issue 表单里那一栏要填）')

    print('downloading %s' % url)
    try:
        blob = download(url)
    except Exception as exc:                                       # noqa: BLE001
        return fail('直链下载失败：%s' % exc)

    try:
        theme_id, meta, rel, _preview = store_theme(blob, expect_id=wanted_id)
    except ValueError as exc:
        return fail(str(exc))
    version_code = int(meta['versionCode'])
    version = str(meta['version'])
    names = list(zipfile.ZipFile(io.BytesIO(blob)).namelist())

    import subprocess
    subprocess.check_call([sys.executable, str(ROOT / 'scripts' / 'build_index.py')])

    comment('✅ 收下了：**%s** v%s（versionCode %d，%d 字节）\n\n'
            '直链：https://cdn.jsdelivr.net/gh/%s@main/%s\n\n'
            '索引已重建，管理器「主题商城」刷新一下就能看到并一键应用。\n'
            '文件清单：%s' % (meta.get('name'), version, version_code, len(blob),
                              REPO, rel, '、'.join(names[:12])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
