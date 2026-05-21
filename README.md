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

Preview intended mirror operations:

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
`$MERMAID/passwords/rudics.csv` are processed; it does not filter remote content.

Preview selected users without contacting remote servers:

```sh
./servercopy_rudics.zsh --dry-run --user foo,bar
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
user,result,start,end
```

Allowed result values are `success` and `failure`. A `failure` is intentionally
broad for now: login/authentication failures, DNS failures, connection failures,
interrupted transfers, permission failures, local filesystem failures, and other
per-user mirror failures all use `failure`. No fine-grained failure typing is
implemented yet.

Use `--dry-run` to perform local validation and print the intended user,
remote endpoint, and destination for each configured account. Dry-run mode does
not contact remote servers, does not modify mirrored server contents, and does
not append to `_runs`. When combined with `--user`, dry-run output is limited to
the selected configured users.

## Requirements

- `zsh`
- `lftp`
- `MERMAID` set in the environment
- Unified RUDICS credentials CSV at `$MERMAID/passwords/rudics.csv`

The unified RUDICS credentials CSV is expected to have no header row and use one
`user,pass` pair per line. Blank lines and lines beginning with `#` are skipped.

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
- `servercopy_rudics.zsh --dry-run` prints intended mirror operations without
  contacting remote servers, modifying mirrored content, or appending to
  `_runs`.
- `servercopy_rudics.zsh --user foo,bar` limits processing to selected
  configured users only. Non-requested users in the credentials CSV are skipped.
