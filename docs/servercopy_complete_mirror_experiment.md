# Servercopy Whole-Tree Mirror Design

## Maintainer warning

> This implementation is intentionally plain. It targets the legacy `lftp
> 4.4.8` available on Frisius and has been validated against the production
> data layout. `servercopy` intentionally mirrors the complete readable remote
> tree for each configured account. Do not reintroduce suffix allowlists or
> endpoint-specific file-selection logic merely to exclude shell files, tools,
> histories, or other account content. Some listed paths may remain unavailable
> because of remote permissions; that limitation should be documented and
> surfaced, not hidden through increasingly complex filtering. Change the
> design only in response to a demonstrated operational failure.

## Transfer model

Every configured source follows the same sequence:

```text
connect
cd <configured remote directory>
lcd <configured local destination>
mirror
```

Configuration supplies the protocol, host, username and credentials, remote
root, and logical-user destination. The transfer implementation has no
RUDICS-, ESO-, Kobe-, or other endpoint-specific file-selection branches.

FTPS uses the three TLS settings validated on the production-style Frisius
environment. SFTP uses its direct connection URL without optional modern
settings. Both protocols then use one whole-tree `mirror`. Normal operation
does not request deletion, reverse mirroring, or forced overwrites.

This whole-tree model applies to every configured source. It replaced fixed
suffix allowlists, numbered-suffix discovery, generated file selections, and
repeated suffix-specific mirror passes. Downloads are no longer restricted to
`.MER`, `.LOG`, `.BIN`, `.cmd`, `.out`, `.vit`, `.S41`, `.S61`, or any other
allowlist.

The broader local scope is deliberate. Any readable content beneath the
configured remote root can appear in the mirror, including shell startup
files, account configuration, scripts, tools, histories, monitoring artifacts,
and other files unrelated to the scientific data stream.

## Remote permissions and completeness

In this design, **whole-tree mirror** means:

> Mirror the entire remote tree that the authenticated account is allowed to
> read.

It does not promise a byte-for-byte local copy of every path visible in a
remote directory listing. Server-side ownership and permissions can allow an
account to list a path without allowing it to read that path. For example, the
`s_psdmaid` source may report:

```text
mirror: Access failed: Permission denied (.buoy_monitoring.sh.nohup.20260704122043)
```

This is a remote permission constraint, not evidence that filename filtering
remains active. `servercopy` must not attempt to change remote ownership or
permissions, and an inaccessible path remains absent from the local mirror.
The accurate completeness claim is therefore **complete readable remote tree**.

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
readable tree.

Remote listing and comparison took roughly ten minutes before transfer began.
Comparable delays have occurred on macOS and on runs that ultimately found no
new files. A long quiet comparison phase is therefore normal and should not be
"optimized" without evidence of an actual operational problem.

The earlier suffix-filtered design added substantial discovery and
multi-command complexity and depended on fragile, version-sensitive `lftp`
behavior. The whole-tree design is easier to understand and maintain on the
legacy production installation. Retaining additional readable account content
locally is the accepted tradeoff.

## Output and heartbeat

Native `lftp` output is forwarded without a line-oriented progress parser, so
interactive progress can update a single terminal line with carriage returns.
`servercopy` does not infer transfer activity from that output.

The periodic heartbeat reports one fact only: the `lftp` child process is still
alive. It does not mean bytes are moving, the remote listing is advancing, or
the transfer will eventually succeed. There is no output-silence watchdog;
`lftp`'s own exit status determines success or failure.
