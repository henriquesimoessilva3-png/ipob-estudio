@echo off
chcp 65001 >nul
title Estúdio IPOB - instalador
rem Instalador de um arquivo só: baixa o Estúdio do GitHub, guarda numa pasta
rem fixa (C:\Users\<nome>\Estudio IPOB) e roda a instalação. Rodar de novo
rem atualiza o programa sem mexer nos estudos e nos vídeos.
set "DESTINO=%USERPROFILE%\Estudio IPOB"
set "ZIP=%TEMP%\ipob-estudio.zip"
set "TMPDIR=%TEMP%\ipob-estudio"
echo.
echo   Estúdio IPOB - baixando a versão mais nova...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; Remove-Item -Recurse -Force $env:TEMP\ipob-estudio -ErrorAction SilentlyContinue; Invoke-WebRequest 'https://github.com/henriquesimoessilva3-png/ipob-estudio/archive/refs/heads/main.zip' -OutFile (Join-Path $env:TEMP 'ipob-estudio.zip'); Expand-Archive -Force (Join-Path $env:TEMP 'ipob-estudio.zip') (Join-Path $env:TEMP 'ipob-estudio')"
if not exist "%TMPDIR%\ipob-estudio-main\estudio\painel.py" (
  echo   Não consegui baixar. Confira a internet e tente de novo.
  echo   Se continuar, tire um print desta janela e mande para o Henrique.
  pause & exit /b 1
)
echo   Copiando para %DESTINO% ...
robocopy "%TMPDIR%\ipob-estudio-main\estudio" "%DESTINO%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
  echo   Não consegui copiar os arquivos. Feche o Estúdio se estiver aberto e tente de novo.
  pause & exit /b 1
)
del /q "%ZIP%" >nul 2>&1
rmdir /s /q "%TMPDIR%" >nul 2>&1
call "%DESTINO%\Instalar no Windows.bat"
