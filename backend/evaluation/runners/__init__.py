"""Evaluation runners: one module per subsystem, each exposing a
``run() -> list[EvalResult]`` (or ``async def run()`` for the LLM/agent
runners) that executes every case in the matching dataset module and
returns a uniform result list. See ``evaluation.runners.base``.
"""
from __future__ import annotations
