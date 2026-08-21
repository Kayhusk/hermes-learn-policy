# Hermes Learn Policy

Standalone Hermes plugin that gives native learning writers one cache-safe quality contract and protects native learning routes without replacing Hermes's mutation system.

## Responsibility boundary

**Native Hermes owns** `skill_manage` and `memory` mutation, target resolution, validation, capacity, locking, atomic writes, staging, background ownership, read-before-write checks, security rollback, pins and archive/delete behavior, the mutation ledger, lifecycle facts, provenance, and native skill linting.

**Hermes Learn Policy owns only:**

- registering one bounded system prompt section for ordinary sessions so foreground agents and inherited automatic background reviewers receive the same conditional learning guidance;
- returning empty section content for the separate `platform="curator"` consolidation runtime;
- redirecting generic `write_file` and `patch` attempts against current-profile `MEMORY.md`, `USER.md`, or `skills/` back to their native tools;
- rejecting obvious private-key material before a model-dispatched `skill_manage` or `memory` write.

`compat.py` contains one version-scoped private read: Hermes's file-mutation target extractor. It imports no write-origin, resolver, linter, mutation, lifecycle, ownership, or fuzzy-match function. Adapter drift fails registration because route protection would otherwise be false.

## Cache-safe quality path

Hermes documents `register_system_prompt_section` as the owner for bounded, durable plugin guidance. Hermes renders the section once for a new ordinary session and freezes it into the cached system prompt. The main agent receives it, and automatic background review inherits that same cached prompt without a second injection. Curator gets empty content.

The policy applies only when the model considers a native learning write:

- USER holds stable user facts and preferences;
- MEMORY holds durable agent or environment facts and conventions, written declaratively;
- skills hold reusable class-level procedures and decision methods;
- before a memory write, the model loads `profile-memory-governance`, reads the complete current target, and preserves unrelated clauses verbatim or makes no write;
- before a skill write, the model loads `skill-governance` and inspects the existing owner and linked references through native discovery;
- same-responsibility guidance updates its current owner, a confirmed ownership gap may create a new owner, and related but distinct responsibilities remain separate and linked;
- multi-file learning is kept coherent: no support-file half-write, repeated rejection, or sibling workaround;
- volatile status, task history, completion receipts, misplaced procedures, duplication, secrets, and unnecessary machine-local detail stay with their proper owners or are not saved;
- replacing a consolidated entry preserves every unaffected clause instead of silently deleting facts to make room.

The model still decides whether to write and uses only native `memory` and `skill_manage`. The plugin does not inspect or rewrite persisted content afterward.

## Explicit limits

This plugin does not:

- inject a second background-review prompt or alter the system prompt after a session begins;
- inject learning policy into the separate Curator consolidation runtime;
- rewrite, roll back, stage, reconcile, archive, or otherwise mutate learning content itself;
- classify skill ownership or override Hermes's bundled, Hub, external, project, pinned, or curator policy;
- rerun Hermes's linter, correlate lifecycle events, or maintain mutation receipts;
- reconstruct fuzzy patches or claim package finalization;
- intercept terminal writes, approved internal replay, dashboard/TUI internal mutations, or every non-tool learning path;
- protect configured external skill directories from generic file tools;
- claim rollout, fleet enforcement, or first-write quality before live pilots prove it.

## Corrected course

1. **One policy section:** keep semantic learning quality in the cache-safe ordinary-session section; keep only deterministic route and private-key protections in `pre_tool_call`.
2. **Local proof:** verify ordinary-session rendering, Curator exclusion, native capability pass-through, consolidated-clause preservation, adapter failure, and deterministic safety with focused tests and Plugin Doctor.
3. **Fresh-session adoption:** update the selected profile checkout and begin a new session after its gateway restart so Hermes freezes the corrected section into that session.
4. **Fleet advisory pilot:** observe real foreground and automatic skill or MEMORY/USER writes across approved non-default profiles; preserve writer and profile identity in every finding.
5. **v0.6 evidence:** owner discovery occurred, but automatic reviewers still repeated rejected skill writes and one Apollo USER replacement dropped unrelated durable clauses.
6. **v0.7 correction:** route memory and skill writers through the existing governance skills, require complete-target preservation for memory replacement, and make one rejection end the review.
7. **Final prompt-first gate:** run isolated USER-preservation, duplicate-owner, new-owner, and rejection-stop pilots. If they fail, keep the plugin advisory and escalate the native writer/read-context defects instead of adding shadow machinery.
8. **Promotion gate:** semantic quality remains advisory. Promote only deterministic trust-boundary rules with safe remediation and positive plus adjacent-negative evidence.

## Check

```bash
python3 -m unittest -v test_plugin.py
hermes plugins doctor . --ci
```

Source contract: [Hermes Event Hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks), especially cache-safe system prompt sections, plus installed `agent/background_review.py` for inherited-prompt behavior.
