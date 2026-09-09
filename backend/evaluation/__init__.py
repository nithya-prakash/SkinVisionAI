"""SkinVision AI evaluation harness (Phase 11).

Measures whether the system behaves correctly and safely -- an
engineering/behavioral/regression tool, never a claim of clinical or
dermatological accuracy. See ``evaluation/README.md`` and
``docs/evaluation.md`` for the full picture.

This package is deliberately separate from ``app`` (production code):
nothing here is imported by the application, and nothing in ``app`` was
changed to make evaluation easier. Datasets are small, transparent,
version-controlled Python modules (not opaque blobs) so every expected
result is reviewable in a diff.
"""
from __future__ import annotations
