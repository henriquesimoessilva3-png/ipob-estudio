"""Acha, na transcrição, onde a pregação (ou a aula da EBD) começa.

Não é adivinhação: a transmissão sempre segue a mesma ordem — oração, louvor,
avisos e só então a Palavra. O que muda é o minuto. Aqui procuramos as frases
que o pastor usa para abrir o texto e pesamos pela posição típica dentro da
transmissão. O painel mostra o trecho encontrado para você conferir.
"""
from __future__ import annotations

import math
import re
import unicodedata

LIVROS = (
    "genesis exodo levitico numeros deuteronomio josue juizes rute samuel reis "
    "cronicas esdras neemias ester jo salmo salmos proverbios eclesiastes "
    "canticos isaias jeremias lamentacoes ezequiel daniel oseias joel amos "
    "obadias jonas miqueias naum habacuque sofonias ageu zacarias malaquias "
    "mateus marcos lucas joao atos romanos corintios galatas efesios "
    "filipenses colossenses tessalonicenses timoteo tito filemom hebreus "
    "tiago pedro judas apocalipse"
).split()


def simples(texto: str) -> str:
    """Tira acento e pontuação para comparar sem tropeçar."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", t)


# O aviso das crianças é o marcador mais confiável do início: elas saem para o
# culto infantil e a pregação começa em seguida.
#
# A fórmula muda toda semana — "poderão descer às classes", "podem colocar-se à
# porta do templo para o culto infantil", "os juvenis que descerão". Decorar
# frases não funciona. O que não muda é a ESTRUTURA: fala-se das crianças
# saindo e, logo depois, o pregador convida a abrir a Bíblia. É esse par que
# procuramos, e é ele que separa o aviso de verdade de uma oração que
# menciona as crianças de passagem.
_CRIANCAS = re.compile(r"crianc|juveni|infanti")
_DISPENSA = re.compile(
    r"\bdesc\w*|\bclasse|\bsala|\bsaiam|\bse retir|\bporta\b|\btemplo\b"
    r"|\bculto infantil|\bacompanh\w*|\bconduz\w*"
    # "Deus abençoe as crianças, os professores" (EBD de 27/09/2026): com o
    # som ruim só sobrou isso do aviso. Crianças + professores é dispensa.
    r"|\bprofessor\w*|\bprofessora\w*"
)
_ABERTURA = re.compile(
    r"\babr\w*\b.{0,40}\b(biblia|escritura|palavra|livro|capitulo)"
    r"|\b(biblia|escritura)s?\b.{0,30}\babert"
)

SEGUNDOS_ATE_A_PALAVRA = 120     # quanto tempo depois do aviso a Palavra abre
FOLGA_DO_CONVITE = 1.0           # não cortar em cima da primeira palavra

# O convite para abrir a Bíblia — "e peço aos irmãos que abram as suas
# Bíblias", "convido você a abrir a sua Bíblia". O verbo fica num bloco e o
# objeto no seguinte, então o verbo é procurado no bloco e o objeto logo
# adiante.
# "abriremos", "abram", "abrir"; e também "deixam as suas Bíblias ABERTAS"
# (aula 4 de Apocalipse): o particípio não começa com "abr".
_VERBO_ABRIR = re.compile(r"\babr\w*\b|\babert\w*\b|\bvamos ler\b|\bfaremos a leitura\b")
_OBJETO_PALAVRA = re.compile(r"\bbiblia|\bescritura|\bpalavra\b|\blivro\b|\bcapitulo")

# A frase do convite às vezes começa um bloco antes do verbo: "E eu convido /
# você que permanecerá no templo a abrir a / sua Bíblia". O corte é onde a
# frase começa, não onde o verbo aparece.
_INICIO_DO_CONVITE = re.compile(r"\bpe[cç]o\b|\bconvido\b|\bconvite\b|\bpedir\b|\bpe[cç]amos\b|\bpergunto\b")
# Avisos mais próximos que isso são o mesmo aviso, falado em blocos seguidos.
# 45s separa a oração de abertura (que também cita as crianças) do aviso de
# verdade, que costuma vir mais de um minuto depois.
INTERVALO_DO_GRUPO = 45


def aviso_das_criancas(texto: str) -> bool:
    t = simples(texto)
    return bool(_CRIANCAS.search(t) and _DISPENSA.search(t))


def _abre_a_palavra(texto: str) -> bool:
    t = simples(texto)
    return bool(_ABERTURA.search(t)) or _tem_referencia(texto)


def bloco_do_convite(blocos: list[dict], desde: int) -> int | None:
    """Onde o pregador convida a abrir a Bíblia — é aí que a pregação começa.

    Henrique definiu assim: o corte perfeito é quando o pastor termina o aviso
    das crianças e emenda "e peço aos irmãos que abram as suas Bíblias". O
    ponto é o começo dessa frase, não o fim do aviso.

    O verbo é procurado no bloco e o objeto ("Bíblias", "capítulo") logo à
    frente, porque a legenda quebra a frase no meio.
    """
    limite = blocos[desde]["fim"] + SEGUNDOS_ATE_A_PALAVRA
    for j in range(desde, min(desde + 80, len(blocos))):
        if blocos[j]["inicio"] > limite:
            break
        if not _VERBO_ABRIR.search(simples(blocos[j]["texto"])):
            continue
        adiante = " ".join(x["texto"] for x in blocos[j: j + 4])
        if not _OBJETO_PALAVRA.search(simples(adiante)):
            continue

        # a frase pode ter começado um ou dois blocos antes, em "E eu convido"
        inicio = j
        for k in (j - 1, j - 2):
            if k < desde or k < 0:
                break
            if blocos[j]["inicio"] - blocos[k]["inicio"] > 10:
                break
            if _INICIO_DO_CONVITE.search(simples(blocos[k]["texto"])):
                inicio = k
        return inicio
    return None


def _confirmado_pela_palavra(blocos: list[dict], i: int) -> bool:
    """O convite para abrir a Bíblia vem logo depois do aviso de verdade.

    Junta o que é falado nos dois minutos seguintes num texto só. Bloco a
    bloco não funciona: a legenda quebra "abrir a / sua Bíblia no livro de /
    Zacarias, capítulo 12" em quatro pedaços, e nenhum deles é reconhecível
    sozinho.
    """
    limite = blocos[i]["fim"] + SEGUNDOS_ATE_A_PALAVRA
    seguinte = []
    for b in blocos[i + 1: i + 80]:
        if b["inicio"] > limite:
            break
        seguinte.append(b["texto"])
    return _abre_a_palavra(" ".join(seguinte))


def _tem_referencia(texto: str) -> bool:
    """'em Amós capítulo 9' / 'Amós 9.1' — leitura da referência bíblica."""
    t = simples(texto)
    if not any(f" {l}" in f" {t}" for l in LIVROS):
        return False
    return bool(re.search(r"\b(capitulo|versiculo|verso)\b", t) or
                re.search(r"\b\d{1,3}\b", t))


def sugerir_inicio(blocos: list[dict], duracao: float, gatilhos: list[str],
                   centro: float = 0.46, folga: float = 6.0,
                   folga_do_convite: float = FOLGA_DO_CONVITE) -> dict | None:
    """Devolve o palpite de início com a frase que o justificou."""
    if not blocos or duracao <= 0:
        return None

    # A janela acompanha o centro aprendido do formato: a EBD abre a Palavra
    # por volta de 20–25% da transmissão (às vezes 17%), o culto perto de 40%.
    # A janela fixa em 18% deixou a aula 4 de Apocalipse (17:41 de 1:42) de
    # fora da busca.
    janela = (max(0.06, centro - 0.22) * duracao, min(0.85, centro + 0.32) * duracao)
    gatilhos_s = [simples(g) for g in gatilhos]
    candidatos = []

    for i, b in enumerate(blocos):
        if not (janela[0] <= b["inicio"] <= janela[1]):
            continue

        # junta o bloco com os vizinhos: a legenda automática quebra as frases
        redor = " ".join(x["texto"] for x in blocos[max(0, i - 2): i + 3])
        alvo = simples(redor)

        peso = 0.0
        achou = None
        depois_do_aviso = False
        total = len(gatilhos) or 1

        # a vizinhança, não o bloco isolado: a legenda do YouTube parte a frase
        # em pedaços e nenhum deles sozinho tem as duas ideias
        convite = None
        if aviso_das_criancas(redor):
            convite = bloco_do_convite(blocos, i)
        if convite is not None:
            # vale mais que tudo: é o que separa a pregação do que veio antes
            peso = 3.0
            achou = "aviso das crianças + convite para abrir a Bíblia"
            depois_do_aviso = True

        for pos, (g, g_s) in enumerate(zip(gatilhos, gatilhos_s)):
            if g_s and g_s in alvo:
                # a ordem da lista importa: uma frase de abertura da Palavra
                # vale mais que um "capítulo" solto lá embaixo
                prioridade = 1.0 + 0.8 * (1 - pos / total)
                peso = max(peso, prioridade + 0.10 * len(g_s.split()))
                achou = achou or g
        if _tem_referencia(redor):
            peso += 1.2
            achou = achou or "leitura da referência bíblica"
        if not peso:
            continue

        # a pregação costuma começar por volta de 45% da transmissão
        desvio = (b["inicio"] / duracao - centro) / 0.20
        peso *= math.exp(-0.5 * desvio * desvio)

        # Com o aviso das crianças, o corte vai para o começo do convite —
        # "e peço aos irmãos que abram as suas Bíblias". Nos outros gatilhos
        # entra um pouco antes, para não perder o anúncio do texto.
        if convite is not None:
            onde = max(0.0, blocos[convite]["inicio"] - folga_do_convite)
        else:
            onde = max(0.0, b["inicio"] - folga)

        candidatos.append({
            "crianc": depois_do_aviso,
            "segundos": onde,
            "peso": round(peso, 3),
            "motivo": achou,
            "trecho": redor[:260].strip(),
        })

    if not candidatos:
        return None
    candidatos.sort(key=lambda c: -c["peso"])

    # O aviso das crianças não disputa peso com os outros: ele é estrutural.
    # Quando aparece, é ele que manda — uma frase como "abram comigo as
    # escrituras" pode ser uma referência cruzada no meio da pregação, mas as
    # crianças só descem uma vez, e a Palavra vem logo depois.
    # Entre os avisos vale o ÚLTIMO GRUPO, e dentro dele o PRIMEIRO.
    #
    # O último grupo, porque a oração de abertura também fala das crianças que
    # vão sair ("abençoa as crianças que descerão às classes") e vem antes.
    # O primeiro do grupo, porque o aviso ocupa vários blocos seguidos e a
    # vizinhança se sobrepõe: pegar o último faria o corte escorregar para
    # frente e começar com a pregação já em curso.
    avisos = sorted((c for c in candidatos if c["crianc"]),
                    key=lambda c: c["segundos"])
    if avisos:
        grupo = [avisos[-1]]
        for c in reversed(avisos[:-1]):
            if grupo[0]["segundos"] - c["segundos"] <= INTERVALO_DO_GRUPO:
                grupo.insert(0, c)
            else:
                break
        melhor = grupo[0]
    else:
        melhor = candidatos[0]
    candidatos = [c for c in candidatos if c is not melhor]

    # alternativas só valem se forem de outro momento da transmissão;
    # três palpites com 8 segundos de diferença não ajudam ninguém
    outros, usados = [], [melhor["segundos"]]
    for c in candidatos:
        if all(abs(c["segundos"] - u) > 90 for u in usados):
            outros.append(c)
            usados.append(c["segundos"])
        if len(outros) == 3:
            break
    melhor["outros"] = outros
    return melhor


_AMEM = re.compile(r"\bam[eé]m\b")

# A bênção apostólica ("a graça do Senhor Jesus, o amor de Deus e a comunhão
# do Espírito repousem sobre vós") vem DEPOIS da pregação e também termina em
# amém. Ela não entra no vídeo — o corte é no amém da oração que fecha a
# pregação, logo antes dela.
_BENCAO = re.compile(
    r"\bgraca\b|\bcomunhao\b|\brepousem\b|\bsobre vos\b|\bide em paz\b"
    r"|\bbencao apostolica\b|\bvos abencoe\b|\babencoe a todos\b"
    r"|\bpovo de deus,? ide\b"
)


def sugerir_fim(blocos: list[dict], duracao: float, gatilhos: list[str],
                sobra: float = 8.0, folga: float = 3.0,
                parar_antes_da_bencao: bool = True) -> float:
    """Acha o fim da pregação pelo amém da oração final.

    A pregação sempre termina com uma oração, e o pastor fecha dizendo amém.
    Logo depois já dá para cortar.

    O cuidado aqui é não confundir esse amém com o da bênção apostólica, que
    vem em seguida e também termina em amém. Por isso os améns são varridos de
    trás para frente: o primeiro que NÃO for de bênção é o da pregação.

    Sem transcrição, cai no padrão de sempre: alguns segundos antes do fim
    da transmissão.
    """
    if not blocos:
        return max(0.0, duracao - sobra)

    limite = duracao * 0.70          # só interessa o encerramento
    finais = [b for b in blocos if b["inicio"] >= limite
              and _AMEM.search(simples(b["texto"]))]

    for i, b in enumerate(finais):
        # o que foi dito nos 45 segundos antes deste amém
        antes = " ".join(x["texto"] for x in blocos
                         if b["inicio"] - 45 <= x["inicio"] <= b["fim"])
        finais[i] = {**b, "_bencao": bool(_BENCAO.search(simples(antes)))}

    if not parar_antes_da_bencao and finais:
        return min(duracao, finais[-1]["fim"] + folga)

    for b in reversed(finais):
        if not b["_bencao"]:
            return min(duracao, b["fim"] + folga)

    if finais:                        # todos pareceram bênção: fica com o 1º
        return min(duracao, finais[0]["fim"] + folga)
    return max(0.0, duracao - sobra)


def texto_do_trecho(blocos: list[dict], inicio: float, fim: float,
                    maximo: int = 1200) -> str:
    """Amostra do que é falado no trecho — o painel usa para você conferir."""
    partes = [b["texto"] for b in blocos if inicio <= b["inicio"] <= fim]
    return " ".join(partes)[:maximo]
