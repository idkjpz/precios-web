from rich.console import Console
from rich.table import Table
from rich import box
from scrapers.base_scraper import Producto

console = Console()


def mostrar_resultados(productos: list[Producto], query: str) -> None:
    if not productos:
        console.print(f"[red]No se encontraron resultados para '{query}'[/red]")
        return

    table = Table(
        title=f"Resultados para: [bold yellow]{query}[/bold yellow]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )

    table.add_column("#", style="dim", width=4)
    table.add_column("Supermercado", style="cyan", width=14)
    table.add_column("Producto", style="white", width=50)
    table.add_column("Precio", style="bold green", justify="right", width=14)
    table.add_column("Dif. %", justify="right", width=8)

    if not productos:
        return

    precio_min = min(p.precio for p in productos)

    for i, p in enumerate(productos, 1):
        diff = ((p.precio - precio_min) / precio_min * 100) if precio_min > 0 else 0
        diff_str = f"+{diff:.1f}%" if diff > 0 else "[bold green]MIN[/bold green]"
        precio_style = "bold red" if i == len(productos) else ("bold green" if diff == 0 else "yellow")

        table.add_row(
            str(i),
            p.supermercado,
            p.nombre[:48],
            f"[{precio_style}]{p.precio_str}[/{precio_style}]",
            diff_str,
        )

    console.print(table)

    precio_max = max(p.precio for p in productos)
    ahorro = precio_max - precio_min
    pct = (ahorro / precio_max * 100) if precio_max > 0 else 0
    ahorro_str = f"${ahorro:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    console.print(
        f"\n[bold]Podés ahorrar hasta [green]{ahorro_str}[/green] "
        f"([yellow]{pct:.1f}%[/yellow]) eligiendo el más barato.[/bold]"
    )
