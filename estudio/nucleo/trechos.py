"""Sugere trechos da pregação para virar Short.

Isto NÃO é detecção de viralidade. As ferramentas que prometem isso usam um
modelo treinado majoritariamente em inglês e escolhem mal em português — foi
por isso que a escolha ficou com você desde o começo.

O que aqui se faz é mais modesto e mais honesto: varrer a transcrição
procurando trechos que tenham as marcas de um bom recorte de pregação —
começam em início de frase, falam com a igreja em vez de só ler o texto, têm
uma virada ("mas", "portanto") e terminam a ideia. Sai uma lista curta para
você ler e escolher, não uma decisão tomada.
"""
from __future__ import annotations

import re

from .corte import simples

DURACAO_MINIMA = 30.0
DURACAO_MAXIMA = 58.0
DISTANCIA_MINIMA = 180.0     # dois Shorts não podem sair do mesmo momento

# o pregador falando COM a igreja, não apenas lendo
_DIRETO = re.compile(
    r"\birmaos?\b|\bvoces?\b|\bvoce\b|\bolh[ae]\b|\bvej[ao]\b|\brepare\b"
    r"\b|\bpresta\b|\bescut[ae]\b|\bpergunto\b|\bquero que\b|\bpreciso\b"
    r"|\bnos\b|\bnossa\b|\bnosso\b"
)
# a virada do argumento
_VIRADA = re.compile(r"\bmas\b|\bporem\b|\bentretanto\b|\bno entanto\b|\bcontudo\b"
                     r"|\bportanto\b|\bpor isso\b|\bentao\b|\bveja bem\b")
# o assunto
_PESO = re.compile(r"\bdeus\b|\bcristo\b|\bjesus\b|\bsenhor\b|\bevangelho\b"
                   r"|\bgraca\b|\bsalvacao\b|\bfe\b|\bpecado\b|\bcruz\b"
                   r"|\besperanca\b|\bamor\b|\bvida\b|\bcoracao\b")
# o que NÃO rende Short
_RUIM = re.compile(r"\bversiculo\b|\bcapitulo\b|\bleitura\b|\bvamos ler\b"
                   r"|\bpagina\b|\bhino\b|\bavis[oa]\b|\boferta\b|\bboletim\b"
                   r"|\bproxim[oa] domingo\b|\bamem\b")

_FIM_DE_FRASE = re.compile(r"[.!?]\s*$")


def _texto(blocos, i, j) -> str:
    return " ".join(b["texto"] for b in blocos[i:j])


def sugerir(blocos: list[dict], inicio: float, fim: float,
            quantos: int = 5) -> list[dict]:
    """Devolve os melhores trechos entre `inicio` e `fim`, já ordenados."""
    dentro = [b for b in blocos if inicio <= b["inicio"] <= fim]
    if len(dentro) < 12:
        return []

    # os primeiros e os últimos minutos são introdução e oração: não rendem
    limite_a = inicio + 240
    limite_b = fim - 180

    candidatos = []
    for i, b in enumerate(dentro):
        if not (limite_a <= b["inicio"] <= limite_b):
            continue
        # só começa onde uma frase começa
        if i > 0 and not _FIM_DE_FRASE.search(dentro[i - 1]["texto"]):
            continue

        # cresce até a duração alvo, parando numa frase completa
        j = i
        while j < len(dentro) and dentro[j]["fim"] - b["inicio"] < DURACAO_MAXIMA:
            j += 1
        while j > i + 3 and not _FIM_DE_FRASE.search(dentro[j - 1]["texto"]):
            j -= 1
        if j <= i + 3:
            continue

        duracao = dentro[j - 1]["fim"] - b["inicio"]
        if not (DURACAO_MINIMA <= duracao <= DURACAO_MAXIMA):
            continue

        bruto = _texto(dentro, i, j)
        t = simples(bruto)
        palavras = max(1, len(t.split()))

        nota = (
            3.0 * len(_DIRETO.findall(t)) / palavras * 100
            + 6.0 * min(3, len(_VIRADA.findall(t)))
            + 2.0 * len(_PESO.findall(t)) / palavras * 100
            - 9.0 * len(_RUIM.findall(t))
            + (4.0 if "?" in bruto else 0.0)
        )
        candidatos.append({
            "inicio": round(b["inicio"], 1),
            "fim": round(dentro[j - 1]["fim"], 1),
            "segundos": round(duracao),
            "nota": round(nota, 1),
            "texto": bruto.strip(),
        })

    candidatos.sort(key=lambda c: -c["nota"])

    # espalha pela pregação: três Shorts do mesmo minuto não servem
    escolhidos: list[dict] = []
    for c in candidatos:
        if all(abs(c["inicio"] - e["inicio"]) >= DISTANCIA_MINIMA for e in escolhidos):
            escolhidos.append(c)
        if len(escolhidos) == quantos:
            break
    return sorted(escolhidos, key=lambda c: c["inicio"])
