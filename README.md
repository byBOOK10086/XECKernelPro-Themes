# XECKernelPro 主题仓库

[XECKernelPro 管理器](https://github.com/byBOOK10086/XECKernelPro) 的「主题商城」默认源。
索引是 [`themes.json`](themes.json)，当前是 **schema 3（对象形态）**，由
[`scripts/build_index.py`](scripts/build_index.py) 从 [`hosted.json`](hosted.json)（我们托管的包）
和 [`sources.json`](sources.json)（作者自己托管的直链）生成。

管理器默认读 jsDelivr 的副本：

```
https://cdn.jsdelivr.net/gh/byBOOK10086/XECKernelPro-Themes@main/themes.json
```

拉不到时自动回退 `https://raw.githubusercontent.com/byBOOK10086/XECKernelPro-Themes/main/themes.json`。

管理器侧解析器（`data/theme/StoreIndexCodec.kt`）同时认识三种形状：

| 形状 | 例子 | 说明 |
|---|---|---|
| v1 | `[ {...} ]` | 最早期的裸数组，只读 |
| v2 | `{"themes": [...]}` | 多一层对象，只读 |
| v3 | `{"schema": 3, "generatedAt": "...", "banners": [...], "sections": [...], "themes": [...]}` | 当前生成格式，**一律对象形态** |

v3 新增字段全部有默认值，老管理器读新索引只会忽略不认识的东西；新管理器读 v1/v2 也照常工作。
两边字段名逐字对齐，`_scratch/check_theme_contract.py` 会解析 Kotlin `StoreThemeModel.kt` /
`StoreCatalog.kt` 的 `data class`，和 `build_index.py` 的 `THEME_FIELDS`、实际 `themes.json`
三方比对，任何一边改名都会红。

## 我想发布自己的主题

1. 管理器 →「主题」→「主题编辑器」：基于当前外观改配色/背景/玻璃参数，填好名字与作者，**保存**；
2. 然后走**任意一条**路都行：

**A. 一键发布（推荐，不需要 GitHub 账号）**

在管理器「主题商城」页顶部点「发布我的主题」→ 选一个主题 → 它会被传到 XEC 网盘的
`/uploads/pending/`。本仓库的定时任务（`ingest-pending.yml`，每 10 分钟一轮）会扫那个目录，
校验、按 sha256 去重后自动收进 `themes/<id>/`、重建索引。管理器刷新商城即可看到。

**B. 开 issue 提交（想留言/要回执时用）**

把包传到任何能公网下载的地方（管理器里的「发布」也会给你一条直链），到
[提交主题](https://github.com/byBOOK10086/XECKernelPro-Themes/issues/new?template=upload-theme.yml)
填那条直链；机器人校验通过后会收进 `themes/<id>/`、重建索引并回帖关掉 issue。

两条路走的是**同一份收货代码**（`scripts/accept_theme.py` 的 `store_theme`），所以校验规则不会有差别。
已看过的上传（含被拒的）记在 `pending-seen.json` 里，避免每轮重新下载；被拒的包不会被收进仓库，
修好后用新文件名重新上传即可。

想自己托管也行：在 `sources.json` 里加一条 `{"id": "...", "url": "https://…/x.xectheme"}`（或开 issue 说明），
索引每 6 小时会自动跟进。

## 主题包格式（`.xectheme`）

就是一个 zip，根目录放 `theme.json`（必需），可选放背景图、字体、**区块背景图**与预览图：

```
theme.json
background-dark.jpg     # 可选，深色档背景
background-light.jpg    # 可选，浅色档背景
font/xec.ttf            # 可选，模式牌字体（.ttf/.otf）
block-home-status.jpg   # 可选，首页某张卡片的背景（见下「区块背景」）
preview.jpg             # 可选，商店卡片预览（≤2MB，会被单独抽出来）
```

**区块背景（`blocks`，2026-10-15 起）**：给首页每张卡片单独设背景（颜色/图片/透明度/压暗），
不写就完全不动那一页。目前支持六个 id：`home.status`、`home.update`、`home.warning`、
`home.privilege`、`home.support`、`home.info`。

```json
"blocks": {
  "home.status": {
    "color": "#AARRGGBB",              // 可选，可写 #RRGGBB（会自动补成不透明）
    "image": "block-home-status.jpg",  // 可选，zip 里的条目名（约定 block-<id 里的点换成横线>.jpg）
    "opacity": 1.0,                    // 0~1，整块（颜色+图）的不透明度
    "dim": 0.25,                       // 0~1，图上的黑色压暗，保证卡片文字可读
    "when": "both"                     // both | dark | light
  }
}
```

认不出的区块 id / 字段会被**安静忽略**（老管理器装新主题不报错，只是一块背景不生效）。

`theme.json`（包格式 `schema` 必须是 `1`；索引 schema 是另一回事，见下）：

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
  "tags": ["暗色", "玻璃"],
  "changelog": "1.0：首版",
  "minManagerVersion": 30000,
  "publishedAt": "2026-10-15T00:00:00Z",
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
* `tags` / `changelog` / `minManagerVersion` / `publishedAt` 是可选的 v3 元数据，缺失时索引取安全缺省。

## 索引格式（schema 3）

```json
{
  "schema": 3,
  "generatedAt": "2026-10-26T12:00:00Z",
  "banners": [{"imageUrl": "…", "themeId": "…", "title": "…", "subtitle": "…"}],
  "sections": [{"id": "hot", "title": "本周热门", "themeIds": ["…"]}],
  "themes": [ { "…": "见下表" } ]
}
```

### `themes[]` 字段表

| 字段 | 类型 | 来源 / 派生 | 缺省 |
|---|---|---|---|
| `themeId` | string | `theme.json` 的 `id`，`^[a-zA-Z][a-zA-Z0-9._-]{1,63}$` 且唯一 | 必需 |
| `name` | string | `theme.json` 的 `name` | 必需 |
| `author` | string | `theme.json` 的 `author` | `""` |
| `version` | string | `theme.json` 的 `version` | 必需 |
| `versionCode` | int | `theme.json` 的 `versionCode`（≥1） | 必需 |
| `summary` | string | `theme.json` 的 `summary`，没有就用 `description` 截断 120 字 | `""` |
| `description` | string | `theme.json` 的 `description` | `""` |
| `size` | int | 主题包的真实字节数（每次重建复算） | 必需 |
| `sha256` | string | 主题包真实字节的 SHA-256（每次重建复算） | 必需 |
| `downloadUrl` | string | hosted → jsDelivr 的包地址；sources → 作者直链 | 必需 |
| `previewUrl` | string | `previews[0]` | `""` |
| `previews` | string[] | 主题目录里 `*.preview.jpg` / `*.preview.png` 与 `preview-*.jpg` / `preview-*.png`，按文件名排序；没有再看 `samples/` 兜底 | `[]` |
| `updatedAt` | string(ISO) | 包的 git 最后提交时间 → `meta.json`/`theme.json` 的 `updatedAt` → `createdAt` | `createdAt` |
| `publishedAt` | string(ISO) | `meta.json`/`theme.json` 的 `publishedAt` → `createdAt` | `createdAt` |
| `category` | string | `elements` ≥2 种 → `theme`；否则单元素映射：`colors→colors`、`modeBadge→badge`、`font→font`、`wallpaper→wallpaper` | `colors` |
| `elements` | string[] | 从包内 `theme.json` + zip 条目推断，见下 | `["colors"]` |
| `tags` | string[] | `theme.json` 的可选 `tags` 数组 | `[]` |
| `screenshots` | string[] | 主题目录里 `screenshot-*.jpg` / `screenshot-*.png`，按文件名排序 | `[]` |
| `types` | string[] | v2 旧口径：含 `modeBadge` → `["modeBadge"]`，否则 `["colors"]` | `["colors"]` |
| `featured` | bool | `meta.json` / `theme.json` 的 `featured`（只认真布尔） | `false` |
| `downloads` | int | 主题目录可选 `stats.json` 的 `downloads` | `0` |
| `rating` | number | `stats.json` 的 `rating`（0~5，**不按下载量估算**） | `0.0` |
| `ratingCount` | int | `stats.json` 的 `ratingCount` | `0` |
| `priceCents` | int | `stats.json` 的 `priceCents`（分，0=免费） | `0` |
| `changelog` | string | `meta.json`/`theme.json` 的 `changelog` | `""` |
| `minManagerVersion` | int | `meta.json`/`theme.json` 的 `minManagerVersion` | `0` |
| `bannerUrl` | string | `meta.json`/`theme.json` 的 `bannerUrl`，没有就同 `previewUrl` | `previewUrl` |
| `colors` | object | `theme.json` 的配色：`{"accent", "backdropDark", "backdropLight"}`，各为 `#RRGGBB[AA]` 或 `""` | 空串 |

`colors` 在 Kotlin 侧映射成 `accentHex/backdropDarkHex/backdropLightHex` 三个字段，
`category` 映射成 `categoryRaw`（`category` 是 Kotlin 的计算属性）；`installedVersionCode`
是管理器本地字段，索引里不出现。

### `elements` 推断

| 元素 | 判定 |
|---|---|
| `colors` | `theme.json` 的 `colors.dark` 或 `colors.light` 非空 |
| `wallpaper` | zip 里有 `background-dark.*` 或 `background-light.*` |
| `font` | zip 里有 `font/*.ttf` 或 `font/*.otf` |
| `modeBadge` | `theme.json` 含 `modeBadge` 或 `badge` 键 |

四种都推不出时写 `["colors"]`，不允许凭空编造。元素顺序固定为
`colors, modeBadge, wallpaper, font`。

### `banners` / `sections`

优先读仓库根可选的 `catalog.json`：

```json
{
  "banners": [
    {"imageUrl": "samples/xecpro-aurora-1.preview.jpg", "themeId": "xecpro-aurora",
     "title": "极光示例", "subtitle": "XECKernelPro"}
  ],
  "sections": [
    {"id": "hot", "title": "本周热门", "themeIds": ["xecpro-aurora"]}
  ]
}
```

* `imageUrl` 可以是 http(s)，也可以是仓库相对路径（必须真实存在）。
* 没有 `catalog.json`（或其中没有对应键）时：`banners` 用 `featured` 且带预览图的主题合成，
  最多 5 个；`sections` 派生 `latest`（按 `updatedAt`/`publishedAt` 倒序取 5）与 `hot`
  （存在 `downloads>0` 时按 `downloads` 倒序取 5，否则不生成）。
* 引用了不存在主题的 banner/section 会被跳过并打印一行提示，索引本身保持可解析。

### 可选文件（主题目录，`themes/<id>/`）

`stats.json`（只放真实统计，没有就不写；**禁止随机/估算**）：

```json
{"downloads": 42, "rating": 4.5, "ratingCount": 7, "priceCents": 0}
```

`meta.json`（运营/补充元数据，覆盖或补充包内字段）：

```json
{
  "featured": true,
  "changelog": "1.1：修了深色模式对比度",
  "minManagerVersion": 30000,
  "publishedAt": "2026-10-15T00:00:00Z",
  "updatedAt": "2026-10-15T00:00:00Z",
  "bannerUrl": "themes/<id>/banner.jpg"
}
```

### 输出确定性

* 固定 `ensure_ascii=False, indent=2`、UTF-8 **无 BOM**、**LF** 换行；
* 字段顺序、主题顺序、`previews`/`screenshots` 顺序都固定，同一份输入连跑两次字节一致；
* `generatedAt` 不取墙钟时间，默认取索引里最新的真实时间戳（`updatedAt`/`publishedAt`），
  可用 `SOURCE_DATE_EPOCH` 覆盖。这样 CI 每 6 小时的例行重建不会仅仅因为“现在几点”就产生 diff。

## 校验规则（`scripts/build_index.py` / `scripts/accept_theme.py`）

* 必须是 zip，且根目录有合法的 `theme.json`；
* 单包 ≤ 24MB，条目 ≤ 24 个；
* 条目名不许有 `..`、绝对路径或反斜杠；
* 包里**不许**出现 `.sh` `.so` `.apk` `.dex` `.jar` `.bin` `.elf`；
* `id` 形如 `^[a-zA-Z][a-zA-Z0-9._-]{1,63}$`，`name`/`version`/`versionCode` 必须有；
* 进索引前会重新读包并复算 sha256/size，与 `hosted.json` 里记的不一致就跳过该条；
* 索引守卫 `python _scratch/check_theme_contract.py` 会核对 Kotlin 字段、真实包字节、路径可下载性。

拒绝的 issue 会被机器人回帖说明原因并关闭，改好后重新开一个即可。
