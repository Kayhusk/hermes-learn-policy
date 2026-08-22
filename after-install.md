# Hermes Learn Policy is installed

Enable it if the installer left it off:

```bash
hermes plugins enable hermes-learn-policy
```

Restart Hermes or the active gateway, then check it:

```bash
hermes plugins list
hermes plugins doctor hermes-learn-policy --ci
```

The plugin adds no slash commands or tools the model can call. It works through three Hermes hooks and leaves every saved write to `memory` or `skill_manage`.

Running several agents? Install and enable the same pinned commit in each profile. Their plugin state and learning files stay separate.

That is the whole setup. No API key, no database, no surprise dashboard.

Read [README.md](README.md) for use and limits. Read [docs/architecture.md](docs/architecture.md) for the technical flow.
