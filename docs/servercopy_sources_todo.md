# Server Source Integration TODO

Canonical checklist for incorporating MERMAID accounts and remote sources into
the server-copy workflow. A live source is complete after configuration
validation and a successful remote preview; normal mirrors and output review
are tracked separately. A retired source is complete after shutdown and
archival disposition are confirmed.

## Highest priority

- [ ] Follow up with Seb and Lionel at GeoAzur to expose all applicable TAAL
  files, especially `*.S61` and `*.[0-9][0-9][0-9]`, in the `eso/` and
  `kobeuni/` subtrees.
  - `servercopy` already mirrors the fixed suffix policy and automatically
    discovers contiguous numbered suffixes; the remaining blocker is remote
    exposure, not client support.
  - Current TAAL discovery reports no numbered suffixes. The live Kobe mirror
    also has no `.S61` files, while its historical archive has 177 `.S61` and
    300 numbered files (`.000` through `.002`).
  - Complete this item after an authenticated preview confirms the newly
    exposed classes and a normal mirror retrieves them. Record any class that
    GeoAzur confirms is intentionally unavailable.

## CLS/RUDICS sources

### General

- [x] `s_mermaid`
- [x] `s_psdmaid`

### JAMSTEC

- [x] `s_m0056`: retired; confirmed shut down on 2026-07-23.
- [x] `s_m0057`
- [x] `s_m0101`
- [x] `s_m0102`

### Brazil

- [x] `s_m0095@rudics.thorium.cls.fr`
- [x] `s_m0096@rudics.thorium.cls.fr`
- [x] `s_m0097@rudics.thorium.cls.fr`
- [x] `s_m0098@rudics.thorium.cls.fr`
- [x] `s_m0099@rudics.thorium.cls.fr`
- [x] `s_m0106@rudics.thorium.cls.fr`
- [x] `s_m0107@rudics.thorium.cls.fr`
- [x] `s_m0108@rudics.thorium.cls.fr`

Operational evidence:

- The authenticated preview on 2026-07-17 succeeded for 18 of 20 configured
  sources.
- `s_m0056` was rejected at login; its later shutdown confirmation supersedes
  that failure, so no successful preview or mirror is expected.
- `s_m0095` authenticated and previewed its tree, but the initial preview
  failed on an inaccessible, unselected `tools/` file. The suffix-specific
  workflow avoided that path, and normal mirrors succeeded on 2026-07-21 and
  2026-07-22.
- All 19 runnable sources completed a normal version 1.7.0 mirror on
  2026-07-22. Every intended `<output>/<logical_user>/` destination was present
  and nonempty when audited on 2026-07-23.
- The `s_m0056` credential is intentionally commented out. Its non-secret
  `servercopy_sources.csv` row remains, so runs will report a skip warning
  until that configuration row is removed.

## TAAL sources

- [x] ESO at `taal.unice.fr`; remote subtree `eso/`.
- [x] Kobe University at `taal.unice.fr`; remote subtree `kobeuni/`.

The legacy selection for both sources was `MER`, `LOG`, `BIN`, `cmd`, `out`,
and `vit`.

## MERMAID serial mappings and data provenance

- [x] `0030`: a misleading external credential filename actually represented
  the `s_m0023` login, which broad account `s_mermaid` encompasses.
- [x] `0075`: mapped to `s_m0075`; authenticated preview succeeded.
- [x] `0076`: mapped to `s_m0076`; authenticated preview succeeded.
- [x] `0077`: mapped to `s_m0077`; authenticated preview succeeded.
- [x] `0080`: mapped to `s_m0080`; authenticated preview succeeded.
- [ ] Resolve the data provenance of `0075`, `0076`, `0077`, and `0080`.
  - All four accounts authenticated at `rudics.thorium.cls.fr` on 2026-07-17
    and completed normal mirror operations on 2026-07-22.
  - Each destination contains the same 19 retained shell, configuration,
    monitoring, and tool files, but no canonical data files (`MER`, `LOG`,
    `BIN`, `cmd`, `out`, `vit`, `S41`, `S61`, or a numbered suffix).
  - The 2026-07-22 run discovered no numbered suffixes. Every fixed-suffix
    command exited successfully without reporting a transfer; a zero-match
    mirror is operationally successful but does not establish that data exists.
  - No current per-user mirror filename identifies any of these instruments
    under the canonical letter-before-final-hyphen rule.
  - Account names establish source and destination mappings, not deployment,
    ownership, or transmission history. For each serial, determine whether the
    account was provisioned but unused, a broader account such as `s_mermaid`
    carries its data, or another source/root is authoritative. Record that no
    data is expected, or configure the actual source.

## Resolved source conventions

- [x] Relate legacy endpoint `iridium-rudics.cls.fr` to current endpoint
  `rudics.thorium.cls.fr`.
- [x] Define destinations for sources without one RUDICS account per
  destination.
- [x] Decide whether transcripts and ledger rows need an additional source
  identity before multiple remotes share the workflow.

Resolved behavior:

- Use the CLS-preferred `rudics.thorium.cls.fr` endpoint.
- Mirror each logical user into `<output>/<user>/`, defaulting to
  `~/mermaid/servers/<user>/`, even when users share an authentication login.
- Retain ledger schema `user,result,start,end,ver`; `user` is the logical user.

## Retired and historical sources

- [x] SUSTech: servers were confirmed shut down and inaccessible on
  2026-07-23, so no live pull is available. No archive was identified; reopen
  only if a historical snapshot is found and its unique data should be
  preserved.
- [x] Old Princeton: this was a retired aggregate workflow, not a distinct
  host.
  - Deleted script `servercopy_princeton.zsh` used the current
    `rudics.thorium.cls.fr` endpoint.
  - It merged all accounts into `$MERMAID/server_princeton/`, allowing
    identical names from different users to overwrite one another. The current
    workflow preserves identity in `$MERMAID/servers/<user>/`.
  - The aggregate destination was absent on 2026-07-23; no local Princeton
    tree awaits import. Reopen only if a distinct historical snapshot appears.
- [x] Old GeoAzur/TAAL transfer and archive relationship.
  - ESO and Kobe at `taal.unice.fr` are the current live sources; normal
    mirrors of both subtrees succeeded on 2026-07-22.
  - `$MERMAID/server_jamstec/` is a misleading legacy name. FileZilla
    redirected the TAAL `kobeuni` user there, so it is a historical Kobe
    archive, not CLS JAMSTEC output.
  - Excluding `.git`, the archive held 7,662 files totaling 234,551,131 bytes
    on 2026-07-23, including 127 `.000`, 97 `.001`, and 76 `.002` files.
  - The live `$MERMAID/servers/kobeuni/` mirror held 5,843 files totaling
    154,306,030 bytes and no numbered files. A basename-only comparison found
    5,834 shared names, 1,828 archive-only names, and 9 live-only names.
  - The current workflow replaces the old live transfer, not the archive
    byte-for-byte: TAAL did not expose the separately supplied numbered files
    over FTPS. Preserve the archive separately. Consolidation into another data
    product is an archival-import task, not live `servercopy` mirroring.

## Incoming sources

Record new accounts and remotes here before assigning a workflow or
destination.
