---
name: music-library-curator
description: 音乐库整理与无损化流水线。从夸克网盘等网盘分享批量下载专辑音频，取官方 LRC 歌词，转制 FLAC/MP3 并写入内嵌封面与内嵌歌词，输出可直接用于本地播放器与网易云云盘的成品目录。当用户要"整理音乐库""批量下载专辑""给音频加封面歌词""转 FLAC""网易云云盘没歌词/没封面""音乐文件信息补全"时触发；用「批量下歌」「专辑转 FLAC」「内嵌歌词」「嵌入封面」「补全 ID3」「网盘音乐整理」等词命中。纯播放、纯剪辑、编曲混音等不涉及标签与下载的音频任务时不自动触发。
agent_created: true
---

# 音乐库整理与无损化流水线

> **它是什么**：一条可复用的「网盘分享 → 下载 → 取官方歌词 → 转无损格式 → 内嵌封面与歌词 → 质量校验」流水线。
> **它解决什么**：绝大多数人手里的专辑文件缺封面、缺歌词、格式有损、标签残缺；网易云云盘上传后显示"无歌词"往往不是平台问题，而是文件本身没写进去。
> **它不做什么**：不绕过版权保护、不破解 DRM、不代替用户做选曲决策。

---

## 〇、先认清战场：三个反复踩的坑

这一节是整个 skill 的核心经验，**动手前务必读完**。

### 坑 1 · ffmpeg 转码默认丢掉封面

音频文件里的封面是一条**独立的 mjpeg 视频流**，不是音频流的一部分。ffmpeg 默认只映射第一条流，于是封面静默消失：

```bash
# ❌ 错：封面被丢弃
ffmpeg -i song.m4a -c:a flac out.flac

# ✅ 对：显式映射封面流
ffmpeg -i song.m4a -map 0:a -map 0:v -c:a flac -c:v copy -disposition:v attached_pic out.flac
```

**症状**：`ffprobe -show_streams` 只看到一条 audio 流，没有 video 流。
**注意**：这个坑很隐蔽——ffmpeg 不报错、退出码为 0，只是封面没了。

### 坑 2 · 封面被有损重编码

`-c:v mjpeg` 会让 ffmpeg 重新编码 JPEG。实测一张 4000×4000、5 MB 的原图会被压到 486 KB，**缩水 90%**：

```bash
# ❌ 错：重编码，封面画质永久损失
-c:v mjpeg

# ✅ 对：原样搬运
-c:v copy          # FLAC / MP4
```

MP3 的 APIC 帧需手工构建才能塞入原始 JPEG 字节（见 `scripts/tag_flac.py` 的 `build_apic()`）。

### 坑 3 · 容器字段污染

从 MP4/M4A 转码时，`major_brand` / `minor_version` / `compatible_brands` 这三个 MP4 专属字段会被原样搬进 FLAC 的 Vorbis Comment 和 MP3 的 TXXX，导致 FLAC/MP3 **谎称自己是 M4A**：

```bash
# ✅ 清除污染
-metadata major_brand= -metadata minor_version= -metadata compatible_brands=
```

---

## 一、流水线总览

```
① 探测目标分享          quark_download.py --list-only
② 批量下载原始音频      quark_download.py --auto-dir
③ 取官方 LRC 歌词       qq_lyrics.py --album <albummid> --out-dir ./lrc
④ 转 FLAC + 写标签      tag_flac.py --batch tracks.json
⑤ 质量校验              verify_library.py
```

---

## 二、步骤详解

### 步骤 1 · 探测并下载（夸克网盘）

用 `scripts/quark_download.py`。**取链与下载必须共用同一个客户端 UA 和同一个 cookie jar**，否则触发 Tengine 防盗链返回 412。

```bash
# 先看目录结构（多数分享根目录下只有一个文件夹）
python3 scripts/quark_download.py --pwd-id <分享id> --out ./src --auto-dir --list-only

# 批量下载（自带断点续传，size 校验不符会自动重试）
python3 scripts/quark_download.py --pwd-id <分享id> --out ./src --auto-dir
```

**关键参数**：
- `--auto-dir`：根目录下若只有文件夹则自动进入（**绝大多数情况需要**）
- `--dir-fid`：已知子目录 fid 时直接指定
- `--passcode`：提取码；留空表示分享无提取码（服务端返回 code=41008 表示需要）
- `--filter`：只下载文件名含指定子串的文件

**分享 id 从哪来**：`pan.quark.cn/s/<分享id>` 里 `s/` 后面那段。

### 步骤 2 · 取官方 LRC 歌词

用 `scripts/qq_lyrics.py` 走 QQ 音乐官方接口，无需登录、无需 cookie。

```bash
# 列出专辑曲目 + songmid
python3 scripts/qq_lyrics.py --album <albummid> --list

# 批量下载歌词（生成 01.lrc … 16.lrc）
python3 scripts/qq_lyrics.py --album <albummid> --out-dir ./lrc
```

**albummid 从哪来**：QQ 音乐歌曲页 URL `y.qq.com/n/ryqq/songDetail/<songmid>` → 调专辑接口
`c.y.qq.com/v8/fcg-bin/fcg_v8_album_info_cp.fcg?format=json&albummid=<albummid>` → `data.list[]` 每项含 `songmid` / `songname` / `singer[].name` / `interval`。

**纯音乐曲目返回空歌词是正常的**（Prelude / Interlude / Break 这类），不是抓取失败。

### 步骤 3 · 转制并写入标签封面歌词

用 `scripts/tag_flac.py`。批量模式需要一份 `tracks.json`：

```json
[
  {"src": "src/01. Prelude.m4a", "out": "01. Prelude.flac",
   "title": "Prelude", "artist": "GAI周延", "track": 1, "comment": "曲目 1/16"},
  {"src": "src/10. 贏-I always win.m4a", "out": "10. 赢-I always win.flac",
   "title": "赢-I always win", "artist": "GAI周延", "track": 10, "comment": "曲目 10/16",
   "lrc": "lrc/10.lrc"}
]
```

```bash
python3 scripts/tag_flac.py --batch tracks.json --batch-dir "Album [FLAC]"
```

单文件模式：

```bash
python3 scripts/tag_flac.py --in song.m4a --out song.flac \
  --title "曲名" --artist "歌手" --album "专辑" --track 10 --total 16 \
  --lrc song.lrc --comment "备注"
```

**支持的输出格式**：
- `--format flac`（默认）：Vorbis Comment 的 `LYRICS` + `UNSYNCEDLYRICS` 双键 + PICTURE 块
- `--format mp3`：ID3 的 `USLT`（时间轴全文）+ `SYLT`（结构化同步）+ `APIC`（picture type=3）

### 步骤 4 · 质量校验

```bash
python3 scripts/verify_library.py "Album [FLAC]"
python3 scripts/verify_library.py "Album [FLAC]" --lossless --src-dir ./src
```

输出六项指标：文件总数 / 含封面 / 含歌词 / 无容器污染 / 封面唯一性 / 无损验证。

**无损验证的原理**：把源文件与产出文件都解码成裸 PCM 逐字节比对，而不是比文件大小——转码后大小必然变化，PCM 一致才是真无损。

---

## 三、标签承载格式对照

选格式前先看这张表——**不同格式的歌词读取点完全不同**：

| 格式 | 封面 | 歌词 | 读取方 |
|---|---|---|---|
| **FLAC** | PICTURE 块（type 6）| `LYRICS` + `UNSYNCEDLYRICS` | foobar2000 / MusicBee / 网易云 |
| **MP3** | ID3 `APIC`（picture type=3）| `USLT` + `SYLT` + `TXXX:LYRICS` | 几乎所有播放器 |
| **M4A** | MP4 `covr` | MP4 `©lyr` | Apple 生态 / 部分播放器 |

**MP3 是兼容性最广的**：ID3 是事实标准，多数平台（含网易云）对其解析最完整。若目标是"让某个平台认出来"，优先 MP3。

---

## 四、网易云云盘机制（重要）

网易云音乐**云盘**与普通播放器是两套机制，误解会导致白折腾。

### 上传端白名单

PC / Android 端云盘上传入口只接受**音频格式**（MP3 / FLAC / WAV / M4A / APE 等）。**`.lrc` 不在白名单，文件选择器根本不接受**——这不是 bug。

### 歌词的三条来源

按优先级：

1. **内嵌标签**：上传时平台解析音频文件头，提取 ID3 的 `SYLT`/`USLT` 或等价字段
2. **同名 `.lrc` 侧车**：官方文档明确支持——歌词、封面、音频三者**文件名一致**且同目录
3. **平台曲库匹配**：按 MD5 → ID3 → 听歌识曲三级匹配

### 曲库不存在时，只有内嵌与侧车有效

若歌曲不在平台曲库（如新专辑未收录），匹配必然失败，**歌词只能来自文件自身携带的信息**。

### 侧车的正确用法（`.lrc` 上传不了时的替代路径）

`.lrc` 不该"上传"，而该在**本地**被读取：

1. 歌词、封面、音频放**同一文件夹**，**文件名完全一致**（仅后缀不同）
2. PC 端「我的音乐」→ 导入该文件夹
3. 全选拖入播放列表 → 收藏到歌单
4. 再从歌单右键「上传到云盘」——客户端在扫描本地时已把歌词读进元数据

**要点**：iOS / Mac / 网页版**没有上传入口**，只能在 PC 或 Android 操作。

### 编码要求

`.lrc` 必须 **UTF-8 无 BOM**。ANSI(GBK) 会导致乱码或整段不显示。首行时间轴不能是空行；纯音乐曲目（无时间轴）不会滚动。

---

## 五、参考文档

按需查阅：

- `references/netdisk-api.md` — 夸克网盘三个接口的完整参数、错误码表、412 排查清单
- `references/tag-formats.md` — 三种格式的标签字节级结构、ID3 帧构造代码
- `references/netease-mechanism.md` — 网易云云盘匹配机制详解与官方文档摘录

---

## 六、执行清单（动手前逐条确认）

- [ ] 已读取「三个坑」一节，`-map 0:a -map 0:v` 与 `-c:v copy` 都写对了
- [ ] 下载用客户端 UA 且取链/下载共用同一 cookie jar
- [ ] 歌词来源优先 QQ 音乐官方接口，不用第三方站点
- [ ] 确认目标格式的歌词承载方式（MP3 兼容最广 / FLAC 最规范）
- [ ] 转码时清除了 major_brand 等污染字段
- [ ] 产出后跑 `verify_library.py`，六项指标全绿
- [ ] 若目标是网易云：准备同名 `.lrc` + `.jpg` 侧车，走本地导入路径而非直接上传
