"""
Non-blocking serial interface with the MCU.

Protocol (ASCII line-based):
  MCU  → Linux : DIST:<mm>\\n          (distance reading, every ~100 ms)
  Linux → MCU  : CMD:<TYPE>:<ARG>\\n   (feedback commands)

CMD types:
  LED   — arg: GREEN | RED | SPLIT | OFF
  BUZZ  — arg: <count>   (number of buzzes)
"""
from __future__ import annotations

import logging
import threading

import serial

log = logging.getLogger(__name__)


class SerialComms:
    def __init__(self, port: str, baud: int):
        self._ser = serial.Serial(port, baud, timeout=0.1)
        self._dist: float | None = None
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        log.info("Serial opened on %s @ %d baud", port, baud)

    # ------------------------------------------------------------------
    def latest_distance(self) -> float | None:
        with self._lock:
            return self._dist

    def send_command(self, cmd: str) -> None:
        """Send e.g. 'LED:GREEN' or 'BUZZ:3' — prefix CMD: is added here."""
        line = f"CMD:{cmd}\n"
        try:
            self._ser.write(line.encode("ascii"))
        except serial.SerialException as exc:
            log.warning("Serial write error: %s", exc)

    def close(self) -> None:
        self._running = False
        self._ser.close()

    # ------------------------------------------------------------------
    def _reader(self) -> None:
        while self._running:
            try:
                raw = self._ser.readline()
                if not raw:
                    continue
                line = raw.decode("ascii", errors="ignore").strip()
                if line.startswith("DIST:"):
                    val = float(line[5:])
                    with self._lock:
                        self._dist = val
            except (serial.SerialException, ValueError) as exc:
                log.debug("Serial read: %s", exc)
