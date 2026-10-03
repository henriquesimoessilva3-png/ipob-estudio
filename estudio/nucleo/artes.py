"""Gera capa e tarja em PNG a partir da página artes/arte.html.

A mesma página que o painel mostra na prévia é fotografada por um Chrome
invisível. Por isso a prévia é fiel: é literalmente o mesmo HTML e o mesmo CSS.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode


def url_da_arte(porta: int, **campos) -> str:
    """Monta o endereço da arte. Campos vazios são omitidos."""
    limpos = {k: v for k, v in campos.items() if v not in (None, "", [])}
    if isinstance(limpos.get("pregadores"), (list, tuple)):
        limpos["pregadores"] = ",".join(limpos["pregadores"])
    return f"http://127.0.0.1:{porta}/artes/arte.html?" + urlencode(limpos)


def fotografar(pedidos: list[tuple[str, Path, bool]],
               largura: int = 1920, altura: int = 1080) -> None:
    """Fotografa várias artes de uma vez.

    `pedidos` é uma lista de (url, destino, transparente). Abrir o navegador
    uma única vez para as duas artes economiza uns 3 segundos por vídeo.
    """
    from playwright.sync_api import sync_playwright

    for _, destino, _ in pedidos:
        destino.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # channel="chrome" usa o Google Chrome já instalado, sem baixar nada;
        # sem Chrome, cai no Chromium que o instalador baixou pelo Playwright.
        args = ["--force-device-scale-factor=1"]
        try:
            navegador = p.chromium.launch(channel="chrome", args=args)
        except Exception:
            navegador = p.chromium.launch(args=args)
        pagina = navegador.new_page(viewport={"width": largura, "height": altura})
        try:
            for url, destino, transparente in pedidos:
                pagina.goto(url, wait_until="load")
                # a página avisa quando fontes e imagens terminaram de carregar
                pagina.wait_for_selector("html[data-pronto]", timeout=20000)
                pagina.screenshot(path=str(destino), omit_background=transparente)
        finally:
            navegador.close()

    faltando = [str(d) for _, d, _ in pedidos if not d.exists()]
    if faltando:
        raise RuntimeError("O Chrome não gerou: " + ", ".join(faltando))


def gerar_capa(porta: int, destino: Path, **campos) -> Path:
    fotografar([(url_da_arte(porta, tipo="capa", **campos), destino, False)])
    return destino


def gerar_tarja(porta: int, destino: Path, **campos) -> Path:
    fotografar([(url_da_arte(porta, tipo="tarja", **campos), destino, True)])
    return destino


def gerar_tarja_vertical(porta: int, destino: Path, **campos) -> Path:
    """A tarja dos Shorts: 1080x1920 em vez de 1920x1080."""
    fotografar(
        [(url_da_arte(porta, tipo="tarja", vertical="1", **campos), destino, True)],
        largura=1080, altura=1920,
    )
    return destino


def gerar_as_duas(porta: int, capa: Path, tarja: Path, **campos) -> tuple[Path, Path]:
    """Capa e tarja numa abertura só do navegador."""
    fotografar([
        (url_da_arte(porta, tipo="capa", **campos), capa, False),
        (url_da_arte(porta, tipo="tarja", **campos), tarja, True),
    ])
    return capa, tarja


def capa_para_miniatura(capa_png: Path, destino_jpg: Path) -> Path:
    """O YouTube quer a miniatura em JPG e abaixo de 2 MB."""
    from PIL import Image

    im = Image.open(capa_png).convert("RGB")
    qualidade = 92
    while True:
        im.save(destino_jpg, "JPEG", quality=qualidade, optimize=True)
        if destino_jpg.stat().st_size < 2_000_000 or qualidade <= 60:
            break
        qualidade -= 8
    return destino_jpg


def gerar_legendas(porta: int, falas: list[dict], pasta: Path,
                   largura: int = 1080, altura: int = 300) -> list[dict]:
    """Uma imagem por fala, para queimar no Short.

    Devolve as falas com o campo 'png' apontando para o arquivo. Tudo numa
    abertura só do navegador — 20 falas levam uns 3 segundos.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    pedidos, saida = [], []
    for i, f in enumerate(falas):
        destino = pasta / f"fala-{i:03d}.png"
        pedidos.append(
            (url_da_arte(porta, tipo="legenda", texto=f["texto"]), destino, True)
        )
        saida.append({**f, "png": destino})
    if pedidos:
        fotografar(pedidos, largura=largura, altura=altura)
    return saida
