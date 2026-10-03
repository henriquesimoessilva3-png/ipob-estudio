"""Aprende com os cortes que você faz na mão.

O palpite de onde a pregação começa e quanto sobra no fim vem de dois números:
em que fração da transmissão a Palavra costuma abrir, e quantos segundos de
encerramento você corta. Chutar esses números é pior do que observar os seus
cortes de verdade — então cada vídeo produzido vira uma medida.

Usa a mediana, não a média: um domingo atípico (uma ceia, uma apresentação
longa antes da pregação) não puxa o palpite da semana seguinte.

Cada formato aprende sozinho. A EBD e o culto têm estruturas diferentes — a
aula começa por volta de 25% da transmissão, a pregação perto de 40% — e uma
mediana só, misturando os dois, errava os dois.

Reeditar o mesmo vídeo substitui a medida dele em vez de somar outra: senão
um culto reprocessado três vezes valia três votos.
"""
from __future__ import annotations

MEMORIA = 12          # quantos cortes recentes contam, por formato
MINIMO = 2            # abaixo disso não vale ajustar nada


def _mediana(valores: list[float]) -> float:
    v = sorted(valores)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _do_formato(memoria: list[dict], formato: str) -> list[dict]:
    """As medidas deste formato.

    As medidas antigas não guardam o formato (foram gravadas antes desta
    correção). Elas só entram enquanto o formato ainda não tem medidas
    próprias suficientes — depois, saem da conta.
    """
    proprias = [c for c in memoria if c.get("formato") == formato]
    if len(proprias) >= MINIMO:
        return proprias[-MEMORIA:]
    antigas = [c for c in memoria if not c.get("formato")]
    return (antigas + proprias)[-MEMORIA:]


def palpite(cfg: dict, formato: str) -> dict:
    """O centro e a sobra que valem para este formato agora."""
    busca = cfg.get("busca_do_corte", {})
    fmt = cfg.get("formatos", {}).get(formato, {})
    return {
        "centro": fmt.get("centro_aprendido", busca.get("centro", 0.46)),
        "sobra": fmt.get("sobra_aprendida",
                         cfg.get("padroes", {}).get("sobra_no_final", 8)),
    }


def registrar(cfg: dict, duracao: float, inicio: float, fim: float,
              formato: str = "", video_id: str = "") -> dict:
    """Guarda um corte e recalcula os palpites do formato. Devolve o que mudou."""
    if duracao <= 0 or fim <= inicio:
        return {}

    memoria = cfg.setdefault("aprendizado", {}).setdefault("cortes", [])
    if video_id:
        memoria[:] = [c for c in memoria
                      if not (c.get("video_id") == video_id
                              and c.get("formato") == formato)]
    memoria.append({
        "formato": formato,
        "video_id": video_id,
        "duracao": round(duracao, 1),
        "fracao_inicio": round(inicio / duracao, 4),
        "sobra_fim": round(max(0.0, duracao - fim), 1),
    })

    # guarda as últimas MEMORIA de cada formato, sem que um empurre o outro
    # para fora da lista
    contagem: dict[str, int] = {}
    manter = []
    for c in reversed(memoria):
        f = c.get("formato", "")
        contagem[f] = contagem.get(f, 0) + 1
        if contagem[f] <= MEMORIA:
            manter.append(c)
    memoria[:] = list(reversed(manter))

    usadas = _do_formato(memoria, formato)
    if len(usadas) < MINIMO:
        return {"cortes": len(usadas)}

    centro = round(_mediana([c["fracao_inicio"] for c in usadas]), 4)
    sobra = round(_mediana([c["sobra_fim"] for c in usadas]), 1)

    fmt = cfg.get("formatos", {}).get(formato)
    if fmt is not None:
        fmt["centro_aprendido"] = centro
        fmt["sobra_aprendida"] = sobra
    return {"cortes": len(usadas), "centro": centro, "sobra": sobra}
