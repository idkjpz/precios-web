"""
Descargador del dataset SEPA (Sistema Electrónico de Publicidad de Precios Argentinos).

Fuente oficial: https://datos.produccion.gob.ar/dataset/sepa-precios
Los archivos se publican como ZIP con CSVs adentro, con actualización diaria.

Columnas conocidas del CSV SEPA:
  id_producto, nombre_producto, marca, precio_unitario,
  comercio_id, comercio_razon_social, sucursal_id, sucursal_nombre,
  provincia, localidad, fecha
"""
import io
import os
import csv
import zipfile
import sqlite3
import logging
import requests
from datetime import date
from collections import defaultdict

from database import DB_PATH, init_db, set_meta

logger = logging.getLogger(__name__)

# API CKAN del portal de datos abiertos
CKAN_API_URL = "https://datos.produccion.gob.ar/api/3/action/package_show?id=sepa-precios"

# Headers a enviar cuando se descarga
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PrecioYa/1.0; precio-comparison-tool)",
}

# Nombres de columna alternativos que puede tener el CSV
_COL_NOMBRE = ("nombre_producto", "producto_nombre", "descripcion", "nombre", "Nombre")
_COL_PRECIO = ("precio_unitario", "precio", "Precio", "precio_lista")
_COL_CADENA = (
    "comercio_razon_social", "comercioRazonSocial",
    "bandera_descripcion", "banderaDescripcion",
    "cadena", "comercio",
)
_COL_PRODUCTO_ID = ("id_producto", "producto_id", "productoid", "ean", "codigo_barras")
_COL_SUCURSAL = ("sucursal_id", "sucursalId")
_COL_MARCA = ("marca",)


def _first(row: dict, keys: tuple) -> str:
    for k in keys:
        v = row.get(k, "")
        if v:
            return str(v).strip()
    return ""


def _get_latest_zip_url() -> str:
    """Consulta la API CKAN y devuelve la URL del ZIP más reciente."""
    logger.info("Consultando API CKAN para dataset SEPA...")
    resp = requests.get(CKAN_API_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resources = resp.json()["result"]["resources"]

    # Filtrar por ZIP o CSV, ordenar por fecha de modificación
    candidatos = [
        r for r in resources
        if r.get("format", "").upper() in ("ZIP", "CSV", "")
        and r.get("url", "").endswith((".zip", ".csv"))
    ]
    if not candidatos:
        # tomar cualquiera si no hay .zip/.csv explícito
        candidatos = resources

    candidatos.sort(
        key=lambda r: r.get("last_modified") or r.get("created") or "",
        reverse=True,
    )
    url = candidatos[0]["url"]
    logger.info(f"Recurso más reciente: {url}")
    return url


def _parsear_csv(content: str, cadena_default: str = "") -> list[dict]:
    """
    Parsea un CSV SEPA y devuelve una lista de dicts con
    {nombre, marca, precio, cadena, producto_id}.
    Agrupa por (nombre, cadena) quedándose con el precio mínimo.
    """
    # Detectar separador (coma o punto y coma)
    primera_linea = content.split("\n")[0]
    sep = ";" if primera_linea.count(";") > primera_linea.count(",") else ","

    reader = csv.DictReader(io.StringIO(content), delimiter=sep)
    headers = list(reader.fieldnames or [])
    logger.debug(f"Columnas detectadas: {headers}")

    # Agregar por (nombre, cadena) con precio mínimo
    agrupado: dict[tuple, dict] = {}

    for row in reader:
        nombre = _first(row, _COL_NOMBRE)
        if not nombre or len(nombre) < 3:
            continue

        precio_str = _first(row, _COL_PRECIO).replace(",", ".").replace("$", "")
        try:
            precio = float(precio_str)
        except ValueError:
            continue
        if precio <= 0:
            continue

        cadena = _first(row, _COL_CADENA) or cadena_default
        if not cadena:
            cadena = "Desconocido"

        producto_id = _first(row, _COL_PRODUCTO_ID)
        marca = _first(row, _COL_MARCA)
        key = (nombre.lower(), cadena.lower())

        if key not in agrupado or precio < agrupado[key]["precio"]:
            agrupado[key] = {
                "nombre": nombre,
                "marca": marca,
                "precio": precio,
                "cadena": cadena,
                "producto_id": producto_id,
                "imagen_url": "",
            }

    return list(agrupado.values())


def _parsear_zip_interno(zip_bytes: bytes, nombre_zip: str) -> list[dict]:
    """Extrae y parsea CSVs de un ZIP interno (por cadena)."""
    productos: list[dict] = []
    cadena_default = os.path.basename(nombre_zip).replace(".zip", "")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            archivos = zf.namelist()
            csvs = [n for n in archivos if n.lower().endswith(".csv")]
            if not csvs:
                csvs = [n for n in archivos if n.lower().endswith(".txt")]
            logger.debug(f"  ZIP interno {nombre_zip}: {archivos}")
            for nombre_csv in csvs:
                with zf.open(nombre_csv) as f:
                    content = f.read().decode("utf-8", errors="replace")
                    resultado = _parsear_csv(content, cadena_default)
                    logger.info(f"  {nombre_zip}/{nombre_csv}: {len(resultado)} productos")
                    productos.extend(resultado)
    except Exception as e:
        logger.warning(f"Error en ZIP interno {nombre_zip}: {e}")
    return productos


def _procesar_zip(zip_bytes: bytes) -> list[dict]:
    """Extrae y parsea todos los CSVs de un ZIP SEPA (puede tener ZIPs anidados)."""
    todos: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        todos_archivos = zf.namelist()
        logger.info(f"Archivos en ZIP externo ({len(todos_archivos)}): {todos_archivos[:5]}...")

        csvs_directos = [n for n in todos_archivos if n.lower().endswith(".csv")]
        zips_internos = [n for n in todos_archivos if n.lower().endswith(".zip")]

        # Caso 1: CSVs directos en el ZIP externo
        for nombre_csv in csvs_directos:
            cadena_default = os.path.basename(nombre_csv).replace(".csv", "")
            with zf.open(nombre_csv) as f:
                try:
                    content = f.read().decode("utf-8", errors="replace")
                    resultado = _parsear_csv(content, cadena_default)
                    logger.info(f"  {nombre_csv}: {len(resultado)} productos")
                    todos.extend(resultado)
                except Exception as e:
                    logger.warning(f"Error parseando {nombre_csv}: {e}")

        # Caso 2: ZIPs anidados (estructura SEPA actual)
        logger.info(f"ZIPs internos a procesar: {len(zips_internos)}")
        for nombre_zip in zips_internos:
            with zf.open(nombre_zip) as f:
                inner_bytes = f.read()
            resultado = _parsear_zip_interno(inner_bytes, nombre_zip)
            todos.extend(resultado)

    return todos


def descargar_y_actualizar() -> tuple[bool, str]:
    """
    Descarga el dataset SEPA más reciente, parsea y actualiza la DB.
    Devuelve (éxito, mensaje).
    """
    try:
        init_db()
        url = _get_latest_zip_url()

        logger.info(f"Descargando {url} ...")
        resp = requests.get(url, headers=HEADERS, timeout=180, stream=True)
        resp.raise_for_status()
        raw = resp.content
        logger.info(f"Descargado: {len(raw):,} bytes")

        # Detectar si es ZIP o CSV directo
        if raw[:2] == b"PK":
            productos = _procesar_zip(raw)
        else:
            content = raw.decode("utf-8", errors="replace")
            productos = _parsear_csv(content)

        if not productos:
            return False, "El archivo no contenía productos reconocibles"

        logger.info(f"Insertando {len(productos):,} productos en DB...")
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM productos")
        conn.executemany(
            """INSERT INTO productos
               (producto_id, nombre, marca, precio, cadena, imagen_url)
               VALUES (:producto_id, :nombre, :marca, :precio, :cadena, :imagen_url)""",
            productos,
        )
        hoy = str(date.today())
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_update', ?)", (hoy,)
        )
        total = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        conn.commit()
        conn.close()

        msg = f"OK – {total:,} productos actualizados al {hoy}"
        logger.info(msg)
        return True, msg

    except Exception as e:
        msg = f"Error: {e}"
        logger.error(msg, exc_info=True)
        return False, msg


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ok, msg = descargar_y_actualizar()
    print("✓" if ok else "✗", msg)
