# mermaid-ops

Operational scripts for MERMAID data and server workflows.

These scripts are intentionally small and direct. They are meant for repeatable
MERMAID operations where the destination paths, credentials files, and server
behavior should be easy to inspect before running.

## Scripts

### `servercopy_rudics.zsh`

Mirror selected MERMAID artifacts from RUDICS SFTP accounts into per-user local
server directories. This is the workflow for creating an operational mirror of
known MERMAID artifact/log file types while intentionally skipping unrelated
directories, hidden dotfiles, hidden dot-directories, and other files.

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

Check local configuration without contacting RUDICS:

```sh
./servercopy_rudics.zsh --check
./servercopy_rudics.zsh -c
```

Preview remote artifact mirror operations through lftp:

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
`$MERMAID/passwords/rudics.csv` are processed; the artifact mirror policy still
controls which remote files are mirrored.

Check selected users without contacting remote servers:

```sh
./servercopy_rudics.zsh --check --user foo,bar
./servercopy_rudics.zsh -c -u foo,bar
```

Preview selected users through lftp:

```sh
./servercopy_rudics.zsh --dry-run --user foo,bar
```

Show help:

```sh
./servercopy_rudics.zsh --help
./servercopy_rudics.zsh -h
```

Show the script version:

```sh
./servercopy_rudics.zsh --version
./servercopy_rudics.zsh -v
```

The RUDICS workflow is intentionally selective. It mirrors only these file
patterns, in order:

```text
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
```

It excludes these directories:

```text
backups/
tools/
lib64/
logs/
```

Hidden dotfiles and hidden dot-directories are also excluded. Everything else is
skipped. The workflow does not delete local files that are absent remotely, and
keeps incremental mirror behavior with `--continue`.

To include another MERMAID artifact file type later, add one quoted glob pattern
to the `include_patterns` array near the top of `servercopy_rudics.zsh`. For
example, to include `.ABC` files:

```zsh
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
    "*.ABC"
)
```

After changing the policy, run `./servercopy_rudics.zsh --dry-run` for a remote
preview before running a normal mirror.

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
user,result,start,end,ver
```

The `ver` column records the current `SERVERCOPY_RUDICS_VERSION` value for each
appended row. This script-level version is lightweight operational provenance,
not a package release system. Bump it whenever operational behavior or ledger
semantics change.

Allowed result values are `success` and `failure`. A `failure` is intentionally
broad for now: login/authentication failures, DNS failures, connection failures,
interrupted transfers, permission failures, local filesystem failures, and other
per-user mirror failures all use `failure`. No fine-grained failure typing is
implemented yet.

Use `--check` or `-c` to perform local validation and print the intended user,
remote endpoint, and destination for each configured account. Check mode does
not contact remote servers, does not authenticate, does not transfer files, does
not create directories or files, and does not append to `_runs`. When combined
with `--user`, check output is limited to the selected configured users.

Use `--dry-run` to contact and authenticate to RUDICS for each selected account
and let `lftp mirror --dry-run` print the mirror operations it would perform.
Dry-run mode transfers nothing and does not append to `_runs`. `--dry-run` is
not offline. Use `--check` or `-c` for offline/local validation.

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
- `servercopy_rudics.zsh` mirrors selected MERMAID artifacts from each remote
  account into
  `$MERMAID/servers/<user>/`.
- `servercopy_rudics.zsh` intentionally skips unrelated remote directories,
  hidden dotfiles, hidden dot-directories, and other files. Remote deletions
  still do not delete local files.
- `servercopy_rudics.zsh` appends UTC run-ledger rows to
  `$MERMAID/servers/_runs/servercopy_rudics_runs.csv` and does not rewrite or
  truncate existing ledgers. The ledger header is `user,result,start,end,ver`.
- `servercopy_rudics.zsh --check` or `servercopy_rudics.zsh -c` prints
  intended mirror operations without contacting remote servers, authenticating,
  transferring files, creating directories or files, or appending to `_runs`.
- `servercopy_rudics.zsh --dry-run` contacts and authenticates to RUDICS, asks
  `lftp` to print what it would mirror, transfers nothing, and does not append
  to `_runs`. `--dry-run` is not offline. Use `--check` or `-c` for
  offline/local validation.
- `servercopy_rudics.zsh --user foo,bar` or `servercopy_rudics.zsh -u foo,bar`
  limits processing to selected configured users only. Non-requested users in
  the credentials CSV are skipped.
