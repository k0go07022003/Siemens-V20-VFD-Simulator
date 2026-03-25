#!/bin/bash
echo "============================================"
echo "  Siemens V20 Simulator - Modbus RTU"
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

# ---- Portkonfiguration ----
echo "Verfuegbare serielle Ports:"
python3 -m serial.tools.list_ports
echo

read -p "Seriellen Port angeben (z.B. /dev/ttyUSB0): " SERPORT
SERPORT="${SERPORT:-/dev/ttyUSB0}"

read -p "Baudrate [9600]: " BAUD
BAUD="${BAUD:-9600}"

read -p "Slave ID [1]: " SLAVEID
SLAVEID="${SLAVEID:-1}"

echo
echo "============================================"
echo "  Web GUI:     http://localhost:5000"
echo "  Modbus RTU:  $SERPORT @ $BAUD, Slave ID $SLAVEID"
echo
echo "  USB-RS485-Adapter an den Modbus-Port"
echo "  anschliessen."
echo "============================================"
echo

python3 v20_web.py --port "$SERPORT" --baudrate "$BAUD" --web-port 5000 --slave-id "$SLAVEID"
