"""Publica o vídeo no canal pela API do YouTube.

O que faz, em ordem: sobe o MP4, define a miniatura, manda a legenda e joga o
vídeo na playlist da série.

DUAS COISAS PARA SABER ANTES DE USAR

1. Precisa de uma credencial OAuth criada por você no Google Cloud. O painel
   explica o passo a passo. Conta de serviço não funciona para upload no
   YouTube — tem que ser do tipo "App para computador".

2. Projeto de API que não passou pela auditoria de conformidade do Google sobe
   o vídeo travado como PRIVADO, ignorando a privacidade pedida aqui. Nesse
   caso o Estúdio economiza o upload e os textos, mas a publicação final
   continua sendo no Studio. O painel avisa quando isso acontece.

Nada aqui roda sozinho: só quando você clica no botão.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .base import CASA

# escopo mínimo: subir vídeo, miniatura, legenda e mexer nas playlists do canal
ESCOPOS = ["https://www.googleapis.com/auth/youtube"]

CREDENCIAIS = CASA / "credenciais"          # fora do Google Drive, de propósito
CLIENT_SECRET = CREDENCIAIS / "client_secret.json"
TOKEN = CREDENCIAIS / "token.json"

CATEGORIA_NONPROFITS = "29"


class ErroUpload(RuntimeError):
    pass


def configurado() -> bool:
    return CLIENT_SECRET.exists()


def conectado() -> bool:
    return TOKEN.exists()


def _simples(t: str) -> str:
    """Compara nome de playlist sem tropeçar em acento ou maiúscula."""
    t = unicodedata.normalize("NFKD", (t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", t)


def servico():
    """Devolve o cliente da API, pedindo o login no navegador se preciso."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    if not CLIENT_SECRET.exists():
        raise ErroUpload(
            f"Falta a credencial do Google. Coloque o arquivo client_secret.json "
            f"em {CREDENCIAIS} — o painel mostra como obtê-lo."
        )

    cred = None
    if TOKEN.exists():
        try:
            cred = Credentials.from_authorized_user_file(str(TOKEN), ESCOPOS)
        except Exception:
            cred = None

    if not cred or not cred.valid:
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        else:
            fluxo = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET), ESCOPOS)
            cred = fluxo.run_local_server(
                port=0, prompt="consent",
                authorization_prompt_message=
                "Abrindo o navegador para você entrar na conta do canal…",
                success_message=
                "Pronto. Pode fechar esta aba e voltar ao Estúdio IPOB.",
            )
        CREDENCIAIS.mkdir(parents=True, exist_ok=True)
        TOKEN.write_text(cred.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=cred, cache_discovery=False)


def _explicar(e: Exception) -> str:
    texto = str(e)
    if "quotaExceeded" in texto:
        return ("A cota diária da API do YouTube acabou. Ela zera à meia-noite "
                "no horário do Pacífico. Suba este pelo Studio.")
    if "youtubeSignupRequired" in texto:
        return "A conta que você autorizou não tem um canal do YouTube."
    if "forbidden" in texto.lower() or "insufficientPermissions" in texto:
        return ("A conta autorizada não tem permissão neste canal. Entre com a "
                "conta dona do canal — apague o token.json para trocar de conta.")
    if "invalid_grant" in texto:
        return ("A autorização expirou. Apague o token.json em "
                f"{CREDENCIAIS} e conecte de novo.")
    return texto[:500]


# --------------------------------------------------------------------- upload
def enviar(video: Path, titulo: str, descricao: str,
           miniatura: Path | None = None,
           legenda_srt: Path | None = None,
           playlist: str = "",
           privacidade: str = "unlisted",
           categoria: str = CATEGORIA_NONPROFITS,
           progresso=None, recado=None) -> dict:
    """Sobe tudo e devolve {'id', 'url', 'privacidade', 'avisos': [...]}."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    def diga(msg: str):
        if recado:
            recado(msg)

    yt = servico()
    avisos: list[str] = []

    corpo = {
        "snippet": {
            "title": titulo[:100],
            "description": descricao[:5000],
            "categoryId": categoria,
        },
        "status": {
            "privacyStatus": privacidade,
            "selfDeclaredMadeForKids": False,
        },
    }

    diga("Enviando o vídeo…")
    midia = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True)
    try:
        pedido = yt.videos().insert(part="snippet,status", body=corpo, media_body=midia)
        resposta = None
        while resposta is None:
            estado, resposta = pedido.next_chunk()
            if estado and progresso:
                progresso(estado.progress())
    except HttpError as e:
        raise ErroUpload(_explicar(e)) from e

    vid = resposta["id"]
    real = resposta.get("status", {}).get("privacyStatus", privacidade)
    if real != privacidade:
        avisos.append(
            f"O YouTube forçou a privacidade para “{real}”. Isso acontece em "
            f"projeto de API sem a auditoria de conformidade do Google — o "
            f"vídeo subiu, mas a publicação final é no Studio."
        )

    if miniatura and miniatura.exists():
        diga("Definindo a miniatura…")
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(miniatura))).execute()
        except HttpError as e:
            avisos.append("Miniatura não aplicada: " + _explicar(e))

    if legenda_srt and legenda_srt.exists():
        diga("Enviando a legenda…")
        try:
            yt.captions().insert(
                part="snippet",
                body={"snippet": {"videoId": vid, "language": "pt-BR",
                                  "name": "Português", "isDraft": False}},
                media_body=MediaFileUpload(str(legenda_srt)),
            ).execute()
        except HttpError as e:
            avisos.append("Legenda não enviada: " + _explicar(e))

    if playlist:
        diga("Jogando na playlist…")
        try:
            pid = achar_playlist(yt, playlist)
            if pid:
                yt.playlistItems().insert(
                    part="snippet",
                    body={"snippet": {"playlistId": pid,
                                      "resourceId": {"kind": "youtube#video", "videoId": vid}}},
                ).execute()
            else:
                avisos.append(
                    f"Não achei a playlist “{playlist}” no canal. O vídeo subiu; "
                    f"é só arrastar para a playlist no Studio (ou criá-la)."
                )
        except HttpError as e:
            avisos.append("Playlist: " + _explicar(e))

    return {"id": vid, "url": f"https://youtu.be/{vid}",
            "privacidade": real, "avisos": avisos}


def achar_playlist(yt, nome: str) -> str | None:
    """Procura pelo nome, ignorando acento e maiúscula. Não cria nada."""
    alvo = _simples(nome)
    pagina = None
    while True:
        r = yt.playlists().list(part="snippet", mine=True, maxResults=50,
                                pageToken=pagina).execute()
        for item in r.get("items", []):
            if _simples(item["snippet"]["title"]) == alvo:
                return item["id"]
        pagina = r.get("nextPageToken")
        if not pagina:
            return None


def testar() -> dict:
    """Confere a credencial sem publicar nada.

    Só pergunta ao YouTube qual canal a conta autorizada controla. Serve para
    você descobrir que a configuração está errada ANTES de esperar meia hora
    de upload — e para conferir que autorizou a conta certa, não a pessoal.
    """
    from googleapiclient.errors import HttpError

    try:
        yt = servico()
        r = yt.channels().list(part="snippet,contentDetails", mine=True).execute()
    except HttpError as e:
        raise ErroUpload(_explicar(e)) from e

    itens = r.get("items", [])
    if not itens:
        raise ErroUpload("A conta autorizada não tem um canal do YouTube. "
                         "Entre com a conta que administra o canal da igreja.")

    canal = itens[0]["snippet"]
    playlists = []
    pagina = None
    while True:
        pl = yt.playlists().list(part="snippet", mine=True, maxResults=50,
                                 pageToken=pagina).execute()
        playlists += [i["snippet"]["title"] for i in pl.get("items", [])]
        pagina = pl.get("nextPageToken")
        if not pagina:
            break

    return {"canal": canal.get("title", ""), "playlists": sorted(playlists)}


def esquecer() -> bool:
    """Desconecta a conta apagando o token."""
    if TOKEN.exists():
        TOKEN.unlink()
        return True
    return False
