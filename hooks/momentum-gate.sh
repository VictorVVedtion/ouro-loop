#!/bin/bash
# Ouro Loop — MOMENTUM Gate (PostToolUse: Edit|Write|Read)
#
# Tracks the read/write ratio of tool calls. If the agent has been reading
# far more than writing (ratio > 3:1 in last 10 actions), it may be stuck.
# Warns the agent to make progress — write something, even if imperfect.

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

[ -z "$TOOL_NAME" ] && exit 0

# State file to track read/write counts
STATE_DIR="${CWD}/.ouro"
TRACKER="${STATE_DIR}/momentum-tracker.json"

# Ensure state dir exists
mkdir -p "$STATE_DIR" 2>/dev/null

# Initialize tracker if missing
if [ ! -f "$TRACKER" ]; then
  echo '{"reads": 0, "writes": 0, "actions": 0}' > "$TRACKER"
fi

# Classify the tool action
IS_WRITE=false
IS_READ=false

case "$TOOL_NAME" in
  Edit|Write|NotebookEdit)
    IS_WRITE=true
    ;;
  Read|Glob|Grep)
    IS_READ=true
    ;;
esac

# Update counts
if [ "$IS_READ" = true ]; then
  jq '.reads += 1 | .actions += 1' "$TRACKER" > "${TRACKER}.tmp" \
    && mv "${TRACKER}.tmp" "$TRACKER"
elif [ "$IS_WRITE" = true ]; then
  jq '.writes += 1 | .actions += 1' "$TRACKER" > "${TRACKER}.tmp" \
    && mv "${TRACKER}.tmp" "$TRACKER"
else
  # Other tools — increment actions only
  jq '.actions += 1' "$TRACKER" > "${TRACKER}.tmp" \
    && mv "${TRACKER}.tmp" "$TRACKER"
fi

# Check ratio every 10 actions
ACTIONS=$(jq -r '.actions // 0' "$TRACKER")
READS=$(jq -r '.reads // 0' "$TRACKER")
WRITES=$(jq -r '.writes // 0' "$TRACKER")

if [ "$ACTIONS" -ge 10 ]; then
  # Reset counter for next window
  jq '.reads = 0 | .writes = 0 | .actions = 0' "$TRACKER" > "${TRACKER}.tmp" \
    && mv "${TRACKER}.tmp" "$TRACKER"

  if [ "$WRITES" -eq 0 ] && [ "$READS" -gt 3 ]; then
    cat << EOF
{
  "additionalContext": "[MOMENTUM] ${READS} reads, ${WRITES} writes in last 10 actions. You may be stuck in analysis paralysis. Stop reading and write something — a test, a stub, a prototype. Iterate."
}
EOF
  elif [ "$WRITES" -gt 0 ] && [ "$READS" -ge "$((WRITES * 3))" ]; then
    cat << EOF
{
  "additionalContext": "[MOMENTUM] Read/write ratio is ${READS}:${WRITES} (above 3:1 threshold). Consider making forward progress — write code, don't just read."
}
EOF
  fi
fi

exit 0
