# api/printouts.py
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

router = APIRouter()

# Intenta primero /<repo>/web/templates (basado en la ubicación real del archivo)
default_dir = Path(__file__).resolve().parents[1] / "web" / "templates"
# Fallback al cwd/web/templates por si el working dir es diferente
cwd_dir = Path.cwd() / "web" / "templates"

TEMPLATES_DIR = default_dir if default_dir.exists() else cwd_dir
env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

@router.get("/_debug", response_class=JSONResponse)
async def print_debug():
    """Muestra dónde está buscando templates y qué archivos ve."""
    return {
        "templates_dir": str(TEMPLATES_DIR),
        "exists": TEMPLATES_DIR.exists(),
        "files": [p.name for p in TEMPLATES_DIR.glob("*")],
    }

@router.get("/historia", response_class=HTMLResponse)
async def print_historia(encounter_id: str = Query(...)):
    try:
        # DEMO: aquí pondrás tu json real por encounter_id
        data = {
            "encounter_id": encounter_id,
            "paciente": {"nombre": "Paciente Demo"},
            "json": {
                "motivo_consulta": "Molestia torácica con síntomas respiratorios",
                "enfermedad_actual": {
                    "inicio": "Hace 3 días",
                    "sintomas": "Tos seca, disnea de esfuerzos",
                    "descripcion": "Dolor torácico pleurítico que aumenta con inspiración profunda."
                },
                "examen_fisico": {"TA":"130/85","FC":"96 lpm","FR":"20 rpm","SatO2":"95%","Temp":"38 °C"}
            },
            "base_normativa_local": [
                "Resolución 1995 de 1999",
                "Ley 2015 de 2020 (HCE)",
                "Decreto 1011 de 2006 (SOGC)",
                "GPC Colombia (MSPS/IES)"
            ],
            "guias_internacionales": [
                "AHA/ACC (cardio)",
                "ESC (European Society of Cardiology)",
                "ADA (Diabetes)",
                "OMS (WHO)",
                "NICE (UK)"
            ],
        }
        tpl = env.get_template("historia_co.html")  # <- Debe existir en TEMPLATES_DIR
        html = tpl.render(**data)
        return HTMLResponse(html, status_code=200)
    except Exception as e:
        raise HTTPException(500, detail=f"print error: {e}")