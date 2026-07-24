# mermaid-ops

Operational scripts for MERMAID data and server workflows.

The canonical synchronization engine is the directly executable `servercopy`
Python script. It mirrors configured remote content into per-user directories,
records each attempt in an append-only CSV ledger, and writes combined
stdout/stderr transcripts. It does not delete local mirror files, commit copied
data to Git, convert VIT files, or run exports.

Scheduled runs use the directly executable `servercopy_cron` Python wrapper. It
prevents overlapping wrapper runs, invokes `servercopy`, sends a macOS Messages
notification only when synchronization fails, and stages and commits the
separate `$MERMAID/servers` repository only after `servercopy` exits
successfully. It never pushes.

`servercopy_rudics.zsh` remains temporarily available for rollout comparison.
Remove it after the combined workflow completes a successful RUDICS check,
remote preview, normal mirror, and output review.

## Configuration

Non-secret source definitions are stored in the tracked file:

```text
data/servercopy_sources.csv
```

Columns:

```csv
user,login,protocol,host,port,remote_root
```

- `user` is the logical server user and local destination name.
- `login` is the authentication username in the protected credential registry.
- `protocol` is `sftp` or `ftps-explicit`.
- `host` and `port` identify the remote endpoint.
- `remote_root` is the directory or file-group root mirrored for the user.

The logical user and authentication login may differ. This allows `eso` and
`kobeuni` to use one shared Taal login while retaining distinct destinations:

```text
~/mermaid/servers/eso/
~/mermaid/servers/kobeuni/
```

The output root defaults to `~/mermaid/servers/`. Override it with
`-o DIR` or `--output DIR`; every mirror, ledger, transcript, and lock is then
written beneath that root.

The ESO and Kobe rows share the `automaid` authentication login.

## Credentials

Credentials are read at runtime from:

```text
$MERMAID/passwords/servercopy_credentials.csv
```

The file is intentionally simple unquoted CSV with no header row and one
`login,password` pair per line:

```csv
s_m0057,example-not-a-real-password
automaid,another-example-not-a-real-password
```

Blank lines and lines beginning with `#` are skipped. Logins and passwords that
contain commas, quotes, backslashes, or whitespace are not supported. The
credential file must not be committed, printed, copied into transcripts, or
passed to `lftp` as a process argument.

Multiple source rows may refer to the same login, so shared passwords appear
only once in the protected file.

A configured source whose login is absent from the credential registry is
skipped with a warning and included in the final summary. Other configured
sources continue normally. If no selected source has credentials, `servercopy`
exits nonzero without attempting a remote operation.

For the initial migration, carry the existing RUDICS `login,password` rows into
the new credential registry unchanged, then add the one shared Taal login. This
is an operator-managed credential step; `servercopy` does not import, rewrite,
or print credentials.

## Filename selection

Every source uses one authoritative fixed suffix tuple hardcoded in
`servercopy`:

```text
.MER .LOG .BIN .cmd .out .vit .S41 .S61
```

Case is significant. Before mirroring, a separate authenticated lftp operation
runs `cls -1` once against the configured remote root. `servercopy` parses that
remote directory listing locally for filenames ending in exactly three decimal
digits, such as `.000` or `.001`. Duplicate numbered suffixes are reduced to
one, sorted numerically, and validated as a contiguous sequence beginning with
`.000`. A source with no numbered suffixes simply retains the fixed plan above.

This discovery is attempted automatically for every source. The current TAAL
FTPS accounts typically expose no numbered-suffix files, so discovery for
`eso` and `kobeuni` normally reports `none`. Historical archive notes indicate
that TAAL `.000`-style files were supplied separately while access to them
through the FTPS endpoint was unavailable. Their absence from a modern TAAL
mirror is therefore expected and does not indicate a mirror failure.

The historical Kobe archive is the working tree at
`~/mermaid/server_jamstec/`. Despite that legacy local name, it contains files
previously downloaded with FileZilla from the TAAL `kobeuni` user; it is not an
output of the CLS JAMSTEC accounts. When audited on 2026-07-23, the archive
working tree contained 7,662 files, including 300 numbered-suffix files
(`.000`, `.001`, and `.002`). The current `~/mermaid/servers/kobeuni/` live
mirror contained 5,843 files and no numbered-suffix files. Preserve the
historical archive separately: the current TAAL mirror supersedes the old live
transfer arrangement, but it cannot reproduce files that TAAL never exposed
through FTPS.

Numbered-suffix discovery is intentionally retained. If those files become
visible on TAAL or any other configured server, `servercopy` will discover and
mirror them automatically without a code or configuration change.

The fixed suffixes followed by any discovered numbered suffixes form the
mirror plan. A second authenticated lftp session runs one ordinary mirror step
per suffix, in that order. The remote pattern stays in `--file` and the
canonical `<output>/<user>/` destination stays in `--target-directory`:

```text
mirror <options> --file=<remote_root>/*.MER --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.LOG --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.BIN --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.cmd --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.out --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.vit --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.S41 --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.S61 --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.000 --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.001 --target-directory=<output>/<user>
```

The numbered examples appear only when those suffixes exist remotely. A gap,
such as `.000`, `.001`, and `.003`, fails discovery rather than silently
omitting `.003`. Discovery applies uniformly to SFTP and explicit-FTPS sources,
uses the same bounded connection and security settings as mirroring, and does
not print the complete remote inventory during normal operation.

`cmd:fail-exit yes` stops the session at a failed suffix, and the marker
immediately before each command identifies the active suffix in output and
failure reports.

Files outside the fixed suffix tuple and discovered numbered suffixes, including
operational dotfiles, tools, and backups, are not selected. Remote files removed
from a source do not delete local files.

### Why this command shape is deliberate

The version 1.3.1 production run on 2026-07-17 successfully fetched `.MER`
files with `--file=<remote_root>/*.MER` and
`--target-directory=<output>/<user>`. ESO completed all of its configured
suffix passes. Kobeuni fetched all 2,864 `.MER` files before an error in that
first pass caused `cmd:fail-exit` to skip the later commands.

Later attempts to generalize suffix handling introduced forms that could exit
successfully without downloading anything. A zero exit status established
neither that a remote pattern matched files nor that files were transferred.
The final implementation therefore repeats the exact proven `.MER` operation
for each suffix. The hardcoded tuple is intentional because the set is small
and operationally fixed. Runtime suffix files, combined include/exclude
filters, alternate mirror forms, and temporary listing diagnostics increased
complexity and obscured the working behavior.

A later attempt to replace the suffix passes with one complete recursive mirror
was also rejected after testing. Numbered-suffix discovery uses one lightweight
directory listing and then preserves the proven per-suffix mirror shape; it
does not use a whole-tree mirror to inspect the source. See
[`servercopy_complete_mirror_experiment.md`](docs/servercopy_complete_mirror_experiment.md)
for the engineering decision and observed evidence.

On `kobeuni`, silent periods of five minutes or more before lftp begins
emitting transfer output are normal. Such silence is not by itself evidence of
failure or of any particular internal lftp operation. The silence watchdog
therefore remains 900 seconds.

Individual network protocol waits use a 30-second timeout and receive at most
two sequential attempts. A transfer with no progress for five minutes also
times out. These finite limits replace lftp's very large retry and
transfer-timeout defaults while still allowing one retry after a transient
research-server failure. As a final bound, `servercopy` terminates lftp and
records a failure if lftp itself produces no output for 15 minutes.

RUDICS uses SFTP on the CLS-preferred endpoint
`rudics.thorium.cls.fr`. The legacy name `iridium-rudics.cls.fr` was checked
without authentication on 2026-07-16; both names resolved through the same
canonical CLS hostname and presented identical RSA and ECDSA SSH host keys.
Use the preferred name and recheck DNS and host identity if CLS announces a
migration.

The retired `servercopy_princeton.zsh` name referred to an old aggregate
workflow, not to a distinct Princeton host. That script also connected to
`rudics.thorium.cls.fr` and merged all of its accounts into
`$MERMAID/server_princeton/`. The canonical workflow supersedes that local
layout by keeping each logical source in `<output>/<user>/`.

Taal uses explicit FTPS on port 21. TLS is required, data and directory-listing
connections are protected, and the server certificate is verified.

FileZilla has independently authenticated to Taal, listed remote directories,
and copied files. It currently reports 5,835 files and 155,451,811 bytes in the
Kobe root. The remaining investigation is therefore scoped to lftp/Taal FTPS
interoperability rather than general reachability, credentials, or remote-root
validity.

## Usage

Use `servercopy` directly for manual synchronization, checks, and authenticated
previews. Use `servercopy_cron` for the scheduled synchronization-and-commit
workflow documented below.

Show the wrapper's independent operational version without starting a run:

```sh
./servercopy_cron --version
./servercopy_cron -v
```

Normal mirror of all configured users:

```sh
./servercopy
```

Validate local configuration without contacting a remote or creating files:

```sh
./servercopy --check
./servercopy -c
```

Authenticate and preview remote mirror operations without transferring files:

```sh
./servercopy --dry-run
```

Process only selected logical users:

```sh
./servercopy --user s_m0057,eso
./servercopy --user=s_m0057,eso
./servercopy -u s_m0057,eso
```

Use a different server output root:

```sh
./servercopy --output /path/to/servers
./servercopy -o /path/to/servers
```

User filtering and output selection work with normal, check, and dry-run modes.
Show help or the operational version with:

```sh
./servercopy --help
./servercopy --version
```

`SFTP_PORT` may override the configured port for all SFTP sources and must be a
number from 1 through 65535. It does not affect FTPS sources.

## Run ledger

Normal runs append one row per attempted logical user to:

```text
<output>/_runs/servercopy_runs.csv
```

The ledger retains the existing format:

```csv
user,result,start,end,ver
```

Allowed results are `success` and `failure`. Successful rows include UTC start
and end times. Failed rows intentionally leave `end` empty. `ver` records the
`servercopy` operational version.

Existing `servercopy_rudics_runs.csv` and RUDICS transcript logs are left
untouched. The combined workflow starts a new ledger rather than rewriting or
renaming historical output.

## Transcript logs and failures

Every normal or dry-run invocation writes one combined stdout/stderr log:

```text
<output>/_runs/servercopy_<UTC>.log
```

Credential-bearing URL user information emitted by `lftp --dry-run` is replaced
with `[REDACTED]` before output is written to the terminal or transcript.
Redacted mirror output lines are streamed to both destinations as they arrive.
The discovery inventory is parsed without being printed; only the discovery
step and its resulting suffix list (or `none`) are reported. If `lftp` is silent
for 30 seconds, `servercopy` prints a short `still-running` line with elapsed
and silent time, including the active suffix once its marker has appeared. Each
suffix-specific mirror prints a marker before it starts.

Check mode creates no directories, ledger, lock, or transcript. Dry-run writes
a transcript but no ledger rows. Normal runs write both.

An individual source failure does not prevent later sources from running. The
script prints the source result and lftp exit status immediately, then prints a
compact final failure summary containing diagnostic lines rather than replaying
all transfer output. It exits nonzero if any selected source fails. Successful
runs exit zero even when sources without credentials were skipped. Malformed
local configuration still exits nonzero before transfer attempts begin; a run
with no runnable sources also exits nonzero.

An advisory lock at `<output>/_runs/servercopy.lock` prevents overlapping normal
and dry-run `servercopy` invocations. The scheduled wrapper also holds
`$MERMAID/logs/servercopy_cron.lock` across synchronization and Git handling. An
overlapping wrapper exits nonzero without running synchronization, Git, or
Messages.

## Cron

Cron must invoke `servercopy_cron`, not `servercopy` directly. The wrapper
requires `MERMAID`, derives the destination as `$MERMAID/servers`, and passes
servercopy output through live to cron's redirection. Create the log directory
once before installing the entry because the shell opens the log before the
wrapper starts:

```sh
mkdir -p /Users/jdsimon/mermaid/logs
```

The scheduled command is:

```cron
PATH=/opt/homebrew/bin:/usr/bin:/bin
MERMAID=/Users/jdsimon/mermaid
30 7,15,23 * * * /Users/jdsimon/programs/mermaid-ops/servercopy_cron >> /Users/jdsimon/mermaid/logs/servercopy_cron.log 2>&1
```

Failure recipients are stored locally in the Git-ignored private file
`data/notification_recipients.txt`, one E.164 number per line. Blank lines and
lines beginning with `#` are ignored. For example, using an intentionally
fictitious number:

```text
# Private local notification recipients
+12025550123
```

The file contains private phone numbers and must remain untracked. Its contents
must remain absent from logs, documentation, and test fixtures. Notifications
use macOS Messages through `osascript`; Messages must be configured for the
cron user and macOS may require Automation permission.

If synchronization fails, partial downloads remain uncommitted, notification
is attempted, and no Git command is run. The next scheduled run proceeds
normally. After `servercopy` exits successfully, the wrapper refuses a
pre-staged index, runs `git add -A`, creates a UTC-dated `servercopy [cron]`
commit only when changes exist, and does not push. Git failures exit nonzero
without sending the synchronization-failure text or attempting a reset.
The wrapper follows the existing `servercopy` exit contract, including its
documented missing-credential skip behavior, and does not parse transfer output
to redefine success. Do not run `servercopy` manually while a scheduled wrapper
may be in its synchronization-and-Git cycle.

See
[`docs/servercopy_cron_workflow.md`](docs/servercopy_cron_workflow.md)
for the complete policy and exit behavior.

## Requirements

- Python 3.14
- `lftp`
- Git
- macOS Messages and `osascript` for failure notifications
- `MERMAID` set in the environment
- Readable `data/servercopy_sources.csv`
- Readable protected credentials at the configured path
- Writable output root, defaulting to `~/mermaid/servers/`
- A Git working tree rooted at `$MERMAID/servers` for scheduled runs
- A private, untracked `data/notification_recipients.txt` for failure texts

## Tests

The test suite checks numbered-suffix discovery, parsing and contiguity,
the hardcoded fixed suffix tuple, recovered lftp command shape, generic SFTP and
FTPS behavior, dry-run generation, output suppression and redaction,
heartbeats, silence termination, notification privacy, wrapper locking, and
conservative Git policy:

```sh
python3.14 -m unittest discover -s tests -v
```

The tests use synthetic data and mocked lftp, Messages, servercopy, and Git
processes. They do not contact remote servers, send notifications, inspect the
private recipient file, or modify the live servers repository.

## Safety notes

- Check the source registry and destination mapping before the first run.
- Run `--check`, then `--dry-run`, before the first normal sequential mirror.
- Treat `--dry-run` as an authenticated remote operation.
- Normal mirrors may modify files beneath `<output>/<user>/`.
- Remote deletions do not remove local files.
- Credentials and private notification recipients must not be committed.
- Mirrored data is committed only in the separate `$MERMAID/servers` repository
  by `servercopy_cron`, and only after `servercopy` exits successfully.
- Failed or partial synchronization output remains uncommitted.
- The wrapper does not push.
