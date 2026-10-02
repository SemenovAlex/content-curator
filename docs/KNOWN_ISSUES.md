# Known live-source discrepancies

The implementation follows the supplied technical specification as the source of truth for acceptance cases. Live publisher metadata can nevertheless change or reveal a discrepancy in the specification.

## One Useful Thing — acceptance date

The supplied specification expects:

- source: `one_useful_thing`
- requested day: `2026-08-23`
- title: `An opinionated guide to which AI to use to do stuff`

A current web check of the publisher/search index reports that article as published on **2026-07-23**, not 2026-08-23. The acceptance script intentionally keeps `2026-08-23` because it mirrors the provided specification; therefore this single live acceptance case may fail until the expected date is confirmed and the specification is corrected.

Do not weaken date validation to make this case pass. The ingest contract forbids substituting the requested date when a trustworthy publication date differs.

## OpenClaw exec mode — specification vs strict allowlist

The supplied specification says `exec.mode = auto`, while its Definition of Done also requires the `curator` agent to have access only to the required CLI. In current OpenClaw, `auto` uses allowlist matching first but can send eligible allowlist misses to an automatic reviewer, which may grant a one-time execution. That is broader than a strict single-binary boundary.

`docs/VPS_SETUP.md` therefore deliberately uses:

```bash
openclaw config set agents.entries.curator.tools.exec.mode allowlist
```

with the only manual Gateway allowlist entry being `/opt/content-curator/.venv/bin/curator`. This is a documented hardening deviation from the literal `auto` line in the specification and better satisfies the stronger security/Definition-of-Done requirement. If exact textual conformance to the spec is preferred over strict enforcement, change that one setting back to `auto`.
