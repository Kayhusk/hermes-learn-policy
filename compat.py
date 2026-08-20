"""Version-scoped read-only adapters to installed Hermes internals."""

try:
    from tools.skill_provenance import get_current_write_origin as _get_write_origin
    from agent.tool_dispatch_helpers import (
        _extract_file_mutation_targets as _get_file_mutation_targets,
    )
except ImportError as exc:  # Plugin Doctor reports this through ensure_compatible().
    _get_write_origin = None
    _get_file_mutation_targets = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class HermesCompatibilityError(RuntimeError):
    pass


def ensure_compatible():
    if _get_write_origin is None or _get_file_mutation_targets is None:
        raise HermesCompatibilityError(
            "Hermes learning adapters are unavailable; revalidate this plugin against the installed Hermes version"
        ) from _IMPORT_ERROR


def current_write_origin():
    ensure_compatible()
    return str(_get_write_origin())


def file_mutation_targets(tool_name, args):
    ensure_compatible()
    return list(_get_file_mutation_targets(tool_name, args))
