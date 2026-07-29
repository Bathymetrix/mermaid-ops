# Servercopy Whole-Tree Mirror Experiment (Superseded)

## Status

This document records the superseded whole-tree experiment and its production
evidence. Current `servercopy` behavior uses one suffix-filtered `lftp mirror`
per configured source. The command includes `.MER`, `.LOG`, `.BIN`, `.cmd`,
`.out`, `.vit`, `.S41`, `.S61`, and exactly three-digit suffixes from `.000`
through `.999`, and excludes directories named exactly `backups`.

The current implementation expresses the numbered family directly as
`*.[0-9][0-9][0-9]`. It performs no preliminary remote listing, suffix
discovery, or suffix-by-suffix mirror passes.

## Transfer model

During the experiment, every configured source followed the same sequence:

```text
connect
cd <configured remote directory>
lcd <configured local destination>
mirror (excluding backups/ directories)
```

Configuration still supplies the protocol, host, username and credentials,
remote root, and logical-user destination. The current transfer implementation
has no RUDICS-, ESO-, Kobe-, or other endpoint-specific file-selection
branches.

FTPS still uses the three TLS settings validated on the production-style
Frisius environment. SFTP still uses its direct connection URL without
optional modern settings. Both protocols use one mirror command. Normal
operation does not request deletion, reverse mirroring, or forced overwrites.

The whole-tree model applied to every configured source. It replaced fixed
suffix allowlists, numbered-suffix discovery, generated file selections, and
repeated suffix-specific mirror passes. During that experiment, downloads were
not restricted to `.MER`, `.LOG`, `.BIN`, `.cmd`, `.out`, `.vit`, `.S41`,
`.S61`, or any other filename allowlist.

That broader local scope was deliberate during the experiment. Any readable
content beneath the configured remote root could appear in the mirror. Current
runs select only the documented suffix allowlist and continue to exclude any
directory named exactly `backups`, at any depth, from traversal.

## Remote permissions and completeness

In the superseded design, **whole-tree mirror** meant:

> Mirror the entire remote tree that the authenticated account is allowed to
> read, excluding `backups/` directories.

It does not promise a byte-for-byte local copy of every path visible in a
remote directory listing. Server-side ownership and permissions can allow an
account to list a path without allowing it to read that path. For example, the
`s_psdmaid` source may report:

```text
mirror: Access failed: Permission denied (.buoy_monitoring.sh.nohup.20260704122043)
```

This is a remote permission constraint. `servercopy` must not attempt to change
remote ownership or permissions, and an inaccessible eligible path remains
absent from the local mirror.

An access failure is still an operational failure when `lftp` returns nonzero.
Do not describe such a run as fully successful merely because other readable
files transferred. Maintainers should investigate repeated or operationally
important permission errors with the server owner, but must not add
endpoint-specific exclusions merely to suppress the diagnostics.

## Production evidence

Frisius provides legacy `lftp 4.4.8`. The minimal FTPS connection and
whole-tree mirror were tested against an existing Kobe destination containing
5,858 files. The comparison correctly identified only 6 new files and 9
modified files, transferring 3,094,464 bytes rather than recopying the complete
eligible readable tree.

Remote listing and comparison took roughly ten minutes before transfer began.
Comparable delays have occurred on macOS and on runs that ultimately found no
new files. A long quiet comparison phase is therefore normal and should not be
"optimized" without evidence of an actual operational problem.

The earlier suffix-filtered design added discovery and multi-command
complexity. The restored design avoids those mechanisms: it combines all
include globs in one mirror command and matches the entire numbered family
directly.

## Output and heartbeat

Native `lftp` output is forwarded without a line-oriented progress parser, so
interactive progress can update a single terminal line with carriage returns.
`servercopy` does not infer transfer activity from that output.

The periodic heartbeat reports one fact only: the `lftp` child process is still
alive. It does not mean bytes are moving, the remote listing is advancing, or
the transfer will eventually succeed. There is no output-silence watchdog;
`lftp`'s own exit status determines success or failure.
