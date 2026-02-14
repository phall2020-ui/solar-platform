#!/usr/bin/env bash
# =============================================================================
# Database Backup Script
# Usage: ./scripts/backup_db.sh
# Keeps last 7 daily backups, prunes older ones.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_ROOT="$PROJECT_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"
DB_PATH="${UNIFIED_DB_PATH:-databases/plant_registry.duckdb}"
MAX_BACKUPS=7

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { log "❌ ERROR: $*" >&2; }
ok()  { log "✅ $*"; }

# ── Backup ───────────────────────────────────────────────────────────────────
backup() {
    local db_file="$PROJECT_DIR/$DB_PATH"

    if [ ! -f "$db_file" ]; then
        err "Database file not found: $db_file"
        exit 1
    fi

    mkdir -p "$BACKUP_DIR"

    log "Backing up: $db_file"
    log "       To:  $BACKUP_DIR/"

    cp "$db_file" "$BACKUP_DIR/"

    # Also copy any WAL file if present
    if [ -f "${db_file}.wal" ]; then
        cp "${db_file}.wal" "$BACKUP_DIR/"
        log "WAL file also backed up"
    fi

    local size
    size=$(du -sh "$BACKUP_DIR" | awk '{print $1}')
    ok "Backup complete ($size): $BACKUP_DIR"
}

# ── Prune old backups ────────────────────────────────────────────────────────
prune() {
    if [ ! -d "$BACKUP_ROOT" ]; then
        return
    fi

    local count
    count=$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')

    if [ "$count" -le "$MAX_BACKUPS" ]; then
        log "Backups retained: $count (max: $MAX_BACKUPS)"
        return
    fi

    local to_prune=$((count - MAX_BACKUPS))
    log "Pruning $to_prune old backup(s)..."

    find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d \
        | sort \
        | head -n "$to_prune" \
        | while read -r dir; do
            log "  Removing: $dir"
            rm -rf "$dir"
        done

    ok "Pruning complete — kept last $MAX_BACKUPS backups"
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    log "─── Database Backup ───"
    backup
    prune
}

main "$@"
