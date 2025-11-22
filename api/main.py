# -*- coding: utf-8 -*-
"""
Scribe-IA API - Main application entry point.

This is the simplified main file that orchestrates all routes.
Business logic has been moved to services, routes, and utils modules.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings

# Import routers
from api.routes import health, ingest, nlp, fhir, knowledge, pubmed, cds, agent
from api.routes import print as print_routes

# Create FastAPI app
app = FastAPI(
    title="Scribe IA API",
    version="3.0.0",
    description="Medical transcription and clinical decision support API"
)

# Configure CORS
allow_origins = settings.CORS_ALLOWED if isinstance(settings.CORS_ALLOWED, list) else [settings.CORS_ALLOWED]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router, tags=["health"])
app.include_router(ingest.router, tags=["ingest"])
app.include_router(nlp.router, tags=["nlp"])
app.include_router(fhir.router, tags=["fhir"])
app.include_router(knowledge.router, tags=["knowledge"])
app.include_router(pubmed.router, tags=["pubmed"])
app.include_router(cds.router, tags=["cds"])
app.include_router(agent.router, tags=["agent"])  # New clinical agent routes
app.include_router(print_routes.router, prefix="/print", tags=["print"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL,
        reload=False
    )
