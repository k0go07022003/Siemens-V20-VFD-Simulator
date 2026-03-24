# Siemens V20 Modbus Simulator

Siemens SINAMICS V20 variable frequency drive simulator with a web-based GUI.
Emulates the full PROFIdrive state machine and Modbus RTU / TCP communication — perfect for testing HMI programs (e.g. Weintek FT2J, Siemens panels) without physical hardware.

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## Quick Start (Windows)

### 1. Install Python
Download from [python.org](https://www.python.org/downloads/).
**Check "Add Python to PATH"** during installation.

### 2. Download the simulator
Download the latest package from the [Releases](../../releases) tab and extract it anywhere.

### 3. Run
Double-click:
- **`run_rtu.bat`** — Modbus RTU mode (RS-485, e.g. USB converter)
- **`run_tcp.bat`** — Modbus TCP mode (Ethernet)

On first run the script will automatically create a Python virtual environment and install all dependencies.

Once started, open your browser: **http://localhost:5000**

---

## Modbus Parameters

### RTU Connection (serial)

| Parameter   | Value       |
|-------------|-------------|
| Baudrate    | 9600 (default) |
| Data bits   | 8           |
| Parity      | None (N)    |
| Stop bits   | 1           |
| Slave ID    | 1 (default) |

### TCP Connection

| Parameter   | Value       |
|-------------|-------------|
| TCP Port    | 502 (default) |
| Slave ID    | 1 (default) |
| Framer      | RTU over TCP |

---

## Register Map (Holding Registers)

Registers follow the PROFIdrive / USS protocol used by Siemens V20.

### Control Registers (write from HMI → simulator)

| Register | Modbus Address | Description |
|----------|---------------|-------------|
| **STW1** (Control Word) | 40100 | Drive control word |
| **HSW** (Speed Setpoint) | 40101 | Speed setpoint (0–16384 = 0–100%) |

### Status Registers (read from simulator → HMI)

| Register | Modbus Address | Description |
|----------|---------------|-------------|
| **ZSW1** (Status Word) | 40110 | Drive status word |
| **HIW** (Actual Speed) | 40111 | Actual speed (0–16384 = 0–100%) |

### STW1 Bits (Control Word) — address 40100

| Bit | Name | Description |
|-----|------|-------------|
| 0 | ON | Start the drive |
| 1 | OFF2 | Coast stop (0 = coast to stop) |
| 2 | OFF3 | Quick stop (0 = ramp down fast) |
| 3 | ENABLE_OP | Enable operation |
| 4 | RFG_EN | Enable ramp function generator |
| 5 | RFG_START | Start ramp function generator |
| 6 | SETPOINT_EN | Enable speed setpoint |
| 7 | FAULT_ACK | Fault acknowledge (rising edge) |
| 10 | PLC_CTRL | PLC control active |
| 11 | REVERSE | Direction: 0 = FWD, 1 = REV |

### ZSW1 Bits (Status Word) — address 40110

| Bit | Name | Description |
|-----|------|-------------|
| 0 | READY_ON | Ready to switch on |
| 1 | READY_RUN | Ready to run |
| 2 | RUNNING | Motor is running |
| 3 | FAULT | Fault active |
| 4 | OFF2_INACTIVE | 1 = coast stop not active |
| 5 | OFF3_INACTIVE | 1 = quick stop not active |
| 6 | ON_INHIBIT | Switch-on inhibited |
| 7 | WARNING | Warning active |
| 8 | SETPOINT_OK | Speed reached |
| 9 | PLC_CTRL | PLC control confirmed |
| 10 | FREQ_LIMIT | Frequency limit reached |
| 11 | REVERSE | Reverse direction active |

### Speed Scaling

Value `16384` (0x4000) = 100% = max frequency (default 50 Hz).

| HSW / HIW | Percent | Frequency |
|-----------|---------|-----------|
| 0         | 0%      | 0.0 Hz    |
| 4096      | 25%     | 12.5 Hz   |
| 8192      | 50%     | 25.0 Hz   |
| 16384     | 100%    | 50.0 Hz   |

---

## Startup Sequence

To start the motor from your HMI, write to STW1 (40100) in sequence:

1. `0x047E` — prepare (OFF2=1, OFF3=1, ENABLE_OP=1, RFG_EN=1, RFG_START=1, SETPOINT_EN=1)
2. `0x047F` — start (+ ON bit = 1)
3. Write the desired speed to HSW (40101), e.g. `8192` = 50%

To stop: clear bit 0 (ON) in STW1 → `0x047E`

---

## Command Line Options

```
python v20_web.py [options]

Modbus:
  --port PORT          COM port (default /dev/ttyUSB0)
  --baudrate BAUD      Baudrate (default 9600)
  --slave-id ID        Slave ID (default 1)
  --tcp                Modbus TCP mode
  --tcp-port PORT      TCP port (default 502)

Motor:
  --max-freq HZ        Max frequency (default 50.0)
  --accel-time SEC     Acceleration time (default 5.0)
  --decel-time SEC     Deceleration time (default 5.0)

Web GUI:
  --web-port PORT      HTTP port (default 5000)
  --no-browser         Don't open browser automatically
```

---

## License

MIT — do whatever you want with it.

---

Made by [ControlByte](https://controlbyte.tech) for training and testing purposes.
