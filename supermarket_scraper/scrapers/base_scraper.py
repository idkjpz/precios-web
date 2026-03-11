import re
import time
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Producto:
    nombre: str
    precio: float
    precio_str: str
    supermercado: str
    url: str
    imagen_url: Optional[str] = None
    precio_por_unidad: Optional[str] = None


class BaseScraper(ABC):
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    @abstractmethod
    def buscar(self, query: str, max_resultados: int = 6) -> list[Producto]:
        pass

    def _esperar(self, min_seg: float = 0.5, max_seg: float = 1.5) -> None:
        time.sleep(random.uniform(min_seg, max_seg))

    def _parsear_precio(self, texto: str) -> Optional[float]:
        if not texto:
            return None
        # Remove currency symbol and whitespace
        texto = texto.strip().replace("$", "").replace("\xa0", "").strip()
        # Handle Argentine format: "1.250,99" → 1250.99
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(".", "")
        try:
            return float(texto)
        except ValueError:
            return None
