"""Escreve o título, a descrição e o recado do WhatsApp, no padrão do canal."""
from __future__ import annotations

from datetime import date
from pathlib import Path

LIMITE_TITULO = 100          # o YouTube corta o que passar disso
IGREJA = "IGREJA PRESBITERIANA DE OURO BRANCO"


def _encurtar(titulo: str, limite: int = LIMITE_TITULO) -> str:
    """Corta no espaço anterior, nunca no meio de uma palavra."""
    if len(titulo) <= limite:
        return titulo
    corte = titulo[: limite - 1]
    if " " in corte:
        corte = corte[: corte.rindex(" ")]
    return corte.rstrip(" -,–") + "…"


def montar_titulo(formato: dict, serie: str, episodio: str, tema: str,
                  data_culto: date | None = None) -> str:
    # aula avulsa, fora de série: o padrão do canal usa a data no lugar
    if not serie.strip():
        quando = (data_culto or date.today()).strftime("%d/%m/%Y")
        cabeca = formato.get("cabecalho_descricao", "MENSAGEM BÍBLICA")
        sigla = " (EBD)" if "ESCOLA" in cabeca.upper() else ""
        return _encurtar(f"{cabeca}{sigla} – {quando} - TEMA: “{tema}”")

    palavra = formato.get("palavra_episodio", "EP")
    if palavra.upper() == "EP":
        miolo = f"SÉRIE “{serie}” EP{episodio}"
    else:
        miolo = f"SÉRIE “{serie}” - {palavra} {episodio}"
    return _encurtar(f"{miolo} - TEMA: “{tema}”")


def montar_descricao(formato: dict, serie: str, episodio: str, tema: str,
                     referencia: str, pregador: str,
                     data_culto: date | None = None,
                     link: str = "") -> str:
    palavra = formato.get("palavra_episodio", "EP")
    quando = (data_culto or date.today()).strftime("%d/%m/%Y")

    if serie.strip():
        linhas = [
            formato.get("cabecalho_descricao", ""),
            f"SÉRIE “{serie}”",
            f"{palavra} {episodio} - TEMA: “{tema}”",
        ]
    else:
        cabeca = formato.get("cabecalho_descricao", "")
        linhas = [
            f"{cabeca} - EBD" if "ESCOLA" in cabeca.upper() else cabeca,
            f"TEMA: “{tema}”",
        ]
    if referencia:
        linhas.append(referencia)
    if pregador:
        linhas.append(pregador)
    linhas += ["", IGREJA, "", "", "-" * 46, ""]

    linhas += [
        formato.get("saudacao", "Boa tarde!"),
        f"Segue o link da {formato.get('nome_do_momento','pregação')} "
        f"de Domingo, {quando}",
    ]
    if serie.strip():
        linhas += [f"SÉRIE “{serie}”", f"{palavra} {episodio} - TEMA: “{tema}”"]
    else:
        linhas += [f"TEMA: “{tema}”"]
    linhas += [link or "(cole aqui o link depois de subir)"]
    return "\n".join(x for x in linhas if x is not None)


def gravar(pasta: Path, titulo: str, descricao: str, playlist: str = "") -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / "titulo e descricao.txt"
    conteudo = (
        "=== TÍTULO ===\n"
        f"{titulo}\n"
        f"({len(titulo)} de {LIMITE_TITULO} caracteres)\n\n"
        "=== DESCRIÇÃO ===\n"
        f"{descricao}\n"
    )
    if playlist:
        conteudo += f"\n=== PLAYLIST ===\n{playlist}\n"
    destino.write_text(conteudo, encoding="utf-8")
    return destino
