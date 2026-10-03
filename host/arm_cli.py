#!/usr/bin/env python3
"""
Minimal terminal controller (handy on a headless Raspberry Pi or for quick tests).

  python arm_cli.py --port COM5            # Windows
  python arm_cli.py --port /dev/ttyUSB0    # Linux / Pi

Type any firmware command, e.g.
  90,90,90,90,90,180     HOME     J 5 90     SPEED 60     MODE POT     ?     OFF
Type 'quit' to exit.
"""

import argparse
import threading
import time

import serial


def reader(ser):
    while ser.is_open:
        try:
            line = ser.readline()
        except Exception:
            break
        if line:
            print("<", line.decode(errors="replace").strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0.1)
    time.sleep(2.0)  # ESP32 auto-reset
    threading.Thread(target=reader, args=(ser,), daemon=True).start()
    try:
        while True:
            cmd = input("> ").strip()
            if cmd.lower() in ("quit", "exit"):
                break
            if cmd:
                ser.write((cmd + "\n").encode())
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        ser.write(b"STOP\n")
        ser.close()


if __name__ == "__main__":
    main()
