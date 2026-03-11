from urllib.parse import quote
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper, Producto


class CotoScraper(BaseScraper):
    BASE_URL = "https://www.cotodigital3.com.ar"
    SEARCH_URL = "https://www.cotodigital3.com.ar/sitios/cdigi/browse?Ntt={query}"

    def buscar(self, query: str, max_resultados: int = 6) -> list[Producto]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[Coto] Playwright no está instalado.")
            return []

        url = self.SEARCH_URL.format(query=quote(query))
        html = ""

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=self.DEFAULT_HEADERS["User-Agent"],
                    extra_http_headers={
                        "Accept-Language": self.DEFAULT_HEADERS["Accept-Language"],
                    },
                )
                page = context.new_page()
                page.goto(url, timeout=30000)
                try:
                    page.wait_for_selector(".product-grid-container", timeout=15000)
                except Exception:
                    pass
                html = page.content()
                browser.close()
        except Exception as e:
            print(f"[Coto] Error con Playwright: {e}")
            return []

        soup = BeautifulSoup(html, "lxml")
        productos = []

        product_items = soup.select(".product-grid-container .product-item") or \
                        soup.select("[class*='product']")

        # Try different selectors
        cards = (
            soup.select(".products-grid .item") or
            soup.select(".product-grid-container li") or
            soup.select("[class*='product-item']")
        )

        for card in cards[:max_resultados]:
            try:
                nombre_el = card.select_one(".description a") or card.select_one("a.product-name")
                precio_el = card.select_one(".atg_store_newPrice") or card.select_one("[class*='price']")
                link_el = card.select_one("a[href*='/product']") or card.select_one("a[href]")

                if not nombre_el or not precio_el:
                    continue

                nombre = nombre_el.get_text(strip=True)
                precio_texto = precio_el.get_text(strip=True)
                precio = self._parsear_precio(precio_texto)

                if not precio or precio == 0:
                    continue

                link = ""
                if link_el:
                    href = link_el.get("href", "")
                    link = href if href.startswith("http") else self.BASE_URL + href

                imagen_el = card.select_one("img")
                imagen_url = ""
                if imagen_el:
                    imagen_url = imagen_el.get("src") or imagen_el.get("data-src", "")

                productos.append(Producto(
                    nombre=nombre,
                    precio=precio,
                    precio_str=f"${precio:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    supermercado="Coto",
                    url=link,
                    imagen_url=imagen_url,
                ))
            except Exception as e:
                print(f"[Coto] Error parseando producto: {e}")
                continue

        return productos[:max_resultados]
