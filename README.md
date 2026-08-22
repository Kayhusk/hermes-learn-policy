# Hermes Learn Policy

> Hermes can learn. It can also get a little too enthusiastic.

Hermes Learn Policy helps Hermes agents save useful memories and skills without creating a second learning system behind the scenes.

It gives the model clear rules before it considers a learning write. It also blocks a small set of routes that should never bypass Hermes's built-in `memory` and `skill_manage` tools.

One agent or a small fleet. Same rules, separate notebooks.

![Hermes Learn Policy architecture](docs/architecture.png)

## Current status

The source is public, but the plugin is not released.

- Current source version: `0.8.3`
- No GitHub Release or version tag
- No Hermes community listing
- No npm or PyPI package
- No public license yet

Version 0.8.3 passed its compatibility checks with Hermes Agent `0.20.4`. Check it again after updating Hermes before using it in a long-running profile.

## What it does

- Adds short learning guidance before each model turn.
- Uses different guidance for regular work, automatic learning review, and Curator maintenance.
- Keeps USER facts tied to real user statements or another trusted source.
- Confirms that the exact skill file was read before a matching background update.
- Gives a rejected background skill write one honest retry, not a new filename and another lap.
- Blocks direct edits to USER, MEMORY, and skill files when the model should use Hermes's built-in tools.
- Blocks obvious private-key text from saved learning.
- Keeps Curator shell access read-only.

Hermes still checks, locks, writes, tracks, and rolls back every saved change.

## One agent or many

Install the plugin separately in every Hermes profile that should use it.

Each running profile keeps its own:

- learning guidance;
- short-lived read and retry records;
- USER, MEMORY, and skill files.

Profiles do not share plugin state. The plugin does not coordinate agents, copy memories between them, or read another profile's learning files.

Pinning the same commit across profiles gives every agent the same policy without turning them into one shared brain.

## How it works

1. Hermes asks the plugin for guidance before the model responds.
2. The model may decide that nothing should be saved. That is a valid result.
3. If the model proposes a learning write, the plugin checks the route and any retry rules.
4. Hermes's built-in tools make the final decision and perform the write.

The plugin registers three Hermes hooks and no tools the model can call:

| Hermes hook | Plain-English job |
|---|---|
| `pre_llm_call` | Add the right guidance to the current model request |
| `pre_tool_call` | Allow the proposed tool call or return a clear block reason |
| `post_tool_call` | Remember a successful skill read or a rejected learning write for this turn |

The added guidance exists only for the current model request. It does not rewrite the saved user message, past conversation, or Hermes system prompt.

[Read the technical architecture](docs/architecture.md) for the exact call sequence, saved outputs, retry rule, and Hermes compatibility checks.

## Install from source

There is no supported release yet. For evaluation, install an exact commit that you have reviewed instead of the moving `main` branch:

```bash
hermes plugins install Kayhusk/hermes-learn-policy \
  --ref <40-character-commit-sha> \
  --no-enable

hermes plugins enable hermes-learn-policy
```

Restart the Hermes process or gateway after enabling it.

The plugin needs no API key, environment variable, service, database, or extra Python package.

## Check the installation

```bash
hermes plugins list
hermes plugins doctor hermes-learn-policy --ci
```

`Plugin Doctor` should report version `0.8.3`, zero tools, and these hooks:

```text
pre_llm_call
pre_tool_call
post_tool_call
```

## After a Hermes update

Most of the plugin uses Hermes's documented hooks and profile-home resolver. Three small connections in `compat.py` read information from Hermes internals. A fourth restores one confirmed, short-lived skill-read marker before Hermes checks a matching update.

If Hermes changes one of those connections, the plugin refuses to start instead of pretending the policy still works.

Run this check before restarting profiles:

```bash
python3 -m unittest -v test_plugin.py
python3 -m py_compile __init__.py compat.py gate.py test_plugin.py
hermes plugins doctor . --ci
git diff --check
```

## Turn it off

```bash
hermes plugins disable hermes-learn-policy
hermes plugins remove hermes-learn-policy
```

Restart Hermes afterward.

The plugin saves no database or settings of its own. Removing it does not remove memories or skills that Hermes already accepted.

## Trust and limits

Hermes plugins run inside Hermes with the current user's permissions. The installer scans source before installation, but a scan is not a sandbox or a code review. Read the source and pin a commit you trust.

This plugin does not:

- write learning files itself;
- call a model or the network;
- read credentials;
- add commands, dashboards, or services;
- control writes that never pass through tools requested by the model;
- guarantee that every proposed memory deserves a permanent home.

There is no shadow memory or second Curator. The plugin has enough to do already.

## Development

```bash
python3 -m unittest -v test_plugin.py
python3 -m py_compile __init__.py compat.py gate.py test_plugin.py
hermes plugins doctor . --ci
git diff --check
```

The test file covers regular work, automatic review, Curator, exact skill reads, one-retry behavior, concurrent calls, direct-file blocks, multiplexed profiles, short-lived state, and Hermes compatibility changes.

See [CHANGELOG.md](CHANGELOG.md) for the short version history.

## License

No public license has been selected. Public source is available for inspection, but that alone does not grant permission to copy, modify, or redistribute it. A license will be chosen before release.
