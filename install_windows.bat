@echo off
chcp 65001 >nul
echo ============================================
echo   Instalacja symulatora Siemens V20
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo BLAD: Python nie jest zainstalowany!
    echo Pobierz z: https://www.python.org/downloads/
    echo Zaznacz "Add Python to PATH" podczas instalacji!
    pause
    exit /b 1
)

echo Tworzenie srodowiska wirtualnego...
python -m venv venv
call venv\Scripts\activate.bat

echo Instalacja zaleznosci...
pip install pymodbus==3.12.1 pyserial==3.5 flask==3.1.3

echo.
echo ============================================
echo   Instalacja zakonczona!
echo   Uruchom: run_tcp.bat lub run_rtu.bat
echo ============================================
pause
