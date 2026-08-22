"""Register the Hermes Learn Policy hooks."""

from .compat import ensure_compatible
from .gate import post_tool_call, pre_llm_call, pre_tool_call


def register(ctx):
    ensure_compatible()
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)


__all__ = ["post_tool_call", "pre_llm_call", "pre_tool_call", "register"]
