import concurrent.futures
import importlib.util
import inspect
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).parent


def load_plugin():
    for name in tuple(sys.modules):
        if name == "hermes_learn_policy" or name.startswith("hermes_learn_policy."):
            sys.modules.pop(name)
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
    def test_manifest_declares_v081_dynamic_hooks(self):
        manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.8.1")
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

    def test_background_rejection_blocks_changed_sibling_and_memory_workarounds(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        args = {"action": "patch", "name": "demo", "old_string": "a", "new_string": "b"}
        ids = {"session_id": "session-a", "turn_id": "turn-a"}
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="telegram", **ids)
        plugin.post_tool_call(
            tool_name="skill_manage",
            args=args,
            result='{"success": false, "error": "native rejection"}',
            status="error",
            **ids,
        )

        attempts = (
            ("skill_manage", dict(args, new_string="changed")),
            ("skill_manage", dict(args, name="sibling")),
            ("skill_manage", dict(args, file_path="references/workaround.md")),
            ("memory", {"action": "add", "target": "memory", "content": "workaround"}),
        )
        for tool_name, candidate in attempts:
            blocked = plugin.pre_tool_call(tool_name, candidate, **ids)
            self.assertEqual(blocked["action"], "block", (tool_name, candidate))
            self.assertIn("review-wide recovery", blocked["message"])

        fresh = {"session_id": "session-a", "turn_id": "turn-b"}
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="telegram", **fresh)
        self.assertIsNone(plugin.pre_tool_call("skill_manage", args, **fresh))

    def test_post_rejection_read_of_another_file_cannot_switch_target(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        ids = {"session_id": "session-switch", "turn_id": "turn-switch"}
        rejected = {
            "action": "patch",
            "name": "demo",
            "old_string": "a",
            "new_string": "b",
        }
        switched = dict(
            rejected,
            file_path="references/other.md",
            old_string="old",
            new_string="new",
        )
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="telegram", **ids)
        plugin.post_tool_call(
            tool_name="skill_manage", args=rejected, status="error", **ids
        )
        plugin.post_tool_call(
            tool_name="skill_view",
            args={"name": "demo", "file_path": "references/other.md"},
            result=json.dumps(
                {
                    "success": True,
                    "name": "demo",
                    "file": "references/other.md",
                    "_source_path": "/tmp/demo/references/other.md",
                }
            ),
            status="ok",
            **ids,
        )
        blocked = plugin.pre_tool_call("skill_manage", switched, **ids)
        self.assertEqual(blocked["action"], "block")
        self.assertIn("exact target", blocked["message"])

    def test_exact_post_rejection_view_bridges_one_retry_then_closes_review(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        args = {"action": "patch", "name": "demo", "old_string": "a", "new_string": "b"}
        ids = {"session_id": "session-view", "turn_id": "turn-view"}
        target = "/tmp/learn-policy-demo/SKILL.md"
        marked = []
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="telegram", **ids)
        plugin.post_tool_call(
            tool_name="skill_manage", args=args, status="error", **ids
        )
        self.assertEqual(
            plugin.pre_tool_call("skill_manage", args, **ids)["action"], "block"
        )

        plugin.post_tool_call(
            tool_name="skill_view",
            args={"name": "other"},
            result=json.dumps({"success": True, "name": "other", "path": "/tmp/other/SKILL.md"}),
            status="ok",
            **ids,
        )
        self.assertEqual(
            plugin.pre_tool_call("skill_manage", args, **ids)["action"], "block"
        )

        plugin.post_tool_call(
            tool_name="skill_view",
            args={"name": "demo"},
            result=json.dumps({"success": True, "name": "demo", "path": target}),
            status="ok",
            **ids,
        )
        with patch.object(
            gate, "mark_native_background_review_skill_read", side_effect=marked.append
        ):
            self.assertIsNone(plugin.pre_tool_call("skill_manage", args, **ids))
        self.assertEqual(marked, [Path(target)])
        plugin.post_tool_call(tool_name="skill_manage", args=args, status="ok", **ids)
        self.assertEqual(
            plugin.pre_tool_call("skill_manage", args, **ids)["action"], "block"
        )
        self.assertEqual(
            plugin.pre_tool_call(
                "skill_manage", dict(args, name="sibling"), **ids
            )["action"],
            "block",
        )

    def test_read_bridge_marks_only_exact_successful_target(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        args = {
            "action": "patch",
            "name": "demo",
            "file_path": "references/check.md",
            "old_string": "a",
            "new_string": "b",
        }
        ids = {"session_id": "session-bridge", "turn_id": "turn-bridge"}
        target = "/tmp/learn-policy-demo/references/check.md"
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="telegram", **ids)
        plugin.post_tool_call(
            tool_name="skill_view",
            args={"name": "demo", "file_path": "references/check.md"},
            result=json.dumps(
                {"success": True, "name": "demo", "file": "references/check.md", "_source_path": target}
            ),
            status="ok",
            **ids,
        )
        marked = []
        with patch.object(
            gate, "mark_native_background_review_skill_read", side_effect=marked.append
        ):
            self.assertIsNone(plugin.pre_tool_call("skill_manage", args, **ids))
            self.assertIsNone(
                plugin.pre_tool_call(
                    "skill_manage", dict(args, file_path="references/other.md"), **ids
                )
            )
        self.assertEqual(marked, [Path(target)])

        bad = {"session_id": "session-bad", "turn_id": "turn-bad"}
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="telegram", **bad)
        plugin.post_tool_call(
            tool_name="skill_view",
            args={"name": "demo", "file_path": "references/check.md"},
            result=json.dumps({"success": False, "error": "missing"}),
            status="ok",
            **bad,
        )
        marked.clear()
        with patch.object(
            gate, "mark_native_background_review_skill_read", side_effect=marked.append
        ):
            self.assertIsNone(plugin.pre_tool_call("skill_manage", args, **bad))
        self.assertEqual(marked, [])

    def test_read_bridge_accepts_native_main_skill_result_shape(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        ids = {"session_id": "session-shape", "turn_id": "turn-shape"}
        args = {"action": "patch", "name": "demo", "old_string": "a", "new_string": "b"}
        skill_dir = "/tmp/native-shape/demo"
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="telegram", **ids)
        plugin.post_tool_call(
            tool_name="skill_view",
            args={"name": "demo"},
            result=json.dumps(
                {
                    "success": True,
                    "name": "demo",
                    "path": "software-development/demo/SKILL.md",
                    "skill_dir": skill_dir,
                }
            ),
            status="ok",
            **ids,
        )
        marked = []
        with patch.object(
            gate, "mark_native_background_review_skill_read", side_effect=marked.append
        ):
            self.assertIsNone(plugin.pre_tool_call("skill_manage", args, **ids))
        self.assertEqual(marked, [Path(skill_dir) / "SKILL.md"])

    def test_bridge_replays_receipt_into_native_background_context(self):
        plugin = load_plugin()
        from tools.skill_manager_tool import (
            _background_review_has_read,
            _reset_background_review_read_marks,
        )
        from tools.skill_provenance import (
            BACKGROUND_REVIEW,
            reset_current_write_origin,
            set_current_write_origin,
        )

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "demo" / "SKILL.md"
            target.parent.mkdir()
            target.write_text("demo", encoding="utf-8")
            ids = {"session_id": "session-native", "turn_id": "turn-native"}
            args = {
                "action": "patch",
                "name": "demo",
                "old_string": "a",
                "new_string": "b",
            }
            token = set_current_write_origin(BACKGROUND_REVIEW)
            try:
                _reset_background_review_read_marks()
                plugin.pre_llm_call(platform="telegram", **ids)
                plugin.post_tool_call(
                    tool_name="skill_view",
                    args={"name": "demo"},
                    result=json.dumps(
                        {"success": True, "name": "demo", "path": str(target)}
                    ),
                    status="ok",
                    **ids,
                )
                self.assertIsNone(plugin.pre_tool_call("skill_manage", args, **ids))
                self.assertTrue(_background_review_has_read(target))
            finally:
                _reset_background_review_read_marks()
                reset_current_write_origin(token)

    def test_bridge_allows_real_native_background_patch_after_worker_mark_loss(self):
        plugin = load_plugin()
        from tools.skill_manager_tool import (
            _reset_background_review_read_marks,
            skill_manage,
        )
        from tools.skill_provenance import (
            BACKGROUND_REVIEW,
            reset_current_write_origin,
            set_current_write_origin,
        )

        content = """---
name: bridge-demo
description: Use when testing the native read bridge.
---

# Bridge demo

Original body.
"""
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"HERMES_HOME": tmp}
        ):
            token = set_current_write_origin(BACKGROUND_REVIEW)
            try:
                created = json.loads(
                    skill_manage(action="create", name="bridge-demo", content=content)
                )
                self.assertTrue(created["success"], created)
                target = Path(tmp) / "skills" / "bridge-demo" / "SKILL.md"
                _reset_background_review_read_marks()
                ids = {"session_id": "session-real", "turn_id": "turn-real"}
                plugin.pre_llm_call(platform="telegram", **ids)
                plugin.post_tool_call(
                    tool_name="skill_view",
                    args={"name": "bridge-demo"},
                    result=json.dumps(
                        {"success": True, "name": "bridge-demo", "path": str(target)}
                    ),
                    status="ok",
                    **ids,
                )
                args = {
                    "action": "patch",
                    "name": "bridge-demo",
                    "old_string": "Original body.",
                    "new_string": "Updated body.",
                }
                self.assertIsNone(plugin.pre_tool_call("skill_manage", args, **ids))
                patched = json.loads(skill_manage(**args))
                self.assertTrue(patched["success"], patched)
                self.assertIn("Updated body.", target.read_text(encoding="utf-8"))
            finally:
                _reset_background_review_read_marks()
                reset_current_write_origin(token)

    def test_review_retry_allowance_is_consumed_atomically(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        args = {
            "action": "patch",
            "name": "atomic",
            "old_string": "a",
            "new_string": "b",
        }
        ids = {"session_id": "session-atomic", "turn_id": "turn-atomic"}
        target = "/tmp/atomic/SKILL.md"
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="telegram", **ids)
        plugin.post_tool_call(tool_name="skill_manage", args=args, status="error", **ids)
        plugin.post_tool_call(
            tool_name="skill_view",
            args={"name": "atomic"},
            result=json.dumps({"success": True, "name": "atomic", "path": target}),
            status="ok",
            **ids,
        )

        with patch.object(gate, "mark_native_background_review_skill_read"):
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

    def test_foreground_rejections_do_not_consume_autonomous_review_budget(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        args = {"action": "patch", "name": "demo", "old_string": "a", "new_string": "b"}
        ids = {"session_id": "session-foreground", "turn_id": "turn-foreground"}
        with patch.object(gate, "current_write_origin", return_value="foreground"):
            plugin.pre_llm_call(platform="telegram", **ids)
        plugin.post_tool_call(tool_name="skill_manage", args=args, status="error", **ids)
        self.assertIsNone(plugin.pre_tool_call("skill_manage", args, **ids))
        self.assertIsNone(
            plugin.pre_tool_call("skill_manage", dict(args, name="other"), **ids)
        )

    def test_memory_rejection_closes_autonomous_learning_for_the_review(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        ids = {"session_id": "session-memory", "turn_id": "turn-memory"}
        args = {"action": "replace", "target": "user", "old_text": "a", "content": "b"}
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="telegram", **ids)
        plugin.post_tool_call(tool_name="memory", args=args, status="error", **ids)
        for tool_name, candidate in (
            ("memory", dict(args, content="changed")),
            ("skill_manage", {"action": "create", "name": "workaround", "content": "safe"}),
        ):
            self.assertEqual(
                plugin.pre_tool_call(tool_name, candidate, **ids)["action"], "block"
            )

    def test_curator_terminal_reads_pass_but_mutations_are_refused(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        ids = {"session_id": "curator-session", "turn_id": "curator-turn"}
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="curator", **ids)
            self.assertIsNone(
                plugin.pre_tool_call("terminal", {"command": "ls -la"}, **ids)
            )
            for command in (
                "rm " + "-rf /tmp/generated-skill",
                "touch /tmp/generated-skill",
                "python3 -c \"open('/tmp/generated-skill','w').write('x')\"",
                "git add SKILL.md",
                "git status --short",
                "git -C /tmp status",
                "git --paginate status",
                "git diff --output=curator-write",
                "git diff --textconv",
                "file -C -m magic",
                "ls & touch curator-write",
                "printf x > /tmp/generated-skill",
                "ls\n" + "rm " + "-rf /tmp/curator-bypass",
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
                    {"command": "rm " + "-rf /tmp/host-will-deny"},
                    **background_ids,
                )
            )
        with patch.object(gate, "current_write_origin", return_value="foreground"):
            self.assertIsNone(
                plugin.pre_tool_call(
                    "terminal",
                    {"command": "rm " + "-rf /tmp/user-directed"},
                    platform="telegram",
                )
            )

    def test_direct_route_uses_native_task_cwd_for_relative_paths(self):
        plugin = load_plugin()
        from tools.terminal_tool import clear_session_cwd, record_session_cwd

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "profile"
            memories = home / "memories"
            memories.mkdir(parents=True)
            task_id = "learn-policy-task-cwd"
            record_session_cwd(task_id, str(memories))
            try:
                blocked = plugin.pre_tool_call(
                    "write_file",
                    {"path": "MEMORY.md", "content": "direct bypass"},
                    home=home,
                    task_id=task_id,
                )
            finally:
                clear_session_cwd(task_id)
        self.assertEqual(blocked["action"], "block")
        self.assertIn("memory(target='memory')", blocked["message"])

    def test_state_pressure_never_evicts_an_active_rejected_review(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        original = {"session_id": "session-original", "turn_id": "turn-original"}
        args = {"action": "patch", "name": "demo", "old_string": "a", "new_string": "b"}
        with patch.object(gate, "current_write_origin", return_value="background_review"):
            plugin.pre_llm_call(platform="telegram", **original)
            plugin.post_tool_call(
                tool_name="skill_manage", args=args, status="error", **original
            )
            for index in range(gate._STATE_LIMIT + 1):
                ids = {
                    "session_id": f"session-pressure-{index}",
                    "turn_id": f"turn-pressure-{index}",
                }
                plugin.pre_llm_call(platform="telegram", **ids)
                plugin.post_tool_call(
                    tool_name="skill_manage", args=args, status="error", **ids
                )
            blocked = plugin.pre_tool_call("skill_manage", args, **original)
        self.assertEqual(blocked["action"], "block")
        self.assertIn("review", blocked["message"])

    def test_retry_state_is_bounded_and_never_retains_argument_content(self):
        plugin = load_plugin()
        gate = sys.modules["hermes_learn_policy.gate"]
        with gate._STATE_LOCK:
            gate._RECOVERY.clear()
            gate._READ_RECEIPTS.clear()
            gate._LANES.clear()

        sensitive = "do-not-store-this-value"
        for index in range(gate._STATE_LIMIT + 20):
            ids = {"session_id": f"session-{index}", "turn_id": f"turn-{index}"}
            with patch.object(gate, "current_write_origin", return_value="background_review"):
                plugin.pre_llm_call(platform="telegram", **ids)
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
                result=json.dumps(
                    {
                        "success": True,
                        "name": f"{sensitive}-{index}",
                        "path": f"/tmp/receipt-{index}/SKILL.md",
                    }
                ),
                status="ok",
                **ids,
            )

        with gate._STATE_LOCK:
            self.assertLessEqual(len(gate._RECOVERY), gate._STATE_LIMIT)
            self.assertLessEqual(len(gate._READ_RECEIPTS), gate._STATE_LIMIT)
            self.assertLessEqual(len(gate._LANES), gate._STATE_LIMIT)
            state_repr = repr((gate._RECOVERY, gate._READ_RECEIPTS, gate._LANES))
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
            "_mark_background_review_skill_read",
            "_resolve_file_path_for_task",
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
        self.assertIn("one native skill rejection permits only one same-owner retry", context)
        self.assertIn("any memory rejection or completed retry ends learning writes", context)
        self.assertIn("Never switch owners or files", context)
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
