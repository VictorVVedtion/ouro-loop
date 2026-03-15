#!/bin/bash
# Ouro Loop — RECALL Gate (PreCompact)
#
# Before context compression, inject BOUND summary so constraints survive compaction.
# This prevents context decay — the #1 practical problem with long-running agents.

CWD=$(cat | jq -r '.cwd // empty')

CLAUDE_MD=""
SEARCH_DIR="$CWD"
for _ in 1 2 3 4 5; do
  [ -f "$SEARCH_DIR/CLAUDE.md" ] && CLAUDE_MD="$SEARCH_DIR/CLAUDE.md" && break
  PARENT=$(dirname "$SEARCH_DIR")
  [ "$PARENT" = "$SEARCH_DIR" ] && break
  SEARCH_DIR="$PARENT"
done

if [ -z "$CLAUDE_MD" ]; then
  echo "No CLAUDE.md found. BOUND not defined."
  exit 0
fi

# Extract the BOUND section (everything between ## BOUND and the next ##)
BOUND_SECTION=$(sed -n '/^## BOUND/,/^## [^B]/p' "$CLAUDE_MD")

if [ -n "$BOUND_SECTION" ]; then
  echo "[RECALL] Context compacting. Re-injecting BOUND constraints:"
  echo "$BOUND_SECTION"
  echo ""
  echo "Remember: You are autonomous INSIDE these boundaries. Escalate if you need to cross them."
fi

exit 0
