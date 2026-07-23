# mermaid-ops

These instructions supplement:

- the global Codex AGENTS (`~/.codex/AGENTS.md`)
- the shared MERMAID AGENTS (`$MERMAID/AGENTS.md`)

The shared MERMAID AGENTS are considered part of this repository's
instructions.

If they cannot be located or read for any reason, stop and notify the user
before making changes.

If instructions conflict, this file takes precedence.

## Repository Scope

`mermaid-ops` owns operational automation for the MERMAID ecosystem.

Its responsibilities include:

- mirroring remote servers;
- operational logging and audit trails;
- synchronization tooling;
- unattended operational workflows.

It does **not** own normalization, scientific interpretation, catalog
generation, timeline construction, or downstream data products.

## Design Philosophy

Keep operational scripts small, direct, deterministic, and easy to audit.

Prefer one straightforward implementation over reusable frameworks,
provider/plugin architectures, or installable packages unless those become
necessary.

The canonical `servercopy` implementation is one directly executable,
standard-library-only Python script targeting Python 3.14.

## Credentials

Treat:

`$MERMAID/passwords/`

as strictly out of bounds.

Never inspect, enumerate, search, print, copy, upload, transmit, or expose
credential files or their metadata.

Operational scripts may refer to credential paths but must never read or
display credential contents.

The canonical `servercopy` credential registry is:

`$MERMAID/passwords/servercopy_credentials.csv`

Its intentionally simple headerless format is:

`login,password`

Logical users and authentication logins are separate concepts. Multiple
logical users may legitimately share one authenticated login.

## Server Operations

Design synchronization tools for unattended cron execution.

Normal execution should:

- never prompt interactively;
- produce deterministic exit status;
- clearly identify per-source failures;
- produce useful audit logs.

Dry-run and validation modes must produce no operational side effects unless
explicitly documented.

Do not combine mirroring with downstream processing such as normalization,
conversion, Git operations, or exports.

## Mirroring

Mirror destinations always terminate at:

`<output>/<logical_user>/`

where `<output>` defaults to:

`~/mermaid/servers/`

Keep logical users separate even when they authenticate through the same
remote account.

Preserve the current run-ledger schema:

`user,result,start,end,ver`

unless the user explicitly requests a schema change.

Redact credential-bearing URL user information from all logs, summaries,
terminal output, and transcript files.

## Instrument Identity

When deriving a MERMAID instrument identifier from filenames, combine:

- the letter immediately preceding the final hyphen;
- the numeric serial following that hyphen, left-padded to four digits.

Examples:

- `452.020-P-0057.vit` → `P0057`
- `452.020-P-06.vit` → `P0006`

Ignore suffixes such as `_old` when deriving identifiers.

## Versioning

`SERVERCOPY_RUDICS_VERSION` represents operational behavior, not package
releases.

Increment it whenever CLI behavior, mirroring behavior, logging, ledger
format, validation semantics, or other operator-visible behavior changes
meaningfully.

## Repository Hygiene

Do not commit:

- credentials;
- mirrored server data;
- generated synchronization outputs.

Keep README files focused on repository purpose, operational usage,
requirements, and safety rather than branding.

Use plain ASCII unless an existing file intentionally uses another character
set.

## Git

When suggesting a commit message with a body, format the elaboration as
hyphen-prefixed phrase fragments rather than full sentences.
