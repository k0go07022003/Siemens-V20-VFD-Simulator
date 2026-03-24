# IDEC FT2J + Siemens V20 Simulator — Kompletna konfiguracja

## 1. MAPOWANIE ZMIENNYCH

### 1.1 Rejestry komunikacyjne Modbus (wymiana z V20)

| Rejestr FT2J | Kierunek | Modbus Addr | Opis | Zakres |
|---|---|---|---|---|
| D100 | HMI → V20 | 40100 | STW1 — Słowo sterujące | 0x0000–0xFFFF |
| D101 | HMI → V20 | 40101 | HSW — Zadana prędkość (raw) | 0–16384 |
| D110 | V20 → HMI | 40110 | ZSW1 — Słowo statusu | 0x0000–0xFFFF |
| D111 | V20 → HMI | 40111 | HIW — Aktualna prędkość (raw) | 0–16384 |

### 1.2 Zmienne wewnętrzne PLC — sterowanie

| Rejestr | Typ | Opis | Uwagi |
|---|---|---|---|
| M0 | Bit | Przycisk START | Momentary (HMI button) |
| M1 | Bit | Przycisk STOP | Momentary |
| M2 | Bit | Przełącznik REVERSE | Toggle ON/OFF |
| M3 | Bit | Przycisk FAULT ACK | Momentary |
| M4 | Bit | Przycisk E-STOP (OFF3) | Momentary, NC logic |
| M5 | Bit | Przycisk COAST STOP (OFF2) | Momentary |
| M10 | Bit | Flaga: Drive READY | Status indicator |
| M11 | Bit | Flaga: Drive RUNNING | Status indicator |
| M12 | Bit | Flaga: Drive FAULT | Status indicator |
| M13 | Bit | Flaga: SP_OK (prędkość osiągnięta) | Status indicator |
| M14 | Bit | Flaga: WARNING | Status indicator |
| M15 | Bit | Flaga: REVERSE aktywny | Status indicator |
| M16 | Bit | Flaga: OFF2 aktywny (coast) | Status indicator |
| M17 | Bit | Flaga: OFF3 aktywny (quick) | Status indicator |
| M20 | Bit | Komenda: buduj STW1 | Wewnętrzna flaga PLC |
| M50 | Bit | Modbus Request 1 trigger (READ) | Request execution |
| M51 | Bit | Modbus Request 2 trigger (WRITE) | Request execution |
| M52 | Bit | Modbus comm OK | Status komunikacji |
| M53 | Bit | Modbus comm ERROR | Błąd komunikacji |

### 1.3 Zmienne wewnętrzne PLC — dane

| Rejestr | Typ | Opis | Uwagi |
|---|---|---|---|
| D200 | Word | Zadana częstotliwość Hz × 10 | np. 250 = 25.0 Hz |
| D201 | Word | Aktualna częstotliwość Hz × 10 | Obliczona z HIW |
| D202 | Word | Max częstotliwość Hz × 10 | Domyślnie 500 (50.0 Hz) |
| D210 | Word | STW1 kopia robocza | Budowany przez LAD |
| D211 | Word | Kopia ZSW1 do dekodowania | Kopia D110 |
| D220 | Word | Prędkość % × 10 | 0–1000 (0.0–100.0%) |

### 1.4 Stałe przeliczeniowe

| Stała | Wartość | Opis |
|---|---|---|
| SPEED_100_PCT | 16384 (0x4000) | Raw = 100% = max freq |
| MAX_FREQ_x10 | 500 | 50.0 Hz × 10 |

---

## 2. KONFIGURACJA KOMUNIKACJI W WindO/I-NV4

### 2.1 Ustawienia portu szeregowego

W WindO/I-NV4: **Project Settings → Communication**

```
Port:           RS485 (COM)
Protocol:       Modbus RTU Master
Baud Rate:      9600
Data Bits:      8
Parity:         Even
Stop Bits:      1
Timeout:        1000 ms
Retry:          3
Scan Rate:      100 ms
```

### 2.2 Modbus Master Request Table

W WindO/I-NV4: **Communication → Modbus Master Requests**

#### Request No. 1 — Odczyt statusu V20

```
Request No:         1
Execution Device:   M50
Slave Address:      1
Function Code:      03 (Read Holding Registers)
Start Address:      40110
Quantity:           2
Destination:        D110
```

Efekt: co cykl M50=ON → czyta 40110-40111 → D110 (ZSW1), D111 (HIW)

#### Request No. 2 — Zapis sterowania do V20

```
Request No:         2
Execution Device:   M51
Slave Address:      1
Function Code:      16 (Write Multiple Registers)
Start Address:      40100
Quantity:           2
Source:             D100
```

Efekt: co cykl M51=ON → pisze D100 (STW1), D101 (HSW) → 40100-40101

### 2.3 Komunikacja cykliczna

W ladderze: M50 i M51 ustawiaj na ON cyklicznie (np. co 100ms przez timer),
albo w WindO/I-NV4 ustaw "Cyclic" w kolumnie Execution Type request table.

---

## 3. MAKRO HMI — Wymiana danych i przeliczenia

W WindO/I-NV4: **Macro → Periodic Macro** (okres: 100ms)

```c
// ============================================================
// MAKRO: V20_COMM — cykliczna wymiana danych
// Uruchamiaj co 100ms jako Periodic Macro
// ============================================================

// --- Stałe ---
#define SPEED_100_PCT  16384
#define MAX_FREQ_X10   500

// ============================================================
// 1. Odczyt i zapis — trigger Modbus requests
// ============================================================
// Włącz cykliczny odczyt/zapis (Request 1 i 2)
M50 = 1;  // Trigger READ  (ZSW1 + HIW)
M51 = 1;  // Trigger WRITE (STW1 + HSW)

// ============================================================
// 2. Przelicz zadaną częstotliwość Hz → raw HSW
//    D200 = częstotliwość × 10 (np. 250 = 25.0 Hz)
//    D101 = raw value (0-16384)
// ============================================================
if (D200 > MAX_FREQ_X10) {
    D200 = MAX_FREQ_X10;  // Clamp do max 50.0 Hz
}
D101 = (D200 * SPEED_100_PCT) / MAX_FREQ_X10;

// ============================================================
// 3. Przelicz aktualną prędkość raw HIW → Hz
//    D111 = raw value z V20
//    D201 = aktualna częstotliwość × 10
//    D220 = prędkość %  × 10
// ============================================================
D201 = (D111 * MAX_FREQ_X10) / SPEED_100_PCT;
D220 = (D111 * 1000) / SPEED_100_PCT;

// ============================================================
// 4. Dekoduj ZSW1 → flagi M10-M17
//    D110 = ZSW1 odczytany z V20
// ============================================================
D211 = D110;  // kopia robocza

M10 = (D211 & 0x0001) ? 1 : 0;  // Bit 0:  READY_ON
M11 = (D211 & 0x0004) ? 1 : 0;  // Bit 2:  RUNNING
M12 = (D211 & 0x0008) ? 1 : 0;  // Bit 3:  FAULT
M13 = (D211 & 0x0100) ? 1 : 0;  // Bit 8:  SP_OK
M14 = (D211 & 0x0080) ? 1 : 0;  // Bit 7:  WARNING
M15 = (D211 & 0x0800) ? 1 : 0;  // Bit 11: REVERSE
M16 = (D211 & 0x0010) ? 0 : 1;  // Bit 4:  OFF2 inactive=1 → aktywny gdy =0
M17 = (D211 & 0x0020) ? 0 : 1;  // Bit 5:  OFF3 inactive=1 → aktywny gdy =0

// ============================================================
// 5. Kopiuj STW1 z rejestru roboczego do rejestru komunikacji
//    D210 = budowany przez LAD
//    D100 = wysyłany do V20
// ============================================================
D100 = D210;
```

---

## 4. PROGRAM PLC W LADDER (LAD)

### 4.1 Przegląd sieci (Rung)

```
Rung 1:  Inicjalizacja — ustaw bazowy STW1
Rung 2:  Sekwencja READY (przygotowanie napędu)
Rung 3:  START Forward / Reverse
Rung 4:  STOP (normalny — rampa)
Rung 5:  E-STOP / Quick Stop (OFF3)
Rung 6:  Coast Stop (OFF2)
Rung 7:  Fault Acknowledge
Rung 8:  Timer cyklicznej komunikacji
```

### 4.2 Szczegółowy Ladder

#### RUNG 1 — Inicjalizacja bazowego STW1

Przy starcie PLC ustaw bazowy STW1 = 0x047E
(OFF2=1, OFF3=1, ENABLE=1, RFG_EN=1, RFG_START=1, SETPOINT=1, PLC_CTRL=1, ON=0)

```
  |                                                              |
  |  M8000                                                       |
  |--] [--------+---[MOV  0x047E  →  D210]---+                   |
  |  (first     |                             |                   |
  |   scan)     +-----------------------------+                   |
  |                                                              |
```

Uwaga: M8000 = Special relay "First Scan" w IDEC.
Jeśli niedostępny, użyj flagi inicjalizacji (np. M100).

Alternatywnie jako always-on baseline:

```
  |                                                              |
  |  M8001      M11                                              |
  |--] [-------]/[--------[MOV  0x047E  →  D210]                 |
  |  (always    (NOT                                             |
  |   ON)        running)                                        |
  |                                                              |
```

#### RUNG 2 — START Forward

Gdy M0 (START) wciśnięty i napęd READY (M10=1) i brak FAULT (M12=0):
Ustaw bit 0 (ON) w D210 → STW1 = 0x047F

```
  |                                                              |
  |  M0         M10        M12                                   |
  |--] [-------] [--------]/[-------[OR  D210, 0x0001 → D210]   |
  |  (START)   (READY)    (no FAULT)  (set bit 0 = ON)          |
  |                                                              |
```

#### RUNG 3 — START Reverse

Gdy M0 (START) + M2 (REVERSE toggle ON):
Ustaw bit 11 (REVERSE) + bit 0 (ON) → STW1 = 0x0C7F

```
  |                                                              |
  |  M0         M2         M10        M12                        |
  |--] [-------] [--------] [--------]/[--+--[OR  D210, 0x0801  |
  |  (START)   (REVERSE)  (READY)  (no   |       → D210]        |
  |                                FAULT) |                      |
  |                                       |                      |
```

Gdy M2 (REVERSE) wyłączony — wyczyść bit 11:

```
  |                                                              |
  |  M2                                                          |
  |--]/[--------[AND  D210, 0xF7FF  →  D210]                    |
  |  (not                 (clear bit 11)                         |
  |   reverse)                                                   |
  |                                                              |
```

#### RUNG 4 — STOP (normalny, z rampą)

Gdy M1 (STOP) wciśnięty:
Wyczyść bit 0 (ON) w D210 → napęd hamuje po rampie

```
  |                                                              |
  |  M1                                                          |
  |--] [--------[AND  D210, 0xFFFE  →  D210]                    |
  |  (STOP)           (clear bit 0 = OFF)                        |
  |                                                              |
```

#### RUNG 5 — E-STOP / Quick Stop (OFF3=0)

Gdy M4 (E-STOP) wciśnięty:
Wyczyść bit 2 (OFF3) i bit 0 (ON) → szybkie zatrzymanie

```
  |                                                              |
  |  M4                                                          |
  |--] [--------[AND  D210, 0xFFFA  →  D210]                    |
  |  (E-STOP)        (clear bits 0,2 = OFF + OFF3)              |
  |                                                              |
```

Po zwolnieniu E-STOP przywróć OFF3:

```
  |                                                              |
  |  M4                                                          |
  |--]/[---------[OR  D210, 0x0004  →  D210]                    |
  |  (E-STOP                                                     |
  |   released)   (set bit 2 = OFF3 inactive)                   |
  |                                                              |
```

#### RUNG 6 — Coast Stop (OFF2=0)

Gdy M5 (COAST) wciśnięty:
Wyczyść bit 1 (OFF2) i bit 0 (ON)

```
  |                                                              |
  |  M5                                                          |
  |--] [--------[AND  D210, 0xFFFC  →  D210]                    |
  |  (COAST)         (clear bits 0,1 = OFF + OFF2)              |
  |                                                              |
```

Po zwolnieniu COAST przywróć OFF2:

```
  |                                                              |
  |  M5                                                          |
  |--]/[---------[OR  D210, 0x0002  →  D210]                    |
  |  (released)   (set bit 1 = OFF2 inactive)                   |
  |                                                              |
```

#### RUNG 7 — Fault Acknowledge

Gdy M3 (FAULT ACK) i FAULT aktywny (M12=1):
Ustaw bit 7 (FAULT_ACK) — zbocze narastające

```
  |                                                              |
  |  M3         M12                                              |
  |--] [-------] [--------[OR  D210, 0x0080  →  D210]           |
  |  (ACK btn) (FAULT)    (set bit 7 = FAULT_ACK)               |
  |                                                              |
```

Po zwolnieniu M3 — wyczyść bit 7:

```
  |                                                              |
  |  M3                                                          |
  |--]/[---------[AND  D210, 0xFF7F  →  D210]                   |
  |  (released)   (clear bit 7)                                  |
  |                                                              |
```

#### RUNG 8 — Timer komunikacji (jeśli nie cykliczny request)

Timer 100ms do cyklicznego triggerowania M50/M51:

```
  |                                                              |
  |  M8001                    T0                                 |
  |--] [-------[TMR  T0  K1]--] [--+--[SET M50]                 |
  |  (always                       |                             |
  |   ON)       (100ms timer)      +--[SET M51]                  |
  |                                |                             |
  |                                +--[RST T0]                   |
  |                                                              |
```

---

## 5. KONFIGURACJA ELEMENTÓW HMI

### 5.1 Przyciski na ekranie HMI

| Element HMI | Typ | Zmienna | Akcja |
|---|---|---|---|
| Przycisk START | Momentary | M0 | Set ON przy naciśnięciu |
| Przycisk STOP | Momentary | M1 | Set ON przy naciśnięciu |
| Toggle REVERSE | Toggle | M2 | ON/OFF przełącznik |
| Przycisk FAULT ACK | Momentary | M3 | Set ON przy naciśnięciu |
| Przycisk E-STOP | Momentary | M4 | Set ON przy naciśnięciu |
| Przycisk COAST | Momentary | M5 | Set ON przy naciśnięciu |

### 5.2 Wskaźniki statusu na HMI

| Element HMI | Typ | Zmienna | Kolor ON / OFF |
|---|---|---|---|
| Lampka READY | Indicator | M10 | Zielony / Szary |
| Lampka RUNNING | Indicator | M11 | Zielony / Szary |
| Lampka FAULT | Indicator | M12 | Czerwony / Szary |
| Lampka SP_OK | Indicator | M13 | Zielony / Szary |
| Lampka WARNING | Indicator | M14 | Żółty / Szary |
| Lampka REVERSE | Indicator | M15 | Niebieski / Szary |

### 5.3 Wyświetlacze numeryczne

| Element HMI | Typ | Zmienna | Format | Opis |
|---|---|---|---|---|
| Zadana częst. | Numeric Input | D200 | ###.# (÷10) | Wpisz Hz × 10 |
| Aktualna częst. | Numeric Display | D201 | ###.# (÷10) | Hz × 10 |
| Prędkość % | Numeric Display | D220 | ###.# (÷10) | 0.0–100.0% |
| Slider prędkości | Slider | D200 | 0–500 | 0.0–50.0 Hz |

### 5.4 Bargraf / Gauge

| Element | Zmienna | Min | Max | Opis |
|---|---|---|---|---|
| Bargraf prędkości | D220 | 0 | 1000 | 0–100.0% |
| Gauge Hz | D201 | 0 | 500 | 0–50.0 Hz |

---

## 6. SCHEMAT PRZEPŁYWU DANYCH

```
┌─────────────────────────────────────────────────────────┐
│                    IDEC FT2J                            │
│                                                         │
│  ┌─────────┐    ┌──────────┐    ┌────────────────────┐  │
│  │   HMI   │    │   PLC    │    │  Modbus Master     │  │
│  │ Screen  │    │  Ladder  │    │  (RS485 → V20)     │  │
│  │         │    │          │    │                    │  │
│  │ M0:START├───►│ Rung 2-3 │    │  REQ 1: READ       │  │
│  │ M1:STOP ├───►│ Rung 4   │    │  40110-40111       │  │
│  │ M2:REV  ├───►│ Rung 3   │    │  → D110, D111      │  │
│  │ M3:ACK  ├───►│ Rung 7   │    │                    │  │
│  │ M4:ESTOP├───►│ Rung 5   │    │  REQ 2: WRITE      │  │
│  │ D200:Hz ├───►│          │    │  D100, D101        │  │
│  │         │    │   ↓      │    │  → 40100-40101     │  │
│  │         │    │ D210     │    │                    │  │
│  │         │    │ (STW1    │    │                    │  │
│  │         │    │  build)  │    │                    │  │
│  │         │    │   ↓      │    │                    │  │
│  │         │    │ MACRO    │    │                    │  │
│  │         │    │ D210→D100├───►│  D100 → 40100      │  │
│  │         │    │ D200→D101├───►│  D101 → 40101      │  │
│  │         │    │          │    │                    │  │
│  │ D201:Hz ◄───┤ D111→D201│◄───┤  40110 → D110      │  │
│  │ M10-M17 ◄───┤ D110→Mxx │◄───┤  40111 → D111      │  │
│  └─────────┘    └──────────┘    └────────────────────┘  │
│                                          │              │
└──────────────────────────────────────────┼──────────────┘
                                           │ RS485
                                           │ 9600 8E1
                                           ▼
                              ┌─────────────────────┐
                              │  Siemens V20        │
                              │  (Symulator)        │
                              │                     │
                              │  40100: STW1        │
                              │  40101: HSW         │
                              │  40110: ZSW1        │
                              │  40111: HIW         │
                              └─────────────────────┘
```

---

## 7. BITY STW1 — ŚCIĄGAWKA

| Bit | Nazwa | 0 = | 1 = | Maska |
|---|---|---|---|---|
| 0 | ON/OFF1 | STOP | START | 0x0001 |
| 1 | OFF2 | Coast Stop aktywny | Normalny | 0x0002 |
| 2 | OFF3 | Quick Stop aktywny | Normalny | 0x0004 |
| 3 | Enable Operation | Zablokowany | Odblokowany | 0x0008 |
| 4 | RFG Enable | Wyłączony | Włączony | 0x0010 |
| 5 | RFG Start | Stop | Start | 0x0020 |
| 6 | Setpoint Enable | Zablokowany | Aktywny | 0x0040 |
| 7 | Fault ACK | - | Potwierdź fault | 0x0080 |
| 10 | PLC Control | Lokalny | PLC | 0x0400 |
| 11 | Reverse | Forward | Reverse | 0x0800 |

### Typowe wartości STW1

| Komenda | STW1 | Hex |
|---|---|---|
| Reset / Idle | 0000 0000 0000 0000 | 0x0000 |
| Przygotowanie (READY) | 0000 0100 0111 1110 | 0x047E |
| START Forward | 0000 0100 0111 1111 | 0x047F |
| START Reverse | 0000 1100 0111 1111 | 0x0C7F |
| STOP (rampa) | 0000 0100 0111 1110 | 0x047E |
| Quick Stop (OFF3) | 0000 0100 0111 1010 | 0x047A |
| Coast Stop (OFF2) | 0000 0100 0111 1100 | 0x047C |

## 8. BITY ZSW1 — ŚCIĄGAWKA

| Bit | Nazwa | 0 = | 1 = | Maska |
|---|---|---|---|---|
| 0 | Ready to switch on | Nie gotowy | Gotowy | 0x0001 |
| 1 | Ready to run | Nie gotowy | Gotowy do pracy | 0x0002 |
| 2 | Running | Stoi | Pracuje | 0x0004 |
| 3 | Fault | Brak | FAULT aktywny | 0x0008 |
| 4 | OFF2 inactive | Coast AKTYWNY | Coast nieaktywny | 0x0010 |
| 5 | OFF3 inactive | Quick AKTYWNY | Quick nieaktywny | 0x0020 |
| 6 | ON inhibit | Można włączyć | Włączenie zablokowane | 0x0040 |
| 7 | Warning | Brak | Ostrzeżenie | 0x0080 |
| 8 | Setpoint reached | Nie | Tak (SP_OK) | 0x0100 |
| 9 | PLC control | Nie | Tak | 0x0200 |
| 10 | Freq limit | Nie | Częstotliwość na limicie | 0x0400 |
| 11 | Reverse | Forward | Reverse | 0x0800 |
