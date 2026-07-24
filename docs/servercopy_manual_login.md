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
set ftp:ssl-force true
set ftp:ssl-protect-data true
set ssl:check-hostname yes

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
  fast or complete; large directory scans may still take considerable time.

- These commands are intended only for diagnostics and interactive inspection.
  Manual synchronization should be performed with `servercopy`; scheduled
  synchronization should use `servercopy_cron`.
  
