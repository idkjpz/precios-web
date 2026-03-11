import sqlite3
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "sepa.db")

# Mapeo de clave interna → nombres de cadena en datos SEPA
CADENAS_SEPA: dict[str, list[str]] = {
    "carrefour": ["carrefour"],
    "coto": ["coto"],
    "la_anonima": ["anonima", "anónima"],
    "dia": ["dia", "día"],
    "walmart": ["walmart", "changomas", "changomás"],
    "jumbo": ["jumbo"],
    "disco": ["disco"],
    "vea": ["vea"],
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS productos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id TEXT,
            nombre      TEXT NOT NULL,
            marca       TEXT,
            precio      REAL NOT NULL,
            cadena      TEXT NOT NULL,
            imagen_url  TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_nombre ON productos(lower(nombre));
        CREATE INDEX IF NOT EXISTS idx_cadena ON productos(cadena);
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    conn.close()


def buscar_productos(
    query: str,
    cadenas: list[str],
    limit: int = 6,
) -> list[dict]:
    """Busca productos en la DB por nombre (todas las palabras) y cadenas."""
    conn = _get_conn()

    palabras = query.lower().split()
    where_nombre = " AND ".join("lower(nombre) LIKE ?" for _ in palabras)
    params: list = [f"%{p}%" for p in palabras]

    # Expandir claves de cadena a nombres SEPA reales
    nombres_cadenas: list[str] = []
    for clave in cadenas:
        nombres_cadenas.extend(CADENAS_SEPA.get(clave, [clave.lower()]))

    if nombres_cadenas:
        placeholders = ",".join("?" * len(nombres_cadenas))
        where_cadena = f"AND lower(cadena) IN ({placeholders})"
        params.extend(nombres_cadenas)
    else:
        where_cadena = ""

    params.append(limit * (len(cadenas) or 1))

    sql = f"""
        SELECT nombre, precio, cadena, imagen_url, producto_id
        FROM productos
        WHERE {where_nombre} {where_cadena}
        ORDER BY precio ASC
        LIMIT ?
    """
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def count_productos() -> int:
    conn = _get_conn()
    n = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
    conn.close()
    return n


def get_cadenas() -> list[str]:
    conn = _get_conn()
    rows = conn.execute("SELECT DISTINCT cadena FROM productos ORDER BY cadena").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_meta(key: str) -> Optional[str]:
    conn = _get_conn()
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None


def set_meta(key: str, value: str) -> None:
    conn = _get_conn()
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
