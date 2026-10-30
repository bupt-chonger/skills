#!/usr/bin/env python3
"""音频转 FLAC 并写入完整标签 + 内嵌封面 + 内嵌歌词。

本脚本沉淀了三个反复踩到的坑：

坑 1 · 封面丢失
    ffmpeg 默认只映射第一条流。音频文件的封面是一条**独立的 mjpeg 视频流**，
    必须显式 `-map 0:a -map 0:v`，否则 PICTURE/APIC/covr 会静默消失。
    典型症状：ffprobe 显示只有 audio 流，无 video 流。

坑 2 · 封面被有损重编码
    `-c:v mjpeg` 会让 ffmpeg 重新编码 JPEG，4000×4000 原图可被压掉 90%。
    要保留原图字节，用 `-c:v copy`（FLAC/MP4 场景）。
    MP3 的 APIC 帧需手工构建才能塞原始 JPEG 字节，见 build_apic()。

坑 3 · 容器字段污染
    从 MP4/M4A 转码时，major_brand / minor_version / compatible_brands 这些
    MP4 专属字段会被原样搬进 FLAC 的 Vorbis Comment 和 MP3 的 TXXX，
    导致 FLAC/MP3 谎称自己是 M4A。转码时显式置空即可清除。

用法:
    # 单文件
    python3 tag_flac.py --in song.m4a --out song.flac --title "赢-I always win" \
        --track 10 --total 16 --lrc song.lrc --cover cover.jpg

    # 批量（目录 -> 目录，按 tracks.json 映射）
    python3 tag_flac.py --batch tracks.json --src ./src --out "Album [FLAC]"
"""
import argparse
import json
import os
import re
import struct
import subprocess
import sys

# ── 会被清除的 MP4 容器字段 ────────────────────────────────
M4A_POLLUTION = ("major_brand", "minor_version", "compatible_brands")


# ── ID3 帧构造（MP3 用） ───────────────────────────────────
def _synchsafe(n):
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def _mkframe(fid, body):
    return fid + struct.pack(">I", len(body)) + b"\x00\x00" + body


def parse_lrc(text):
    """解析 LRC -> [(毫秒, 文本)]。"""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        stamps = re.findall(r"\[(\d+):(\d+)(?:[.:](\d+))?\]", line)
        if not stamps:
            continue
        content = re.sub(r"\[(\d+):(\d+)(?:[.:](\d+))?\]", "", line).strip()
        for st in stamps:
            mm, ss = int(st[0]), int(st[1])
            frac = st[2] or "0"
            ms = int(frac) * 10 if len(frac) == 1 else int(frac[:2].ljust(2, "0"))
            out.append((mm * 60000 + ss * 1000 + ms, content))
    return out


def build_apic(jpeg_bytes):
    """ID3 APIC 帧：picture type=3 (Cover front)，嵌入原始 JPEG 字节。"""
    body = b"\x00" + b"image/jpeg\x00" + b"\x03" + b"\x00" + jpeg_bytes
    return _mkframe(b"APIC", body)


def build_uslt(text):
    """ID3 USLT 帧：带时间轴的歌词全文（多数播放器的通用读取点）。"""
    return _mkframe(b"USLT", b"\x03" + b"chi" + b"\x00" + text.encode("utf-8") + b"\x00")


def build_sylt(pairs):
    """ID3 SYLT 帧：结构化同步歌词（每条带毫秒时间戳）。"""
    body = b"\x03" + b"chi" + b"\x02" + b"\x01" + b"\x00"
    for ms, txt in pairs:
        body += struct.pack(">I", ms) + txt.encode("utf-8") + b"\x00"
    return _mkframe(b"SYLT", body)


def build_txxx(desc, val):
    return _mkframe(b"TXXX", b"\x03" + desc.encode("utf-8") + b"\x00" +
                    val.encode("utf-8") + b"\x00")


def id3_rebuild(src, dst, extra_frames, drop_txxx=()):
    """重建 ID3 标签，保留 APIC 等非目标帧，注入 extra_frames。"""
    d = open(src, "rb").read()
    if d[:3] != b"ID3":
        raise RuntimeError(f"{src} 不是带 ID3 的文件")
    ver, flags = d[3], d[5]
    size = (d[6] << 21) | (d[7] << 14) | (d[8] << 7) | d[9]
    frames, audio = d[10:10 + size], d[10 + size:]
    out, off = b"", 0
    while off < len(frames):
        fid = frames[off:off + 4]
        if fid == b"\x00\x00\x00\x00":
            break
        fsz = ((frames[off + 4] << 24) | (frames[off + 5] << 16) |
               (frames[off + 6] << 8) | frames[off + 7])
        raw = frames[off:off + 10 + fsz]
        name = fid.decode("latin1", errors="replace")
        drop = name in ("USLT", "SYLT", "APIC")
        if name == "TXXX":
            desc = raw[10:].split(b"\x00")[0].decode("utf-8", errors="replace")
            if desc.upper() in ("LYRICS", "UNSYNCEDLYRICS") or desc in drop_txxx:
                drop = True
        if not drop:
            out += raw
        off += 10 + fsz
    for f in extra_frames:
        out += f
    tag = b"ID3" + bytes([ver, 0, flags]) + _synchsafe(len(out)) + out
    open(dst, "wb").write(tag + audio)


def flac_has_picture(path):
    d = open(path, "rb").read()
    off = 4
    while off < len(d):
        hdr = d[off]
        last, bt = hdr & 0x80, hdr & 0x7F
        sz = int.from_bytes(d[off + 1:off + 4], "big")
        if bt == 6:
            return True
        off += 4 + sz
        if last:
            break
    return False


def probe(path, entries="format"):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries,
                        "-of", "json", path], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


# ── FLAC 转制 ──────────────────────────────────────────────
def to_flac(src, dst, meta, lrc_text=None, cover_jpg=None):
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src,
           "-map", "0:a", "-map", "0:v",      # ← 必须带 0:v，否则封面丢失
           "-c:a", "flac", "-ar", "44100",
           "-c:v", "copy", "-disposition:v", "attached_pic"]
    for k, v in meta.items():
        if v is None:
            continue
        cmd += ["-metadata", f"{k}={v}"]
    for k in M4A_POLLUTION:      # ← 清除 MP4 容器字段污染
        cmd += ["-metadata", f"{k}="]
    if lrc_text:
        cmd += ["-metadata", "LYRICS=" + lrc_text,
                "-metadata", "UNSYNCEDLYRICS=" + lrc_text]
    cmd.append(dst)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError((r.stderr or "").strip()[:300])


def to_mp3(src, dst, meta, lrc_text=None, cover_jpg=None):
    """转 MP3 320K：先转码（带封面流），再手工注入 APIC/USLT/SYLT。"""
    tmp = dst + ".base.mp3"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src,
           "-map", "0:a", "-map", "0:v",
           "-c:a", "libmp3lame", "-b:a", "320k", "-ar", "44100",
           "-c:v", "mjpeg", "-disposition:v", "attached_pic",
           "-id3v2_version", "3"]
    for k, v in meta.items():
        if v is None:
            continue
        cmd += ["-metadata", f"{k}={v}"]
    for k in M4A_POLLUTION:
        cmd += ["-metadata", f"{k}="]
    cmd.append(tmp)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip()[:300])

    extra = []
    if lrc_text:
        extra += [build_txxx("LYRICS", lrc_text),
                  build_txxx("UNSYNCEDLYRICS", lrc_text),
                  build_uslt(lrc_text), build_sylt(parse_lrc(lrc_text))]
    if cover_jpg:
        extra.append(build_apic(open(cover_jpg, "rb").read()))
    try:
        id3_rebuild(tmp, dst, extra, drop_txxx=M4A_POLLUTION)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def build_meta(args, track_no=None, total=None):
    m = {"title": args.title, "artist": args.artist, "album": args.album,
         "album_artist": args.album_artist or args.artist,
         "genre": args.genre, "date": args.date}
    if track_no is not None:
        m["track"] = str(track_no)
    if total is not None:
        m["track_total"] = str(total)
    if args.comment:
        m["comment"] = args.comment
    return m


def main():
    ap = argparse.ArgumentParser(description="转 FLAC/MP3 并写入完整标签+封面+歌词")
    ap.add_argument("--in", dest="src")
    ap.add_argument("--out", dest="dst")
    ap.add_argument("--batch", help="tracks.json 路径（批量模式）")
    ap.add_argument("--batch-dir", help="批量模式输出根目录")
    ap.add_argument("--format", default="flac", choices=["flac", "mp3"])
    ap.add_argument("--title")
    ap.add_argument("--artist", default="GAI周延")
    ap.add_argument("--album", default="REAL G")
    ap.add_argument("--album-artist")
    ap.add_argument("--genre", default="Rap/Hip-Hop")
    ap.add_argument("--date", default="2026")
    ap.add_argument("--track", type=int)
    ap.add_argument("--total", type=int)
    ap.add_argument("--comment")
    ap.add_argument("--lrc", help="LRC 文件路径")
    ap.add_argument("--cover", help="封面 jpg 路径（MP3 用）")
    args = ap.parse_args()

    if args.batch:
        if not args.batch_dir:
            print("批量模式需 --batch-dir", file=sys.stderr)
            sys.exit(1)
        spec = json.load(open(args.batch, encoding="utf-8"))
        os.makedirs(args.batch_dir, exist_ok=True)
        done, fail = 0, []
        for item in spec:
            src = item.get("src")
            if not src or not os.path.exists(src):
                print(f"  ✗ {item.get('title')}: 源缺失 {src}")
                fail.append(item.get("title"))
                continue
            dst = os.path.join(args.batch_dir, item["out"])
            if os.path.exists(dst):
                print(f"  ⏭ {item['out']} (已存在)")
                done += 1
                continue
            lrc = None
            if item.get("lrc") and os.path.exists(item["lrc"]):
                lrc = open(item["lrc"], encoding="utf-8").read()
            meta = {"title": item["title"], "artist": item.get("artist", args.artist),
                    "album": item.get("album", args.album),
                    "album_artist": item.get("artist", args.artist),
                    "genre": item.get("genre", args.genre), "date": args.date,
                    "track": str(item.get("track", "")), "track_total": str(spec[0].get("total", len(spec)))}
            if item.get("comment"):
                meta["comment"] = item["comment"]
            try:
                if args.format == "flac":
                    to_flac(src, dst, meta, lrc)
                else:
                    to_mp3(src, dst, meta, lrc, item.get("cover"))
                fmt = probe(dst, "format").get("format", {})
                print(f"  ✓ {item['out']:<38} {float(fmt.get('duration', 0)):>8.3f}s "
                      f"{int(fmt.get('size', 0)):>11,}B")
                done += 1
            except Exception as e:
                print(f"  ✗ {item.get('title')}: {e}")
                fail.append(item.get("title"))
        print(f"\n完成 {done}/{len(spec)}")
        if fail:
            print("失败:", fail)
            sys.exit(1)
        return

    if not args.src or not args.dst:
        ap.print_help()
        sys.exit(1)
    lrc = open(args.lrc, encoding="utf-8").read() if args.lrc and os.path.exists(args.lrc) else None
    meta = build_meta(args, args.track, args.total)
    if args.format == "flac":
        to_flac(args.src, args.dst, meta, lrc)
    else:
        to_mp3(args.src, args.dst, meta, lrc, args.cover)
    fmt = probe(args.dst, "format").get("format", {})
    print(f"完成 {args.dst}  {float(fmt.get('duration', 0)):.3f}s  "
          f"{int(fmt.get('size', 0)):,}B  封面={flac_has_picture(args.dst) if args.format == 'flac' else 'n/a'}")


if __name__ == "__main__":
    main()
