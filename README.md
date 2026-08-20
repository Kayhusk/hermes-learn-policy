# Hermes Learning Quality Gate

Standalone Hermes plugin for bounded learning-write safety and advisory quality diagnostics.

Current slice:

- preserves native `skill_manage` create, edit, fuzzy patch, delete/archive, references, templates, scripts, and assets;
- blocks direct file-tool writes to current-profile durable learning files;
- blocks explicit `file_path="SKILL.md"` bypass shapes so native structural validation/lifecycle stays in charge;
- blocks obvious private-key material before persistence;
- appends bounded diagnostics after successful autonomous background create/edit writes while foreground writes remain untouched;
- fails closed only for relevant learning calls.

The private coupling is isolated in `compat.py`, currently adapting Hermes write origin and native file-mutation target extraction. Registration and Plugin Doctor fail clearly if either symbol moves. Future native provenance, resolver, linter, or lifecycle reads belong in the same compatibility boundary only when an active slice uses them.

Semantic diagnostics are advisory. The plugin does not claim package transactions, authoritative cross-root provenance, internal non-tool mutation coverage, or fleet rollout.

## Check

```bash
python3 -m unittest -v test_plugin.py
hermes plugins doctor . --ci
```
