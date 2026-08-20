"""Hermes Learn Policy plugin."""

from .compat import ensure_compatible
from .gate import learning_quality_section, pre_tool_call


def register(ctx):
    ensure_compatible()
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_system_prompt_section(
        "hermes-learn-policy.learning-quality",
        learning_quality_section,
        position="after_memory",
        max_chars=3000,
    )


__all__ = ["learning_quality_section", "pre_tool_call", "register"]
