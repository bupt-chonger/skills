# Skills

> 可复用的 **WorkBuddy Skill** 合集 —— 把一次做对的流程，固化成下次能直接跑的工具。

每个 Skill 都是一个独立目录，包含 `SKILL.md`（触发条件与工作流）+ `scripts/`（确定性脚本）+ `references/`（按需加载的深度资料）。

---

## 索引

### 媒体 · media

处理音频/视频素材的工程化流水线。

| Skill | 解决什么 | 核心能力 |
| --- | --- | --- |
| [`music-library-curator`](media/music-library-curator) | 专辑文件缺封面、缺歌词、格式有损；网易云云盘显示"无歌词" | 网盘免转存直链下载 · 官方 LRC 抓取 · FLAC/MP3 转制 · 内嵌封面与歌词 · 六项质量校验 |

**一句话选型**：要把一批专辑整理成「播放器里封面歌词俱全的无损文件」，用 `music-library-curator`。

---

## 目录结构

```
skills/
├── README.md                        ← 本文件：索引
├── media/
│   └── music-library-curator/       ← 一个 Skill 一个目录
│       ├── SKILL.md                 ← 必需：frontmatter + 工作流
│       ├── README.md               ← 人读的说明
│       ├── scripts/                 ← 可执行脚本（不必读入上下文即可运行）
│       └── references/              ← 深度资料（按需加载）
└── scripts/
    └── link-skills.sh               ← 把本仓库的 Skill 挂载到本地 skills 目录
```

**分类约定**：`media` 处理多媒体素材。其余分类按需扩展。

---

## 安装

### 方式一 · 挂载到本地（推荐）

仓库里的每个 Skill 挂载到 `~/.workbuddy/skills/`，改仓库即生效：

```bash
bash scripts/link-skills.sh
# 或指定目标目录
bash scripts/link-skills.sh /path/to/skills
```

> **为什么不用目录软链**：部分 skill 扫描器用 `readdir(withFileTypes)` +
> `dirent.isDirectory()` 枚举目录，该方法对**目录软链**返回 false，会导致 skill
> 扫不到。脚本采用「真实目录 + 内部软链」的方式规避这个坑。

### 方式二 · 单个 Skill 安装

```bash
git clone https://github.com/bupt-chonger/skills.git
cp -R skills/media/music-library-curator ~/.workbuddy/skills/
```

---

## 编写规范

新建 Skill 时遵循以下结构：

```
<category>/<skill-name>/
├── SKILL.md          # YAML frontmatter: name / description / agent_created: true
├── README.md
├── scripts/          # 确定性脚本
└── references/       # 深度参考资料
```

**frontmatter 要求**：

- `name`：与目录名一致，kebab-case
- `description`：**第三人称**描述触发条件。写清「做什么 + 何时用 + 命中词 + 何时不该用」
- `agent_created: true`：允许 `skill_manage` 后续修改或删除

**内容分工**：

| 位置 | 放什么 |
| --- | --- |
| `SKILL.md` | 核心工作流、决策要点、执行清单。控制在 5k 词内 |
| `scripts/` | 会被反复重写的代码。放进上下文不如直接执行 |
| `references/` | API 参数表、格式规范、平台机制。SKILL.md 里只留指引 |

**写作风格**：祈使句 / 不定式（"执行 X" 而非 "你应该 X"），面向 AI 消费。

---

## 依赖

- WorkBuddy（Skill 运行环境）
- `python3` 3.8+
- `ffmpeg` / `ffprobe` —— `brew install ffmpeg` / `apt install ffmpeg`

---

## 许可

MIT
