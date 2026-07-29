# mermaid-ops

Operational automation for mirroring MERMAID remote servers and recording
scheduled synchronization results.

The repository owns two directly executable, standard-library-only Python
3.12 programs:

- `servercopy` mirrors configured remote content into separate logical-user
  directories, records run-ledger rows, and writes synchronization transcripts.
- `servercopy_cron` wraps a scheduled synchronization with invocation logging,
  single-host locking, Healthchecks.io lifecycle pings, a clean-repository
  preflight, and a conservative Git commit. It never pushes.

Remote deletions do not remove local mirror files. Neither program performs
normalization, conversion, catalog generation, exports, or other downstream
processing.

Production runs on `frisius.princeton.edu`. See
[`docs/frisius_installation.md`](docs/frisius_installation.md) to rebuild the
host and [`docs/servercopy_cron_workflow.md`](docs/servercopy_cron_workflow.md)
for the operational runbook.

## Quick start

Requirements:

- Python 3.12 or newer
- `lftp`
- Git
- a configured `MERMAID` directory

Set `MERMAID` to the data root:

```sh
export MERMAID=/path/to/mermaid
```

Validate local configuration without contacting a remote or creating output:

```sh
./servercopy --check
```

Authenticate and preview remote mirror operations without transferring files:

```sh
./servercopy --dry-run
```

Dry-run mode does not create local destinations; each selected
`<output>/<logical_user>/` directory must already exist.

Run a normal synchronization:

```sh
./servercopy
```

Process selected logical users or choose another output root:

```sh
./servercopy --user s_m0057,eso
./servercopy --output /path/to/servers
```

Show the public command interfaces:

```sh
./servercopy --help
./servercopy --version
./servercopy_cron --version
```

Use `servercopy_cron` only for the complete monitored synchronization-and-commit
workflow. Its production invocation and operator procedures are documented in
the linked installation guide and runbook.

## Configuration

Non-secret source definitions are stored in:

```text
data/servercopy_sources.csv
```

This registry is authoritative for each source's protocol, host, port, and
remote root.

The columns are:

```csv
user,login,protocol,host,port,remote_root
```

`user` is the logical source identity and local destination name. `login` is
the authentication identity, so multiple logical users may share one remote
login while retaining separate destinations:

```text
<output>/<logical_user>/
```

Credentials are read from the protected, untracked registry:

```text
$MERMAID/passwords/servercopy_credentials.csv
```

Its headerless format is one `login,password` pair per line. Blank lines and
lines beginning with `#` are ignored. Never commit, print, or copy this file
into logs or generated artifacts.

The scheduled wrapper also requires one private Healthchecks.io Check UUID in
the ignored file:

```text
data/healthchecks_uuid.txt
```

The wrapper validates and uses the UUID without including it in logs or error
messages.

## Synchronization behavior

Every configured source uses the same transfer workflow:

```text
connect
cd <configured remote directory>
lcd <output>/<logical_user>
mirror
```

The implementation runs one suffix-filtered `lftp mirror` per configured
source. That single command includes files ending in `.MER`, `.LOG`, `.BIN`,
`.cmd`, `.out`, `.vit`, `.S41`, `.S61`, or exactly three decimal digits from
`.000` through `.999`. Mirroring is non-recursive: only matching files located
directly in the configured remote root are eligible, and no remote
subdirectories are traversed. Numbered suffixes are matched directly with
`*.[0-9][0-9][0-9]`; no preliminary remote listing or suffix discovery is
performed.

Protocol, host, credentials, remote root, and local destination are
configuration; the mirror construction does not vary for RUDICS SFTP accounts,
ESO explicit-FTPS, Kobe explicit-FTPS, or other endpoints. The mirror uses
`--continue`, `--overwrite`, `--no-perms`, and four parallel transfers. It does
not delete remote or local files or reverse the transfer.

The implementation deliberately uses the smallest practical subset of `lftp`
features validated on the production environments, including legacy `lftp
4.4.8` on Frisius. A remote-root listing and comparison can be quiet even when
no files need transfer. This interval is expected, not evidence that the
process has hung.

Native `lftp` progress may update one terminal line with carriage returns.
While `lftp` remains active, `servercopy` emits a periodic heartbeat. The
heartbeat means only that the child process is alive; it does not assert that
bytes are moving or that remote comparison is advancing. Output silence never
causes `servercopy` to terminate an otherwise live `lftp` process.

Normal runs append one row per attempted logical user to:

```text
<output>/_runs/servercopy_runs.csv
```

The stable ledger schema is:

```csv
user,result,start,end,ver
```

Normal and dry-run invocations write combined transcripts beneath
`<output>/_runs/`. Check mode has no operational side effects. An individual
source failure does not prevent later configured sources from running, and the
process exits nonzero if any attempted source fails. Sources without configured
credentials are reported and skipped under the established public exit
contract.

An advisory lock prevents overlapping direct `servercopy` runs. The scheduled
wrapper holds a separate lock across synchronization, Git handling, and the
terminal Healthchecks.io ping.

## Development and testing

Run the offline test suite with Python 3.12 or newer:

```sh
python3.12 -m unittest discover -s tests -v
```

The tests use synthetic data and mocked `lftp`, HTTP, `servercopy`, and Git
processes. They do not contact remote servers or Healthchecks.io, read private
credential files, or modify the production servers repository.

Before submitting changes, also run:

```sh
git diff --check
```

Operator-visible changes to either executable require an appropriate
operational version increment.

## Documentation

- [`docs/frisius_installation.md`](docs/frisius_installation.md): rebuild the
  production Frisius installation from scratch.
- [`docs/servercopy_cron_workflow.md`](docs/servercopy_cron_workflow.md):
  scheduled lifecycle, locking, logging, monitoring, Git policy, and recovery.
- [`docs/servercopy_manual_login.md`](docs/servercopy_manual_login.md):
  interactive remote-connectivity diagnostics.
- [`docs/servercopy_inventory.md`](docs/servercopy_inventory.md): current
  login-to-instrument inventory.
- [`docs/servercopy_sources_todo.md`](docs/servercopy_sources_todo.md):
  unresolved source-integration work.
- [`docs/servercopy_complete_mirror_experiment.md`](docs/servercopy_complete_mirror_experiment.md):
  superseded whole-tree experiment and retained production evidence.

## Safety

- Review source and destination mappings before a first normal run.
- Treat `--dry-run` as an authenticated remote operation.
- Normal runs may modify files beneath `<output>/<logical_user>/`.
- Only top-level files matching the documented suffix allowlist are selected.
- Remote subdirectories are not traversed.
- Remote deletions do not delete local files.
- `servercopy` never changes remote ownership or permissions.
- Do not expose credentials or the Healthchecks.io UUID.
- Do not run `servercopy` manually while the scheduled wrapper may be active.
- `servercopy_cron` commits only after successful synchronization and never
  pushes.
