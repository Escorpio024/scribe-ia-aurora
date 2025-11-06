# -*- coding: utf-8 -*-
import os

# ========= API / Infra =========
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8080"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

# Acepta lista separada por comas; '*' para permitir todo en dev
CORS_ALLOWED = [o.strip() for o in os.getenv("CORS_ALLOWED", "*").split(",")]

# Dir temporales y conocimiento
TMP_DIR = os.getenv("TMP_DIR", "/tmp")
DATA_DIR = os.getenv("DATA_DIR", "/data")
KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", "/app/knowledge")

# ========= FHIR =========
# En docker-compose el servicio suele llamarse 'hapi'
FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "http://hapi:8080/fhir")

# ========= LLaMA (Ollama) =========
# En docker-compose tu servicio se llama 'scribe_ollama'; en local usa http://localhost:11434
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://scribe_ollama:11434")

# Compatibilidad: si defines OLLAMA_MODEL_PRIMARY en .env, lo usamos; si no, LLM_MODEL;
# si ninguno está, por defecto llama3:8b
LLM_MODEL = (
    os.getenv("LLM_MODEL")
    or os.getenv("OLLAMA_MODEL_PRIMARY")
    or "llama3:8b"
)
# Modelo de respaldo opcional (no lo usamos por defecto, pero queda disponible)
OLLAMA_MODEL_FALLBACK = os.getenv("OLLAMA_MODEL_FALLBACK", LLM_MODEL)

# Forzar salida JSON desde el LLM (si tu wrapper lo soporta)
OLLAMA_JSON_ENFORCE = os.getenv("OLLAMA_JSON_ENFORCE", "true").lower() == "true"

# ========= ASR (faster-whisper) =========
ASR_MODEL = os.getenv("ASR_MODEL", "base")
ASR_COMPUTE_TYPE = os.getenv("ASR_COMPUTE_TYPE", "int8")
ASR_LANGUAGE = os.getenv("ASR_LANGUAGE", "es")
ASR_SAMPLE_RATE = int(os.getenv("ASR_SAMPLE_RATE", "16000"))
ASR_MAX_MINUTES = int(os.getenv("ASR_MAX_MINUTES", "15"))
ASR_VAD = os.getenv("ASR_VAD", "true").lower() == "true"

# ========= PubMed =========
PUBMED_EUTILS_BASE = os.getenv(
    "PUBMED_EUTILS_BASE",
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
)
PUBMED_EMAIL = os.getenv("PUBMED_EMAIL", "you@example.com")

# ========= System prompt =========
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    (
        "Eres un asistente médico experto que transforma turnos DOCTOR/PACIENTE en una HISTORIA CLÍNICA "
        "completa y estructurada. Devuelve SOLO un JSON VÁLIDO que siga EXACTAMENTE el siguiente esquema. "
        "Incluye el máximo detalle clínico explícito del transcript y, cuando sea muy obvio por contexto, "
        "puedes inferir mínimamente (si no hay dato, omite la clave). No repitas tokens como 's s s s'.\n\n"
        "Esquema requerido:\n"
        "{\n"
        "  \"motivo_consulta\": string,\n"
        "  \"enfermedad_actual\": string | {\n"
        "      \"sintomas\": string,\n"
        "      \"evolucion\": string,\n"
        "      \"factores_riesgo\": [string]\n"
        "  },\n"
        "  \"antecedentes\": [string],\n"
        "  \"examen_fisico\": {\n"
        "      \"TA\": string, \"Temp\": string, \"FC\": string, \"FR\": string, \"SatO2\": string, \"hallazgos\": string\n"
        "  },\n"
        "  \"impresion_dx\": [string],\n"
        "  \"ordenes\": [{\"detalle\": string}],\n"
        "  \"recetas\": [{\"detalle\": string}],\n"
        "  \"alertas\": [string]\n"
        "}\n\n"
        "Reglas: 1) Mantén terminología clínica estándar. 2) Extrae y normaliza signos vitales con unidades "
        "(TA en mmHg, FC en lpm, FR en rpm, Temp en °C, SatO2 en %). 3) Si el examen físico viene sin unidad, añade la apropiada. "
        "4) No escribas nada fuera del JSON."
    )
)