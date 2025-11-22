# -*- coding: utf-8 -*-
"""Audio ingest routes."""

import os
from fastapi import APIRouter, UploadFile, File, Query, HTTPException
from api.config import settings
from api.services.asr_service import transcribe_audio

router = APIRouter()


@router.post("/ingest/upload")
async def upload_audio(
    encounter_id: str = Query(..., description="ID del encuentro"),
    wav: UploadFile = File(..., description="WAV mono 16k (o se re-muestrea en backend)")
):
    """
    Upload and transcribe audio file.
    
    Returns transcript with speaker diarization.
    """
    try:
        os.makedirs(settings.TMP_DIR, exist_ok=True)
        path = os.path.join(settings.TMP_DIR, f"{encounter_id}.wav")
        
        # Save uploaded file
        raw = await wav.read()
        with open(path, "wb") as f:
            f.write(raw)
        
        # Transcribe
        transcript = transcribe_audio(path)
        
        return {
            "encounter_id": encounter_id,
            "transcript": transcript,
            "stored_wav": path
        }
    except Exception as e:
        raise HTTPException(500, f"ingest failed: {e}")
