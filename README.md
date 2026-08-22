# Hermes Learn Policy

Standalone Hermes plugin that dynamically guides native learning writers, bridges one verified native skill read across tool-worker contexts, and bounds autonomous rejection recovery without replacing Hermes's mutation system.

## Responsibility boundary

**Native Hermes owns** `memory` and `skill_manage`, target resolution, validation, capacity, locking, atomic writes, staging, ownership, provenance, rollback, pinning, archive/delete, and lifecycle.

**This plugin owns only:**

- lane-specific guidance immediately before each LLM decision;
- deterministic protection against direct learning-file writes and obvious private keys;
- a bounded ephemeral receipt for successful native `skill_view` results;
- replay of that receipt into Hermes's existing background-review read marker;
- one review-wide autonomous recovery budget;
- a strict read-only terminal allowlist for Curator.

It has no model tool, writer, database, service, daemon, alternate memory store, linter, rollback engine, or second Curator. One version-scoped native file resolver is reused so direct-route checks match Hermes's actual task CWD.

## Version 0.8.1

v0.8.1 preserves the three public hooks introduced in v0.8.0:

- `pre_llm_call`
- `pre_tool_call`
- `post_tool_call`

It adds no dependency and modifies no Hermes core file.

## Runtime flow

```text
foreground / background review / Curator
        |
        v
pre_llm_call
  -> record lane by session + turn
  -> append lane-specific policy to the API-bound user message
        |
        v
native model decision
        |
        +---- skill_view ----------------------------------+
        |                                                   |
        |                                            post_tool_call
        |                                      validate native success
        |                                      record exact path receipt
        |                                                   |
        +---- skill_manage / memory                         |
        |                                                   |
        v                                                   |
pre_tool_call <---------------------------------------------+
  -> enforce autonomous recovery budget
  -> replay exact receipt into native background read mark
  -> apply deterministic route/secret protection
        |
        v
native memory / skill_manage
        |
        v
post_tool_call
  -> observe native success or rejection
  -> never rewrite the native result
```

`pre_llm_call` context is dynamic and API-only. It does not modify the cached system prompt or past conversation.

## Lane policy

### Foreground

Foreground guidance is conditional. The user's task remains primary, no write is valid, and foreground user-directed learning retains the complete native tool capability. Autonomous recovery throttling does not apply.

### Automatic background review

The reviewer must classify USER, MEMORY, and skill ownership, load the two governance owners, inspect the catalogue and target, preserve unrelated USER/MEMORY clauses, and accept no write as a valid outcome.

After a skill rejection, only one same-owner retry is possible, and only after reading the exact target file again. A memory rejection ends learning writes for that review.

### Curator

Curator receives a separate skill-only policy. It preserves native Curator ownership, pins, provenance, and archive/delete behavior. Terminal remains available through a small standard-library read-only allowlist. Git is excluded entirely because repository configuration can execute external programs even for commands such as `git status`.

## Native read bridge

Installed Hermes records background `skill_view` reads in a `ContextVar`. Separate tool-worker contexts can lose that mark before the following `skill_manage` call.

v0.8.1 uses the smallest no-core bridge:

1. `post_tool_call` accepts a receipt only when the native `skill_view` result is a successful mapping whose name and requested supporting file match the call.
2. The native result's canonical absolute path is retained only in bounded in-process state for that session and turn.
3. `pre_tool_call(skill_manage)` selects only the receipt matching the same hashed skill identity and exact hashed target file.
4. The plugin calls Hermes's existing `mark_background_review_skill_read(Path)` function in the current tool context.
5. Native `skill_manage` performs every subsequent ownership, provenance, validation, read-before-write, and mutation decision.

Failed, malformed, mismatched, relative-path, unrelated-owner, and unrelated-file results create no usable receipt. The bridge imports no private writer, linter, lifecycle function, or fuzzy-patch implementation.

## Review-wide recovery

Recovery applies only to automatic background review and Curator.

- The first native skill rejection records the rejected tool, hashed skill owner, hashed exact target file, and current read generation.
- Changed arguments, another target file, a sibling skill, or a memory write cannot bypass that rejection.
- A successful same-owner exact-target `skill_view` after rejection arms one retry.
- Admission is consumed atomically before native execution, so concurrent duplicate calls yield exactly one allow.
- Retry success or failure closes learning writes for the rest of that review.
- A memory rejection closes learning writes immediately.
- Read-only diagnosis remains available.
- A new turn receives a fresh budget.

The first native result is never transformed or hidden. Plugin refusals identify `learning-policy` in the returned error.

## Bounded state

Three maps are each capped at 256 entries per plugin process:

- lane: session + turn -> lane label;
- read receipt: session + turn + hashed owner + hashed target -> generation + canonical native path;
- recovery: session + turn -> rejected tool, hashed owner, hashed exact target, generation, consumed, and closed.

Active autonomous state is never evicted. A new turn purges only superseded turns from the same session. Capacity pressure fails closed until bounded state is available again.

The plugin stores no learning content, USER/MEMORY text, raw tool argument object, or secret. The transient canonical receipt path may contain the on-disk skill directory name. State is not written to disk and cannot cross profile processes.

## Deterministic protection

`pre_tool_call` also:

- rejects obvious private-key material before model-dispatched `memory` or `skill_manage` writes;
- redirects direct `write_file` or `patch` attempts against current-profile USER, MEMORY, or local skill storage to native tools;
- resolves relative generic-file targets through Hermes's native task-aware resolver and the hook's `task_id`;
- resolves symlinks and lexical targets for supported direct file routes;
- refuses Curator terminal commands outside the read-only allowlist;
- fails closed on internal errors only after a native learning route is known;
- leaves unrelated tools and every safe native foreground `skill_manage` operation available.

## Compatibility boundary

`compat.py` contains four version-scoped adapters to installed Hermes:

- current write origin;
- native file-mutation target extraction;
- native task-aware file-path resolution;
- native ephemeral background-review skill-read marking.

The package does not import a private mutation, skill resolver, linter, ownership classifier, lifecycle function, or fuzzy-patch function. It reuses one native generic-file resolver solely to align route protection with file-tool behavior. Plugin Doctor, the focused suite, and the real native bridge test are the upgrade gate.

## Explicit limits

This plugin does not:

- modify Hermes core;
- create, patch, delete, stage, roll back, reconcile, archive, or lint learning content itself;
- intercept internal dashboard/TUI/approved-replay writes that bypass model-dispatched tools;
- guarantee that a model proposes useful durable learning;
- treat safe rejection as proof that learning quality succeeded;
- make synthetic clean-profile evidence a substitute for mature-profile natural work.

## Evidence selecting v0.8.1

The v0.8.0 natural pilot proved dynamic foreground delivery and native safety. It also found:

- Apollo received ten skill rejections across two reviews by changing files, arguments, and owners after failures.
- Successful `skill_view` calls still preceded native `not loaded in this review turn` errors.
- Talos made one promising USER write but no profile produced a successful skill update or new skill creation.

Those observations select the bridge and review-wide budget. They do not authorize a shadow writer.

## Verification

Run from this directory:

```bash
python3 -m unittest -v test_plugin.py
python3 -m py_compile __init__.py compat.py gate.py test_plugin.py
hermes plugins doctor . --ci
git diff --check
```

The focused suite includes:

- dynamic foreground/background/Curator prompt selection;
- real native background skill creation followed by a bridged native patch;
- exact supporting-file receipt isolation;
- exact rejected-file recovery binding, including a freshly read same-owner file-switch attempt;
- malformed and mismatched receipt refusal;
- changed-argument, sibling-owner, file-switch, and memory-workaround refusal;
- one sequential and concurrent retry allowance;
- retry success/failure closure;
- foreground capability preservation;
- bounded state without raw learning content or argument objects;
- active-state capacity pressure with fail-closed recovery;
- task-CWD relative direct-file, private-key, and Curator terminal adversarial cases, with every Git command blocked;
- compatibility-adapter drift failure.

## Rollout discipline

Adopt one verified commit exactly. Verify per profile:

- plugin version and enabled state;
- checkout cleanliness and exact file hashes;
- unchanged config, credentials, SOUL, USER, MEMORY, skills, cron, MCP, and gateway identity except for the explicitly installed plugin package;
- process and fresh-session pickup separately from persisted bytes.

A disposable clean profile can prove creation and memory mechanics. Existing profiles remain the natural dense-catalog regression lane.
