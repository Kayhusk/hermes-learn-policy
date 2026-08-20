import importlib.util
import inspect
import json
import os
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
    def test_registers_only_public_safety_and_diagnostic_hooks(self):
        plugin = load_plugin()

        class Context:
            def __init__(self):
                self.hooks = {}

            def register_hook(self, name, callback):
                self.hooks[name] = callback

        ctx = Context()
        plugin.register(ctx)
        self.assertTrue(callable(plugin.classify))
        self.assertTrue(callable(plugin.evaluate))
        self.assertIsNone(plugin.evaluate("terminal", {"command": "true"}))
        self.assertEqual(set(ctx.hooks), {"pre_tool_call", "transform_tool_result"})
        for callback in ctx.hooks.values():
            self.assertTrue(
                any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD
                    for parameter in inspect.signature(callback).parameters.values()
                )
            )

    def test_preserves_v01_classify_and_evaluate_behavior(self):
        plugin = load_plugin()
        compat = sys.modules["hermes_learn_policy.compat"]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skills = home / "skills"
            (skills / ".hub").mkdir(parents=True)
            (skills / ".bundled_manifest").write_text("bundled:hash\n", encoding="utf-8")
            (skills / ".hub" / "lock.json").write_text(
                '{"installed": {"hub-skill": {}}}', encoding="utf-8"
            )
            (skills / "custom").mkdir()
            (skills / "custom" / "SKILL.md").write_text("---\nname: custom\n---\n")

            self.assertEqual(
                plugin.classify(
                    "skill_manage", {"action": "create", "name": "new"}, home
                ),
                "profile-local-custom",
            )
            self.assertEqual(
                plugin.classify(
                    "skill_manage", {"action": "patch", "name": "bundled"}, home
                ),
                "hermes-bundled",
            )
            self.assertEqual(
                plugin.classify(
                    "skill_manage", {"action": "patch", "name": "hub-skill"}, home
                ),
                "hub-installed",
            )
            self.assertEqual(
                plugin.classify(
                    "skill_manage", {"action": "patch", "name": "custom"}, home
                ),
                "profile-local-custom",
            )
            self.assertEqual(
                plugin.evaluate(
                    "skill_manage", {"action": "patch", "name": "bundled"}, home
                )["action"],
                "block",
            )
            self.assertIsNone(
                plugin.evaluate(
                    "skill_manage", {"action": "patch", "name": "custom"}, home
                )
            )
            with patch.object(compat, "_get_file_mutation_targets", None):
                self.assertEqual(
                    plugin.classify(
                        "write_file",
                        {"path": str(home / "memories" / "MEMORY.md")},
                        home,
                    ),
                    "direct-memory",
                )

    def test_preserves_every_native_skill_manage_capability(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skills = home / "skills"
            skills.mkdir()
            (skills / ".bundled_manifest").write_text("bundled-skill:hash\n", encoding="utf-8")
            operations = (
                {"action": "create", "name": "new-skill", "content": "Use references/api.md when needed."},
                {"action": "edit", "name": "custom-skill", "content": "Updated instructions."},
                {"action": "patch", "name": "custom-skill", "old_string": "old", "new_string": "new"},
                {"action": "delete", "name": "custom-skill", "absorbed_into": ""},
                {"action": "write_file", "name": "custom-skill", "file_path": "references/api.md", "file_content": "API"},
                {"action": "write_file", "name": "custom-skill", "file_path": "references/SKILL.md", "file_content": "Nested example"},
                {"action": "patch", "name": "custom-skill", "file_path": "references/SKILL.md", "old_string": "old", "new_string": "new"},
                {"action": "remove_file", "name": "custom-skill", "file_path": "references/api.md"},
                {"action": "patch", "name": "bundled-skill", "old_string": "old", "new_string": "new"},
            )
            for args in operations:
                self.assertIsNone(plugin.pre_tool_call("skill_manage", args, home=home), args)
            with patch.object(gate, "_write_origin", return_value="background_review"):
                result = plugin.pre_tool_call(
                    "skill_manage",
                    {"action": "patch", "name": "bundled-skill", "old_string": "a", "new_string": "b"},
                    home=home,
                )
            self.assertEqual(result["action"], "block")

    def test_blocks_only_deterministic_safety_bypasses(self):
        plugin = load_plugin()
        private_key = "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"
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
                        "path": str(root / "decoy"),
                        "patch": (
                            "*** Begin Patch\r\n"
                            f"*** Update File: {home / 'memories' / 'MEMORY.md'}\r\n"
                            "@@\r\n-old\r\n+new\r\n"
                            "*** End Patch\r\n"
                        ),
                    },
                ),
                ("skill_manage", {"action": "write_file", "name": "x", "file_path": "SKILL.md", "file_content": "x"}),
                ("skill_manage", {"action": "remove_file", "name": "x", "file_path": "SKILL.md"}),
                ("skill_manage", {"action": "patch", "name": "x", "file_path": "SKILL.md", "old_string": "a", "new_string": "b"}),
                ("skill_manage", {"action": "patch", "name": "x", "file_path": "references/../SKILL.md", "old_string": "a", "new_string": "b"}),
                ("skill_manage", {"action": "create", "name": "x", "content": private_key}),
                ("skill_manage", {"action": "patch", "name": "x", "old_string": "a", "new_string": private_key}),
                ("skill_manage", {"action": "write_file", "name": "x", "file_path": "references/key.txt", "file_content": private_key}),
                ("memory", {"action": "add", "target": "memory", "content": private_key}),
                ("memory", {"target": "memory", "operations": [{"action": "add", "content": private_key}]}),
            )
            for tool_name, args in blocked:
                result = plugin.pre_tool_call(tool_name, args, home=home)
                self.assertEqual(result["action"], "block", (tool_name, args))
                self.assertIn("learning-quality gate", result["message"])

            skills = home / "skills"
            skills.mkdir()
            cross_alias = skills / "memory-alias"
            cross_alias.symlink_to(memories, target_is_directory=True)
            result = plugin.pre_tool_call(
                "write_file", {"path": str(cross_alias / "MEMORY.md"), "content": "x"}, home=home
            )
            self.assertIn("memory(target='memory')", result["message"])

            self.assertIsNone(
                plugin.pre_tool_call(
                    "terminal", {"command": f"printf '%s' '{private_key}'"}, home=home
                )
            )

    def test_fails_closed_only_for_relevant_learning_calls(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        with patch.object(gate, "_pre_decision", side_effect=RuntimeError("boom")):
            result = plugin.pre_tool_call(
                "skill_manage", {"action": "create", "name": "x", "content": "safe"}
            )
            self.assertEqual(result["action"], "block")
            self.assertIn("failed closed", result["message"])
            self.assertIsNone(plugin.pre_tool_call("terminal", {"command": "true"}))

    def test_appends_bounded_diagnostics_only_for_background_writes(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        success = json.dumps({"success": True, "message": "Skill updated"})
        noisy = (
            "Current status: rollout complete.\n"
            "Incident 2026-08-20 failed under /home/alice/project."
        )
        with patch.object(gate, "_write_origin", return_value="background_review"):
            transformed = plugin.transform_tool_result(
                tool_name="skill_manage",
                args={"action": "edit", "name": "example", "content": noisy},
                result=success,
            )
        self.assertIn("Learning-quality diagnostic", transformed)
        self.assertIn("volatile-status", transformed)
        self.assertIn("dated-evidence", transformed)
        self.assertIn("machine-local", transformed)
        self.assertNotIn("/home/alice/project", transformed)

        clean = "Use references/api.md when API details are needed."
        with patch.object(gate, "_write_origin", return_value="background_review"):
            self.assertIsNone(
                plugin.transform_tool_result(
                    tool_name="skill_manage",
                    args={"action": "create", "name": "clean", "content": clean},
                    result=success,
                )
            )
            self.assertIsNone(
                plugin.transform_tool_result(
                    tool_name="skill_manage",
                    args={"action": "patch", "name": "clean", "new_string": noisy},
                    result=success,
                )
            )
            self.assertIsNone(
                plugin.transform_tool_result(
                    tool_name="skill_manage",
                    args={"action": "edit", "name": "clean", "content": noisy},
                    result=json.dumps({"success": False, "error": "write failed"}),
                )
            )
        with patch.object(gate, "_write_origin", return_value="foreground"):
            self.assertIsNone(
                plugin.transform_tool_result(
                    tool_name="skill_manage",
                    args={"action": "edit", "name": "clean", "content": noisy},
                    result=success,
                )
            )


if __name__ == "__main__":
    unittest.main()
