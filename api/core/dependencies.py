# api/core/dependencies.py
# -*- coding: utf-8 -*-
"""ASR dependencies and configuration."""

import os
from typing import List, Dict, Any, Optional

from faster_whisper import WhisperModel
from api.config import settings

# =========================
# Configuración por entorno
# =========================
ASR_MODEL_NAME     = settings.ASR_MODEL
ASR_LANGUAGE       = settings.ASR_LANGUAGE or None
ASR_COMPUTE_TYPE   = settings.ASR_COMPUTE_TYPE
ASR_BEAM_SIZE      = int(os.getenv("ASR_BEAM_SIZE", "5"))
ASR_TEMPERATURES   = tuple(float(x) for x in os.getenv("ASR_TEMPERATURES", "0.0,0.2,0.4,0.6").split(","))
ASR_VAD_FILTER     = settings.ASR_VAD
ASR_VAD_THRESHOLD  = float(os.getenv("ASR_VAD_THRESHOLD", "0.6"))
ASR_WORD_TS        = os.getenv("ASR_WORD_TIMESTAMPS", "false").lower() == "true"
ASR_COND_ON_PREV   = os.getenv("ASR_CONDITION_ON_PREV", "false").lower() == "true"
ASR_NO_SPEECH_PROB = float(os.getenv("ASR_NO_SPEECH_PROB", "0.6"))

# Filtros post-ASR
CLEAN_MIN_CHARS     = int(os.getenv("CLEAN_MIN_CHARS", "8"))
CLEAN_DROP_LOW_PROB = os.getenv("CLEAN_DROP_LOW_PROB", "true").lower() == "true"
CLEAN_LOGPROB_MIN   = float(os.getenv("CLEAN_LOGPROB_MIN", "-0.6"))

# Pausa (seg) que dispara cambio de hablante en la heurística
HEURISTIC_GAP_SEC   = float(os.getenv("ASR_HEURISTIC_GAP", "2.5"))

# =========================
# Correcciones frecuentes
# =========================
_REPLACE_MAP = {
    "hebres": "fiebres", "hebre": "fiebre", "tamol": "paracetamol",
    "tos eca": "tos seca", "toseca": "tos seca",
    "civilancias": "sibilancias", "respiratorial": "respiratoria",
    "dercha": "derecha", "izqierda": "izquierda",
    "tención": "tensión", "fracuencia": "frecuencia",
    "olor": "dolor", "torats": "tórax", "demogramos": "hemograma",
    "neumoni": "neumonía"
}

_model: Optional[WhisperModel] = None

def get_asr() -> WhisperModel:
    """Inicializa (lazy) y retorna el modelo de ASR."""
    global _model
    if _model is None:
        _model = WhisperModel(
            ASR_MODEL_NAME,
            compute_type=ASR_COMPUTE_TYPE
        )
    return _model

def _light_normalize(text: str) -> str:
    """Normalización ligera + correcciones comunes."""
    t = (text or "").strip()
    low = t.lower()
    for wrong, right in _REPLACE_MAP.items():
        low = low.replace(wrong, right)
    if low:
        low = low[0].upper() + low[1:]
    return low

def _drop_bad_segment(text: str, avg_logprob: Optional[float]) -> bool:
    """Filtra segmentos de baja calidad/ruido."""
    if not text or len(text.strip()) < CLEAN_MIN_CHARS:
        return True
    if CLEAN_DROP_LOW_PROB and avg_logprob is not None and avg_logprob < CLEAN_LOGPROB_MIN:
        return True
    return False

def _assign_speakers_heuristic(segments) -> List[Dict[str, Any]]:
    """
    Heurística simple (sin diarización):
    - Alterna DOCTOR/PACIENTE.
    - Cambia de hablante si hay una pausa > HEURISTIC_GAP_SEC.
    """
    out: List[Dict[str, Any]] = []
    speaker_toggle = 0  # 0=DOCTOR, 1=PACIENTE (arranca DOCTOR por defecto)
    last_end = 0.0

    for seg in segments:
        # Los objetos de faster-whisper tienen .text/.start/.end; no siempre .avg_logprob (usamos getattr seguro)
        text = (getattr(seg, "text", "") or "").strip()
        avg_lp = getattr(seg, "avg_logprob", None)

        if _drop_bad_segment(text, avg_lp):
            continue

        clean = _light_normalize(text)

        start = float(getattr(seg, "start", 0.0) or 0.0)
        end   = float(getattr(seg, "end", start) or start)

        # Cambio de hablante por pausa grande
        if start - last_end > HEURISTIC_GAP_SEC:
            speaker_toggle = 1 - speaker_toggle

        spk = "DOCTOR" if speaker_toggle == 0 else "PACIENTE"

        out.append({
            "t0": round(start, 2),
            "t1": round(end, 2),
            "speaker": spk,
            "text": clean,
            "clinical": True
        })

        last_end = end
        # Alterna por línea para simular diálogo fluido
        speaker_toggle = 1 - speaker_toggle

    return out

def transcribe_file(wav_path: str) -> List[Dict[str, Any]]:
    """
    Transcribe un WAV y devuelve turnos estilo:
    [{t0,t1,speaker,text,clinical}]
    * Sin diarización (whisperx/pyannote) -> heurística simple de hablante.
    """
    model = get_asr()

    segments, _info = model.transcribe(
        wav_path,
        language=ASR_LANGUAGE,
        beam_size=ASR_BEAM_SIZE,
        best_of=ASR_BEAM_SIZE,
        temperature=ASR_TEMPERATURES,
        vad_filter=ASR_VAD_FILTER,
        vad_parameters={"threshold": ASR_VAD_THRESHOLD},
        word_timestamps=ASR_WORD_TS,
        condition_on_previous_text=ASR_COND_ON_PREV,
        no_speech_threshold=ASR_NO_SPEECH_PROB,
    )

    out = _assign_speakers_heuristic(segments)

    if not out:
        # Fallback si quedó vacío
        out = [{
            "t0": 0.0, "t1": 0.0, "speaker": "PACIENTE",
            "text": "No se entendió el audio (silencio o ruido).",
            "clinical": False
        }]

    return out