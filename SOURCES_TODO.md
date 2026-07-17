# Server Source Integration TODO

Use this checklist to track MERMAID accounts and remote sources as they are
incorporated into the canonical server-copy workflow.

Check an account or source after its configuration is validated and a remote
preview succeeds. Track normal-mirror and local-output verification separately
when they remain pending.

## Existing CLS/RUDICS accounts to verify

### General

- [x] `s_mermaid`
- [x] `s_psdmaid`

### JAMSTEC

- [ ] `s_m0056`
- [x] `s_m0057`
- [x] `s_m0101`
- [x] `s_m0102`

### Brazil

- [ ] `s_m0095@rudics.thorium.cls.fr`
- [x] `s_m0096@rudics.thorium.cls.fr`
- [x] `s_m0097@rudics.thorium.cls.fr`
- [x] `s_m0098@rudics.thorium.cls.fr`
- [x] `s_m0099@rudics.thorium.cls.fr`
- [x] `s_m0106@rudics.thorium.cls.fr`
- [x] `s_m0107@rudics.thorium.cls.fr`
- [x] `s_m0108@rudics.thorium.cls.fr`

The full authenticated preview on 2026-07-17 succeeded for 18 of 20
configured sources. `s_m0056` was rejected at login. `s_m0095` authenticated
and previewed its remote tree, but an inaccessible remote `tools/` file caused
the preview to fail. Normal mirrors and local-output verification remain
pending for all sources.

## Additional live sources to add

- [x] ESO at `taal.unice.fr`
  - Remote subtree: `eso/`
  - Legacy file selection: `MER`, `LOG`, `BIN`, `cmd`, `out`, and `vit`
- [x] Kobe University at `taal.unice.fr`
  - Remote subtree: `kobeuni/`
  - Legacy file selection: `MER`, `LOG`, `BIN`, `cmd`, `out`, and `vit`

## Unmapped MERMAID serials

Identify the full instrument ID, source, remote account, and intended local
destination for each serial.

- [x] `0030`: external credential filename was misleading; its actual
  `s_m0023` login is encompassed by broad `s_mermaid`.
- [x] `0075`: configured as `s_m0075`; authenticated preview succeeded.
- [x] `0076`: configured as `s_m0076`; authenticated preview succeeded.
- [x] `0077`: configured as `s_m0077`; authenticated preview succeeded.
- [x] `0080`: configured as `s_m0080`; authenticated preview succeeded.

All four accounts authenticated at `rudics.thorium.cls.fr` on 2026-07-17.
Normal mirrors and output verification remain pending.

## Source reconciliation

- [x] Establish the relationship between the legacy CLS endpoint
  `iridium-rudics.cls.fr` and the current endpoint
  `rudics.thorium.cls.fr`.
- [x] Confirm the intended local destination naming scheme for sources that do
  not use one RUDICS account per destination.
- [x] Confirm whether source identity must be added to transcript names and run
  ledger rows before multiple remotes share one workflow.

Resolved conventions:

- Use the CLS-preferred `rudics.thorium.cls.fr` endpoint.
- Mirror each logical user into `<output>/<user>/`, defaulting to
  `~/mermaid/servers/<user>/`, even when logical users share one authentication
  login.
- Retain `user,result,start,end,ver`; the `user` value is the logical user.

## Retired sources to classify

- [ ] SUSTech: confirm that no live pull or archival import is required.
- [ ] Old Princeton server: confirm that no live pull or archival import is
  required.
- [ ] Old GeoAzur server: confirm that the ESO and Kobe sources on
  `taal.unice.fr` fully replace it.

## Incoming sources

Add newly identified accounts and remotes here before assigning them to a
workflow or destination.
