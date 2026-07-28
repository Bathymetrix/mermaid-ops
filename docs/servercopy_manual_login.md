# Manual Login / Diagnostic Procedures

These procedures are useful for verifying that credentials work and that the
remote server is reachable independently of `servercopy`.

**Never place passwords on the command line or in shell history.**
When prompted, enter the password interactively.

---

# RUDICS (CLS)

Host:
```
rudics.thorium.cls.fr
```

Protocol:
```
SFTP (SSH), port 22
```

Example login:

```bash
lftp -u s_mermaid sftp://rudics.thorium.cls.fr:22
```

After connecting, useful commands include:

```text
pwd
ls
cls
exit
```

---

# TAAL

Host:
```
taal.unice.fr
```

Protocol:
```
Explicit FTPS, port 21
```

Example login:

```bash
lftp
```

Then at the `lftp>` prompt:

```text
set ftp:ssl-force yes
set ftp:ssl-protect-data yes
set ftp:ssl-protect-list yes

open -u automaid ftp://taal.unice.fr:21
```

When prompted, enter the password.

Useful diagnostic commands:

```text
pwd
ls
cls
cd eso
ls

cd ..
cd kobeuni
ls

exit
```

---

# Notes

- Successful login confirms:
  - DNS resolution
  - Network connectivity
  - Authentication
  - Server availability

- A successful login does **not** guarantee that a `mirror` operation will be
  fast or complete; the remote listing and comparison may be quiet for
  approximately ten minutes even when no files need transfer.

- `servercopy` mirrors the complete readable tree beneath the configured
  remote root for RUDICS, ESO, and Kobe alike. It does not filter by scientific
  filename suffix, so shell files, account configuration, scripts, tools,
  histories, and other readable account content may appear locally.

- A path shown by `ls` or `cls` is not necessarily readable. Server-side
  ownership or permissions may cause `mirror: Access failed: Permission
  denied`; the path then remains absent locally and `lftp` may exit nonzero.
  Diagnostic sessions must not change remote permissions.

- These commands are intended only for diagnostics and interactive inspection.
  Manual synchronization should be performed with `servercopy`; scheduled
  synchronization should use `servercopy_cron`.
  
