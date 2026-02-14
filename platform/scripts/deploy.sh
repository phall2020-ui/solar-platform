#!/usr/bin/env bash
# =============================================================================
# Production Deployment Script
# Usage: ./scripts/deploy.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$PROJECT_DIR/backups/$TIMESTAMP"
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

# ── Pre-flight checks ───────────────────────────────────────────────────────
preflight() {
    log "Running pre-flight checks..."

    # Docker daemon running
    if ! docker info >/dev/null 2>&1; then
        err "Docker daemon is not running"
        exit 1
    fi
    ok "Docker daemon running"

    # Docker Compose available
    if ! $DOCKER_COMPOSE version >/dev/null 2>&1; then
        err "Docker Compose not available"
        exit 1
    fi
    ok "Docker Compose available ($DOCKER_COMPOSE)"

    # Disk space check (require at least 2 GB free)
    local avail_kb
    avail_kb=$(df -k "$PROJECT_DIR" | awk 'NR==2 {print $4}')
    local avail_gb=$((avail_kb / 1024 / 1024))
    if [ "$avail_gb" -lt 2 ]; then
        err "Insufficient disk space: ${avail_gb}GB free (need >= 2GB)"
        exit 1
    fi
    ok "Disk space: ${avail_gb}GB available"

    # docker-compose.yml exists
    if [ ! -f "$PROJECT_DIR/docker-compose.yml" ]; then
        err "docker-compose.yml not found in $PROJECT_DIR"
        exit 1
    fi
    ok "docker-compose.yml found"
}

# ── Database backup ──────────────────────────────────────────────────────────
backup_database() {
    log "Backing up database to $BACKUP_DIR ..."
    mkdir -p "$BACKUP_DIR"

    local db_file="$PROJECT_DIR/$DB_PATH"
    if [ -f "$db_file" ]; then
        cp "$db_file" "$BACKUP_DIR/"
        ok "Database backed up: $BACKUP_DIR/$(basename "$db_file")"
    else
        log "⚠️  Database file not found at $db_file — skipping backup"
    fi

    # Save current image tags for rollback
    $DOCKER_COMPOSE -f "$PROJECT_DIR/docker-compose.yml" config \
        > "$BACKUP_DIR/docker-compose-snapshot.yml" 2>/dev/null || true
    ok "Docker Compose config snapshot saved"
}

# ── Build ────────────────────────────────────────────────────────────────────
build_image() {
    log "Building new image (no cache)..."
    cd "$PROJECT_DIR"
    $DOCKER_COMPOSE build --no-cache
    ok "Image built successfully"
}

# ── Deploy ───────────────────────────────────────────────────────────────────
deploy() {
    log "Starting rolling restart..."
    cd "$PROJECT_DIR"
    $DOCKER_COMPOSE up -d --remove-orphans
    ok "Containers started"
}

# ── Health check ─────────────────────────────────────────────────────────────
health_check() {
    log "Waiting for health check (timeout: ${HEALTH_TIMEOUT}s)..."
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
    err "Health check failed after ${HEALTH_TIMEOUT}s"
    return 1
}

# ── Rollback ─────────────────────────────────────────────────────────────────
rollback() {
    err "Deployment failed — initiating rollback..."
    "$SCRIPT_DIR/rollback.sh" "$BACKUP_DIR"
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    log "========================================="
    log "  Production Deployment — $TIMESTAMP"
    log "========================================="

    preflight
    backup_database
    build_image
    deploy

    if health_check; then
        echo ""
        ok "🚀 Deployment successful!"
        log "  Backup stored in: $BACKUP_DIR"
        log "  App running at:   http://localhost:8501"
    else
        rollback
        exit 1
    fi
}

main "$@"
