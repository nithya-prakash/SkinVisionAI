"""The structured-output contract requested from the LLM.

Deliberately narrative-only: there is no ``severity``, ``source``, or
``source_url`` field anywhere in this schema. The LLM cannot alter what
it was never given a field to write in the first place -- the final API
response (``app.schemas.explanation``) attaches those from the trusted
deterministic result, never from the model. References to deterministic
items (``rule_id``, ``ingredient``) are validated against the actual
deterministic input by ``app.llm.validation`` before this output is ever
merged into a response.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InteractionExplanationItem(BaseModel):
    """The LLM's plain-language explanation of one deterministic
    interaction, referenced by ``rule_id`` only.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1)
    explanation: str = Field(min_length=1, max_length=600)


class OverlapExplanationItem(BaseModel):
    """The LLM's plain-language explanation of one deterministic
    overlapping-active finding, referenced by canonical ingredient name.
    """

    model_config = ConfigDict(extra="forbid")

    ingredient: str = Field(min_length=1)
    explanation: str = Field(min_length=1, max_length=600)


class ExplanationLLMOutput(BaseModel):
    """The complete raw structure requested from the LLM for one
    explanation call. See ``app.llm.prompts`` for the system prompt that
    constrains how these fields must be filled in, and
    ``app.llm.validation`` for the checks run on this output before it is
    trusted.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1000)
    key_points: list[str] = Field(default_factory=list, max_length=8)
    interactions_explained: list[InteractionExplanationItem] = Field(default_factory=list)
    overlap_explained: list[OverlapExplanationItem] = Field(default_factory=list)
    routine_notes: list[str] = Field(default_factory=list, max_length=6)
