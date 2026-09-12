"""Standalone maintenance jobs, run via ``python -m app.jobs.<name>`` or
from ``app.main``'s background loop. Never imported by request-handling
code -- see ``app.jobs.cleanup_images``.
"""
