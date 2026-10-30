#!/usr/bin/env bash
f=$(jq -r '.tool_input.file_path // empty')
[ -z "$f" ] && exit 0
case "$f" in
  *.py) ruff format "$f" >/dev/null 2>&1; ruff check --fix "$f" >/dev/null 2>&1 ;;
  *.tf) terraform fmt "$f" >/dev/null 2>&1 ;;
esac
exit 0
