"""Route protection and prompt-first guidance for Hermes learning."""

import os
import re
from pathlib import Path

from .compat import file_mutation_targets

PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
LEARNING_QUALITY_GUIDANCE = """Hermes Learn Policy — native learning quality

When considering a native `memory` or `skill_manage` write, classify the durable owner first and save only material that will improve future sessions:

- USER: stable facts about the user, preferences, communication style, and expectations.
- MEMORY: stable agent or environment facts, conventions, and corrections. Write declarative facts, not commands to a future agent.
- skills: reusable class-level procedures and decision methods. Keep active guidance portable; put session-specific evidence in an appropriate reference only when it has lasting diagnostic value.

Before a skill write, inspect the current catalog and owner with native `skills_list` and `skill_view`, including relevant linked references. If the same responsibility or procedure already exists, update that owner only after satisfying native read-before-write. If inspection is incomplete, make no write. If inspection confirms no existing owner has that responsibility, native creation remains available. If responsibilities are related but distinct, keep them separate and link instead of merging or copying guidance.

Keep a multi-file learning proposal coherent. If an owner/index change and support file are both required, do not persist only one half; prefer one self-contained native mutation or no write. After a native mutation rejection, do not retry unchanged or create a sibling to route around the guard.

Do not persist secrets, volatile status, task history, completion claims, issue/PR/commit/test receipts, duplicated meaning, misplaced procedures, or unnecessary machine-local paths. Prefer the current project/runtime source, session history, or no write when those are the correct owners. When replacing a consolidated entry, preserve every unaffected clause rather than silently dropping facts to make room. Preserve unrelated entries and use one native atomic memory batch when several entries change together."""


def _home():
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _direct_owner(path, home):
    base = Path(os.environ.get("TERMINAL_CWD", Path.cwd()))
    raw = Path(path).expanduser()
    candidate = Path(os.path.abspath(raw if raw.is_absolute() else base / raw))
    lexical_home = Path(os.path.abspath(home))
    for target, root in (
        (candidate.resolve(), lexical_home.resolve()),
        (candidate, lexical_home),
    ):
        if target == root / "memories" / "MEMORY.md":
            return "memory(target='memory')"
        if target == root / "memories" / "USER.md":
            return "memory(target='user')"
        try:
            target.relative_to(root / "skills")
            return "skill_manage"
        except ValueError:
            pass
    return None


def _persisted_text(args):
    values = [
        value
        for key in ("content", "new_text", "file_content", "new_string")
        if isinstance((value := args.get(key)), str)
    ]
    for operation in args.get("operations") or []:
        if not isinstance(operation, dict):
            continue
        values.extend(
            value
            for key in ("content", "new_text")
            if isinstance((value := operation.get(key)), str)
        )
    return "\n".join(values)


def _pre_decision(tool_name, args, home):
    if tool_name in {"skill_manage", "memory"} and PRIVATE_KEY_RE.search(
        _persisted_text(args)
    ):
        return {
            "action": "block",
            "message": "learning-policy: obvious private-key material cannot be persisted",
        }

    if tool_name in {"write_file", "patch"}:
        for path in file_mutation_targets(tool_name, args):
            owner = _direct_owner(path, home)
            if owner:
                return {
                    "action": "block",
                    "message": (
                        "learning-policy: direct durable-learning write refused; "
                        f"retry with {owner}"
                    ),
                }
    return None


def pre_tool_call(tool_name="", args=None, home=None, **kwargs):
    if tool_name not in {"skill_manage", "memory", "write_file", "patch"}:
        return None
    args = args if isinstance(args, dict) else {}
    try:
        return _pre_decision(tool_name, args, Path(home or _home()))
    except Exception:
        if tool_name in {"skill_manage", "memory"}:
            return {
                "action": "block",
                "message": "learning-policy failed closed: inspect the learning proposal and retry",
            }
        return None


def learning_quality_section(session_info):
    if str(session_info.get("platform", "")).lower() == "curator":
        return ""
    return LEARNING_QUALITY_GUIDANCE
