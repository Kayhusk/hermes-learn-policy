"""Hermes learning-quality gate plugin."""

from .gate import classify, evaluate, pre_tool_call


def register(ctx):
    ctx.register_hook("pre_tool_call", pre_tool_call)


__all__ = ["classify", "evaluate", "pre_tool_call", "register"]
