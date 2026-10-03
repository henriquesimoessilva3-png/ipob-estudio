"""Gera a legenda (.srt) do trecho cortado.

Aproveita a transcrição que o Estúdio já baixa do YouTube para achar o corte:
basta recortar a faixa de tempo, tirar o deslocamento do início e somar os
segundos da capa. Não processa áudio nem instala nada.

Se o `faster-whisper` estiver instalado, ele pode transcrever localmente — mais
preciso e funciona em transmissão sem legenda automática. É opcional.
"""
from __future__ import annotations

import re
from pathlib import Path

# a legenda automática marca sons assim: [ressonante], [música]
_ANOTACAO = re.compile(r"\[[^\]]*\]")

# Uma legenda confortável de ler tem umas 2 linhas curtas e fica de 1,5 a 6
# segundos na tela. Os blocos da legenda automática do YouTube são pedacinhos
# de 2 ou 3 palavras, então precisam ser reagrupados.
MAX_CARACTERES = 84
MAX_SEGUNDOS = 6.0
MIN_SEGUNDOS = 1.2


def _tempo_srt(s: float) -> str:
    s = max(0.0, s)
    h, resto = divmod(s, 3600)
    m, seg = divmod(resto, 60)
    inteiro = int(seg)
    ms = int(round((seg - inteiro) * 1000))
    if ms == 1000:                       # arredondamento não pode virar 60s
        inteiro, ms = inteiro + 1, 0
    return f"{int(h):02d}:{int(m):02d}:{inteiro:02d},{ms:03d}"


def agrupar(blocos: list[dict]) -> list[dict]:
    """Junta os pedacinhos da transcrição em falas legíveis."""
    juntos: list[dict] = []
    atual: dict | None = None

    for b in blocos:
        texto = _ANOTACAO.sub("", b["texto"]).strip()
        if not texto:
            continue
        if atual is None:
            atual = {"inicio": b["inicio"], "fim": b["fim"], "texto": texto}
            continue

        cabe = (len(atual["texto"]) + 1 + len(texto)) <= MAX_CARACTERES
        curto = (b["fim"] - atual["inicio"]) <= MAX_SEGUNDOS
        if cabe and curto:
            atual["texto"] += " " + texto
            atual["fim"] = b["fim"]
        else:
            juntos.append(atual)
            atual = {"inicio": b["inicio"], "fim": b["fim"], "texto": texto}

    if atual:
        juntos.append(atual)

    # nenhuma legenda pode sumir antes de dar tempo de ler, nem invadir a próxima
    for i, c in enumerate(juntos):
        c["fim"] = max(c["fim"], c["inicio"] + MIN_SEGUNDOS)
        if i + 1 < len(juntos):
            c["fim"] = min(c["fim"], juntos[i + 1]["inicio"])
        c["fim"] = max(c["fim"], c["inicio"] + 0.4)
    return juntos


def quebrar_linhas(texto: str, largura: int = 42) -> str:
    """Duas linhas curtas leem melhor que uma comprida."""
    if len(texto) <= largura:
        return texto
    palavras = texto.split()
    meio = len(texto) // 2
    melhor, corte = None, 0
    conta = 0
    for i, p in enumerate(palavras[:-1]):
        conta += len(p) + 1
        d = abs(conta - meio)
        if melhor is None or d < melhor:
            melhor, corte = d, i + 1
    return " ".join(palavras[:corte]) + "\n" + " ".join(palavras[corte:])


def cortar(blocos: list[dict], inicio: float, fim: float,
           deslocamento: float = 0.0) -> list[dict]:
    """Recorta a transcrição na faixa pedida e devolve as falas com tempo.

    Cada item é {'a': início, 'b': fim, 'texto': …}, já com os tempos contados
    a partir do começo do vídeo final. `deslocamento` são os segundos de capa
    que entram antes da pregação.
    """
    faixa = [b for b in blocos if b["fim"] > inicio and b["inicio"] < fim]
    if not faixa:
        return []

    falas = []
    for c in agrupar(faixa):
        a = max(0.0, c["inicio"] - inicio) + deslocamento
        b = max(0.0, min(c["fim"], fim) - inicio) + deslocamento
        # o primeiro e o último bloco costumam ficar pela metade no corte;
        # uma legenda de meio segundo ninguém lê, então some
        if b - a < 0.8:
            continue
        falas.append({"a": a, "b": b, "texto": c["texto"]})
    return falas


def montar_srt(blocos: list[dict], inicio: float, fim: float,
               deslocamento: float = 0.0) -> str:
    """O texto do arquivo .srt, para subir no Studio."""
    partes = [
        f"{n}\n{_tempo_srt(f['a'])} --> {_tempo_srt(f['b'])}\n"
        f"{quebrar_linhas(f['texto'])}\n"
        for n, f in enumerate(cortar(blocos, inicio, fim, deslocamento), start=1)
    ]
    return "\n".join(partes)


def gravar(blocos: list[dict], inicio: float, fim: float, destino: Path,
           deslocamento: float = 0.0) -> Path | None:
    texto = montar_srt(blocos, inicio, fim, deslocamento)
    if not texto:
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return destino


# ---------------------------------------------------------------- opcional
def whisper_disponivel() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def transcrever_local(video: Path, modelo: str = "small") -> list[dict]:
    """Transcreve o arquivo aqui na máquina. Só se o faster-whisper existir.

    Serve para quando a transmissão ainda não tem legenda automática no
    YouTube — o que acontece nas primeiras horas depois da live.
    """
    from faster_whisper import WhisperModel

    # O Whisper erra muito menos com o som limpo e no volume certo. Aqui a
    # transmissão passa pela mesma limpeza do vídeo final e vira um WAV mono
    # de 16 kHz (o formato que o modelo usa por dentro).
    import tempfile

    from .base import rodar
    from .render import LIMPEZA

    pasta = Path(tempfile.mkdtemp(prefix="whisper-"))
    limpo = pasta / "limpo.wav"
    r = rodar(["ffmpeg", "-y", "-v", "error", "-i", str(video),
               "-af", f"{LIMPEZA},loudnorm=I=-16:TP=-1.5:LRA=11",
               "-ac", "1", "-ar", "16000", str(limpo)])
    fonte = limpo if (r.returncode == 0 and limpo.exists()) else video

    m = WhisperModel(modelo, device="auto", compute_type="int8")
    segmentos, _ = m.transcribe(str(fonte), language="pt", vad_filter=True,
                                beam_size=5, condition_on_previous_text=False)
    return [{"inicio": s.start, "fim": s.end, "texto": s.text.strip()}
            for s in segmentos]
