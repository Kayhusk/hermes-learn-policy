"""Classify learning writes before later policy checks."""

import json
import os
import re
from pathlib import Path

IMMUTABLE_SKILLS = {"hermes-bundled", "hub-installed", "plugin-owned"}


def _home():
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _bundled_names(skills):
    manifest = skills / ".bundled_manifest"
    if not manifest.exists():
        return set()
    return {
        line.split(":", 1)[0].strip()
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _hub_names(skills):
    lock = skills / ".hub" / "lock.json"
    if not lock.exists():
        return set()
    installed = json.loads(lock.read_text(encoding="utf-8", errors="replace")).get(
        "installed", {}
    )
    return set(installed) if isinstance(installed, dict) else set()


def _local_skill_exists(skills, name):
    if not skills.exists():
        return False
    # ponytail: linear catalog scan; index it if hook latency becomes measurable.
    return any(path.parent.name == name for path in skills.rglob("SKILL.md"))


def _write_paths(tool_name, args):
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


def _direct_owner(path, home):
    base = Path(os.environ.get("TERMINAL_CWD", Path.cwd()))
    raw = Path(path).expanduser()
    candidate = Path(os.path.abspath(raw if raw.is_absolute() else base / raw))
    home = Path(os.path.abspath(home))
    if candidate == home / "memories" / "MEMORY.md":
        return "direct-memory"
    if candidate == home / "memories" / "USER.md":
        return "direct-user"
    try:
        candidate.relative_to(home / "skills")
        return "direct-skill"
    except ValueError:
        return None


def classify(tool_name, args, home=None):
    if not isinstance(args, dict):
        return None
    if tool_name == "memory":
        target = args.get("target") or "memory"
        return target if target in {"memory", "user"} else None
    if tool_name in {"write_file", "patch"}:
        home = Path(home or _home())
        for path in _write_paths(tool_name, args):
            owner = _direct_owner(path, home)
            if owner:
                return owner
        return None
    if tool_name != "skill_manage":
        return None

    name = args.get("name")
    if not isinstance(name, str) or not name:
        return "unknown-skill"
    if ":" in name:
        return "plugin-owned"

    skills = Path(home or _home()) / "skills"
    if name in _bundled_names(skills):
        return "hermes-bundled"
    if name in _hub_names(skills):
        return "hub-installed"
    if args.get("action") == "create" or _local_skill_exists(skills, name):
        return "profile-local-custom"
    return "unknown-skill"


def evaluate(tool_name, args, home=None):
    provenance = classify(tool_name, args, home or _home())
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


def pre_tool_call(tool_name="", args=None, **kwargs):
    try:
        return evaluate(tool_name, args or {})
    except Exception:
        return {
            "action": "block",
            "message": "learning-quality gate failed closed: repair provenance metadata and retry",
        }
