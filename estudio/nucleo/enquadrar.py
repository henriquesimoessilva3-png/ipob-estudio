"""Descobre, para cada trecho, onde recortar o quadro do Short.

Recorte fixo não funciona, por dois motivos que só apareceram no uso:

1. A transmissão nem sempre tem o mesmo layout. Às vezes a câmera ocupa o
   quadro inteiro; às vezes a igreja monta um quadro com fundo liso e coloca a
   câmera num painel menor, com o versículo projetado ao lado.
2. O pregador anda. Num trecho de 50 segundos ele pode cruzar dois terços da
   largura do quadro.

Então o enquadramento é medido no próprio trecho: amostram-se quadros ao longo
dele, vê-se onde está a imagem (nitidez, para achar o painel) e onde houve
movimento (variação no tempo, que é o pregador). O recorte é a área que contém
todo o movimento dele, com uma folga.
"""
from __future__ import annotations

from pathlib import Path

AMOSTRAS = 20              # quadros analisados por trecho
FOLGA = 0.05               # sobra em volta do movimento, em fração da largura
LARGURA_MINIMA = 0.30      # não adianta apertar mais que isso
MOVIMENTO_MINIMO = 0.22    # abaixo disso o "movimento" é ruído de compressão
VARIACAO_MAXIMA = 0.06     # o quanto o layout pode oscilar e ainda valer o corte


def _pilha(fonte: Path, inicio: float, duracao: float):
    """Amostra quadros do trecho e devolve como um array (n, altura, largura)."""
    import tempfile

    import numpy as np
    from PIL import Image

    from .base import rodar

    with tempfile.TemporaryDirectory() as d:
        taxa = max(0.05, AMOSTRAS / max(1.0, duracao))
        rodar(["ffmpeg", "-v", "error", "-ss", f"{inicio:.2f}", "-t", f"{duracao:.2f}",
               "-i", str(fonte), "-vf", f"fps={taxa:.4f},scale=480:-1",
               str(Path(d) / "q%03d.png")])
        arqs = sorted(Path(d).glob("q*.png"))
        if len(arqs) < 4:
            return None
        return np.stack([np.array(Image.open(a).convert("L"), dtype=np.float32)
                         for a in arqs])


def enquadrar(fonte: Path, inicio: float, fim: float) -> dict | None:
    """Devolve {x, y, largura, altura} em fração do quadro, ou None se falhar."""
    import numpy as np

    pilha = _pilha(fonte, inicio, max(1.0, fim - inicio))
    if pilha is None:
        return None
    _, h, w = pilha.shape

    # 0. o layout é estável durante o trecho?
    #
    # A mesa de transmissão da igreja alterna entre câmera cheia e um quadro
    # com a câmera num painel menor ao lado do versículo projetado. Quando essa
    # troca acontece DENTRO do trecho, nenhum recorte fixo serve: o que
    # enquadra o pregador num layout o decapita no outro. Nesse caso é melhor
    # não recortar nada do que recortar errado.
    bordas = []
    for q in pilha:
        d = np.abs(np.diff(q, axis=1)).mean(axis=1)
        marcas = np.where(d > d.max() * 0.12)[0]
        if len(marcas):
            bordas.append((marcas.min() / h, (marcas.max() + 1) / h))
    if len(bordas) >= 4:
        topos = np.array([b[0] for b in bordas])
        bases = np.array([b[1] for b in bordas])
        if topos.std() > VARIACAO_MAXIMA or bases.std() > VARIACAO_MAXIMA:
            return {"instavel": True}

    medio = pilha.mean(axis=0)

    # 1. onde está a imagem: o fundo liso do quadro não tem detalhe
    det_lin = np.abs(np.diff(medio, axis=1)).mean(axis=1)
    det_col = np.abs(np.diff(medio, axis=0)).mean(axis=0)
    ys = np.where(det_lin > det_lin.max() * 0.12)[0]
    xs_util = np.where(det_col > det_col.max() * 0.12)[0]
    if len(ys) < h * 0.1 or len(xs_util) < w * 0.1:
        return None
    y0, y1 = ys.min() / h, (ys.max() + 1) / h
    xu0, xu1 = xs_util.min() / w, (xs_util.max() + 1) / w

    # 2. onde o pregador andou: variação ao longo do tempo
    mov = pilha.std(axis=0)[ys.min(): ys.max() + 1].mean(axis=0)
    if mov.max() <= 0:
        return None
    ativos = np.where(mov > mov.max() * MOVIMENTO_MINIMO)[0]
    if len(ativos) == 0:
        return None

    x0 = max(xu0, ativos.min() / w - FOLGA)
    x1 = min(xu1, (ativos.max() + 1) / w + FOLGA)

    # onde ele mais esteve, e não o meio do retângulo: o corte 9:16 se ancora
    # aqui. Sem isso, num instante em que ele está na ponta da área medida, o
    # corte centrado o joga contra a borda.
    centro = float((mov * np.arange(len(mov))).sum() / mov.sum()) / w

    # nunca menor que o mínimo, e sempre dentro da parte útil
    if x1 - x0 < LARGURA_MINIMA:
        centro = (x0 + x1) / 2
        x0 = max(xu0, centro - LARGURA_MINIMA / 2)
        x1 = min(xu1, x0 + LARGURA_MINIMA)
        x0 = max(xu0, x1 - LARGURA_MINIMA)

    return {"instavel": False, "x": round(x0, 4), "y": round(y0, 4),
            "largura": round(x1 - x0, 4), "altura": round(y1 - y0, 4),
            "centro": round(min(max(centro, x0), x1), 4)}
