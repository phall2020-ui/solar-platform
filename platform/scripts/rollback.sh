#!/usr/bin/env bash
# =============================================================================
# Rollback Script
# Usage: ./scripts/rollback.sh <backup_directory>
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HEALTH_URL="http://localhost:8501/_stcore/health"
HEALTH_TIMEOUT=30
DB_PATH="${UNIFIED_DB_PATH:-databases/plant_registry.duckdb}"

# Detect docker compose command
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "❌ ERROR: Docker Compose is not installed"
    exit 1
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { log "❌ ERROR: $*" >&2; }
ok()  { log "✅ $*"; }

# ── Validate arguments ──────────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_directory>"
    echo ""
    echo "Available backups:"
    if [ -d "$PROJECT_DIR/backups" ]; then
        ls -1d "$PROJECT_DIR/backups"/*/ 2>/dev/null | sort -r | head -10
    else
        echo "  (none)"
    fi
    exit 1
fi

BACKUP_DIR="$1"

# Allow relative paths from project root
if [ ! -d "$BACKUP_DIR" ]; then
    BACKUP_DIR="$PROJECT_DIR/backups/$1"
fi

if [ ! -d "$BACKUP_DIR" ]; then
    err "Backup directory not found: $1"
    exit 1
fi

# ── Stop current deployment ──────────────────────────────────────────────────
stop_current() {
    log "Stopping current deployment..."
    cd "$PROJECT_DIR"
    $DOCKER_COMPOSE down --timeout 30
    ok "Containers stopped"
}

# ── Restore database ────────────────────────────────────────────────────────
restore_database() {
    local db_file="$PROJECT_DIR/$DB_PATH"
    local db_name
    db_name=$(basename "$DB_PATH")
    local backup_db="$BACKUP_DIR/$db_name"

    if [ -f "$backup_db" ]; then
        log "Restoring database from $backup_db ..."
        mkdir -p "$(dirname "$db_file")"
        cp "$backup_db" "$db_file"
        ok "Database restored"
    else
        log "⚠️  No database backup found in $BACKUP_DIR — skipping restore"
    fi
}

# ── Restart previous version ────────────────────────────────────────────────
restart() {
    log "Restarting services..."
    cd "$PROJECT_DIR"
    $DOCKER_COMPOSE up -d --remove-orphans
    ok "Services restarted"
}

# ── Health check ─────────────────────────────────────────────────────────────
health_check() {
    log "Verifying health after rollback (timeout: ${HEALTH_TIMEOUT}s)..."
    local elapsed=0
    local interval=3
    while [ "$elapsed" -lt "$HEALTH_TIMEOUT" ]; do
        if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
            ok "Health check passed after ${elapsed}s"
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    err "Health check failed after rollback"
    return 1
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    log "========================================="
    log "  Rollback — from $BACKUP_DIR"
    log "========================================="

    stop_current
    restore_database
    restart

    if health_check; then
        echo ""
        ok "🔄 Rollback completed successfully!"
    else
        err "Rollback health check failed — manual intervention required"
        exit 1
    fi
}

main "$@"
