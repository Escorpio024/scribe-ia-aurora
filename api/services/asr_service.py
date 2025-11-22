# -*- coding: utf-8 -*-
"""ASR (Automatic Speech Recognition) service."""

from typing import List, Dict, Any
from api.core.dependencies import transcribe_file

__all__ = ["transcribe_audio"]


def transcribe_audio(wav_path: str) -> List[Dict[str, Any]]:
    """
    Transcribe audio file and return transcript with speaker diarization.
    
    Args:
        wav_path: Path to WAV audio file
        
    Returns:
        List of turns with speaker, text, timestamps
    """
    return transcribe_file(wav_path)
