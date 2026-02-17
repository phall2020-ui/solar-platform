#!/bin/bash
# Script to remove the test schedule from Daily Notion Pull workflow after verification
# This removes both the test schedule AND reverts the UK 4am gate logic
# Run this after confirming 2-3 successful test runs

set -euo pipefail

WORKFLOW_FILE=".github/workflows/daily_notion_pull.yml"

echo "Removing test schedule and reverting UK 4am gate logic from $WORKFLOW_FILE..."

# Create backup
cp "$WORKFLOW_FILE" "$WORKFLOW_FILE.backup"
echo "Created backup: $WORKFLOW_FILE.backup"

# Remove the test schedule lines
sed -i '/# Test schedule - runs every 15 minutes/d' "$WORKFLOW_FILE"
sed -i "/- cron: '\*\/15 \* \* \* \*'/d" "$WORKFLOW_FILE"

echo "✓ Removed test schedule"

# Revert UK 4am gate logic to simpler version
# This is a placeholder - manual edit recommended
echo ""
echo "⚠️  MANUAL STEP REQUIRED:"
echo "Edit $WORKFLOW_FILE and simplify the UK 4am gate logic (around lines 39-56):"
echo ""
echo "Replace the current gate logic with:"
echo ""
cat <<'EOF'
      - name: UK 4am gate (DST-aware)
        if: github.event_name == 'schedule'
        id: uk4_gate
        run: |
          set -euo pipefail
          UK_HOUR="$(TZ=Europe/London date +%H)"
          if [ "${UK_HOUR}" = "04" ]; then
            echo "run=true" >> "$GITHUB_OUTPUT"
            echo "Proceeding: UK local time is 04:00."
          else
            echo "run=false" >> "$GITHUB_OUTPUT"
            echo "Skipping: UK local time is ${UK_HOUR}:00 (not 04:00)."
          fi
EOF

echo ""
echo "---"
echo ""

# Show the diff
echo "Changes made so far:"
git --no-pager diff "$WORKFLOW_FILE" || true

echo ""
echo "Next steps:"
echo "1. Manually edit the UK 4am gate logic as shown above"
echo "2. Review all changes"
echo "3. If correct, commit and push:"
echo "   git add $WORKFLOW_FILE"
echo "   git commit -m 'Remove test schedule and revert to production gate logic'"
echo "   git push"
echo "4. If incorrect, restore from backup:"
echo "   mv $WORKFLOW_FILE.backup $WORKFLOW_FILE"
