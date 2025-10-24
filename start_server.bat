@echo off
REM RawCandle Server Startup Script for Windows
REM Käynnistää sovelluksen virtuaaliympäristössä portissa 8888

setlocal enabledelayedexpansion

echo 🚀 RawCandle Server Käynnistys
echo ==============================

REM Projektin hakemisto (muuta tämä tarvittaessa)
set PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"

echo 📁 Projektihakemisto: %PROJECT_DIR%

REM Varmista että olemme oikeassa hakemistossa
if not exist "main.py" (
    echo ❌ Virhe: main.py ei löydy hakemistosta %PROJECT_DIR%
    pause
    exit /b 1
)

REM Varmista että virtuaaliympäristö on olemassa
if not exist "venv" (
    echo ❌ Virhe: Virtuaaliympäristö ei löydy hakemistosta %PROJECT_DIR%venv
    pause
    exit /b 1
)

echo 🐍 Virtuaaliympäristö: %PROJECT_DIR%venv

REM Vapaa portti 8888 (tappa kaikki prosessit jotka käyttävät sitä)
echo 🔌 Vapautetaan portti 8888...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8888') do (
    echo    Tapetaan prosessi %%a...
    taskkill /f /pid %%a >nul 2>&1
)

REM Tappa mahdolliset aiemmat main.py prosessit
echo 🛑 Tapetaan mahdolliset aiemmat RawCandle prosessit...
taskkill /f /im python.exe /fi "WINDOWTITLE eq *main.py*" >nul 2>&1

echo 🌐 Käynnistetään RawCandle portissa 8888...
echo    Avaa selaimessa: http://localhost:8888
echo.

REM Käynnistä sovellus virtuaaliympäristössä
set FLET_PORT=8888
"%PROJECT_DIR%venv\Scripts\python.exe" main.py --port 8888

echo.
echo 👋 RawCandle Server sammui
pause