@echo off
chcp 65001 >nul
title Estúdio IPOB
cd /d "%~dp0"
if not exist painel.py cd /d "%USERPROFILE%\Estudio IPOB\app\estudio"
start "" http://localhost:4747
python painel.py --sem-navegador
pause
