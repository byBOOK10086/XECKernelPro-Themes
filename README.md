# XECKernelPro 主题仓库

[XECKernelPro 管理器](https://github.com/byBOOK10086/XECKernelPro) 的「主题商城」默认源。
索引是 [`themes.json`](themes.json)，由 [`scripts/build_index.py`](scripts/build_index.py) 从
[`hosted.json`](hosted.json)（我们托管的包）和 [`sources.json`](sources.json)（作者自己托管的直链）生成。

管理器默认读 jsDelivr 的副本：

```
https://cdn.jsdelivr.net/gh/byBOOK10086/XECKernelPro-Themes@main/themes.json
```

拉不到时自动回退 `https://raw.githubusercontent.com/byBOOK10086/XECKernelPro-Themes/main/themes.json`。

## 我想发布自己的主题

1. 管理器 →「主题」→「主题编辑器」：基于当前外观改配色/背景/玻璃参数，填好名字与作者，**保存**；
2. 同一个页面点「导出主题包」，得到 `你的主题.xectheme`；想直接分享就用「导出并发布」，
   它会把包传到 XEC 网盘并给你一条直链；
3. 到 [提交主题](https://github.com/byBOOK10086/XECKernelPro-Themes/issues/new?template=upload-theme.yml)
   填那条直链；
4. 机器人校验通过后会把它收进 `themes/<id>/`、重建索引并关掉 issue。管理器刷新即可看到。

想自己托管也行：在 `sources.json` 里加一条 `{"id": "...", "url": "https://…/x.xectheme"}`（或开 issue 说明），
索引每 6 小时会自动跟进。

## 主题包格式（`.xectheme`）

就是一个 zip，根目录放 `theme.json`（必需），可选放背景图与预览图：

```
theme.json
background-dark.jpg     # 可选，深色档背景
background-light.jpg    # 可选，浅色档背景
preview.jpg             # 可选，商店卡片预览（≤2MB，会被单独抽出来）
```

`theme.json`（`schema` 必须是 `1`）：

```json
{
  "schema": 1,
  "id": "aurora-glass",
  "name": "极光玻璃",
  "author": "byBOOK10086",
  "version": "1.0",
  "versionCode": 1,
  "description": "一句话到一段话都行",
  "summary": "卡片上显示的一行",
  "createdAt": "2026-10-15T00:00:00Z",
  "colors": {
    "dark":  { "backdrop": "#0B0F10", "surface": "#131A1C", "accent": "#12B886", "text": "#E7EDEE" },
    "light": { "backdrop": "#F2F5F6", "surface": "#FFFFFF", "accent": "#0E9E76", "text": "#161D1F" }
  },
  "shapes": { "sm": 10, "md": 16, "lg": 22 },
  "glass": { "tintAlpha": 0.55, "refraction": 1.0 },
  "background": { "dark": "background-dark.jpg", "light": "background-light.jpg" }
}
```

* 颜色一律 `#RRGGBB` 或 `#AARRGGBB`；不认识的键会被管理器忽略（向前兼容）。
* `colors.dark` / `colors.light` 里只需要写你想改的令牌，其余沿用管理器默认值。
* `accent`、`colors.dark.backdrop`、`colors.light.backdrop` 会被索引用作商店卡片的缩略色块。

## 校验规则（`scripts/build_index.py` / `scripts/accept_theme.py`）

* 必须是 zip，且根目录有合法的 `theme.json`；
* 单包 ≤ 24MB，条目 ≤ 24 个；
* 条目名不许有 `..`、绝对路径或反斜杠；
* 包里**不许**出现 `.sh` `.so` `.apk` `.dex` `.jar` `.bin` `.elf`；
* `id` 形如 `^[a-zA-Z][a-zA-Z0-9._-]{1,63}$`，`name`/`version`/`versionCode` 必须有；
* 进索引前会重新下载并复算 sha256，与 `hosted.json` 里记的不一致就跳过该条。

拒绝的 issue 会被机器人回帖说明原因并关闭，改好后重新开一个即可。
