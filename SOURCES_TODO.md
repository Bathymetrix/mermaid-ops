# Server Source Integration TODO

Use this checklist to track MERMAID accounts and remote sources as they are
incorporated into the canonical server-copy workflow.

An account or source is complete only after its configuration is validated, a
remote preview succeeds, a normal mirror succeeds, and its local output is
verified in the intended destination.

## Existing CLS/RUDICS accounts to verify

### General

- [ ] `s_mermaid`
- [ ] `s_psdmaid`

### JAMSTEC

- [ ] `s_m0056`
- [ ] `s_m0057`
- [ ] `s_m0101`
- [ ] `s_m0102`

### Brazil

- [ ] `s_m0095@rudics.thorium.cls.fr`
- [ ] `s_m0096@rudics.thorium.cls.fr`
- [ ] `s_m0097@rudics.thorium.cls.fr`
- [ ] `s_m0098@rudics.thorium.cls.fr`
- [ ] `s_m0099@rudics.thorium.cls.fr`
- [ ] `s_m0106@rudics.thorium.cls.fr`
- [ ] `s_m0107@rudics.thorium.cls.fr`
- [ ] `s_m0108@rudics.thorium.cls.fr`

## Additional live sources to add

- [ ] ESO at `taal.unice.fr`
  - Remote subtree: `eso/`
  - Legacy file selection: `MER`, `LOG`, `BIN`, `cmd`, `out`, and `vit`
- [ ] Kobe University at `taal.unice.fr`
  - Remote subtree: `kobeuni/`
  - Legacy file selection: `MER`, `LOG`, `BIN`, `cmd`, `out`, and `vit`

## Unmapped MERMAID serials

Identify the full instrument ID, source, remote account, and intended local
destination for each serial.

- [ ] `0030`
- [ ] `0075`
- [ ] `0076`
- [ ] `0077`
- [ ] `0080`

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
