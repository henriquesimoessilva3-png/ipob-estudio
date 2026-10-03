"""A lista dos vídeos já produzidos, para poder voltar neles.

Cada produção grava um `producao.json` na própria pasta, com tudo que é preciso
para retomar depois: o link da transmissão, os tempos de corte, a série e as
cores. Sem isso não dá para gerar um Short semanas depois — a pasta teria só o
MP4, sem saber de onde ele veio.

Pastas antigas, feitas antes disso existir, são reconstruídas pelo nome e pelo
"titulo e descricao.txt". O que não der para descobrir (o link, quase sempre)
o painel pede uma vez e grava.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import SAIDA, SAIDA_ANTIGA, TRABALHO

FICHA = "producao.json"


def gravar(pasta: Path, dados: dict) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / FICHA
    destino.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destino


def _do_nome(pasta: Path) -> dict:
    """Reconstrói o que dá a partir de '2026-08-30 JOAO 2 TESTE'."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})\s+(.*)", pasta.name)
    if not m:
        return {"data": "", "serie": "", "episodio": "", "tema": pasta.name}
    resto = m.group(2)
    m2 = re.match(r"(.+?)\s+(\d+)\s+(.*)", resto)
    if m2:
        return {"data": m.group(1), "serie": m2.group(1),
                "episodio": m2.group(2), "tema": m2.group(3)}
    return {"data": m.group(1), "serie": resto, "episodio": "", "tema": ""}


def _do_texto(pasta: Path) -> dict:
    """Pesca a referência e a playlist do arquivo de título e descrição."""
    arq = pasta / "titulo e descricao.txt"
    if not arq.exists():
        return {}
    t = arq.read_text(encoding="utf-8", errors="ignore")
    achado = {}
    m = re.search(r"=== PLAYLIST ===\s*\n(.+)", t)
    if m:
        achado["playlist"] = m.group(1).strip()
    m = re.search(r"=== TÍTULO ===\s*\n(.+)", t)
    if m:
        achado["titulo"] = m.group(1).strip()
    return achado


def _transcricao_em_disco(video_id: str) -> bool:
    return bool(video_id) and any((TRABALHO / video_id).glob("*.vtt"))


def _videos_principais(pasta: Path) -> list[Path]:
    """Os MP4 da pasta que não são Shorts."""
    return sorted(p for p in pasta.glob("*.mp4") if not p.name.startswith("short-"))


def _tem_producao(p: Path) -> bool:
    return bool(_videos_principais(p)) or bool(list(p.glob("short-*.mp4")))


def _pastas_de_producao() -> list[Path]:
    """Toda pasta que tem um vídeo principal ou Shorts: a árvore nova
    (formato/estudo/episódio) e a pasta antiga, plana."""
    achadas = []
    if SAIDA.is_dir():
        for p in SAIDA.rglob("*"):
            if p.is_dir() and _tem_producao(p):
                achadas.append(p)
    if SAIDA_ANTIGA.is_dir():
        achadas += [p for p in SAIDA_ANTIGA.iterdir() if p.is_dir() and _videos_principais(p)]
    return sorted(achadas, key=lambda p: -p.stat().st_mtime)


def listar() -> list[dict]:
    """As produções, da mais recente para a mais antiga."""
    saida = []
    for pasta in _pastas_de_producao():
        videos = _videos_principais(pasta) or sorted(pasta.glob("short-*.mp4"))

        ficha = pasta / FICHA
        if ficha.exists():
            try:
                d = json.loads(ficha.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                d = {}
        else:
            d = {**_do_nome(pasta), **_do_texto(pasta), "_reconstruida": True}

        d["pasta"] = str(pasta)
        d["arquivo"] = str(videos[0])
        d["mb"] = round(videos[0].stat().st_size / 1_048_576)
        d["tem_transcricao"] = _transcricao_em_disco(d.get("video_id", ""))
        d["tem_shorts"] = bool(list(pasta.glob("short-*.mp4"))) or (pasta / "shorts").is_dir()
        saida.append(d)
    return saida


def fonte_da_transmissao(video_id: str) -> dict:
    """A transmissão crua baixada — é dela que os Shorts são recortados.

    O vídeo editado nunca é usado como fonte: os tempos dos Shorts são os da
    live inteira, então recortar do editado nem funcionaria.
    """
    if not video_id:
        return {"tem": False}
    from .youtube import video_baixado

    arq = video_baixado(video_id)
    if arq:
        return {"tem": True, "arquivo": str(arq),
                "mb": round(arq.stat().st_size / 1_048_576)}
    return {"tem": False}


def shorts_de(pasta: Path | str) -> list[dict]:
    """Os Shorts que já existem nesta produção."""
    from .base import rodar

    # Shorts novos ficam na própria pasta (short-N.mp4); os antigos, em shorts/
    base = Path(pasta)
    arquivos = sorted(base.glob("short-*.mp4"))
    if (base / "shorts").is_dir():
        arquivos += sorted((base / "shorts").glob("*.mp4"))
    if not arquivos:
        return []

    achados = []
    for arq in arquivos:
        r = rodar(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                   "-of", "csv=p=0", str(arq)])
        try:
            seg = round(float(r.stdout.strip()))
        except ValueError:
            seg = 0
        achados.append({
            "arquivo": str(arq), "nome": arq.name,
            "mb": round(arq.stat().st_size / 1_048_576), "segundos": seg,
        })
    return achados


def completar(pasta: Path, novos: dict) -> dict:
    """Acrescenta o que faltava (o link, por exemplo) e regrava a ficha."""
    atual = {}
    ficha = Path(pasta) / FICHA
    if ficha.exists():
        try:
            atual = json.loads(ficha.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    if not atual:
        atual = {**_do_nome(Path(pasta)), **_do_texto(Path(pasta))}
    atual.update({k: v for k, v in novos.items() if v not in (None, "")})
    atual.pop("_reconstruida", None)
    gravar(Path(pasta), atual)
    return atual
