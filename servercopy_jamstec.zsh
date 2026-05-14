#!/usr/bin/env zsh
#
# servercopy_jamstec.zsh
# Bathymetrix(TM) MERMAID operations
# https://bathymetrix.com
#
# Mirrors JAMSTEC RUDICS SFTP accounts into a local server directory.
# Expects a simple comma-separated credentials file; quoted commas in fields are
# not supported.
#
# Author: Joel D. Simon <jdsimon@bathymetrix.com>
# Last modified: 14-May-2026

usage() {
    cat <<'EOF'
servercopy_jamstec.zsh - Bathymetrix(TM) MERMAID operations
https://bathymetrix.com

Usage:
  ./servercopy_jamstec.zsh [--help]

Requirements:
  - MERMAID must be set in the environment.
  - lftp must be installed and available on PATH.

Credentials CSV format:
  - Read from $MERMAID/passwords/jamstec.csv.
  - No header lines are expected.
  - Column 1 must contain the SFTP username.
  - Column 2 must contain the SFTP password.
  - Columns are expected to be simple comma-separated fields.
  - Quoted commas in fields are not supported.

Notes:
  - Downloads from iridium-rudics.cls.fr using SFTP on port 22.
  - Mirrors the remote working directory into $MERMAID/server_jamstec/.
  - lftp mirror recurses into subdirectories by default.
  - This script does not delete remote files.
  - This script does not delete local files unless lftp replaces an older
    local copy of a file it is downloading.
  - If multiple users are mirrored into the same local directory, files with
    identical names may overwrite each other locally.
EOF
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

: "${MERMAID:?MERMAID must be set before running this script}"

if ! command -v lftp >/dev/null 2>&1; then
    printf "Error: lftp is required but was not found on PATH.\n" >&2
    exit 1
fi

credentials_file="$MERMAID/passwords/jamstec.csv"
server="$MERMAID/server_jamstec/"
sftp_host="iridium-rudics.cls.fr"
sftp_port="${SFTP_PORT:-22}"

if [[ ! -r "$credentials_file" ]]; then
    printf "Error: cannot read credentials file: %s\n" "$credentials_file" >&2
    exit 1
fi

mkdir -p "$server"

typeset -a login_failed_users

while IFS=$'\t' read -r user passwrd; do
    [[ -n "$user" && -n "$passwrd" ]] || continue

    printf "Syncing %s:\n" "$user"

    if ! lftp <<EOF
set sftp:auto-confirm yes
open -u "$user","$passwrd" "sftp://$sftp_host:$sftp_port"
mirror --verbose --continue --only-newer --parallel=4 \
    --exclude 'tools/' \
    --exclude 'backups/' \
    --exclude 'logs/' \
    --exclude 'lib64/' \
    --exclude-glob '*.cmd.*' \
    --exclude-glob '*.txt' \
    --exclude-glob '.*' \
    --exclude 'dummy' \
    . "$server"
    bye
EOF
    then
        login_failed_users+=("$user")
        printf "Warning: login failed for %s; continuing.\n" "$user" >&2
    fi
done < <(
    awk -F, '
        {
            gsub(/\r/, "")
            if ($1 != "" && $2 != "") {
                print $1 "\t" $2
            }
        }
    ' "$credentials_file"
)

if (( ${#login_failed_users[@]} > 0 )); then
    printf "\nLogin failures:\n" >&2
    printf "  %s\n" "${login_failed_users[@]}" >&2
fi

printf "\nDone: Synced to %s\n" "$server"
