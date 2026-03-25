#!/bin/bash
echo "============================================"
echo "  Siemens V20 Simulator - Modbus TCP"
echo "============================================"
echo

# ---- Python pruefen ----
if ! command -v python3 &>/dev/null; then
    echo "[FEHLER] Python3 ist nicht installiert!"
    echo
    echo "Installieren mit: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# ---- venv erstellen falls nicht vorhanden ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "venv/bin/activate" ]; then
    echo "[1/2] Erstelle virtuelle Umgebung..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "[FEHLER] venv konnte nicht erstellt werden!"
        exit 1
    fi
    echo "     OK"
    echo
    echo "[2/2] Installiere Abhaengigkeiten..."
    source venv/bin/activate
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "[FEHLER] Abhaengigkeiten konnten nicht installiert werden!"
        exit 1
    fi
    echo "     OK"
    echo
else
    source venv/bin/activate
fi

# ---- Start ----
echo "============================================"
echo "  Web GUI:    http://localhost:5000"
echo "  Modbus TCP: Port 502, Slave ID 1"
echo
echo "  Hinweis: Port 502 erfordert root-Rechte."
echo "  Alternativ: --tcp-port 5020 verwenden."
echo "============================================"
echo

python3 v20_web.py --tcp --tcp-port 502 --web-port 5000 --slave-id 1
