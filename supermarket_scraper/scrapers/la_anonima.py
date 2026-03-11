import requests
from urllib.parse import quote
from .base_scraper import BaseScraper, Producto


class LaAnonimaScaper(BaseScraper):
    BASE_URL = "https://www.laanonima.com.ar"
    SEARCH_ENDPOINT = "/api/catalog_system/pub/products/search/{query}?_from=0&_to={to}"

    def buscar(self, query: str, max_resultados: int = 6) -> list[Producto]:
        url = self.BASE_URL + self.SEARCH_ENDPOINT.format(
            query=quote(query),
            to=max_resultados - 1,
        )
        try:
            self._esperar()
            response = requests.get(url, headers=self.DEFAULT_HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[La Anónima] Error al buscar '{query}': {e}")
            return []

        productos = []
        for item in data:
            try:
                nombre = item.get("productName", "")
                link = item.get("link", "")
                if not link.startswith("http"):
                    link = self.BASE_URL + link

                items = item.get("items", [])
                if not items:
                    continue

                primer_item = items[0]
                imagenes = primer_item.get("images", [])
                imagen_url = imagenes[0].get("imageUrl", "") if imagenes else ""

                sellers = primer_item.get("sellers", [])
                if not sellers:
                    continue
                precio = sellers[0].get("commertialOffer", {}).get("Price", 0)

                if not precio or precio == 0:
                    continue

                productos.append(Producto(
                    nombre=nombre,
                    precio=float(precio),
                    precio_str=f"${precio:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    supermercado="La Anónima",
                    url=link,
                    imagen_url=imagen_url,
                ))
            except Exception as e:
                print(f"[La Anónima] Error parseando producto: {e}")
                continue

        return productos[:max_resultados]
