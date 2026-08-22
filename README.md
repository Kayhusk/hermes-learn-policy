# Hermes Learn Policy

Hermes Learn Policy governs when a Hermes agent may save USER facts, MEMORY facts, or skills. It adds learning guidance before model calls and checks learning-related tool calls before Hermes runs them. Hermes remains the only component that writes lasting learning files.

## What it does

- Selects different guidance for foreground work, automatic learning review, and Curator maintenance.
- Requires USER facts from autonomous reviews to be supported by a real user message or an independently verified source.
- Carries a confirmed skill read into the matching background update.
- Allows one same-file skill retry after a rejected autonomous write.
- Blocks direct edits to USER, MEMORY, and skill files when the native learning tools should own the change.
- Rejects obvious private-key text in proposed learning.
- Limits Curator terminal use to approved read-only commands.

Hermes continues to own validation, locking, persistence, history, and rollback.

## Profile isolation

Install the plugin separately in each Hermes profile that needs the policy. Every profile keeps its own guidance, short-lived read and retry records, USER file, MEMORY file, and skills. A shared gateway does not change this boundary.

The plugin does not coordinate profiles or copy learning between them. Pin the same commit across profiles to apply the same policy while preserving isolation.

## How it works

The plugin registers three Hermes hooks and no model-callable tools:

| Hermes hook | Responsibility |
|---|---|
| `pre_llm_call` | Adds the guidance for the current work type |
| `pre_tool_call` | Allows the proposed call or blocks it with a specific reason |
| `post_tool_call` | Records a successful skill read or rejected learning write for the current turn |

The model may choose not to save anything. When it proposes a write, Hermes's built-in `memory` and `skill_manage` tools make the final decision and perform the change.

Hook guidance applies only to the current model request. It does not alter the stored user message, earlier conversation, or Hermes system prompt.

See the [technical architecture](docs/architecture.md) for the runtime flow, retry rule, short-lived state, and Hermes dependencies.

## Install from source

Version `0.8.3` has been tested with Hermes Agent `0.20.4`. Install a reviewed commit rather than the moving `main` branch:

```bash
hermes plugins install Kayhusk/hermes-learn-policy \
  --ref <40-character-commit-sha> \
  --no-enable

hermes plugins enable hermes-learn-policy
```

Restart the Hermes process or gateway after enabling the plugin.

The plugin needs no API key, environment variable, service, database, or extra Python package.

## Verify

Check the installed plugin:

```bash
hermes plugins list
hermes plugins doctor hermes-learn-policy --ci
```

Plugin Doctor should report version `0.8.3`, no tools, and the three hooks listed above.

From a source checkout, run:

```bash
python3 -m unittest -v test_plugin.py
python3 -m py_compile __init__.py compat.py gate.py test_plugin.py
hermes plugins doctor . --ci
git diff --check
```

Run the source checks after changing the plugin or updating Hermes. The plugin refuses to register when a required Hermes contract is unavailable.

## Disable or remove

```bash
hermes plugins disable hermes-learn-policy
hermes plugins remove hermes-learn-policy
```

Restart Hermes afterward. Removing the plugin does not delete learning that Hermes previously accepted.

## Security and scope

Hermes plugins run with the current user's permissions. The installer scans source, but that scan is not a sandbox or a code review. Review the source and pin a commit you trust.

The plugin does not:

- write learning files itself;
- call a model or network service;
- read credentials;
- add commands, dashboards, or services;
- control writes that do not pass through model-requested tools;
- guarantee that every accepted learning item is useful.

## Changelog

[CHANGELOG.md](CHANGELOG.md) records changes by source version.

## License

No license is granted for this repository. Source visibility does not grant permission to copy, modify, or redistribute it.
