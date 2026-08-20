# Hermes Learn Policy

Standalone Hermes plugin that guides the native background learning reviewer before it writes and protects native learning routes without replacing Hermes's mutation system.

## Responsibility boundary

**Native Hermes owns** `skill_manage` and `memory` mutation, target resolution, validation, locking, atomic writes, staging, background ownership, read-before-write checks, security rollback, pins and archive/delete behavior, the mutation ledger, lifecycle facts, provenance, and native skill linting.

**Hermes Learn Policy owns only:**

- injecting bounded learning-quality guidance through `pre_llm_call` when Hermes identifies the active turn as `background_review`, excluding the separate `platform="curator"` consolidation runtime;
- redirecting generic `write_file` and `patch` attempts against current-profile `MEMORY.md`, `USER.md`, or `skills/` back to their native tools;
- rejecting obvious private-key material before a model-dispatched `skill_manage` or `memory` write.

`compat.py` contains the only version-scoped private reads: Hermes's write-origin signal and its file-mutation target extractor. It imports no resolver, linter, mutation, lifecycle, ownership, or fuzzy-match function. File-target adapter drift fails registration because route protection would be false; write-origin drift disables only the optional learning prompt.

## Prompt-first quality path

Hermes's automatic review fork is a normal `AIAgent`. Installed Hermes binds its write origin to `background_review` before `pre_llm_call`, then appends plugin context to the API-bound user message for that review turn while leaving the clean transcript unchanged. The review fork also uses Hermes's native persistence isolation. Hermes Learn Policy uses that existing path to guide classification before any write:

- USER holds stable user facts and preferences;
- MEMORY holds durable agent or environment facts and conventions, written declaratively;
- skills hold reusable class-level procedures and decision methods;
- volatile status, task history, completion receipts, misplaced procedures, duplication, secrets, and unnecessary machine-local detail stay with their proper owners or are not saved.

The reviewer still decides whether to write and uses only native `memory` and `skill_manage`. The plugin does not inspect or rewrite persisted content afterward.

## Explicit limits

This plugin does not:

- inject learning policy into foreground or main-agent turns;
- rewrite, roll back, stage, reconcile, archive, or otherwise mutate learning content itself;
- classify skill ownership or override Hermes's bundled, Hub, external, project, pinned, or curator policy;
- rerun Hermes's linter, correlate lifecycle events, or maintain mutation receipts;
- reconstruct fuzzy patches or claim package finalization;
- intercept terminal writes, approved internal replay, dashboard/TUI internal mutations, or every non-tool learning path;
- protect configured external skill directories from generic file tools;
- claim installation, rollout, fleet enforcement, or first-write quality before a live pilot proves it.

## Corrected course

1. **Prompt-first contract:** keep semantic learning quality in the targeted `pre_llm_call` context; keep only deterministic route and private-key protections in `pre_tool_call`.
2. **Local proof:** verify background-only prompt injection, foreground silence, native capability pass-through, adapter drift, and deterministic safety with focused tests and Plugin Doctor.
3. **Orion pilot:** observe one real automatic skill write and one real automatic MEMORY/USER write. Each must be clean on its first native write, preserve unrelated content, and avoid unnecessary adjacent mutations.
4. **Evidence gate:** if prompt-first guidance misses a concrete case, record that exact false negative before considering one bounded fallback. Do not prebuild scanners, correction loops, receipts, or lifecycle machinery.
5. **Promotion gate:** semantic quality remains advisory. Promote only deterministic trust-boundary rules with safe remediation and positive plus adjacent-negative evidence.
6. **Rollout:** expand beyond Orion only after both first-write quality paths pass and Eddy explicitly approves the rollout.

## Check

```bash
python3 -m unittest -v test_plugin.py
hermes plugins doctor . --ci
```

Source contract: [Hermes Event Hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks) and installed `agent/turn_context.py` plus `agent/background_review.py` for the version-scoped background-review path.
