from .carrefour import CarrefourScraper
from .coto import CotoScraper
from .la_anonima import LaAnonimaScaper

SCRAPERS_DISPONIBLES = {
    "carrefour": CarrefourScraper,
    "coto": CotoScraper,
    "la_anonima": LaAnonimaScaper,
}
