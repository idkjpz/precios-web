import asyncio
import sys
import requests
from urllib.parse import quote
from .base_scraper import BaseScraper, Producto


class LaAnonimaScaper(BaseScraper):
    FRONTEND_BASE = "https://www.laanonimaonline.com"
    SEARCH_URL = "https://www.laanonimaonline.com/busqueda/?q={query}"

    # URLs que pueden contener datos de productos en las requests XHR del SPA
    PRODUCT_URL_KEYWORDS = [
        "search", "product", "catalog", "graphql", "intelligent", "busqueda", "buscar",
    ]

    def _extraer_productos_vtex_array(self, data: list, max_resultados: int) -> list[Producto]:
        """Parsea el formato array del catalog API de VTEX (legacy)."""
        productos = []
        for item in data[:max_resultados]:
            try:
                nombre = item.get("productName", "")
                link = item.get("link", "") or item.get("linkText", "")
                if link and not link.startswith("http"):
                    link = self.FRONTEND_BASE + "/" + link.lstrip("/")

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
                if not precio:
                    continue

                productos.append(self._crear_producto(nombre, precio, link, imagen_url))
            except Exception:
                continue
        return productos

    def _extraer_productos_vtex_io(self, data: dict, max_resultados: int) -> list[Producto]:
        """Parsea el formato del VTEX Intelligent Search (IO)."""
        productos = []
        items = (
            data.get("products") or
            data.get("data", {}).get("productSearch", {}).get("products") or
            []
        )
        for item in items[:max_resultados]:
            try:
                nombre = item.get("productName", "") or item.get("productTitle", "")
                link_text = item.get("linkText", "") or item.get("link", "")
                link = self.FRONTEND_BASE + "/" + link_text.lstrip("/") if link_text else ""

                skus = item.get("items", [])
                if not skus:
                    continue
                imagenes = skus[0].get("images", [])
                imagen_url = imagenes[0].get("imageUrl", "") if imagenes else ""
                sellers = skus[0].get("sellers", [])
                if not sellers:
                    continue
                precio = sellers[0].get("commertialOffer", {}).get("Price", 0)
                if not precio:
                    continue

                productos.append(self._crear_producto(nombre, precio, link, imagen_url))
            except Exception:
                continue
        return productos

    def _crear_producto(self, nombre: str, precio: float, link: str, imagen_url: str) -> Producto:
        precio_str = f"${precio:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return Producto(
            nombre=nombre,
            precio=float(precio),
            precio_str=precio_str,
            supermercado="La Anónima",
            url=link,
            imagen_url=imagen_url,
        )

    def _intentar_parsear_respuesta(self, data, max_resultados: int) -> list[Producto]:
        """Intenta extraer productos de cualquier formato JSON conocido."""
        if isinstance(data, list) and data and isinstance(data[0], dict):
            productos = self._extraer_productos_vtex_array(data, max_resultados)
            if productos:
                return productos

        if isinstance(data, dict):
            productos = self._extraer_productos_vtex_io(data, max_resultados)
            if productos:
                return productos

        return []

    async def _scrape_con_playwright(self, query: str, max_resultados: int) -> list[Producto]:
        """Abre el SPA con Playwright e intercepta las requests XHR para capturar datos de productos."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return []

        url = self.SEARCH_URL.format(query=quote(query))
        capturado: list[Producto] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.DEFAULT_HEADERS["User-Agent"],
                extra_http_headers={"Accept-Language": self.DEFAULT_HEADERS["Accept-Language"]},
            )
            page = await context.new_page()

            async def on_response(response):
                if capturado:
                    return
                resp_url = response.url
                if not any(kw in resp_url.lower() for kw in self.PRODUCT_URL_KEYWORDS):
                    return
                try:
                    content_type = response.headers.get("content-type", "")
                    if "json" not in content_type:
                        return
                    data = await response.json()
                    productos = self._intentar_parsear_respuesta(data, max_resultados)
                    if productos:
                        print(f"[La Anónima] XHR con productos encontrado: {resp_url}")
                        capturado.extend(productos)
                except Exception:
                    pass

            page.on("response", on_response)
            await page.goto(url, timeout=35000, wait_until="networkidle")
            await browser.close()

        return capturado

    def buscar(self, query: str, max_resultados: int = 6) -> list[Producto]:
        self._esperar()
        try:
            if sys.platform == "win32":
                loop = asyncio.ProactorEventLoop()
                productos = loop.run_until_complete(
                    self._scrape_con_playwright(query, max_resultados)
                )
                loop.close()
            else:
                productos = asyncio.run(self._scrape_con_playwright(query, max_resultados))

            if productos:
                return productos
        except Exception as e:
            print(f"[La Anónima] Error con Playwright: {e}")

        return []
