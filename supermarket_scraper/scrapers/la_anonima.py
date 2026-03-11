import requests
from urllib.parse import quote
from .base_scraper import BaseScraper, Producto


class LaAnonimaScaper(BaseScraper):
    BASE_URL = "https://www.laanonimaonline.com"
    SEARCH_ENDPOINT = "/api/catalog_system/pub/products/search/{query}?_from=0&_to={to}"
    INTELLIGENT_SEARCH_ENDPOINT = "/api/io/_v/api/intelligent-search/product_search/?query={query}&count={count}&page=1"

    def _make_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            **self.DEFAULT_HEADERS,
            "Accept": "application/json, text/plain, */*",
            "Referer": self.BASE_URL + "/",
            "Origin": self.BASE_URL,
        })
        # Visitar homepage para obtener cookies de sesión
        try:
            session.get(self.BASE_URL, timeout=10)
        except Exception:
            pass
        return session

    def _parsear_items_vtex(self, data: list) -> list[Producto]:
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
        return productos

    def buscar(self, query: str, max_resultados: int = 6) -> list[Producto]:
        self._esperar()
        session = self._make_session()

        # Intento 1: Legacy VTEX catalog search API
        url = self.BASE_URL + self.SEARCH_ENDPOINT.format(
            query=quote(query),
            to=max_resultados - 1,
        )
        try:
            response = session.get(url, timeout=15)
            print(f"[La Anónima] API legacy status: {response.status_code}, body len: {len(response.text)}")
            if response.status_code == 200 and response.text.strip():
                data = response.json()
                if isinstance(data, list) and data:
                    return self._parsear_items_vtex(data)[:max_resultados]
        except Exception as e:
            print(f"[La Anónima] Error con API legacy '{query}': {e}")

        # Intento 2: VTEX Intelligent Search API
        url2 = self.BASE_URL + self.INTELLIGENT_SEARCH_ENDPOINT.format(
            query=quote(query),
            count=max_resultados,
        )
        try:
            response2 = session.get(url2, timeout=15)
            print(f"[La Anónima] Intelligent Search status: {response2.status_code}, body len: {len(response2.text)}")
            if response2.status_code == 200 and response2.text.strip():
                data2 = response2.json()
                products = data2.get("products", [])
                if products:
                    return self._parsear_items_vtex(products)[:max_resultados]
        except Exception as e:
            print(f"[La Anónima] Error con Intelligent Search '{query}': {e}")

        print(f"[La Anónima] No se encontraron resultados para '{query}'")
        return []
