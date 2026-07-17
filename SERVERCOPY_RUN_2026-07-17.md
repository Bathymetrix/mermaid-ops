# Servercopy Full Mirror Observations: 2026-07-17

## Run summary

The canonical `servercopy` version 1.3.1 ran in normal mode against all 20
configured logical sources. It used the protected credential registry through
the script; the registry was not inspected or printed during this review.

- Start: `2026-07-17T19:40:36Z`
- Transcript last modification: `2026-07-17T20:37:45Z`
- Approximate wall time: 57 minutes 9 seconds
- Output: `/Users/jdsimon/mermaid/servers/`
- Transcript: `_runs/servercopy_2026-07-17T19:40:36Z.log`
- Ledger: `_runs/servercopy_runs.csv`
- Overall process exit status: 1
- Per-source results: 16 success, 4 failure
- Configured-destination inventory: 6,819 files, 218,578,299 bytes

The transcript contains all 20 distinct source headers in registry order, and
the ledger contains exactly 20 version-1.3.1 rows. Every success row has an end
time. As currently designed, every failure row has a blank end time.

## Source results and local inventory

File and byte totals describe the post-run local destinations. A populated
failed destination is partial and must not be interpreted as success.

| Logical user | Result | Files | Bytes | Zero-byte files | Backup-suffix files |
| --- | --- | ---: | ---: | ---: | ---: |
| `s_mermaid` | success | 58 | 146,822 | 2 | 19 |
| `s_psdmaid` | success | 92 | 1,589,073 | 2 | 12 |
| `s_m0056` | failure | 0 | 0 | 0 | 0 |
| `s_m0057` | success | 883 | 49,346,959 | 2 | 36 |
| `s_m0075` | success | 19 | 31,214 | 2 | 0 |
| `s_m0076` | success | 19 | 31,214 | 2 | 0 |
| `s_m0077` | success | 19 | 31,214 | 2 | 0 |
| `s_m0080` | success | 19 | 31,214 | 2 | 0 |
| `s_m0101` | failure | 449 | 8,202,472 | 7 | 35 |
| `s_m0102` | success | 218 | 2,991,201 | 4 | 0 |
| `s_m0095` | failure | 128 | 1,747,990 | 3 | 28 |
| `s_m0096` | success | 131 | 1,679,488 | 5 | 28 |
| `s_m0097` | success | 156 | 2,063,968 | 2 | 35 |
| `s_m0098` | success | 132 | 1,511,926 | 2 | 28 |
| `s_m0099` | success | 133 | 1,601,267 | 4 | 28 |
| `s_m0106` | success | 141 | 1,350,245 | 2 | 28 |
| `s_m0107` | success | 137 | 1,378,495 | 2 | 35 |
| `s_m0108` | success | 120 | 1,452,019 | 2 | 21 |
| `eso` | success | 1,101 | 25,881,561 | 1 | 0 |
| `kobeuni` | failure | 2,864 | 117,509,957 | 4 | 0 |

## Failures

### `s_m0056`: authentication failure

The server rejected the login with `Login failed: Login incorrect`. The local
destination exists because `servercopy` creates destinations before starting
`lftp`, but it is empty. The same credential failed during the preceding dry
run.

Logging implication: record an explicit phase (`connect` or `authenticate`),
the `lftp` return code, a normalized error class, and `partial=false`. Directory
existence alone conveys none of those facts.

### `s_m0101`: remote names cannot be represented locally

The dry run succeeded because it did not create local files. The normal mirror
encountered three entries under `logs/` whose names contain non-UTF-8 bytes.
`lftp` reported `Illegal byte sequence` for all three. The local destination has
414 remote-like files plus 35 timestamped backup-suffix files, but the three
problem entries from the preview are absent.

The transcript contains six Unicode replacement characters: each affected
name appears once in a transfer line and once in an error line. Replacement
decoding kept the workflow alive but destroyed the exact byte identity needed
to distinguish and remediate the remote names.

Logging implication: retain a safe escaped or hexadecimal representation of
undecodable path bytes, the display-safe path, the local filesystem error, and
`partial=true`. A dry-run success cannot certify that remote names are locally
representable.

### `s_m0095`: permission failure after useful output

The mirror returned `Access failed: Permission denied` but continued to produce
useful local output. All 100 remote file names seen in the dry-run preview are
present locally, along with 28 timestamped backup-suffix files. The actual
failure transcript does not associate the permission error with a path. The
preceding dry run placed the error adjacent to `tools/zmodem_tty_set.sh`, but
stdout/stderr merging and reordering make that attribution uncertain.

Logging implication: preserve the source path and operation on every access
error, keep stdout and stderr identity when possible, and report transferred,
skipped, and failed object counts. Local name presence does not prove that file
contents are complete or current.

### `kobeuni`: blank-detail file error stopped later policy passes

The first `mermaid-selected` pass transferred the complete set of 2,864 `.MER`
names seen in the dry-run preview. It then ended with the incomplete diagnostic
`mirror: 05_654E35D0.MER:`. That local file exists and is 1,569 bytes, but the
transcript gives no reason and no remote size or checksum with which to verify
it.

Because `cmd:fail-exit` stopped the remaining mirror commands, these previewed
files were not attempted:

- 2,917 `.LOG`
- 24 `.cmd`
- 15 `.out`
- 14 `.vit`

No `.BIN` files were present in the preview. The resulting Kobe destination is
therefore a partial, `.MER`-only mirror even though it contains 2,864 files and
about 117.5 MB.

Logging implication: treat each selected-extension pass as a named substep.
Record substep start/end/result, attempted/transferred/failed counts and bytes,
the failing path, return code, and the later substeps skipped because of that
failure.

## Other observed oddities and consistency checks

### Local backup-suffix accumulation

The configured destinations contain 333 files whose names end in an lftp-style
timestamped backup suffix. One hundred have `20260717` suffix timestamps and
strongly appear to have been produced by this run. The installed lftp defaults
include `xfer:make-backup yes`, `xfer:clobber no`, and a timestamped
`xfer:backup-suffix`. They also report `xfer:keep-backup no`, yet the artifacts
remain after successful source runs; that behavior needs an isolated policy
test before changing production settings.

The RUDICS `*~` exclusion applies to remote selection; it does not prevent
local backup files created while replacing existing destinations. No remote
`backups/` tree was mirrored, and no `.part`, `.partial`, `.in.*`, or
lftp-status temporary files remained.

Future run summaries should distinguish remote objects, locally generated
backup artifacts, and incomplete-transfer artifacts. Backup creation and
retention should be an explicit configured policy rather than an implicit lftp
default.

### Successful accounts with no instrument data

`s_m0075`, `s_m0076`, `s_m0077`, and `s_m0080` each succeeded with the same 19
operational dotfiles and tool/configuration files (31,214 bytes). None contains
a file with `MER`, `LOG`, `BIN`, `cmd`, `out`, or `vit` extension, and none
contains a filename from which a canonical instrument ID can be derived.

A successful connection and mirror should therefore be logged separately from
the presence of instrument data, the number of new data objects, and the age of
the newest data object.

### Zero-byte files

There are 52 zero-byte files across configured destinations. Thirty-four are
dotfiles. The remaining 18 include eight `.MER` files, two `.S61` files, five
odd `s_m0101/logs/` names, and three unusual `s_m0096` names. Some may be valid
remote objects, but the current transcript and ledger cannot distinguish valid
empty files from truncated or placeholder files.

Per-source summaries should report zero-byte counts by extension and whether
the remote object was also zero bytes.

### Preview-to-mirror drift and aggregate identities

The normal mirror began about three hours after the preview. Compared with the
preview, the two aggregate sources gained five remote-like names:

- `s_mermaid`: one new `P0017` command file
- `s_psdmaid`: four new MER/BIN data files

This is expected for live sources but demonstrates that the full 20-source run
is not one atomic snapshot. A run-level timestamp cannot represent the state of
every source; per-source observation windows are required.

Canonical IDs derived from artifact names in the final aggregate outputs are:

- `s_mermaid`: `P0013`, `P0016`, `P0017`, `P0018`, `P0019`, `P0020`, `P0021`,
  `P0023`
- `s_psdmaid`: `R0002`, `R0003`, `R0004`, `R0007`

ESO contains `P0006`, `P0007`, and `W0114` through `W0121`. Kobe's current
`.MER` naming does not contain the letter-before-final-hyphen form needed for
canonical ID derivation.

### Policy checks

- No configured RUDICS destination contains a `backups/` path.
- ESO and Kobe contain no extensions outside the configured case-sensitive
  selection.
- ESO exactly matches all 1,101 names from its preview: 600 MER, 470 LOG,
  10 cmd, 11 out, and 10 vit.
- Kobe contains all 2,864 previewed MER names but none of the 2,970 names from
  the later policy passes.
- No symlinks or recognized partial-transfer/status files remain.

### Protocol naming

The same Taal connection is described as `ftps-explicit` in configuration,
`ftp+tls` in the source summary, and `ftp://` in lftp URL output. Structured
logs should use one normalized protocol value while optionally retaining the
tool-specific transport label.

### Historical logs

The `_runs` directory retains the historical `servercopy_rudics` ledger and
transcripts beside the new combined workflow's ledger and transcript. This is
intentional preservation, but downstream log discovery must distinguish the
two schemas/workflows by filename and version rather than treating every file
in `_runs` as one homogeneous stream.

## Transcript and ledger limitations exposed by this run

The 176,095-byte transcript has 4,481 lines, no warnings, one final failure
section, and no `DONE` or explicit failed-run footer. It does not record the
numeric overall exit status. No credential-bearing URL user information was
present in the transcript. This check only covers URL user information; it is
not a comparison against secret values.

Observed limitations:

- `lftp` output is buffered until a source exits, so there is no heartbeat or
  live filename/byte progress. Kobe was silent for long enumeration periods.
- Successful source output is inline, but all failed-source output is moved to
  the final failure section. Thousands of successful transfer lines can bury
  the actual error.
- stdout and stderr are merged before parsing. Error order and path attribution
  can be ambiguous.
- Warning lines would be removed from source context and emitted at the end.
- A failed run has no final end time, duration, status footer, or closing
  separator.
- Failure ledger rows have no end time. No row contains a run ID, host, policy,
  phase/substep, return code, error class, warning count, object/byte counts, or
  partial-state flag.
- Transcript text decoding replaces invalid bytes. The exact bytes needed to
  diagnose `s_m0101` are unavailable from the transcript.
- There is no timeout, retry record, remote/local count comparison, size
  verification, or checksum verification.
- A populated destination can mean success, useful partial output, stale files,
  or locally generated backup artifacts.
- Transcript names have second resolution and use append mode, so invocations
  beginning in the same second could merge into one file.
- The README calls transcripts raw, but redaction, replacement decoding,
  stdout/stderr merging, warning extraction, and failure reordering all
  transform the tool output.

## Recommended logging design

Preserve the existing `user,result,start,end,ver` ledger for compatibility.
Add a structured per-run sidecar, preferably JSON Lines, with these events:

1. `run_start`: run ID, mode, start, version, output root, source count,
   configuration digest, Python/lftp versions, and available disk space.
2. `source_start`: run ID, logical user, normalized protocol, host, remote root,
   policy, destination, and start.
3. `source_progress`: heartbeat, active policy substep, current safe path,
   attempted/completed files and bytes, and last-progress time.
4. `source_error`: phase/substep, normalized class, tool return code, safe
   display path, escaped raw path bytes when needed, message, retry count, and
   whether output is partial.
5. `source_end`: end, duration, result, warning/error counts, transferred,
   unchanged, skipped and failed counts/bytes, zero-byte count, backup-artifact
   count, and verification status.
6. `run_end`: end, duration, overall exit status, success/failure counts, failed
   users, transcript path, ledger row count, and whether all expected sources
   reached a terminal state.

Write `source_end` and `run_end` in `finally` paths so interruptions and
unexpected exceptions are explicit. Keep a redacted streaming transcript for
operator diagnostics, but do not make transcript parsing the only source of
machine-readable status.
