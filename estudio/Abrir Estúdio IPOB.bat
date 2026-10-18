@echo off
chcp 65001 >nul
title Estúdio IPOB - deixe esta janela aberta enquanto usa
cd /d "%~dp0"
rem programas instalados pelo winget nesta mesma sessão ainda não estão no PATH
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
echo.
echo   Estúdio IPOB abrindo em http://localhost:4747
echo   Deixe esta janela aberta. Para fechar o Estúdio, feche esta janela.
echo.
rem abre o navegador alguns segundos depois, quando o painel já está no ar
start "" /b cmd /c "timeout /t 4 >nul & start http://localhost:4747"
python painel.py --sem-navegador
echo.
echo   O Estúdio parou. Se apareceu um erro acima, tire um print e mande para o Henrique.
pause
