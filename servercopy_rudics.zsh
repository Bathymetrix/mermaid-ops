#!/usr/bin/env zsh
#
# servercopy_rudics.zsh
# Bathymetrix MERMAID operations
# https://bathymetrix.com
#
# Mirrors RUDICS SFTP accounts into per-user local server directories.
# Expects a simple comma-separated credentials file; quoted commas in fields are
# not supported.
#
# Author: Joel D. Simon <jdsimon@bathymetrix.com>
# Last modified: 21-May-2026

usage() {
    cat <<'EOF'
servercopy_rudics.zsh - Bathymetrix MERMAID operations
https://bathymetrix.com

Usage:
  ./servercopy_rudics.zsh [--help]

Requirements:
  - MERMAID must be set in the environment.
  - lftp must be installed and available on PATH.

Credentials CSV format:
  - Read from $MERMAID/passwords/rudics.csv.
  - No header row is expected.
  - Column 1 must contain the SFTP username.
  - Column 2 must contain the SFTP password.
  - Blank lines are skipped.
  - Lines beginning with # are skipped.
  - Columns are expected to be simple comma-separated fields.
  - Quoted commas in fields are not supported.

Notes:
  - Downloads from rudics.thorium.cls.fr using SFTP.
  - SFTP_PORT may override the default port 22.
  - Mirrors each account into $MERMAID/servers/<user>/.
  - Appends one UTC run-ledger row per user mirror attempt to:
    $MERMAID/servers/_runs/servercopy_rudics_runs.csv
  - lftp mirror recurses into subdirectories by default.
  - This script does not delete remote files.
  - This script does not use lftp --delete.
  - This script intentionally does not exclude remote content.
EOF
}

utc_now() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

emulate -L zsh
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

if (( $# > 0 )); then
    printf "Error: unknown argument: %s\n\n" "$1" >&2
    usage >&2
    exit 2
fi

if [[ -z "${MERMAID:-}" ]]; then
    printf "Error: MERMAID must be set before running this script.\n" >&2
    exit 1
fi

if ! command -v lftp >/dev/null 2>&1; then
    printf "Error: lftp is required but was not found on PATH.\n" >&2
    exit 1
fi

credentials_file="$MERMAID/passwords/rudics.csv"
server_root="$MERMAID/servers"
runs_dir="$server_root/_runs"
runs_ledger="$runs_dir/servercopy_rudics_runs.csv"
sftp_host="rudics.thorium.cls.fr"
sftp_port="${SFTP_PORT:-22}"

if [[ ! -r "$credentials_file" ]]; then
    printf "Error: cannot read credentials file: %s\n" "$credentials_file" >&2
    exit 1
fi

mkdir -p "$server_root" "$runs_dir"

if [[ ! -e "$runs_ledger" ]]; then
    printf "run_started_utc,user,status,run_finished_utc\n" > "$runs_ledger"
fi

typeset -a failed_users

while IFS=$'\t' read -r user passwrd; do
    [[ -n "$user" && -n "$passwrd" ]] || continue

    server="$server_root/$user"
    run_started_utc="$(utc_now)"

    if ! mkdir -p "$server"; then
        failed_users+=("$user")
        printf "%s,%s,failure,\n" "$run_started_utc" "$user" >> "$runs_ledger"
        printf "Warning: sync failed for %s; continuing.\n" "$user" >&2
        continue
    fi

    printf "Syncing %s to %s:\n" "$user" "$server"

    if ! lftp <<EOF
set sftp:auto-confirm yes
open -u "$user","$passwrd" "sftp://$sftp_host:$sftp_port"
mirror --verbose --continue --only-newer --parallel=4 \
    . "$server"
bye
EOF
    then
        failed_users+=("$user")
        printf "%s,%s,failure,\n" "$run_started_utc" "$user" >> "$runs_ledger"
        printf "Warning: sync failed for %s; continuing.\n" "$user" >&2
    else
        run_finished_utc="$(utc_now)"
        printf "%s,%s,success,%s\n" "$run_started_utc" "$user" "$run_finished_utc" >> "$runs_ledger"
    fi
done < <(
    awk -F, '
        {
            gsub(/\r/, "")
            if ($0 ~ /^[[:space:]]*$/ || $0 ~ /^[[:space:]]*#/) {
                next
            }
            if ($1 != "" && $2 != "") {
                print $1 "\t" $2
            }
        }
    ' "$credentials_file"
)

if (( ${#failed_users[@]} > 0 )); then
    printf "\nFailures:\n" >&2
    printf "  %s\n" "${failed_users[@]}" >&2
    exit 1
fi

printf "\nDone: Synced all accounts to %s\n" "$server_root"
