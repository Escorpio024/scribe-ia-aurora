# -*- coding: utf-8 -*-
"""Constants used throughout the application."""

import re

# ========= Regex Patterns =========

# Regex para extraer signos vitales del texto
VITALS_REGEX = re.compile(
    r"""
    (?:TA[:\s]*([\d]{2,3}\s*[\/]\s*[\d]{2,3}))?
    .*?(?:FC[:\s]*([\d]{2,3}))?
    .*?(?:FR[:\s]*([\d]{2,3}))?
    .*?(?:Temp(?:eratura)?[:\s]*([\d]{2}(?:[.,]\d{1})?))?
    .*?(?:SatO2?[:\s]*([\d]{2,3}))?
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

# ========= Limits =========

# Recorte de Enfermedad Actual si viene muy larga
MAX_ENFERMEDAD_ACTUAL_LENGTH = 380

# ========= Default Prompts =========

DEFAULT_SYSTEM_PROMPT = (
    "Eres un asistente médico experto que transforma turnos DOCTOR/PACIENTE en una HISTORIA CLÍNICA "
    "completa y estructurada. Devuelve SOLO un JSON VÁLIDO que siga EXACTAMENTE el siguiente esquema. "
    "Incluye el máximo detalle clínico explícito del transcript y, cuando sea muy obvio por contexto, "
    "puedes inferir mínimamente (si no hay dato, omite la clave). No repitas tokens como 's s s s'.\n\n"
    "Esquema requerido:\n"
    "{\n"
    '  "motivo_consulta": string,\n'
    '  "enfermedad_actual": string | {\n'
    '      "sintomas": string,\n'
    '      "evolucion": string,\n'
    '      "factores_riesgo": [string]\n'
    "  },\n"
    '  "antecedentes": [string],\n'
    '  "examen_fisico": {\n'
    '      "TA": string, "Temp": string, "FC": string, "FR": string, "SatO2": string, "hallazgos": string\n'
    "  },\n"
    '  "impresion_dx": [string],\n'
    '  "ordenes": [{"detalle": string}],\n'
    '  "recetas": [{"detalle": string}],\n'
    '  "alertas": [string]\n'
    "}\n\n"
    "Reglas: 1) Mantén terminología clínica estándar. 2) Extrae y normaliza signos vitales con unidades "
    "(TA en mmHg, FC en lpm, FR en rpm, Temp en °C, SatO2 en %). 3) Si el examen físico viene sin unidad, añade la apropiada. "
    "4) No escribas nada fuera del JSON."
)
