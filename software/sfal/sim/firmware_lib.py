"""Carrega o núcleo do firmware (C++) como biblioteca e expõe uma estação por objeto.

É o mesmo código-fonte gravado no ESP32 (firmware/lib/station_core). Aqui a camada de hardware
são variáveis que o simulador escreve: relógio, botões, temperatura, leitor e enlace.
"""

from __future__ import annotations

import ctypes
import subprocess
from collections.abc import Callable
from pathlib import Path

from ..paths import FIRMWARE_DIR

BTN_START, BTN_FAIL, BTN_CALL = 0, 1, 2
OUT_GREEN, OUT_YELLOW, OUT_RED, OUT_BUZZER = 1, 2, 4, 8
STATES = ("IDLE", "WAIT", "RUNNING", "BLOCKED")

_PUBLISH_FN = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int
)
_lib: ctypes.CDLL | None = None


def _sources(firmware: Path) -> list[Path]:
    return [*sorted((firmware / "lib" / "station_core" / "src").glob("*")), firmware / "sim" / "capi.cpp"]


def build(firmware: Path = FIRMWARE_DIR, force: bool = False) -> Path:
    """Compila a biblioteca se ela não existe ou se algum fonte do núcleo é mais novo."""
    lib = firmware / "sim" / "build" / "libstation_core.so"
    stale = force or not lib.exists() or any(s.stat().st_mtime > lib.stat().st_mtime for s in _sources(firmware))
    if stale:
        subprocess.run([str(firmware / "sim" / "build.sh")], check=True, capture_output=True, text=True)
    return lib


def load() -> ctypes.CDLL:
    global _lib
    if _lib is None:
        lib = ctypes.CDLL(str(build()))
        lib.sc_create.restype = ctypes.c_void_p
        lib.sc_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32, _PUBLISH_FN, ctypes.c_void_p]
        for name, args in {
            "sc_destroy": [],
            "sc_set_time": [ctypes.c_uint32],
            "sc_set_button": [ctypes.c_int, ctypes.c_int],
            "sc_set_temp": [ctypes.c_int, ctypes.c_float],
            "sc_push_scan": [ctypes.c_char_p],
            "sc_set_link": [ctypes.c_int],
            "sc_on_message": [ctypes.c_char_p, ctypes.c_char_p],
            "sc_loop": [],
        }.items():
            fn = getattr(lib, name)
            fn.restype = None
            fn.argtypes = [ctypes.c_void_p, *args]
        for name in ("sc_outputs", "sc_state", "sc_call_active", "sc_queued"):
            fn = getattr(lib, name)
            fn.restype = ctypes.c_int
            fn.argtypes = [ctypes.c_void_p]
        for name in ("sc_unit", "sc_block_reason", "sc_will_topic", "sc_will_payload", "sc_command_filter"):
            fn = getattr(lib, name)
            fn.restype = ctypes.c_char_p
            fn.argtypes = [ctypes.c_void_p]
        _lib = lib
    return _lib


Publish = Callable[[str, str, int, bool], bool]


class FirmwareStation:
    """Uma instância do firmware. `publish(topic, payload, qos, retain) -> bool` é a saída MQTT."""

    def __init__(self, station_id: str, publish: Publish, boot_id: int = 1, fw_version: str = "1.0.0"):
        self.id = station_id
        self._lib = load()
        self._publish = publish

        def _cb(_user, topic, payload, qos, retain):
            return 1 if self._publish(topic.decode(), payload.decode(), qos, bool(retain)) else 0

        self._cb = _PUBLISH_FN(_cb)  # manter a referência viva
        self._h = self._lib.sc_create(station_id.encode(), fw_version.encode(), boot_id & 0xFFFFFFFF, self._cb, None)

    def close(self) -> None:
        if self._h:
            self._lib.sc_destroy(self._h)
            self._h = None

    def __del__(self):
        self.close()

    # entradas
    def set_time(self, ms: int) -> None:
        self._lib.sc_set_time(self._h, int(ms) & 0xFFFFFFFF)

    def set_button(self, button: int, pressed: bool) -> None:
        self._lib.sc_set_button(self._h, button, 1 if pressed else 0)

    def set_temp(self, celsius: float | None) -> None:
        self._lib.sc_set_temp(self._h, 0 if celsius is None else 1, 0.0 if celsius is None else celsius)

    def push_scan(self, code: str) -> None:
        self._lib.sc_push_scan(self._h, code.encode())

    def set_link(self, up: bool) -> None:
        self._lib.sc_set_link(self._h, 1 if up else 0)

    def on_message(self, topic: str, payload: str) -> None:
        self._lib.sc_on_message(self._h, topic.encode(), payload.encode())

    def loop(self) -> None:
        self._lib.sc_loop(self._h)

    # saídas e estado
    @property
    def outputs(self) -> int:
        return self._lib.sc_outputs(self._h)

    @property
    def state(self) -> str:
        return STATES[self._lib.sc_state(self._h)]

    @property
    def unit(self) -> str:
        return self._lib.sc_unit(self._h).decode()

    @property
    def block_reason(self) -> str:
        return self._lib.sc_block_reason(self._h).decode()

    @property
    def call_active(self) -> bool:
        return bool(self._lib.sc_call_active(self._h))

    @property
    def queued(self) -> int:
        return self._lib.sc_queued(self._h)

    @property
    def will(self) -> tuple[str, str]:
        return self._lib.sc_will_topic(self._h).decode(), self._lib.sc_will_payload(self._h).decode()

    @property
    def command_filter(self) -> str:
        return self._lib.sc_command_filter(self._h).decode()
