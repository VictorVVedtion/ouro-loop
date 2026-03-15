#!/bin/bash
# Ouro Loop — BOUND Guard (PreToolUse: Edit|Write)
#
# Parses CLAUDE.md for DANGER ZONES, blocks edits to protected files.
# Agent sees the denial reason and can decide to escalate or reroute.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

# No file path = not a file edit, allow
[ -z "$FILE_PATH" ] && exit 0

# Find CLAUDE.md — recursive upward search (up to 5 levels)
CLAUDE_MD=""
SEARCH_DIR="$CWD"
for _ in 1 2 3 4 5; do
  [ -f "$SEARCH_DIR/CLAUDE.md" ] && CLAUDE_MD="$SEARCH_DIR/CLAUDE.md" && break
  PARENT=$(dirname "$SEARCH_DIR")
  [ "$PARENT" = "$SEARCH_DIR" ] && break  # reached filesystem root
  SEARCH_DIR="$PARENT"
done

# No CLAUDE.md = no BOUND defined, allow (warn via stderr)
if [ -z "$CLAUDE_MD" ]; then
  exit 0
fi

# Extract DANGER ZONES from CLAUDE.md
# Looks for lines like: - `src/payments/` — description
DANGER_ZONES=$(sed -n '/### DANGER ZONES/,/### /p' "$CLAUDE_MD" \
  | sed -n "s/.*\`\\([^\`]*\\)\`.*/\\1/p" \
  | head -20)

[ -z "$DANGER_ZONES" ] && exit 0

# Make FILE_PATH relative to CWD for matching
REL_PATH="${FILE_PATH#"$CWD"/}"

# Check if the file matches any DANGER ZONE (path-segment aware)
# Matches Python-side _file_in_danger_zone() behavior:
#   - Directory zone "auth/" matches "auth/login.py" but NOT "unauthorized.py"
#   - File zone "auth/core.py" matches exact path segments
while IFS= read -r zone; do
  [ -z "$zone" ] && continue
  if [[ "$zone" == */ ]]; then
    # Directory zone: only prefix match
    if [[ "$REL_PATH" == "$zone"* ]]; then
      echo "DANGER ZONE: '$REL_PATH' matches bound '$zone' in CLAUDE.md. You must escalate to the user before modifying this file. Do NOT retry this edit without explicit user approval." >&2
      exit 2
    fi
  else
    # File zone: exact match or path-segment match (zone appears after a /)
    if [[ "$REL_PATH" == "$zone" || "$REL_PATH" == *"/$zone" || "$REL_PATH" == *"/$zone/"* ]]; then
      echo "DANGER ZONE: '$REL_PATH' matches bound '$zone' in CLAUDE.md. You must escalate to the user before modifying this file. Do NOT retry this edit without explicit user approval." >&2
      exit 2
    fi
  fi
done <<< "$DANGER_ZONES"

# No match — allow silently
exit 0
