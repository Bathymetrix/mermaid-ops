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

Case is significant. For each source, one authenticated lftp session changes
to `<output>/<user>/` and runs one command per suffix, in the listed order:

```text
mirror -c -f <remote_root>/*.MER
mirror -c -f <remote_root>/*.LOG
mirror -c -f <remote_root>/*.BIN
mirror -c -f <remote_root>/*.cmd
mirror -c -f <remote_root>/*.out
mirror -c -f <remote_root>/*.vit
mirror -c -f <remote_root>/*.S41
mirror -c -f <remote_root>/*.S61
```

The installed lftp 4.9.2 manual defines `-c` as continuing a mirror job when
possible and `-f FILE` as mirroring one file or globbed group, with
`/path/to/*.txt` as its example. Thus each generated command has the same
semantics as the proven historical invocation. `cmd:fail-exit yes` stops the
session at a failed suffix, and the marker immediately before each command
identifies the active suffix in output and failure reports.

Files outside the hardcoded suffix tuple, including operational dotfiles,
tools, and backups, are not selected. Remote files removed from a source do not
delete local files.

### Why the mirror commands are sequential

The older external implementation used explicit commands such as
`mirror -c -f kobeuni/*.MER`, `mirror -c -f kobeuni/*.LOG`, and so on. A newer
implementation tried to generalize the fixed selection by loading suffixes
from a tracked text file, generating repeated `--include-glob` options for one
combined nonrecursive mirror, and adding listing diagnostics and TLS-listing
experiments.

The existing Kobeuni destination contained only `.MER` files because the
historical sequential run copied that first group and then failed before later
suffix commands ran. This was initially mistaken for evidence that the glob
filters were incorrect. Live diagnostics later established that:

- protected `cls` listing worked;
- ESO returned 1,102 filenames in about five seconds;
- lftp mirror could enumerate and select files;
- a minimal one-suffix mirror took about 117 seconds before selecting its first
  file; and
- the full eight-suffix combined mirror took about 204 seconds before selecting
  its first file.

The combined mirror was not categorically broken, but its slow, opaque startup
made diagnosis and operation unnecessarily difficult. The silence watchdog was
increased from 300 to 900 seconds because lftp can legitimately spend several
minutes gathering file information.

The project returned to sequential `mirror -c -f` commands because they match
the known working external script, expose each suffix operationally, associate
failures with a suffix, and are easier to understand and troubleshoot. The
small fixed suffix set does not justify runtime configuration. The attempt to
be clever with a generic allowlist and one combined mirror added complexity
without delivering enough operational value.

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

Compare protected and unprotected FTPS directory listings without mirroring:

```sh
./servercopy --user eso --diagnose-listing --listing-tls protected
./servercopy --user eso --diagnose-listing --listing-tls unprotected
```

`--diagnose-listing` requires exactly one explicit-FTPS user. It runs no mirror
or transfer command and creates no destination, ledger, transcript, or lock.
Output is redacted and streamed to the terminal under the existing 15-minute
silence watchdog. The unprotected comparison exposes listing metadata, but
`ftp:ssl-protect-data yes` remains enabled.

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
Listing diagnostics require one user and ignore the output root. Show help or
the operational version with:

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
a transcript but no ledger rows. Listing diagnostics create none of these and
stream directly to the terminal. Normal runs write both.

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

The test suite checks the hardcoded suffix tuple, generated lftp scripts, listing
diagnostics, output streaming, redaction, heartbeats, and silence termination:

```sh
python3.14 -m unittest discover -s tests -v
```

The tests use fake credentials and mocked lftp processes. They do not contact
remote servers.

## Safety notes

- Check the source registry and destination mapping before the first run.
- Run `--check`, then `--dry-run`, before the first normal sequential mirror.
- Treat `--dry-run` and `--diagnose-listing` as authenticated remote operations.
- Normal mirrors may modify files beneath `<output>/<user>/`.
- Remote deletions do not remove local files.
- Credentials, generated server data, and local sync output must not be
  committed.
