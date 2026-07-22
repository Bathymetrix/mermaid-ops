# mermaid-ops

Operational scripts for MERMAID data and server workflows.

The canonical server-copy workflow is the directly executable `servercopy`
Python script. It mirrors configured remote content into per-user directories,
records each attempt in an append-only CSV ledger, and writes combined
stdout/stderr transcripts for cron diagnostics. It does not delete local mirror
files, commit copied data to Git, convert VIT files, or run exports.

`servercopy_rudics.zsh` remains temporarily available for rollout comparison.
Remove it after the combined workflow completes a successful RUDICS check,
remote preview, normal mirror, and output review.

## Configuration

Non-secret source definitions are stored in the tracked file:

```text
servercopy_sources.csv
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

For the initial migration, carry the existing RUDICS `login,password` rows into
the new credential registry unchanged, then add the one shared Taal login. This
is an operator-managed credential step; `servercopy` does not import, rewrite,
or print credentials.

## Filename selection

Every source uses one authoritative suffix tuple hardcoded in `servercopy`:

```text
.MER .LOG .BIN .cmd .out .vit .S41 .S61
```

Case is significant. For each source, one authenticated lftp session runs one
command per suffix, in the listed order. The remote pattern stays in `--file`
and the canonical `<output>/<user>/` destination stays in
`--target-directory`:

```text
mirror <options> --file=<remote_root>/*.MER --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.LOG --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.BIN --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.cmd --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.out --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.vit --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.S41 --target-directory=<output>/<user>
mirror <options> --file=<remote_root>/*.S61 --target-directory=<output>/<user>
```

`cmd:fail-exit yes` stops the session at a failed suffix, and the marker
immediately before each command identifies the active suffix in output and
failure reports.

Files outside the hardcoded suffix tuple, including operational dotfiles,
tools, and backups, are not selected. Remote files removed from a source do not
delete local files.

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
was also rejected after testing. See
[`SERVERCOPY_COMPLETE_MIRROR_EXPERIMENT.md`](SERVERCOPY_COMPLETE_MIRROR_EXPERIMENT.md)
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

Taal uses explicit FTPS on port 21. TLS is required, data and directory-listing
connections are protected, and the server certificate is verified.

FileZilla has independently authenticated to Taal, listed remote directories,
and copied files. It currently reports 5,835 files and 155,451,811 bytes in the
Kobe root. The remaining investigation is therefore scoped to lftp/Taal FTPS
interoperability rather than general reachability, credentials, or remote-root
validity.

## Usage

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
Redacted `lftp` lines are streamed to both destinations as they arrive. If
`lftp` is silent for 30 seconds, `servercopy` prints a short `still-running`
line with elapsed and silent time, including the active suffix once its marker
has appeared. Each suffix-specific mirror prints a marker before it starts.

Check mode creates no directories, ledger, lock, or transcript. Dry-run writes
a transcript but no ledger rows. Normal runs write both.

An individual source failure does not prevent later sources from running. The
script prints the source result and lftp exit status immediately, then prints a
compact final failure summary containing diagnostic lines rather than replaying
all transfer output. It exits nonzero if any selected source fails. Successful
all-source runs exit zero. Missing or malformed local configuration also exits
nonzero before transfer attempts begin.

An advisory lock at `<output>/_runs/servercopy.lock` prevents overlapping normal
and dry-run invocations. This is intended for unattended cron use.

## Cron

Cron must provide `MERMAID` and a `PATH` containing Python 3.14 and `lftp`. For
the current Homebrew installation, the command environment can use:

```sh
MERMAID=/Users/jdsimon/mermaid
PATH=/opt/homebrew/bin:/usr/bin:/bin
/Users/jdsimon/programs/mermaid-ops/servercopy \
  --output /Users/jdsimon/mermaid/servers
```

Keep cron's own mail or redirection enabled as an additional alerting channel.
The `_runs` transcript remains the detailed diagnostic record.

## Requirements

- Python 3.14
- `lftp`
- `MERMAID` set in the environment
- Readable `servercopy_sources.csv` beside the executable
- Readable protected credentials at the configured path
- Writable output root, defaulting to `~/mermaid/servers/`

## Tests

The test suite checks the hardcoded suffix tuple, recovered lftp command shape,
output streaming, redaction, heartbeats, and silence termination:

```sh
python3.14 -m unittest discover -s tests -v
```

The tests use fake credentials and mocked lftp processes. They do not contact
remote servers.

## Safety notes

- Check the source registry and destination mapping before the first run.
- Run `--check`, then `--dry-run`, before the first normal sequential mirror.
- Treat `--dry-run` as an authenticated remote operation.
- Normal mirrors may modify files beneath `<output>/<user>/`.
- Remote deletions do not remove local files.
- Credentials, generated server data, and local sync output must not be
  committed.
