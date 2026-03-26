"""Pydantic request models for app-facing wrappers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ValidatePayload(BaseModel):
    """App wrapper payload for conversion validation."""

    adf_json: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    pipeline_name: str | None = None


class ParallelRunPayload(BaseModel):
    """App wrapper payload for parallel execution checks."""

    pipeline_name: str = Field(min_length=1)
    parameters: dict[str, str] = Field(default_factory=dict)
    snapshot: dict[str, Any] | None = None
