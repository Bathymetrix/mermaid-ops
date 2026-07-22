# Servercopy Complete-Mirror Experiment

## Decision

Do not replace the current suffix-specific synchronization strategy with the
tested complete-recursive-mirror implementation. The repository was
intentionally restored to the previously working implementation, and the
experiment was abandoned before deployment.

Correctness and operational robustness currently take priority over reducing
the number of mirror commands.

## Implementations compared

The current implementation runs eight suffix-specific mirror commands for each
configured source. Each command identifies its remote selection and exact local
destination explicitly:

```text
mirror <options> --file=<remote-root>/*<suffix> \
    --target-directory=<output>/<user>
```

The stashed experiment removed suffix selection. It changed to the configured
remote directory with `cd` where needed, selected `<output>/<user>` with `lcd`,
and then ran one recursive mirror with no source or destination arguments:

```text
mirror --verbose --continue --overwrite --no-perms --parallel=4
```

The intended benefit was a simpler synchronization policy with one remote
comparison pass instead of the repeated passes caused by multiple mirror
operations.

The stash is not a minimal mirror-command patch. It also contains changes to
progress reporting, redaction, dry-run directory handling, the retained RUDICS
script, tests, and documentation. It should not be reapplied wholesale as a
production change.

## Observed result

During testing, the `kobeuni` endpoint produced no lftp output for 900 seconds.
The servercopy silence watchdog then terminated the process. The lack of output
does not establish what internal operation lftp was performing during that
interval.

The complete-mirror implementation therefore did not demonstrate usable
production behavior and was abandoned before deployment. Its changes remain in
git stash only as material for possible future investigation.

## Future work

Any further optimization should start with small, focused experiments against
one endpoint and measure observable behavior before replacing the production
synchronization strategy. A simpler architecture is not an improvement unless
it preserves correctness and unattended operational reliability.
