# 夸克网盘免转存直链 · 接口参考

> 全部接口基于 `drive-pc.quark.cn`（网盘 API 主机，与 `pan.quark.cn` 前端区分）。
> 部分接口在 `drive-h.quark.cn` 上也有同构实现，实测两者返回一致。

## 通用约束（最重要）

### 1. 取链与下载必须同 UA、同 cookie

混用浏览器 UA 会触发 Tengine 防盗链，直链请求直接返回：

```
HTTP/2 412 Precondition Failed
Server: Tengine
Content-Disposition: attachment; filename=...
```

注意 412 响应里**带了正确的 filename**，说明 URL 本身有效，是防盗链按 UA/Cookie 判定失败。

必须使用夸克桌面客户端 UA：

```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)
quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 Electron/24.1.3.8 Safari/537.36
Channel/pckk_other_ch
```

且**取链请求与下载请求必须使用同一个 cookie jar**（`-c jar -b jar` 贯穿全流程）。

### 2. 直链有时效

`download_url` 带 `auth_key` 参数，形如：

```
auth_key = 1793288020-30855-21600-6cfbd78e7ace4ad9d7bab8312b87a4bc
```

三段含义：过期时间戳 - 相对偏移 - 签名。过期后需重新取链。大文件下载中途断流也应重取。

### 3. 文件大小校验

detail 接口返回的 `size` 与实际下载字节数必须一致。`quark_download.py` 用它做校验，不符则重试。

---

## 接口一：建立会话 + 取 stoken

**请求**

```
POST https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc
Content-Type: application/json
Referer: https://pan.quark.cn/s/<pwd_id>
Origin: https://pan.quark.cn

{"pwd_id": "<分享id>", "passcode": ""}
```

**响应**

```json
{
  "status": 200, "code": 0, "message": "ok",
  "data": {
    "stoken": "3XFytAA91k+GwKpmAI9j2hruQ9aN1DbLfc5CfN9a/mQ=",
    "title": "GAI - REAL G (2026) ALAC",
    "author": {"nick_name": "Ea*TheMusic", "member_type": "SUPER_VIP"},
    "expired_at": 4102416000000,
    "share_type": 0,
    "url_type": 1
  }
}
```

**错误码**

| code | 含义 | 处理 |
|---|---|---|
| 0 | 成功 | — |
| 41008 | 需要提取码 | 传 `passcode`，或用 `--passcode` 参数 |
| 41004 | 分享已过期 | 换源 |
| 41006 | 分享不存在 | 换源 |

**注意**：即使返回 41008，响应里仍带 `title` / `author`，可用于确认分享存在。

---

## 接口二：列目录

**请求**

```
GET https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail
    ?pr=ucpro&fr=pc&pwd_id=<id>&stoken=<stoken>
    &pdir_fid=<fid>&force=0&_page=1&_size=100
    &_sort=file_type:asc,updated_at:desc
```

**`pdir_fid` 语义**：`0` = 分享根目录。很多分享根目录下只有一个文件夹，真实文件在子目录里——需用返回的 `fid` 再查一层。

**响应关键字段**

```json
{
  "code": 0,
  "data": {
    "list": [
      {
        "fid": "025bbad2ef184a4ea5aa871ce2e16308",
        "file_name": "10. 贏-I always win.m4a",
        "size": 31595911,
        "dir": false,
        "duration": 215,
        "share_fid_token": "b146435526e229c73f7489f5d7cb3ac5",
        "format_type": "audio/mp4",
        "category": 2,
        "file_type": 1,
        "obj_category": "audio",
        "pdir_fid": "9429249cc9ca47a184496af05c3db5e4",
        "source": "ucpro-android",
        "file_source": "UCPRO-ANDROID:UPLOAD"
      }
    ]
  },
  "metadata": {"_total": 17}
}
```

**`share_fid_token` 是免转存下载的必需参数**，每次 detail 查询都会刷新，必须与本次 stoken 配套使用。

---

## 接口三：免转存直链

**请求**

```
POST https://drive-pc.quark.cn/1/clouddrive/file/download?entry=ft&fr=pc&pr=ucpro
Content-Type: application/json

{
  "fids": ["<fid>"],
  "fids_token": ["<share_fid_token>"],
  "pwd_id": "<分享id>",
  "stoken": "<stoken>"
}
```

**备用 query**（按顺序尝试，哪个返回 code=0 用哪个）：

```
entry=ft&fr=pc&pr=ucpro
pr=ucpro&fr=pc&uc_param_str=
pr=ucpro&fr=android&uc_param_str=
```

**响应**

```json
{
  "status": 200, "code": 0,
  "data": [{
    "fid": "025bbad2ef184a4ea5aa871ce2e16308",
    "file_name": "10. 贏-I always win.m4a",
    "size": 31595911,
    "download_url": "https://dl-guest-zb-u.drive.quark.cn/...?abt=5_0_&au=...&sp=100&token=...&filename=...",
    "preview_url": "https://dl-c-zb-u.drive.quark.cn/...?auth_key=...&sp=100&token=..."
  }]
}
```

`download_url` 主机形如 `dl-guest-zb-u.drive.quark.cn`（`guest` 表示免登录直链）。

**常见错误**

| code | 含义 |
|---|---|
| 0 | 成功 |
| 41020 | 参数错误（多为 stoken 与 share_fid_token 不配套，重新走一遍流程） |
| 31001 | 需要登录（用了非 sharepage 的接口路径） |

---

## 412 排查清单

直链下载返回 412 时，逐条检查：

1. 下载用的 UA 是否为夸克客户端 UA（不是浏览器 UA）
2. 取链与下载是否用了**同一个** cookie jar
3. 是否带了 `Referer: https://pan.quark.cn/s/<pwd_id>`
4. 是否带了 `Origin: https://pan.quark.cn`
5. 直链是否已过期（`auth_key` 首段时间戳 vs 当前时间）
6. 是否误用 `preview_url`（那个是缩略图/预览地址，返回 JPEG 而非音频）

---

## 相关开源实现

| 仓库 | 说明 |
|---|---|
| `huaotem-bot/gezi-quark-downloader` | C# 桌面客户端，「免转存直链」实现最完整，`QuarkClient.GetShareDownloadAsync` 揭示了取链的三种 query 兜底 |
| `Ruk1ng001/QuarkDownloader` | Go 实现，`shareDetail.go` 展示目录递归与 fid_token 用法 |
| `psylch/quark-download-skill` | Claude Code skill，脚本 `quark_search.py` 封装了 token/detail 两步 |
| `CaliCastle/seedhub-cli` | 影视站夸克链接解析 CLI |
