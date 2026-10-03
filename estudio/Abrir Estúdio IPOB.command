#!/bin/zsh
# Clique duas vezes para abrir o Estúdio IPOB.
# Pode clicar quantas vezes quiser. Se já estiver no ar com a versão certa,
# só abre o navegador; se o programa mudou, reinicia; se caiu, sobe.
# Com o serviço do macOS instalado ("Ligar sozinho ao iniciar o Mac"), o
# reinício é pedido ao launchd, que é quem cuida do processo.

# funciona também pelo atalho da Mesa (link simbólico criado pelo instalador)
ORIGEM="$0"; [ -L "$ORIGEM" ] && ORIGEM="$(readlink "$ORIGEM")"
cd "$(dirname "$ORIGEM")" || exit 1

PORTA=4747
SERVICO="br.ipob.estudio"
LOG="$HOME/Library/Logs/estudio-ipob.log"
mkdir -p "$(dirname "$LOG")"

versao_no_ar() {
  curl -s --max-time 3 "http://localhost:$PORTA/api/config" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin).get("_versao",""))' 2>/dev/null
}
tem_servico() { launchctl print "gui/$(id -u)/$SERVICO" >/dev/null 2>&1; }
esperar_subir() {
  for i in {1..40}; do
    [[ "$(versao_no_ar)" == "$1" ]] && return 0
    sleep 0.5
  done
  return 1
}

VERSAO_ARQUIVO=$(grep -m1 '^VERSAO' painel.py | cut -d'"' -f2)

if lsof -ti:$PORTA >/dev/null 2>&1; then
  if [[ -n "$VERSAO_ARQUIVO" && "$(versao_no_ar)" == "$VERSAO_ARQUIVO" ]]; then
    echo "O Estúdio já estava no ar. Abrindo o navegador…"
    open "http://localhost:$PORTA"
    echo; echo "Pode fechar esta janela."
    exit 0
  fi
  echo "O programa mudou (no ar: $(versao_no_ar); arquivo: $VERSAO_ARQUIVO). Reiniciando…"
  if tem_servico; then
    launchctl kickstart -k "gui/$(id -u)/$SERVICO"
  else
    lsof -ti:$PORTA | xargs kill 2>/dev/null
    sleep 1
  fi
fi

if tem_servico; then
  # o serviço cuida do processo: só esperamos ele responder
  launchctl kickstart "gui/$(id -u)/$SERVICO" 2>/dev/null
  if esperar_subir "$VERSAO_ARQUIVO"; then
    echo "Estúdio no ar pelo serviço do macOS. Abrindo o navegador…"
    open "http://localhost:$PORTA"
    echo; echo "Pode fechar esta janela."
    exit 0
  fi
  echo "O serviço não respondeu; veja $LOG. Subindo à mão…"
fi

echo "Abrindo o Estúdio IPOB em http://localhost:$PORTA"
echo "Vídeos prontos em: $(dirname "$PWD")/Vídeos Editados"
echo
echo "Deixe esta janela aberta enquanto usar. Para desligar, feche-a."
echo "----------------------------------------------------------------"
exec python3 painel.py --esperar-porta 2>&1 | tee -a "$LOG"
