#!/bin/bash
# Ouro Loop — RECALL Gate (PreCompact)
#
# Before context compression, inject BOUND summary so constraints survive compaction.
# This prevents context decay — the #1 practical problem with long-running agents.

CWD=$(cat | jq -r '.cwd // empty')

CLAUDE_MD=""
for candidate in "$CWD/CLAUDE.md" "$CWD/../CLAUDE.md"; do
  [ -f "$candidate" ] && CLAUDE_MD="$candidate" && break
done

if [ -z "$CLAUDE_MD" ]; then
  echo "No CLAUDE.md found. BOUND not defined."
  exit 0
fi

# Extract the BOUND section (everything between ## BOUND and the next ##)
BOUND_SECTION=$(sed -n '/^## BOUND/,/^## [^B]/p' "$CLAUDE_MD" | head -50)

if [ -n "$BOUND_SECTION" ]; then
  echo "[RECALL] Context compacting. Re-injecting BOUND constraints:"
  echo "$BOUND_SECTION"
  echo ""
  echo "Remember: You are autonomous INSIDE these boundaries. Escalate if you need to cross them."
fi

exit 0
