# Hermes Learning Quality Gate

Standalone Hermes plugin scaffold for deterministic admission checks before autonomous learning writes persist.

Current slice:

- registers the public `pre_tool_call` hook;
- routes `skill_manage` and `memory` learning calls;
- blocks direct writes to governed skill, MEMORY, and USER files;
- blocks bundled, Hub-installed, and plugin-owned skill mutation;
- fails closed when provenance classification errors.

Full semantic admission policy and rollout are intentionally not included yet.

## Check

```bash
python3 -m unittest -v test_plugin.py
hermes plugins doctor . --ci
```
