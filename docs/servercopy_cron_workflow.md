# Servercopy Cron Workflow

## Overview

`servercopy` remains responsible only for synchronization. The cron job invokes
the directly executable Python 3.14 wrapper `servercopy_cron`, which adds the
small amount of operational policy needed around a scheduled run:

```text
cron
  |
  v
servercopy_cron
  |
  +-- servercopy failed --> Messages notification, no Git commands
  |
  `-- servercopy exited successfully
        |
        +-- staged index already nonempty --> refuse
        |
        `-- git add -A
              |
              +-- no staged changes --> exit successfully
              |
              `-- commit, but do not push
```

The wrapper requires a nonempty `MERMAID` environment variable. It derives all
paths without a separate `MERMAID_OPS` setting:

```text
servers repository  $MERMAID/servers
lock                 $MERMAID/logs/servercopy_cron.lock
servercopy command   <mermaid-ops repository>/servercopy
recipient file       <mermaid-ops repository>/data/notification_recipients.txt
```

The repository-local paths are resolved from `servercopy_cron` itself.
`servercopy_cron --version` (or `-v`) reports the wrapper's independent
operational version without requiring `MERMAID` or starting a run.
`SERVERCOPY_CRON_VERSION` should be incremented whenever CLI, locking,
notification, or Git behavior changes meaningfully.

## Locking and synchronization

The wrapper takes a nonblocking advisory lock before starting `servercopy` and
holds it through any Git work. If another wrapper owns the lock, the new
invocation exits nonzero without running `servercopy`, Git, or Messages. The
lock contains no PID and requires no stale-lock cleanup.

`servercopy` is invoked with:

```text
--output $MERMAID/servers
```

Its stdout and stderr are inherited rather than captured, so the cron log is
updated while the long-running synchronization is in progress.

If `servercopy` returns nonzero, the wrapper:

- attempts one brief text notification for every usable configured recipient;
- runs no Git command, including read-only Git inspection;
- leaves partial downloads in the working tree without staging, reverting, or
  deleting them; and
- returns the nonzero synchronization status.

The next scheduled invocation runs normally. A later successful synchronization
can finish the partial downloads and commit the resulting state.

The wrapper follows `servercopy`'s existing exit-status contract; it does not
parse or reinterpret synchronization output. In particular, `servercopy`
currently returns zero when at least one source runs successfully and other
sources are skipped for missing credentials. That existing behavior is
unchanged, so credential configuration must be maintained as an operational
prerequisite.

The outer lock coordinates `servercopy_cron` invocations. Do not launch
`servercopy` manually while the scheduled wrapper may be running: the direct
command's internal lock covers synchronization, but it does not cover the
wrapper's later Git window.

## Failure notifications

Recipients are stored one per line in:

```text
data/notification_recipients.txt
```

Blank lines and lines beginning with `#` are ignored. Other usable lines must
be E.164 numbers with a leading `+`, for example the intentionally fictitious
number:

```text
# Private local notification recipients
+12025550123
```

This file contains private information, is Git-ignored, and must remain
untracked. Do not print it, include it in logs or fixtures, or copy it into
documentation.

Notifications use `osascript` to ask macOS Messages to send through its
iMessage service. Delivery as iMessage or SMS depends on the host's Messages
configuration. The sending user must be signed in to Messages, and macOS may
require Automation permission for the cron execution context.

If the file is missing, unreadable, empty, or has no usable recipients, the
wrapper reports a generic notification error without exposing recipient data.
An individual Messages failure is also reported generically. Notification
failures are secondary: there are no retries or alternative services, the
synchronization remains failed, and no Git action follows.

## Git behavior after success

Git is considered only after `servercopy` returns zero. The wrapper first
verifies that `$MERMAID/servers` is the root of a Git working tree. It then
checks the entire index before staging anything.

If the index already contains staged changes, the wrapper refuses to run
`git add` or `git commit` and exits nonzero. This prevents an unattended run
from committing work staged by a person or another process.

With a clean index, the wrapper runs:

```sh
git -C "$MERMAID/servers" add -A
```

If the index is still empty, it prints a concise no-changes message and exits
zero. Otherwise it creates a commit such as:

```text
servercopy [cron]: 2026-07-23T22:30:00Z
```

The timestamp is timezone-aware UTC. The wrapper never pushes.

A Git worktree check, index inspection, staging, or commit failure is reported
to stderr and returns nonzero. Git failures do not trigger the
synchronization-failure notification. The wrapper does not reset the index,
remove lock files, roll back files, or otherwise attempt automatic recovery.

## Crontab

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

This schedule runs at 07:30, 15:30, and 23:30 local time. The redirected log
receives live `servercopy` output plus wrapper diagnostics.

## Exit status summary

- Missing `MERMAID`, lock setup failure, or overlap refusal: nonzero, with no
  synchronization, Git action, or text.
- Synchronization failure: the nonzero `servercopy` status, after notification
  attempts and with no Git commands.
- Git validation, staging, inspection, or commit failure: nonzero, with no
  synchronization-failure text and no automatic recovery.
- Successful synchronization with no changes: zero.
- Successful synchronization and commit: zero.
