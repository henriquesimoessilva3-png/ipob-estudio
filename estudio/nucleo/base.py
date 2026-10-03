"""Caminhos, configuração e utilidades comuns do Estúdio IPOB."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Sob o LaunchAgent o PATH é só /usr/bin:/bin:/usr/sbin:/sbin — o ffmpeg e o
# node (Homebrew) e o yt-dlp (instalado pelo pip do Python.org) ficam de fora
# e o painel falhava com "No such file or directory: 'yt-dlp'". Pela linha de
# comando funcionava, porque o terminal tem o PATH completo. Completar aqui,
# antes de qualquer subprocess, vale para os dois jeitos de subir.
_PASTAS_DE_FERRAMENTAS = [
    str(Path(sys.executable).resolve().parent),  # yt-dlp do mesmo Python
    "/Library/Frameworks/Python.framework/Versions/3.13/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
]
_path = os.environ.get("PATH", "").split(os.pathsep)
os.environ["PATH"] = os.pathsep.join(
    [p for p in _PASTAS_DE_FERRAMENTAS if p not in _path] + _path
)

# ---------------------------------------------------------------- caminhos
RAIZ = Path(__file__).resolve().parent.parent          # .../estudio
ARTES = RAIZ / "artes"
ASSETS = RAIZ / "assets"
WEB = RAIZ / "web"
DADOS = RAIZ / "dados"
CONFIG = DADOS / "config.json"

# Os vídeos ficam FORA do Google Drive de propósito: um culto de 1h40 em 1080p
# passa de 1 GB e subiria para a nuvem a cada download. Aqui fica só local.
# No Mac a pasta de vídeos é ~/Movies; no Windows e no Linux, ~/Videos.
_VIDEOS = Path.home() / ("Movies" if sys.platform == "darwin" else "Videos")
CASA = _VIDEOS / "Estudio IPOB"
TRABALHO = CASA / "trabalho"     # downloads e transcrições (pode apagar)
# Os vídeos prontos ficam organizados por formato, estudo e episódio:
#   Vídeos Editados / Culto Noturno / JOÃO / 03 - 2026-10-05 - A Palavra se fez carne /
# com o MP4 final e os Shorts na mesma pasta. A pasta antiga ("saida", uma
# pasta por vídeo) continua sendo lida pela biblioteca.
# Os prontos também ficam fora do Drive (decisão do Henrique, 01/10/2026):
# depois de subir para o YouTube eles são apagados, não vale sincronizar.
# Para mudar: padroes.pasta_dos_editados na config (caminho absoluto).
def _pasta_dos_editados() -> Path:
    try:
        escolha = json.loads(CONFIG.read_text(encoding="utf-8"))["padroes"].get("pasta_dos_editados")
        if escolha:
            return Path(escolha).expanduser()
    except (OSError, ValueError, KeyError):
        pass
    return CASA / "Vídeos Editados"


SAIDA = _pasta_dos_editados()
SAIDA_ANTIGA = CASA / "saida"

for _p in (TRABALHO, SAIDA):
    _p.mkdir(parents=True, exist_ok=True)

# Onde o Google Chrome costuma estar em cada sistema. Se não houver nenhum,
# o Playwright usa o Chromium que o instalador baixa (ver artes.navegador()).
_CHROMES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"),
    "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium",
]
CHROME = next((c for c in _CHROMES if Path(c).exists()), _CHROMES[0])
WINDOWS = sys.platform.startswith("win")
MAC = sys.platform == "darwin"


def chromium_do_playwright() -> bool:
    """O Chromium baixado por `playwright install chromium` existe?"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


def abrir_no_sistema(caminho: str, revelar: bool = False) -> None:
    """Abre pasta/arquivo no Finder, Explorer ou gerenciador do sistema."""
    if MAC:
        subprocess.run(["open", "-R", caminho] if revelar else ["open", caminho])
    elif WINDOWS:
        if revelar:
            subprocess.run(["explorer", "/select,", caminho])
        else:
            os.startfile(caminho)  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", caminho])


# ------------------------------------------------------------------ config
def ler_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def gravar_config(cfg: dict) -> None:
    CONFIG.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ------------------------------------------------------------- utilidades
def hms(segundos: float) -> str:
    """123.4 -> '00:02:03'"""
    s = max(0, int(round(segundos)))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def para_segundos(texto: str) -> float:
    """'00:42:15' ou '42:15' ou '2535' -> 2535.0"""
    texto = str(texto).strip().replace(",", ".")
    if not texto:
        return 0.0
    partes = texto.split(":")
    try:
        partes = [float(x) for x in partes]
    except ValueError:
        return 0.0
    total = 0.0
    for parte in partes:
        total = total * 60 + parte
    return total


def nome_de_arquivo(texto: str) -> str:
    """Transforma um título em algo que o Finder aceita."""
    texto = re.sub(r"[\\/:*?\"<>|]", "-", str(texto))
    texto = re.sub(r"\s+", " ", texto).strip(" .-")
    return texto[:120] or "sem-nome"


# O processo externo (ffmpeg, yt-dlp) que cada thread está rodando agora.
# É o que o botão "Parar" mata: interromper só a thread Python deixaria o
# ffmpeg vivo escrevendo no arquivo.
import threading as _threading
PROCESSOS: dict[int, subprocess.Popen] = {}
CANCELADAS: set[int] = set()


class Cancelado(RuntimeError):
    pass


def cancelar_thread(ident: int) -> bool:
    """Marca a thread como cancelada e mata o que ela estiver rodando."""
    CANCELADAS.add(ident)
    proc = PROCESSOS.get(ident)
    if proc and proc.poll() is None:
        proc.terminate()
        return True
    return False


def _checar_cancelamento():
    if _threading.get_ident() in CANCELADAS:
        CANCELADAS.discard(_threading.get_ident())
        raise Cancelado("Parado por você.")


def rodar(cmd: list[str], ao_vivo=None, **kw) -> subprocess.CompletedProcess:
    """Roda um comando repassando cada linha de saída para `ao_vivo`."""
    _checar_cancelamento()
    ident = _threading.get_ident()
    if ao_vivo is None:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, **kw)
        PROCESSOS[ident] = proc
        try:
            out, err = proc.communicate()
        finally:
            PROCESSOS.pop(ident, None)
        _checar_cancelamento()
        return subprocess.CompletedProcess(cmd, proc.returncode, out, err)

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, **kw
    )
    PROCESSOS[ident] = proc
    linhas = []
    try:
        for linha in proc.stdout:
            linha = linha.rstrip()
            linhas.append(linha)
            ao_vivo(linha)
        proc.wait()
    finally:
        PROCESSOS.pop(ident, None)
    _checar_cancelamento()
    return subprocess.CompletedProcess(cmd, proc.returncode, "\n".join(linhas), "")


def ferramenta(nome: str) -> str | None:
    if nome == "yt-dlp" and not shutil.which(nome):
        try:
            import yt_dlp  # noqa: F401
            return "python -m yt_dlp"
        except ImportError:
            return None
    return shutil.which(nome)


def checar_ambiente() -> list[dict]:
    """O painel mostra isso na primeira tela."""
    itens = []
    dica_ffmpeg = "winget install Gyan.FFmpeg" if WINDOWS else "brew install ffmpeg"
    for nome, dica in (
        ("ffmpeg", dica_ffmpeg),
        ("yt-dlp", "pip install -U yt-dlp"),
    ):
        itens.append({"nome": nome, "ok": bool(ferramenta(nome)), "dica": dica})
    itens.append({
        "nome": "Google Chrome",
        "ok": Path(CHROME).exists() or chromium_do_playwright(),
        "dica": "necessário para gerar capa e tarja (ou rode: playwright install chromium)",
    })
    return itens
