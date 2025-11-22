# 🩺 Scribe-IA Aurora

**Scribe-IA** es un sistema inteligente de transcripción médica y soporte a decisiones clínicas que convierte consultas médicas grabadas en historias clínicas estructuradas con formato FHIR.

## ✨ Características

- 🎤 **Transcripción automática** con Whisper (faster-whisper)
- 🧠 **Generación de historia clínica** estructurada con LLM (Ollama + Llama3)
- 📋 **Extracción inteligente** de signos vitales, diagnósticos, órdenes y recetas
- 💡 **Soporte a decisiones clínicas (CDS)** con evidencia de PubMed
- 📦 **Integración FHIR** para interoperabilidad con sistemas de salud
- 🔍 **Búsqueda en PubMed** para aumentar conocimiento médico
- 🖨️ **Generación de reportes** en formato imprimible

## 🏗️ Arquitectura

### Backend (API)

El backend está organizado en una arquitectura modular y escalable:

```
api/
├── config/              # Configuración centralizada
│   ├── settings.py      # Variables de entorno y configuración
│   └── constants.py     # Constantes del sistema
├── core/                # Núcleo de la aplicación
│   ├── models.py        # Modelos Pydantic
│   └── dependencies.py  # Dependencias compartidas (ASR)
├── services/            # Lógica de negocio
│   ├── asr_service.py   # Transcripción de audio
│   ├── nlp_service.py   # Procesamiento NLP
│   ├── fhir_service.py  # Integración FHIR
│   ├── cds_service.py   # Soporte a decisiones clínicas
│   └── knowledge_service.py  # Gestión de conocimiento
├── routes/              # Endpoints de API
│   ├── health.py        # Health checks
│   ├── ingest.py        # Ingesta de audio
│   ├── nlp.py           # Procesamiento NLP
│   ├── fhir.py          # FHIR
│   ├── knowledge.py     # Gestión de conocimiento
│   ├── pubmed.py        # Búsqueda en PubMed
│   ├── cds.py           # CDS
│   └── print.py         # Impresión de reportes
├── utils/               # Utilidades
│   ├── text_processing.py    # Procesamiento de texto
│   ├── rule_extraction.py    # Extracción de reglas
│   ├── postprocessing.py     # Post-procesamiento
│   └── augmentation.py       # Aumentación con PubMed
└── main.py              # Entry point (50 líneas)
```

### Frontend (Web)

Interfaz web interactiva para:
- Grabar audio de consultas médicas
- Visualizar transcripciones
- Editar historia clínica generada
- Ver sugerencias CDS
- Exportar a FHIR

## 🚀 Inicio Rápido

### Requisitos

- Docker y Docker Compose
- 8GB+ RAM (para Ollama + Whisper)

### Instalación

1. **Clonar el repositorio**
   ```bash
   git clone <repo-url>
   cd scribe-ia
   ```

2. **Configurar variables de entorno**
   ```bash
   cp .env.example .env
   # Editar .env según necesidades
   ```

3. **Iniciar servicios**
   ```bash
   docker compose up -d
   ```

   Esto iniciará:
   - `scribe_api`: API principal (puerto 8080)
   - `scribe_ollama`: Servidor Ollama con Llama3 (puerto 11434)
   - `hapi`: Servidor FHIR (puerto 8081)

4. **Verificar que todo funciona**
   ```bash
   curl http://localhost:8080/health
   # Debe retornar: {"status":"ok","service":"scribe-ia"}
   ```

5. **Abrir interfaz web**
   - Abrir `web/index.html` en navegador
   - O servir con: `python -m http.server 8000` desde carpeta `web/`

## 📖 Uso

### API

#### 1. Subir y transcribir audio

```bash
curl -X POST "http://localhost:8080/ingest/upload?encounter_id=enc123" \
  -F "wav=@audio.wav"
```

#### 2. Generar historia clínica

```bash
curl -X POST "http://localhost:8080/nlp/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "encounter_id": "enc123",
    "patient_id": "pat1",
    "practitioner_id": "doc1",
    "schema_id": "auto",
    "transcript": [
      {"speaker": "PACIENTE", "text": "Tengo dolor de cabeza desde hace 3 días"},
      {"speaker": "DOCTOR", "text": "¿Tiene fiebre?"}
    ]
  }'
```

#### 3. Obtener sugerencias CDS

```bash
curl -X POST "http://localhost:8080/cds/suggest" \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "diagnosis": "Cefalea tensional",
      "symptoms": "dolor de cabeza"
    },
    "use_pubmed": true
  }'
```

### Interfaz Web

1. **Configurar API base**: `http://localhost:8080`
2. **Llenar datos del paciente**
3. **Grabar audio** o subir archivo WAV
4. **Procesar**: Click en "Subir audio" → "Generar Historia"
5. **Revisar y editar** bloques clínicos
6. **Ver sugerencias CDS**
7. **Exportar a FHIR** o imprimir

## 🔧 Configuración

### Variables de Entorno

Ver `.env.example` para todas las opciones. Principales:

```bash
# API
API_PORT=8080
LOG_LEVEL=info

# LLM (Ollama)
OLLAMA_BASE_URL=http://scribe_ollama:11434
LLM_MODEL=llama3:8b

# ASR (Whisper)
ASR_MODEL=base
ASR_LANGUAGE=es
ASR_COMPUTE_TYPE=int8

# FHIR
FHIR_BASE_URL=http://hapi:8080/fhir

# PubMed
PUBMED_EMAIL=tu@email.com
```

## 🧪 Desarrollo

### Estructura del Código

- **Separación de responsabilidades**: Cada módulo tiene una función clara
- **Services**: Lógica de negocio reutilizable
- **Routes**: Endpoints HTTP que delegan a services
- **Utils**: Funciones auxiliares sin estado
- **Config**: Configuración centralizada

### Agregar Nueva Funcionalidad

1. **Crear servicio** en `api/services/`
2. **Crear route** en `api/routes/`
3. **Registrar router** en `api/main.py`
4. **Actualizar documentación**

### Testing

```bash
# Health check
curl http://localhost:8080/health

# Ver logs
docker compose logs -f scribe_api

# Reiniciar servicios
docker compose restart scribe_api
```

## 📚 Documentación Adicional

- [Arquitectura Detallada](docs/architecture.md) - Diagramas y explicación profunda
- [Referencia de API](docs/api-reference.md) - Todos los endpoints
- [Guía de Desarrollo](docs/development.md) - Convenciones y mejores prácticas
- [Guía de Despliegue](docs/deployment.md) - Producción y escalamiento

## 🤝 Contribuir

1. Fork el proyecto
2. Crear rama feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request

## 📄 Licencia

[Especificar licencia]

## 🙏 Agradecimientos

- [Faster Whisper](https://github.com/guillaumekln/faster-whisper) - Transcripción ASR
- [Ollama](https://ollama.ai/) - Servidor LLM local
- [HAPI FHIR](https://hapifhir.io/) - Servidor FHIR
- [FastAPI](https://fastapi.tiangolo.com/) - Framework web

---

**Versión**: 3.0.0 (Arquitectura modular)  
**Última actualización**: 2025-11-22
