#!/usr/bin/env bash
# agent_view.sh —— 多 agent 工作看板写入 / 渲染工具。
#
# 每个 agent（含主会话）在开工、阶段切换、受阻和收工时调用本脚本，
# 脚本用 flock 串行化写入，并重新渲染仓库根目录的 view.md。
# 用户只看 view.md 就能知道每个 agent 在干什么、为什么干、下一步干什么。
#
# 用法：
#   tools/agent_view.sh start  --agent <名字> --doing "..." --why "..." --next "..."
#   tools/agent_view.sh update --agent <名字> --doing "..." --why "..." --next "..."
#   tools/agent_view.sh block  --agent <名字> --doing "..." --why "..." --next "..."
#   tools/agent_view.sh done   --agent <名字> --doing "..." --why "..." --next "..."
#   tools/agent_view.sh show   [--agent <名字>]      # 打印当前状态
#   tools/agent_view.sh clear  [--agent <名字>|--all-done]  # 清理已完成条目
#
# 说明：
#   * --doing 在做什么 / --why 为了解决什么问题 / --next 下一步可能干什么
#   * update 时省略的字段沿用上一次的值（只更新变化的部分）。
#   * --status 可覆盖子命令给出的默认状态文字。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$REPO_ROOT/.agent_view"
HISTORY="$STATE_DIR/history.log"
LOCK="$STATE_DIR/.lock"
VIEW="$REPO_ROOT/view.md"
HISTORY_TAIL=40

usage() { sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

slug() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]\+/-/g; s/^-//; s/-$//' | cut -c1-64
}

esc() {  # 换行/制表符转义成单行存储
  printf '%s' "$1" | sed ':a;N;$!ba;s/\t/ /g; s/\n/\\n/g'
}

unesc() { printf '%s' "$1" | sed 's/\\n/\n/g'; }

get_field() {  # get_field <state_file> <KEY>
  [ -f "$1" ] || return 0
  sed -n "s/^$2\t//p" "$1" | head -1
}

now_stamp() { date '+%Y-%m-%d %H:%M:%S %Z'; }

render_view() {
  local tmp="$STATE_DIR/.view.tmp"
  {
    echo "# Agent 工作看板"
    echo
    echo "> 本文件由 \`tools/agent_view.sh\` 自动生成，**请勿手工编辑**（改动会被下一次刷新覆盖）。"
    echo "> 最后刷新：$(now_stamp)"
    echo
    echo "## 当前状态"
    echo

    local files=("$STATE_DIR"/*.state)
    if [ ! -e "${files[0]:-}" ]; then
      echo "_当前没有 agent 在登记工作。_"
      echo
    else
      echo "| Agent | 状态 | 在做什么 | 更新时间 |"
      echo "| --- | --- | --- | --- |"
      local f
      for f in $(ls -t "$STATE_DIR"/*.state 2>/dev/null); do
        local a s d u
        a="$(get_field "$f" AGENT)"; s="$(get_field "$f" STATUS)"
        d="$(get_field "$f" DOING)"; u="$(get_field "$f" UPDATED)"
        printf '| %s | %s | %s | %s |\n' "$a" "$s" "${d//|/\\|}" "$u"
      done
      echo
      echo "## 详情"
      echo
      for f in $(ls -t "$STATE_DIR"/*.state 2>/dev/null); do
        local a s d w n u p
        a="$(get_field "$f" AGENT)"; s="$(get_field "$f" STATUS)"
        d="$(get_field "$f" DOING)"; w="$(get_field "$f" WHY)"
        n="$(get_field "$f" NEXT)"; u="$(get_field "$f" UPDATED)"
        p="$(get_field "$f" STARTED)"
        echo "### $a — $s"
        echo
        echo "- **在做什么**：$(unesc "${d:-（未填写）}")"
        echo "- **为了解决什么问题**：$(unesc "${w:-（未填写）}")"
        echo "- **下一步可能干什么**：$(unesc "${n:-（未填写）}")"
        echo "- 开始于 ${p:-?}，更新于 ${u:-?}"
        echo
      done
    fi

    echo "## 最近 $HISTORY_TAIL 条动态"
    echo
    if [ -s "$HISTORY" ]; then
      tail -n "$HISTORY_TAIL" "$HISTORY" | tac | while IFS=$'\t' read -r t a s d; do
        printf -- '- `%s` **%s** [%s] %s\n' "$t" "$a" "$s" "$(unesc "$d")"
      done
    else
      echo "_暂无。_"
    fi
  } > "$tmp"
  mv "$tmp" "$VIEW"
}

write_entry() {
  local agent="$1" status="$2" doing="$3" why="$4" next="$5"
  local sl file stamp started
  sl="$(slug "$agent")"
  [ -n "$sl" ] || { echo "agent_view: --agent 名字非法" >&2; exit 2; }
  file="$STATE_DIR/$sl.state"
  stamp="$(now_stamp)"

  # 省略的字段沿用上一次的值
  [ -n "$doing" ] || doing="$(get_field "$file" DOING)"
  [ -n "$why"   ] || why="$(get_field "$file" WHY)"
  [ -n "$next"  ] || next="$(get_field "$file" NEXT)"
  started="$(get_field "$file" STARTED)"; [ -n "$started" ] || started="$stamp"

  printf 'AGENT\t%s\nSTATUS\t%s\nDOING\t%s\nWHY\t%s\nNEXT\t%s\nSTARTED\t%s\nUPDATED\t%s\n' \
    "$agent" "$status" "$(esc "$doing")" "$(esc "$why")" "$(esc "$next")" "$started" "$stamp" > "$file"

  printf '%s\t%s\t%s\t%s\n' "$stamp" "$agent" "$status" "$(esc "$doing")" >> "$HISTORY"
  render_view
}

mkdir -p "$STATE_DIR"
touch "$HISTORY" "$LOCK"

cmd="${1:-}"; shift || true
agent=""; doing=""; why=""; next=""; status=""; all_done=0
while [ $# -gt 0 ]; do
  case "$1" in
    --agent)  agent="${2:-}"; shift 2 ;;
    --doing|--task) doing="${2:-}"; shift 2 ;;
    --why)    why="${2:-}"; shift 2 ;;
    --next)   next="${2:-}"; shift 2 ;;
    --status) status="${2:-}"; shift 2 ;;
    --all-done) all_done=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "agent_view: 未知参数 $1" >&2; exit 2 ;;
  esac
done

case "$cmd" in
  start|update|block|done)
    [ -n "$agent" ] || { echo "agent_view: 必须提供 --agent" >&2; exit 2; }
    if [ -z "$status" ]; then
      case "$cmd" in
        start)  status="进行中" ;;
        update) status="进行中" ;;
        block)  status="阻塞"   ;;
        done)   status="完成"   ;;
      esac
    fi
    exec 9>"$LOCK"; flock 9
    write_entry "$agent" "$status" "$doing" "$why" "$next"
    exec 9>&-
    echo "view.md 已更新：[$status] $agent"
    ;;
  show)
    if [ -n "$agent" ]; then
      f="$STATE_DIR/$(slug "$agent").state"
      [ -f "$f" ] && cat "$f" || echo "（无记录）"
    else
      [ -f "$VIEW" ] && cat "$VIEW" || echo "（view.md 尚未生成）"
    fi
    ;;
  clear)
    exec 9>"$LOCK"; flock 9
    if [ -n "$agent" ]; then
      rm -f "$STATE_DIR/$(slug "$agent").state"
    elif [ "$all_done" = 1 ]; then
      for f in "$STATE_DIR"/*.state; do
        [ -e "$f" ] || continue
        [ "$(get_field "$f" STATUS)" = "完成" ] && rm -f "$f"
      done
    else
      echo "agent_view: clear 需要 --agent <名字> 或 --all-done" >&2; exit 2
    fi
    render_view
    exec 9>&-
    echo "已清理，view.md 重新生成"
    ;;
  ""|-h|--help|help) usage ;;
  *) echo "agent_view: 未知子命令 $cmd" >&2; usage >&2; exit 2 ;;
esac
