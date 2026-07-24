# Servercopy Cron Workflow

## Overview

The cron job does **not** invoke `servercopy` directly. Instead, it invokes a lightweight Python wrapper responsible for operational tasks such as notifications and Git commits.

```
cron
  │
  ▼
servercopy_cron
  │
  ▼
servercopy
```

## Workflow

```text
run servercopy
    ↓
did every source succeed?
    ├─ no  → notify, exit nonzero, touch nothing in Git
    └─ yes → git add -A
              ↓
            any staged changes?
              ├─ no  → exit 0
              └─ yes → commit
```

## Design Decisions

- `servercopy` is responsible only for synchronization.
- `servercopy_cron` is responsible for operational concerns (notifications, Git, logging).
- If **any** synchronization source fails:
  - send a notification;
  - exit with a nonzero status;
  - perform **no Git operations** (`git add`, `git commit`, etc.).
- Partial downloads remain in the working tree and will be included in the next successful synchronization.
- Git commits are created only after a completely successful synchronization.
- If no files changed, exit successfully without creating an empty commit.
