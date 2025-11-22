# -*- coding: utf-8 -*-
"""Configuration module for Scribe-IA API."""

from .settings import settings
from .constants import (
    VITALS_REGEX,
    MAX_ENFERMEDAD_ACTUAL_LENGTH,
    DEFAULT_SYSTEM_PROMPT,
)

__all__ = [
    "settings",
    "VITALS_REGEX",
    "MAX_ENFERMEDAD_ACTUAL_LENGTH",
    "DEFAULT_SYSTEM_PROMPT",
]
