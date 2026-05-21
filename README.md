# mermaid-ops

Operational scripts for MERMAID data and server workflows.

These scripts are intentionally small and direct. They are meant for repeatable
MERMAID operations where the destination paths, credentials files, and server
behavior should be easy to inspect before running.

## Scripts

### `servercopy_rudics.zsh`

Mirror RUDICS SFTP accounts into per-user local server directories. This is the
new unified workflow for creating faithful local mirrors of RUDICS accounts for
debugging, historical comparison, reproducibility, and future archival work.

By default, it reads credentials from:

```sh
$MERMAID/passwords/rudics.csv
```

The credentials file has no header row and uses one simple `user,pass` pair per
line. Blank lines and lines beginning with `#` are skipped. Quoted commas in
fields are not supported.

Each account syncs into:

```sh
$MERMAID/servers/<user>/
```

Run:

```sh
./servercopy_rudics.zsh
```

Show help:

```sh
./servercopy_rudics.zsh --help
```

The unified RUDICS workflow is intended to produce canonical, full mirrors. It
does not apply exclude rules, does not prune or filter remote content, and does
not use `lftp mirror --delete`. It keeps incremental mirror behavior with
`--continue` and `--only-newer`.

The script also maintains an append-only UTC run ledger under:

```sh
$MERMAID/servers/_runs/
```

The ledger file is:

```sh
$MERMAID/servers/_runs/servercopy_rudics_runs.csv
```

It records one row per user mirror attempt with these columns:

```csv
run_started_utc,user,status,run_finished_utc
```

Allowed status values are `success` and `failure`. A `failure` is intentionally
broad for now: login/authentication failures, DNS failures, connection failures,
interrupted transfers, permission failures, local filesystem failures, and other
per-user mirror failures all use `failure`. No fine-grained failure typing is
implemented yet.

### `servercopy_princeton.zsh`

Retained legacy workflow for mirroring Princeton RUDICS SFTP accounts into a
local server directory.

By default, it reads credentials from:

```sh
$MERMAID/passwords/princeton.csv
```

and syncs into:

```sh
$MERMAID/server_princeton/
```

Run:

```sh
./servercopy_princeton.zsh
```

Show help:

```sh
./servercopy_princeton.zsh --help
```

### `servercopy_jamstec.zsh`

Retained legacy workflow for mirroring JAMSTEC/KOBE RUDICS SFTP accounts into a
local server directory.

By default, it reads credentials from:

```sh
$MERMAID/passwords/jamstec.csv
```

and syncs into:

```sh
$MERMAID/server_jamstec/
```

Run:

```sh
./servercopy_jamstec.zsh
```

Show help:

```sh
./servercopy_jamstec.zsh --help
```

## Requirements

- `zsh`
- `lftp`
- `MERMAID` set in the environment
- Unified RUDICS credentials CSV at `$MERMAID/passwords/rudics.csv`
- Princeton credentials CSV at `$MERMAID/passwords/princeton.csv`
- JAMSTEC credentials CSV at `$MERMAID/passwords/jamstec.csv`

The unified RUDICS credentials CSV is expected to have no header row and use one
`user,pass` pair per line. Blank lines and lines beginning with `#` are skipped.

The Princeton credentials CSV is expected to use the fourth column for the SFTP
username and the fifth column for the SFTP password. The first two lines are
skipped as headers.

The JAMSTEC credentials CSV is expected to have no header lines and use one
`user,pass` pair per line.

Credential files are expected to use simple comma-separated fields; quoted
commas in fields are not supported.

## Safety Notes

- Scripts may touch live MERMAID server data.
- Credentials files should never be committed.
- Check destination paths before running a script for the first time.
- `servercopy_rudics.zsh` mirrors each remote account into
  `$MERMAID/servers/<user>/`.
- `servercopy_rudics.zsh` is a faithful full-mirror workflow. It intentionally
  has no exclude rules and does not use `lftp mirror --delete`.
- `servercopy_rudics.zsh` appends UTC run-ledger rows to
  `$MERMAID/servers/_runs/servercopy_rudics_runs.csv` and does not rewrite or
  truncate existing ledgers.
- `servercopy_princeton.zsh` does not delete remote files.
- `servercopy_princeton.zsh` does not delete local files unless `lftp` replaces
  an older local copy of a file it is downloading.
- `servercopy_jamstec.zsh` does not delete remote files.
- `servercopy_jamstec.zsh` does not delete local files unless `lftp` replaces an
  older local copy of a file it is downloading.
