# Siemens V20 Modbus Simulator

Symulator falownika Siemens SINAMICS V20 z interfejsem webowym.
Emuluje pełną maszynę stanów PROFIdrive i komunikację Modbus RTU / TCP — idealny do testowania programów HMI (np. Weintek FT2J) bez fizycznego falownika.

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## Szybki start (Windows)

### 1. Zainstaluj Pythona
Pobierz z [python.org](https://www.python.org/downloads/).
**Zaznacz "Add Python to PATH"** podczas instalacji.

### 2. Pobierz symulator
Pobierz najnowszą paczkę z zakładki [Releases](../../releases) i rozpakuj w dowolne miejsce.

### 3. Uruchom
Dwuklik na:
- **`run_rtu.bat`** — tryb Modbus RTU (RS-485, np. konwerter USB)
- **`run_tcp.bat`** — tryb Modbus TCP (Ethernet)

Przy pierwszym uruchomieniu skrypt sam utworzy środowisko wirtualne i zainstaluje zależności.

Po starcie otwórz przeglądarkę: **http://localhost:5000**

---

## Parametry Modbus

### Połączenie RTU (serial)

| Parametr     | Wartość     |
|-------------|-------------|
| Baudrate    | 9600 (domyślnie) |
| Data bits   | 8           |
| Parity      | None (N)    |
| Stop bits   | 1           |
| Slave ID    | 1 (domyślnie) |

### Połączenie TCP

| Parametr     | Wartość     |
|-------------|-------------|
| Port TCP    | 502 (domyślnie) |
| Slave ID    | 1 (domyślnie) |
| Framer      | RTU over TCP |

---

## Mapa rejestrów (Holding Registers)

Rejestry zgodne z protokołem PROFIdrive / USS Siemens V20.

### Rejestry sterujące (zapis z HMI → symulator)

| Rejestr | Adres Modbus | Opis |
|---------|-------------|------|
| **STW1** (Control Word) | 40100 | Słowo sterujące falownikiem |
| **HSW** (Speed Setpoint) | 40101 | Zadana prędkość (0–16384 = 0–100%) |

### Rejestry statusowe (odczyt symulator → HMI)

| Rejestr | Adres Modbus | Opis |
|---------|-------------|------|
| **ZSW1** (Status Word) | 40110 | Słowo statusowe falownika |
| **HIW** (Actual Speed) | 40111 | Aktualna prędkość (0–16384 = 0–100%) |

### Bity STW1 (Control Word) — adres 40100

| Bit | Nazwa | Opis |
|-----|-------|------|
| 0 | ON | Start falownika |
| 1 | OFF2 | Coast stop (0 = stop wybiegowy) |
| 2 | OFF3 | Quick stop (0 = szybkie hamowanie) |
| 3 | ENABLE_OP | Zezwolenie na pracę |
| 4 | RFG_EN | Enable ramp function |
| 5 | RFG_START | Start ramp function |
| 6 | SETPOINT_EN | Enable speed setpoint |
| 7 | FAULT_ACK | Potwierdzenie błędu (zbocze narastające) |
| 10 | PLC_CTRL | Sterowanie z PLC |
| 11 | REVERSE | Kierunek: 0 = FWD, 1 = REV |

### Bity ZSW1 (Status Word) — adres 40110

| Bit | Nazwa | Opis |
|-----|-------|------|
| 0 | READY_ON | Gotowy do załączenia |
| 1 | READY_RUN | Gotowy do pracy |
| 2 | RUNNING | Silnik pracuje |
| 3 | FAULT | Błąd aktywny |
| 4 | OFF2_INACTIVE | 1 = coast stop nieaktywny |
| 5 | OFF3_INACTIVE | 1 = quick stop nieaktywny |
| 6 | ON_INHIBIT | Blokada załączenia |
| 7 | WARNING | Ostrzeżenie |
| 8 | SETPOINT_OK | Prędkość osiągnięta |
| 9 | PLC_CTRL | Sterowanie z PLC aktywne |
| 10 | FREQ_LIMIT | Osiągnięto limit częstotliwości |
| 11 | REVERSE | Kierunek REV aktywny |

### Skalowanie prędkości

Wartość `16384` (0x4000) = 100% = max częstotliwość (domyślnie 50 Hz).

| HSW / HIW | Procent | Częstotliwość |
|-----------|---------|---------------|
| 0         | 0%      | 0.0 Hz        |
| 4096      | 25%     | 12.5 Hz       |
| 8192      | 50%     | 25.0 Hz       |
| 16384     | 100%    | 50.0 Hz       |

---

## Sekwencja startowa

Aby uruchomić silnik z HMI, wyślij do STW1 (40100) kolejno:

1. `0x047E` — przygotowanie (OFF2=1, OFF3=1, ENABLE_OP=1, RFG_EN=1, RFG_START=1, SETPOINT_EN=1)
2. `0x047F` — start (+ bit ON=1)
3. Wpisz zadaną prędkość do HSW (40101), np. `8192` = 50%

Aby zatrzymać: wyzeruj bit 0 (ON) w STW1 → `0x047E`

---

## Opcje wiersza poleceń

```
python v20_web.py [opcje]

Modbus:
  --port PORT          Port COM (domyślnie /dev/ttyUSB0)
  --baudrate BAUD      Baudrate (domyślnie 9600)
  --slave-id ID        Slave ID (domyślnie 1)
  --tcp                Tryb Modbus TCP
  --tcp-port PORT      Port TCP (domyślnie 502)

Silnik:
  --max-freq HZ        Max częstotliwość (domyślnie 50.0)
  --accel-time SEC     Czas rozpędzania (domyślnie 5.0)
  --decel-time SEC     Czas hamowania (domyślnie 5.0)

Web GUI:
  --web-port PORT      Port HTTP (domyślnie 5000)
  --no-browser         Nie otwieraj przeglądarki
```

---

## Docker (opcjonalnie)

```bash
docker-compose up
```

---

## Licencja

MIT — rób z tym co chcesz.

---

Stworzono przez [ControlByte](https://controlbyte.pl) do celów szkoleniowych i testowych.
