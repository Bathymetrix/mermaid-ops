# mermaid-ops

Operational scripts for MERMAID data and server workflows.

These scripts are intentionally small and direct. They are meant for repeatable
MERMAID operations where the destination paths, credentials files, and server
behavior should be easy to inspect before running.

## Scripts

### `servercopy_princeton.zsh`

Bathymetrix(TM) MERMAID operations script for mirroring Princeton RUDICS SFTP
accounts into a local server directory.

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

## Requirements

- `zsh`
- `lftp`
- `MERMAID` set in the environment
- Princeton credentials CSV at `$MERMAID/passwords/princeton.csv`

The credentials CSV is expected to use the fourth column for the SFTP username
and the fifth column for the SFTP password. The first two lines are skipped as
headers. The file is expected to use simple comma-separated fields; quoted
commas in fields are not supported.

## Safety Notes

- Scripts may touch live MERMAID server data.
- Credentials files should never be committed.
- Check destination paths before running a script for the first time.
- `servercopy_princeton.zsh` does not delete remote files.
- `servercopy_princeton.zsh` does not delete local files unless `lftp` replaces
  an older local copy of a file it is downloading.

## Branding

User-facing scripts may identify themselves as Bathymetrix(TM) MERMAID
operations tools in headers and help output. Keep source headers plain ASCII;
use the typographic Bathymetrix(TM) mark only in rendered docs or public web
copy if needed.
