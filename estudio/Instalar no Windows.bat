@echo off
chcp 65001 >nul
title Estúdio IPOB - instalação
cd /d "%~dp0"
set "PASTA=%~dp0"
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
echo.
echo   Estúdio IPOB - instalação
echo   =========================
echo.

where winget >nul 2>&1 || (
  echo   Este Windows não tem o winget. Abra a Microsoft Store, procure "Instalador de Aplicativo",
  echo   atualize e rode este instalador de novo.
  pause & exit /b 1
)

rem "python" pode ser só o atalho da Microsoft Store, que não funciona: testa de verdade
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 (
  echo   [1/4] Instalando o Python...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --silent
  python -c "import sys" >nul 2>&1 || (
    echo.
    echo   Python instalado. FECHE esta janela e dê dois cliques de novo em "Instalar no Windows".
    pause & exit /b 0
  )
) else (
  echo   [1/4] Python já instalado.
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo   [2/4] Instalando o ffmpeg...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements --silent
) else (
  echo   [2/4] ffmpeg já instalado.
)

echo   [3/4] Instalando as bibliotecas (pode levar alguns minutos)...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo   Algo falhou nas bibliotecas. Tire um print desta janela e mande para o Henrique.
  pause & exit /b 1
)

if not exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" if not exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" if not exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
  echo   Baixando o navegador usado para gerar capa e tarja...
  python -m playwright install chromium
)

echo   [4/4] Criando o atalho na Área de Trabalho...
set "ATALHO=%USERPROFILE%\Desktop\Abrir Estúdio IPOB.bat"
if exist "%USERPROFILE%\OneDrive\Desktop" set "ATALHO=%USERPROFILE%\OneDrive\Desktop\Abrir Estúdio IPOB.bat"
if exist "%USERPROFILE%\OneDrive\Área de Trabalho" set "ATALHO=%USERPROFILE%\OneDrive\Área de Trabalho\Abrir Estúdio IPOB.bat"
(
  echo @echo off
  echo call "%PASTA%Abrir Estúdio IPOB.bat"
) > "%ATALHO%"

echo.
echo   Pronto! Para usar, dê dois cliques em "Abrir Estúdio IPOB" na Área de Trabalho.
echo   Os vídeos prontos ficam em Vídeos\Estudio IPOB\Vídeos Editados.
echo.
pause
call "%PASTA%Abrir Estúdio IPOB.bat"
