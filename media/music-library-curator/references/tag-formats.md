# 音频标签格式参考

> 三种主流容器的字节级结构与构造代码。用于手工写入 ffmpeg 不直接支持的字段。

## 速查表

| 容器 | 封面 | 歌词 | 备注 |
|---|---|---|---|
| **MP3** | `APIC` 帧 | `USLT` / `SYLT` / `TXXX:LYRICS` | ID3v2.3 最通用 |
| **FLAC** | METADATA_BLOCK type=6 | Vorbis Comment `LYRICS` / `UNSYNCEDLYRICS` | 字段名全大写 |
| **M4A** | MP4 atom `covr` | MP4 atom `©lyr` | Apple 生态原生 |

---

## MP3 · ID3v2.3

### 帧结构

```
帧头 10 字节：
  [0:4]  Frame ID   如 b'USLT' / b'APIC' / b'TXXX'
  [4:8]  Size       大端 32 位整数，不含帧头本身
  [8:10] Flags      b'\x00\x00'
帧体：可变
```

### 文本编码字节（帧体第 1 字节）

| 值 | 编码 |
|---|---|
| 0 | ISO-8859-1 |
| 1 | UTF-16 带 BOM |
| 2 | UTF-16BE 无 BOM |
| 3 | UTF-8 |

中文歌词**一律用 3（UTF-8）**。

### USLT 帧（非同步歌词）

```
[0]      编码字节 = 3
[1:4]    语言代码 = b'chi'
[4]      内容描述符，以 \x00 结尾（本例为空）
其后     歌词全文，以 \x00 结尾
```

歌词全文保留完整 LRC 文本（含 `[mm:ss.xx]` 时间轴），多数播放器据此渲染滚动。

### SYLT 帧（同步歌词）

```
[0]      编码字节 = 3
[1:4]    语言代码 = b'chi'
[4]      时间戳格式 = 2（毫秒）
[5]      内容类型 = 1（歌词）
[6]      内容描述符，以 \x00 结尾
其后     每条：[4 字节大端毫秒时间戳][文本][\x00]
```

每条独立带时间戳，是「同步歌词」的标准形态。

### APIC 帧（封面）

```
[0]      编码字节 = 0（图片数据本身与编码无关）
[1..]    MIME，以 \x00 结尾，如 b'image/jpeg\x00'
[ ]      图片类型 = 3（Cover front，正封面）
[ ]      内容描述符，以 \x00 结尾
其后     原始图片字节（这里直接塞 JPEG，不重编码）
```

**图片类型枚举**：0=Other, 1=32x32 PNG, 2=File icon, 3=Cover front, 4=Cover back。

ffmpeg 的 `-c:v mjpeg` 会**重新编码** JPEG。要保留原始字节必须手工构造 APIC。

### TXXX 帧（自定义描述符）

```
[0]      编码字节 = 3
[1..]    描述符，以 \x00 结尾，如 b'LYRICS\x00'
其后     值，以 \x00 结尾
```

常见描述符：`LYRICS`、`UNSYNCEDLYRICS`。第三方播放器（如 mp3tag）默认写 `UNSYNCEDLYRICS`。

### 同步安全整数（synchsafe）

标签总长用 7 位每字节编码：

```python
def synchsafe(n):
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])
```

---

## FLAC

### METADATA_BLOCK 结构

```
[0]     标志位：bit7 = 是否最后一个块，bit0-6 = 块类型
[1:4]   长度，24 位大端
[4..]   块数据
```

块类型：`0` STREAMINFO，`1` PADDING，`2` APPLICATION，`3` SEEKTABLE，
`4` VORBIS_COMMENT，`5` CUESHEET，`6` PICTURE。

**块顺序**：`STREAMINFO` 必须第一且仅一个；`PICTURE` 可多个（不同类型）。

### PICTURE 块（type 6）

```
[0:4]    图片类型（3 = Cover front）
[4:8]    MIME 长度
[8..]    MIME 字符串
         描述符长度 + 描述符（UTF-8）
[4]      宽（像素）
[4]      高
[4]      颜色深度
[4]      索引色数（0 = 非调色板）
[4]      图片数据长度
         图片数据
```

ffmpeg 的 `-c:v copy` 会把整条视频流原样搬进 PICTURE 块，无需手工构造。

### VORBIS_COMMENT 块（type 4）

```
[4]      厂商字符串长度 + 厂商字符串
[4]      条目数量
每条     [4 字节长度][UTF-8 的 KEY=VALUE]
```

**键名全大写**：`TITLE` / `ARTIST` / `ALBUM` / `ALBUMARTIST` / `TRACKNUMBER` /
`TRACKTOTAL` / `GENRE` / `DATE` / `COMMENT` / `LYRICS` / `UNSYNCEDLYRICS` / `COPYRIGHT`。

多值键可重复出现，`LYRICS` 与 `UNSYNCEDLYRICS` 同时写是刻意的双写策略——覆盖不同播放器的读取偏好。

---

## M4A / MP4

### ilst 结构

```
moov
 └ udta
    └ meta
       └ ilst
          ├ ©nam  标题
          ├ ©ART  艺术家
          ├ aART  专辑艺术家
          ├ ©alb  专辑
          ├ ©day  日期
          ├ ©gen  流派
          ├ ©cmt  注释
          ├ ©too  编码器
          ├ ©lyr  歌词
          ├ covr   封面
          └ trkn   音轨号
```

每个 item 内含一个 `data` box：

```
[0:4]   size
[4:8]   'data'
[8:12]  type flags（1 = UTF-8 文本）
[12:16] locale（0）
[16..]  值
```

### 关键 atom 名

| atom | 含义 |
|---|---|
| `©nam` | Title |
| `©ART` | Artist |
| `aART` | Album Artist |
| `©alb` | Album |
| `©day` | Date |
| `©gen` | Genre |
| `©cmt` | Comment |
| `©lyr` | Lyrics（歌词） |
| `covr` | Cover Art（封面） |
| `trkn` | Track Number |
| `disk` | Disc Number |

`covr` 的 data type flags：13 = JPEG，14 = PNG。

### MP4 容器独有字段（转码时需清除）

`major_brand` / `minor_version` / `compatible_brands` 是 MP4 专属，出现在
`ftyp` box 里。ffmpeg 转码时会把它们搬进 FLAC 的 Vorbis Comment 和 MP3 的
TXXX —— 导致 FLAC/MP3 谎称自己是 M4A。转码时显式置空：

```bash
-metadata major_brand= -metadata minor_version= -metadata compatible_brands=
```

---

## ffmpeg 元数据对照

| 通用名 | MP3 | FLAC | MP4 |
|---|---|---|---|
| title | TIT2 | TITLE | ©nam |
| artist | TPE1 | ARTIST | ©ART |
| album | TALB | ALBUM | ©alb |
| album_artist | TPE2 | ALBUMARTIST | aART |
| genre | TCON | GENRE | ©gen |
| date | TYER | DATE | ©day |
| track | TRCK | TRACKNUMBER | trkn |
| track_total | — | TRACKTOTAL | — |
| comment | COMM | COMMENT | ©cmt |
| copyright | TCOP | COPYRIGHT | cpyr |
| lyrics | USLT / TXXX | LYRICS | ©lyr |

---

## 常用命令速查

```bash
# 查看全部标签（JSON）
ffprobe -v error -show_entries format_tags -of json file.flac

# 查看流（确认封面流是否存在）
ffprobe -v error -show_entries stream=codec_type,codec_name,disposition=attached_pic -of default=nw=1 file.flac

# 提取封面
ffmpeg -i file.flac -an -vcodec copy cover.jpg

# 无损验证：解码成裸 PCM 逐字节比对（而非比文件大小）
ffmpeg -i a.m4a -f s16le -ar 44100 -ac 2 - > a.raw
ffmpeg -i b.flac -f s16le -ar 44100 -ac 2 - > b.raw
cmp a.raw b.raw
```

**为什么必须比 PCM**：转码后文件大小必然变化（FLAC 与 ALAC 压缩算法不同），
只有解码后的采样值一致才是真无损。
