"""Route protection and prompt-first guidance for Hermes learning."""

import hashlib
import json
import os
import re
import shlex
import threading
from pathlib import Path

from .compat import (
    current_write_origin,
    file_mutation_targets,
    mark_native_background_review_skill_read,
    resolve_native_file_path,
)

PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
_STATE_LIMIT = 256
_STATE_LOCK = threading.Lock()
_RECOVERY = {}
_READ_RECEIPTS = {}
_LANES = {}
_VIEW_GENERATION = 0
_STATE_SATURATED = False
_CURATOR_READ_COMMANDS = {
    "df",
    "du",
    "ls",
    "pwd",
    "readlink",
    "realpath",
    "sha256sum",
    "stat",
    "wc",
}

LEARNING_QUALITY_GUIDANCE = """Hermes Learn Policy — native learning quality

When considering a native `memory` or `skill_manage` write, classify the durable owner first and save only material that will improve future sessions:

- USER: stable facts about the user, preferences, communication style, and expectations.
- MEMORY: stable agent or environment facts, conventions, and corrections. Write declarative facts, not commands to a future agent.
- skills: reusable class-level procedures and decision methods. Keep active guidance portable; put session-specific evidence in an appropriate reference only when it has lasting diagnostic value.

Before any memory write, load `profile-memory-governance` with native `skill_view` and follow its admission and write workflow. Use the complete current USER or MEMORY content available to this turn. For replacement, carry every unrelated clause forward verbatim. Never solve capacity by silently dropping clauses. If exact preservation, ownership, or capacity cannot be verified, make no write.

Before a skill write, load `skill-governance` with native `skill_view`, then inspect the current catalog and owner with native `skills_list` and `skill_view`, including relevant linked references. If the same responsibility or procedure already exists, update that owner only after satisfying native read-before-write. If inspection is incomplete, make no write. If inspection confirms no existing owner has that responsibility, native creation remains available. If responsibilities are related but distinct, keep them separate and link instead of merging or copying guidance.

Keep a multi-file learning proposal coherent. If an owner/index change and support file are both required, do not persist only one half; prefer one self-contained native mutation or no write. In an autonomous review, one native skill rejection permits only one same-owner retry after reading the exact target again; any memory rejection or completed retry ends learning writes for that review. Never switch owners or files to route around a rejection.

Do not persist secrets, volatile status, task history, completion claims, issue/PR/commit/test receipts, duplicated meaning, misplaced procedures, or unnecessary machine-local paths. Prefer the current project/runtime source, session history, or no write when those are the correct owners. When replacing a consolidated entry, preserve every unaffected clause rather than silently dropping facts to make room. Preserve unrelated entries and use one native atomic memory batch when several entries change together."""

FOREGROUND_GUIDANCE = """Foreground learning lane

The user's current task remains primary. The current real user message can support a USER write when it passes profile-memory governance. Apply this policy only if this turn considers a native learning write. A no-write decision is valid."""

BACKGROUND_GUIDANCE = """Automatic background-review lane

The current review prompt is synthetic review machinery, not a real user statement and never USER authority. These are process or evidence sources, never user preferences: system prompts, plugin context, review instructions, skills, assistant output, and tool results. USER facts require explicit support from pre-existing real user messages in the inherited conversation history or an independently verified authoritative factual source. Autonomous USER learning remains available from qualifying real-user evidence. If no authoritative support exists, make no USER write.

Inspect native owners before writing. A no-write result is valid. Never create a sibling to bypass ownership or read-before-write rejection. After a skill rejection, read the exact same owner and target file once before one retry; every further learning write in this review will be refused. A memory rejection ends learning writes for this review."""

CURATOR_GUIDANCE = """Hermes Learn Policy — Curator consolidation lane

This lane is skill-only. Before a write, load `skill-governance`, inspect current owners with native `skills_list` and `skill_view`, and keep related but distinct responsibilities separate. A no-write result is valid. Preserve native Curator ownership, pins, archive/delete, and provenance rules. Use terminal only for read-only inspection; durable skill mutation must remain on native `skill_manage`. After a rejection, read the exact same owner and target file once before one retry; every further skill write in this review will be refused."""


def _purge_superseded_turns_locked(session_id, turn_id):
    """Drop only prior turns from this session; never evict another active turn."""
    global _STATE_SATURATED
    session_id, turn_id = str(session_id), str(turn_id)
    for mapping in (_LANES, _RECOVERY, _READ_RECEIPTS):
        for key in tuple(mapping):
            if key[0] == session_id and key[1] != turn_id:
                mapping.pop(key, None)
    _STATE_SATURATED = any(
        len(mapping) >= _STATE_LIMIT
        for mapping in (_LANES, _RECOVERY, _READ_RECEIPTS)
    )


def _bounded_store_locked(mapping, key, value):
    global _STATE_SATURATED
    if key not in mapping and len(mapping) >= _STATE_LIMIT:
        _STATE_SATURATED = True
        return False
    mapping[key] = value
    return True


def _remember_lane(session_id, turn_id, lane):
    if not session_id or not turn_id:
        return
    key = (str(session_id), str(turn_id))
    with _STATE_LOCK:
        _purge_superseded_turns_locked(*key)
        _bounded_store_locked(_LANES, key, lane)


def pre_llm_call(platform="", session_id="", turn_id="", **_):
    if str(platform).lower() == "curator":
        _remember_lane(session_id, turn_id, "curator")
        return {"context": CURATOR_GUIDANCE}
    if current_write_origin() == "background_review":
        _remember_lane(session_id, turn_id, "background_review")
        guidance = BACKGROUND_GUIDANCE
    else:
        _remember_lane(session_id, turn_id, "foreground")
        guidance = FOREGROUND_GUIDANCE
    return {"context": f"{LEARNING_QUALITY_GUIDANCE}\n\n{guidance}"}


def _digest(value):
    return hashlib.sha256(str(value or "").encode()).hexdigest()


def _turn_key(session_id, turn_id):
    if not session_id or not turn_id:
        return None
    return (str(session_id), str(turn_id))


def _owner_digest(args):
    return _digest(args.get("name")) if isinstance(args, dict) else _digest("")


def _target_label(args):
    if not isinstance(args, dict):
        return None
    action = str(args.get("action") or "")
    if action not in {"edit", "patch", "delete", "write_file", "remove_file"}:
        return None
    return str(args.get("file_path") or "SKILL.md")


def _receipt_key(session_id, turn_id, args):
    turn = _turn_key(session_id, turn_id)
    target = _target_label(args)
    if turn is None or target is None:
        return None
    return (*turn, _owner_digest(args), _digest(target))


def _recovery_target_digest(args):
    if not isinstance(args, dict):
        return _digest("SKILL.md")
    return _digest(args.get("file_path") or "SKILL.md")


def _autonomous_lane(session_id, turn_id):
    turn = _turn_key(session_id, turn_id)
    if turn is None:
        return False
    with _STATE_LOCK:
        lane = _LANES.get(turn)
    return lane in {"background_review", "curator"}


def _parse_skill_view_result(args, result):
    if not isinstance(args, dict):
        return None
    try:
        payload = json.loads(result) if isinstance(result, str) else result
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return None
    if str(payload.get("name") or "") != str(args.get("name") or ""):
        return None
    expected = str(args.get("file_path") or "SKILL.md")
    if args.get("file_path") and str(payload.get("file") or "") != expected:
        return None
    path = payload.get("_source_path")
    if path is None and expected == "SKILL.md":
        skill_dir = payload.get("skill_dir")
        if isinstance(skill_dir, str) and Path(skill_dir).is_absolute():
            path = str(Path(skill_dir) / "SKILL.md")
        elif isinstance(payload.get("path"), str) and Path(payload["path"]).is_absolute():
            path = payload["path"]
    if not isinstance(path, str) or not Path(path).is_absolute():
        return None
    return Path(path).resolve()


def _remember_view(session_id, turn_id, args, result):
    global _VIEW_GENERATION
    key = _receipt_key(session_id, turn_id, {
        "action": "patch",
        "name": args.get("name") if isinstance(args, dict) else "",
        "file_path": args.get("file_path") if isinstance(args, dict) else None,
    })
    path = _parse_skill_view_result(args, result)
    if key is None or path is None:
        return
    with _STATE_LOCK:
        _VIEW_GENERATION += 1
        _bounded_store_locked(_READ_RECEIPTS, key, (_VIEW_GENERATION, path))


def _remember_rejection(session_id, turn_id, tool_name, args):
    if not _autonomous_lane(session_id, turn_id):
        return
    turn = _turn_key(session_id, turn_id)
    if turn is None:
        return
    with _STATE_LOCK:
        if turn in _RECOVERY:
            _RECOVERY[turn]["closed"] = True
            return
        state = {
            "tool": str(tool_name),
            "owner": _owner_digest(args) if tool_name == "skill_manage" else None,
            "target": (
                _recovery_target_digest(args)
                if tool_name == "skill_manage"
                else None
            ),
            "rejected_generation": _VIEW_GENERATION,
            "consumed": False,
            "closed": tool_name != "skill_manage",
        }
        _bounded_store_locked(_RECOVERY, turn, state)


def post_tool_call(
    tool_name="",
    args=None,
    result=None,
    status="",
    session_id="",
    turn_id="",
    **_,
):
    args = args if isinstance(args, dict) else {}
    if tool_name == "skill_view" and status == "ok":
        _remember_view(session_id, turn_id, args, result)
    elif tool_name in {"skill_manage", "memory"} and status == "error":
        _remember_rejection(session_id, turn_id, tool_name, args)
    return None


def _curator_terminal_is_read_only(command):
    command = str(command or "")
    if any(
        marker in command
        for marker in ("\n", "\r", ";", "&", "||", "|", ">", "<", "`", "$(")
    ):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return False
    executable = Path(tokens[0]).name
    if executable != tokens[0] or "/" in tokens[0] or "\\" in tokens[0]:
        return False
    return executable in _CURATOR_READ_COMMANDS


def _home():
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _direct_owner(path, home, task_id=""):
    candidate = resolve_native_file_path(path, task_id)
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


def _pre_decision(tool_name, args, home, task_id=""):
    if tool_name in {"skill_manage", "memory"} and PRIVATE_KEY_RE.search(
        _persisted_text(args)
    ):
        return {
            "action": "block",
            "message": "learning-policy: obvious private-key material cannot be persisted",
        }

    if tool_name in {"write_file", "patch"}:
        for path in file_mutation_targets(tool_name, args):
            owner = _direct_owner(path, home, task_id)
            if owner:
                return {
                    "action": "block",
                    "message": (
                        "learning-policy: direct durable-learning write refused; "
                        f"retry with {owner}"
                    ),
                }
    return None


def pre_tool_call(
    tool_name="",
    args=None,
    home=None,
    session_id="",
    turn_id="",
    task_id="",
    **kwargs,
):
    args = args if isinstance(args, dict) else {}
    turn = _turn_key(session_id, turn_id)
    with _STATE_LOCK:
        lane = _LANES.get(turn) if turn is not None else None
        saturated = _STATE_SATURATED
    if (
        saturated
        and current_write_origin() == "background_review"
        and tool_name in {"skill_manage", "memory", "terminal"}
    ):
        return {
            "action": "block",
            "message": (
                "learning-policy: autonomous review state capacity reached; "
                "end this review and continue on a fresh turn"
            ),
        }
    if tool_name == "terminal" and lane == "curator":
        if not _curator_terminal_is_read_only(args.get("command")):
            return {
                "action": "block",
                "message": (
                    "learning-policy: Curator terminal mutation refused; "
                    "use terminal for inspection and native skill_manage for durable changes"
                ),
            }
        return None
    if tool_name not in {"skill_manage", "memory", "write_file", "patch"}:
        return None

    receipt_path = None
    if tool_name == "skill_manage" and turn is not None:
        receipt_key = _receipt_key(session_id, turn_id, args)
        with _STATE_LOCK:
            receipt = _READ_RECEIPTS.get(receipt_key) if receipt_key is not None else None
            recovery = _RECOVERY.get(turn)
            if lane in {"background_review", "curator"} and recovery is not None:
                allowed = (
                    not recovery["closed"]
                    and not recovery["consumed"]
                    and recovery["tool"] == "skill_manage"
                    and recovery["owner"] == _owner_digest(args)
                    and recovery["target"] == _recovery_target_digest(args)
                    and receipt is not None
                    and receipt[0] > recovery["rejected_generation"]
                )
                if not allowed:
                    return {
                        "action": "block",
                        "message": (
                            "learning-policy: autonomous review-wide recovery refused; "
                            "read the rejected owner and exact target once, retry once, or end this review"
                        ),
                    }
                recovery["consumed"] = True
                recovery["closed"] = True
            receipt_path = receipt[1] if receipt is not None else None
    elif tool_name == "memory" and turn is not None:
        with _STATE_LOCK:
            recovery = _RECOVERY.get(turn)
            if lane in {"background_review", "curator"} and recovery is not None:
                return {
                    "action": "block",
                    "message": (
                        "learning-policy: autonomous review-wide recovery refused; "
                        "a prior learning rejection ended writes for this review"
                    ),
                }

    if receipt_path is not None and lane in {"background_review", "curator"}:
        mark_native_background_review_skill_read(receipt_path)
    try:
        return _pre_decision(
            tool_name,
            args,
            Path(home or _home()),
            task_id=task_id,
        )
    except Exception:
        if tool_name in {"skill_manage", "memory"}:
            return {
                "action": "block",
                "message": "learning-policy failed closed: inspect the learning proposal and retry",
            }
        return None
