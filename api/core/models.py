# -*- coding: utf-8 -*-
"""Core data models for Scribe-IA API."""

from typing import List, Optional
from pydantic import BaseModel, Field, validator


class Turn(BaseModel):
    """Represents a single turn in a conversation transcript."""

    speaker: str = Field(..., description="DOCTOR/PACIENTE/u otro")
    text: str = Field(..., min_length=1)
    t0: Optional[float] = None
    t1: Optional[float] = None
    clinical: Optional[bool] = None

    @validator("speaker", pre=True, always=True)
    def _norm_speaker(cls, v):
        return (v or "").strip().upper()


class GenerateBody(BaseModel):
    """Request body for generating clinical history from transcript."""

    encounter_id: str
    patient_id: str
    practitioner_id: str
    schema_id: str = "auto"
    transcript: List[Turn] = Field(..., min_items=1)