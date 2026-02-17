# Daily Notion Pull Workflow Fix - February 2026

## Problem Summary
The Daily Notion Pull workflow stopped triggering on February 17, 2026 at 03:52 and 04:37 UTC.

## Root Causes Identified

### 1. Job-Level Working Directory Issue (CRITICAL)
**Problem:** The workflow configuration had `working-directory: tools/inverter-data-juggle` set at the job level, which applied to ALL steps including the first "UK 4am gate" step that runs BEFORE the repository is checked out.

**Error:** 
```
An error occurred trying to start process '/usr/bin/bash' with working directory 
'/home/runner/work/solar-platform/solar-platform/tools/inverter-data-juggle'. 
No such file or directory
```

**Fix:** Removed job-level `defaults.run.working-directory` and applied `working-directory` only to individual steps that need it (after checkout).

### 2. Missing Dependencies
**Problem:** The workflow only installed `requests` and `pandas`, but `requirements.txt` specifies 4 dependencies: `requests`, `pandas`, `openpyxl`, and `notion-client`.

**Fix:** Changed from `pip install requests pandas` to `pip install -r requirements.txt`.

### 3. Test Schedule Gating Issue
**Problem:** The 15-minute test schedule would be blocked by the UK 4am gate logic, preventing verification of the fixes.

**Fix:** Modified the UK 4am gate logic to allow runs at 15-minute intervals (for testing) while still enforcing the 04:00 London time requirement for production runs.

## Changes Made

### File: `.github/workflows/daily_notion_pull.yml`

1. **Removed job-level working-directory:**
   ```yaml
   # BEFORE (lines 28-30)
   defaults:
     run:
       working-directory: tools/inverter-data-juggle
   
   # AFTER
   # (removed - applied at step level instead)
   ```

2. **Added working-directory to individual steps:**
   ```yaml
   - name: Install dependencies
     working-directory: tools/inverter-data-juggle
     run: |
       python -m pip install --upgrade pip
       pip install -r requirements.txt
   ```

3. **Updated UK 4am gate logic:**
   ```yaml
   UK_MINUTE="$(TZ=Europe/London date +%M)"
   if [ "$((UK_MINUTE % 15))" -eq 0 ] || [ "${UK_HOUR}" = "04" ]; then
     echo "run=true" >> "$GITHUB_OUTPUT"
     # ... logging ...
   fi
   ```

4. **Added test schedule:**
   ```yaml
   schedule:
     - cron: '0 3 * * *'
     - cron: '0 4 * * *'
     - cron: '*/15 * * * *'  # Test schedule - remove after verification
   ```

### File: `tools/inverter-data-juggle/.github/workflows/README.md` (NEW)
Added documentation explaining that workflows in subdirectories are not executed by GitHub Actions.

## Testing Instructions

### 1. Merge to Main Branch
The workflow changes must be on the `main` branch to take effect for scheduled runs:
```bash
# Create PR and merge copilot/investigate-juggle-inverter-issue to main
```

### 2. Monitor Test Schedule
After merging, the workflow should trigger within 15 minutes (at :00, :15, :30, :45).

### 3. Verify Success
Check the workflow run at: https://github.com/phall2020-ui/solar-platform/actions/workflows/daily_notion_pull.yml

Expected success indicators:
- ✅ UK 4am gate passes (logs: "Proceeding: Test run (every 15 minutes)")
- ✅ Repository checkout succeeds
- ✅ All dependencies install from requirements.txt
- ✅ Secrets validation passes
- ✅ Notion DB access verification succeeds
- ✅ Notion sync runs without errors

### 4. Remove Test Schedule
After confirming 2-3 successful test runs, remove the test schedule by editing `.github/workflows/daily_notion_pull.yml`:

```yaml
# Remove this line:
- cron: '*/15 * * * *'
```

Also update the UK 4am gate logic to remove the test bypass:

```yaml
# Simplify back to:
if [ "${UK_HOUR}" = "04" ]; then
  echo "run=true" >> "$GITHUB_OUTPUT"
  echo "Proceeding: UK local time is 04:00."
else
  echo "run=false" >> "$GITHUB_OUTPUT"
  echo "Skipping: UK local time is ${UK_HOUR}:00 (not 04:00)."
fi
```

## Verification Checklist

- [ ] PR merged to main
- [ ] First test run completed successfully (within 15 min)
- [ ] Second test run completed successfully
- [ ] Third test run completed successfully
- [ ] Regular 04:00 London run completed successfully
- [ ] Test schedule removed
- [ ] UK 4am gate logic simplified (test bypass removed)
- [ ] Final verification run at 04:00 London

## Prevention

To prevent similar issues in the future:

1. **Never set working-directory at job level** if any steps run before checkout
2. **Always test workflow changes** with workflow_dispatch before relying on scheduled triggers
3. **Use requirements.txt** for dependency installation rather than hardcoding package names
4. **Monitor workflow runs** regularly to catch failures early

## Related Files

- `.github/workflows/daily_notion_pull.yml` - Main workflow file (ACTIVE)
- `tools/inverter-data-juggle/.github/workflows/daily_pull.yml` - Nested duplicate (INACTIVE)
- `tools/inverter-data-juggle/notion_sync.py` - Sync script
- `tools/inverter-data-juggle/requirements.txt` - Dependencies
