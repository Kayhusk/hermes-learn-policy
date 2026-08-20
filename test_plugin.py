import importlib.util
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "hermes_learn_policy",
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PluginContractTest(unittest.TestCase):
    def test_registers_only_route_protection_and_custom_diagnostics(self):
        plugin = load_plugin()

        class Context:
            def __init__(self):
                self.hooks = {}

            def register_hook(self, name, callback):
                self.hooks[name] = callback

        ctx = Context()
        plugin.register(ctx)

        self.assertEqual(set(ctx.hooks), {"pre_tool_call", "transform_tool_result"})
        self.assertFalse(hasattr(plugin, "classify"))
        self.assertFalse(hasattr(plugin, "evaluate"))
        for callback in ctx.hooks.values():
            self.assertTrue(
                any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD
                    for parameter in inspect.signature(callback).parameters.values()
                )
            )

    def test_preserves_every_native_skill_manage_capability(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            operations = (
                {"action": "create", "name": "new", "content": "safe"},
                {"action": "edit", "name": "custom", "content": "safe"},
                {"action": "patch", "name": "custom", "old_string": "a", "new_string": "b"},
                {"action": "delete", "name": "custom", "absorbed_into": ""},
                {"action": "write_file", "name": "custom", "file_path": "references/api.md", "file_content": "safe"},
                {"action": "write_file", "name": "custom", "file_path": "templates/report.md", "file_content": "safe"},
                {"action": "write_file", "name": "custom", "file_path": "scripts/check.py", "file_content": "safe"},
                {"action": "write_file", "name": "custom", "file_path": "assets/example.txt", "file_content": "safe"},
                {"action": "patch", "name": "custom", "file_path": "references/api.md", "old_string": "a", "new_string": "b"},
                {"action": "remove_file", "name": "custom", "file_path": "references/api.md"},
                {"action": "write_file", "name": "custom", "file_path": "SKILL.md", "file_content": "safe"},
                {"action": "patch", "name": "custom", "file_path": "SKILL.md", "old_string": "a", "new_string": "b"},
                {"action": "remove_file", "name": "custom", "file_path": "SKILL.md"},
            )
            for args in operations:
                self.assertIsNone(plugin.pre_tool_call("skill_manage", args, home=home), args)

            with patch.object(gate, "current_write_origin", return_value="background_review"):
                self.assertIsNone(
                    plugin.pre_tool_call(
                        "skill_manage",
                        {"action": "patch", "name": "bundled", "old_string": "a", "new_string": "b"},
                        home=home,
                    )
                )

    def test_blocks_direct_learning_file_bypasses_and_private_keys(self):
        plugin = load_plugin()
        private_key = "-----BEGIN " + "RSA PRIVATE KEY-----"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            memories = home / "memories"
            memories.mkdir(parents=True)
            alias = root / "memory-alias"
            alias.symlink_to(memories, target_is_directory=True)

            blocked = (
                ("write_file", {"path": str(home / "memories" / "MEMORY.md"), "content": "x"}),
                ("write_file", {"path": str(alias / "MEMORY.md"), "content": "x"}),
                ("patch", {"mode": "replace", "path": str(home / "skills" / "x" / "SKILL.md")}),
                (
                    "patch",
                    {
                        "mode": "patch",
                        "patch": (
                            "*** Begin Patch\r\n"
                            f"*** Update File: {home / 'memories' / 'USER.md'}\r\n"
                            "@@\r\n-old\r\n+new\r\n"
                            "*** End Patch\r\n"
                        ),
                    },
                ),
                ("skill_manage", {"action": "create", "name": "x", "content": private_key}),
                ("skill_manage", {"action": "patch", "name": "x", "old_string": "a", "new_string": private_key}),
                ("skill_manage", {"action": "write_file", "name": "x", "file_path": "references/key.txt", "file_content": private_key}),
                ("memory", {"action": "add", "target": "memory", "content": private_key}),
                ("memory", {"target": "memory", "operations": [{"action": "add", "content": private_key}]}),
            )
            for tool_name, args in blocked:
                result = plugin.pre_tool_call(tool_name, args, home=home)
                self.assertEqual(result["action"], "block", (tool_name, args))
                self.assertIn("learning-policy", result["message"])

            self.assertIsNone(
                plugin.pre_tool_call(
                    "write_file", {"path": str(home / "notes.md"), "content": "safe"}, home=home
                )
            )

    def test_fails_closed_only_after_a_native_learning_route_is_known(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        with patch.object(gate, "_pre_decision", side_effect=RuntimeError("boom")):
            for tool_name in ("skill_manage", "memory"):
                result = plugin.pre_tool_call(tool_name, {}, home=Path("/tmp"))
                self.assertEqual(result["action"], "block")
            self.assertIsNone(plugin.pre_tool_call("terminal", {"command": "true"}))
            self.assertIsNone(plugin.pre_tool_call("write_file", {"path": "/tmp/notes"}))

    def test_adapter_drift_disables_only_optional_advice(self):
        plugin = load_plugin()
        compat = sys.modules["hermes_learn_policy.compat"]
        success = json.dumps({"success": True})

        with patch.object(compat, "_get_write_origin", None):
            compat.ensure_compatible()
            self.assertIsNone(
                plugin.transform_tool_result(
                    tool_name="skill_manage",
                    args={
                        "action": "edit",
                        "name": "example",
                        "content": "Current status: changing.",
                    },
                    result=success,
                )
            )

        with patch.object(compat, "_get_file_mutation_targets", None):
            with self.assertRaises(compat.HermesCompatibilityError):
                compat.ensure_compatible()

    def test_custom_diagnostics_are_background_full_content_advice_only(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        success = json.dumps({"success": True, "message": "Skill updated"})
        noisy = (
            "Current status: rollout complete.\n"
            "Incident 2026-08-20 failed under /home/alice/project."
        )

        with patch.object(gate, "current_write_origin", return_value="background_review"):
            transformed = plugin.transform_tool_result(
                tool_name="skill_manage",
                args={"action": "edit", "name": "example", "content": noisy},
                result=success,
            )
            self.assertIn("Learning-policy diagnostic", transformed)
            self.assertIn("volatile-status", transformed)
            self.assertIn("dated-evidence", transformed)
            self.assertIn("machine-local", transformed)
            self.assertNotIn("/home/alice/project", transformed)

            self.assertIsNone(
                plugin.transform_tool_result(
                    tool_name="skill_manage",
                    args={"action": "create", "name": "clean", "content": "Reusable procedure."},
                    result=success,
                )
            )
            for args in (
                {"action": "patch", "name": "example", "new_string": noisy},
                {"action": "write_file", "name": "example", "file_path": "references/a.md", "file_content": noisy},
                {"action": "remove_file", "name": "example", "file_path": "references/a.md"},
                {"action": "delete", "name": "example", "absorbed_into": ""},
            ):
                self.assertIsNone(
                    plugin.transform_tool_result(
                        tool_name="skill_manage",
                        args=args,
                        result=success,
                    )
                )
            self.assertIsNone(
                plugin.transform_tool_result(
                    tool_name="skill_manage",
                    args={"action": "edit", "name": "example", "content": noisy},
                    result=json.dumps({"success": False, "error": "failed"}),
                )
            )

        self.assertIsNone(
            plugin.transform_tool_result(
                tool_name="skill_manage",
                args={"action": "edit", "name": "example", "content": noisy},
                result=success,
            )
        )


if __name__ == "__main__":
    unittest.main()
