#!/bin/bash
# Ouro Loop — RELEVANCE Gate (PreToolUse: Edit|Write)
#
# Tracks which files have been edited. If a file is outside the initial scope
# (first 3 edited files define the scope), warns about potential drift.
# Does NOT block — just warns. The agent decides.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

[ -z "$FILE_PATH" ] && exit 0

STATE_DIR="${CWD}/.ouro"
SCOPE_FILE="${STATE_DIR}/scope-files.txt"
mkdir -p "$STATE_DIR" 2>/dev/null

REL_PATH="${FILE_PATH#$CWD/}"

# Extract directory of the file (scope = directories, not individual files)
FILE_DIR=$(dirname "$REL_PATH")

# If scope file doesn't exist, we're in early phase — just record
if [ ! -f "$SCOPE_FILE" ]; then
  echo "$FILE_DIR" > "$SCOPE_FILE"
  exit 0
fi

# Add to known directories
if ! grep -qxF "$FILE_DIR" "$SCOPE_FILE" 2>/dev/null; then
  SCOPE_SIZE=$(wc -l < "$SCOPE_FILE" | tr -d ' ')
  
  if [ "$SCOPE_SIZE" -ge 5 ]; then
    # More than 5 different directories touched — possible drift
    cat << EOF
{
  "additionalContext": "[RELEVANCE] Editing file in new directory '$FILE_DIR' ($((SCOPE_SIZE + 1)) directories touched so far). Are you still working on the original task, or have you drifted to a tangent?"
}
EOF
  fi
  
  echo "$FILE_DIR" >> "$SCOPE_FILE"
fi

exit 0
