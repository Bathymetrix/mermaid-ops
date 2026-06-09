# mermaid-ops

Operational scripts for MERMAID data and server workflows.

These scripts are intentionally small and direct. They are meant for repeatable
MERMAID operations where destination paths, credentials files, and server
behavior should be easy to inspect before running.

## Scripts

### `servercopy_rudics.zsh`

Mirror accessible content from RUDICS SFTP accounts into per-user local server
directories. This workflow skips remote `backups/` directories and files ending
in `~`, does not delete local files when remote files disappear, and does not
preserve remote Unix permission bits.

Credentials are read from:

```sh
$MERMAID/passwords/rudics.csv
```

The credentials file is intentionally simple unquoted CSV with no header row and
one `user,pass` pair per line. Blank lines and lines beginning with `#` are
skipped. No quoted CSV parsing is supported. Usernames and passwords that
contain commas, quotes, backslashes, or whitespace are not supported.

Usernames are used as a single local path component under:

```sh
$MERMAID/servers/<user>/
```

Empty usernames, `.`, `..`, and usernames containing `/` are rejected.

Run:

```sh
./servercopy_rudics.zsh
```

Check local configuration without contacting RUDICS:

```sh
./servercopy_rudics.zsh --check
./servercopy_rudics.zsh -c
```

Preview remote mirror operations through `lftp`:

```sh
./servercopy_rudics.zsh --dry-run
```

Process only selected configured users:

```sh
./servercopy_rudics.zsh --user foo,bar
./servercopy_rudics.zsh --user=foo,bar
./servercopy_rudics.zsh -u foo,bar
```

User filtering accepts a comma-separated list of usernames and trims whitespace
around names. It only changes which configured users from
`$MERMAID/passwords/rudics.csv` are processed.

Check selected users without contacting remote servers:

```sh
./servercopy_rudics.zsh --check --user foo,bar
./servercopy_rudics.zsh -c -u foo,bar
```

Preview selected users through `lftp`:

```sh
./servercopy_rudics.zsh --dry-run --user foo,bar
```

Show help or version:

```sh
./servercopy_rudics.zsh --help
./servercopy_rudics.zsh -h
./servercopy_rudics.zsh --version
./servercopy_rudics.zsh -v
```

The workflow mirrors accessible remote content from each account into:

```sh
$MERMAID/servers/<user>/
```

Excluded remote content:

```text
backups/
*~
```

The workflow does not delete local files that are absent remotely and keeps
incremental mirror behavior with `--continue`. Remote Unix permission bits are
intentionally not preserved; this is an operational mirror, not a
permission-preserving filesystem archive.

After changing the policy, run:

```sh
./servercopy_rudics.zsh --dry-run
```

before running a normal mirror.

## Run ledger

The script maintains a single append-only UTC run ledger under:

```sh
$MERMAID/servers/_runs/
```

Ledger file:

```sh
$MERMAID/servers/_runs/servercopy_rudics_runs.csv
```

Columns:

```csv
user,result,start,end,ver
```

The `ver` column records the current `SERVERCOPY_RUDICS_VERSION` value for each
appended row. This script-level version is lightweight operational provenance,
not a package release system.

Successful rows populate `end` with the UTC finish time. Failed rows
intentionally leave `end` blank.

Allowed result values are `success` and `failure`. `failure` is intentionally
broad for now: login/authentication failures, DNS failures, connection failures,
interrupted transfers, permission failures, local filesystem failures, and other
per-user mirror failures all use `failure`.

## Transcript logs

Each normal or dry-run invocation writes one raw combined stdout/stderr
transcript log under:

```sh
$MERMAID/servers/_runs/
```

Transcript filenames use the invocation UTC timestamp:

```sh
servercopy_rudics_<UTC>.log
```

These logs are raw operational/debug evidence only. They are not parsed or used
to classify failures. Check mode does not create transcript logs.

## Check vs dry-run

`--check` / `-c` performs local validation and prints the intended user, remote
endpoint, and destination for each configured account. Check mode does not:
- contact remote servers
- authenticate
- transfer files
- create directories or files
- append to `_runs`
- create transcript logs

When combined with `--user`, output is limited to selected configured users.

`--dry-run` contacts and authenticates to RUDICS for each selected account and
lets `lftp mirror --dry-run` print the operations it would perform. Dry-run mode
transfers nothing, writes a transcript log, and does not append to `_runs`.

`--dry-run` is not offline. Use `--check` or `-c` for offline/local validation.

## Requirements

- `zsh`
- `lftp`
- `MERMAID` set in the environment
- Unified RUDICS credentials CSV at `$MERMAID/passwords/rudics.csv`
- Optional `SFTP_PORT` override must be numeric

## Safety Notes

- Scripts may touch live MERMAID server data.
- Credentials files should never be committed.
- Check destination paths before running a script for the first time.
- `servercopy_rudics.zsh` mirrors accessible remote content into
  `$MERMAID/servers/<user>/`.
- Remote `backups/` directories and files ending in `~` are skipped.
- Remote deletions do not delete local files.
- The run ledger is append-only and is not rewritten or truncated.
