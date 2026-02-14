#!/usr/bin/env bash
# =============================================================================
# Post-Launch Health Check Script
# Usage: ./scripts/health_check.sh
# Designed to run via cron every 5 minutes:
#   */5 * * * * /path/to/scripts/health_check.sh >> /var/log/solar_health.log 2>&1
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HEALTH_URL="http://localhost:8501/_stcore/health"
DB_PATH="${UNIFIED_DB_PATH:-databases/plant_registry.duckdb}"
LOG_DIR="$PROJECT_DIR/logs"
DISK_WARN_PERCENT=85
MEM_WARN_MB=2048
LOG_WARN_MB=500

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
EXIT_CODE=0

# ── Output helpers ───────────────────────────────────────────────────────────
pass() { echo "  ✅ PASS  | $*"; }
warn() { echo "  ⚠️  WARN  | $*"; }
fail() { echo "  ❌ FAIL  | $*"; EXIT_CODE=1; }

echo "═══════════════════════════════════════════════════════════"
echo "  Health Check — $TIMESTAMP"
echo "═══════════════════════════════════════════════════════════"

# ── 1. App health endpoint ───────────────────────────────────────────────────
echo ""
echo "── Application ──"
if curl -sf --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
    pass "Streamlit health endpoint responding"
else
    fail "Streamlit health endpoint NOT responding ($HEALTH_URL)"
fi

# ── 2. Database file ────────────────────────────────────────────────────────
echo ""
echo "── Database ──"
DB_FILE="$PROJECT_DIR/$DB_PATH"
if [ -f "$DB_FILE" ]; then
    db_size=$(du -sh "$DB_FILE" | awk '{print $1}')
    db_mtime=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$DB_FILE" 2>/dev/null || stat -c "%y" "$DB_FILE" 2>/dev/null | cut -d. -f1)
    pass "Database exists ($db_size, modified: $db_mtime)"

    # Check if file is readable
    if [ -r "$DB_FILE" ]; then
        pass "Database file is readable"
    else
        fail "Database file is NOT readable"
    fi
else
    fail "Database file not found: $DB_FILE"
fi

# ── 3. Data freshness (optional — requires duckdb CLI or Python) ────────────
if command -v python3 >/dev/null 2>&1 && [ -f "$DB_FILE" ]; then
    freshness=$(python3 -c "
import duckdb, sys
from datetime import datetime, timedelta
try:
    con = duckdb.connect('$DB_FILE', read_only=True)
    tables = [r[0] for r in con.execute(\"SHOW TABLES\").fetchall()]
    if 'inverter_data' in tables:
        row = con.execute('SELECT MAX(timestamp) FROM inverter_data').fetchone()
        if row and row[0]:
            latest = row[0]
            if hasattr(latest, 'date'):
                age_days = (datetime.now() - latest).days
                print(f'OK|Latest data: {latest.strftime(\"%Y-%m-%d %H:%M\")} ({age_days}d ago)')
            else:
                print(f'OK|Latest data: {latest}')
        else:
            print('WARN|No data rows found in inverter_data')
    else:
        print('SKIP|inverter_data table not found')
    con.close()
except Exception as e:
    print(f'WARN|Could not query freshness: {e}')
" 2>/dev/null || echo "SKIP|DuckDB query failed")

    status=$(echo "$freshness" | cut -d'|' -f1)
    message=$(echo "$freshness" | cut -d'|' -f2-)
    case "$status" in
        OK)   pass "$message" ;;
        WARN) warn "$message" ;;
        *)    pass "Data freshness check skipped: $message" ;;
    esac
fi

# ── 4. Disk space ───────────────────────────────────────────────────────────
echo ""
echo "── Infrastructure ──"
disk_percent=$(df -h "$PROJECT_DIR" | awk 'NR==2 {gsub(/%/,""); print $5}')
disk_avail=$(df -h "$PROJECT_DIR" | awk 'NR==2 {print $4}')
if [ "$disk_percent" -ge "$DISK_WARN_PERCENT" ]; then
    warn "Disk usage: ${disk_percent}% (${disk_avail} free) — threshold: ${DISK_WARN_PERCENT}%"
else
    pass "Disk usage: ${disk_percent}% (${disk_avail} free)"
fi

# ── 5. Memory usage ─────────────────────────────────────────────────────────
if [[ "$(uname)" == "Darwin" ]]; then
    # macOS: use vm_stat
    pages_free=$(vm_stat | awk '/Pages free/ {gsub(/\./,""); print $3}')
    pages_inactive=$(vm_stat | awk '/Pages inactive/ {gsub(/\./,""); print $3}')
    mem_free_mb=$(( (pages_free + pages_inactive) * 4096 / 1024 / 1024 ))
    mem_total_mb=$(( $(sysctl -n hw.memsize) / 1024 / 1024 ))
    mem_used_mb=$((mem_total_mb - mem_free_mb))
else
    # Linux: use /proc/meminfo
    mem_total_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
    mem_avail_mb=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
    mem_used_mb=$((mem_total_mb - mem_avail_mb))
fi

if [ "$mem_used_mb" -ge "$MEM_WARN_MB" ]; then
    warn "Memory usage: ${mem_used_mb}MB used — threshold: ${MEM_WARN_MB}MB"
else
    pass "Memory usage: ${mem_used_mb}MB used"
fi

# ── 6. Log file size ────────────────────────────────────────────────────────
echo ""
echo "── Logs ──"
if [ -d "$LOG_DIR" ]; then
    total_log_size_kb=$(du -sk "$LOG_DIR" 2>/dev/null | awk '{print $1}')
    total_log_size_mb=$((total_log_size_kb / 1024))
    if [ "$total_log_size_mb" -ge "$LOG_WARN_MB" ]; then
        warn "Log directory size: ${total_log_size_mb}MB — threshold: ${LOG_WARN_MB}MB"
    else
        pass "Log directory size: ${total_log_size_mb}MB"
    fi
else
    pass "No log directory found (using stdout/Docker logs)"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "───────────────────────────────────────────────────────────"
if [ "$EXIT_CODE" -eq 0 ]; then
    echo "  ✅ All checks passed"
else
    echo "  ❌ One or more checks FAILED"
fi
echo "═══════════════════════════════════════════════════════════"
echo ""

exit $EXIT_CODE
