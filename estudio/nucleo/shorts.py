"""Corta trechos verticais (9:16) da pregação, para Shorts.

A escolha dos trechos é sua — as ferramentas de "detecção de viralidade" são
treinadas majoritariamente em inglês e escolhem mal em português. O que o
Estúdio faz é o trabalho mecânico: reenquadrar, pôr a tarja e queimar a fala na
tela (Short se assiste sem som, então legenda ali não é enfeite).

Dois modos de reenquadramento:

  pregador-cheio  recorta o painel da câmera e amplia até encher a tela. É o
                  que parece um Short de verdade, e é o padrão.
  pregador        o painel inteiro no meio, com fundo borrado. Use quando o
                  pregador sair do enquadramento e o corte cheio o cortar.
  completo        o quadro inteiro da transmissão. Só faz sentido quando o que
                  está no telão importa mais que quem fala.

A live da igreja não sai em tela cheia: ela monta um quadro com fundo liso e
põe dentro o painel da câmera e, muitas vezes, um segundo painel com o
versículo projetado. Por isso o corte cego não funciona — o retângulo do painel
está medido em `padroes.recorte_do_short`, no config.json.

Sobre a legenda: o ffmpeg desta máquina foi compilado sem libass, então o
filtro `subtitles` não existe. Em vez de trocar o ffmpeg do sistema, cada fala
vira um PNG (desenhado pelo mesmo Chrome que faz as capas) e entra como
sobreposição, aparecendo só na sua faixa de tempo.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import rodar
from .render import ALVO_LUFS, PICO_MAXIMO, cadeia_de_audio, medir_loudness

LARGURA, ALTURA = 1080, 1920

# No modo "medio": quanto da largura do quadro original fica, e em volta de que
# ponto. Nesta igreja o pregador está por volta de 45% e o telão vai até 95%,
# então guarda-se 66% da largura centrado em 63% — cabem os dois.
MEDIO_LARGURA = 0.66
MEDIO_CENTRO = 0.63

# No modo "pregador": quando a transmissão está em tela dividida, que fração da
# faixa útil é o painel da câmera. O versículo projetado à direita não faz falta
# no Short — a legenda queimada já traz o que está sendo dito.
FRACAO_DO_PREGADOR = 0.56
LIMITE_SHORT = 180.0          # o YouTube aceita Shorts de até 3 minutos
Y_LEGENDA = 1330              # logo acima da barra de baixo da tarja
Y_LEGENDA_LIMPO = 1480        # sem barras, a fala desce e sobra mais imagem

_TEMPO = re.compile(r"out_time_ms=(\d+)")


class ErroShort(RuntimeError):
    pass


def detectar_painel(fonte: Path, tempo: float) -> dict | None:
    """Descobre onde está a imagem útil dentro do quadro da transmissão.

    A live da igreja não sai em tela cheia: ela monta um quadro com fundo liso
    e coloca dentro dele o painel da câmera e, muitas vezes, um segundo painel
    com o versículo projetado. Recortar sem saber disso desperdiça a tela do
    Short — no modo completo o conteúdo real fica com 18% da altura.

    A detecção é por NITIDEZ, não por cor: o fundo do quadro é liso e os
    painéis têm detalhe. Assim funciona com qualquer cor de fundo que a igreja
    venha a usar.
    """
    import tempfile

    from PIL import Image

    with tempfile.TemporaryDirectory() as d:
        quadro = Path(d) / "q.png"
        rodar(["ffmpeg", "-v", "error", "-ss", f"{tempo:.2f}", "-i", str(fonte),
               "-frames:v", "1", "-y", str(quadro)])
        if not quadro.exists():
            return None
        im = Image.open(quadro).convert("L")
        larg, alt = im.size
        peq = im.resize((larg // 4, alt // 4))
        w, h = peq.size
        px = peq.load()

    def detalhe_linha(y):
        return sum(abs(px[x, y] - px[x + 1, y]) for x in range(0, w - 1, 2)) / (w / 2)

    def detalhe_coluna(x):
        return sum(abs(px[x, y] - px[x, y + 1]) for y in range(0, h - 1, 2)) / (h / 2)

    linhas = [detalhe_linha(y) for y in range(h)]
    colunas = [detalhe_coluna(x) for x in range(w)]
    corte_l = max(linhas) * 0.18
    corte_c = max(colunas) * 0.18

    ys = [y for y, v in enumerate(linhas) if v > corte_l]
    xs = [x for x, v in enumerate(colunas) if v > corte_c]
    if not ys or not xs:
        return None

    y0, y1 = min(ys) / h, (max(ys) + 1) / h
    x0, x1 = min(xs) / w, (max(xs) + 1) / w
    if (x1 - x0) < 0.25 or (y1 - y0) < 0.15:
        return None

    # dois painéis? procura uma faixa lisa no meio da parte útil
    vazias = [x for x in range(int(x0 * w) + 3, int(x1 * w) - 3)
              if colunas[x] < corte_c * 0.45]
    divisao = None
    if len(vazias) >= 2 and (max(vazias) - min(vazias)) < w * 0.12:
        divisao = (min(vazias) + max(vazias)) / 2 / w

    return {"x0": x0, "x1": x1, "y0": y0, "y1": y1, "divisao": divisao}


def montar(fonte: Path, destino: Path, inicio: float, fim: float,
           tarja: Path | None = None,
           falas: list[dict] | None = None,
           modo: str = "completo",
           fade: float = 0.4,
           y_legenda: int = Y_LEGENDA,
           bitrate: str = "8M",
           normalizar_audio: bool = True,
           recorte: dict | None = None,
           limpar_audio: bool = True,
           progresso=None) -> Path:
    """Renderiza um trecho vertical e devolve o caminho do MP4.

    `falas` vem de artes.gerar_legendas(): [{'a', 'b', 'png'}, …], com os
    tempos contados a partir do começo do trecho.
    """
    duracao = max(1.0, fim - inicio)
    destino.parent.mkdir(parents=True, exist_ok=True)
    falas = [f for f in (falas or []) if f.get("png") and Path(f["png"]).exists()]
    if not (tarja and tarja.exists()) and y_legenda == Y_LEGENDA:
        y_legenda = Y_LEGENDA_LIMPO

    # Short se assiste no celular, muitas vezes na rua. O áudio da transmissão
    # chega por volta de -34 LUFS: sem corrigir, ninguém ouve.
    limpar = normalizar_audio and limpar_audio
    medida = medir_loudness(fonte, inicio, duracao, limpar) if normalizar_audio else None
    corrigir = ""
    if medida:
        corrigir = (
            f",{cadeia_de_audio(limpar)}loudnorm=I={ALVO_LUFS}:TP={PICO_MAXIMO}:LRA=11:linear=true"
            f":measured_I={medida['input_i']}:measured_TP={medida['input_tp']}"
            f":measured_LRA={medida['input_lra']}"
            f":measured_thresh={medida['input_thresh']}"
            f":offset={medida['target_offset']}"
        )

    entradas = ["-ss", f"{inicio:.3f}", "-t", f"{duracao:.3f}", "-i", str(fonte)]
    indice = 1

    i_tarja = None
    if tarja and tarja.exists():
        entradas += ["-i", str(tarja)]
        i_tarja = indice
        indice += 1

    for f in falas:
        entradas += ["-i", str(f["png"])]
        f["_i"] = indice
        indice += 1

    if modo == "perto":
        # recorta a faixa central do quadro e amplia até encher a tela
        filtro = (f"[0:v]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
                  f"scale={LARGURA}:{ALTURA},setsar=1[base];")
    elif modo in ("pregador", "pregador-cheio"):
        # A live não sai em tela cheia: monta um quadro com fundo liso e põe
        # dentro o painel da câmera (e às vezes o versículo à direita). Aqui
        # recortamos só esse painel. O versículo não faz falta — a legenda
        # queimada já traz o que está sendo dito.
        # o recorte é medido no próprio trecho: o layout da transmissão muda
        # ao longo do culto e o pregador anda. Se o layout mudar DENTRO do
        # trecho, não há recorte que sirva — cai no quadro inteiro.
        from .enquadrar import enquadrar as medir

        r = recorte
        if not r:
            r = medir(fonte, inicio, fim)
        if not r or r.get("instavel"):
            modo = "completo"
            r = None
        else:
            r = {k: r[k] for k in ("x", "y", "largura", "altura", "centro")
                 if k in r}

    if modo in ("pregador", "pregador-cheio") and r:
        corte = (f"[0:v]crop=iw*{r['largura']:.4f}:ih*{r['altura']:.4f}"
                 f":iw*{r['x']:.4f}:ih*{r['y']:.4f}[util];")
        if modo == "pregador-cheio":
            # amplia até encher a tela, ancorando o corte onde o pregador mais
            # esteve — centrar no meio do retângulo o jogava contra a borda
            c = r.get("centro")
            onde = ((c - r["x"]) / r["largura"]) if c is not None else 0.5
            onde = min(max(onde, 0.0), 1.0)
            filtro = (corte +
                      f"[util]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
                      f"crop={LARGURA}:{ALTURA}"
                      f":'clip(iw*{onde:.4f}-{LARGURA // 2},0,iw-{LARGURA})':0,"
                      f"setsar=1[base];")
        else:
            filtro = (
                corte +
                f"[util]split=2[fundo][frente];"
                f"[fundo]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
                f"crop={LARGURA}:{ALTURA},boxblur=32:2,eq=brightness=-0.16:saturation=0.7[borrado];"
                f"[frente]scale={LARGURA}:-2[centro];"
                f"[borrado][centro]overlay=(W-w)/2:(H-h)/2,setsar=1[base];"
            )
    elif modo == "medio":
        # corta as laterais que não interessam e amplia o que sobrou; o resto
        # da tela continua com a cópia borrada, como no completo
        x = max(0.0, MEDIO_CENTRO - MEDIO_LARGURA / 2)
        filtro = (
            f"[0:v]split=2[fundo][frente];"
            f"[fundo]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
            f"crop={LARGURA}:{ALTURA},boxblur=32:2,eq=brightness=-0.14:saturation=0.7[borrado];"
            f"[frente]crop=iw*{MEDIO_LARGURA:.4f}:ih:iw*{x:.4f}:0,"
            f"scale={LARGURA}:-2[centro];"
            f"[borrado][centro]overlay=(W-w)/2:(H-h)/2,setsar=1[base];"
        )
    else:
        # o quadro inteiro no meio, com ele mesmo borrado atrás
        filtro = (
            f"[0:v]split=2[fundo][frente];"
            f"[fundo]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
            f"crop={LARGURA}:{ALTURA},boxblur=32:2,eq=brightness=-0.14:saturation=0.7[borrado];"
            f"[frente]scale={LARGURA}:-2[centro];"
            f"[borrado][centro]overlay=(W-w)/2:(H-h)/2,setsar=1[base];"
        )

    corrente = "base"
    if i_tarja is not None:
        filtro += f"[{i_tarja}:v]scale={LARGURA}:{ALTURA}[tar];[{corrente}][tar]overlay=0:0[comtarja];"
        corrente = "comtarja"

    # cada fala aparece só entre os seus tempos
    for n, f in enumerate(falas):
        proximo = f"leg{n}"
        filtro += (f"[{corrente}][{f['_i']}:v]"
                   f"overlay=0:{y_legenda}:enable='between(t,{f['a']:.2f},{f['b']:.2f})'"
                   f"[{proximo}];")
        corrente = proximo

    saida_fade = max(0.0, duracao - fade)
    filtro += (f"[{corrente}]fade=t=in:st=0:d={fade},"
               f"fade=t=out:st={saida_fade:.2f}:d={fade},format=yuv420p[v];"
               f"[0:a]aresample=48000{corrigir},aresample=48000,"
               f"afade=t=in:st=0:d={fade},"
               f"afade=t=out:st={saida_fade:.2f}:d={fade}[a]")

    tem_hw = "videotoolbox" in (rodar(["ffmpeg", "-hide_banner", "-encoders"]).stdout or "")
    video = (["-c:v", "h264_videotoolbox", "-b:v", bitrate, "-profile:v", "high"]
             if tem_hw else ["-c:v", "libx264", "-crf", "20", "-preset", "medium"])

    cmd = ["ffmpeg", "-y", "-hide_banner", "-nostats", *entradas,
           "-filter_complex", filtro, "-map", "[v]", "-map", "[a]", *video,
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", "-progress", "pipe:1", str(destino)]

    def ao_vivo(linha: str):
        if progresso is None:
            return
        m = _TEMPO.search(linha)
        if m:
            progresso(min(0.999, (int(m.group(1)) / 1_000_000) / duracao))

    r = rodar(cmd, ao_vivo=ao_vivo)
    if r.returncode != 0 or not destino.exists():
        raise ErroShort("O ffmpeg falhou no Short.\n" +
                        "\n".join(r.stdout.splitlines()[-20:]))
    if progresso:
        progresso(1.0)
    return destino
