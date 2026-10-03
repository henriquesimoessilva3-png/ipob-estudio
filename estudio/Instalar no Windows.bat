@echo off
chcp 65001 >nul
title Estúdio IPOB — instalação
cd /d "%~dp0"
echo.
echo   Estúdio IPOB — instalação
echo   =========================

where winget >nul 2>&1 || (echo   Este Windows nao tem o winget. Atualize o Windows ^(App Installer na Microsoft Store^) e rode de novo. & pause & exit /b 1)

where python >nul 2>&1 || (
  echo   Instalando o Python...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
  echo   Python instalado. FECHE esta janela e rode o instalador de novo para ele ser reconhecido.
  pause & exit /b 0
)

where ffmpeg >nul 2>&1 || (
  echo   Instalando o ffmpeg...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements --silent
)

echo   Instalando as bibliotecas Python...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt

if not exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" if not exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
  echo   Baixando o navegador usado para gerar capa e tarja...
  python -m playwright install chromium
)

echo   Criando o atalho na Area de Trabalho...
copy /y "Abrir Estúdio IPOB.bat" "%USERPROFILE%\Desktop\Abrir Estúdio IPOB.bat" >nul

echo.
echo   Pronto. Para usar, de dois cliques em "Abrir Estúdio IPOB" na Area de Trabalho.
echo   (Os videos ficam em Videos\Estudio IPOB.)
echo   Se o ffmpeg nao for reconhecido na primeira vez, feche e abra o atalho de novo.
pause
call "Abrir Estúdio IPOB.bat"
