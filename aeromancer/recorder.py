"""Reads the meter forever and stores what it says, reconnecting when unplugged."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from .device import CO2Monitor, DeviceNotFound
from .store import Store

log = logging.getLogger(__name__)

RETRY_SECONDS = 5.0


@dataclass
class RecorderStatus:
    """Shared with the dashboard so it can say whether recording is live."""

    connected: bool = False
    device: str | None = None
    error: str | None = None
    last_reading: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **kwargs) -> None:
        with self.lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "connected": self.connected,
                "device": self.device,
                "error": self.error,
                "last_reading": self.last_reading,
            }


def record(
    db_path,
    device: str | None = None,
    min_interval: float = 5.0,
    status: RecorderStatus | None = None,
    stop: threading.Event | None = None,
) -> None:
    """Store at most one reading per quantity every ``min_interval`` seconds."""
    status = status or RecorderStatus()
    stop = stop or threading.Event()
    store = Store(db_path)
    last_stored: dict[str, float] = {}
    try:
        while not stop.is_set():
            try:
                with CO2Monitor(device) as monitor:
                    log.info("recording from %s into %s", monitor.path, db_path)
                    status.update(connected=True, device=monitor.path, error=None)
                    for reading in monitor.readings():
                        if stop.is_set():
                            break
                        if reading is None:
                            continue
                        log.debug("%s = %s", reading.quantity, reading.value)
                        if reading.ts - last_stored.get(reading.quantity, 0) < min_interval:
                            continue
                        store.add([reading])
                        last_stored[reading.quantity] = reading.ts
                        status.update(last_reading=reading.ts)
            except (DeviceNotFound, OSError) as e:
                if status.error != str(e):
                    log.warning("%s; retrying every %.0f s", e, RETRY_SECONDS)
                status.update(connected=False, error=str(e))
                stop.wait(RETRY_SECONDS)
    finally:
        status.update(connected=False)
        store.close()


def start_in_background(db_path, **kwargs) -> tuple[RecorderStatus, threading.Event]:
    status, stop = RecorderStatus(), threading.Event()
    threading.Thread(
        target=record,
        args=(db_path,),
        kwargs={**kwargs, "status": status, "stop": stop},
        name="recorder",
        daemon=True,
    ).start()
    return status, stop
