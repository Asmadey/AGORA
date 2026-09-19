#!/usr/bin/env bash
# Поднять рабочее состояние после /clear. Ничего не меняет.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

echo "── Каталоги, ветки и незавершённые слияния ──────────────────────────"
git worktree list --porcelain | awk '/^worktree /{print $2}' | while read -r w; do
  gd=$(git -C "$w" rev-parse --git-dir 2>/dev/null) || continue
  st=""
  [ -d "$gd/rebase-merge" ] || [ -d "$gd/rebase-apply" ] && st="⚠ НЕЗАВЕРШЁННЫЙ REBASE"
  [ -f "$gd/MERGE_HEAD" ] && st="⚠ НЕЗАВЕРШЁННОЕ СЛИЯНИЕ"
  dirty=$(git -C "$w" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  [ "$dirty" != "0" ] && st="$st ($dirty несохранённых)"
  printf "  %-26s %-34s %s\n" "$(basename "$w")" "$(git -C "$w" branch --show-current 2>/dev/null)" "$st"
done

echo
echo "── Открытые PR и их проверки ────────────────────────────────────────"
gh pr list --state open --json number,title,mergeable,statusCheckRollup \
  --jq '.[] | "  #\(.number) \(.mergeable) [\([.statusCheckRollup[]?.conclusion // "ждёт"] | join(","))] \(.title[0:44])"' 2>/dev/null \
  || echo "  gh недоступен"

echo
echo "── Исполнители Codex ────────────────────────────────────────────────"
if pgrep -fl "codex exec" >/dev/null 2>&1; then
  ps -eo etime,args | grep "[c]odex exec" | sed -E 's|.*--cd ([^ ]+).*|  работает: \1|' | sort -u
else
  echo "  ни одного не запущено"
fi

echo
echo "── Заметки, которым ещё негде лежать ────────────────────────────────"
notes=".ai-memory/in-flight.md"
if [ -s "$notes" ]; then
  echo "  $notes — изменён: $(date -r "$notes" '+%d.%m %H:%M')"
  sed 's/^/    /' "$notes"
else
  echo "  пусто"
fi
