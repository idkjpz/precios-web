import requests
from urllib.parse import quote
from .base_scraper import BaseScraper, Producto


class LaAnonimaScaper(BaseScraper):
    # El dominio principal es un SPA (VTEX IO), los endpoints API no funcionan ahí.
    # Usar el subdominio vtexcommercestable.com.br que expone la API directamente.
    # Candidatos de nombre de cuenta VTEX para La Anónima (probar en orden):
    VTEX_ACCOUNTS = ["laanonima", "laanonimaonline", "anonimaonline"]
    FRONTEND_BASE = "https://www.laanonimaonline.com"
    SEARCH_ENDPOINT = "/api/catalog_system/pub/products/search/{query}?_from=0&_to={to}&sc=1"

    API_HEADERS = {
        **BaseScraper.DEFAULT_HEADERS,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.laanonimaonline.com/",
    }

    def _parsear_items_vtex(self, data: list) -> list[Producto]:
        productos = []
        for item in data:
            try:
                nombre = item.get("productName", "")
                link = item.get("link", "")
                if not link.startswith("http"):
                    link = self.FRONTEND_BASE + link

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
        return productos

    def buscar(self, query: str, max_resultados: int = 6) -> list[Producto]:
        self._esperar()

        for account in self.VTEX_ACCOUNTS:
            api_base = f"https://{account}.vtexcommercestable.com.br"
            url = api_base + self.SEARCH_ENDPOINT.format(
                query=quote(query),
                to=max_resultados - 1,
            )
            try:
                response = requests.get(url, headers=self.API_HEADERS, timeout=15)
                preview = response.text[:150].strip()
                print(f"[La Anónima] account={account} status={response.status_code} preview={repr(preview)}")

                if response.status_code == 200 and preview.startswith("["):
                    data = response.json()
                    if isinstance(data, list) and data:
                        return self._parsear_items_vtex(data)[:max_resultados]
            except Exception as e:
                print(f"[La Anónima] Error con account={account}: {e}")

        print(f"[La Anónima] No se encontraron resultados para '{query}'")
        return []
