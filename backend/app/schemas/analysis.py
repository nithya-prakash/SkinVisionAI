"""Session and analysis identifier schemas, and the top-level analysis shape.

``SkinAnalysisRead`` intentionally leaves ``visual_observations`` and
``structured_response`` empty/``None`` until the Phase 3 vision pipeline and
Phase 6/7 agent exist — Phase 1 must not fabricate ML output.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DISCLAIMER
from app.schemas.image import ImageMetadataRead
from app.schemas.vision import VisualAnalysisResult, VisualObservation


class AnalysisStatus(StrEnum):
    """Lifecycle state of a ``SkinAnalysis`` run, as stored in the database."""

    PENDING = "pending"
    IMAGE_UPLOADED = "image_uploaded"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisClientStatus(StrEnum):
    """Client-facing analysis status (Phase 8), derived from
    ``(SkinAnalysis.status, ImageMetadata.quality_result.is_acceptable)``
    rather than stored as a sixth database value -- see
    ``app.services.analysis_query_service._derive_client_status`` and
    docs/persistence.md. ``image_uploaded`` never appears to a client: it
    is always reported as one of the two states below instead, so the
    frontend never has to re-check the quality result itself.
    """

    QUALITY_REJECTED = "quality_rejected"
    READY_FOR_VISUAL_ANALYSIS = "ready_for_visual_analysis"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionRead(BaseModel):
    """An anonymous session identifier, as returned by the API."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    created_at: datetime


class SkinAnalysisCreate(BaseModel):
    """Payload accepted when starting a new analysis for an uploaded image."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    image_id: UUID


class SkinAnalysisRead(BaseModel):
    """An analysis run as returned by the API.

    ``visual_observations`` is populated by the Phase 3 vision pipeline and
    is empty until then. This schema never carries a diagnosis field.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    image_id: UUID
    status: AnalysisStatus
    visual_observations: list[VisualObservation] = Field(default_factory=list)
    created_at: datetime
    disclaimer: str = DISCLAIMER


class AnalysisDetailResponse(BaseModel):
    """Response for ``GET /api/analysis/{id}`` (Phase 8).

    Never exposes ``ImageMetadata.storage_path`` (via ``ImageMetadataRead``,
    same as the upload response) or any other filesystem detail.
    ``visual_analysis`` is ``None`` until ``status`` is ``completed`` --
    never a fabricated/placeholder result.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    status: AnalysisClientStatus
    image: ImageMetadataRead
    visual_analysis: VisualAnalysisResult | None = None
    disclaimer: str = DISCLAIMER
    created_at: datetime
    updated_at: datetime
