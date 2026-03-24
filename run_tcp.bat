@echo off
chcp 65001 >nul
title Siemens V20 Simulator - Modbus TCP
echo ============================================
echo   Siemens V20 Simulator - Modbus TCP
echo ============================================
echo.

:: ---- Sprawdz czy Python jest zainstalowany ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [BLAD] Python nie jest zainstalowany!
    echo.
    echo Pobierz z: https://www.python.org/downloads/
    echo WAZNE: Zaznacz "Add Python to PATH" podczas instalacji!
    echo.
    pause
    exit /b 1
)

:: ---- Utworz venv jesli nie istnieje ----
if not exist "venv\Scripts\activate.bat" (
    echo [1/2] Tworzenie srodowiska wirtualnego...
    python -m venv venv
    if errorlevel 1 (
        echo [BLAD] Nie udalo sie utworzyc venv!
        pause
        exit /b 1
    )
    echo      OK
    echo.
    echo [2/2] Instalacja zaleznosci...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [BLAD] Nie udalo sie zainstalowac zaleznosci!
        pause
        exit /b 1
    )
    echo      OK
    echo.
) else (
    call venv\Scripts\activate.bat
)

:: ---- Start ----
echo ============================================
echo   Web GUI:    http://localhost:5000
echo   Modbus TCP: port 502, slave ID 1
echo.
echo   Podlacz FT2J po Ethernecie.
echo   W FT2J ustaw IP tego komputera i port 502.
echo ============================================
echo.

python v20_web.py --tcp --tcp-port 502 --web-port 5000 --slave-id 1

pause
