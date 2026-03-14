#!/bin/bash
# Ouro Loop — ROOT_CAUSE Gate (PostToolUse: Edit|Write)
#
# Tracks how many times the same file is edited in this session.
# After 3+ edits to the same file, warns the agent about potential stuck loops.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

[ -z "$FILE_PATH" ] && exit 0

# State file to track edit counts
STATE_DIR="${CWD}/.ouro"
TRACKER="${STATE_DIR}/edit-tracker.json"

# Ensure state dir exists
mkdir -p "$STATE_DIR" 2>/dev/null

# Initialize tracker if missing
[ ! -f "$TRACKER" ] && echo '{}' > "$TRACKER"

# Get relative path
REL_PATH="${FILE_PATH#"$CWD"/}"

# Increment edit count
COUNT=$(jq -r --arg f "$REL_PATH" '.[$f] // 0' "$TRACKER")
NEW_COUNT=$((COUNT + 1))
jq --arg f "$REL_PATH" --argjson c "$NEW_COUNT" '.[$f] = $c' "$TRACKER" > "${TRACKER}.tmp" \
  && mv "${TRACKER}.tmp" "$TRACKER"

# Warn at 3+, strongly warn at 5+
if [ "$NEW_COUNT" -ge 5 ]; then
  cat << EOF
{
  "additionalContext": "[ROOT_CAUSE] $REL_PATH edited $NEW_COUNT times this session. You are likely stuck in a fix-break loop. STOP. Revert to last good state and try a fundamentally different approach. Consult remediation playbook."
}
EOF
elif [ "$NEW_COUNT" -ge 3 ]; then
  cat << EOF
{
  "additionalContext": "[ROOT_CAUSE] $REL_PATH edited $NEW_COUNT times. Are you fixing the root cause, or patching symptoms? Consider stepping back and re-analyzing."
}
EOF
fi

exit 0
