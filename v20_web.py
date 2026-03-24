#!/usr/bin/env python3
"""
Symulator Siemens V20 z GUI webowym
====================================
Wszystko w jednym: serwer Modbus + wizualizacja w przegladarce.

Uzycie:
  pip install pymodbus pyserial flask
  python v20_web.py --port COM3 --baudrate 9600 --slave-id 1
  python v20_web.py --tcp --tcp-port 502 --slave-id 1

  Otworz przegladarke: http://localhost:5000
"""

import argparse
import json
import logging
import threading
import time
import signal
import sys

from flask import Flask, Response, request, jsonify

# --- Modbus imports (pymodbus 3.x) ---
try:
    from pymodbus.server import StartSerialServer, StartTcpServer
    from pymodbus.framer import FramerType
    from pymodbus.datastore import (
        ModbusSequentialDataBlock,
        ModbusServerContext,
    )
    # pymodbus >= 3.12: ModbusDeviceContext
    try:
        from pymodbus.datastore import ModbusDeviceContext as ModbusSlaveContext
    except ImportError:
        from pymodbus.datastore import ModbusSlaveContext
except ImportError:
    print("BLAD: pip install pymodbus pyserial flask")
    sys.exit(1)

# ============================================================
# Stale
# ============================================================
# Adresy Modbus (jak widzi je klient)
REG_STW1_MB = 99    # 40100
REG_HSW_MB  = 100   # 40101
REG_ZSW1_MB = 109   # 40110
REG_HIW_MB  = 110   # 40111

# Adresy wewnetrzne datablock (pymodbus mapuje addr N -> index N+1)
REG_STW1 = 100
REG_HSW  = 101
REG_ZSW1 = 110
REG_HIW  = 111
SPEED_100_PCT = 16384

STW_ON=0; STW_OFF2=1; STW_OFF3=2; STW_ENABLE_OP=3
STW_RFG_EN=4; STW_RFG_START=5; STW_SETPOINT_EN=6
STW_FAULT_ACK=7; STW_PLC_CTRL=10; STW_REVERSE=11

ZSW_READY_ON=0; ZSW_READY_RUN=1; ZSW_RUNNING=2
ZSW_FAULT=3; ZSW_OFF2_INACTIVE=4; ZSW_OFF3_INACTIVE=5
ZSW_ON_INHIBIT=6; ZSW_WARNING=7; ZSW_SETPOINT_OK=8
ZSW_PLC_CTRL=9; ZSW_FREQ_LIMIT=10; ZSW_REVERSE=11

def bit_set(w,b): return bool(w & (1<<b))
def set_bit(w,b): return w | (1<<b)

# ============================================================
# Drive states
# ============================================================
class DS:
    NOT_READY="NOT_READY"; READY_ON="READY_TO_SWITCH_ON"
    READY_RUN="READY_TO_RUN"; RUNNING="RUNNING"
    FAULT="FAULT"; COAST="COAST_STOP"; QUICK="QUICK_STOP"

# ============================================================
# V20 Simulator
# ============================================================
class V20:
    def __init__(self, max_freq=50.0, accel=5.0, decel=5.0):
        self.max_freq=max_freq; self.accel=accel; self.decel=decel
        self.quick_time=1.0
        self.state=DS.NOT_READY; self.speed=0.0; self.target=0.0
        self.direction=1; self.fault_code=0; self.sim_fault=False
        self.stw1=0; self.zsw1=0; self.hsw=0; self.hiw=0
        self._t=time.time(); self._prev=0
        self.log_lines = []

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log_lines.append(line)
        if len(self.log_lines) > 100:
            self.log_lines = self.log_lines[-100:]

    def update(self, stw1, hsw):
        now=time.time(); dt=now-self._t; self._t=now
        old_state = self.state
        self.stw1=stw1; self.hsw=hsw

        if self.sim_fault:
            self.state=DS.FAULT; self.fault_code=7
            self.sim_fault=False
            self._log("FAULT zasymulowany (F007 overcurrent)")

        self._fsm(dt); self._ramp(dt); self._zsw()
        self.hiw=int(abs(self.speed))

        if self.state != old_state:
            self._log(f"Stan: {old_state} -> {self.state}")

        self._prev=stw1

    def _fsm(self, dt):
        s=self.stw1
        if not bit_set(s,STW_OFF2) and self.state in (DS.RUNNING,DS.READY_RUN):
            self.state=DS.COAST; self.target=0; self._log("COAST STOP (OFF2=0)"); return
        if not bit_set(s,STW_OFF3) and self.state in (DS.RUNNING,DS.READY_RUN):
            self.state=DS.QUICK; self._log("QUICK STOP (OFF3=0)"); return

        if self.state==DS.NOT_READY:
            self.state=DS.READY_ON
        elif self.state==DS.READY_ON:
            if all(bit_set(s,b) for b in [STW_OFF2,STW_OFF3,STW_ENABLE_OP,STW_RFG_EN,STW_RFG_START,STW_SETPOINT_EN]):
                self.state=DS.READY_RUN
        elif self.state==DS.READY_RUN:
            if bit_set(s,STW_ON): self.state=DS.RUNNING
            if not(bit_set(s,STW_OFF2) and bit_set(s,STW_OFF3)): self.state=DS.READY_ON
        elif self.state==DS.RUNNING:
            new_dir=-1 if bit_set(s,STW_REVERSE) else 1
            if new_dir != self.direction and self.speed > 10:
                # Zmiana kierunku w biegu — najpierw hamuj do 0
                self.target=0
            else:
                if self.speed <= 10 and new_dir != self.direction:
                    self.direction=new_dir
                    self._log(f"Kierunek zmieniony na {'REV' if new_dir==-1 else 'FWD'}")
                self.direction=new_dir if self.speed <= 10 else self.direction
                self.target=float(min(self.hsw,SPEED_100_PCT)) if bit_set(s,STW_SETPOINT_EN) else 0
            if not bit_set(s,STW_ON): self.state=DS.READY_RUN; self.target=0
        elif self.state==DS.FAULT:
            if bit_set(s,STW_FAULT_ACK) and not bit_set(self._prev,STW_FAULT_ACK):
                self.fault_code=0; self.state=DS.READY_ON; self.speed=0
                self._log("Fault potwierdzony (ACK)")
        elif self.state==DS.COAST:
            if self.speed>0: self.speed=max(0,self.speed-(SPEED_100_PCT/10)*dt)
            else: self.state=DS.READY_ON
        elif self.state==DS.QUICK:
            if self.speed>0: self.speed=max(0,self.speed-(SPEED_100_PCT/self.quick_time)*dt)
            else: self.state=DS.READY_ON

    def _ramp(self, dt):
        if self.state!=DS.RUNNING:
            if self.state not in (DS.COAST,DS.QUICK):
                self.speed=max(0,self.speed-(SPEED_100_PCT/self.decel)*dt)
            return
        d=self.target-self.speed
        if abs(d)<10: self.speed=self.target
        elif d>0: self.speed=min(self.target,self.speed+(SPEED_100_PCT/self.accel)*dt)
        else: self.speed=max(self.target,self.speed-(SPEED_100_PCT/self.decel)*dt)

    def _zsw(self):
        z=0
        # OFF2/OFF3 inactive = 1 w normalnym stanie (PROFIdrive standard)
        # Bit = 0 oznacza ze dany stop JEST aktywny
        off2_inactive = self.state != DS.COAST
        off3_inactive = self.state != DS.QUICK

        if self.state==DS.READY_ON:
            z=set_bit(z,ZSW_READY_ON)
        elif self.state==DS.READY_RUN:
            z=set_bit(set_bit(z,ZSW_READY_ON),ZSW_READY_RUN)
        elif self.state==DS.RUNNING:
            z=set_bit(set_bit(set_bit(z,ZSW_READY_ON),ZSW_READY_RUN),ZSW_RUNNING)
            if abs(self.speed-self.target)<50: z=set_bit(z,ZSW_SETPOINT_OK)
            if self.direction<0: z=set_bit(z,ZSW_REVERSE)
        elif self.state==DS.FAULT:
            z=set_bit(z,ZSW_FAULT)
            z=set_bit(z,ZSW_ON_INHIBIT)  # ON zablokowane w FAULT
        elif self.state==DS.QUICK:
            z=set_bit(z,ZSW_READY_ON)
        elif self.state==DS.COAST:
            pass  # brak READY bitow podczas coast

        # OFF2/OFF3 inactive bity (1 = stop NIE jest aktywny)
        if off2_inactive: z=set_bit(z,ZSW_OFF2_INACTIVE)
        if off3_inactive: z=set_bit(z,ZSW_OFF3_INACTIVE)

        if self.speed>=SPEED_100_PCT-10: z=set_bit(z,ZSW_FREQ_LIMIT)
        if bit_set(self.stw1,STW_PLC_CTRL): z=set_bit(z,ZSW_PLC_CTRL)
        self.zsw1=z

    def freq_hz(self): return (abs(self.speed)/SPEED_100_PCT)*self.max_freq
    def target_hz(self): return (self.target/SPEED_100_PCT)*self.max_freq
    def speed_pct(self): return (abs(self.speed)/SPEED_100_PCT)*100

    def to_dict(self):
        return {
            "state": self.state,
            "freq": round(self.freq_hz(),2),
            "target_freq": round(self.target_hz(),2),
            "speed_pct": round(self.speed_pct(),1),
            "direction": self.direction,
            "stw1": self.stw1,
            "hsw": self.hsw,
            "zsw1": self.zsw1,
            "hiw": self.hiw,
            "fault_code": self.fault_code,
            "bits_stw": {
                "ON": bit_set(self.stw1,0), "OFF2": bit_set(self.stw1,1),
                "OFF3": bit_set(self.stw1,2), "ENABLE": bit_set(self.stw1,3),
                "RFG_EN": bit_set(self.stw1,4), "RFG_START": bit_set(self.stw1,5),
                "SETPOINT": bit_set(self.stw1,6), "FAULT_ACK": bit_set(self.stw1,7),
                "PLC_CTRL": bit_set(self.stw1,10), "REVERSE": bit_set(self.stw1,11),
            },
            "bits_zsw": {
                "READY_ON": bit_set(self.zsw1,0), "READY_RUN": bit_set(self.zsw1,1),
                "RUNNING": bit_set(self.zsw1,2), "FAULT": bit_set(self.zsw1,3),
                "OFF2": bit_set(self.zsw1,4), "OFF3": bit_set(self.zsw1,5),
                "ON_INHIBIT": bit_set(self.zsw1,6),
                "WARNING": bit_set(self.zsw1,7), "SP_OK": bit_set(self.zsw1,8),
                "PLC_CTRL": bit_set(self.zsw1,9), "FREQ_LIM": bit_set(self.zsw1,10),
                "REVERSE": bit_set(self.zsw1,11),
            },
            "log": self.log_lines[-20:],
        }


# ============================================================
# Global state
# ============================================================
drive = None
mb_context = None
mb_store = None
args_global = None

# ============================================================
# Flask app
# ============================================================
app = Flask(__name__)

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Siemens V20 Simulator</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0e17;--card:#111827;--border:#1e293b;--text:#e2e8f0;
--green:#22c55e;--red:#ef4444;--yellow:#eab308;--blue:#3b82f6;
--cyan:#06b6d4;--dim:#475569;--accent:#6366f1}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.header{background:linear-gradient(135deg,#1e293b,#0f172a);border-bottom:2px solid var(--accent);
padding:12px 24px;display:flex;align-items:center;gap:16px}
.header h1{font-size:1.3em;font-weight:600;color:var(--cyan)}
.header .siemens{color:var(--dim);font-size:0.85em;letter-spacing:2px;text-transform:uppercase}
.header .conn{margin-left:auto;display:flex;align-items:center;gap:8px;font-size:0.85em}
.header .dot{width:8px;height:8px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}

.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;padding:16px;max-width:1400px;margin:0 auto}
@media(max-width:1000px){.grid{grid-template-columns:1fr 1fr}}
@media(max-width:650px){.grid{grid-template-columns:1fr}}

.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px}
.card h2{font-size:0.8em;text-transform:uppercase;letter-spacing:2px;color:var(--dim);margin-bottom:14px}
.card.span2{grid-column:span 2}
@media(max-width:650px){.card.span2{grid-column:span 1}}

/* Motor visualization */
.motor-wrap{display:flex;flex-direction:column;align-items:center;gap:12px}
.motor-container{position:relative;width:220px;height:220px}
.motor-body{position:absolute;inset:20px;border-radius:50%;
background:conic-gradient(from 0deg,#1e293b,#334155,#1e293b);
border:3px solid #475569;display:flex;align-items:center;justify-content:center;
box-shadow:0 0 30px rgba(0,0,0,0.5),inset 0 0 20px rgba(0,0,0,0.3)}
.motor-shaft{width:30px;height:30px;border-radius:50%;background:#64748b;
border:2px solid #94a3b8;transition:box-shadow 0.3s}
.motor-shaft.running{box-shadow:0 0 15px var(--cyan)}
.motor-blades{position:absolute;inset:35px;transition:transform 0.05s linear}
.blade{position:absolute;width:4px;height:40%;background:linear-gradient(to top,#64748b,#94a3b8);
top:10%;left:calc(50% - 2px);transform-origin:bottom center;border-radius:2px}
.blade:nth-child(1){transform:rotate(0deg)}.blade:nth-child(2){transform:rotate(60deg)}
.blade:nth-child(3){transform:rotate(120deg)}.blade:nth-child(4){transform:rotate(180deg)}
.blade:nth-child(5){transform:rotate(240deg)}.blade:nth-child(6){transform:rotate(300deg)}

/* Gauge */
.gauge-wrap{position:relative;width:220px;height:130px;overflow:hidden}
.gauge-bg{position:absolute;width:220px;height:220px;border-radius:50%;
background:conic-gradient(from 0.75turn,#1e293b 0deg,#1e293b 180deg);
border:3px solid var(--border)}
.gauge-fill{position:absolute;width:220px;height:220px;border-radius:50%;
background:conic-gradient(from 0.75turn,var(--cyan) 0deg,transparent 0deg);
transition:background 0.15s;clip-path:polygon(0 0,100% 0,100% 50%,0 50%)}
.gauge-center{position:absolute;width:160px;height:160px;border-radius:50%;
background:var(--card);top:30px;left:30px;display:flex;flex-direction:column;
align-items:center;justify-content:center}
.gauge-val{font-size:2.2em;font-weight:700;color:var(--cyan);font-variant-numeric:tabular-nums}
.gauge-unit{font-size:0.8em;color:var(--dim)}
.gauge-ticks{position:absolute;width:220px;height:220px}
.gauge-ticks span{position:absolute;font-size:0.65em;color:var(--dim)}

/* Status LEDs */
.leds{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.led{display:flex;align-items:center;gap:10px;padding:8px 12px;
border-radius:8px;background:#0f172a;border:1px solid var(--border)}
.led-dot{width:14px;height:14px;border-radius:50%;background:#1e293b;
border:2px solid #334155;transition:all 0.3s;flex-shrink:0}
.led-dot.on-green{background:var(--green);border-color:var(--green);box-shadow:0 0 10px var(--green)}
.led-dot.on-red{background:var(--red);border-color:var(--red);box-shadow:0 0 10px var(--red);
animation:blink 0.5s infinite}
.led-dot.on-yellow{background:var(--yellow);border-color:var(--yellow);box-shadow:0 0 10px var(--yellow)}
.led-dot.on-blue{background:var(--blue);border-color:var(--blue);box-shadow:0 0 10px var(--blue)}
.led-dot.on-cyan{background:var(--cyan);border-color:var(--cyan);box-shadow:0 0 10px var(--cyan)}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.2}}
.led-label{font-size:0.8em;color:var(--text)}
.led-label small{display:block;color:var(--dim);font-size:0.85em}

/* State badge */
.state-badge{text-align:center;padding:12px;border-radius:8px;
font-size:1.1em;font-weight:600;letter-spacing:1px;margin-bottom:10px;
transition:all 0.3s}
.state-NOT_READY{background:#1e293b;color:var(--dim)}
.state-READY_TO_SWITCH_ON{background:#422006;color:var(--yellow)}
.state-READY_TO_RUN{background:#083344;color:var(--cyan)}
.state-RUNNING{background:#052e16;color:var(--green)}
.state-FAULT{background:#450a0a;color:var(--red);animation:blink 1s infinite}
.state-COAST_STOP{background:#422006;color:var(--yellow)}
.state-QUICK_STOP{background:#450a0a;color:#fca5a5}

/* Direction */
.dir-display{display:flex;align-items:center;justify-content:center;gap:16px;
padding:10px;font-size:1.1em;margin-top:6px}
.dir-arrow{font-size:1.8em;transition:all 0.3s}
.dir-arrow.active{color:var(--cyan);text-shadow:0 0 10px var(--cyan)}
.dir-arrow.inactive{color:var(--dim)}
.dir-label{font-weight:600;min-width:40px;text-align:center}

/* Bits display */
.bits-grid{display:flex;flex-wrap:wrap;gap:4px}
.bit-chip{padding:4px 8px;border-radius:4px;font-size:0.72em;font-weight:600;
font-family:monospace;background:#0f172a;color:var(--dim);border:1px solid var(--border);transition:all 0.2s}
.bit-chip.on{background:var(--accent);color:white;border-color:var(--accent);
box-shadow:0 0 8px rgba(99,102,241,0.3)}

/* Registers */
.reg-table{width:100%;border-collapse:collapse}
.reg-table td{padding:6px 10px;font-family:monospace;font-size:0.85em;border-bottom:1px solid var(--border)}
.reg-table td:first-child{color:var(--dim);width:100px}
.reg-table td:nth-child(2){color:var(--cyan);font-weight:600;text-align:right;width:80px}
.reg-table td:nth-child(3){color:var(--dim);font-size:0.8em}

/* Log */
.log-box{background:#0a0e17;border:1px solid var(--border);border-radius:8px;
padding:10px;height:180px;overflow-y:auto;font-family:monospace;font-size:0.78em;
color:var(--dim);line-height:1.6}
.log-box div{border-bottom:1px solid #111827;padding:2px 0}

/* Fault button */
.fault-btn{background:linear-gradient(135deg,#991b1b,#7f1d1d);color:white;
border:2px solid var(--red);border-radius:8px;padding:10px 20px;font-size:0.9em;
font-weight:600;cursor:pointer;transition:all 0.2s;width:100%;margin-top:10px}
.fault-btn:hover{background:var(--red);box-shadow:0 0 20px rgba(239,68,68,0.4)}

/* Speed info */
.speed-info{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
.speed-box{background:#0f172a;border:1px solid var(--border);border-radius:8px;
padding:10px;text-align:center}
.speed-box .val{font-size:1.4em;font-weight:700;font-variant-numeric:tabular-nums}
.speed-box .lbl{font-size:0.7em;color:var(--dim);text-transform:uppercase;letter-spacing:1px}
.speed-box.actual .val{color:var(--cyan)}
.speed-box.target .val{color:var(--accent)}

/* Footer bar */
.footer{position:fixed;bottom:0;left:0;right:0;background:#0f172a;
border-top:1px solid var(--border);padding:6px 24px;display:flex;
align-items:center;gap:20px;font-size:0.75em;color:var(--dim)}
.footer span.v{color:var(--accent)}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>SIEMENS SINAMICS V20</h1>
    <div class="siemens">Modbus RTU Simulator</div>
  </div>
  <div class="conn">
    <div class="dot" id="connDot"></div>
    <span id="connText">Modbus Active</span>
  </div>
</div>

<div class="grid">

  <!-- Motor visualization -->
  <div class="card">
    <h2>Silnik</h2>
    <div class="motor-wrap">
      <div class="motor-container">
        <div class="motor-body">
          <div class="motor-blades" id="motorBlades">
            <div class="blade"></div><div class="blade"></div><div class="blade"></div>
            <div class="blade"></div><div class="blade"></div><div class="blade"></div>
          </div>
          <div class="motor-shaft" id="motorShaft"></div>
        </div>
      </div>
      <div class="dir-display">
        <span class="dir-arrow inactive" id="arrLeft">&#9664;&#9664;</span>
        <span class="dir-label" id="dirLabel">STOP</span>
        <span class="dir-arrow inactive" id="arrRight">&#9654;&#9654;</span>
      </div>
    </div>
  </div>

  <!-- Gauge -->
  <div class="card">
    <h2>Czestotliwosc</h2>
    <div style="display:flex;flex-direction:column;align-items:center">
      <div class="gauge-wrap">
        <div class="gauge-bg"></div>
        <div class="gauge-fill" id="gaugeFill"></div>
        <div class="gauge-center">
          <div class="gauge-val" id="gaugeVal">0.0</div>
          <div class="gauge-unit">Hz</div>
        </div>
        <div class="gauge-ticks">
          <span style="bottom:2px;left:8px">0</span>
          <span style="top:42px;left:0">10</span>
          <span style="top:4px;left:42px">20</span>
          <span style="top:-4px;left:50%;transform:translateX(-50%)">30</span>
          <span style="top:4px;right:42px">40</span>
          <span style="top:42px;right:0">50</span>
        </div>
      </div>
      <div class="speed-info">
        <div class="speed-box actual">
          <div class="val" id="actualHz">0.0</div>
          <div class="lbl">Aktualna Hz</div>
        </div>
        <div class="speed-box target">
          <div class="val" id="targetHz">0.0</div>
          <div class="lbl">Zadana Hz</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Status -->
  <div class="card">
    <h2>Status falownika</h2>
    <div class="state-badge" id="stateBadge">NOT_READY</div>
    <div class="leds">
      <div class="led"><div class="led-dot" id="ledReady"></div>
        <div class="led-label">READY<small>Gotowy</small></div></div>
      <div class="led"><div class="led-dot" id="ledRun"></div>
        <div class="led-label">RUN<small>Praca</small></div></div>
      <div class="led"><div class="led-dot" id="ledFault"></div>
        <div class="led-label">FAULT<small>Blad</small></div></div>
      <div class="led"><div class="led-dot" id="ledSpOk"></div>
        <div class="led-label">SP OK<small>Predk. osiagn.</small></div></div>
      <div class="led"><div class="led-dot" id="ledRev"></div>
        <div class="led-label">REVERSE<small>Lewo</small></div></div>
      <div class="led"><div class="led-dot" id="ledPlc"></div>
        <div class="led-label">PLC CTRL<small>Ster. zdalne</small></div></div>
    </div>
    <button class="fault-btn" onclick="simFault()">&#9888; SYMULUJ FAULT</button>
  </div>

  <!-- STW1 bits -->
  <div class="card">
    <h2>STW1 — Slowo sterujace (od mastera)</h2>
    <div class="bits-grid" id="stwBits"></div>
    <table class="reg-table" style="margin-top:14px">
      <tr><td>Rejestr</td><td>40100</td><td>Holding Register</td></tr>
      <tr><td>Hex</td><td id="stwHex">0x0000</td><td></td></tr>
      <tr><td>Dec</td><td id="stwDec">0</td><td></td></tr>
    </table>
  </div>

  <!-- ZSW1 bits -->
  <div class="card">
    <h2>ZSW1 — Slowo statusu (do mastera)</h2>
    <div class="bits-grid" id="zswBits"></div>
    <table class="reg-table" style="margin-top:14px">
      <tr><td>Rejestr</td><td>40110</td><td>Holding Register</td></tr>
      <tr><td>Hex</td><td id="zswHex">0x0000</td><td></td></tr>
      <tr><td>Dec</td><td id="zswDec">0</td><td></td></tr>
    </table>
  </div>

  <!-- Registers -->
  <div class="card">
    <h2>Rejestry Modbus</h2>
    <table class="reg-table">
      <tr><td>40100</td><td id="r100">0</td><td>STW1 Control Word</td></tr>
      <tr><td>40101</td><td id="r101">0</td><td>HSW Speed Setpoint</td></tr>
      <tr><td>40110</td><td id="r110">0</td><td>ZSW1 Status Word</td></tr>
      <tr><td>40111</td><td id="r111">0</td><td>HIW Actual Speed</td></tr>
    </table>
    <table class="reg-table" style="margin-top:10px;border-top:2px solid var(--border)">
      <tr><td>HSW</td><td id="hswHz">0.0 Hz</td><td>= <span id="hswPct">0</span>%</td></tr>
      <tr><td>HIW</td><td id="hiwHz">0.0 Hz</td><td>= <span id="hiwPct">0</span>%</td></tr>
    </table>
  </div>

  <!-- Log -->
  <div class="card span2">
    <h2>Log zdarzen</h2>
    <div class="log-box" id="logBox"></div>
  </div>

</div>

<div class="footer">
  <span>Symulator <span class="v">Siemens V20</span> | Modbus RTU/TCP</span>
  <span>Slave ID: <span class="v" id="ftSlave">1</span></span>
  <span>Max freq: <span class="v" id="ftFreq">50</span> Hz</span>
  <span>Refresh: 100ms</span>
</div>

<script>
let motorAngle = 0;
let lastSpeed = 0;

function update() {
  fetch('/api/status')
    .then(r => r.json())
    .then(d => {
      // State badge
      const badge = document.getElementById('stateBadge');
      badge.textContent = d.state;
      badge.className = 'state-badge state-' + d.state;

      // Gauge
      const pct = d.speed_pct;
      const deg = (pct / 100) * 180;
      document.getElementById('gaugeFill').style.background =
        `conic-gradient(from 0.75turn, var(--cyan) ${deg}deg, transparent ${deg}deg)`;
      document.getElementById('gaugeVal').textContent = d.freq.toFixed(1);
      document.getElementById('actualHz').textContent = d.freq.toFixed(1);
      document.getElementById('targetHz').textContent = d.target_freq.toFixed(1);

      // Motor rotation
      lastSpeed = pct;
      const shaft = document.getElementById('motorShaft');
      shaft.className = pct > 0 ? 'motor-shaft running' : 'motor-shaft';

      // Direction
      const isRev = d.direction < 0;
      const isRun = d.bits_zsw.RUNNING;
      document.getElementById('arrLeft').className = 'dir-arrow ' + (isRun && isRev ? 'active' : 'inactive');
      document.getElementById('arrRight').className = 'dir-arrow ' + (isRun && !isRev ? 'active' : 'inactive');
      document.getElementById('dirLabel').textContent = !isRun ? 'STOP' : (isRev ? 'REV' : 'FWD');
      document.getElementById('dirLabel').style.color = !isRun ? 'var(--dim)' : 'var(--cyan)';

      // LEDs
      setLed('ledReady', d.bits_zsw.READY_RUN, 'on-green');
      setLed('ledRun', d.bits_zsw.RUNNING, 'on-blue');
      setLed('ledFault', d.bits_zsw.FAULT, 'on-red');
      setLed('ledSpOk', d.bits_zsw.SP_OK, 'on-cyan');
      setLed('ledRev', d.bits_zsw.REVERSE, 'on-yellow');
      setLed('ledPlc', d.bits_zsw.PLC_CTRL, 'on-green');

      // STW1 bits
      renderBits('stwBits', d.bits_stw);
      document.getElementById('stwHex').textContent = '0x' + d.stw1.toString(16).toUpperCase().padStart(4,'0');
      document.getElementById('stwDec').textContent = d.stw1;

      // ZSW1 bits
      renderBits('zswBits', d.bits_zsw);
      document.getElementById('zswHex').textContent = '0x' + d.zsw1.toString(16).toUpperCase().padStart(4,'0');
      document.getElementById('zswDec').textContent = d.zsw1;

      // Registers
      document.getElementById('r100').textContent = d.stw1;
      document.getElementById('r101').textContent = d.hsw;
      document.getElementById('r110').textContent = d.zsw1;
      document.getElementById('r111').textContent = d.hiw;

      const maxF = 50.0;
      const hswHz = (d.hsw / 16384 * maxF);
      const hiwHz = (d.hiw / 16384 * maxF);
      document.getElementById('hswHz').textContent = hswHz.toFixed(1) + ' Hz';
      document.getElementById('hiwHz').textContent = hiwHz.toFixed(1) + ' Hz';
      document.getElementById('hswPct').textContent = (d.hsw / 16384 * 100).toFixed(0);
      document.getElementById('hiwPct').textContent = (d.hiw / 16384 * 100).toFixed(0);

      // Log
      const logBox = document.getElementById('logBox');
      const atBottom = logBox.scrollHeight - logBox.scrollTop - logBox.clientHeight < 30;
      logBox.innerHTML = d.log.map(l => '<div>' + l + '</div>').join('');
      if (atBottom) logBox.scrollTop = logBox.scrollHeight;

      // Conn dot
      document.getElementById('connDot').style.background = 'var(--green)';
      document.getElementById('connText').textContent = 'Modbus Active | STW1=0x' +
        d.stw1.toString(16).toUpperCase().padStart(4,'0');
    })
    .catch(() => {
      document.getElementById('connDot').style.background = 'var(--red)';
      document.getElementById('connText').textContent = 'Brak polaczenia';
    });
}

function setLed(id, on, cls) {
  const el = document.getElementById(id);
  el.className = 'led-dot' + (on ? ' ' + cls : '');
}

function renderBits(containerId, bits) {
  const c = document.getElementById(containerId);
  c.innerHTML = Object.entries(bits).map(([k,v]) =>
    `<span class="bit-chip ${v?'on':''}">${k}</span>`
  ).join('');
}

function simFault() {
  fetch('/api/fault', {method:'POST'});
}

// Motor animation loop
function animateMotor() {
  if (lastSpeed > 0.5) {
    const dir = document.getElementById('arrLeft').classList.contains('active') ? -1 : 1;
    motorAngle += (lastSpeed / 100) * 8 * dir;
  }
  document.getElementById('motorBlades').style.transform = `rotate(${motorAngle}deg)`;
  requestAnimationFrame(animateMotor);
}

animateMotor();
setInterval(update, 100);
update();
</script>
</body>
</html>"""


@app.route('/')
def index():
    return Response(HTML_PAGE, mimetype='text/html')


@app.route('/api/status')
def api_status():
    if drive:
        return jsonify(drive.to_dict())
    return jsonify({"error": "not ready"})


@app.route('/api/fault', methods=['POST'])
def api_fault():
    if drive:
        drive.sim_fault = True
    return jsonify({"ok": True})


# ============================================================
# Modbus + update loop
# ============================================================
def update_loop():
    global drive, mb_context, args_global
    while True:
        try:
            ctx = mb_context[0]  # single=True: dowolny klucz zwraca ten sam context
            hr = ctx.store['h']
            stw1 = hr.getValues(REG_STW1, 1)[0]
            hsw = hr.getValues(REG_HSW, 1)[0]
            drive.update(stw1, hsw)
            hr.setValues(REG_ZSW1, [drive.zsw1])
            hr.setValues(REG_HIW, [drive.hiw])
            time.sleep(0.05)
        except Exception as e:
            time.sleep(0.1)


def start_modbus_server():
    global mb_context, args_global
    try:
        if args_global.tcp:
            print(f"  Modbus TCP na porcie {args_global.tcp_port}")
            StartTcpServer(
                context=mb_context,
                address=("0.0.0.0", args_global.tcp_port),
                framer=FramerType.RTU,
            )
        else:
            print(f"  Modbus RTU na {args_global.port} @ {args_global.baudrate}")
            StartSerialServer(
                context=mb_context,
                port=args_global.port,
                baudrate=args_global.baudrate,
                bytesize=8, parity='N', stopbits=1,
                timeout=1,
            )
    except Exception as e:
        print(f"  BLAD Modbus: {e}")
        if not args_global.tcp:
            print(f"  Sprawdz port {args_global.port}")
            print(f"  python -m serial.tools.list_ports")


# ============================================================
# Main
# ============================================================
def main():
    global drive, mb_context, mb_store, args_global

    parser = argparse.ArgumentParser(description="V20 Simulator + Web GUI")
    conn = parser.add_argument_group("Polaczenie Modbus")
    conn.add_argument("--port", default="/dev/ttyUSB0")
    conn.add_argument("--baudrate", type=int, default=9600)
    conn.add_argument("--slave-id", type=int, default=1)
    conn.add_argument("--tcp", action="store_true", help="Modbus TCP")
    conn.add_argument("--tcp-port", type=int, default=502)

    motor = parser.add_argument_group("Silnik")
    motor.add_argument("--max-freq", type=float, default=50.0)
    motor.add_argument("--accel-time", type=float, default=5.0)
    motor.add_argument("--decel-time", type=float, default=5.0)

    web = parser.add_argument_group("Web GUI")
    web.add_argument("--web-port", type=int, default=5000, help="Port HTTP (default: 5000)")
    web.add_argument("--no-browser", action="store_true", help="Nie otwieraj przegladarki")

    args = parser.parse_args()
    args_global = args

    print(r"""
   _____ _                                  __     ______  ___
  / ___/(_)__  ____ ___  ___  ____  _____   \ \   / /___ \/ _ \
  \__ \/ / _ \/ __ `__ \/ _ \/ __ \/ ___/    \ \ / /  __) | | | |
 ___/ / /  __/ / / / / /  __/ / / (__  )      \ V /  / __/| |_| |
/____/_/\___/_/ /_/ /_/\___/_/ /_/____/        \_/  |_____|\___/

        S Y M U L A T O R  +  W E B   G U I
    """)

    # Drive
    drive = V20(max_freq=args.max_freq, accel=args.accel_time, decel=args.decel_time)
    drive._log("Symulator uruchomiony")
    drive._log(f"Max freq: {args.max_freq} Hz, Accel: {args.accel_time}s, Decel: {args.decel_time}s")

    # Pymodbus debug logging
    logging.basicConfig()
    log = logging.getLogger('pymodbus')
    log.setLevel(logging.DEBUG)

    # Modbus datastore
    mb_store = ModbusSequentialDataBlock(0, [0] * 1000)
    slave_ctx = ModbusSlaveContext(
        di=ModbusSequentialDataBlock(0, [0]*100),
        co=ModbusSequentialDataBlock(0, [0]*100),
        hr=mb_store,
        ir=ModbusSequentialDataBlock(0, [0]*100),
    )
    mb_context = ModbusServerContext(devices=slave_ctx, single=True)

    # Start threads
    threading.Thread(target=update_loop, daemon=True).start()
    threading.Thread(target=start_modbus_server, daemon=True).start()

    drive._log(f"Slave ID: {args.slave_id}")
    if args.tcp:
        drive._log(f"Modbus TCP port: {args.tcp_port}")
    else:
        drive._log(f"Modbus RTU: {args.port} @ {args.baudrate}")

    print(f"  Web GUI:  http://localhost:{args.web_port}")
    print(f"  Slave ID: {args.slave_id}")
    if args.tcp:
        print(f"  Modbus:   TCP port {args.tcp_port}")
    else:
        print(f"  Modbus:   RTU {args.port} @ {args.baudrate}")
    print()

    # Open browser
    if not args.no_browser:
        import webbrowser
        webbrowser.open(f"http://localhost:{args.web_port}")

    # Start Flask
    signal.signal(signal.SIGINT, lambda s,f: sys.exit(0))
    app.run(host="0.0.0.0", port=args.web_port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
