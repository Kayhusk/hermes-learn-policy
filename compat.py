"""Version-scoped read-only adapters to installed Hermes internals."""

try:
    from agent.tool_dispatch_helpers import (
        _extract_file_mutation_targets as _get_file_mutation_targets,
    )
except ImportError as exc:
    _get_file_mutation_targets = None
    _REQUIRED_IMPORT_ERROR = exc
else:
    _REQUIRED_IMPORT_ERROR = None

try:
    from tools.skill_provenance import get_current_write_origin as _get_write_origin
except ImportError:
    _get_write_origin = None


class HermesCompatibilityError(RuntimeError):
    pass


def ensure_compatible():
    """Require only the adapter used by pre-write route protection."""
    if _get_file_mutation_targets is None:
        raise HermesCompatibilityError(
            "Hermes file-target adapter is unavailable; revalidate this plugin against the installed Hermes version"
        ) from _REQUIRED_IMPORT_ERROR


def current_write_origin():
    """Return an inert value when the optional diagnostic origin moves."""
    return "unknown" if _get_write_origin is None else str(_get_write_origin())


def file_mutation_targets(tool_name, args):
    ensure_compatible()
    assert _get_file_mutation_targets is not None
    return list(_get_file_mutation_targets(tool_name, args))
