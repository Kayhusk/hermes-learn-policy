"""Version-scoped read-only adapters to installed Hermes internals."""

try:
    from agent.tool_dispatch_helpers import (
        _extract_file_mutation_targets as _get_file_mutation_targets,
    )
    from tools.skill_provenance import (
        get_current_write_origin as _get_current_write_origin,
    )
except ImportError as exc:
    _get_file_mutation_targets = None
    _get_current_write_origin = None
    _REQUIRED_IMPORT_ERROR = exc
else:
    _REQUIRED_IMPORT_ERROR = None

class HermesCompatibilityError(RuntimeError):
    pass


def ensure_compatible():
    """Require the read-only adapters used by guidance and route protection."""
    if any(
        adapter is None
        for adapter in (
            _get_file_mutation_targets,
            _get_current_write_origin,
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
