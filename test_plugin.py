import importlib.util
import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "hermes_learning_quality_gate",
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PluginContractTest(unittest.TestCase):
    def test_routes_learning_calls_and_ignores_unrelated_tools(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertEqual(plugin.classify("memory", {"target": "memory"}, home), "memory")
            self.assertEqual(plugin.classify("memory", {"target": "user"}, home), "user")
            self.assertEqual(
                plugin.classify("skill_manage", {"action": "create", "name": "example"}, home),
                "profile-local-custom",
            )
            self.assertIsNone(plugin.classify("terminal", {"command": "true"}, home))
            self.assertIsNone(plugin.evaluate("memory", {"target": "memory"}, home))

    def test_blocks_immutable_skill_provenance(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skills = home / "skills"
            (skills / ".hub").mkdir(parents=True)
            (skills / ".bundled_manifest").write_text("bundled-skill:hash\n", encoding="utf-8")
            (skills / ".hub" / "lock.json").write_text(
                '{"installed": {"hub-skill": {}}}', encoding="utf-8"
            )
            (skills / "custom-skill").mkdir()
            (skills / "custom-skill" / "SKILL.md").write_text("---\nname: custom-skill\n---\n")

            cases = {
                "bundled-skill": "hermes-bundled",
                "hub-skill": "hub-installed",
                "plugin:skill": "plugin-owned",
            }
            for name, provenance in cases.items():
                args = {"action": "patch", "name": name}
                self.assertEqual(plugin.classify("skill_manage", args, home), provenance)
                self.assertEqual(plugin.evaluate("skill_manage", args, home)["action"], "block")

            custom = {"action": "patch", "name": "custom-skill"}
            self.assertEqual(
                plugin.classify("skill_manage", custom, home), "profile-local-custom"
            )
            self.assertIsNone(plugin.evaluate("skill_manage", custom, home))

    def test_blocks_direct_writes_to_learning_files(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            memory_path = home / "memories" / "MEMORY.md"
            skill_path = home / "skills" / "example" / "SKILL.md"
            user_patch = (
                "*** Begin Patch\n"
                f"*** Update File: {home / 'memories' / 'USER.md'}\n"
                "@@\n-old\n+new\n"
                "*** End Patch\n"
            )

            cases = (
                ("write_file", {"path": str(memory_path), "content": "x"}, "direct-memory"),
                ("patch", {"mode": "replace", "path": str(skill_path)}, "direct-skill"),
                ("patch", {"mode": "patch", "patch": user_patch}, "direct-user"),
            )
            for tool_name, args, owner in cases:
                self.assertEqual(plugin.classify(tool_name, args, home), owner)
                self.assertEqual(plugin.evaluate(tool_name, args, home)["action"], "block")

            self.assertIsNone(
                plugin.classify("write_file", {"path": str(home / "notes.md")}, home)
            )

    def test_registers_forward_compatible_hook_that_fails_closed(self):
        plugin = load_plugin()

        class Context:
            def register_hook(self, name, callback):
                self.hook = (name, callback)

        ctx = Context()
        plugin.register(ctx)
        name, callback = ctx.hook
        self.assertEqual(name, "pre_tool_call")
        self.assertTrue(
            any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in inspect.signature(callback).parameters.values()
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "skills" / ".hub").mkdir(parents=True)
            (home / "skills" / ".hub" / "lock.json").write_text("not-json")
            with patch.dict(os.environ, {"HERMES_HOME": str(home)}):
                result = callback(
                    tool_name="skill_manage",
                    args={"action": "patch", "name": "example"},
                    task_id="test",
                )
        self.assertEqual(result["action"], "block")
        self.assertIn("failed closed", result["message"])


if __name__ == "__main__":
    unittest.main()
