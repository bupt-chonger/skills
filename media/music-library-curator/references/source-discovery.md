# 音源发现 · 实操流程

> 从「我要下载某首歌」到「拿到可下载的网盘分享」的完整路径。
> 这是整条流水线里最耗时的一环——**技术再熟，找不到源就无从下手**。

## 优先级顺序

从省事到麻烦，依次尝试：

### 1 · QQ 音乐官方接口（最优先）

QQ 音乐既是最好的**歌词源**，也常是**下载源**。

```bash
# 搜歌拿 songmid / albummid
curl -s -H "User-Agent: Mozilla/5.0" -H "Referer: https://y.qq.com/" \
 "https://c.y.qq.com/soso/fcgi-bin/client_search_cp?p=1&n=12&w=<关键词>&format=json"
```

> ⚠️ `musicu.fcg` 的 POST 形式已失效（返回 `bad request`），
> `client_search_cp` 的 GET 形式仍可用。搜索响应是 **HTML 转义**的
> （`mid` 字段会显示为 `None`），需用 `fcg_v8_album_info_cp.fcg` 二次确认。

拿到 albummid 后：

```bash
# 列全部曲目 + songmid
curl -s -H "Referer: https://y.qq.com/" \
 "https://c.y.qq.com/v8/fcg-bin/fcg_v8_album_info_cp.fcg?format=json&albummid=<albummid>"
```

### 2 · PanSou 聚合搜索（网盘资源首选）

聚合 90+ TG 频道与 60+ 网站插件的网盘链接索引。

```bash
curl -s "https://s.panhunt.com/api/search?kw=<关键词>&res=merge&src=all&page=1&limit=30"
```

**关键**：必须带 `res=merge&src=all`，否则只搜指定网盘且结果为空。

返回结构里 `merged_by_type` 按网盘类型分组，每项含 `url` / `note` / `password`。
`password` 字段**常常就是提取码**——这是免密分享的主要来源。

> ⚠️ 接口有速率限制，连续查询会返回非 JSON。批量查询之间 sleep 2–3 秒。

### 3 · HiFi 类论坛（质量最好，但提取码常隐藏）

`hifiti.com` / `hifiti.cc` / `hifiri.com` / `wsyycc.com` / `gggmusic.com` /
`yinyuemoshi.com` —— 提供母带级 FLAC，通常**内嵌封面歌词**。

**找帖技巧**：直接抓歌手标签页，比搜索引擎快且准：

```bash
curl -s "https://www.hifiti.com/tag-361.htm" -o tag.html
grep -oE 'href="[^"]*thread-[0-9]+\.htm?"[^>]*>[^<]{0,120}' tag.html | grep 晚风
```

**提取码的三种可见性**：

| 形式 | 特征 | 处理 |
|---|---|---|
| 直接公开 | 页面里有 `提取码: abcd` | 直接用 |
| 回复可见 | `提取码 回复 查看` | 需注册回帖，或另找源 |
| 隐藏内容 | `本帖含有隐藏内容，请您 回复 后查看` | 同上 |

**当论坛源都要码时**，转去找聚合站或播放器站——它们往往**不带码**。

### 4 · 播放器站（免密分享的最佳来源）

`higequ.com/player/<id>`、`gequbao.com/music/<id>`、`51hires.com`、`51flacmusic.com`。

播放器站的 HTML 里**直接内嵌夸克分享链接**，且**通常免提取码**：

```bash
curl -s "https://higequ.com/player/521282703" -o p.html
grep -oE 'pan\.quark\.cn/s/[0-9a-zA-Z]+' p.html
```

**同时还是封面来源**：播放器页会引用专辑封面图（常来自酷我 CDN）：

```html
<img id="album-cover" src="https://img1.kuwo.cn/star/albumcover/300/....jpg">
```

酷我封面图可换分辨率前缀：`/1000/`、`/500/`、`/300/`、`/200/`，1000 约 270 KB。

### 5 · 直接找免密分享

有的分享压根不需要提取码。用 `quark_download.py --list-only` 逐个验证比猜快。

```bash
python3 scripts/quark_download.py --pwd-id <id> --out /tmp/x --jar /tmp/j.txt \
    --auto-dir --list-only
```

返回 `code=41008 需要提取码` 即需码；返回文件列表即免密。

---

## 各站点的提取码可见性速查

| 站点 | 提取码 | 备注 |
|---|---|---|
| `hifiti.com` / `hifiti.cc` | 回复可见 | 帖子多、版本全 |
| `hifiri.com` | 回复可见 | — |
| `wsyycc.com` | 回复可见 | — |
| `gggmusic.com` | 部分公开 | 页面含完整歌词 |
| `yinyuemoshi.com` | **公开** | 搜索结果里直接可见 |
| `higequ.com` | **无需提取码** | 内嵌夸克链接 + 封面 |
| `gequbao.com` | **无需提取码** | 同上，且歌词带时间轴 |
| `51hires.com` | 需登录 | 网盘信息登录后可见 |
| PanSou 聚合 | `password` 字段常为空 | 空即免密 |

---

## 实战案例：《街角的晚风》陈小春

```
① QQ 音乐搜歌
   client_search_cp?w=街角的晚风
   → 陈小春版 albummid=0028jKt80PGmlB, songmid=001e2FJz3QXaf0

② PanSou 搜"街角的晚风"
   → total=1，命中的是无关短剧 ❌
   → 换关键词组合（加歌手/格式）仍为 0

③ HiFiTi 标签页找帖
   tag-361.htm → 5 个相关帖
   → quark 链接 17a57044f380，提取码「回复查看」❌

④ 其它论坛
   yinyuemoshi.com/thread-107.htm
   → quark 18a8468df13b 提取码 hsfT（MP3 9.6MB）✅
   → quark 8c7bde41cb3a 提取码 s9F4（FLAC 54MB）
        └ 取链报 code=23018 大小超限 ❌

⑤ 播放器站（转折点）
   higequ.com/player/521282703
   → quark 1e02cb3b6cfc，免提取码 ✅
   → 目录内: FLAC 53.7MB（超限）+ MP3 9.2MB（✅ 取链成功）
   → 同一页还给出了酷我封面图 URL ✅
   → 另一个 player 页 541954309 是「春晚现场版」，FLAC 仅 2.5MB
        └ 但 ffprobe 显示 codec_name=vorbis / 87kbps → 伪 FLAC ❌

⑥ 组装成品
   MP3（320K，240.000s，完整）
   + higequ 页的 1000px 封面
   + QQ 音乐官方 LRC（85 个时间轴行）
   → tag_flac.py 注入 APIC + USLT + SYLT
```

**教训**：

1. **播放器站是最优解**——免提取码 + 自带封面，且往往同一首歌有多个分享可互补
2. **论坛源要码时别死磕**，换站比研究怎么绕验证码快十倍
3. **「免转存直链」有大小上限**，MP3 版几乎必过；拿到 MP3 是合理兜底
4. **文件名带 .flac 不代表无损**，必须 `ffprobe` 看 `codec_name`
5. **网易云曲库有这首歌**（多个翻唱版）→ 可用「更多 → 匹配歌词」兜底
