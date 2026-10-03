#!/bin/zsh
# Instalador do Estúdio IPOB para Mac.
# Dê dois cliques. Se o macOS reclamar, clique com o botão direito → Abrir.
set -e
cd "$(dirname "$0")"
echo ""
echo "  Estúdio IPOB — instalação"
echo "  ========================="

# 1) Python 3 (vem com as ferramentas de linha de comando da Apple)
if ! command -v python3 >/dev/null; then
  echo "  Instalando as ferramentas da Apple (Python)… aceite a janela que abrir."
  xcode-select --install || true
  echo "  Quando terminar, rode este instalador de novo."; read -k1; exit 0
fi

# 2) Homebrew + ffmpeg
if ! command -v brew >/dev/null; then
  echo "  Instalando o Homebrew (gerenciador de programas)…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
fi
command -v ffmpeg >/dev/null || brew install ffmpeg

# 3) Bibliotecas Python
echo "  Instalando as bibliotecas Python…"
python3 -m pip install --user --upgrade pip >/dev/null
python3 -m pip install --user -r requirements.txt

# 4) Navegador para gerar capa e tarja (usa o Chrome se já houver)
[ -d "/Applications/Google Chrome.app" ] || python3 -m playwright install chromium

# 5) Atalho na Mesa
ln -sf "$PWD/Abrir Estúdio IPOB.command" "$HOME/Desktop/Abrir Estúdio IPOB.command"
chmod +x "Abrir Estúdio IPOB.command"
echo ""
echo "  Pronto. Para usar, dê dois cliques em 'Abrir Estúdio IPOB' na Mesa."
echo "  (Os vídeos ficam em ~/Movies/Estudio IPOB.)"
open "http://localhost:4747" 2>/dev/null || true
"./Abrir Estúdio IPOB.command"
