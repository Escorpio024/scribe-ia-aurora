# api/text_normalizer.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import re
import unicodedata
from typing import List, Dict, Any

__all__ = [
    "normalize_text",
    "clean_inline_repetitions",
    "clean_text",
    "normalize_spanish_clinical",
    "normalize_transcript_turns",
]

# Espacios / puntuación
SPACE_RX        = re.compile(r"\s+")
PUNCT_RX        = re.compile(r"\s+([,.;:!?])")
PUNCT_DUP_RX    = re.compile(r"([,.;:!?])\1+")
DASH_SPACE_RX   = re.compile(r"\s*([–—-])\s*")
QUOTE_RX        = re.compile(r"[“”]")

# Repeticiones tipo “s s s s”, “eh eh eh”, “tos tos tos”
ISOLATED_LETTERS_RX   = re.compile(r"\b([a-zA-ZáéíóúñÑ])(?:\s+\1){2,}\b", re.IGNORECASE)
SHORT_TOKEN_REP_RX    = re.compile(r"\b([a-zA-ZáéíóúñÑ]{1,2})\b(?:\s+\1\b){2,}", re.IGNORECASE)
WORD_TRIPLE_RX        = re.compile(r"\b([a-zA-ZáéíóúñÑ]{3,})\b(?:\s+\1\b){2,}", re.IGNORECASE)

def _strip_accents(s: str) -> str:
    if not s:
        return s
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def clean_inline_repetitions(text: str) -> str:
    t = text or ""
    t = ISOLATED_LETTERS_RX.sub(lambda m: m.group(1), t)   # “s s s s” -> “s”
    t = SHORT_TOKEN_REP_RX.sub(lambda m: m.group(1), t)    # “eh eh eh” -> “eh”
    t = WORD_TRIPLE_RX.sub(lambda m: m.group(1), t)        # “tos tos tos” -> “tos”
    return t

def normalize_text(text: str) -> str:
    """Normalización genérica para enunciados sueltos."""
    if not text:
        return text
    t = text.strip()
    # comillas/guiones
    t = QUOTE_RX.sub('"', t)
    t = DASH_SPACE_RX.sub(r" \1 ", t)
    # repeticiones “s s s”
    t = clean_inline_repetitions(t)
    # puntuación/espacios
    t = PUNCT_DUP_RX.sub(r"\1", t)
    t = PUNCT_RX.sub(r"\1", t)
    t = SPACE_RX.sub(" ", t).strip()
    # capitalización suave
    if len(t) > 1 and t[0].isalpha():
        t = t[0].upper() + t[1:]
    return t

def clean_text(t: str) -> str:
    """Versión compacta usada por algunos pipelines heredados."""
    t = (t or "").strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\b([a-záéíóúñ])(?:\s+\1){2,}\b", r"\1", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(\w{2,})(?:\s+\1){1,}\b", r"\1", t, flags=re.IGNORECASE)
    t = re.sub(r"([!?.,;:])\1{1,}", r"\1", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([(\[]) +", r"\1", t)
    t = re.sub(r" +([)\]])", r"\1", t)
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t

def normalize_spanish_clinical(text: str) -> str:
    """
    Punto de entrada que espera nlp_pipeline: limpia repeticiones (“s s s”),
    normaliza espacios/puntuación y aplica capitalización suave.
    """
    if not text:
        return text
    # Combina las dos capas por robustez
    t = normalize_text(text)
    t = clean_text(t)
    # Evita duplicados extremos de nuevo por si quedaron
    t = clean_inline_repetitions(t)
    return t.strip()

def normalize_transcript_turns(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normaliza cada turno de transcript (speaker/text), eliminando “s s s”,
    espacios raros, etc. Mantiene t0/t1/clinical si vienen.
    """
    out: List[Dict[str, Any]] = []
    for t in turns or []:
        spk = (t.get("speaker") or "").strip().upper() or "OTRO"
        txt = normalize_spanish_clinical(t.get("text") or "")
        out.append({
            "speaker": spk,
            "text": txt,
            "t0": t.get("t0"),
            "t1": t.get("t1"),
            "clinical": t.get("clinical"),
        })
    return out