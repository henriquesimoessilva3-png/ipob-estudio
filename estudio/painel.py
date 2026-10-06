#!/usr/bin/env python3
"""Estúdio IPOB — painel local para editar e publicar os vídeos do canal.

Rode:  python3 painel.py      e abra  http://localhost:4747
"""
from __future__ import annotations

import json
import re
import threading
import traceback
import uuid
import webbrowser
from datetime import date, datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from nucleo import (aprendizado, artes, biblioteca, corte, legenda, pacote,
                    render, shorts, subir, trechos, youtube)
from nucleo.base import (
    ARTES, ASSETS, CASA, SAIDA, abrir_no_sistema, SAIDA_ANTIGA, TRABALHO, WEB, Cancelado, cancelar_thread,
    checar_ambiente, gravar_config, hms, ler_config, nome_de_arquivo,
    para_segundos,
)

# A página confere esta versão com a dela: se o painel.py mudou e o servidor
# não foi reiniciado, as rotas novas não existem e tudo falha com erro
# críptico. Com a versão, o painel avisa e oferece reiniciar.
VERSAO = "2026-10-06.17"

app = Flask(__name__, static_folder=None)
# sem isso o Flask reordena as chaves em ordem alfabética e a ordem dos
# pregadores na capa sai trocada
app.json.sort_keys = False
PORTA = ler_config()["padroes"].get("porta_do_painel", 4747)

TAREFAS: dict[str, dict] = {}

# Só uma renderização por vez. Sem isto, produzir duas vezes o mesmo episódio
# faz dois ffmpeg escreverem no mesmo arquivo, e o MP4 sai corrompido — com o
# índice duplicado e o final truncado. Aconteceu em 03/09/2026.
EM_ANDAMENTO: dict[str, str] = {}          # tipo -> id da tarefa
TRANSCRICOES: dict[str, list] = {}      # video_id -> blocos, para não rebaixar

# Conferir se há tarefa rodando e marcar a nova precisa ser um passo só: o
# Flask atende cada pedido numa thread, e um clique duplo passava pelos dois
# antes de qualquer um marcar.
TRAVA_DAS_TAREFAS = threading.Lock()

# A produção leva 10 a 20 minutos. Ela relê a config na hora de gravar, e esta
# trava impede que um "salvar" do painel no meio do caminho seja apagado.
TRAVA_DA_CONFIG = threading.Lock()


def _sugerir_corte(blocos: list, duracao: float, cfg: dict, formato: str) -> dict:
    """Palpite de início e fim, com o aprendizado do formato certo."""
    busca = cfg["busca_do_corte"]
    aprendido = aprendizado.palpite(cfg, formato)
    centro = aprendido["centro"]
    palpite = corte.sugerir_inicio(
        blocos, duracao, busca["gatilhos_inicio"], centro,
        busca.get("folga_antes_do_inicio", 6),
        busca.get("folga_do_convite", 1))
    fim = corte.sugerir_fim(
        blocos, duracao, busca["gatilhos_fim"], aprendido["sobra"],
        busca.get("folga_apos_o_amem", 3),
        busca.get("parar_antes_da_bencao", False))
    inicio = palpite["segundos"] if palpite else duracao * centro
    return {
        "inicio": inicio, "inicio_texto": hms(inicio),
        "fim": fim, "fim_texto": hms(fim),
        "achou": bool(palpite),
        "motivo": palpite["motivo"] if palpite else None,
        "trecho": palpite["trecho"] if palpite else None,
        "alternativas": [
            {"segundos": o["segundos"], "texto": hms(o["segundos"]),
             "motivo": o["motivo"]}
            for o in (palpite or {}).get("outros", [])
        ],
    }


# ------------------------------------------------------------------ estáticos
@app.get("/")
def raiz():
    return send_from_directory(WEB, "painel.html")


@app.get("/fila")
def fila():
    """Página pública da fila: quem não mexe no painel cadastra os sermões aqui."""
    return send_from_directory(WEB, "fila.html")


@app.get("/web/<path:arquivo>")
def estatico_web(arquivo):
    return send_from_directory(WEB, arquivo)


@app.get("/artes/<path:arquivo>")
def estatico_artes(arquivo):
    return send_from_directory(ARTES, arquivo)


@app.get("/assets/<path:arquivo>")
def estatico_assets(arquivo):
    return send_from_directory(ASSETS, arquivo)


@app.get("/favicon.ico")
def favicon():
    # sem isto, cada render de arte deixa um 404 no log
    return send_from_directory(ASSETS, "logo-redondo.png")


# ----------------------------------------------------------------------- fila
# Sermões cadastrados pela página /fila. Cada envio vira um JSON em
# ~/Movies/Estudio IPOB/fila/, à espera do modo lote (que lê daí e produz).
FILA = CASA / "fila"


# A página pública (GitHub Pages) chama estas rotas de outro domínio; sem
# estes cabeçalhos o navegador barra a chamada antes de chegar aqui.
@app.after_request
def _liberar_site_publico(resp):
    if request.path.startswith(("/api/", "/artes/", "/assets/")):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/api/<path:_rota>", methods=["OPTIONS"])
def api_opcoes(_rota):
    return ("", 204)


@app.post("/api/lote")
def api_lote():
    d = request.get_json(force=True) or {}
    sermoes = d.get("sermoes") or []
    if not isinstance(sermoes, list) or not sermoes:
        return jsonify({"erro": "Lista vazia."}), 400
    limpos = []
    for s in sermoes[:200]:
        m = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/)([\w-]{11})", str(s.get("link", "")))
        vid = m.group(1) if m else ""
        if not vid:
            return jsonify({"erro": f"Link inválido: {s.get('link')}"}), 400
        if s.get("grupo") not in ("culto", "ebd"):
            return jsonify({"erro": "Grupo tem de ser culto ou ebd."}), 400
        limpos.append({
            "video_id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
            "data": str(s.get("data", ""))[:10], "formato": s["grupo"],
            "serie": str(s.get("estudo", "")).strip().upper()[:80],
            "tema": str(s.get("tema", "")).strip()[:160],
            "referencia": str(s.get("referencia", "")).strip()[:80],
            "pregador": str(s.get("pregador", "")).strip()[:40],
            "recebido_em": datetime.now().isoformat(timespec="seconds"),
            "situacao": "aguardando",
        })
    FILA.mkdir(parents=True, exist_ok=True)
    nome = datetime.now().strftime("%Y-%m-%d_%H%M%S") + f"_{uuid.uuid4().hex[:6]}.json"
    (FILA / nome).write_text(json.dumps(limpos, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"recebidos": len(limpos), "arquivo": nome})


# --------------------------------------------------------------------- config
@app.get("/api/config")
def api_config():
    cfg = ler_config()
    cfg["_ambiente"] = checar_ambiente()
    cfg["_versao"] = VERSAO
    cfg["_pastas"] = {"saida": str(SAIDA), "trabalho": str(TRABALHO)}
    cfg["_fundos"] = sorted(p.name for p in (ASSETS / "fundos").glob("*.jpg"))
    return jsonify(cfg)


@app.post("/api/config")
def api_gravar_config():
    novo = request.get_json(force=True)
    with TRAVA_DA_CONFIG:
        cfg = ler_config()
        for chave in ("formatos", "pregadores", "padroes", "busca_do_corte"):
            if chave in novo:
                cfg[chave] = novo[chave]
        gravar_config(cfg)
    return jsonify({"ok": True})


# ------------------------------------------------------------------- estudos
# Um "estudo" é uma série em andamento num formato: guarda o visual escolhido
# (layout e cores), o pregador e a lista dos episódios já produzidos. Com ele,
# a semana seguinte já vem com tudo pronto e o número certo — e quando a série
# acaba, encerra-se o estudo e começa outro. Só pode haver um estudo em
# andamento por formato.
def _estudos(cfg: dict) -> list:
    return cfg.setdefault("estudos", [])


def _estudo_ativo(cfg: dict, formato: str) -> dict | None:
    for e in _estudos(cfg):
        if e.get("formato") == formato and not e.get("fim"):
            return e
    return None


def _estudo_por_id(cfg: dict, eid: str) -> dict | None:
    return next((e for e in _estudos(cfg) if e.get("id") == eid), None)


def _proximo_episodio(estudo: dict) -> int:
    numeros = []
    for ep in estudo.get("episodios", []):
        try:
            numeros.append(int(ep.get("n")))
        except (TypeError, ValueError):
            pass
    if numeros:
        return max(numeros) + 1
    try:
        return int(estudo.get("primeiro_episodio") or 1)
    except (TypeError, ValueError):
        return 1


def _com_proximo(estudo: dict) -> dict:
    return {**estudo, "proximo": _proximo_episodio(estudo)}


@app.get("/api/estudos")
def api_estudos():
    cfg = ler_config()
    return jsonify({"estudos": [_com_proximo(e) for e in _estudos(cfg)]})


@app.post("/api/estudos")
def api_iniciar_estudo():
    d = request.get_json(force=True)
    formato = d.get("formato", "")
    serie = (d.get("serie") or "").strip()
    if not serie:
        return jsonify({"erro": "Dê um nome à série antes de iniciar o estudo."}), 400
    with TRAVA_DA_CONFIG:
        cfg = ler_config()
        if formato not in cfg["formatos"]:
            return jsonify({"erro": "Formato desconhecido."}), 400
        if _estudo_ativo(cfg, formato):
            return jsonify({"erro": f"Já existe um estudo em andamento neste formato: \"{ativo['serie']}\". "
                                    "Encerre-o antes de iniciar outro."}), 409
        try:
            primeiro = int(d.get("primeiro_episodio") or 1)
        except (TypeError, ValueError):
            primeiro = 1
        estudo = {
            "id": uuid.uuid4().hex[:8],
            "formato": formato,
            "serie": serie,
            "playlist": (d.get("playlist") or serie).strip().upper(),
            "pregador": d.get("pregador", ""),
            "pregadores_na_capa": d.get("pregadores_na_capa") or [],
            "visual": d.get("visual") or {},
            "primeiro_episodio": primeiro,
            "inicio": date.today().isoformat(),
            "fim": None,
            "episodios": [],
        }
        _estudos(cfg).append(estudo)
        gravar_config(cfg)
    return jsonify({"estudo": _com_proximo(estudo)})


@app.post("/api/estudos/<eid>/encerrar")
def api_encerrar_estudo(eid):
    with TRAVA_DA_CONFIG:
        cfg = ler_config()
        e = _estudo_por_id(cfg, eid)
        if not e:
            return jsonify({"erro": "Estudo não encontrado."}), 404
        e["fim"] = date.today().isoformat()
        gravar_config(cfg)
    return jsonify({"estudo": _com_proximo(e)})


@app.post("/api/estudos/<eid>/episodios/<n>/remover")
def api_remover_episodio(eid, n):
    """Tira o episódio da linha do tempo do estudo. Os arquivos ficam na pasta."""
    with TRAVA_DA_CONFIG:
        cfg = ler_config()
        e = _estudo_por_id(cfg, eid)
        if not e:
            return jsonify({"erro": "Estudo não encontrado."}), 404
        eps = e.get("episodios", [])
        restantes = [x for x in eps if str(x.get("n")) != str(n)]
        if len(restantes) == len(eps):
            return jsonify({"erro": "Episódio não encontrado."}), 404
        e["episodios"] = restantes
        gravar_config(cfg)
    return jsonify({"estudo": _com_proximo(e)})


@app.post("/api/estudos/<eid>/reabrir")
def api_reabrir_estudo(eid):
    with TRAVA_DA_CONFIG:
        cfg = ler_config()
        e = _estudo_por_id(cfg, eid)
        if not e:
            return jsonify({"erro": "Estudo não encontrado."}), 404
        ativo = _estudo_ativo(cfg, e["formato"])
        if ativo and ativo is not e:
            return jsonify({"erro": f"Encerre o estudo \"{ativo['serie']}\" antes de "
                                    f"reabrir este."}), 409
        e["fim"] = None
        gravar_config(cfg)
    return jsonify({"estudo": _com_proximo(e)})


@app.post("/api/estudos/<eid>/visual")
def api_visual_do_estudo(eid):
    """Guarda um ajuste de aparência ou de pregador feito no meio do estudo."""
    d = request.get_json(force=True)
    with TRAVA_DA_CONFIG:
        cfg = ler_config()
        e = _estudo_por_id(cfg, eid)
        if not e:
            return jsonify({"erro": "Estudo não encontrado."}), 404
        for chave in ("visual", "pregador", "pregadores_na_capa", "playlist"):
            if chave in d:
                e[chave] = d[chave]
        gravar_config(cfg)
    return jsonify({"estudo": _com_proximo(e)})


# -------------------------------------------------------------- corte gravado
# O corte conferido por você fica gravado ao lado da transmissão. Analisar o
# mesmo vídeo de novo devolve esse corte, não um palpite novo — e o
# aprendizado já conta com ele antes mesmo de produzir.
CORTE_GRAVADO = "corte.json"


def _corte_gravado(video_id: str) -> dict | None:
    arq = TRABALHO / video_id / CORTE_GRAVADO
    if not arq.exists():
        return None
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


@app.post("/api/corte")
def api_gravar_corte():
    d = request.get_json(force=True)
    vid = d.get("video_id", "")
    inicio, fim = para_segundos(d.get("inicio", "")), para_segundos(d.get("fim", ""))
    if not vid:
        return jsonify({"erro": "Analise a transmissão antes de gravar o corte."}), 400
    if fim <= inicio:
        return jsonify({"erro": "O fim precisa vir depois do começo."}), 400
    info = TRANSCRICOES.get("_info_" + vid) or {}
    duracao = float(info.get("duracao") or d.get("duracao") or 0)
    formato = d.get("formato", "")
    registro = {"inicio": inicio, "fim": fim, "inicio_texto": hms(inicio), "fim_texto": hms(fim),
                "formato": formato, "quando": datetime.now().isoformat(timespec="minutes")}
    pasta = TRABALHO / vid
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / CORTE_GRAVADO).write_text(json.dumps(registro, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    aprendeu = {}
    if duracao > 0 and formato:
        with TRAVA_DA_CONFIG:
            cfg = ler_config()
            aprendeu = aprendizado.registrar(cfg, duracao, inicio, fim,
                                             formato=formato, video_id=vid)
            gravar_config(cfg)
    return jsonify({"ok": True, "corte": registro, "aprendeu": aprendeu})


# ------------------------------------------------------------------- analisar
@app.post("/api/analisar")
def api_analisar():
    """Lê a transmissão e propõe onde a pregação começa e termina."""
    dados = request.get_json(force=True)
    url = (dados.get("url") or "").strip()
    if not url:
        return jsonify({"erro": "Cole o link da transmissão."}), 400

    cfg = ler_config()
    try:
        info = youtube.informacoes(url)
    except youtube.ErroYouTube as e:
        return jsonify({"erro": str(e)}), 400
    except Exception as e:
        return jsonify({"erro": f"{type(e).__name__}: {e}"}), 500

    # A transcrição pode não existir ainda: o YouTube leva algumas horas para
    # gerar depois que a live acaba. Isso não impede o trabalho — só faz você
    # informar o minuto na mão. Por isso não é erro, é aviso.
    blocos, recado = [], None
    try:
        blocos = youtube.baixar_transcricao(url, info["id"])
    except youtube.ErroYouTube as e:
        recado = str(e)

    TRANSCRICOES[info["id"]] = blocos
    TRANSCRICOES["_info_" + info["id"]] = info
    sugestao = _sugerir_corte(blocos, info["duracao"], cfg, dados.get("formato", ""))
    gravado = _corte_gravado(info["id"])
    if gravado:
        # o que você conferiu vale mais que qualquer palpite novo
        sugestao.update(
            inicio=gravado["inicio"], inicio_texto=hms(gravado["inicio"]),
            fim=gravado["fim"], fim_texto=hms(gravado["fim"]),
            achou=True, gravado=gravado.get("quando", ""),
            motivo="corte gravado por você", trecho=None)
    return jsonify({
        "info": info,
        "duracao_texto": hms(info["duracao"]),
        **sugestao,
        "blocos": len(blocos),
        "fonte": biblioteca.fonte_da_transmissao(info["id"]),
        "sem_transcricao": recado,
        "pode_transcrever": legenda.whisper_disponivel(),
    })


def _tarefa_transcrever(tid: str, d: dict):
    """Transcreve a transmissão aqui na máquina, quando o YouTube não tem.

    Baixa só o áudio (bem mais leve que o vídeo) e roda o Whisper. Na primeira
    vez o modelo é baixado — uns 500 MB, uma vez só.
    """
    t = TAREFAS[tid]
    try:
        cfg = ler_config()

        t["etapa"] = "Baixando o áudio…"

        def do_download(linha: str):
            if "%" in linha and "ETA" in linha:
                try:
                    pct = float(linha.split("%")[0].split()[-1]) / 100
                    t.update(progresso=round(0.25 * pct, 3),
                             detalhe=linha.strip()[:110])
                except (ValueError, IndexError):
                    pass

        audio = youtube.baixar_audio(d["url"], d["video_id"], ao_vivo=do_download)

        t.update(etapa="Transcrevendo aqui na máquina…", progresso=0.28,
                 detalhe="na primeira vez o modelo é baixado (uma vez só)")
        blocos = legenda.transcrever_local(
            audio, cfg["padroes"].get("modelo_whisper", "small"))
        TRANSCRICOES[d["video_id"]] = blocos
        youtube.gravar_transcricao_local(d["video_id"], blocos)

        duracao = float(d.get("duracao") or 0)
        t.update(estado="pronto", progresso=1.0, etapa="Transcrito", detalhe="",
                 resultado={
                     "blocos": len(blocos),
                     **_sugerir_corte(blocos, duracao, cfg, d.get("formato", "")),
                 })
    except Exception as e:
        t.update(estado="erro", erro=str(e))
        traceback.print_exc()


@app.post("/api/transcrever-local")
def api_transcrever_local():
    if not legenda.whisper_disponivel():
        return jsonify({"erro": "O faster-whisper não está instalado. "
                                "No Terminal: pip3 install faster-whisper"}), 400
    d = request.get_json(force=True)
    tid = uuid.uuid4().hex[:8]
    TAREFAS[tid] = {"estado": "rodando", "etapa": "Começando…", "progresso": 0.0,
                    "detalhe": "", "log": [], "erro": None}
    threading.Thread(target=_tarefa_transcrever, args=(tid, d), daemon=True).start()
    return jsonify({"tarefa": tid})


@app.post("/api/conferir")
def api_conferir():
    """Mostra o que é falado em volta de um tempo — para conferir o corte."""
    d = request.get_json(force=True)
    blocos = TRANSCRICOES.get(d.get("video_id"), [])
    t = float(d.get("segundos", 0))
    perto = [b for b in blocos if t - 25 <= b["inicio"] <= t + 55]
    return jsonify({
        "linhas": [{"tempo": hms(b["inicio"]), "texto": b["texto"]} for b in perto][:40]
    })


# ------------------------------------------------------------------- produzir
def _pasta_do_episodio(formato: dict, chave_formato: str, serie: str, episodio: str,
                       data: str, tema: str) -> tuple[Path, str]:
    """Vídeos Editados / <formato> / <estudo> / <nº - data - tema>.

    O vídeo completo e os Shorts usam a mesma conta, então os Shorts podem
    ser gerados antes do vídeo e cair na pasta certa."""
    pasta_formato = formato.get("pasta") or formato.get("rotulo", chave_formato).split(" — ")[0]
    try:
        numero = f"{int(episodio):02d}"
    except (TypeError, ValueError):
        numero = str(episodio) or "00"
    pasta = (SAIDA / nome_de_arquivo(pasta_formato)
             / (nome_de_arquivo(serie) or "Sem série")
             / nome_de_arquivo(f"{numero} - {data} - {tema}"))
    return pasta, numero


def _tarefa(tid: str, d: dict):
    t = TAREFAS[tid]
    t["thread"] = threading.get_ident()

    def passo(etapa: str, fracao: float):
        t["etapa"] = etapa
        t["progresso"] = round(fracao, 3)
        t["log"].append(f"{datetime.now():%H:%M:%S}  {etapa}")

    try:
        cfg = ler_config()
        chave_formato = d["formato"]
        formato = cfg["formatos"][chave_formato]

        serie = d["serie"].strip()
        episodio = str(d["episodio"]).strip()
        tema = d["tema"].strip()
        referencia = d.get("referencia", "").strip()
        pregador_chave = d.get("pregador", "")
        pregador = cfg["pregadores"].get(pregador_chave, {})
        na_capa = d.get("pregadores_na_capa") or formato.get("pregadores_na_capa", [])

        pasta, numero = _pasta_do_episodio(formato, chave_formato, serie, episodio,
                                           d.get("data", ""), tema)
        pasta.mkdir(parents=True, exist_ok=True)
        t["pasta"] = str(pasta)

        visual = d.get("visual") or {}
        comuns = dict(
            formato=chave_formato, serie=serie, ep=episodio, tema=tema,
            ref=referencia, badge=formato.get("prefixo_badge", ""),
            pregadores=na_capa, pregador=pregador_chave,
            cor=visual.get("cor", ""), destaque=visual.get("destaque", ""),
            fundo=visual.get("fundo", ""), marca=visual.get("marca", "sim"),
            vars=visual.get("vars", ""),
            layout=visual.get("layout", "classico"),
            fotos=visual.get("fotos", ""),
        )

        passo("Gerando a capa e a tarja…", 0.04)
        capa, tarja = artes.gerar_as_duas(
            PORTA, pasta / "capa.png", pasta / "tarja.png", **comuns
        )
        artes.capa_para_miniatura(capa, pasta / "capa.jpg")

        passo("Baixando a transmissão do YouTube…", 0.10)

        def do_download(linha: str):
            if "%" in linha and "ETA" in linha:
                try:
                    pct = float(linha.split("%")[0].split()[-1]) / 100
                    t["progresso"] = round(0.10 + 0.45 * pct, 3)
                    t["detalhe"] = linha.strip()[:120]
                except (ValueError, IndexError):
                    pass

        fonte = youtube.baixar_video(
            d["url"], d["video_id"],
            cfg["padroes"].get("qualidade_do_download", "1080"),
            ao_vivo=do_download,
        )

        passo("Renderizando o vídeo…", 0.56)
        arquivo = pasta / f"{nome_de_arquivo(f'{serie} {numero} - {tema}')}.mp4"
        render.montar(
            fonte, capa, tarja, arquivo,
            inicio=para_segundos(d["inicio"]), fim=para_segundos(d["fim"]),
            segundos_de_capa=cfg["padroes"].get("segundos_de_capa", 5),
            fade_da_capa=cfg["padroes"].get("fade_da_capa", 0.6),
            fade_do_audio=cfg["padroes"].get("fade_do_audio", 1.0),
            bitrate=cfg["padroes"].get("bitrate_do_video", "3M"),
            normalizar_audio=cfg["padroes"].get("normalizar_audio", True),
            limpar_audio=cfg["padroes"].get("limpar_audio", True),
            progresso=lambda f: t.update(
                progresso=round(0.56 + 0.42 * f, 3),
                detalhe=f"{round(f*100)}% renderizado",
            ),
        )

        passo("Gerando a legenda…", 0.985)
        srt = None
        try:
            blocos = TRANSCRICOES.get(d["video_id"]) or youtube.baixar_transcricao(
                d["url"], d["video_id"])
            srt = legenda.gravar(
                blocos, para_segundos(d["inicio"]), para_segundos(d["fim"]),
                pasta / "legenda.srt",
                deslocamento=cfg["padroes"].get("segundos_de_capa", 5),
            )
        except Exception as e:
            # sem transcrição não há legenda, mas o vídeo já está pronto:
            # isso nunca pode derrubar a tarefa inteira
            t["log"].append(f"Sem legenda: {e}")

        passo("Escrevendo título e descrição…", 0.99)
        try:
            quando = datetime.strptime(d.get("data", ""), "%Y-%m-%d").date()
        except ValueError:
            quando = date.today()

        titulo = pacote.montar_titulo(formato, serie, episodio, tema, quando)
        descricao = pacote.montar_descricao(
            formato, serie, episodio, tema, referencia,
            pregador.get("descricao", ""), quando,
        )
        # a playlist do canal tem o nome da série ("AMOS", "PENTATEUCO"…).
        # Só quando não há série é que se usa a playlist geral do formato.
        estudo = _estudo_por_id(cfg, d.get("estudo_id", "")) if d.get("estudo_id") else None
        playlist = ((estudo or {}).get("playlist")
                    or cfg.get("series_salvas", {}).get(serie.upper(), {}).get("playlist")
                    or serie.upper()
                    or formato.get("playlist_sem_serie", ""))
        pacote.gravar(pasta, titulo, descricao, playlist)

        # a ficha é o que permite voltar neste vídeo semanas depois
        biblioteca.gravar(pasta, {
            "url": d["url"], "video_id": d["video_id"],
            "formato": chave_formato, "serie": serie, "episodio": episodio,
            "tema": tema, "referencia": referencia,
            "pregador": pregador_chave, "pregadores_na_capa": na_capa,
            "inicio": d["inicio"], "fim": d["fim"], "data": d.get("data", ""),
            "visual": visual, "playlist": playlist, "titulo": titulo,
            "arquivo": str(arquivo),
        })

        # guarda o estado para a semana que vem: série, próximo episódio e o
        # visual escolhido, para não precisar montar tudo de novo.
        #
        # A config é relida AGORA, não usada a do começo: entre um e outro se
        # passaram 10 a 20 minutos, e o que você salvou no painel nesse tempo
        # seria apagado pela cópia velha.
        with TRAVA_DA_CONFIG:
            cfg = ler_config()
            formato = cfg["formatos"][chave_formato]
            aprendeu = _guardar_semana(cfg, formato, chave_formato, d, serie,
                                       episodio, visual, playlist, titulo, pasta)
            gravar_config(cfg)
        if aprendeu.get("centro"):
            t["log"].append(
                f"Aprendido com {aprendeu['cortes']} cortes de {chave_formato}: "
                f"começa por volta de {round(aprendeu['centro']*100)}% da "
                f"transmissão, {round(aprendeu['sobra'])}s de sobra no fim.")

        t.update(
            estado="pronto", progresso=1.0, etapa="Pronto",
            detalhe="", titulo=titulo,
            arquivo=str(arquivo),
            tamanho_mb=round(arquivo.stat().st_size / 1_048_576),
            legenda=str(srt) if srt else "",
            legendas=(len(srt.read_text(encoding="utf-8").strip().split("\n\n"))
                      if srt else 0),
            playlist=playlist,
        )
        t["log"].append(f"{datetime.now():%H:%M:%S}  Pronto: {arquivo.name}")

    except Cancelado:
        t.update(estado="erro", erro="Produção parada por você. O que já foi baixado "
                                     "fica guardado; produzir de novo continua de onde parou.")
        t["log"].append("Parada por você.")
    except Exception as e:
        t.update(estado="erro", erro=str(e))
        t["log"].append(f"ERRO: {e}")
        traceback.print_exc()
    finally:
        EM_ANDAMENTO.pop("produção", None)


def _guardar_semana(cfg, formato, chave_formato, d, serie, episodio, visual,
                    playlist, titulo_do_episodio="", pasta_do_episodio="") -> dict:
    formato["serie"] = serie
    try:
        formato["proximo_episodio"] = int(episodio) + 1
    except ValueError:
        pass
    if serie:
        cfg.setdefault("series_salvas", {})[serie.upper()] = {
            "formato": chave_formato,
            "modelo": visual.get("modelo", ""),
            "cor": visual.get("cor", ""),
            "destaque": visual.get("destaque", ""),
            "fundo": visual.get("fundo", ""),
            "tarja_fundo": visual.get("tarja_fundo", ""),
            "tarja_altura": visual.get("tarja_altura", "148"),
            "marca": visual.get("marca", "sim"),
            "layout": visual.get("layout", "classico"),
            "playlist": playlist,
        }
    # o episódio entra na linha do tempo do estudo; reeditar o mesmo número
    # substitui a entrada em vez de duplicar
    estudo = _estudo_por_id(cfg, d.get("estudo_id", "")) if d.get("estudo_id") else None
    if estudo is not None:
        eps = estudo.setdefault("episodios", [])
        eps[:] = [e for e in eps if str(e.get("n")) != str(episodio)]
        eps.append({
            "n": episodio, "tema": d["tema"].strip(), "referencia": d.get("referencia", ""),
            "data": d.get("data", ""), "video_id": d["video_id"], "titulo": titulo_do_episodio,
            "pasta": str(pasta_do_episodio),
        })
        eps.sort(key=lambda e: (str(e.get("n")).zfill(4), e.get("data", "")))
        # o visual que saiu é o visual do estudo: um ajuste feito no painel fica
        estudo["visual"] = {k: v for k, v in visual.items() if k != "vars"}
        estudo["pregador"] = d.get("pregador", estudo.get("pregador", ""))
        if d.get("pregadores_na_capa"):
            estudo["pregadores_na_capa"] = d["pregadores_na_capa"]
    # o corte que você confirmou vale mais que qualquer chute meu
    info_video = TRANSCRICOES.get("_info_" + d["video_id"]) or {}
    return aprendizado.registrar(
        cfg, float(info_video.get("duracao") or d.get("duracao") or 0),
        para_segundos(d["inicio"]), para_segundos(d["fim"]),
        formato=chave_formato, video_id=d["video_id"])


def _reservar(tipo: str, tid: str, *bloqueiam: str) -> str | None:
    """Marca a tarefa como em andamento, ou explica por que não pode.

    Conferir e marcar acontecem sob a mesma trava: sem isso, dois cliques
    seguidos passavam ambos pela conferência.
    """
    with TRAVA_DAS_TAREFAS:
        for outro in (tipo, *bloqueiam):
            impedido = _ja_rodando(outro)
            if impedido:
                return impedido
        EM_ANDAMENTO[tipo] = tid
        return None


def _ja_rodando(tipo: str) -> str | None:
    """Devolve uma explicação se já houver tarefa desse tipo em andamento."""
    tid = EM_ANDAMENTO.get(tipo)
    if not tid:
        return None
    t = TAREFAS.get(tid, {})
    if t.get("estado") != "rodando":
        EM_ANDAMENTO.pop(tipo, None)
        return None
    return (f"Já tem uma {tipo} em andamento desde o começo desta sessão "
            f"({t.get('etapa', '')} {round(t.get('progresso', 0) * 100)}%). "
            f"Espere ela terminar — duas ao mesmo tempo escrevem no mesmo "
            f"arquivo e o vídeo sai corrompido.")


@app.post("/api/produzir")
def api_produzir():
    d = request.get_json(force=True)
    tid = uuid.uuid4().hex[:8]
    TAREFAS[tid] = {
        "estado": "rodando", "etapa": "Começando…", "progresso": 0.0,
        "detalhe": "", "log": [], "erro": None,
    }
    impedido = _reservar("produção", tid)
    if impedido:
        TAREFAS.pop(tid, None)
        return jsonify({"erro": impedido}), 409
    threading.Thread(target=_tarefa, args=(tid, d), daemon=True).start()
    return jsonify({"tarefa": tid})


@app.post("/api/tarefa/<tid>/parar")
def api_parar_tarefa(tid):
    """Interrompe uma produção ou geração de Shorts: mata o ffmpeg/yt-dlp da
    vez e a tarefa termina como 'parada'."""
    t = TAREFAS.get(tid)
    if not t or t.get("estado") != "rodando":
        return jsonify({"erro": "Essa tarefa não está rodando."}), 400
    ident = t.get("thread")
    if not ident:
        return jsonify({"erro": "Essa tarefa não pode ser parada."}), 400
    matou = cancelar_thread(ident)
    t["log"].append(f"{datetime.now():%H:%M:%S}  Parando…")
    return jsonify({"ok": True, "matou_processo": matou})


@app.get("/api/tarefa/<tid>")
def api_tarefa(tid):
    return jsonify(TAREFAS.get(tid, {"estado": "desconhecida"}))


# --------------------------------------------------------------- biblioteca
@app.get("/api/producoes")
def api_producoes():
    return jsonify({"producoes": biblioteca.listar()})


@app.post("/api/abrir-producao")
def api_abrir_producao():
    """Retoma um vídeo já produzido: carrega a transcrição e devolve os dados."""
    d = request.get_json(force=True)
    ficha = biblioteca.completar(d["pasta"], {"url": d.get("url", "")})

    url = ficha.get("url", "")
    vid = ficha.get("video_id", "")
    if not vid and url:
        try:
            vid = youtube.informacoes(url)["id"]
            ficha = biblioteca.completar(d["pasta"], {"video_id": vid})
        except Exception as e:
            return jsonify({"erro": str(e)}), 400
    if not vid:
        return jsonify({"erro": "Esta pasta é antiga e não guarda o link da "
                                "transmissão. Cole o link uma vez que eu gravo."}), 400

    try:
        blocos = youtube.baixar_transcricao(url, vid)
        TRANSCRICOES[vid] = blocos
    except youtube.ErroYouTube as e:
        return jsonify({"erro": str(e)}), 400

    return jsonify({
        "producao": ficha, "video_id": vid, "blocos": len(blocos),
        "shorts": biblioteca.shorts_de(d["pasta"]),
        "pasta_shorts": str(Path(d["pasta"])),
        "fonte": biblioteca.fonte_da_transmissao(vid),
    })


@app.post("/api/sugerir-trechos")
def api_sugerir_trechos():
    """Uma lista curta para você ler e escolher — não uma decisão tomada."""
    d = request.get_json(force=True)
    blocos = TRANSCRICOES.get(d.get("video_id")) or []
    if not blocos:
        return jsonify({"erro": "Sem transcrição desta transmissão. Analise-a "
                                "primeiro, ou marque os trechos na mão."}), 400
    achados = trechos.sugerir(
        blocos, para_segundos(d.get("inicio", 0)), para_segundos(d.get("fim", 0)),
        int(d.get("quantos", 5)),
    )
    return jsonify({"trechos": [
        {**c, "inicio_texto": hms(c["inicio"]), "fim_texto": hms(c["fim"])}
        for c in achados
    ]})


# -------------------------------------------------------------------- Shorts
def _tarefa_shorts(tid: str, d: dict):
    t = TAREFAS[tid]
    t["thread"] = threading.get_ident()
    try:
        cfg = ler_config()
        formato = cfg["formatos"][d["formato"]]
        visual = d.get("visual") or {}
        # os Shorts ficam na mesma pasta do episódio, ao lado do vídeo. Sem o
        # vídeo completo ainda, a pasta é calculada do mesmo jeito que a
        # produção calcularia — e ganha uma ficha para a biblioteca achar.
        if d.get("pasta"):
            pasta = Path(d["pasta"])
        else:
            pasta, _ = _pasta_do_episodio(formato, d["formato"], d.get("serie", ""),
                                          d.get("episodio", ""), d.get("data", ""),
                                          d.get("tema", ""))
        pasta.mkdir(parents=True, exist_ok=True)
        if not (pasta / biblioteca.FICHA).exists():
            biblioteca.gravar(pasta, {
                "url": d["url"], "video_id": d["video_id"], "formato": d["formato"],
                "serie": d.get("serie", ""), "episodio": d.get("episodio", ""),
                "tema": d.get("tema", ""), "referencia": d.get("referencia", ""),
                "data": d.get("data", ""), "visual": visual, "so_shorts": True,
            })
        t["pasta"] = str(pasta)

        fonte = youtube.baixar_video(d["url"], d["video_id"],
                                     cfg["padroes"].get("qualidade_do_download", "1080"))

        # sem identificação o Short fica com a cara da transmissão, sem
        # carimbo por cima — foi o que ficou melhor no teste com o Henrique
        tarja = None
        if d.get("tarja", "limpa") == "completa":
            t["etapa"] = "Gerando a tarja vertical…"
            tarja = artes.gerar_tarja_vertical(
                PORTA, pasta / "tarja-vertical.png",
                formato=d["formato"], serie=d["serie"], ep=str(d["episodio"]),
                tema=d["tema"], ref=d.get("referencia", ""),
                badge=formato.get("prefixo_badge", ""),
                cor=visual.get("cor", ""), destaque=visual.get("destaque", ""),
                marca=visual.get("marca", "sim"), vars=visual.get("vars", ""),
            )

        blocos = TRANSCRICOES.get(d["video_id"], [])
        if not blocos and d.get("legendar"):
            try:
                blocos = youtube.baixar_transcricao(d["url"], d["video_id"])
            except Exception:
                blocos = []

        feitos = []
        trechos = d["trechos"]
        for n, tr in enumerate(trechos, start=1):
            ini, f = para_segundos(tr["inicio"]), para_segundos(tr["fim"])
            if f <= ini:
                t["log"].append(f"Short {n}: fim antes do início, pulado.")
                continue
            if f - ini > shorts.LIMITE_SHORT:
                f = ini + shorts.LIMITE_SHORT
                t["log"].append(
                    f"Short {n}: cortado em {int(shorts.LIMITE_SHORT)}s, "
                    f"que é o limite do YouTube.")

            t["etapa"] = f"Short {n} de {len(trechos)}…"
            falas = []
            if d.get("legendar") and blocos:
                falas = artes.gerar_legendas(
                    PORTA, legenda.cortar(blocos, ini, f, 0),
                    pasta / f"falas-{n}",
                )

            arquivo = pasta / f"short-{n}.mp4"
            shorts.montar(
                fonte, arquivo, ini, f, tarja=tarja, falas=falas,
                modo=d.get("modo", "pregador-cheio"),
                recorte=cfg["padroes"].get("recorte_do_short") or None,
                bitrate=cfg["padroes"].get("bitrate_do_short", "8M"),
                normalizar_audio=cfg["padroes"].get("normalizar_audio", True),
                limpar_audio=cfg["padroes"].get("limpar_audio", True),
                progresso=lambda x, n=n: t.update(
                    progresso=round((n - 1 + x) / len(trechos), 3),
                    detalhe=f"{round(x*100)}%"),
            )
            feitos.append({"arquivo": str(arquivo),
                           "segundos": round(f - ini),
                           "mb": round(arquivo.stat().st_size / 1_048_576)})
            t["log"].append(f"{datetime.now():%H:%M:%S}  {arquivo.name} pronto")

        t.update(estado="pronto", progresso=1.0, etapa="Shorts prontos",
                 detalhe="", shorts=feitos, pasta_shorts=str(pasta))
    except Cancelado:
        t.update(estado="erro", erro="Geração de Shorts parada por você.")
        t["log"].append("Parada por você.")
    except Exception as e:
        t.update(estado="erro", erro=str(e))
        t["log"].append(f"ERRO: {e}")
        traceback.print_exc()
    finally:
        EM_ANDAMENTO.pop("shorts", None)


@app.post("/api/shorts")
def api_shorts():
    d = request.get_json(force=True)
    tid = uuid.uuid4().hex[:8]
    TAREFAS[tid] = {"estado": "rodando", "etapa": "Começando…", "progresso": 0.0,
                    "detalhe": "", "log": [], "erro": None}
    impedido = _reservar("shorts", tid, "produção")
    if impedido:
        TAREFAS.pop(tid, None)
        return jsonify({"erro": impedido}), 409
    threading.Thread(target=_tarefa_shorts, args=(tid, d), daemon=True).start()
    return jsonify({"tarefa": tid})


# ------------------------------------------------------------------- YouTube
@app.get("/api/youtube/estado")
def api_youtube_estado():
    return jsonify({
        "configurado": subir.configurado(),
        "conectado": subir.conectado(),
        "pasta": str(subir.CREDENCIAIS),
    })


@app.post("/api/youtube/testar")
def api_youtube_testar():
    """Valida a credencial sem publicar nada — só pergunta qual é o canal."""
    try:
        return jsonify(subir.testar())
    except subir.ErroUpload as e:
        return jsonify({"erro": str(e)}), 400
    except Exception as e:
        return jsonify({"erro": f"{type(e).__name__}: {e}"}), 500


@app.post("/api/youtube/desconectar")
def api_youtube_desconectar():
    return jsonify({"ok": subir.esquecer()})


def _tarefa_upload(tid: str, d: dict):
    t = TAREFAS[tid]
    try:
        pasta = Path(d["pasta"])
        video = Path(d["arquivo"])
        miniatura = pasta / "capa.jpg"
        srt = pasta / "legenda.srt"

        texto = (pasta / "titulo e descricao.txt").read_text(encoding="utf-8")
        titulo = d.get("titulo") or ""
        descricao = texto.split("=== DESCRIÇÃO ===", 1)[-1]
        descricao = descricao.split("=== PLAYLIST ===", 1)[0].strip()

        t["etapa"] = "Conectando ao YouTube…"
        r = subir.enviar(
            video, titulo, descricao,
            miniatura=miniatura if miniatura.exists() else None,
            legenda_srt=srt if srt.exists() else None,
            playlist=d.get("playlist", ""),
            privacidade=d.get("privacidade", "unlisted"),
            progresso=lambda f: t.update(progresso=round(f, 3),
                                         detalhe=f"{round(f*100)}% enviado"),
            recado=lambda m: t.update(etapa=m),
        )
        t.update(estado="pronto", progresso=1.0, etapa="Publicado",
                 detalhe="", resultado=r)
        t["log"].append(f"{datetime.now():%H:%M:%S}  {r['url']}")
        for a in r["avisos"]:
            t["log"].append("aviso: " + a)
        # a ficha guarda o link: abrir a produção depois mostra que já subiu
        try:
            biblioteca.completar(pasta, {"youtube": r["url"]})
        except Exception:
            pass
    except Exception as e:
        t.update(estado="erro", erro=str(e))
        t["log"].append(f"ERRO: {e}")
        traceback.print_exc()
    finally:
        EM_ANDAMENTO.pop("envio", None)


@app.post("/api/youtube/subir")
def api_youtube_subir():
    """Só roda quando você clica no botão. Nunca sobe nada sozinho."""
    d = request.get_json(force=True)
    tid = uuid.uuid4().hex[:8]
    TAREFAS[tid] = {"estado": "rodando", "etapa": "Começando…", "progresso": 0.0,
                    "detalhe": "", "log": [], "erro": None}
    # Um envio por vez. Dois cliques seguidos publicavam o vídeo duas vezes
    # no canal — e cada envio gasta boa parte da cota diária da API.
    impedido = _reservar("envio", tid)
    if impedido:
        TAREFAS.pop(tid, None)
        return jsonify({"erro": impedido}), 409
    threading.Thread(target=_tarefa_upload, args=(tid, d), daemon=True).start()
    return jsonify({"tarefa": tid})


@app.post("/api/reiniciar")
def api_reiniciar():
    """Reinicia o servidor no lugar: o processo se substitui por um novo.

    Serve para carregar um painel.py que mudou. Só é chamado pelo botão da
    página; se houver renderização em andamento, recusa.
    """
    import os
    import sys
    d = request.get_json(silent=True) or {}
    rodando = [t for t in EM_ANDAMENTO.values() if TAREFAS.get(t, {}).get("estado") == "rodando"]
    if rodando and not d.get("forcar"):
        etapas = "; ".join(TAREFAS[t].get("etapa", "") for t in rodando)
        return jsonify({"erro": f"Há uma tarefa em andamento ({etapas}). Espere terminar "
                                "ou force o reinício.", "ocupado": True}), 409

    def trocar():
        import subprocess
        import time
        time.sleep(0.5)
        # Sob o launchd (pai = 1, KeepAlive), basta sair: ele religa sozinho
        # em alguns segundos. Subir um filho aqui faria dois processos
        # disputarem a porta.
        if os.getppid() != 1:
            # rodando à mão: um filho independente (sessão própria, sem
            # herdar a porta) espera a porta liberar e sobe
            subprocess.Popen(
                [sys.executable, os.path.abspath(sys.argv[0]), "--sem-navegador", "--esperar-porta"],
                cwd=os.path.dirname(os.path.abspath(sys.argv[0])),
                close_fds=True, start_new_session=True,
            )
            time.sleep(0.3)
        os._exit(0)

    threading.Thread(target=trocar, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/apagar-videos")
def api_apagar_videos():
    """Apaga os MP4 de uma produção já publicada. Capa, legenda, título e a
    ficha ficam — são pequenos e permitem reconstruir o histórico."""
    d = request.get_json(force=True)
    pasta = Path(d.get("pasta", ""))
    if not pasta.is_dir() or not (pasta == SAIDA or SAIDA in pasta.parents
                                  or (SAIDA_ANTIGA.exists() and SAIDA_ANTIGA in pasta.parents)):
        return jsonify({"erro": "Essa pasta não é de uma produção do Estúdio."}), 400
    apagados, mb = [], 0
    for arq in list(pasta.glob("*.mp4")) + list((pasta / "shorts").glob("*.mp4")):
        mb += arq.stat().st_size / 1_048_576
        arq.unlink()
        apagados.append(arq.name)
    return jsonify({"ok": True, "apagados": apagados, "mb": round(mb)})


@app.post("/api/apagar-producao")
def api_apagar_producao():
    """Apaga a pasta inteira de uma produção (vídeo, Shorts, capa, ficha) e
    tira o episódio da linha do tempo do estudo. O painel confirma antes."""
    import shutil
    d = request.get_json(force=True)
    pasta = Path(d.get("pasta", ""))
    if not pasta.is_dir() or not (SAIDA in pasta.parents
                                  or (SAIDA_ANTIGA.exists() and SAIDA_ANTIGA in pasta.parents)):
        return jsonify({"erro": "Essa pasta não é de uma produção do Estúdio."}), 400
    shutil.rmtree(pasta)
    # pasta do estudo vazia some junto, para não deixar casca na biblioteca
    try:
        if pasta.parent != SAIDA and not any(pasta.parent.iterdir()):
            pasta.parent.rmdir()
    except OSError:
        pass
    with TRAVA_DA_CONFIG:
        cfg = ler_config()
        mexeu = False
        for e in _estudos(cfg):
            eps = e.get("episodios", [])
            novos = [x for x in eps if x.get("pasta") != str(pasta)]
            if len(novos) != len(eps):
                e["episodios"] = novos
                mexeu = True
        if mexeu:
            gravar_config(cfg)
    return jsonify({"ok": True})


@app.post("/api/abrir-pasta")
def api_abrir_pasta():
    """Abre no Finder. Com `revelar`, seleciona o arquivo dentro da pasta."""
    import subprocess
    d = request.get_json(force=True)
    caminho = d.get("caminho") or str(SAIDA)
    if not Path(caminho).exists():
        return jsonify({"erro": f"Não achei: {caminho}"}), 404
    abrir_no_sistema(caminho, revelar=bool(d.get("revelar")))
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"\n  Estúdio IPOB  →  http://localhost:{PORTA}\n")
    print(f"  vídeos prontos em: {SAIDA}\n")
    import sys
    if "--esperar-porta" in sys.argv:
        # nasceu de um reinício: o processo antigo ainda pode estar soltando a porta
        import socket
        import time
        for _ in range(60):
            try:
                with socket.socket() as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(("127.0.0.1", PORTA))
                break
            except OSError:
                time.sleep(0.25)
    if "--sem-navegador" not in sys.argv:   # num reinício a página já está aberta
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{PORTA}")).start()
    app.run(host="127.0.0.1", port=PORTA, debug=False, threaded=True)
