import asyncio
import sys
import requests
from urllib.parse import quote
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper, Producto


class CotoScraper(BaseScraper):
    BASE_URL = "https://www.cotodigital3.com.ar"
    SEARCH_URL = "https://www.cotodigital3.com.ar/sitios/cdigi/browse?Ntt={query}&view=grid&Nrpp=12"

    def _parsear_cards(self, soup: BeautifulSoup, max_resultados: int) -> list[Producto]:
        productos = []

        cards = (
            soup.select("#products li") or
            soup.select(".grilla li") or
            soup.select(".product-grid-container li") or
            soup.select(".products-grid .item") or
            soup.select("li[class*='product']") or
            soup.select("[class*='grilla'] li")
        )

        for card in cards[:max_resultados]:
            try:
                nombre_el = (
                    card.select_one(".descrip_full") or
                    card.select_one("[class*='descrip']") or
                    card.select_one("h3 a") or
                    card.select_one(".product-name a") or
                    card.select_one(".description a") or
                    card.select_one("a[title]")
                )
                precio_el = (
                    card.select_one(".atg_store_newPrice") or
                    card.select_one(".atg_store_productPrice") or
                    card.select_one("[class*='price']") or
                    card.select_one("[class*='Price']")
                )
                link_el = card.select_one("a[href]")

                if not nombre_el or not precio_el:
                    continue

                nombre = nombre_el.get("title") or nombre_el.get_text(strip=True)
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

    async def _scrape_con_playwright(self, url: str) -> str:
        """Carga la página con Playwright asíncrono y devuelve el HTML."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ""

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.DEFAULT_HEADERS["User-Agent"],
                extra_http_headers={"Accept-Language": self.DEFAULT_HEADERS["Accept-Language"]},
            )
            page = await context.new_page()
            await page.goto(url, timeout=30000)

            for selector in ["#products li", ".grilla li", ".product-grid-container", "[class*='grilla']"]:
                try:
                    await page.wait_for_selector(selector, timeout=8000)
                    break
                except Exception:
                    continue

            html = await page.content()
            await browser.close()
            return html

    def buscar(self, query: str, max_resultados: int = 6) -> list[Producto]:
        url = self.SEARCH_URL.format(query=quote(query))

        # Intento 1: requests directo (ATG renderiza HTML server-side)
        try:
            self._esperar()
            response = requests.get(url, headers=self.DEFAULT_HEADERS, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "lxml")
                productos = self._parsear_cards(soup, max_resultados)
                if productos:
                    return productos
                print("[Coto] requests: sin productos en HTML, probando Playwright...")
        except Exception as e:
            print(f"[Coto] Error con requests: {e}")

        # Intento 2: async Playwright (asyncio.run crea su propio event loop, funciona en threads)
        try:
            html = asyncio.run(self._scrape_con_playwright(url))
            if html:
                soup = BeautifulSoup(html, "lxml")
                return self._parsear_cards(soup, max_resultados)
        except Exception as e:
            print(f"[Coto] Error con Playwright: {e}")

        return []
