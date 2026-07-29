# Unresolved Server Source Work

The configured suffix-filtered synchronization workflow is operational. Only
the following source-level questions remain; neither requires a `servercopy`
code change unless new evidence changes the established mirror policy.

## TAAL file exposure

- [ ] Follow up with Seb and Lionel at GeoAzur to expose all applicable TAAL
  files, especially `*.S61` and `*.[0-9][0-9][0-9]`, in the `eso/` and
  `kobeuni/` subtrees.
  - `servercopy` includes both classes in its suffix allowlist, so newly exposed
    files require no transfer-policy change once the account can read them.
  - The live Kobe mirror currently has no `.S61` files, while its historical
    archive has 177 `.S61` and 300 numbered files (`.000` through `.002`).
  - Complete this item after an authenticated preview confirms the newly
    exposed classes and a normal mirror retrieves them. Record any class that
    GeoAzur confirms is intentionally unavailable.

## RUDICS data provenance

- [ ] Resolve the data provenance of accounts `s_m0075`, `s_m0076`, `s_m0077`,
  and `s_m0080`.
  - All four accounts authenticated at `rudics.thorium.cls.fr` on 2026-07-17
    and completed normal mirror operations on 2026-07-22.
  - Each destination currently contains the same 19 retained shell,
    configuration, monitoring, and tool files from earlier whole-tree runs,
    but no canonical data files (`MER`, `LOG`, `BIN`, `cmd`, `out`, `vit`,
    `S41`, `S61`, or a numbered suffix).
  - A successful suffix-filtered mirror containing no canonical data does not
    establish that data exists. It establishes only that no eligible file
    failed to mirror.
  - Determine whether each account was provisioned but unused, whether a
    broader account carries its data, or whether another source or remote root
    is authoritative. Record that no data is expected or configure the actual
    source.

Completed source-integration history is recorded in Git. Current configured
sources are listed in `data/servercopy_sources.csv`, and the current
login-to-instrument mapping is in
[`servercopy_inventory.md`](servercopy_inventory.md).
