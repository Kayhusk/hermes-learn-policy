import importlib.util
import inspect
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
    def test_registers_route_protection_and_one_learning_section(self):
        plugin = load_plugin()

        class Context:
            def __init__(self):
                self.hooks = {}
                self.sections = {}

            def register_hook(self, name, callback):
                self.hooks[name] = callback

            def register_system_prompt_section(self, name, content, **options):
                self.sections[name] = (content, options)

        ctx = Context()
        plugin.register(ctx)

        self.assertEqual(set(ctx.hooks), {"pre_tool_call"})
        self.assertEqual(set(ctx.sections), {"hermes-learn-policy.learning-quality"})
        callback, options = ctx.sections["hermes-learn-policy.learning-quality"]
        self.assertIs(callback, plugin.learning_quality_section)
        self.assertEqual(options, {"position": "after_memory", "max_chars": 3000})
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

    def test_required_file_adapter_drift_fails_registration(self):
        load_plugin()
        compat = sys.modules["hermes_learn_policy.compat"]

        with patch.object(compat, "_get_file_mutation_targets", None):
            with self.assertRaises(compat.HermesCompatibilityError):
                compat.ensure_compatible()

    def test_learning_section_covers_native_writers_and_preserves_consolidated_clauses(self):
        plugin = load_plugin()

        context = plugin.learning_quality_section({"platform": "telegram"})
        self.assertIn("USER", context)
        self.assertIn("MEMORY", context)
        self.assertIn("skills", context)
        self.assertIn("declarative facts", context)
        self.assertIn("volatile status", context)
        self.assertIn("task history", context)
        self.assertIn("native `memory`", context)
        self.assertIn("`skill_manage` write", context)
        self.assertIn("preserve every unaffected clause", context)
        self.assertIn("`skills_list` and `skill_view`", context)
        self.assertIn("same responsibility or procedure", context)
        self.assertIn("inspection confirms no existing owner", context)
        self.assertIn("native creation remains available", context)
        self.assertNotIn("otherwise make no write", context)
        self.assertIn("keep them separate and link", context)
        self.assertIn("one self-contained native mutation or no write", context)
        self.assertIn("do not retry", context)
        self.assertIn("When considering", context)
        self.assertLessEqual(len(context), 3000)
        for workspace_term in ("Foldly", "SourceBand", "Apollo", "Orion", "KYD-"):
            self.assertNotIn(workspace_term, context)

    def test_learning_section_skips_curator(self):
        plugin = load_plugin()

        self.assertEqual(plugin.learning_quality_section({"platform": "curator"}), "")


if __name__ == "__main__":
    unittest.main()
