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
)

PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
_STATE_LIMIT = 256
_STATE_LOCK = threading.Lock()
_REJECTIONS = {}
_VIEWS = {}
_LANES = {}
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
_CURATOR_GIT_READ_COMMANDS = {"diff", "log", "rev-parse", "show", "status"}
LEARNING_QUALITY_GUIDANCE = """Hermes Learn Policy — native learning quality

When considering a native `memory` or `skill_manage` write, classify the durable owner first and save only material that will improve future sessions:

- USER: stable facts about the user, preferences, communication style, and expectations.
- MEMORY: stable agent or environment facts, conventions, and corrections. Write declarative facts, not commands to a future agent.
- skills: reusable class-level procedures and decision methods. Keep active guidance portable; put session-specific evidence in an appropriate reference only when it has lasting diagnostic value.

Before any memory write, load `profile-memory-governance` with native `skill_view` and follow its admission and write workflow. Use the complete current USER or MEMORY content available to this turn. For replacement, carry every unrelated clause forward verbatim. Never solve capacity by silently dropping clauses. If exact preservation, ownership, or capacity cannot be verified, make no write.

Before a skill write, load `skill-governance` with native `skill_view`, then inspect the current catalog and owner with native `skills_list` and `skill_view`, including relevant linked references. If the same responsibility or procedure already exists, update that owner only after satisfying native read-before-write. If inspection is incomplete, make no write. If inspection confirms no existing owner has that responsibility, native creation remains available. If responsibilities are related but distinct, keep them separate and link instead of merging or copying guidance.

Keep a multi-file learning proposal coherent. If an owner/index change and support file are both required, do not persist only one half; prefer one self-contained native mutation or no write. After a native mutation rejection, make only a meaningfully changed, cause-directed recovery. Do not retry unchanged or create a sibling to route around the guard.

Do not persist secrets, volatile status, task history, completion claims, issue/PR/commit/test receipts, duplicated meaning, misplaced procedures, or unnecessary machine-local paths. Prefer the current project/runtime source, session history, or no write when those are the correct owners. When replacing a consolidated entry, preserve every unaffected clause rather than silently dropping facts to make room. Preserve unrelated entries and use one native atomic memory batch when several entries change together."""

FOREGROUND_GUIDANCE = """Foreground learning lane

The user's current task remains primary. Apply this policy only if this turn considers a native learning write. A no-write decision is valid."""

BACKGROUND_GUIDANCE = """Automatic background-review lane

Inspect native owners before writing. A no-write result is valid. Never create a sibling to bypass ownership or read-before-write rejection. After rejection, use only a meaningfully changed recovery; an unchanged retry will be refused."""

CURATOR_GUIDANCE = """Hermes Learn Policy — Curator consolidation lane

This lane is skill-only. Before a write, load `skill-governance`, inspect current owners with native `skills_list` and `skill_view`, and keep related but distinct responsibilities separate. A no-write result is valid. Preserve native Curator ownership, pins, archive/delete, and provenance rules. Use terminal only for read-only inspection; durable skill mutation must remain on native `skill_manage`. After rejection, make only a meaningfully changed recovery and never create a sibling workaround."""


def _remember_lane(session_id, turn_id, lane):
    if not session_id or not turn_id:
        return
    key = (str(session_id), str(turn_id))
    with _STATE_LOCK:
        if len(_LANES) >= _STATE_LIMIT and key not in _LANES:
            _LANES.pop(next(iter(_LANES)))
        _LANES[key] = lane


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


def _fingerprint(tool_name, args):
    payload = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{tool_name}\0{payload}".encode()).hexdigest()


def _state_key(session_id, turn_id, tool_name, args):
    if not session_id or not turn_id:
        return None
    return (str(session_id), str(turn_id), _fingerprint(tool_name, args))


def _view_key(session_id, turn_id, tool_name, args):
    if not session_id or not turn_id:
        return None
    name = str(args.get("name") or "") if isinstance(args, dict) else ""
    identity = "*" if tool_name == "memory" else hashlib.sha256(name.encode()).hexdigest()
    return (str(session_id), str(turn_id), identity)


def _remember_rejection(session_id, turn_id, tool_name, args):
    key = _state_key(session_id, turn_id, tool_name, args)
    if key is None:
        return
    with _STATE_LOCK:
        if len(_REJECTIONS) >= _STATE_LIMIT:
            _REJECTIONS.pop(next(iter(_REJECTIONS)))
        view_key = _view_key(session_id, turn_id, tool_name, args)
        _REJECTIONS[key] = _VIEWS.get(view_key, 0)


def _remember_view(session_id, turn_id, args):
    key = _view_key(session_id, turn_id, "skill_view", args)
    if key is None:
        return
    with _STATE_LOCK:
        if len(_VIEWS) >= _STATE_LIMIT and key not in _VIEWS:
            _VIEWS.pop(next(iter(_VIEWS)))
        _VIEWS[key] = _VIEWS.get(key, 0) + 1


def post_tool_call(
    tool_name="", args=None, status="", session_id="", turn_id="", **_
):
    if tool_name == "skill_view" and status == "ok":
        _remember_view(session_id, turn_id, args if isinstance(args, dict) else {})
    elif tool_name in {"skill_manage", "memory"} and status == "error":
        _remember_rejection(
            session_id,
            turn_id,
            tool_name,
            args if isinstance(args, dict) else {},
        )
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
    if executable != "git":
        return executable in _CURATOR_READ_COMMANDS
    index = 1
    while index < len(tokens) and tokens[index].startswith("-"):
        index += 2 if tokens[index] == "-C" else 1
    if index >= len(tokens) or tokens[index] not in _CURATOR_GIT_READ_COMMANDS:
        return False
    return not any(
        token == "--output"
        or token.startswith("--output=")
        or token == "--ext-diff"
        or token == "--textconv"
        for token in tokens[index + 1 :]
    )


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


def pre_tool_call(
    tool_name="",
    args=None,
    home=None,
    session_id="",
    turn_id="",
    **kwargs,
):
    args = args if isinstance(args, dict) else {}
    with _STATE_LOCK:
        lane = _LANES.get((str(session_id), str(turn_id)))
    if (
        tool_name == "terminal"
        and lane == "curator"
    ):
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
    key = _state_key(session_id, turn_id, tool_name, args)
    if key is not None:
        with _STATE_LOCK:
            rejected_at = _REJECTIONS.get(key)
            current_view = _VIEWS.get(
                _view_key(session_id, turn_id, tool_name, args), 0
            )
            rejected = rejected_at is not None and current_view <= rejected_at
            if rejected_at is not None and not rejected:
                _REJECTIONS[key] = current_view
        if rejected:
            return {
                "action": "block",
                "message": (
                    "learning-policy: unchanged rejected learning call refused; "
                    "make a meaningfully changed recovery or end this review"
                ),
            }
    try:
        return _pre_decision(tool_name, args, Path(home or _home()))
    except Exception:
        if tool_name in {"skill_manage", "memory"}:
            return {
                "action": "block",
                "message": "learning-policy failed closed: inspect the learning proposal and retry",
            }
        return None
