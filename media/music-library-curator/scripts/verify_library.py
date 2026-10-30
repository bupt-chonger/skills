#!/usr/bin/env python3
"""音乐库质量校验：封面 / 歌词 / 标签 / 无损性 / 污染字段。

用法:
    python3 verify_library.py "REAL G (2026) [FLAC]"
    python3 verify_library.py <dir> --lossless   # 额外逐字节比对源文件
    python3 verify_library.py <dir> --json
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

POLLUTION = ("major_brand", "minor_version", "compatible_brands")


def probe(path, entries="format"):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries,
                        "-of", "json", path], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def flac_blocks(path):
    """返回 FLAC metadata block 类型列表。"""
    d = open(path, "rb").read()
    if d[:4] != b"fLaC":
        return []
    off, out = 4, []
    while off < len(d):
        hdr = d[off]
        last, bt = hdr & 0x80, hdr & 0x7F
        sz = int.from_bytes(d[off + 1:off + 4], "big")
        out.append(bt)
        off += 4 + sz
        if last:
            break
    return out


def pcm(path):
    """解码为裸 PCM，用于无损比对。"""
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "s16le",
         "-ar", "44100", "-ac", "2", "-"], capture_output=True).stdout


def extract_cover(path, tmp="/tmp/_cover_check.jpg"):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path,
                    "-an", "-vcodec", "copy", tmp], capture_output=True)
    if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        return None
    return hashlib.md5(open(tmp, "rb").read()).hexdigest()


def check_file(path):
    fmt = probe(path).get("format", {})
    tags = fmt.get("tags", {})
    ext = path.rsplit(".", 1)[-1].lower()
    r = {
        "file": os.path.basename(path),
        "duration": float(fmt.get("duration", 0)),
        "size": int(fmt.get("size", 0)),
        "cover": False,
        "lyric_keys": [],
        "pollution": [k for k in POLLUTION if k in tags],
        "tags": sorted(tags.keys()),
    }
    if ext == "flac":
        r["cover"] = 6 in flac_blocks(path)
    else:
        d = open(path, "rb").read()
        r["cover"] = (b"APIC" in d) if ext == "mp3" else (b"covr" in d)
    for k in ("LYRICS", "UNSYNCEDLYRICS", "lyrics", "lyrics-chi", "\xa9lyr"):
        if k in tags:
            r["lyric_keys"].append(k)
    if ext == "mp3":
        d = open(path, "rb").read()
        if b"USLT" in d:
            r["lyric_keys"].append("USLT")
        if b"SYLT" in d:
            r["lyric_keys"].append("SYLT")
    return r


def main():
    ap = argparse.ArgumentParser(description="音乐库质量校验")
    ap.add_argument("dir", help="目录")
    ap.add_argument("--lossless", action="store_true", help="与源文件逐字节比对 PCM")
    ap.add_argument("--src-dir", help="源文件目录（--lossless 时必需）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.dir)
                   if f.lower().endswith((".flac", ".mp3", ".m4a", ".wav", ".aiff")))
    rows = [check_file(os.path.join(args.dir, f)) for f in files]

    covers = set()
    for f in files:
        h = extract_cover(os.path.join(args.dir, f))
        if h:
            covers.add(h)

    summary = {
        "files": len(rows),
        "with_cover": sum(1 for r in rows if r["cover"]),
        "with_lyrics": sum(1 for r in rows if r["lyric_keys"]),
        "clean": sum(1 for r in rows if not r["pollution"]),
        "total_duration": round(sum(r["duration"] for r in rows), 3),
        "total_size": sum(r["size"] for r in rows),
        "unique_covers": len(covers),
    }

    lossless = None
    if args.lossless and args.src_dir:
        srcs = {f: os.path.join(args.src_dir, f) for f in os.listdir(args.src_dir)}
        ok = tot = 0
        for r in rows:
            base = r["file"]
            cand = srcs.get(base)
            if not cand:
                for s, p in srcs.items():
                    if s.endswith(".m4a") and base.rsplit(".", 1)[0][-6:] in s:
                        cand = p
                        break
            if not cand or not os.path.exists(cand):
                continue
            tot += 1
            if pcm(cand) == pcm(os.path.join(args.dir, base)):
                ok += 1
        lossless = {"passed": ok, "total": tot}

    if args.json:
        print(json.dumps({"summary": summary, "lossless": lossless, "rows": rows},
                         ensure_ascii=False, indent=2))
        return

    print(f"{'文件':<40} {'时长':>9} {'封面':>5} {'歌词键':>26} {'污染':>6}")
    print("-" * 92)
    for r in rows:
        print(f"{r['file']:<40} {r['duration']:>9.3f} "
              f"{'✅' if r['cover'] else '❌':>5} "
              f"{','.join(r['lyric_keys']) or '—':>26} "
              f"{('❌' + ','.join(r['pollution'])) if r['pollution'] else '✅无':>6}")
    print()
    print(f"文件总数     : {summary['files']}")
    print(f"含封面       : {summary['with_cover']}/{summary['files']}")
    print(f"含歌词       : {summary['with_lyrics']}/{summary['files']}")
    print(f"无容器污染   : {summary['clean']}/{summary['files']}")
    print(f"封面唯一性   : {summary['unique_covers']} 种")
    print(f"总时长       : {summary['total_duration']}s")
    print(f"总大小       : {summary['total_size']:,} bytes")
    if lossless:
        print(f"无损验证     : {lossless['passed']}/{lossless['total']} 通过")

    bad = [r["file"] for r in rows if not r["cover"] or not r["lyric_keys"] or r["pollution"]]
    if bad:
        print("\n⚠️ 需关注:", ", ".join(bad))
        sys.exit(1)


if __name__ == "__main__":
    main()
