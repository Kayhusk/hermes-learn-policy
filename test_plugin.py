import concurrent.futures
import importlib.util
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

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
    def test_manifest_declares_v080_dynamic_hooks(self):
        manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.8.0")
        self.assertEqual(
            set(manifest["provides_hooks"]),
            {"pre_llm_call", "pre_tool_call", "post_tool_call"},
        )

    def test_registers_lane_aware_dynamic_hooks_without_frozen_section(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]

        class Context:
            def __init__(self):
                self.hooks = {}

            def register_hook(self, name, callback):
                self.hooks[name] = callback

        ctx = Context()
        plugin.register(ctx)

        self.assertEqual(
            set(ctx.hooks), {"pre_llm_call", "pre_tool_call", "post_tool_call"}
        )
        self.assertFalse(hasattr(ctx, "sections"))
        with patch.object(gate, "current_write_origin", return_value="foreground"):
            foreground = plugin.pre_llm_call(platform="telegram")["context"]
        with patch.object(
            gate, "current_write_origin", return_value="background_review"
        ):
            background = plugin.pre_llm_call(platform="telegram")["context"]
            curator = plugin.pre_llm_call(platform="curator")["context"]

        self.assertIn("Foreground learning lane", foreground)
        self.assertIn("Automatic background-review lane", background)
        self.assertIn("Curator consolidation lane", curator)
        self.assertNotEqual(foreground, background)
        self.assertNotEqual(background, curator)
        for context in (foreground, background, curator):
            self.assertIn("Hermes Learn Policy", context)
            self.assertLessEqual(len(context), 4000)
            for workspace_term in ("Foldly", "SourceBand", "Apollo", "Orion", "KYD-"):
                self.assertNotIn(workspace_term, context)
        for callback in ctx.hooks.values():
            self.assertTrue(
                any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD
                    for parameter in inspect.signature(callback).parameters.values()
                )
            )

    def test_unchanged_rejected_learning_call_is_blocked_but_changed_recovery_is_allowed(self):
        plugin = load_plugin()
        args = {"action": "create", "name": "demo", "content": "safe"}
        ids = {"session_id": "session-a", "turn_id": "turn-a"}

        plugin.post_tool_call(
            tool_name="skill_manage",
            args=args,
            result='{"success": false, "error": "native rejection"}',
            status="error",
            **ids,
        )

        blocked = plugin.pre_tool_call("skill_manage", args, **ids)
        self.assertEqual(blocked["action"], "block")
        self.assertIn("unchanged rejected learning call", blocked["message"])
        changed = dict(args, content="meaningfully changed")
        self.assertIsNone(plugin.pre_tool_call("skill_manage", changed, **ids))
        self.assertIsNone(
            plugin.pre_tool_call(
                "skill_manage", args, session_id="session-a", turn_id="turn-b"
            )
        )

    def test_intervening_skill_view_allows_one_same_call_retry(self):
        plugin = load_plugin()
        args = {"action": "patch", "name": "demo", "old_string": "a", "new_string": "b"}
        ids = {"session_id": "session-view", "turn_id": "turn-view"}

        plugin.post_tool_call(
            tool_name="skill_manage", args=args, status="error", **ids
        )
        self.assertEqual(
            plugin.pre_tool_call("skill_manage", args, **ids)["action"], "block"
        )

        plugin.post_tool_call(
            tool_name="skill_view",
            args={"name": "other"},
            result='{"success": true, "name": "other"}',
            status="ok",
            **ids,
        )
        self.assertEqual(
            plugin.pre_tool_call("skill_manage", args, **ids)["action"], "block"
        )

        plugin.post_tool_call(
            tool_name="skill_view",
            args={"name": "demo"},
            result='{"success": true, "name": "demo"}',
            status="ok",
            **ids,
        )
        self.assertIsNone(plugin.pre_tool_call("skill_manage", args, **ids))
        self.assertEqual(
            plugin.pre_tool_call("skill_manage", args, **ids)["action"], "block"
        )

        plugin.post_tool_call(
            tool_name="skill_manage", args=args, status="error", **ids
        )
        self.assertEqual(
            plugin.pre_tool_call("skill_manage", args, **ids)["action"], "block"
        )

    def test_same_skill_retry_allowance_is_consumed_atomically(self):
        plugin = load_plugin()
        args = {
            "action": "patch",
            "name": "atomic",
            "old_string": "a",
            "new_string": "b",
        }
        ids = {"session_id": "session-atomic", "turn_id": "turn-atomic"}
        plugin.post_tool_call(
            tool_name="skill_manage", args=args, status="error", **ids
        )
        plugin.post_tool_call(
            tool_name="skill_view", args={"name": "atomic"}, status="ok", **ids
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: plugin.pre_tool_call("skill_manage", args, **ids),
                    range(2),
                )
            )

        self.assertEqual(sum(result is None for result in results), 1)
        blocked = [result for result in results if result is not None]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["action"], "block")

    def test_curator_terminal_reads_pass_but_mutations_are_refused(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        ids = {"session_id": "curator-session", "turn_id": "curator-turn"}
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="curator", **ids)
            self.assertIsNone(
                plugin.pre_tool_call(
                    "terminal", {"command": "git status --short"}, **ids
                )
            )
            for command in (
                "rm -rf /tmp/generated-skill",
                "touch /tmp/generated-skill",
                "python3 -c \"open('/tmp/generated-skill','w').write('x')\"",
                "git add SKILL.md",
                "git diff --output=curator-write",
                "git diff --textconv",
                "file -C -m magic",
                "ls & touch curator-write",
                "printf x > /tmp/generated-skill",
                "ls\nrm -rf /tmp/curator-bypass",
                "/tmp/ls",
            ):
                blocked = plugin.pre_tool_call(
                    "terminal", {"command": command}, **ids
                )
                self.assertEqual(blocked["action"], "block", command)
                self.assertIn("Curator terminal mutation", blocked["message"])
            background_ids = {
                "session_id": "background-session",
                "turn_id": "background-turn",
            }
            plugin.pre_llm_call(platform="telegram", **background_ids)
            self.assertIsNone(
                plugin.pre_tool_call(
                    "terminal",
                    {"command": "rm -rf /tmp/host-will-deny"},
                    **background_ids,
                )
            )
        with patch.object(gate, "current_write_origin", return_value="foreground"):
            self.assertIsNone(
                plugin.pre_tool_call(
                    "terminal", {"command": "rm -rf /tmp/user-directed"}, platform="telegram"
                )
            )

    def test_retry_state_is_bounded_and_never_retains_argument_content(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        with gate._STATE_LOCK:
            gate._REJECTIONS.clear()
            gate._VIEWS.clear()
            gate._LANES.clear()

        sensitive = "do-not-store-this-value"
        for index in range(gate._STATE_LIMIT + 20):
            ids = {"session_id": f"session-{index}", "turn_id": f"turn-{index}"}
            plugin.post_tool_call(
                tool_name="skill_manage",
                args={
                    "action": "create",
                    "name": f"{sensitive}-{index}",
                    "content": sensitive,
                },
                status="error",
                **ids,
            )
            plugin.post_tool_call(
                tool_name="skill_view",
                args={"name": f"{sensitive}-{index}"},
                status="ok",
                **ids,
            )
            with patch.object(gate, "current_write_origin", return_value="foreground"):
                plugin.pre_llm_call(platform="telegram", **ids)

        with gate._STATE_LOCK:
            self.assertLessEqual(len(gate._REJECTIONS), gate._STATE_LIMIT)
            self.assertLessEqual(len(gate._VIEWS), gate._STATE_LIMIT)
            self.assertLessEqual(len(gate._LANES), gate._STATE_LIMIT)
            state_repr = repr((gate._REJECTIONS, gate._VIEWS, gate._LANES))
        self.assertNotIn(sensitive, state_repr)

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

    def test_required_private_adapters_drift_fails_registration(self):
        load_plugin()
        compat = sys.modules["hermes_learn_policy.compat"]

        for attribute in (
            "_get_file_mutation_targets",
            "_get_current_write_origin",
        ):
            with self.subTest(attribute=attribute), patch.object(compat, attribute, None):
                with self.assertRaises(compat.HermesCompatibilityError):
                    compat.ensure_compatible()

    def test_dynamic_guidance_covers_native_writers_and_preserves_consolidated_clauses(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        with patch.object(gate, "current_write_origin", return_value="foreground"):
            context = plugin.pre_llm_call(platform="telegram")["context"]
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
        self.assertIn("`profile-memory-governance`", context)
        self.assertIn("`skill-governance`", context)
        self.assertIn("Before any memory write", context)
        self.assertIn("complete current USER or MEMORY content", context)
        self.assertIn("every unrelated clause forward verbatim", context)
        self.assertNotIn("lossless consolidation", context)
        self.assertIn("Never solve capacity by silently dropping clauses", context)
        self.assertIn("same responsibility or procedure", context)
        self.assertIn("inspection confirms no existing owner", context)
        self.assertIn("native creation remains available", context)
        self.assertNotIn("otherwise make no write", context)
        self.assertIn("keep them separate and link", context)
        self.assertIn("one self-contained native mutation or no write", context)
        self.assertIn("meaningfully changed, cause-directed recovery", context)
        self.assertIn("Do not retry", context)
        self.assertIn("When considering", context)
        self.assertLessEqual(len(context), 4000)
        for workspace_term in ("Foldly", "SourceBand", "Apollo", "Orion", "KYD-"):
            self.assertNotIn(workspace_term, context)

    def test_curator_guidance_is_skill_only(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        with patch.object(
            gate, "current_write_origin", return_value="background_review"
        ):
            context = plugin.pre_llm_call(platform="curator")["context"]
        self.assertIn("Curator consolidation lane", context)
        self.assertIn("skill_manage", context)
        self.assertNotIn("USER:", context)
        self.assertNotIn("MEMORY:", context)
        self.assertNotIn("memory write", context)


if __name__ == "__main__":
    unittest.main()
