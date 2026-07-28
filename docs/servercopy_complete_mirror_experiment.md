# Servercopy Whole-Tree Mirror Design

## Maintainer warning

> This implementation is intentionally plain. It targets the legacy `lftp
> 4.4.8` available on Frisius and has been validated against the production
> data layout. Do not replace the single whole-tree `mirror` with suffix
> discovery, generated file lists, capability-dependent flags, output parsing,
> or custom progress handling merely to make the implementation appear more
> sophisticated. Change it only in response to a demonstrated operational
> failure.

## Transfer model

Every configured source follows the same sequence:

```text
connect
cd <configured remote directory>
lcd <configured local destination>
mirror
```

Configuration supplies the protocol, host, username and credentials, remote
directory, and logical-user destination. The transfer implementation has no
Kobe-, ESO-, RUDICS-, or endpoint-specific branches.

FTPS uses the three TLS settings validated on the production-style Frisius
environment. SFTP uses its direct connection URL without optional modern
settings. Both protocols then use one whole-tree `mirror`. Normal operation
does not request deletion, reverse mirroring, or forced overwrites.

This whole-tree model replaced fixed suffix allowlists, numbered-suffix
discovery, generated file selections, and repeated suffix-specific mirror
passes for all supported endpoints.

## Production evidence

Frisius provides legacy `lftp 4.4.8`. The minimal FTPS connection and plain
mirror were tested against an existing Kobe destination containing 5,858
files. The comparison correctly identified only 6 new files and 9 modified
files, transferring 3,094,464 bytes rather than recopying the complete tree.

Remote listing and comparison took roughly ten minutes before transfer began.
Comparable delays have occurred on macOS and on runs that ultimately found no
new files. A long quiet comparison phase is therefore normal and should not be
"optimized" without evidence of an actual operational problem.

## Output and heartbeat

Native `lftp` output is forwarded without a line-oriented progress parser, so
interactive progress can update a single terminal line with carriage returns.
`servercopy` does not infer transfer activity from that output.

The periodic heartbeat reports one fact only: the `lftp` child process is still
alive. It does not mean bytes are moving, the remote listing is advancing, or
the transfer will eventually succeed. There is no output-silence watchdog;
`lftp`'s own exit status determines success or failure.
