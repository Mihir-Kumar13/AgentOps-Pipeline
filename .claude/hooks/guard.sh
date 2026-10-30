#!/usr/bin/env bash
cmd=$(jq -r '.tool_input.command // empty')

# 1) Never let Terraform apply or destroy without a human prompt
if echo "$cmd" | grep -qE 'terraform +(apply|destroy).*(-auto-approve)'; then
  echo "Blocked: -auto-approve is not allowed. Show the plan and ask the user." >&2
  exit 2
fi

# 2) Scan staged changes for secrets before any commit
if echo "$cmd" | grep -qE '(^|[;&| ])git +commit'; then
  if command -v gitleaks >/dev/null 2>&1; then
    if ! { gitleaks git --staged --redact >&2 2>/dev/null || gitleaks protect --staged --redact >&2; }; then
      echo "Blocked: gitleaks found possible secrets in staged files. Remove them first." >&2
      exit 2
    fi
  fi
fi
exit 0
