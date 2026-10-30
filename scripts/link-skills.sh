#!/usr/bin/env bash
# 把本仓库内的 skill 挂载到 WorkBuddy 的 skills 目录。
#
# 挂载方式：skills/<name>/ 是「真实目录」，里面的条目是指向本仓库的软链。
# 为什么不直接把 skills/<name> 做成目录软链：部分 skill 扫描器用
# readdir(withFileTypes) + dirent.isDirectory() 枚举，该方法对目录软链返回
# false，会导致 skill 扫不到。真实目录 + 内部软链可以规避这一点。
#
# 用法：bash scripts/link-skills.sh [目标skills目录]
# 默认目标：~/.workbuddy/skills

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="${1:-$HOME/.workbuddy/skills}"

if [ ! -d "$SKILLS_DIR" ]; then
  echo "目标 skills 目录不存在：$SKILLS_DIR" >&2
  exit 1
fi

echo "仓库：$REPO_ROOT"
echo "挂载到：$SKILLS_DIR"
echo

linked=0
# 遍历所有分类目录（creation/ 等）下的 skill
for skill_dir in "$REPO_ROOT"/*/*/SKILL.md; do
  [ -e "$skill_dir" ] || continue
  src="$(dirname "$skill_dir")"
  name="$(basename "$src")"
  dest="$SKILLS_DIR/$name"

  # 关键安全步骤：必须先彻底移除旧条目。
  # 若 dest 仍是指向本仓库的目录软链，后续 ln 会「穿透」软链写回仓库，
  # 把仓库里的真实文件覆盖成自指软链（曾导致 ELOOP 并丢文件）。
  if [ -L "$dest" ]; then
    rm -f "$dest"
  elif [ -d "$dest" ]; then
    rm -rf "$dest"
  fi

  mkdir -p "$dest"
  for item in "$src"/*; do
    [ -e "$item" ] || continue
    ln -sn "$item" "$dest/$(basename "$item")"
  done

  echo "  ✓ $name  <-  ${src#$REPO_ROOT/}"
  linked=$((linked + 1))
done

echo
echo "已挂载 $linked 个 skill。"

# 自检：确认真实目录 + 内容可读，且仓库内没有被写坏
echo "自检："
fail=0
for skill_dir in "$REPO_ROOT"/*/*/SKILL.md; do
  [ -e "$skill_dir" ] || continue
  name="$(basename "$(dirname "$skill_dir")")"
  if [ -L "$SKILLS_DIR/$name" ] || [ ! -d "$SKILLS_DIR/$name" ]; then
    echo "  ✗ $name 不是真实目录"; fail=1
  elif ! head -1 "$SKILLS_DIR/$name/SKILL.md" >/dev/null 2>&1; then
    echo "  ✗ $name SKILL.md 不可读"; fail=1
  else
    echo "  ✓ $name"
  fi
done

stray="$(find "$REPO_ROOT"/*/ -type l 2>/dev/null | wc -l | tr -d ' ')"
if [ "$stray" != "0" ]; then
  echo "  ✗ 仓库内出现 $stray 个软链（不应存在），请检查！"; fail=1
else
  echo "  ✓ 仓库内无软链污染"
fi

exit $fail
