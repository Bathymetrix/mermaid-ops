# Unresolved Server Source Work

The configured whole-tree synchronization workflow is operational. Only the
following source-level questions remain; neither requires a `servercopy` code
change unless new evidence changes the established mirror policy.

## TAAL file exposure

- [ ] Follow up with Seb and Lionel at GeoAzur to expose all applicable TAAL
  files, especially `*.S61` and `*.[0-9][0-9][0-9]`, in the `eso/` and
  `kobeuni/` subtrees.
  - `servercopy` mirrors the complete readable configured remote tree outside
    `backups/`, so newly exposed classes require no transfer-policy change once
    the account can read them.
  - The live Kobe mirror currently has no `.S61` files, while its historical
    archive has 177 `.S61` and 300 numbered files (`.000` through `.002`).
  - Complete this item after an authenticated preview confirms the newly
    exposed classes and a normal whole-tree mirror retrieves them. Record any
    class that GeoAzur confirms is intentionally unavailable.

## RUDICS data provenance

- [ ] Resolve the data provenance of accounts `s_m0075`, `s_m0076`, `s_m0077`,
  and `s_m0080`.
  - All four accounts authenticated at `rudics.thorium.cls.fr` on 2026-07-17
    and completed normal mirror operations on 2026-07-22.
  - Each destination contains the same 19 retained shell, configuration,
    monitoring, and tool files, but no canonical data files (`MER`, `LOG`,
    `BIN`, `cmd`, `out`, `vit`, `S41`, `S61`, or a numbered suffix).
    These non-data files are expected whole-tree content, not evidence of an
    endpoint-specific selection policy.
  - A successful whole-tree mirror containing no canonical data does not
    establish that data exists. It establishes only that the account's
    readable tree outside `backups/` was mirrored without an `lftp` failure.
  - Determine whether each account was provisioned but unused, whether a
    broader account carries its data, or whether another source or remote root
    is authoritative. Record that no data is expected or configure the actual
    source.

Completed source-integration history is recorded in Git. Current configured
sources are listed in `data/servercopy_sources.csv`, and the current
login-to-instrument mapping is in
[`servercopy_inventory.md`](servercopy_inventory.md).
