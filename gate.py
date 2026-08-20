"""Bounded safety checks and diagnostics for Hermes learning writes."""

import json
import os
import re
from pathlib import Path

from .compat import current_write_origin, file_mutation_targets

PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
STATUS_RE = re.compile(
    r"(?im)^\s*(?:current|project|implementation|rollout) status\s*:"
)
DATED_EVIDENCE_RE = re.compile(
    r"(?is)\b(?:incident|evidence|audit|postmortem)\b.{0,80}\b20\d{2}-\d{2}-\d{2}\b"
)
MACHINE_PATH_RE = re.compile(
    r"(?i)(?:^|[\s`'\"])(?:/home/|/Users/|[A-Z]:\\Users\\)"
)
IMMUTABLE_SKILLS = {"hermes-bundled", "hub-installed", "plugin-owned"}


def _home():
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _write_paths(tool_name, args):
    return file_mutation_targets(tool_name, args)


def _legacy_write_paths(tool_name, args):
    path = args.get("path")
    if tool_name == "write_file":
        return [path] if isinstance(path, str) else []
    if tool_name != "patch":
        return []
    if isinstance(path, str):
        return [path]
    raw = args.get("patch")
    if not isinstance(raw, str):
        return []
    return re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", raw, re.MULTILINE)


def _legacy_direct_owner(path, home):
    base = Path(os.environ.get("TERMINAL_CWD", Path.cwd()))
    raw = Path(path).expanduser()
    candidate = Path(os.path.abspath(raw if raw.is_absolute() else base / raw))
    home = Path(os.path.abspath(home))
    if candidate == home / "memories" / "MEMORY.md":
        return "memory(target='memory')"
    if candidate == home / "memories" / "USER.md":
        return "memory(target='user')"
    try:
        candidate.relative_to(home / "skills")
        return "skill_manage"
    except ValueError:
        return None


def _direct_owner(path, home):
    base = Path(os.environ.get("TERMINAL_CWD", Path.cwd()))
    raw = Path(path).expanduser()
    candidate = Path(os.path.abspath(raw if raw.is_absolute() else base / raw))
    lexical_home = Path(os.path.abspath(home))
    probes = ((candidate.resolve(), lexical_home.resolve()), (candidate, lexical_home))
    for target, root in probes:
        if target == root / "memories" / "MEMORY.md":
            return "memory(target='memory')"
        if target == root / "memories" / "USER.md":
            return "memory(target='user')"
        try:
            target.relative_to(root / "skills")
            return "skill_manage"
        except ValueError:
            continue
    return None


def _targets_main_skill_file(args):
    path = args.get("file_path")
    if not isinstance(path, str):
        return False
    normalized = Path(os.path.normpath(path))
    return not normalized.is_absolute() and normalized.parts == ("SKILL.md",)


def _persisted_text(args):
    values = [
        value
        for key in ("content", "new_text", "file_content", "new_string")
        if isinstance((value := args.get(key)), str)
    ]
    operations = args.get("operations")
    if isinstance(operations, list):
        for operation in operations:
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
            "message": "learning-quality gate: obvious private-key material cannot be persisted",
        }

    if tool_name in {"write_file", "patch"}:
        for path in _write_paths(tool_name, args):
            owner = _direct_owner(path, home)
            if owner:
                return {
                    "action": "block",
                    "message": (
                        "learning-quality gate: direct durable-learning write refused; "
                        f"retry with {owner}"
                    ),
                }
        return None

    if tool_name != "skill_manage":
        return None

    action = args.get("action")
    if _targets_main_skill_file(args):
        if action == "patch":
            remediation = "omit file_path so native SKILL.md validation runs"
        elif action == "remove_file":
            remediation = "use action='delete' for the skill lifecycle"
        else:
            remediation = "use action='edit' with the full SKILL.md content"
        return {
            "action": "block",
            "message": f"learning-quality gate: main-file bypass refused; {remediation}",
        }

    return None


def _is_relevant(tool_name, args, home):
    if tool_name in {"skill_manage", "memory"}:
        return True
    if tool_name in {"write_file", "patch"}:
        return any(_direct_owner(path, home) for path in _write_paths(tool_name, args))
    return False


def pre_tool_call(tool_name="", args=None, home=None, **kwargs):
    if not isinstance(args, dict):
        args = {}
    home = Path(home or _home())
    try:
        if not _is_relevant(tool_name, args, home):
            return None
        decision = _pre_decision(tool_name, args, home)
        if decision is not None:
            return decision
        if tool_name == "skill_manage" and _write_origin() == "background_review":
            return evaluate(tool_name, args, home)
        return None
    except Exception:
        return {
            "action": "block",
            "message": "learning-quality gate failed closed: inspect the learning proposal and retry",
        }


def _legacy_bundled_names(skills):
    manifest = skills / ".bundled_manifest"
    if not manifest.exists():
        return set()
    return {
        line.split(":", 1)[0].strip()
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _legacy_hub_names(skills):
    lock = skills / ".hub" / "lock.json"
    if not lock.exists():
        return set()
    installed = json.loads(lock.read_text(encoding="utf-8", errors="replace")).get(
        "installed", {}
    )
    return set(installed) if isinstance(installed, dict) else set()


def _legacy_local_skill_exists(skills, name):
    if not skills.exists():
        return False
    # ponytail: v0.1 compatibility scan; remove with the compatibility API in v1.
    return any(path.parent.name == name for path in skills.rglob("SKILL.md"))


def classify(tool_name, args, home=None):
    """Behavior-compatible v0.1 classification API."""
    if not isinstance(args, dict):
        return None
    home = Path(home or _home())
    if tool_name == "memory":
        target = args.get("target") or "memory"
        return target if target in {"memory", "user"} else None
    if tool_name in {"write_file", "patch"}:
        mapping = {
            "memory(target='memory')": "direct-memory",
            "memory(target='user')": "direct-user",
            "skill_manage": "direct-skill",
        }
        for path in _legacy_write_paths(tool_name, args):
            owner = _legacy_direct_owner(path, home)
            if owner:
                return mapping[owner]
        return None
    if tool_name != "skill_manage":
        return None

    name = args.get("name")
    if not isinstance(name, str) or not name:
        return "unknown-skill"
    if ":" in name:
        return "plugin-owned"
    skills = home / "skills"
    if name in _legacy_bundled_names(skills):
        return "hermes-bundled"
    if name in _legacy_hub_names(skills):
        return "hub-installed"
    if args.get("action") == "create" or _legacy_local_skill_exists(skills, name):
        return "profile-local-custom"
    return "unknown-skill"


def evaluate(tool_name, args, home=None):
    """Behavior-compatible v0.1 admission API."""
    provenance = classify(tool_name, args, home)
    if provenance in IMMUTABLE_SKILLS:
        return {
            "action": "block",
            "message": (
                f"learning-quality gate: {provenance} skill '{args.get('name')}' is "
                "immutable; use its official owner or update path"
            ),
        }
    if provenance == "unknown-skill":
        return {
            "action": "block",
            "message": "learning-quality gate: skill provenance is unresolved; retry against a verified custom owner",
        }
    if provenance and provenance.startswith("direct-"):
        owner = {
            "direct-memory": "memory(target='memory')",
            "direct-user": "memory(target='user')",
            "direct-skill": "skill_manage",
        }[provenance]
        return {
            "action": "block",
            "message": f"learning-quality gate: direct learning-file write refused; use {owner}",
        }
    return None


def _write_origin():
    return current_write_origin()


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
        or _write_origin() != "background_review"
        or not _successful(result)
        or not isinstance(args.get("content"), str)
    ):
        return None
    findings = _diagnostics(args["content"])
    if not findings:
        return None
    lines = ["⚠️ Learning-quality diagnostic"]
    lines.extend(f"- [{rule}] {message}" for rule, message in findings)
    lines.append("Review these signals and self-correct only where they apply.")
    return result + "\n\n---\n" + "\n".join(lines)
