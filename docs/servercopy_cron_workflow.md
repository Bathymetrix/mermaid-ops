# Servercopy Cron Workflow

## Overview

`servercopy` remains responsible only for synchronization. The cron job invokes
the directly executable Python 3.14 wrapper `servercopy_cron`, which adds the
small amount of operational policy needed around a scheduled run and reports
the lifecycle of the complete workflow to Healthchecks.io:

```text
cron invokes servercopy_cron
        |
        v
acquire lock and validate monitoring configuration
        |
        v
send Healthchecks.io /start
        |
        v
run servercopy
        |
        v
did synchronization succeed?
    no  --> send /fail
            perform no Git operations
            exit with the synchronization failure status
    yes --> continue
        |
        v
validate and perform the conservative Git workflow
        |
        v
did the complete workflow succeed?
    no  --> send /fail
            exit nonzero
    yes --> send success
            exit zero
```

The wrapper requires a nonempty `MERMAID` environment variable. It derives all
paths without a separate `MERMAID_OPS` setting:

```text
servers repository   $MERMAID/servers
lock                  $MERMAID/logs/servercopy_cron.lock
servercopy command    <mermaid-ops repository>/servercopy
monitoring UUID file  <mermaid-ops repository>/data/healthchecks_uuid.txt
```

The repository-local paths are resolved from `servercopy_cron` itself.
`servercopy_cron --version` (or `-v`) reports the wrapper's independent
operational version without requiring `MERMAID`, loading monitoring
configuration, or starting a run. `SERVERCOPY_CRON_VERSION` is independent of
the `servercopy` version and should be incremented whenever the wrapper's CLI,
locking, monitoring, or Git behavior changes meaningfully.

## Locking and monitoring configuration

The wrapper takes a nonblocking advisory lock before loading the Healthchecks.io
configuration and holds it through synchronization, Git work, and the terminal
Healthchecks.io ping. If another wrapper owns the lock, the new invocation exits
nonzero without loading the UUID, sending `/start` or `/fail`, running
`servercopy`, or using Git. The lock contains no PID and requires no stale-lock
cleanup.

Monitoring configuration is required. The private file:

```text
data/healthchecks_uuid.txt
```

contains exactly one Healthchecks.io Check UUID. Blank lines and comment lines
whose first non-whitespace character is `#` are ignored, and surrounding
whitespace on the UUID is permitted. Multiple values, internal whitespace, an
empty file, and malformed UUIDs are rejected. The wrapper normalizes the value
with Python's `uuid.UUID` and never includes the configured UUID in errors or
logs.

The UUID is a capability secret because possession of it permits forged pings.
The file is Git-ignored, must remain untracked, and should have restrictive
permissions:

```sh
chmod 600 data/healthchecks_uuid.txt
```

If the file is missing, unreadable, empty, or invalid, the wrapper exits
nonzero after releasing the lock. It does not send a Healthchecks.io ping, run
`servercopy`, or perform Git operations.

## Healthchecks.io execution monitoring

The wrapper constructs Ping URLs internally from the fixed base URL
`https://hc-ping.com`; the configuration file contains only the Check UUID.
Each lifecycle signal is one empty HTTP POST with a 15-second timeout:

```text
start     https://hc-ping.com/<check-uuid>/start
success   https://hc-ping.com/<check-uuid>
failure   https://hc-ping.com/<check-uuid>/fail
```

The wrapper does not upload command output, logs, filenames, exceptions, or
credentials. It requires an HTTP-success response, does not read or report the
response body, and does not retry.

The `/start` request must succeed before `servercopy` begins. If it fails, the
wrapper reports a sanitized monitoring error and exits nonzero without
synchronization or Git activity. This prevents an unmonitored run from
modifying the servers repository.

After `/start` succeeds, every handled synchronization or Git failure attempts
`/fail`. A secondary failure-ping error is reported but never replaces the
meaningful underlying nonzero status. A success ping is sent only after the
entire synchronization-and-Git workflow has completed. If that final request
fails, the wrapper exits nonzero but does not undo a completed commit or other
successful work.

Healthchecks.io, not the wrapper, detects executions that never report a
terminal state:

```text
cron never runs, the host disappears, or the process hangs
        |
        v
no expected terminal ping arrives
        |
        v
Healthchecks.io detects the missed deadline
        |
        v
Healthchecks.io sends alerts through its configured Integrations
```

Human-facing alert delivery is configured in Healthchecks.io. Telegram may be
selected as an Integration there, but this repository does not configure
Telegram, call the Telegram Bot API, or store a Telegram bot token or chat ID.

## Synchronization behavior

After the start ping succeeds, `servercopy` is invoked with:

```text
--output $MERMAID/servers
```

Its stdout and stderr are inherited rather than captured, so the cron log is
updated while the long-running synchronization is in progress.

If `servercopy` returns nonzero, the wrapper:

- attempts one Healthchecks.io failure ping;
- runs no Git command, including read-only Git inspection;
- leaves partial downloads in the working tree without staging, reverting, or
  deleting them; and
- returns the original nonzero synchronization status, even if the failure ping
  also fails.

The next scheduled cron invocation runs normally. A later successful
synchronization can finish the partial downloads and commit the resulting
state.

The wrapper follows `servercopy`'s existing exit-status contract; it does not
parse or reinterpret synchronization output. In particular, `servercopy`
currently returns zero when at least one source runs successfully and other
sources are skipped for missing credentials. That existing behavior is
unchanged, so credential configuration must be maintained as an operational
prerequisite.

The outer lock coordinates `servercopy_cron` invocations. Do not launch
`servercopy` manually while the scheduled wrapper may be running: the direct
command's internal lock covers synchronization, but it does not cover the
wrapper's later Git and terminal-ping window.

## Git behavior after synchronization

Git is considered only after `servercopy` returns zero. The wrapper first
verifies that `$MERMAID/servers` is the exact root of a Git working tree. It then
checks the entire index before staging anything.

If the index already contains staged changes, the wrapper refuses to run
`git add` or `git commit`, sends the failure ping, and exits nonzero. This
prevents an unattended run from committing work staged by a person or another
process.

With a clean index, the wrapper runs:

```sh
git -C "$MERMAID/servers" add -A
```

If the index is still empty, it prints a concise no-changes message, sends the
success ping, and exits zero. Otherwise it creates a commit such as:

```text
servercopy [cron]: 2026-07-23T22:30:00Z
```

The timestamp is timezone-aware UTC. Only after the commit succeeds does the
wrapper send the success ping and exit zero. The wrapper never pushes.

A Git worktree check, index inspection, staging, or commit failure is reported
to stderr, followed by an attempted failure ping and a nonzero exit. The wrapper
does not reset the index, remove lock files, roll back files, or otherwise
attempt automatic recovery. A success-ping failure after completed Git work
also exits nonzero but does not attempt a rollback or send `/fail`.

## Crontab and Healthchecks.io Check setup

Create the log directory once before installing the cron entry. Shell
redirection happens before the wrapper can create the directory for its lock:

```sh
mkdir -p /Users/jdsimon/mermaid/logs
```

Use the wrapper, not `servercopy`, in crontab:

```cron
PATH=/opt/homebrew/bin:/usr/bin:/bin
MERMAID=/Users/jdsimon/mermaid
30 7,15,23 * * * /Users/jdsimon/programs/mermaid-ops/servercopy_cron >> /Users/jdsimon/mermaid/logs/servercopy_cron.log 2>&1
```

The existing cron command needs no monitoring environment variables because
the wrapper reads its repository-local ignored UUID file. This schedule runs at
07:30, 15:30, and 23:30 in the host's local timezone. The redirected log
receives live `servercopy` output plus wrapper diagnostics.

Configure the Healthchecks.io Check with the actual cron expression:

```cron
30 7,15,23 * * *
```

Set the Check timezone to the same timezone used by the cron host. Set its Grace
Time longer than the longest legitimate `servercopy_cron` runtime so an active,
slow synchronization is not mistaken for a hung run. Configure one or more
Healthchecks.io Integrations if human-facing alerts are desired.
`servercopy_cron` does not create or manage the Healthchecks.io account, Check,
schedule, Grace Time, or Integrations.

## Exit status summary

- `--version` or `-v`: zero without requiring `MERMAID`, the lock, or monitoring
  configuration.
- Missing `MERMAID`, lock setup failure, lock acquisition failure, or overlap
  refusal: nonzero, with no monitoring ping, synchronization, or Git action.
- Missing, unreadable, empty, or invalid UUID file: nonzero, with no monitoring
  ping, synchronization, or Git action.
- Start-ping failure: nonzero, with no synchronization or Git action.
- Synchronization failure: the original nonzero `servercopy` status after one
  failure-ping attempt, with no Git command.
- Git validation, inspection, staging, or commit failure: nonzero after one
  failure-ping attempt and with no automatic recovery.
- Successful synchronization with no changes: zero after the success ping.
- Successful synchronization and commit: zero after the success ping.
- Success-ping failure after otherwise successful work: nonzero, with completed
  Git work left intact and no failure ping.
- Failure-ping failure: the original workflow failure status, with the
  secondary monitoring error reported generically.
