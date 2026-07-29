# Servercopy Cron Workflow

## Overview

`servercopy` remains responsible only for synchronization. The cron job invokes
the Python 3.12 wrapper `servercopy_cron`, which adds the small amount of
operational policy needed around a scheduled run and reports the lifecycle of
the complete workflow to Healthchecks.io:

```text
cron invokes servercopy_cron
        |
        v
resolve MERMAID, create run log, and write invocation header
        |
        v
acquire lock and validate monitoring configuration
        |
        v
send Healthchecks.io /start
        |
        v
verify the servers Git repository is completely clean
        |
        v
is the repository clean?
    no  --> print Git status and send /fail
            perform no synchronization, staging, or commit
            exit nonzero
    yes --> continue
        |
        v
query servercopy --version
        |
        v
did version discovery succeed?
    no  --> send /fail
            perform no synchronization or Git operations
            exit nonzero
    yes --> continue
        |
        v
run servercopy
        |
        v
did synchronization succeed?
    no  --> record the synchronization failure and continue
    yes --> record synchronization success and continue
        |
        v
validate and perform the conservative Git workflow
        |
        v
did Git processing succeed?
    no  --> report the Git failure and any synchronization failure
            send /fail
            exit nonzero
    yes --> did synchronization succeed?
                no  --> send /fail and exit with the synchronization status
                yes --> send success and exit zero
```

The wrapper requires a nonempty `MERMAID` environment variable. It derives all
paths without a separate `MERMAID_OPS` setting:

```text
servers repository   $MERMAID/servers
lock                  $MERMAID/logs/servercopy_cron.lock
workflow logs         $MERMAID/logs/servercopy_cron/<UTC>.log
servercopy command    <mermaid-ops repository>/servercopy
monitoring UUID file  <mermaid-ops repository>/data/healthchecks_uuid.txt
```

Production is `frisius.princeton.edu`, with these resolved paths:

```text
repository            /home/jdsimon/programs/mermaid-ops
MERMAID                /home/jdsimon/mermaid
Python                 /home/jdsimon/miniforge3/envs/python3.12/bin/python3
workflow logs          /home/jdsimon/mermaid/logs/servercopy_cron/
outer cron log         /home/jdsimon/mermaid/logs/servercopy_cron_cron.log
lock                   /home/jdsimon/mermaid/logs/servercopy_cron.lock
monitoring UUID file   /home/jdsimon/programs/mermaid-ops/data/healthchecks_uuid.txt
```

See [`frisius_installation.md`](frisius_installation.md) for installation,
configuration, verification, and the complete production crontab.

The repository-local paths are resolved from `servercopy_cron` itself.
`servercopy_cron --version` (or `-v`) reports the wrapper's independent
operational version without requiring `MERMAID`, loading monitoring
configuration, or starting a run. `SERVERCOPY_CRON_VERSION` is independent of
the `servercopy` version and should be incremented whenever the wrapper's CLI,
locking, monitoring, or Git behavior changes meaningfully.

For commit provenance, `servercopy_cron` obtains `servercopy`'s independently
versioned value through the public `servercopy --version` CLI and records both
versions. The executables do not need matching versions and do not share a
version constant.

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

## Per-invocation logging

Immediately after parsing normal-operation arguments and resolving `MERMAID`,
the wrapper creates exactly one UTC-timestamped log:

```text
$MERMAID/logs/servercopy_cron/2026-07-27T19-56-50Z.log
```

The wrapper internally duplicates stdout and stderr to the terminal and the
log, flushing each write promptly. It also copies `servercopy` stdout and stderr
through live, line-buffered streams, so interactive output remains visible
during long synchronizations. The transcript includes wrapper, synchronization,
Git, and Healthchecks diagnostics plus the final workflow exit status. No
external `tee` command is used. The production crontab separately appends
launcher output to
`/home/jdsimon/mermaid/logs/servercopy_cron_cron.log` so cron-startup and
pre-wrapper failures have an outer diagnostic.

This boundary precedes lock-file preparation, lock acquisition, and monitoring
configuration, so failures in those stages receive the same complete
transcript. Unexpected exceptions inside the logged invocation are recorded
with a traceback and final nonzero status. Each transcript begins with:

```text
servercopy_cron started: <UTC timestamp>
servercopy_cron version: <version>
invocation: <user>@<fully-qualified-hostname>
system: <system information>
MERMAID: <resolved path>
repository: <resolved mermaid-ops repository path>
command: <safely rendered argv>
log: <log path>
```

After the monitored workflow successfully determines the synchronization
engine version, the transcript records `servercopy version: <version>`.

Lightweight operations remain outside this logging boundary.
`servercopy_cron --version` exits before lock acquisition, monitoring
configuration, or log creation. A missing `MERMAID` also retains direct
stderr-only behavior: because the configured log directory is beneath
`MERMAID`, the wrapper cannot determine it without inventing an implicit root.

## Healthchecks.io execution monitoring

The wrapper constructs Ping URLs internally from the fixed base URL
`https://hc-ping.com`; the configuration file contains only the Check UUID.
Each lifecycle signal is one HTTP POST with a 15-second timeout:

```text
start     https://hc-ping.com/<check-uuid>/start
success   https://hc-ping.com/<check-uuid>
failure   https://hc-ping.com/<check-uuid>/fail
```

The start and success bodies are empty. A failure request contains a bounded,
concise summary of the immediate failure, recent useful diagnostic output, and
the local workflow-log path when available. The complete transcript remains
local; credentials and the private Check UUID are never included. The wrapper
requires an HTTP-success response, does not read or report the response body,
and does not retry.

The `/start` request must succeed before `servercopy` begins. If it fails, the
wrapper reports a sanitized monitoring error and exits nonzero without
synchronization or Git activity. This prevents an unmonitored run from
modifying the servers repository.

After `/start` succeeds, a version-discovery, synchronization, or Git failure
attempts `/fail`. A secondary failure-ping error is reported but never replaces
the meaningful underlying nonzero status. A success ping is sent only after
the entire synchronization-and-Git workflow has completed. If that final
request fails, the wrapper exits nonzero but does not undo a completed commit
or other successful work.

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

After the start ping succeeds and `servercopy --version` returns a valid
version, `servercopy` is invoked with the wrapper's current Python interpreter
and:

```text
--output $MERMAID/servers
```

Its stdout and stderr are copied concurrently to the live terminal streams and
the current workflow transcript. `PYTHONUNBUFFERED=1` is set for the child
process so output remains prompt while the long-running synchronization is in
progress. Production cron does not activate Conda; its explicit Miniforge
interpreter therefore remains authoritative for both programs.

For each configured source, `servercopy` runs one `lftp mirror` after selecting
that source's configured remote root and local destination. The single mirror
command uses multiple `--include-glob` filters for `.MER`, `.LOG`, `.BIN`,
`.cmd`, `.out`, `.vit`, `.S41`, `.S61`, and exactly three-digit suffixes from
`.000` through `.999`. It also uses `--no-recursion`, so only approved files
located directly in the configured remote root are synchronized and no
subdirectory is traversed. RUDICS SFTP, ESO FTPS, and Kobe FTPS differ only in
connection and path configuration.

An eligible path can still be unreadable because of server-side ownership or
permissions. Such a path remains absent locally. If the access failure makes
`lftp` return nonzero, the source and overall `servercopy` run are failures
even if other files transferred.

If `servercopy` returns nonzero, the wrapper:

- records the synchronization failure;
- waits for the completed invocation, then runs the normal Git workflow;
- commits any completed downloads using a partial-run commit message;
- attempts one Healthchecks.io failure ping; and
- returns the original nonzero synchronization status when Git processing
  succeeds, even if the failure ping also fails.

If the failed synchronization produced no repository changes, the Git workflow
creates no empty commit. A successful partial-data commit preserves completed
downloads but does not convert the synchronization or overall wrapper result
to success.

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

## Git preflight and post-synchronization behavior

After sending `/start` but before querying the `servercopy` version or starting
synchronization, the wrapper requires `$MERMAID/servers` to be the exact root of
a completely clean Git working tree. It runs the legacy-compatible
`git status --porcelain`, which reports staged changes, unstaged tracked
changes, tracked deletions, and untracked files while omitting ignored files.
If any changes are present, the wrapper prints the status output and directs
the operator to inspect the changes and commit legitimate synchronization
results. It then sends `/fail` and exits nonzero without running `servercopy`,
staging files, or creating a commit.
Failure to inspect the repository follows the same monitored failure path and
includes captured Git stderr when available.

After every completed `servercopy` invocation, regardless of its exit status,
the wrapper again verifies that `$MERMAID/servers` is the exact root of a Git
working tree. It then checks the entire index before staging anything.

If the index already contains staged changes, the wrapper refuses to run
`git add` or `git commit`, sends the failure ping, and exits nonzero. This
prevents an unattended run from committing work staged by a person or another
process.

With a clean index, the wrapper runs:

`git add -A` with `$MERMAID/servers` as its working directory.

If the index is still empty, it prints a concise no-changes message and creates
no empty commit. Otherwise a successful synchronization creates a commit such
as:

```text
servercopy [cron]: 2026-07-23T22:30:00Z [servercopy=2.2.2 servercopy_cron=2.5.0]
```

A failed synchronization that produced changes instead creates:

```text
servercopy [cron partial]: 2026-07-23T22:30:00Z [servercopy=2.2.2 servercopy_cron=2.5.0]
```

The timestamp is timezone-aware UTC, and the two version fields identify the
independently versioned synchronization engine and cron wrapper used for the
run. After Git processing, the wrapper determines the overall outcome
independently: synchronization and Git must both succeed before it sends the
success ping and exits zero. A synchronization or Git failure sends `/fail`;
when both fail, both are reported. The wrapper never pushes.

A Git worktree check, index inspection, staging, or commit failure is reported
to stderr, followed by an attempted failure ping and a nonzero exit. The wrapper
does not reset the index, remove lock files, roll back files, or otherwise
attempt automatic recovery. A success-ping failure after completed Git work
also exits nonzero but does not attempt a rollback or send `/fail`.

## Production schedule and monitoring

Frisius runs the wrapper at 07:30, 15:30, and 23:30 in the host's local
timezone. The canonical crontab is maintained in
[`frisius_installation.md`](frisius_installation.md); it invokes the wrapper
with the explicit Miniforge interpreter and appends launcher output to the
outer cron log.

The cron command needs no monitoring environment variables because the wrapper
reads its repository-local ignored UUID file. The outer cron log is not a
replacement for the wrapper's promptly flushed, per-invocation workflow logs.

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
- Missing `MERMAID`: nonzero with direct stderr output and no log because the
  configured log location cannot be resolved.
- Lock setup failure, lock acquisition failure, or overlap refusal: nonzero and
  logged, with no monitoring ping, synchronization, or Git action.
- Missing, unreadable, empty, or invalid UUID file: nonzero, with no monitoring
  ping, synchronization, or Git action; the failure is recorded in the
  invocation log.
- Start-ping failure: nonzero, with no synchronization or Git action.
- `servercopy --version` execution failure or malformed output: nonzero after
  one failure-ping attempt, with no synchronization or Git action.
- Synchronization failure with successful Git processing: the original nonzero
  `servercopy` status after committing any partial changes (or reporting no
  changes) and attempting one failure ping.
- Git validation, inspection, staging, or commit failure: nonzero after one
  failure-ping attempt and with no automatic recovery; any simultaneous
  synchronization failure is also reported.
- Successful synchronization with no changes: zero after the success ping.
- Successful synchronization and commit: zero after the success ping.
- Success-ping failure after otherwise successful work: nonzero, with completed
  Git work left intact and no failure ping.
- Failure-ping failure: the original workflow failure status, with the
  secondary monitoring error reported generically.

## Recovery

Always begin with the timestamped workflow log for the failed invocation. If no
workflow log exists, begin with the outer cron log.

### Dirty repository or interrupted synchronization

Inspect the servers repository before changing it:

```sh
git -C /home/jdsimon/mermaid/servers status
git -C /home/jdsimon/mermaid/servers diff
```

An interrupted synchronization, or a Git failure after synchronization, may
leave legitimate downloaded files uncommitted. Inspect those files and commit
valid synchronization results before rerunning the wrapper. Do not delete or
stash legitimate downloads merely to satisfy the clean-repository preflight.

If files are invalid or unrelated to synchronization, resolve them deliberately
according to their provenance. The wrapper performs no automatic reset,
deletion, or rollback.

### Active lock

An overlap refusal usually means another wrapper invocation still owns
`/home/jdsimon/mermaid/logs/servercopy_cron.lock`. Check for the active process
and its current workflow log, then wait for it to finish. The lock is advisory
and contains no PID; it is released automatically when the process exits. Do
not delete the lock file as a recovery step.

### Healthchecks.io failure

A start-ping failure prevents synchronization. Correct DNS, outbound HTTPS, or
Healthchecks.io configuration and rerun manually.

A failure ping that itself fails does not replace the underlying workflow
status. A success-ping failure occurs after synchronization and Git work have
completed; inspect the workflow log and repository before rerunning, because a
commit may already exist.

### Remote synchronization failure

Use the timestamped workflow log and the nested `servercopy` diagnostics to
identify the logical user and failing stage. If Git processing succeeded, any
partial downloads were preserved in a `[cron partial]` commit even though the
wrapper still reported failure.

A diagnostic such as:

```text
mirror: Access failed: Permission denied (.buoy_monitoring.sh.nohup.20260704122043)
```

means the authenticated account could list a path that the remote server would
not allow it to read. `servercopy` does not and must not alter remote
permissions, so the inaccessible path remains absent locally. Investigate
repeated or operationally important cases with the server owner; do not add
source-specific exclusions merely to hide the failure.

Correct the remote permission, network, or credential problem when appropriate,
inspect the partial commit (or recover from any reported Git failure), and
rerun manually. A nonzero `lftp` status remains a failed run even when most of
the eligible top-level files were mirrored and committed successfully.

### Git failure

Inspect both the workflow log and:

```sh
git -C /home/jdsimon/mermaid/servers status
```

Determine whether staging or a commit completed before the failure. Preserve
valid synchronized data, repair the specific Git problem, and commit or clean
the repository deliberately. The wrapper never resets the index, rewrites
history, or pushes.

### Cron startup failure

If no timestamped workflow log was created, inspect:

```text
/home/jdsimon/mermaid/logs/servercopy_cron_cron.log
```

Verify the installed crontab, the explicit Miniforge interpreter, executable
repository paths, `MERMAID`, permissions, and available disk space. After
correcting the startup problem, run the exact cron command manually and confirm
that a timestamped workflow log and Healthchecks.io lifecycle appear.
