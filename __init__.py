"""Hermes learning-quality gate plugin."""

from .compat import ensure_compatible
from .gate import classify, evaluate, pre_tool_call, transform_tool_result


def register(ctx):
    ensure_compatible()
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("transform_tool_result", transform_tool_result)


__all__ = [
    "classify",
    "evaluate",
    "pre_tool_call",
    "transform_tool_result",
    "register",
]
