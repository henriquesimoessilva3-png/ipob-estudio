"""Monta o vídeo final com ffmpeg.

Estrutura da saída, igual à que você fazia no Filmora:
    [ capa parada, com fade ]  →  [ trecho da pregação, com a tarja fixa ]
O áudio entra com fade-in para não estourar no corte.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import ferramenta, rodar

_TEMPO = re.compile(r"out_time_ms=(\d+)")

# O YouTube normaliza o som para perto de -14 LUFS, mas só ABAIXA o que está
# alto — nunca levanta o que está baixo. As transmissões da igreja chegam por
# volta de -34 LUFS, ou seja, 20 dB abaixo: publicado assim, o vídeo toca
# baixo demais e o pessoal precisa forçar o volume.
ALVO_LUFS = -14.0
PICO_MAXIMO = -1.5      # dBTP, folga para não estourar na conversão

# Limpeza antes de normalizar. O som da igreja vem com zumbido grave da mesa
# e ruído de fundo constante; levantar 20 dB sem limpar levanta isso junto.
#   highpass  — corta o ronco abaixo da voz
#   afftdn    — reduz o ruído de fundo constante (ventilador, chiado)
#   acompressor — aproxima as partes baixas das altas, para a fala ficar
#                 inteligível sem precisar forçar o volume
# A mesma cadeia é usada para medir e para corrigir, senão a medida não bate.
# Com o modelo RNNoise (assets/audio/rnnoise-voz.rnnn) o resultado é bem
# melhor: no culto de 27/09 o ruído nas pausas caiu 8 dB a mais que com o
# afftdn sozinho, e a voz ficou mais presente. O arnndn é filtro nativo do
# ffmpeg (não precisa de biblioteca), só precisa do arquivo do modelo.
# A equalização tira a "lama" de 250–500 Hz (ruído de sala) e devolve
# presença em 3 kHz, que a transmissão quase não tem.
from .base import ASSETS as _ASSETS
MODELO_RNN = _ASSETS / "audio" / "rnnoise-voz.rnnn"
_COMPRESSOR = "acompressor=threshold=-26dB:ratio=2.5:attack=20:release=300:makeup=3"
def _tem_filtro(nome: str) -> bool:
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        return False
    try:
        saida = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                               capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return f" {nome} " in saida


if MODELO_RNN.exists() and _tem_filtro("arnndn"):
    LIMPEZA = (f"highpass=f=90,arnndn=m='{MODELO_RNN}':mix=0.9,afftdn=nf=-40:nr=10:tn=1,"
               f"equalizer=f=350:t=q:w=1.2:g=-4,equalizer=f=3000:t=q:w=1:g=3,{_COMPRESSOR}")
else:
    LIMPEZA = f"highpass=f=70,lowpass=f=14000,afftdn=nf=-30:nr=10:tn=1,{_COMPRESSOR}"


def cadeia_de_audio(limpar: bool) -> str:
    """Prefixo da cadeia de filtros de áudio (vazio ou LIMPEZA + vírgula)."""
    return f"{LIMPEZA}," if limpar else ""


def medir_loudness(fonte: Path, inicio: float, duracao: float,
                   limpar: bool = True) -> dict | None:
    """Mede o som do trecho antes de renderizar.

    Medir e depois corrigir com ganho constante (duas passadas) soa melhor que
    corrigir na hora: numa pregação de uma hora, o ajuste dinâmico bombeia o
    volume nas pausas.
    """
    r = rodar([
        "ffmpeg", "-hide_banner", "-nostats",
        "-ss", f"{inicio:.3f}", "-t", f"{duracao:.3f}", "-i", str(fonte),
        "-af", f"{cadeia_de_audio(limpar)}loudnorm=I={ALVO_LUFS}:TP={PICO_MAXIMO}:LRA=11:print_format=json",
        "-f", "null", "-",
    ])
    saida = (r.stdout or "") + (r.stderr or "")
    try:
        bruto = saida[saida.rindex("{"): saida.rindex("}") + 1]
        import json
        d = json.loads(bruto)
        if d.get("input_i") in (None, "-inf", "inf"):
            return None
        return d
    except (ValueError, KeyError):
        return None


def duracao_de(caminho: Path) -> float:
    r = rodar(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(caminho)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def taxa_de_quadros(caminho: Path) -> str:
    """'30/1', '30000/1001'… — a taxa do vídeo, como o ffmpeg escreve."""
    r = rodar(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0",
               str(caminho)])
    taxa = (r.stdout or "").strip().splitlines()
    taxa = taxa[0].strip() if taxa else ""
    try:
        num, den = (float(x) for x in taxa.split("/"))
        if 10 <= num / den <= 120:
            return taxa
    except (ValueError, ZeroDivisionError):
        pass
    return "30"


def montar(fonte: Path, capa: Path, tarja: Path, destino: Path,
           inicio: float, fim: float,
           segundos_de_capa: float = 5.0,
           fade_da_capa: float = 0.6,
           fade_do_audio: float = 1.0,
           aceleracao: bool = True,
           bitrate: str = "6M",
           normalizar_audio: bool = True,
           limpar_audio: bool = True,
           progresso=None) -> Path:
    """Renderiza e devolve o caminho do MP4."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    trecho = max(1.0, fim - inicio)
    total = segundos_de_capa + trecho
    saida_capa = max(0.0, segundos_de_capa - fade_da_capa)

    limpar = normalizar_audio and limpar_audio
    medida = medir_loudness(fonte, inicio, trecho, limpar) if normalizar_audio else None
    if medida:
        corrigir = (
            f",{cadeia_de_audio(limpar)}loudnorm=I={ALVO_LUFS}:TP={PICO_MAXIMO}:LRA=11:linear=true"
            f":measured_I={medida['input_i']}:measured_TP={medida['input_tp']}"
            f":measured_LRA={medida['input_lra']}"
            f":measured_thresh={medida['input_thresh']}"
            f":offset={medida['target_offset']}"
        )
    else:
        corrigir = ""

    # A capa (uma imagem) e a transmissão precisam ter a mesma taxa de quadros
    # antes do concat. Sem isso a capa entra a 25 fps e a pregação a 30: o
    # arquivo sai com taxa variável, e o ffmpeg 4 chega a travar no concat
    # (reproduzido em 01/10/2026 — fica rodando sem gravar nada).
    fps = taxa_de_quadros(fonte)

    filtro = (
        f"[0:v]scale=1920:1080,setsar=1,fps={fps},"
        f"fade=t=in:st=0:d={fade_da_capa},"
        f"fade=t=out:st={saida_capa:.2f}:d={fade_da_capa},format=yuv420p[capa];"

        f"[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[base];"

        f"[2:v]scale=1920:1080[tar];"
        f"[base][tar]overlay=0:0:format=auto,format=yuv420p[corpo];"

        f"[3:a]afade=t=out:st={saida_capa:.2f}:d={fade_da_capa}[silencio];"
        f"[1:a]aresample=48000{corrigir},aresample=48000,"
        f"afade=t=in:st=0:d={fade_do_audio}[fala];"

        f"[capa][silencio][corpo][fala]concat=n=2:v=1:a=1[v][a]"
    )

    # A transmissão do YouTube vem em ~1,5 Mbps. O bitrate vem da config
    # (hoje 3M, o dobro da fonte): folga de sobra, sem arquivos de 3 GB à toa.
    if aceleracao and "videotoolbox" in (rodar(["ffmpeg", "-hide_banner", "-encoders"]).stdout or ""):
        video = ["-c:v", "h264_videotoolbox", "-b:v", bitrate, "-profile:v", "high"]
    else:
        video = ["-c:v", "libx264", "-crf", "20", "-preset", "medium"]

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-loop", "1", "-t", f"{segundos_de_capa}", "-i", str(capa),
        "-ss", f"{inicio:.3f}", "-t", f"{trecho:.3f}", "-i", str(fonte),
        "-i", str(tarja),
        "-f", "lavfi", "-t", f"{segundos_de_capa}",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-filter_complex", filtro,
        "-map", "[v]", "-map", "[a]",
        *video,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        str(destino),
    ]

    def ao_vivo(linha: str):
        if progresso is None:
            return
        m = _TEMPO.search(linha)
        if m:
            feito = int(m.group(1)) / 1_000_000
            progresso(min(0.999, feito / total) if total else 0.0)

    r = rodar(cmd, ao_vivo=ao_vivo)
    if r.returncode != 0 or not destino.exists():
        cauda = "\n".join(r.stdout.splitlines()[-25:])
        raise RuntimeError(f"O ffmpeg falhou.\n{cauda}")
    if progresso:
        progresso(1.0)
    return destino
