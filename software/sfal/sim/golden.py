"""Executa um roteiro de referência (firmware/test/golden/*.script) no firmware carregado como
biblioteca e devolve o traço. O teste nativo em C++ faz o mesmo e os dois têm de bater."""

from __future__ import annotations

from pathlib import Path

from .firmware_lib import BTN_CALL, BTN_FAIL, BTN_START, FirmwareStation

STEP_MS = 10
_BUTTONS = {"start": BTN_START, "fail": BTN_FAIL, "call": BTN_CALL}


def run_script(script: Path, station_id: str = "asm", boot_id: int = 7) -> str:
    lines: list[str] = []
    clock = {"now": 0}

    def publish(topic: str, payload: str, qos: int, retain: bool) -> bool:
        lines.append(f"{clock['now']} pub {topic} q{qos} {'r' if retain else '-'} {payload}")
        return True

    fw = FirmwareStation(station_id, publish, boot_id=boot_id)
    last_out = 0

    def advance(until: int) -> None:
        nonlocal last_out
        while clock["now"] < until:
            clock["now"] += STEP_MS
            fw.set_time(clock["now"])
            fw.loop()
            out = fw.outputs & 7
            if out != last_out:
                last_out = out
                lines.append(f"{clock['now']} out {out}")

    for raw in script.read_text().splitlines():
        if not raw or raw.startswith("#"):
            continue
        t, cmd, *rest = raw.split(" ", 3)
        advance(int(t))
        if cmd == "end":
            break
        a = rest[0]
        tail = " ".join(rest[1:])
        if cmd == "link":
            fw.set_link(a == "1")
        elif cmd == "temp":
            fw.set_temp(None if a == "nan" else float(a))
        elif cmd == "scan":
            fw.push_scan(a)
        elif cmd == "btn":
            fw.set_button(_BUTTONS[a], tail == "1")
        elif cmd == "rx":
            fw.on_message(f"sfal/v1/{station_id}/cmd/{a}", tail)
    fw.close()
    return "\n".join(lines) + "\n"
