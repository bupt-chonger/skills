#!/usr/bin/env python3
"""QQ 音乐官方歌词接口客户端。

接口（无需登录、无需 cookie）：
    GET https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg
        ?songmid=<mid>&format=json&nobase64=1&g_tk=5381
    Header: Referer: https://y.qq.com/

返回 JSON 的 lyric 字段即标准 LRC 文本，含 [ti:] [ar:] [al:] [by:] [offset:]
四行头 + [mm:ss.xx] 时间轴行。纯音乐曲目 lyric 为空字符串（属正常）。

取 songmid：调用 QQ 音乐专辑接口
    GET https://c.y.qq.com/v8/fcg-bin/fcg_v8_album_info_cp.fcg?format=json&albummid=<albummid>
    -> data.list[] 每项含 songmid / songname / singer[].name / interval(秒)

用法:
    python3 qq_lyrics.py --mid 001CA1Hf0zxPsY              # 单曲，输出到 stdout
    python3 qq_lyrics.py --mid 001CA1Hf0zxPsY --out song.lrc
    python3 qq_lyrics.py --album 004OEuto2OvymU --out-dir ./lrc
        # 会按曲目顺序生成 01.lrc 02.lrc ...
    python3 qq_lyrics.py --album 004OEuto2OvymU --list
"""
import argparse
import json
import os
import subprocess
import sys

LYRIC_URL = ("https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
             "?songmid={mid}&format=json&nobase64=1&g_tk=5381")
ALBUM_URL = ("https://c.y.qq.com/v8/fcg-bin/fcg_v8_album_info_cp.fcg"
             "?format=json&albummid={albummid}")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _get(url):
    r = subprocess.run(["curl", "-s", "--max-time", "30",
                        "-H", f"User-Agent: {UA}",
                        "-H", "Referer: https://y.qq.com/", url],
                       capture_output=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def fetch_lyric(mid):
    """返回 LRC 文本；无歌词返回空串。"""
    d = _get(LYRIC_URL.format(mid=mid))
    if d.get("retcode") != 0:
        raise RuntimeError(f"接口返回 retcode={d.get('retcode')} code={d.get('code')}")
    return d.get("lyric", "")


def fetch_album(albummid):
    """返回 [(songmid, songname, artist, interval_seconds), ...]"""
    d = _get(ALBUM_URL.format(albummid=albummid))
    lst = d.get("data", {}).get("list", [])
    out = []
    for s in lst:
        singers = "/".join(x.get("name", "") for x in s.get("singer", []))
        out.append((s.get("songmid", ""), s.get("songname", ""),
                    singers, s.get("interval", 0)))
    return out


def main():
    ap = argparse.ArgumentParser(description="QQ 音乐官方 LRC 歌词获取")
    ap.add_argument("--mid", help="单曲 songmid")
    ap.add_argument("--album", help="专辑 albummid")
    ap.add_argument("--out", help="单曲输出路径")
    ap.add_argument("--out-dir", help="专辑输出目录（生成 01.lrc …）")
    ap.add_argument("--list", action="store_true", help="只列出曲目不下载")
    args = ap.parse_args()

    if args.album:
        tracks = fetch_album(args.album)
        if not tracks:
            print("专辑为空或接口失败", file=sys.stderr)
            sys.exit(1)
        if args.list:
            for i, (mid, name, ar, iv) in enumerate(tracks, 1):
                print(f"  {i:>2}. {name:<32} | {ar:<16} | {iv:>4}s | {mid}")
            return
        if not args.out_dir:
            print("批量模式需 --out-dir", file=sys.stderr)
            sys.exit(1)
        os.makedirs(args.out_dir, exist_ok=True)
        for i, (mid, name, ar, iv) in enumerate(tracks, 1):
            try:
                txt = fetch_lyric(mid)
            except Exception as e:
                print(f"  [{i:>2}] {name:<32} ✗ {e}")
                continue
            p = os.path.join(args.out_dir, f"{i:02d}.lrc")
            with open(p, "w", encoding="utf-8") as f:
                f.write(txt)
            ts = sum(1 for l in txt.splitlines()
                     if l.strip().startswith("[") and l.strip()[1:3].isdigit())
            mark = "✓" if txt.strip() else "○纯音乐"
            print(f"  [{i:>2}] {name:<32} {mark} {len(txt):>5}字符 / {ts:>3}时间轴行")
        return

    if args.mid:
        txt = fetch_lyric(args.mid)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(txt)
            print(f"已写入 {args.out} ({len(txt)} 字符)")
        else:
            print(txt)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
