"""Hermes Learn Policy plugin."""

from .compat import ensure_compatible
from .gate import pre_llm_call, pre_tool_call


def register(ctx):
    ensure_compatible()
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("pre_llm_call", pre_llm_call)


__all__ = ["pre_llm_call", "pre_tool_call", "register"]
