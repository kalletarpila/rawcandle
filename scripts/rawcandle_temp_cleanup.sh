#!/usr/bin/env bash
set -euo pipefail

TEMP_DIR="/home/kalle/projects/rawcandle/temp"
LOG_DIR="/home/kalle/logs/rawcandle_temp_cleanup"
LOCK_FILE="/tmp/rawcandle_temp_cleanup.lock"

MODE="${1:---dry-run}"

if [[ "$MODE" != "--dry-run" && "$MODE" != "--apply" ]]; then
    echo "Usage: $0 [--dry-run|--apply]" >&2
    exit 2
fi

if [[ ! -d "$TEMP_DIR" ]]; then
    echo "ERROR: Temp directory not found: $TEMP_DIR" >&2
    exit 1
fi

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/cleanup_$(date +%Y%m%d_%H%M%S).log"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "ERROR: Another cleanup run is already active." >&2
    exit 1
fi

is_protected_file() {
    case "$(basename "$1")" in
        analysis__ec_source_layer_backfill__*|analysis__ec_source_layer_refresh__*)
            # Owned by the EC scheduler terminal lifecycle, including zero-byte
            # interrupted destinations and their diagnostic sidecars.
            return 0
            ;;
        analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite|\
        analysis__before_dc_report_v2_cleanup__20260617T143742Z.sqlite|\
        analysis__before_dc_dashboard_enrichment_cleanup__20260617T170509Z.sqlite)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

remove_candidate() {
    local reason="$1"
    local file="$2"

    if is_protected_file "$file"; then
        printf 'PROTECTED    %s\n' "$file"
        return
    fi

    if [[ "$MODE" == "--apply" ]]; then
        printf 'DELETE %-22s %s\n' "$reason" "$file"
        rm -- "$file"
    else
        printf 'WOULD_DELETE %-16s %s\n' "$reason" "$file"
    fi
}

{
    echo "RawCandle temp cleanup"
    echo "Started: $(date --iso-8601=seconds)"
    echo "Mode: $MODE"
    echo "Temp directory: $TEMP_DIR"
    echo

    echo "=== EC source-layer backups ==="
    echo "Protected here; rawcandle.ec_backup_retention owns terminal release."
    echo

    echo "=== Smoke databases older than 14 days ==="

    while IFS= read -r -d '' file; do
        remove_candidate "old-smoke" "$file"
    done < <(
        find "$TEMP_DIR" -maxdepth 2 -type f \
            \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) \
            \( -iname '*smoke*' -o -iname '*resmoke*' \) \
            -mtime +14 -print0
    )

    echo
    echo "=== Before-backups older than 30 days ==="

    while IFS= read -r -d '' file; do
        remove_candidate "old-before" "$file"
    done < <(
        find "$TEMP_DIR" -maxdepth 1 -type f \
            \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) \
            \( -name 'analysis_before_*' -o -name 'analysis__before_*' \) \
            -mtime +30 -print0
    )

    echo
    echo "=== Empty databases older than one day ==="

    while IFS= read -r -d '' file; do
        remove_candidate "empty-database" "$file"
    done < <(
        find "$TEMP_DIR" -maxdepth 2 -type f \
            \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) \
            -size 0 -mtime +1 -print0
    )

    echo
    echo "=== Current disk usage ==="
    du -sh "$TEMP_DIR"
    df -h /

    echo
    echo "Finished: $(date --iso-8601=seconds)"
} 2>&1 | tee "$LOG_FILE"
