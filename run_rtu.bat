@echo off
chcp 65001 >nul
title Siemens V20 Simulator - Modbus RTU
echo ============================================
echo   Siemens V20 Simulator - Modbus RTU
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

:: ---- Konfiguracja portu ----
echo Dostepne porty COM:
python -m serial.tools.list_ports
echo.

set /p COMPORT="Podaj port COM (np. COM3): "
set /p BAUD="Podaj baudrate [9600]: "
if "%BAUD%"=="" set BAUD=9600
set /p SLAVEID="Podaj slave ID [1]: "
if "%SLAVEID%"=="" set SLAVEID=1

echo.
echo ============================================
echo   Web GUI:     http://localhost:5000
echo   Modbus RTU:  %COMPORT% @ %BAUD%, slave ID %SLAVEID%
echo.
echo   Podlacz konwerter USB-RS485 do portu
echo   Modbus na FT2J.
echo ============================================
echo.

python v20_web.py --port %COMPORT% --baudrate %BAUD% --web-port 5000 --slave-id %SLAVEID%

pause
