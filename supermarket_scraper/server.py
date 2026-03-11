import sys
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

# Fix para Playwright en Windows: ProactorEventLoop no soporta subprocesos en threads
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))
from scrapers import SCRAPERS_DISPONIBLES

app = FastAPI(title="PrecioYa API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/supermercados")
def get_supermercados():
    return list(SCRAPERS_DISPONIBLES.keys())


@app.get("/api/buscar", response_model=BusquedaResponse)
def buscar(
    q: str = Query(..., description="Término de búsqueda"),
    supers: str = Query("carrefour,la_anonima", description="Supermercados separados por coma"),
    max: int = Query(6, description="Máximo de resultados por supermercado"),
):
    supers_lista = [s.strip() for s in supers.split(",") if s.strip() in SCRAPERS_DISPONIBLES]

    if not supers_lista:
        supers_lista = list(SCRAPERS_DISPONIBLES.keys())

    todos_productos = []
    consultados = []

    def buscar_en_super(nombre_super: str):
        scraper_cls = SCRAPERS_DISPONIBLES[nombre_super]
        scraper = scraper_cls()
        return nombre_super, scraper.buscar(q, max_resultados=max)

    with ThreadPoolExecutor(max_workers=len(supers_lista)) as executor:
        futures = {executor.submit(buscar_en_super, s): s for s in supers_lista}
        for future in as_completed(futures):
            try:
                nombre_super, productos = future.result()
                consultados.append(nombre_super)
                todos_productos.extend(productos)
            except Exception as e:
                print(f"Error en búsqueda paralela: {e}")

    todos_productos.sort(key=lambda p: p.precio)

    return BusquedaResponse(
        query=q,
        total=len(todos_productos),
        productos=[
            ProductoResponse(
                nombre=p.nombre,
                precio=p.precio,
                precio_str=p.precio_str,
                supermercado=p.supermercado,
                url=p.url,
                imagen_url=p.imagen_url,
                precio_por_unidad=p.precio_por_unidad,
            )
            for p in todos_productos
        ],
        supermercados_consultados=consultados,
        supermercados_disponibles=list(SCRAPERS_DISPONIBLES.keys()),
    )
