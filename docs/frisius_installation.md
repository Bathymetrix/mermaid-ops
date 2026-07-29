# Installing `mermaid-ops` on Frisius

This is the canonical procedure for rebuilding the production installation on
`frisius.princeton.edu` from nothing. For normal operation and recovery, see
[`servercopy_cron_workflow.md`](servercopy_cron_workflow.md).

## Production paths

```text
Repository          /home/jdsimon/programs/mermaid-ops
MERMAID root        /home/jdsimon/mermaid
Python              /home/jdsimon/miniforge3/envs/python3.12/bin/python3
Wrapper             /home/jdsimon/programs/mermaid-ops/servercopy_cron
Workflow logs       /home/jdsimon/mermaid/logs/servercopy_cron/
Outer cron log      /home/jdsimon/mermaid/logs/servercopy_cron_cron.log
Lock                /home/jdsimon/mermaid/logs/servercopy_cron.lock
Healthchecks UUID   /home/jdsimon/programs/mermaid-ops/data/healthchecks_uuid.txt
```

## Prerequisites

The production account must have:

- SSH access to Frisius;
- Git access to the `mermaid-ops` and servers repositories;
- outbound HTTPS and DNS access to `hc-ping.com`;
- a securely transferred
  `$MERMAID/passwords/servercopy_credentials.csv`;
- the private Healthchecks.io Check UUID; and
- sufficient storage for the mirrored server data and logs.

The following system commands must be installed and discoverable through the
restricted cron `PATH` of `/usr/bin:/bin`:

```sh
/usr/bin/env PATH=/usr/bin:/bin git --version
/usr/bin/env PATH=/usr/bin:/bin curl --version
/usr/bin/env PATH=/usr/bin:/bin lftp --version
```

Install `lftp` on Frisius with:

```bash
sudo yum install lftp
```

Frisius currently provides `lftp 4.4.8`. `servercopy` intentionally uses only
the smallest practical, legacy-compatible command subset validated on the
production environments. Do not substitute newer settings or mirror flags
without first demonstrating an operational need on every supported deployment
target.

Each configured RUDICS SFTP, ESO FTPS, and Kobe FTPS source uses the same
transfer algorithm: connect, select the configured remote root and
logical-user destination, and run exactly one `lftp mirror` command. The
command uses multiple `--include-glob` filters for `.MER`, `.LOG`, `.BIN`,
`.cmd`, `.out`, `.vit`, `.S41`, `.S61`, and exactly three-digit suffixes from
`.000` through `.999`. It uses `--no-recursion`, so only approved files
directly in the configured remote root are synchronized and no subdirectory is
traversed. Only connection and path configuration differ.

Install any other missing system commands through the Frisius administrator or
its supported operating-system package manager. The repository itself has no
third-party Python dependencies.

## Install Miniforge

Log in as `jdsimon`, download the Linux x86-64 Miniforge installer, and run it:

```sh
cd /home/jdsimon
curl -L -O \
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh
```

Accept `/home/jdsimon/miniforge3` as the installation location and allow the
installer to initialize the login shell.

After installation, log out completely and log back in. This is required so
the new login shell loads the Miniforge initialization before the environment
is created.

Verify:

```sh
conda --version
command -v conda
```

## Create the production Python environment

Create the Python 3.12 environment:

```sh
conda create --name python3.12 python=3.12
conda activate python3.12
```

The programs use only the Python standard library, so no `pip` installation is
needed. Verify the exact production interpreter:

```sh
/home/jdsimon/miniforge3/envs/python3.12/bin/python3 --version
```

## Create the MERMAID layout

Create the data and log roots:

```sh
mkdir -p /home/jdsimon/mermaid/logs
mkdir -p /home/jdsimon/mermaid/passwords
```

Clone the separate servers Git repository:

```sh
git clone jdsimon@ariel.princeton.edu:~/mermaid/servers/ \
  /home/jdsimon/mermaid/servers
```

The completed layout is:

```text
/home/jdsimon/mermaid/
├── logs/
├── passwords/
│   └── servercopy_credentials.csv
└── servers/
    └── .git/
```

Transfer `servercopy_credentials.csv` through the approved secure channel and
restrict its permissions:

```sh
chmod 600 /home/jdsimon/mermaid/passwords/servercopy_credentials.csv
```

Do not print, inspect in transcripts, or commit the credential registry.

## Check out `mermaid-ops`

```sh
mkdir -p /home/jdsimon/programs
cd /home/jdsimon/programs
git clone git@github.com:Bathymetrix/mermaid-ops.git
cd /home/jdsimon/programs/mermaid-ops
```

Confirm that both programs retain executable permissions:

```sh
test -x servercopy
test -x servercopy_cron
```

## Configure Healthchecks.io

Create:

```text
/home/jdsimon/programs/mermaid-ops/data/healthchecks_uuid.txt
```

The file contains exactly one private Healthchecks.io Check UUID. Blank lines
and comment lines are allowed. Restrict its permissions:

```sh
chmod 600 \
  /home/jdsimon/programs/mermaid-ops/data/healthchecks_uuid.txt
```

The file is ignored by Git. Configure the Healthchecks.io Check with:

```cron
30 7,15,23 * * *
```

Use the Frisius timezone and a grace period longer than the longest legitimate
synchronization. Configure human-facing alerts through Healthchecks.io
Integrations.

## Verify the installation

Use the explicit production interpreter for every verification command:

```sh
cd /home/jdsimon/programs/mermaid-ops

/home/jdsimon/miniforge3/envs/python3.12/bin/python3 \
  servercopy --version

/home/jdsimon/miniforge3/envs/python3.12/bin/python3 \
  servercopy_cron --version

MERMAID=/home/jdsimon/mermaid \
/home/jdsimon/miniforge3/envs/python3.12/bin/python3 \
  servercopy --check
```

Confirm that the servers repository is the exact clean worktree root:

```sh
git -C /home/jdsimon/mermaid/servers rev-parse --show-toplevel
git -C /home/jdsimon/mermaid/servers status --short
```

Then run the offline test suite:

```sh
/home/jdsimon/miniforge3/envs/python3.12/bin/python3 \
  -m unittest discover -s tests -v
```

Before installing cron, run the wrapper once manually:

```sh
MERMAID=/home/jdsimon/mermaid \
/home/jdsimon/miniforge3/envs/python3.12/bin/python3 \
  /home/jdsimon/programs/mermaid-ops/servercopy_cron
```

Confirm that the synchronization finishes, the servers repository contains the
expected commit or clean no-change result, the timestamped workflow log records
exit status zero, and Healthchecks.io records a successful run.

The initial remote listing and comparison may be quiet for approximately ten
minutes, including when no new files exist. That delay is expected. A
`servercopy` heartbeat during this phase means only that the `lftp` child is
still alive.

The include filters do not override remote permissions. An eligible top-level
file may still fail with `mirror: Access failed: Permission denied`; it then
remains absent locally and may cause `lftp` and the monitored workflow to
return nonzero. Investigate repeated or important access errors with the remote
server owner. Do not change remote permissions from `servercopy`.

## Install the production crontab

Edit the `jdsimon` user crontab with `crontab -e` and install exactly:

```cron
SHELL=/bin/bash
PATH=/usr/bin:/bin
MERMAID=/home/jdsimon/mermaid

30 7,15,23 * * * /home/jdsimon/miniforge3/envs/python3.12/bin/python3 /home/jdsimon/programs/mermaid-ops/servercopy_cron >> /home/jdsimon/mermaid/logs/servercopy_cron_cron.log 2>&1
```

Cron does not activate Conda. It launches `servercopy_cron` with the explicit
Miniforge interpreter, and the wrapper uses that same interpreter to launch
`servercopy`. The restricted `PATH` is still used to locate system `git` and
`lftp`.

The wrapper creates one timestamped log per invocation beneath:

```text
/home/jdsimon/mermaid/logs/servercopy_cron/
```

The outer cron log is:

```text
/home/jdsimon/mermaid/logs/servercopy_cron_cron.log
```

It captures cron-launch and pre-wrapper failures. The single-host lock is:

```text
/home/jdsimon/mermaid/logs/servercopy_cron.lock
```

Verify the installed schedule:

```sh
crontab -l
```

After the first scheduled execution, inspect the outer log, the new timestamped
workflow log, the servers repository, and the corresponding Healthchecks.io
event.

## Update the installation

Update only when no scheduled synchronization is active:

```sh
cd /home/jdsimon/programs/mermaid-ops
git status --short
git pull --ff-only

/home/jdsimon/miniforge3/envs/python3.12/bin/python3 \
  -m unittest discover -s tests -v

/home/jdsimon/miniforge3/envs/python3.12/bin/python3 \
  servercopy_cron --version
```

Review release notes and operational-version changes, then perform one manual
wrapper run before relying on the next schedule. The wrapper now pulls the
servers repository with fast-forward-only policy and pushes each commit it
creates; confirm that the checked-out production branch has a configured
upstream and non-interactive pull/push authentication.
