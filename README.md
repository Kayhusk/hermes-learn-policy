# Hermes Learn Policy

Standalone Hermes plugin that protects native learning routes and adds bounded, advisory quality signals without replacing Hermes's mutation system.

## Responsibility boundary

**Native Hermes owns** `skill_manage` and `memory` mutation, target resolution, write approval and staging, background ownership, read-before-write checks, structure and size validation, security rollback, pins and archive/delete behavior, the mutation ledger, lifecycle facts, provenance, and native skill linting.

**Hermes Learn Policy owns only:**

- redirecting generic `write_file` and `patch` attempts against current-profile `MEMORY.md`, `USER.md`, or `skills/` back to their native tools;
- rejecting obvious private-key material before a model-dispatched `skill_manage` or `memory` write;
- appending its own semantic diagnostics after successful autonomous `create` or full `edit` calls, while leaving foreground writes unchanged.

`compat.py` contains the only version-scoped private reads: Hermes's write-origin signal and its file-mutation target extractor. It imports no resolver, linter, mutation, lifecycle, or fuzzy-match function. File-target adapter drift fails registration because route protection would be false; write-origin drift disables only optional diagnostics.

## Explicit limits

This plugin does not:

- classify skill ownership or override Hermes's bundled, Hub, external, project, pinned, or curator policy;
- block any native `skill_manage` action or path shape unless the proposed content contains obvious private-key material;
- rerun Hermes's linter, correlate lifecycle events, or maintain mutation receipts;
- reconstruct fuzzy patches or claim package finalization for incremental reference/script/template/asset writes;
- intercept terminal writes, approved internal replay, dashboard/TUI internal mutations, or every non-tool learning path;
- protect configured external skill directories from generic file tools;
- claim universal learning-write coverage, installation, rollout, or fleet enforcement.

## Corrected course

1. **Native boundary:** keep the responsibility and operation matrix tied to current Hermes docs and installed source before changing policy.
2. **Local contract:** maintain only route protection, explicit private-key rejection, and custom advisory diagnostics with positive and adjacent-negative fixtures.
3. **Orion pilot:** after explicit install/enable approval, observe semantic diagnostics in one profile. Record false positives, false negatives, and whether the agent self-corrects without reducing native capability.
4. **Memory and USER quality:** treat durability guidance as a separate slice. Trace their actual model-dispatch and internal mutation paths first; reuse native scanning, limits, locking, and atomic batches rather than duplicating them.
5. **Promotion gate:** promote a diagnostic only when a deterministic invariant, safe remediation, positive fixture, adjacent non-trigger, and pilot evidence all support that exact rule. Otherwise it remains advisory.
6. **Coverage gaps:** request a public Hermes capability only after a real accepted rule requires unavailable origin, resolved provenance, post-mutation bytes, or finalization. Do not emulate the missing contract with private lifecycle machinery.
7. **Rollout:** install, enable, publish, or expand beyond the pilot only with explicit approval and direct runtime readback.

## Check

```bash
python3 -m unittest -v test_plugin.py
hermes plugins doctor . --ci
```

Source contract: [Hermes Event Hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks) and [Hermes Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills).
