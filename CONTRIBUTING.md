# Contributing

Hermes Learn Policy depends on version-specific Hermes contracts. Changes must keep Hermes as the only durable learning writer and preserve foreground learning, profile isolation, native validation, and the documented retry rules.

## Before opening a pull request

1. Explain the behavior being changed and the Hermes contract it depends on.
2. Add a focused test for the intended behavior and one nearby case that must remain allowed.
3. Update the README or architecture document when public behavior or compatibility changes.
4. Keep new dependencies, network access, model calls, and new plugin tools out unless the change requires them.
5. Run the repository checks.

```bash
python3 -m unittest -v test_plugin.py
python3 -m py_compile __init__.py compat.py gate.py test_plugin.py
hermes plugins doctor . --ci
git diff --check
```

The plugin must fail registration when a required Hermes contract is unavailable. Do not replace that check with a partial fallback that changes policy behavior.
