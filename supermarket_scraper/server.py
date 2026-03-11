import sys
import os
import asyncio
import logging
import threading
from typing import Optional

# Fix para Playwright en Windows: ProactorEventLoop no soporta subprocesos en threads
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))

import database as db
from sepa_downloader import descargar_y_actualizar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="PrecioYa API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── Scheduler diario ──────────────────────────────────────────────────────────

def _iniciar_scheduler():
    """Lanza un hilo que ejecuta la descarga SEPA una vez al día (3:00 AM)."""
    import time
    from datetime import datetime, timedelta

    def _loop():
        while True:
            ahora = datetime.now()
            proxima = ahora.replace(hour=3, minute=0, second=0, microsecond=0)
            if proxima <= ahora:
                proxima += timedelta(days=1)
            segundos = (proxima - ahora).total_seconds()
            logger.info(f"Próxima descarga SEPA en {segundos/3600:.1f} h ({proxima})")
            time.sleep(segundos)
            logger.info("Iniciando descarga diaria SEPA...")
            descargar_y_actualizar()

    t = threading.Thread(target=_loop, daemon=True, name="sepa-scheduler")
    t.start()


@app.on_event("startup")
def on_startup():
    db.init_db()

    # Si la DB está vacía o el último update fue antes de hoy, descargar ahora
    ultima = db.get_meta("last_update")
    from datetime import date
    hoy = str(date.today())

    if ultima != hoy or db.count_productos() == 0:
        logger.info("DB desactualizada o vacía — iniciando descarga SEPA en background...")
        t = threading.Thread(
            target=descargar_y_actualizar, daemon=True, name="sepa-startup"
        )
        t.start()
    else:
        logger.info(f"DB SEPA al día ({ultima}, {db.count_productos():,} productos)")

    _iniciar_scheduler()


# ── Modelos ───────────────────────────────────────────────────────────────────

class ProductoResponse(BaseModel):
    nombre: str
    precio: float
    precio_str: str
    supermercado: str
    url: str
    imagen_url: Optional[str] = None
    precio_por_unidad: Optional[str] = None


class BusquedaResponse(BaseModel):
    query: str
    total: int
    productos: list[ProductoResponse]
    supermercados_consultados: list[str]
    supermercados_disponibles: list[str]


# Cadenas disponibles en el sistema SEPA
CADENAS_DISPONIBLES = list(db.CADENAS_SEPA.keys())


def _precio_str(precio: float) -> str:
    return f"${precio:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/supermercados")
def get_supermercados():
    return CADENAS_DISPONIBLES


@app.get("/api/estado")
def get_estado():
    """Estado de la base de datos SEPA."""
    return {
        "last_update": db.get_meta("last_update"),
        "total_productos": db.count_productos(),
        "cadenas": db.get_cadenas(),
    }


@app.post("/api/actualizar")
def trigger_actualizacion(background_tasks: BackgroundTasks):
    """Dispara manualmente una descarga SEPA."""
    background_tasks.add_task(descargar_y_actualizar)
    return {"status": "descarga iniciada en background"}


@app.get("/api/buscar", response_model=BusquedaResponse)
def buscar(
    q: str = Query(..., description="Término de búsqueda"),
    supers: str = Query(
        "carrefour,coto,la_anonima,dia,walmart",
        description="Cadenas separadas por coma",
    ),
    max: int = Query(6, description="Máximo de resultados por cadena"),
):
    supers_lista = [
        s.strip() for s in supers.split(",")
        if s.strip() in db.CADENAS_SEPA
    ]
    if not supers_lista:
        supers_lista = CADENAS_DISPONIBLES

    # Consultar DB SEPA
    rows = db.buscar_productos(q, supers_lista, limit=max * len(supers_lista))

    productos = [
        ProductoResponse(
            nombre=r["nombre"],
            precio=r["precio"],
            precio_str=_precio_str(r["precio"]),
            supermercado=r["cadena"],
            url="",
            imagen_url=r.get("imagen_url") or "",
        )
        for r in rows
    ]

    # Cadenas que tienen al menos un resultado
    consultados = list({p.supermercado for p in productos})

    return BusquedaResponse(
        query=q,
        total=len(productos),
        productos=productos,
        supermercados_consultados=consultados,
        supermercados_disponibles=CADENAS_DISPONIBLES,
    )
