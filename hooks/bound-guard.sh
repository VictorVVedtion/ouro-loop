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

# Find CLAUDE.md
CLAUDE_MD=""
for candidate in "$CWD/CLAUDE.md" "$CWD/../CLAUDE.md"; do
  [ -f "$candidate" ] && CLAUDE_MD="$candidate" && break
done

# No CLAUDE.md = no BOUND defined, allow (warn via stderr)
if [ -z "$CLAUDE_MD" ]; then
  exit 0
fi

# Extract DANGER ZONES from CLAUDE.md
# Looks for lines like: - `src/payments/` — description
DANGER_ZONES=$(sed -n '/### DANGER ZONES/,/### /p' "$CLAUDE_MD" \
  | sed -n 's/.*`\([^`]*\)`.*/\1/p' \
  | head -20)

[ -z "$DANGER_ZONES" ] && exit 0

# Make FILE_PATH relative to CWD for matching
REL_PATH="${FILE_PATH#$CWD/}"

# Check if the file matches any DANGER ZONE
while IFS= read -r zone; do
  [ -z "$zone" ] && continue
  if [[ "$REL_PATH" == $zone* || "$REL_PATH" == *"$zone"* ]]; then
    # Match found — output denial JSON
    cat << EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "DANGER ZONE: '$REL_PATH' matches bound '$zone'. This file is in a DANGER ZONE defined in CLAUDE.md. Escalate to user for approval before modifying."
  }
}
EOF
    exit 0
  fi
done <<< "$DANGER_ZONES"

# No match — allow silently
exit 0
