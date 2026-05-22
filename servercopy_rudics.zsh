#!/usr/bin/env zsh
#
# servercopy_rudics.zsh
# Bathymetrix(TM) MERMAID operations
# https://bathymetrix.com
#
# Mirrors selected MERMAID artifacts from RUDICS SFTP accounts into per-user
# local server directories.
# Expects intentional simple unquoted credentials: one user,pass pair per line.
# No quoted CSV parsing is supported; usernames and passwords must not contain
# commas, quotes, backslashes, or whitespace.
#
# Author: Joel D. Simon <jdsimon@bathymetrix.com>
# Last modified: 21-May-2026

SERVERCOPY_RUDICS_VERSION="0.2.3"

include_patterns=(
    "*.cmd"
    "*.out"
    "*.vit"
    "*.LOG"
    "*.BIN"
    "*.MER"
    "*.[0-9][0-9][0-9]"
    "*.S41"
    "*.S61"
    "*.RBR"
)

exclude_directories=(
    "backups/"
    "tools/"
    "lib64/"
    "logs/"
)

usage() {
    cat <<'EOF'
servercopy_rudics.zsh - Bathymetrix MERMAID operations
https://bathymetrix.com

Usage:
  ./servercopy_rudics.zsh [options]

Options:
  -c, --check        Validate local configuration only
  --dry-run          Preview remote artifact mirror operations
  -u, --user USERS   Comma-separated usernames
  -h, --help         Show help
  -v, --version      Show script version

Requirements:
  - MERMAID must be set in the environment.
  - lftp must be installed and available on PATH.

Credentials CSV format:
  - Read from $MERMAID/passwords/rudics.csv.
  - Intentionally simple unquoted CSV: user,pass
  - No header row is expected.
  - Column 1 must contain the SFTP username.
  - Column 2 must contain the SFTP password.
  - Blank lines are skipped.
  - Lines beginning with # are skipped.
  - No quoted CSV parsing is supported.
  - Usernames and passwords must not contain commas, quotes, backslashes, or
    whitespace.
  - Usernames are used as a single local path component and must not be empty,
    ".", "..", or contain "/".

Notes:
  - Downloads from rudics.thorium.cls.fr using SFTP.
  - SFTP_PORT may override the default port 22 and must be numeric.
  - Mirrors selected MERMAID artifact/log file types from each account into
    $MERMAID/servers/<user>/.
  - Included file patterns, in order:
    *.cmd
    *.out
    *.vit
    *.LOG
    *.BIN
    *.MER
    *.[0-9][0-9][0-9]
    *.S41
    *.S61
    *.RBR
  - Excluded directories:
    backups/
    tools/
    lib64/
    logs/
  - Hidden dotfiles and hidden dot-directories are excluded.
  - -u USERS, --user USERS, or --user=USERS processes only matching
    configured users. USERS is a comma-separated username list.
  - Appends one UTC run-ledger row per user mirror attempt to:
    $MERMAID/servers/_runs/servercopy_rudics_runs.csv
  - -v or --version prints the script version and exits.
  - -c or --check validates local configuration and prints intended mirror
    operations without contacting remote servers, authenticating, transferring
    files, creating directories or files, or appending to the run ledger.
  - --dry-run contacts and authenticates to RUDICS, then asks lftp to
    print the mirror operations it would perform without transferring files or
    modifying local files. It does not append to the run ledger. --dry-run is
    not offline. Use --check for offline/local validation.
  - This script does not delete remote or local mirror files.
  - Remote deletions do not remove local files.
  - Files and directories outside the artifact mirror policy are skipped.
EOF
}

utc_now() {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
}

print_version() {
    printf "servercopy_rudics.zsh %s\n" "$SERVERCOPY_RUDICS_VERSION"
}

lftp_quote_arg() {
    local value="$1"

    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"

    printf '"%s"' "$value"
}

trim_space() {
    local value="$1"

    while [[ "$value" == [[:space:]]* ]]; do
        value="${value[2,-1]}"
    done
    while [[ "$value" == *[[:space:]] ]]; do
        value="${value[1,-2]}"
    done

    printf "%s" "$value"
}

append_lftp_output() {
    local output="$1"
    local line

    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == [Ww]arning:* ]]; then
            warnings+=("$line")
        else
            printf "%s\n" "$line"
        fi
    done <<< "$output"
}

record_failure() {
    local user="$1"
    local detail="${2:-}"
    local line
    local clean_detail=""

    failed_users+=("$user")

    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == [Ww]arning:* ]]; then
            warnings+=("$line")
        elif [[ -n "$line" ]]; then
            clean_detail+="${line}"$'\n'
        fi
    done <<< "$detail"

    failure_details[$user]="${clean_detail%$'\n'}"
}

run_lftp_mirror() {
    local user="$1"
    local passwrd="$2"
    local destination="$3"
    local preview="$4"
    local -a mirror_args
    local -a quoted_args
    local arg
    local mirror_command

    if (( preview )); then
        mirror_args=("${mirror_options[@]}" "${mirror_filter_options[@]}" --dry-run . "$destination")
    else
        mirror_args=("${mirror_options[@]}" "${mirror_filter_options[@]}" . "$destination")
    fi
    for arg in "${mirror_args[@]}"; do
        quoted_args+=("$(lftp_quote_arg "$arg")")
    done
    mirror_command="mirror ${(j: :)quoted_args}"

    lftp 2>&1 <<EOF
set sftp:auto-confirm yes
open -u "$user","$passwrd" "sftp://$sftp_host:$sftp_port"
$mirror_command
bye
EOF
}

emulate -L zsh
set -euo pipefail

check_mode=0
dry_run=0
user_filter=""
user_filter_provided=0
mirror_options=(
    --verbose
    --continue
    --overwrite
    --no-perms
    --no-empty-dirs
    --parallel=4
)
mirror_filter_options=(
    --exclude-glob "*"
    --include-glob "*/"
)

# lftp needs an explicit directory include to traverse normal subdirectories.
# The catch-all exclude comes first so later artifact includes can override it;
# hidden and named directory excludes come after the includes so they still win.
for include_pattern in "${include_patterns[@]}"; do
    mirror_filter_options+=(--include-glob "$include_pattern")
done
mirror_filter_options+=(
    --exclude-glob ".*"
    --exclude-glob ".*/"
    --exclude-glob "*/.*"
    --exclude-glob "*/.*/"
)
for exclude_directory in "${exclude_directories[@]}"; do
    mirror_filter_options+=(--exclude-glob "$exclude_directory")
    mirror_filter_options+=(--exclude-glob "${exclude_directory}*")
done

while (( $# > 0 )); do
    case "$1" in
        -c|--check)
            check_mode=1
            ;;
        --dry-run)
            dry_run=1
            ;;
        -u|--user)
            if (( $# < 2 )); then
                printf "Error: %s requires a comma-separated username list.\n\n" "$1" >&2
                usage >&2
                exit 2
            fi
            user_filter="$2"
            user_filter_provided=1
            shift
            ;;
        --user=*)
            user_filter="${1#--user=}"
            user_filter_provided=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -v|--version)
            print_version
            exit 0
            ;;
        *)
            printf "Error: unknown argument: %s\n\n" "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if (( check_mode && dry_run )); then
    printf "Error: --check and --dry-run are mutually exclusive.\n" >&2
    exit 2
fi

if (( user_filter_provided )) && [[ -z "$user_filter" ]]; then
    printf "Error: --user requires a comma-separated username list.\n" >&2
    exit 2
fi

typeset -A requested_users
typeset -A seen_requested_users
typeset -a requested_user_order

if (( user_filter_provided )); then
    for raw_user in ${(s:,:)user_filter}; do
        requested_user="$(trim_space "$raw_user")"
        if [[ -z "$requested_user" ]]; then
            printf "Error: --user contains an empty username.\n" >&2
            exit 2
        fi
        if [[ -z "${requested_users[$requested_user]:-}" ]]; then
            requested_user_order+=("$requested_user")
        fi
        requested_users[$requested_user]=1
    done
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

case "$sftp_port" in
    ""|*[!0-9]*)
        printf "Error: SFTP_PORT must be numeric.\n" >&2
        exit 1
        ;;
esac

if [[ ! -r "$credentials_file" ]]; then
    printf "Error: cannot read credentials file: %s\n" "$credentials_file" >&2
    exit 1
fi

if ! awk -F, '
    {
        gsub(/\r/, "")
        if ($0 ~ /^[[:space:]]*$/ || $0 ~ /^[[:space:]]*#/) {
            next
        }
        if (NF != 2 || $1 == "" || $2 == "") {
            printf "Error: malformed credentials line %d in %s\n", NR, FILENAME > "/dev/stderr"
            exit 1
        }
        if ($1 == "." || $1 == ".." || $1 ~ /\//) {
            printf "Error: unsafe username path component on credentials line %d in %s: %s\n", NR, FILENAME, $1 > "/dev/stderr"
            exit 1
        }
    }
' "$credentials_file"; then
    exit 1
fi

if ! (( check_mode || dry_run )); then
    mkdir -p "$server_root" "$runs_dir"

    if [[ ! -e "$runs_ledger" ]]; then
        printf "user,result,start,end,ver\n" > "$runs_ledger"
    else
        IFS= read -r ledger_header < "$runs_ledger" || ledger_header=""
        if [[ "$ledger_header" != "user,result,start,end,ver" ]]; then
            printf "Error: unexpected run ledger header in %s\n" "$runs_ledger" >&2
            exit 1
        fi
    fi
fi

typeset -a failed_users
typeset -a warnings
typeset -A failure_details
processed_users=0

while IFS=$'\t' read -r user passwrd; do
    [[ -n "$user" && -n "$passwrd" ]] || continue

    if (( user_filter_provided )); then
        [[ -n "${requested_users[$user]:-}" ]] || continue
        seen_requested_users[$user]=1
    fi

    (( processed_users += 1 ))
    server="$server_root/$user"
    run_started_utc="$(utc_now)"

    if (( check_mode )); then
        printf "[check] user=%s\n" "$user"
        printf "[check] remote=sftp://%s:%s\n" "$sftp_host" "$sftp_port"
        printf "[check] destination=%s\n\n" "$server"
        if [[ -e "$server" && ! -d "$server" ]]; then
            record_failure "$user" "destination exists but is not a directory: $server"
        fi
        continue
    fi

    if (( dry_run )); then
        printf "[dry-run] user=%s\n" "$user"
        printf "[dry-run] remote=sftp://%s:%s\n" "$sftp_host" "$sftp_port"
        printf "[dry-run] destination=%s\n" "$server"
        printf "[dry-run] lftp mirror preview follows:\n"

        if lftp_output="$(run_lftp_mirror "$user" "$passwrd" "$server" 1)"; then
            append_lftp_output "$lftp_output"
        else
            record_failure "$user" "$lftp_output"
        fi
        printf "\n"
        continue
    fi

    if ! mkdir -p "$server"; then
        record_failure "$user" "could not create destination directory: $server"
        printf "%s,failure,%s,,%s\n" "$user" "$run_started_utc" "$SERVERCOPY_RUDICS_VERSION" >> "$runs_ledger"
        continue
    fi

    printf "Syncing %s to %s:\n" "$user" "$server"

    if lftp_output="$(run_lftp_mirror "$user" "$passwrd" "$server" 0)"; then
        append_lftp_output "$lftp_output"
        run_finished_utc="$(utc_now)"
        printf "%s,success,%s,%s,%s\n" "$user" "$run_started_utc" "$run_finished_utc" "$SERVERCOPY_RUDICS_VERSION" >> "$runs_ledger"
    else
        record_failure "$user" "$lftp_output"
        printf "%s,failure,%s,,%s\n" "$user" "$run_started_utc" "$SERVERCOPY_RUDICS_VERSION" >> "$runs_ledger"
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

printf "##########################################################\n"
if (( user_filter_provided )); then
    for requested_user in "${requested_user_order[@]}"; do
        if [[ -z "${seen_requested_users[$requested_user]:-}" ]]; then
            warnings+=("Warning: requested user not found in credentials file: $requested_user")
        fi
    done

    if (( processed_users == 0 )); then
        if (( ${#warnings[@]} > 0 )); then
            printf "%s\n" "${warnings[@]}" >&2
        fi
        printf "Error: no requested users were found in credentials file: %s\n" "$credentials_file" >&2
        exit 1
    fi
fi

if (( ${#warnings[@]} > 0 )); then
    printf "%s\n" "${warnings[@]}" >&2
fi

if (( ${#failed_users[@]} > 0 )); then
    printf "\nFailures:\n" >&2
    for failed_user in "${failed_users[@]}"; do
        printf "  %s\n" "$failed_user" >&2
        if [[ -n "${failure_details[$failed_user]:-}" ]]; then
            while IFS= read -r line || [[ -n "$line" ]]; do
                printf "    %s\n" "$line" >&2
            done <<< "${failure_details[$failed_user]}"
        fi
    done
    exit 1
fi
if (( check_mode )); then
    printf "DONE: local check completed for %s\n" "$server_root"
    exit 0
fi
if (( dry_run )); then
    printf "\nDONE: dry run completed for %s\n" "$server_root"
    printf "\n##########################################################\n"
    exit 0
fi
printf "\nDONE: synced all accounts to %s\n" "$server_root"
printf "\n##########################################################\n"
