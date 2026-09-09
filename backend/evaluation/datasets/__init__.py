"""Evaluation datasets: small, transparent, version-controlled fixtures
for each subsystem. Every dataset here is a plain Python module (not a
binary blob) so an expected result is reviewable in a code diff like any
other change.

**These are engineering / behavioral evaluation fixtures, not clinical
ground truth.** Vision fixtures are procedurally generated synthetic
images with deliberately controlled properties (a uniform color, a flat
noise pattern, a red tint) -- they prove the pipeline responds correctly
and deterministically to a *known, controlled* input, never that it is
accurate against real skin or a real medical condition. See
docs/evaluation.md's "Not a clinical accuracy benchmark" section.
"""
from __future__ import annotations
