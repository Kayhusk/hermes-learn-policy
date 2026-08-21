# Hermes Learn Policy

Standalone Hermes plugin that dynamically guides native learning writers and protects native learning routes without replacing Hermes's mutation system.

## Responsibility boundary

**Native Hermes owns** `memory` and `skill_manage`, target resolution, validation, capacity, locking, atomic writes, staging, ownership, provenance, rollback, pins, linting, and archive/delete lifecycle.

**Hermes Learn Policy owns only:**

- lane-aware `pre_llm_call` guidance for foreground turns, automatic background review, and Curator;
- deterministic `pre_tool_call` protection for direct durable-learning file bypasses, obvious private keys, destructive Curator terminal commands, and unchanged retries after native rejection;
- observational `post_tool_call` tracking of native rejection and relevant `skill_view` evidence in bounded process memory.

It does not write USER, MEMORY, or skills itself.

## Dynamic native path

```text
foreground AIAgent turn
background_review AIAgent turn
Curator AIAgent turn
        |
        v
pre_llm_call -> lane policy appended to the API-bound user message
        |
        v
native model decision
        |
        v
pre_tool_call -> deterministic route/safety/retry checks
        |
        v
native memory / skill_manage
        |
        v
post_tool_call -> observe native outcome only
```

Hermes binds write origin before `pre_llm_call`. The hook runs once for the actual turn and its context is appended to the API-only user message, preserving the cached system prompt and clean transcript. Background review uses normal `AIAgent.run_conversation()` with origin `background_review`. Curator uses normal `AIAgent.run_conversation()` with `platform="curator"`.

## Lane policy

### Foreground

The current user task remains primary. Learning policy applies only when the turn considers `memory` or `skill_manage`.

- USER holds stable user facts and preferences.
- MEMORY holds durable environment and agent facts, written declaratively.
- Skills hold reusable class-level procedures and decision methods.
- Replacements preserve every unrelated clause.
- Volatile status, task history, completion receipts, secrets, duplicated meaning, misplaced procedures, and unnecessary machine-local paths are not saved.

### Automatic background review

- Inspect existing owners through native `skills_list` and `skill_view` before writing.
- A no-write result is valid.
- Update the current owner when native policy permits; create only after confirmed ownership absence.
- Do not create siblings to bypass ownership or read-before-write rejection.
- After native rejection, only a meaningfully changed, cause-directed recovery is valid.

### Curator

Curator receives a separate skill-only policy. It preserves native Curator ownership, pins, provenance, and archive/delete behavior. Terminal remains available through a small standard-library read-only command allowlist; other autonomous terminal commands are refused so durable changes stay on native `skill_manage`.

## Bounded rejection handling

`post_tool_call` records only:

- session ID;
- turn ID;
- SHA-256 of tool name plus arguments;
- the relevant skill-view generation.

`pre_llm_call` records only the lane label for the same session and turn so `pre_tool_call` can distinguish Curator from ordinary background review without relying on an unavailable pre-tool platform field.

Raw arguments, skill names, learning content, and secrets are never stored in retry state. Arguments and skill identities are hashed before storage. Rejection, view, and lane maps are each capped at 256 entries per plugin process.

`pre_tool_call` refuses an unchanged learning call after native rejection. Changed arguments are allowed. A successful `skill_view` for the same skill permits one same-argument retry and consumes that allowance atomically; an unrelated skill view does not. If native rejects again, the next unchanged attempt is refused.

## Deterministic protection

The plugin also:

- redirects generic `write_file` or `patch` calls targeting current-profile USER, MEMORY, or local skills back to native learning tools;
- rejects obvious private-key material before model-dispatched `memory` or `skill_manage` writes;
- fails closed on internal errors only after a native learning route is known;
- leaves unrelated tools and every native `skill_manage` operation available.

## Compatibility boundary

`compat.py` contains two version-scoped read-only adapters to installed Hermes:

- current write origin;
- native file-mutation target extraction;

It imports no private mutation, resolver, linter, lifecycle, ownership, terminal classifier, or fuzzy-patch function. Curator terminal classification uses only `shlex` and an explicit read-only command set. Plugin Doctor and focused tests are the upgrade gate.

## Explicit limits

This plugin does not:

- modify Hermes core;
- mutate, rewrite, roll back, stage, reconcile, archive, or lint learning content;
- add a second memory or skill tool;
- reconstruct native patches or target resolution;
- persist rejection receipts;
- intercept internal dashboard/TUI/approved-replay writes that bypass model-dispatched tools;
- guarantee that a native background patch succeeds after `skill_view` when the installed host loses its read mark across tool-worker contexts.

A read-receipt compatibility bridge is deliberately excluded from v0.8. Add it only if the dynamic pilot proves successful existing-owner updates still require one.

## Evidence that selected v0.8

The v0.7 fleet pilot proved the frozen policy section was present but too distant from the live decision:

- Apollo repeated one rejected patch three times.
- Talos continued after rejection and rewrote USER clauses without the required live-target read.
- Orion stopped after one rejection but produced no successful owner update.
- Metis did not adopt v0.7 in a fresh runtime.

v0.8 moves semantic guidance to the same native `pre_llm_call` seam used by Ponytail and adds bounded native-result observation instead of adding shadow mutation machinery.

## Check

```bash
python3 -m unittest -v test_plugin.py
hermes plugins doctor . --ci
python3 -m py_compile __init__.py compat.py gate.py test_plugin.py
```

Rollout is exact-commit only to approved non-default profiles. Gateway restart and fresh-session pickup remain operator-owned.

Sources:

- https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks
- installed `agent/turn_context.py`
- installed `agent/background_review.py`
- installed `agent/curator.py`
- installed `model_tools.py`
