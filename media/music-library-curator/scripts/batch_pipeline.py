#!/usr/bin/env python3
"""一键批量处理：下载 → 取歌词 → 转 FLAC → 校验。

串联四个脚本，产出可直接使用的成品目录。

用法:
    # 1. 探测分享结构
    python3 batch_pipeline.py probe --pwd-id <分享id>

    # 2. 完整流水线
    python3 batch_pipeline.py run \
        --pwd-id <分享id> \
        --album-mid <QQ音乐 albummid> \
        --out "Album [FLAC]" \
        --title-map title_map.json

title_map.json 格式（把源文件名映射到标准曲名与序号）:
    [
      {"src": "01. Prelude.m4a",          "title": "Prelude",                     "track": 1},
      {"src": "10. 贏-I always win.m4a",  "title": "赢-I always win",             "track": 10}
    ]

省略 --title-map 时，按文件名排序自动编号（01. → 01），曲名取源文件名去掉序号前缀。
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
QLYRIC = os.path.join(HERE, "qq_lyrics.py")
QDOWN = os.path.join(HERE, "quark_download.py")
QTAG = os.path.join(HERE, "tag_flac.py")
QVERIFY = os.path.join(HERE, "verify_library.py")


def run(cmd, **kw):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, **kw)


def parse_numbered(name):
    """从 '10. 贏-I always win.m4a' 提取 (10, '贏-I always win')。"""
    stem = os.path.splitext(name)[0]
    m = re.match(r"^\s*(\d+)\s*[.．、]\s*(.+)$", stem)
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None, stem


def cmd_probe(args):
    r = run([sys.executable, QDOWN, "--pwd-id", args.pwd_id, "--out", args.work,
             "--jar", os.path.join(args.work, "qcj.txt"), "--auto-dir", "--list-only"])
    return r.returncode


def cmd_run(args):
    work = args.work
    os.makedirs(work, exist_ok=True)
    src_dir = os.path.join(work, "src")
    lrc_dir = os.path.join(work, "lrc")

    # ── 1. 下载 ────────────────────────────────────────────
    print("\n═══ 步骤 1/4 · 下载原始音频 ═══")
    r = run([sys.executable, QDOWN, "--pwd-id", args.pwd_id, "--out", src_dir,
             "--jar", os.path.join(work, "qcj.txt"), "--auto-dir"])
    if r.returncode != 0:
        print("下载有失败项，继续处理已下载文件", file=sys.stderr)

    # ── 2. 歌词 ────────────────────────────────────────────
    print("\n═══ 步骤 2/4 · 获取官方 LRC ═══")
    if args.album_mid:
        run([sys.executable, QLYRIC, "--album", args.album_mid, "--out-dir", lrc_dir])
    else:
        print("  未指定 --album-mid，跳过歌词")

    # ── 3. 转制 ────────────────────────────────────────────
    print("\n═══ 步骤 3/4 · 转 FLAC 并写入标签 ═══")
    tracks = build_spec(src_dir, lrc_dir, args)
    spec_path = os.path.join(work, "tracks.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(tracks, f, ensure_ascii=False, indent=2)
    print(f"  曲目表: {spec_path} ({len(tracks)} 首)")
    run([sys.executable, QTAG, "--batch", spec_path, "--batch-dir", args.out,
         "--artist", args.artist, "--album", args.album])

    # ── 4. 校验 ────────────────────────────────────────────
    print("\n═══ 步骤 4/4 · 质量校验 ═══")
    run([sys.executable, QVERIFY, args.out])


def build_spec(src_dir, lrc_dir, args):
    """构造 tracks.json。"""
    if args.title_map:
        raw = json.load(open(args.title_map, encoding="utf-8"))
        by_name = {os.path.basename(x["src"]): x for x in raw}
    else:
        by_name = {}

    files = sorted(f for f in os.listdir(src_dir) if f.endswith(".m4a"))
    total = len(files)
    out = []
    for f in files:
        num, stem = parse_numbered(f)
        meta = by_name.get(f, {})
        title = meta.get("title", stem)
        track = meta.get("track", num)
        item = {
            "src": os.path.join(src_dir, f),
            "out": f"{track:02d}. {title}.flac" if track else f"{title}.flac",
            "title": title,
            "artist": meta.get("artist", args.artist),
            "track": track or 0,
            "total": meta.get("total", total),
        }
        if meta.get("comment"):
            item["comment"] = meta["comment"]
        if lrc_dir:
            for cand in (f"{track:02d}.lrc" if track else None, f"{stem}.lrc"):
                if cand and os.path.exists(os.path.join(lrc_dir, cand)):
                    item["lrc"] = os.path.join(lrc_dir, cand)
                    break
        out.append(item)
    return out


def main():
    ap = argparse.ArgumentParser(description="音乐库批量处理流水线")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="探测分享目录结构")
    p.add_argument("--pwd-id", required=True)
    p.add_argument("--work", default="./_work")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("run", help="执行完整流水线")
    p.add_argument("--pwd-id", required=True)
    p.add_argument("--album-mid", help="QQ 音乐 albummid，用于取歌词")
    p.add_argument("--out", default="Album [FLAC]", help="成品输出目录")
    p.add_argument("--work", default="./_work", help="中间文件目录")
    p.add_argument("--title-map", help="曲名映射 JSON")
    p.add_argument("--artist", default="GAI周延")
    p.add_argument("--album", default="REAL G")
    p.set_defaults(func=cmd_run)

    args = ap.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
