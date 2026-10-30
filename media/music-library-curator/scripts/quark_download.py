#!/usr/bin/env python3
"""夸克网盘「免转存直链」下载器。

原理（2026-10 实测有效）：
  1. GET  https://pan.quark.cn/s/<pwd_id>          建立会话 cookie
  2. POST https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token
       body {pwd_id, passcode}                     -> data.stoken
  3. GET  .../share/sharepage/detail?stoken=...   -> 文件列表，每项含
                                                      fid / share_fid_token / size
  4. POST .../clouddrive/file/download?entry=ft&fr=pc&pr=ucpro
       body {fids, fids_token, pwd_id, stoken}     -> data[].download_url
  5. GET  download_url                            -> 音频字节

关键约束（踩过的坑）：
  * 取链与下载必须用**同一个夸克客户端 UA**，且**共用同一个 cookie jar**。
    混用浏览器 UA 会触发 Tengine 防盗链，直接返回 412 Precondition Failed。
  * download_url 带 auth_key，有时效性，取链后应尽快下载；断流需重取。
  * passcode 为空表示该分享无提取码；需要提取码时服务端返回 code=41008。

用法:
    python3 quark_download.py --pwd-id <分享id> --out ./music
    python3 quark_download.py --pwd-id <id> --out ./m --dir-fid <子目录id>
    python3 quark_download.py --pwd-id <id> --out ./m --passcode abcd
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse

# 夸克桌面客户端 UA —— 取链与下载必须一致，否则 412
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 "
      "Electron/24.1.3.8 Safari/537.36 Channel/pckk_other_ch")

API = "https://drive-pc.quark.cn/1/clouddrive"


def curl(args, data=None, timeout=60):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout)] + args,
                       input=data, capture_output=True)
    return r.stdout


class Quark:
    def __init__(self, pwd_id, passcode="", jar="qcj.txt"):
        self.pwd_id = pwd_id
        self.passcode = passcode
        self.jar = jar
        self.ref = f"https://pan.quark.cn/s/{pwd_id}"
        self.stoken = None

    def _base(self, extra=None):
        return ["-c", self.jar, "-b", self.jar, "-H", f"User-Agent: {UA}",
                "-H", f"Referer: {self.ref}", "-H", "Origin: https://pan.quark.cn"] + (extra or [])

    def _post(self, url, body):
        raw = curl(self._base(["-X", "POST", "-H", "Content-Type: application/json",
                                "--data-raw", json.dumps(body), url]))
        try:
            return json.loads(raw)
        except Exception:
            raise RuntimeError(f"响应非 JSON: {raw[:200]!r}")

    def _get(self, url):
        raw = curl(self._base([url]))
        try:
            return json.loads(raw)
        except Exception:
            raise RuntimeError(f"响应非 JSON: {raw[:200]!r}")

    def open_share(self):
        """建立会话并取 stoken。"""
        curl(self._base(["-L", self.ref]))
        r = self._post(f"{API}/share/sharepage/token?pr=ucpro&fr=pc",
                       {"pwd_id": self.pwd_id, "passcode": self.passcode})
        if r.get("code") != 0:
            raise RuntimeError(f"取 stoken 失败 code={r.get('code')} msg={r.get('message')}")
        self.stoken = r["data"]["stoken"]
        return self.stoken

    def list_files(self, dir_fid="0", page_size=100):
        """列出目录下的文件（不含子目录）。"""
        q = urllib.parse.urlencode({
            "pr": "ucpro", "fr": "pc", "pwd_id": self.pwd_id, "stoken": self.stoken,
            "pdir_fid": dir_fid, "force": "0", "_page": "1", "_size": str(page_size),
            "_sort": "file_type:asc,updated_at:desc"})
        r = self._get(f"{API}/share/sharepage/detail?{q}")
        if r.get("code") != 0:
            raise RuntimeError(f"取文件列表失败 code={r.get('code')} msg={r.get('message')}")
        return [f for f in r["data"]["list"] if not f.get("dir")]

    def list_dirs(self, dir_fid="0"):
        """列出目录下的子目录 [(name, fid), ...]。

        许多分享的根目录下只有一个文件夹，真实文件在子目录里 ——
        此时需要用返回的 fid 作为 --dir-fid 再查一层。
        """
        q = urllib.parse.urlencode({
            "pr": "ucpro", "fr": "pc", "pwd_id": self.pwd_id, "stoken": self.stoken,
            "pdir_fid": dir_fid, "force": "0", "_page": "1", "_size": "100",
            "_sort": "file_type:asc,updated_at:desc"})
        r = self._get(f"{API}/share/sharepage/detail?{q}")
        if r.get("code") != 0:
            raise RuntimeError(f"取目录失败 code={r.get('code')} msg={r.get('message')}")
        return [(f.get("file_name", ""), f.get("fid", ""))
                for f in r["data"]["list"] if f.get("dir")]

    def direct_url(self, fid, fid_token):
        """免转存直链：需要 fileId + share_fid_token + pwd_id + stoken。"""
        r = self._post(f"{API}/file/download?entry=ft&fr=pc&pr=ucpro", {
            "fids": [fid], "fids_token": [fid_token],
            "pwd_id": self.pwd_id, "stoken": self.stoken})
        if r.get("code") != 0:
            raise RuntimeError(f"取直链失败 code={r.get('code')} msg={r.get('message')}")
        return r["data"][0]["download_url"]

    def fetch(self, url, dest, expect_size=None, retries=3):
        """下载直链到本地，校验大小；失败自动重取直链。"""
        for attempt in range(1, retries + 1):
            tmp = dest + ".part"
            curl(self._base(["-L", "-o", tmp, url]), timeout=900)
            got = os.path.getsize(tmp) if os.path.exists(tmp) else 0
            if expect_size and got != expect_size:
                print(f"    重试 {attempt}/{retries}: 大小 {got} != {expect_size}")
                if os.path.exists(tmp):
                    os.remove(tmp)
                time.sleep(1)
                continue
            if got == 0:
                print(f"    重试 {attempt}/{retries}: 下载为空")
                time.sleep(1)
                continue
            os.replace(tmp, dest)
            return got
        raise RuntimeError(f"下载失败（已重试 {retries} 次）: {dest}")


def main():
    ap = argparse.ArgumentParser(description="夸克网盘免转存直链下载器")
    ap.add_argument("--pwd-id", required=True, help="分享 id，即 pan.quark.cn/s/<pwd_id> 中的那段")
    ap.add_argument("--out", default="./download", help="输出目录")
    ap.add_argument("--dir-fid", default="0",
                    help="子目录 fid，根目录为 0；用 --auto-dir 可自动探测")
    ap.add_argument("--auto-dir", action="store_true",
                    help="根目录下若只有文件夹则自动进入（多数分享需要）")
    ap.add_argument("--passcode", default="", help="提取码，无则留空")
    ap.add_argument("--jar", default="qcj.txt", help="cookie jar 路径")
    ap.add_argument("--filter", default="", help="只下载文件名包含该子串的文件")
    ap.add_argument("--list-only", action="store_true", help="只列出文件不下载")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    q = Quark(args.pwd_id, args.passcode, args.jar)
    q.open_share()

    dir_fid = args.dir_fid
    if args.auto_dir:
        dirs = q.list_dirs(dir_fid)
        if dirs:
            dir_fid = dirs[0][1]
            print(f"自动进入子目录: {dirs[0][0]} (fid={dir_fid})")

    files = q.list_files(dir_fid)
    if args.filter:
        files = [f for f in files if args.filter in f["file_name"]]
    print(f"共 {len(files)} 个文件\n")

    if args.list_only:
        for f in files:
            print(f"  {f.get('size', 0):>12,}  {f['file_name']}")
        return

    ok, fail = 0, []
    for f in files:
        name = f["file_name"]
        dest = os.path.join(args.out, name)
        want = f.get("size")
        if os.path.exists(dest) and (not want or os.path.getsize(dest) == want):
            print(f"  ⏭  {name} (已存在)")
            ok += 1
            continue
        try:
            url = q.direct_url(f["fid"], f.get("share_fid_token", ""))
            got = q.fetch(url, dest, want)
            print(f"  ✓  {name}  ({got:,} bytes)")
            ok += 1
        except Exception as e:
            print(f"  ✗  {name}: {e}")
            fail.append(name)
        time.sleep(0.5)

    print(f"\n成功 {ok}/{len(files)}")
    if fail:
        print("失败:", fail)
        sys.exit(1)


if __name__ == "__main__":
    main()
