"""Adapters for required Hermes contracts not exposed by plugin hooks."""

from pathlib import Path

try:
    from agent.tool_dispatch_helpers import (
        _extract_file_mutation_targets as _get_file_mutation_targets,
    )
    from tools.file_tools import _resolve_path_for_task as _resolve_file_path_for_task
    from tools.skill_provenance import (
        get_current_write_origin as _get_current_write_origin,
    )
    from tools.skill_manager_tool import (
        mark_background_review_skill_read as _mark_background_review_skill_read,
    )
except ImportError as exc:
    _get_file_mutation_targets = None
    _get_current_write_origin = None
    _mark_background_review_skill_read = None
    _resolve_file_path_for_task = None
    _REQUIRED_IMPORT_ERROR = exc
else:
    _REQUIRED_IMPORT_ERROR = None

class HermesCompatibilityError(RuntimeError):
    pass


def ensure_compatible():
    """Verify every required Hermes adapter before hook registration."""
    if any(
        adapter is None
        for adapter in (
            _get_file_mutation_targets,
            _get_current_write_origin,
            _mark_background_review_skill_read,
            _resolve_file_path_for_task,
        )
    ):
        raise HermesCompatibilityError(
            "A required Hermes compatibility adapter is unavailable; "
            "revalidate this plugin against the installed Hermes version"
        ) from _REQUIRED_IMPORT_ERROR

def file_mutation_targets(tool_name, args):
    ensure_compatible()
    assert _get_file_mutation_targets is not None
    return list(_get_file_mutation_targets(tool_name, args))


def current_write_origin():
    ensure_compatible()
    assert _get_current_write_origin is not None
    return str(_get_current_write_origin() or "foreground")


def resolve_native_file_path(path, task_id=""):
    """Resolve a target with the installed Hermes file-path resolver."""
    ensure_compatible()
    assert _resolve_file_path_for_task is not None
    return Path(_resolve_file_path_for_task(str(path), str(task_id or "default")))


def mark_native_background_review_skill_read(path):
    """Restore one confirmed skill read in the current Hermes tool context."""
    ensure_compatible()
    assert _mark_background_review_skill_read is not None
    _mark_background_review_skill_read(Path(path))
