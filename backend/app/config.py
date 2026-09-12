"""Application configuration loaded from environment variables.

All settings are read once at process start via a cached ``get_settings()``
accessor. Nothing here performs I/O beyond reading the environment/.env file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    Values are sourced from environment variables (or a local ``.env`` file
    during development) and validated by pydantic-settings. See
    ``.env.example`` for the full list of supported variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App metadata ---
    app_name: str = "SkinVision AI"
    environment: str = Field(default="development")
    # Only controls SQLAlchemy's SQL echo (app/database.py) -- server-side
    # log verbosity, never an HTTP response. FastAPI's own debug mode is
    # never enabled; the global exception handler (app/main.py) always
    # returns the same sanitized {code, message} body regardless of this
    # flag, so this can never leak a traceback to a client either way.
    debug: bool = Field(default=False)

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://skinvision:skinvision@localhost:5435/skinvision"
    )

    # --- CORS ---
    frontend_origin: str = Field(default="http://localhost:3010")

    # --- LLM provider (Phase 6) ---
    # "anthropic" | "openai" (OpenAI-compatible chat-completions endpoint)
    # | "fake" (deterministic, offline -- no key/network; see docs/llm.md).
    llm_provider: str = Field(default="anthropic")
    llm_api_key: str | None = Field(default=None)
    llm_model: str = Field(default="claude-sonnet-5")
    # Only used by the "openai" provider; lets it target any
    # OpenAI-compatible endpoint (self-hosted, proxy, alternate vendor).
    llm_base_url: str | None = Field(default=None)
    llm_timeout_seconds: float = Field(default=30.0)

    # --- Agent tool-calling layer (Phase 7) ---
    # Hard limits so the agent loop can never spin indefinitely -- see
    # docs/agent.md. A "turn" is one round-trip to the LLM; each turn
    # produces at most one tool call or the final answer.
    agent_max_tool_calls: int = Field(default=5)
    agent_max_turns: int = Field(default=8)
    # A tool result JSON-serialized longer than this is truncated to a
    # bounded, structured summary before being fed back to the LLM.
    agent_max_tool_result_chars: int = Field(default=20_000)

    # --- Uploads / image handling (Phase 2) ---
    upload_directory: Path = Field(default=Path("./data/uploads"))
    image_max_size_mb: int = Field(default=8)
    # "temporary" persists the file to upload_directory for downstream (Phase 3)
    # processing; "none" analyzes fully in-memory and never writes to disk.
    image_retention_mode: str = Field(default="temporary")
    # How long a "temporary"-mode file may sit on disk before the cleanup
    # job deletes it (the ImageMetadata row and its analysis history are
    # kept; only storage_path is cleared). See app/core/image_cleanup.py.
    image_retention_ttl_hours: float = Field(default=24.0)
    # How often the background cleanup loop (started in app.main's
    # lifespan) sweeps for expired images. Independent of the TTL above.
    image_cleanup_interval_hours: float = Field(default=1.0)

    # --- Image quality gate thresholds (Phase 2) ---
    # Centralized here (not scattered in code) so every threshold is
    # configurable via environment/.env. See docs/vision.md for rationale.
    image_min_width_px: int = Field(default=400)
    image_min_height_px: int = Field(default=400)
    image_blur_variance_threshold: float = Field(default=80.0)
    image_brightness_min: float = Field(default=40.0)
    image_brightness_max: float = Field(default=215.0)
    image_contrast_min_std: float = Field(default=15.0)

    # --- Vision preprocessing / region-of-interest (Phase 3) ---
    # Max longest-edge dimension analysis images are downscaled to, for
    # consistent, deterministic, fast processing. Purely a performance/
    # determinism knob -- has no bearing on the Phase 2 quality gate, which
    # runs on the full-resolution image.
    vision_max_analysis_dimension: int = Field(default=1024)
    # A Haar-cascade face detection below this fraction of the image's
    # shorter side is treated as a likely false positive and ignored.
    vision_face_min_size_fraction: float = Field(default=0.15)
    # Detected face boxes are expanded by this fraction (each side) before
    # cropping, so the region-of-interest includes forehead/cheeks/chin
    # rather than just facial landmarks.
    vision_face_margin_fraction: float = Field(default=0.25)
    # When no face is detected, fall back to analyzing a centered square
    # crop covering this fraction of the image's shorter side.
    vision_center_crop_fraction: float = Field(default=0.6)

    # --- Vision feature thresholds (Phase 3) ---
    # Every threshold below is a heuristic, documented in docs/vision.md,
    # calibrated against synthetic test images -- not a clinically derived
    # or validated value. Each feature has a "_norm_max" (or equivalent)
    # that maps a raw measurement to a 0-1 score, and three cut points
    # (mild_min / moderate_min / pronounced_min) that bucket that score
    # into a level. Below mild_min is "minimal".

    # Redness: mean of the Lab a* channel (positive = red/magenta) within
    # the region of interest.
    vision_redness_norm_max: float = Field(default=12.0)
    vision_redness_mild_min: float = Field(default=0.2)
    vision_redness_moderate_min: float = Field(default=0.45)
    vision_redness_pronounced_min: float = Field(default=0.7)

    # Visible texture: variance of the Laplacian (same focus measure as the
    # Phase 2 blur check) within the region of interest -- here interpreted
    # as "amount of fine local detail" rather than "in vs. out of focus".
    vision_texture_norm_max: float = Field(default=600.0)
    vision_texture_mild_min: float = Field(default=0.2)
    vision_texture_moderate_min: float = Field(default=0.45)
    vision_texture_pronounced_min: float = Field(default=0.7)

    # Visible shine/oiliness: fraction of region-of-interest pixels that are
    # both very bright and low-saturation (a specular-highlight signature).
    vision_shine_brightness_min: float = Field(default=220.0)
    vision_shine_saturation_max: float = Field(default=60.0)
    vision_shine_mild_min: float = Field(default=0.02)
    vision_shine_moderate_min: float = Field(default=0.06)
    vision_shine_pronounced_min: float = Field(default=0.12)

    # Uneven tone: standard deviation of the Lab L* (lightness) channel
    # within the region of interest.
    vision_tone_norm_max: float = Field(default=18.0)
    vision_tone_mild_min: float = Field(default=0.2)
    vision_tone_moderate_min: float = Field(default=0.45)
    vision_tone_pronounced_min: float = Field(default=0.7)

    # Visible spots/marks: connected components in a high-pass (difference
    # from a heavily blurred baseline) map, filtered to a plausible size
    # range, normalized by count.
    vision_spots_diff_threshold: int = Field(default=18)
    vision_spots_min_area_px: int = Field(default=12)
    vision_spots_max_area_fraction: float = Field(default=0.02)
    vision_spots_norm_max_count: int = Field(default=25)
    vision_spots_mild_min: float = Field(default=0.15)
    vision_spots_moderate_min: float = Field(default=0.4)
    vision_spots_pronounced_min: float = Field(default=0.7)

    # --- Rate limiting (Phase 12 follow-up) ---
    # Per-client-IP fixed-window limits on endpoints with a real per-request
    # cost (LLM tokens, CV pipeline CPU, password-hashing/brute-force risk),
    # independent of and in addition to authentication. See
    # app/core/rate_limit.py.
    rate_limit_upload_max_requests: int = Field(default=10)
    rate_limit_upload_window_seconds: float = Field(default=60.0)
    rate_limit_agent_chat_max_requests: int = Field(default=20)
    rate_limit_agent_chat_window_seconds: float = Field(default=60.0)
    rate_limit_auth_max_requests: int = Field(default=10)
    rate_limit_auth_window_seconds: float = Field(default=60.0)

    # --- Authentication (release-hardening follow-up) ---
    # A UserSession is now owned by a User (app/models/user.py) rather
    # than accessible to anyone who holds its UUID -- see
    # app/services/auth_service.py and docs/persistence.md's Security
    # section. jwt_secret_key ships with a local-dev-only default (see
    # .env.example's own warning) -- never reuse it for a real deployment.
    jwt_secret_key: str = Field(default="dev-only-insecure-secret-change-me")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiry_days: int = Field(default=7)
    # Cookie name for the JWT; httpOnly, so frontend JS never reads it.
    auth_cookie_name: str = Field(default="skinvision_auth")

    # --- Logging ---
    log_level: str = Field(default="INFO")


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached ``Settings`` instance."""
    return Settings()
