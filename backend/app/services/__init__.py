"""Cross-cutting service orchestration used by API routers.

Each service ties together validation, a deterministic engine (vision,
ingredients, ...), and database persistence, so API route handlers stay a
thin HTTP boundary. See ``image_service.py`` (Phase 2).
"""
