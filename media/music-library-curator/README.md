# music-library-curator

> 音乐库整理与无损化流水线：**网盘分享 → 下载 → 官方歌词 → 转 FLAC/MP3 → 内嵌封面与歌词 → 质量校验**。

针对一个具体而普遍的痛点：手里的专辑文件**缺封面、缺歌词、格式有损、标签残缺**；
传到网易云云盘后显示"无歌词"，往往不是平台的问题，而是**文件本身没写进去**。

---

## 它解决什么

| 症状 | 真实原因 |
|---|---|
| ffmpeg 转码后封面消失 | 默认只映射音频流，封面是独立的 mjpeg 视频流 |
| 封面画质变差、体积缩水 90% | `-c:v mjpeg` 重编码了原图 |
| FLAC/MP3 里出现 `major_brand=M4A` | MP4 容器字段污染 |
| 网易云云盘无歌词 | 文件无内嵌歌词 + 平台曲库无此曲 + 侧车走错路径 |
| 上传 `.lrc` 被拒 | 云盘上传白名单只含音频格式，`.lrc` 本不该上传 |

---

## 快速开始

```bash
# 1. 探测分享结构
python3 scripts/batch_pipeline.py probe --pwd-id <分享id>

# 2. 一键完整流水线
python3 scripts/batch_pipeline.py run \
    --pwd-id <分享id> \
    --album-mid <QQ音乐 albummid> \
    --out "REAL G (2026) [FLAC]" \
    --title-map title_map.json
```

或分步执行：

```bash
# 下载（自带断点续传 + 大小校验 + 断流重试）
python3 scripts/quark_download.py --pwd-id <id> --out ./src --auto-dir

# 取官方 LRC（QQ 音乐接口，无需登录）
python3 scripts/qq_lyrics.py --album <albummid> --out-dir ./lrc

# 转 FLAC 并写入封面 + 歌词 + 完整标签
python3 scripts/tag_flac.py --batch tracks.json --batch-dir "Album [FLAC]"

# 质量校验
python3 scripts/verify_library.py "Album [FLAC]" --lossless --src-dir ./src
```

---

## 脚本

| 脚本 | 作用 |
|---|---|
| `scripts/batch_pipeline.py` | 一键串联全流程 |
| `scripts/quark_download.py` | 夸克网盘免转存直链下载（取链 + 下载 + 校验 + 重试） |
| `scripts/qq_lyrics.py` | QQ 音乐官方 LRC 获取（单曲 / 批量专辑） |
| `scripts/tag_flac.py` | 转 FLAC/MP3 + 写标签 + 内嵌封面 + 内嵌歌词 |
| `scripts/verify_library.py` | 六项质量指标 + 无损逐字节验证 |

---

## 参考文档

| 文档 | 内容 |
|---|---|
| `references/netdisk-api.md` | 夸克三个接口的完整参数、错误码表、412 排查清单 |
| `references/tag-formats.md` | 三种容器的字节级标签结构、ID3 帧构造代码 |
| `references/netease-mechanism.md` | 网易云云盘匹配机制详解与官方文档摘录 |

---

## 核心经验（三个必知坑）

**1. 封面是独立流，必须显式映射**

```bash
ffmpeg -i song.m4a -map 0:a -map 0:v -c:a flac -c:v copy -disposition:v attached_pic out.flac
```

**2. 封面别重编码**

`-c:v mjpeg` 会把 4000×4000 的 5 MB 原图压到 486 KB。用 `-c:v copy`。

**3. 清除容器字段污染**

```bash
-metadata major_brand= -metadata minor_version= -metadata compatible_brands=
```

---

## 网易云云盘使用提示

`.lrc` **无法上传**是设计如此——云盘上传白名单只含音频格式。

正确路径是让客户端在**本地扫描**时读到歌词：

1. 歌词、封面、音频放同一文件夹，**文件名完全一致**
2. PC 端「我的音乐」→ 导入该文件夹
3. 全选拖入播放列表 → 收藏到歌单
4. 从歌单右键「上传到云盘」

客户端扫描时已把歌词读进元数据，上传时随音频一起走。

详见 `references/netease-mechanism.md`。

---

## 依赖

- Python 3.8+
- `ffmpeg` / `ffprobe`（含 libmp3lame、flac 编码器）
- 网络访问 `drive-pc.quark.cn`、`c.y.qq.com`

```bash
# macOS
brew install ffmpeg
# Debian/Ubuntu
sudo apt install ffmpeg
```

---

## 许可

MIT
