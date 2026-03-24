#!/usr/bin/env python3
"""
Klient testowy Modbus - symuluje komendy z IDEC FT2J
=====================================================
Uzyj tego do testowania symulatora V20 bez fizycznego panelu.

Uzycie:
  1. Uruchom symulator:  python v20_simulator.py --tcp --tcp-port 502
  2. Uruchom klienta:    python test_client.py --tcp --tcp-port 502

  Lub przez port szeregowy (potrzebujesz 2 porty + null modem / virtual COM):
  1. Uruchom symulator:  python v20_simulator.py --port COM3
  2. Uruchom klienta:    python test_client.py --port COM4
"""

import argparse
import time
import sys

try:
    from pymodbus.client import ModbusTcpClient, ModbusSerialClient
    PYMODBUS_V3 = True
except ImportError:
    try:
        from pymodbus.client.sync import ModbusTcpClient, ModbusSerialClient
        PYMODBUS_V3 = False
    except ImportError:
        print("BLAD: Zainstaluj pymodbus:")
        print("  pip install pymodbus pyserial")
        sys.exit(1)


# Adresy rejestrow (0-based dla pymodbus client)
REG_STW1 = 99    # 40100
REG_HSW  = 100   # 40101
REG_ZSW1 = 109   # 40110
REG_HIW  = 110   # 40111

SPEED_100_PCT = 16384


def hz_to_raw(freq_hz: float, max_freq: float = 50.0) -> int:
    """Przelicz Hz na wartosc surowa (0-16384)."""
    return int((freq_hz / max_freq) * SPEED_100_PCT)


def raw_to_hz(raw: int, max_freq: float = 50.0) -> float:
    """Przelicz wartosc surowa na Hz."""
    return (raw / SPEED_100_PCT) * max_freq


def bit_set(word: int, bit: int) -> bool:
    return bool(word & (1 << bit))


def read_status(client, slave_id):
    """Odczytaj status z falownika."""
    result = client.read_holding_registers(REG_ZSW1, count=2, device_id=slave_id)
    if result.isError():
        print(f"  BLAD odczytu: {result}")
        return None, None

    zsw1 = result.registers[0]
    hiw = result.registers[1]
    return zsw1, hiw


def print_status(zsw1, hiw):
    """Wyswietl status."""
    if zsw1 is None:
        print("  Status: BRAK KOMUNIKACJI")
        return

    freq = raw_to_hz(hiw)

    flags = []
    if bit_set(zsw1, 0): flags.append("READY_ON")
    if bit_set(zsw1, 1): flags.append("READY_RUN")
    if bit_set(zsw1, 2): flags.append("RUNNING")
    if bit_set(zsw1, 3): flags.append("FAULT")
    if not bit_set(zsw1, 4): flags.append("OFF2_ACTIVE")
    if not bit_set(zsw1, 5): flags.append("OFF3_ACTIVE")
    if bit_set(zsw1, 6): flags.append("ON_INHIBIT")
    if bit_set(zsw1, 7): flags.append("WARNING")
    if bit_set(zsw1, 8): flags.append("SP_OK")
    if bit_set(zsw1, 11): flags.append("REVERSE")

    bar_len = 25
    bar_fill = int((hiw / SPEED_100_PCT) * bar_len) if SPEED_100_PCT > 0 else 0
    bar_fill = min(bar_fill, bar_len)
    bar = "█" * bar_fill + "░" * (bar_len - bar_fill)

    print(f"  ZSW1: 0x{zsw1:04X}  [{', '.join(flags)}]")
    print(f"  HIW:  [{bar}] {freq:.1f} Hz  (raw: {hiw})")


def write_control(client, slave_id, stw1, hsw):
    """Wyslij slowo sterujace i predkosc."""
    result = client.write_registers(REG_STW1, [stw1, hsw], device_id=slave_id)
    if result.isError():
        print(f"  BLAD zapisu: {result}")
        return False
    return True


def interactive_mode(client, slave_id):
    """Tryb interaktywny - menu sterowania."""
    stw1 = 0x0000
    hsw = 0

    print()
    print("=" * 55)
    print("  KLIENT TESTOWY - STEROWANIE FALOWNIKIEM V20")
    print("=" * 55)

    while True:
        print()
        print("-" * 55)
        print("  MENU:")
        print("    1 - Przygotuj (STW1 = 0x047E)")
        print("    2 - START Forward (STW1 = 0x047F)")
        print("    3 - START Reverse (STW1 = 0x0C7F)")
        print("    4 - STOP (bit ON = 0)")
        print("    5 - E-STOP / Quick Stop (OFF3 = 0)")
        print("    6 - Coast Stop (OFF2 = 0)")
        print("    7 - Ustaw predkosc [Hz]")
        print("    8 - Fault ACK")
        print("    9 - Odczytaj status")
        print("    0 - Reset (STW1 = 0x0000)")
        print("    s - Status ciagle (co 0.5s, ESC=stop)")
        print("    q - Wyjscie")
        print("-" * 55)

        choice = input("  Wybierz> ").strip().lower()

        if choice == '1':
            # Przygotowanie - bity 1-6 + 10
            stw1 = 0x047E
            print(f"  -> STW1 = 0x{stw1:04X} (READY)")
            write_control(client, slave_id, stw1, hsw)
            time.sleep(0.3)
            zsw1, hiw = read_status(client, slave_id)
            print_status(zsw1, hiw)

        elif choice == '2':
            # START Forward
            stw1 = 0x047F
            print(f"  -> STW1 = 0x{stw1:04X} (RUN FORWARD)")
            write_control(client, slave_id, stw1, hsw)
            time.sleep(0.3)
            zsw1, hiw = read_status(client, slave_id)
            print_status(zsw1, hiw)

        elif choice == '3':
            # START Reverse
            stw1 = 0x0C7F
            print(f"  -> STW1 = 0x{stw1:04X} (RUN REVERSE)")
            write_control(client, slave_id, stw1, hsw)
            time.sleep(0.3)
            zsw1, hiw = read_status(client, slave_id)
            print_status(zsw1, hiw)

        elif choice == '4':
            # STOP (normalny - rampa)
            stw1 = stw1 & 0xFFFE  # clear bit 0
            print(f"  -> STW1 = 0x{stw1:04X} (STOP)")
            write_control(client, slave_id, stw1, hsw)
            time.sleep(0.3)
            zsw1, hiw = read_status(client, slave_id)
            print_status(zsw1, hiw)

        elif choice == '5':
            # E-STOP / Quick stop - OFF3 = 0
            stw1 = stw1 & 0xFFFB  # clear bit 2
            stw1 = stw1 & 0xFFFE  # clear bit 0 tez
            print(f"  -> STW1 = 0x{stw1:04X} (QUICK STOP)")
            write_control(client, slave_id, stw1, hsw)
            time.sleep(0.3)
            zsw1, hiw = read_status(client, slave_id)
            print_status(zsw1, hiw)

        elif choice == '6':
            # Coast stop - OFF2 = 0
            stw1 = stw1 & 0xFFFD  # clear bit 1
            stw1 = stw1 & 0xFFFE  # clear bit 0
            print(f"  -> STW1 = 0x{stw1:04X} (COAST STOP)")
            write_control(client, slave_id, stw1, hsw)
            time.sleep(0.3)
            zsw1, hiw = read_status(client, slave_id)
            print_status(zsw1, hiw)

        elif choice == '7':
            # Ustaw predkosc
            try:
                freq = float(input("  Podaj czestotliwosc [Hz] (0-50): "))
                freq = max(0.0, min(50.0, freq))
                hsw = hz_to_raw(freq)
                print(f"  -> HSW = {hsw} (raw) = {freq:.1f} Hz")
                write_control(client, slave_id, stw1, hsw)
            except ValueError:
                print("  Nieprawidlowa wartosc!")

        elif choice == '8':
            # Fault ACK
            stw1_ack = stw1 | 0x0080  # set bit 7
            print(f"  -> STW1 = 0x{stw1_ack:04X} (FAULT ACK)")
            write_control(client, slave_id, stw1_ack, hsw)
            time.sleep(0.5)
            # Zdejmij bit ACK
            stw1 = stw1 & 0xFF7F
            write_control(client, slave_id, stw1, hsw)
            zsw1, hiw = read_status(client, slave_id)
            print_status(zsw1, hiw)

        elif choice == '9':
            # Odczyt statusu
            zsw1, hiw = read_status(client, slave_id)
            print_status(zsw1, hiw)

        elif choice == '0':
            # Reset
            stw1 = 0x0000
            hsw = 0
            print(f"  -> STW1 = 0x{stw1:04X}, HSW = 0 (RESET)")
            write_control(client, slave_id, stw1, hsw)
            time.sleep(0.3)
            zsw1, hiw = read_status(client, slave_id)
            print_status(zsw1, hiw)

        elif choice == 's':
            # Ciagly odczyt statusu
            print("  Ciagly odczyt (Ctrl+C = stop)...")
            try:
                while True:
                    zsw1, hiw = read_status(client, slave_id)
                    if zsw1 is not None:
                        freq = raw_to_hz(hiw)
                        running = "RUN" if bit_set(zsw1, 2) else "---"
                        fault = "FAULT!" if bit_set(zsw1, 3) else ""
                        rev = "REV" if bit_set(zsw1, 11) else "FWD"
                        sp_ok = "OK" if bit_set(zsw1, 8) else ".."
                        print(f"\r  {running} {rev} {freq:6.1f} Hz  SP:{sp_ok}  {fault}    ", end="")
                    time.sleep(0.5)
            except KeyboardInterrupt:
                print("\n  Zatrzymano.")

        elif choice == 'q':
            print("  Zamykanie...")
            break

        else:
            print("  Nieznana opcja!")


def auto_test(client, slave_id):
    """Automatyczny test sekwencji startowej."""
    print()
    print("=" * 55)
    print("  AUTOMATYCZNY TEST SEKWENCJI V20")
    print("=" * 55)

    steps = [
        ("Reset",           0x0000, 0,     1.0),
        ("Przygotowanie",   0x047E, 0,     1.0),
        ("START FWD 25Hz",  0x047F, hz_to_raw(25.0), 6.0),
        ("Zmiana na 50Hz",  0x047F, hz_to_raw(50.0), 6.0),
        ("Zmiana na 10Hz",  0x047F, hz_to_raw(10.0), 6.0),
        ("START REV 30Hz",  0x0C7F, hz_to_raw(30.0), 6.0),
        ("STOP (rampa)",    0x047E, hz_to_raw(30.0), 6.0),
        ("Reset",           0x0000, 0,     2.0),
    ]

    for name, stw1, hsw, wait in steps:
        print(f"\n  >>> {name}  (STW1=0x{stw1:04X}, HSW={hsw})")
        write_control(client, slave_id, stw1, hsw)

        # Monitorowanie przez 'wait' sekund
        t_start = time.time()
        while time.time() - t_start < wait:
            zsw1, hiw = read_status(client, slave_id)
            if zsw1 is not None:
                freq = raw_to_hz(hiw)
                running = "RUN" if bit_set(zsw1, 2) else "---"
                rev = "REV" if bit_set(zsw1, 11) else "FWD"
                print(f"\r      {running} {rev} {freq:6.1f} Hz  ZSW1=0x{zsw1:04X}    ", end="")
            time.sleep(0.3)
        print()

    print("\n  TEST ZAKONCZONY!")


def main():
    parser = argparse.ArgumentParser(description="Klient testowy Modbus dla symulatora V20")

    parser.add_argument("--port", default="/dev/ttyUSB0", help="Port szeregowy")
    parser.add_argument("--baudrate", type=int, default=9600, help="Baudrate")
    parser.add_argument("--slave-id", type=int, default=1, help="Adres slave")
    parser.add_argument("--tcp", action="store_true", help="Uzyj Modbus TCP")
    parser.add_argument("--tcp-host", default="localhost", help="Host TCP")
    parser.add_argument("--tcp-port", type=int, default=502, help="Port TCP")
    parser.add_argument("--auto-test", action="store_true",
                        help="Uruchom automatyczny test sekwencji")

    args = parser.parse_args()

    # Polaczenie
    if args.tcp:
        client = ModbusTcpClient(args.tcp_host, port=args.tcp_port)
        print(f"  Laczenie TCP -> {args.tcp_host}:{args.tcp_port}...")
    else:
        client = ModbusSerialClient(
            port=args.port,
            baudrate=args.baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=1,
        )
        print(f"  Laczenie RTU -> {args.port} @ {args.baudrate}...")

    if not client.connect():
        print("  BLAD: Nie mozna polaczyc!")
        sys.exit(1)

    print("  Polaczono!")

    try:
        if args.auto_test:
            auto_test(client, args.slave_id)
        else:
            interactive_mode(client, args.slave_id)
    finally:
        client.close()


if __name__ == "__main__":
    main()
