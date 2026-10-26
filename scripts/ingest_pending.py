#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫 XEC 网盘的上传暂存目录，自动收录管理器「发布」上来的主题包。

为什么需要它：原来的发布流程是"管理器上传到网盘 → 用户去 GitHub 开 issue 填直链 → 机器人收货"。
第二步在国内手机上经常直接卡死（github.com 打不开），用户看到的就是"上传了但商城一直没有"。
现在管理器把包传进 `/uploads/pending/`，这个脚本定时扫那个目录自动收货 —— **不需要 GitHub 账号**。
issue 表单那条路仍然保留（想留言、想要回执时用）。

幂等：靠**内容 sha256** 去重（已收录的同内容直接跳过），另外用 `pending-seen.json`
记住"已经看过的文件名"，避免每轮把同一个 20MB 的包重新下一遍。

触发：`.github/workflows/ingest-pending.yml`（每 10 分钟 + 手动 dispatch）。
"""
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from accept_theme import store_theme                                     # noqa: E402
from build_index import ROOT, load_json, read_theme_json                 # noqa: E402

BASE = os.environ.get('XEC_PAN_BASE', 'http://42.193.123.248:5244')
PENDING_DIR = os.environ.get('XEC_PENDING_DIR', '/uploads/pending')
SEEN_PATH = ROOT / 'pending-seen.json'
SEEN_LIMIT = 500
MAX_PER_RUN = 6
UA = 'xeckernelpro-themerepo'


def api(path, payload):
    request = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=60) as resp:
        return json.loads(resp.read())


def list_pending():
    data = api('/api/fs/list', {
        'path': PENDING_DIR, 'password': '', 'page': 1, 'per_page': 0, 'refresh': False,
    })
    if data.get('code') != 200:
        raise SystemExit('list failed: %s' % data.get('message'))
    return [item for item in (data.get('data') or {}).get('content') or []
            if not item.get('is_dir') and item.get('name', '').lower().endswith(('.xectheme', '.zip'))]


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=180) as resp:
        return resp.read()


def main():
    # 注意 build_index.load_json 收的是**相对 ROOT 的文件名**，不是路径。
    seen = load_json('pending-seen.json', {'seen': {}})
    entries = seen.setdefault('seen', {})
    hosted = load_json('hosted.json', {'themes': []})
    hosted_sha = {t.get('sha256') for t in hosted.get('themes', []) if t.get('sha256')}

    pending = list_pending()
    print('pending files: %d' % len(pending))
    accepted = 0
    checked = 0
    for item in pending:
        name = item['name']
        size = item.get('size') or 0
        known = entries.get(name)
        if known and known.get('size') == size:
            continue                      # 这一轮之前就看过了（收下或拒了），不再重复下载
        if checked >= MAX_PER_RUN:
            print('per-run cap reached, the rest waits for the next round')
            break
        checked += 1
        url = '%s/d%s/%s' % (BASE, PENDING_DIR, urllib.parse.quote(name))
        print('fetching %s (%d bytes)' % (name, size))
        try:
            blob = fetch(url)
        except Exception as exc:                                       # noqa: BLE001
            print('  download failed: %s' % exc)
            continue

        sha = hashlib.sha256(blob).hexdigest()
        if sha in hosted_sha:
            print('  already in the store (sha256 %s), skip' % sha[:12])
            entries[name] = {'sha256': sha, 'size': size, 'status': 'accepted',
                             'at': int(time.time()), 'note': 'already hosted'}
            continue
        try:
            theme_id, meta, rel, _preview = store_theme(blob)
        except ValueError as exc:
            # 校验不过就只记一笔：**不改仓库**，也不去评论（没有 issue 可评论）。
            print('  rejected: %s' % exc)
            entries[name] = {'sha256': sha, 'size': size, 'status': 'rejected',
                             'at': int(time.time()), 'note': str(exc)[:200]}
            continue
        hosted_sha.add(sha)
        accepted += 1
        print('  accepted %s (v%s, versionCode %s) -> %s' % (theme_id, meta['version'],
                                                             meta['versionCode'], rel))
        entries[name] = {'sha256': sha, 'size': size, 'status': 'accepted',
                         'at': int(time.time()), 'themeId': theme_id}

    # 只留最近 SEEN_LIMIT 条：这个文件是仓库里的状态，不能无限长。
    if len(entries) > SEEN_LIMIT:
        keep = sorted(entries.items(), key=lambda kv: kv[1].get('at') or 0, reverse=True)[:SEEN_LIMIT]
        seen['seen'] = dict(keep)
    seen['updatedAt'] = int(time.time())
    SEEN_PATH.write_bytes(
        (json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8'))

    if accepted == 0:
        print('nothing accepted this round')
        return 0

    import subprocess
    subprocess.check_call([sys.executable, str(ROOT / 'scripts' / 'build_index.py')])
    print('index rebuilt with %d new theme(s)' % accepted)
    return 0


if __name__ == '__main__':
    sys.exit(main())
