"""Conversa com o YouTube: informações da live, transcrição e download."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from .base import TRABALHO, rodar, para_segundos

# O YouTube exige duas coisas para liberar os formatos de vídeo:
#
#  1. Cookies de uma sessão logada — usamos os do Chrome, o mesmo navegador
#     que você já usa. Nada sai da máquina.
#  2. Um motor JavaScript, para resolver o desafio que o YouTube aplica desde
#     2025. Sem isso o yt-dlp só enxerga imagens e falha com "Requested format
#     is not available". O Deno é o padrão; o Node também serve.
COOKIES = ["--cookies-from-browser", "chrome"]


def _motor_js() -> list[str]:
    from .base import ferramenta
    for nome in ("deno", "node", "bun"):
        if ferramenta(nome):
            return [] if nome == "deno" else ["--js-runtimes", nome]
    return []


MOTOR = _motor_js()


class ErroYouTube(RuntimeError):
    pass


def _explicar(saida: str) -> str:
    s = saida.lower()
    if "sign in to confirm" in s or "not a bot" in s:
        return ("O YouTube pediu confirmação de que não é robô. Abra o Chrome, "
                "entre na sua conta do YouTube e tente de novo — o Estúdio usa "
                "os cookies do Chrome automaticamente.")
    if "http error 429" in s or "too many requests" in s:
        return ("O YouTube limitou os acessos por excesso de pedidos. "
                "Espere alguns minutos e tente de novo.")
    if "video unavailable" in s or "private video" in s:
        return "Vídeo indisponível ou privado. Confira o link."
    if "is not a valid url" in s:
        return "Esse link não parece um endereço do YouTube."
    if "requested format is not available" in s or "challenge solving failed" in s:
        return ("O YouTube bloqueou os formatos de vídeo. Isso acontece quando o "
                "yt-dlp está velho ou falta um motor JavaScript na máquina. "
                "Rode no Terminal:  pip3 install -U yt-dlp yt-dlp-ejs  "
                "(e instale o Node ou o Deno, se não tiver).")
    return saida.strip()[-700:] or "Falha ao falar com o YouTube."


def _yt(args: list[str], ao_vivo=None):
    # Sem o executável no PATH (comum no Windows), chama o módulo pelo Python.
    base = ["yt-dlp"] if shutil.which("yt-dlp") else [sys.executable, "-m", "yt_dlp"]
    r = rodar([*base, "--no-update", *MOTOR, *COOKIES, *args], ao_vivo=ao_vivo)
    if r.returncode != 0:
        raise ErroYouTube(_explicar((r.stdout or "") + (r.stderr or "")))
    return r


# --------------------------------------------------------------- informações
def informacoes(url: str) -> dict:
    r = _yt(["--skip-download", "--dump-single-json", "--no-playlist", url])
    d = json.loads(r.stdout)
    return {
        "id": d.get("id", ""),
        "titulo": d.get("title", ""),
        "duracao": float(d.get("duration") or 0),
        "data": d.get("upload_date", ""),
        "miniatura": d.get("thumbnail", ""),
    }


# -------------------------------------------------------------- transcrição
# A transcrição feita aqui pelo Whisper fica gravada ao lado do vídeo. Antes
# ela só existia na memória do painel: reiniciar o Mac a apagava, e "abrir
# produção" ia buscar a do YouTube — que era justamente a que não existia.
TRANSCRICAO_LOCAL = "transcricao-local.json"


def gravar_transcricao_local(video_id: str, blocos: list[dict]) -> Path:
    destino = TRABALHO / video_id
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / TRANSCRICAO_LOCAL
    arquivo.write_text(json.dumps(blocos, ensure_ascii=False), encoding="utf-8")
    return arquivo


def transcricao_local(video_id: str) -> list[dict]:
    arquivo = TRABALHO / video_id / TRANSCRICAO_LOCAL
    if not arquivo.exists():
        return []
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []


def baixar_transcricao(url: str, video_id: str) -> list[dict]:
    """Baixa a legenda automática em português e devolve blocos com tempo.

    Ordem: a legenda do YouTube já baixada, a do Whisper já feita aqui, e só
    então um pedido novo ao YouTube.
    """
    destino = TRABALHO / video_id
    destino.mkdir(parents=True, exist_ok=True)

    existente = _vtts(destino)
    if not existente:
        locais = transcricao_local(video_id)
        if locais:
            return locais
    if not existente:
        _yt([
            "--skip-download",
            "--write-auto-subs", "--write-subs",
            "--sub-langs", "pt.*,pt-BR,pt-orig",
            "--sub-format", "vtt",
            "--no-playlist",
            "-o", str(destino / "legenda.%(ext)s"),
            url,
        ])
        existente = _vtts(destino)

    if not existente:
        raise ErroYouTube(
            "Essa transmissão não tem transcrição automática em português. "
            "Informe o minuto de início manualmente."
        )
    return ler_vtt(existente[0])


def _vtts(pasta: Path) -> list[Path]:
    """As legendas da pasta, a ORIGINAL primeiro.

    O YouTube entrega três: pt-orig (o que foi falado), pt e pt-PT (traduções
    automáticas, com "está a dizer" e palavras trocadas). Em ordem alfabética
    a pt-PT vinha primeiro, e a busca do corte rodava sobre a tradução — foi
    assim que "deixam as suas Bíblias abertas" virou outra coisa. Descoberto
    em 01/10/2026.
    """
    ordem = {"pt-orig": 0, "pt": 1, "pt-BR": 2}
    def chave(p: Path):
        partes = p.name.split(".")
        lingua = partes[-2] if len(partes) > 2 else ""
        return (ordem.get(lingua, 9), p.name)
    return sorted(pasta.glob("*.vtt"), key=chave)


_TEMPO = re.compile(
    r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})"
)
_TAGS = re.compile(r"<[^>]+>")


def ler_vtt(caminho: Path) -> list[dict]:
    """Converte o .vtt em [{'inicio': 12.3, 'fim': 15.0, 'texto': '...'}].

    A legenda automática do YouTube repete as frases em cascata (cada bloco
    reescreve o anterior). Aqui isso é desfeito, sobrando o texto corrido.
    """
    blocos: list[dict] = []
    inicio = fim = None
    buffer: list[str] = []

    def fechar():
        nonlocal inicio, fim, buffer
        if inicio is not None and buffer:
            texto = " ".join(buffer).strip()
            if texto:
                blocos.append({"inicio": inicio, "fim": fim, "texto": texto})
        buffer = []

    for linha in caminho.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = _TEMPO.search(linha)
        if m:
            fechar()
            inicio = para_segundos(m.group(1).replace(",", "."))
            fim = para_segundos(m.group(2).replace(",", "."))
            continue
        if not linha.strip() or linha.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        limpa = _TAGS.sub("", linha).strip()
        if limpa:
            buffer.append(limpa)
    fechar()

    return _desempilhar(blocos)


def _desempilhar(blocos: list[dict]) -> list[dict]:
    """Desfaz a repetição em cascata da legenda automática do YouTube.

    O YouTube mostra a legenda rolando: cada bloco repete o fim do anterior e
    acrescenta algumas palavras. Sem tratar isso, o texto sai com tudo dobrado.
    A ideia aqui é comparar palavra a palavra: do bloco novo, guarda-se só o
    pedaço que ainda não foi dito.
    """
    limpos: list[dict] = []
    cauda: list[str] = []          # as últimas palavras já aproveitadas

    for b in blocos:
        palavras = b["texto"].split()
        if not palavras:
            continue

        # maior sobreposição entre o fim do que já saiu e o começo deste bloco
        maximo = min(len(cauda), len(palavras))
        salto = 0
        for n in range(maximo, 0, -1):
            if cauda[-n:] == palavras[:n]:
                salto = n
                break

        novas = palavras[salto:]
        if not novas:
            continue

        limpos.append({**b, "texto": " ".join(novas)})
        cauda = (cauda + novas)[-24:]

    return limpos


# ------------------------------------------------------------------ download
def video_baixado(video_id: str) -> Path | None:
    """O vídeo final já juntado, e só ele.

    O yt-dlp baixa imagem e som separados (video.f137.mp4, video.f140.m4a) e
    depois junta em video.mp4. Se o download for interrompido na junção, os
    pedaços ficam na pasta — e o pedaço de imagem também termina em .mp4.
    Aceitá-lo era reaproveitar um vídeo mudo. Por isso o nome tem de ser
    exatamente "video".
    """
    for p in sorted((TRABALHO / video_id).glob("video.*")):
        if p.stem == "video" and p.suffix in (".mp4", ".mkv", ".webm"):
            return p
    return None


def baixar_video(url: str, video_id: str, qualidade: str = "1080",
                 ao_vivo=None) -> Path:
    """Baixa a transmissão inteira uma vez e guarda para reaproveitar."""
    destino = TRABALHO / video_id
    destino.mkdir(parents=True, exist_ok=True)

    ja = video_baixado(video_id)
    if ja:
        return ja

    _yt([
        "-f", f"bv*[height<={qualidade}]+ba/b[height<={qualidade}]/b",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--newline",
        "-o", str(destino / "video.%(ext)s"),
        url,
    ], ao_vivo=ao_vivo)

    ja = video_baixado(video_id)
    if not ja:
        raise ErroYouTube("O download terminou mas o arquivo não apareceu.")
    return ja


def baixar_audio(url: str, video_id: str, ao_vivo=None) -> Path:
    """Só o áudio, para transcrever aqui na máquina.

    Uma transmissão de 1h40 dá uns 50 MB — baixa em pouco mais de um minuto,
    bem mais rápido que o vídeo inteiro.
    """
    destino = TRABALHO / video_id
    destino.mkdir(parents=True, exist_ok=True)

    ja = list(destino.glob("audio.*"))
    if ja:
        return ja[0]

    _yt(["-f", "bestaudio/best", "-x", "--audio-format", "mp3",
         "--audio-quality", "5", "--no-playlist", "--newline",
         "-o", str(destino / "audio.%(ext)s"), url], ao_vivo=ao_vivo)

    ja = list(destino.glob("audio.*"))
    if not ja:
        raise ErroYouTube("O áudio não foi baixado.")
    return ja[0]
