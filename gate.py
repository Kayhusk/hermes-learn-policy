"""Route protection and bounded advice for Hermes learning writes."""

import json
import os
import re
from pathlib import Path

from .compat import current_write_origin, file_mutation_targets

PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
STATUS_RE = re.compile(r"(?im)^\s*(?:current|project|implementation|rollout) status\s*:")
DATED_EVIDENCE_RE = re.compile(
    r"(?is)\b(?:incident|evidence|audit|postmortem)\b.{0,80}\b20\d{2}-\d{2}-\d{2}\b"
)
MACHINE_PATH_RE = re.compile(r"(?i)(?:^|[\s`'\"])(?:/home/|/Users/|[A-Z]:\\Users\\)")


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


def _diagnostics(content):
    findings = []
    if STATUS_RE.search(content):
        findings.append(
            ("volatile-status", "Move mutable status to current project or runtime source.")
        )
    if DATED_EVIDENCE_RE.search(content):
        findings.append(
            ("dated-evidence", "Keep dated incidents in evidence; retain only the reusable lesson.")
        )
    if MACHINE_PATH_RE.search(content):
        findings.append(
            ("machine-local", "Confirm this is intentionally profile-local, not portable guidance.")
        )
    return findings


def _successful(result):
    if not isinstance(result, str):
        return False
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("success") is True
        and not payload.get("staged")
        and not payload.get("error")
    )


def transform_tool_result(tool_name="", args=None, result=None, **kwargs):
    if (
        tool_name != "skill_manage"
        or not isinstance(args, dict)
        or args.get("action") not in {"create", "edit"}
        or current_write_origin() != "background_review"
        or not _successful(result)
        or not isinstance(args.get("content"), str)
    ):
        return None
    findings = _diagnostics(args["content"])
    if not findings:
        return None
    lines = ["Learning-policy diagnostic"]
    lines.extend(f"- [{rule}] {message}" for rule, message in findings)
    lines.append("Review these signals and self-correct only where they apply.")
    return result + "\n\n---\n" + "\n".join(lines)
