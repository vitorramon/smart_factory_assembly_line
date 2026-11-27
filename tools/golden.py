#!/usr/bin/env python3
"""Confere (ou regrava com --update) os traços de referência do firmware.

    uv run --project software python tools/golden.py            # confere
    uv run --project software python tools/golden.py --update   # regrava após mudança intencional
"""

import sys
from pathlib import Path

from sfal.paths import FIRMWARE_DIR
from sfal.sim.golden import run_script

update = "--update" in sys.argv
status = 0
for script in sorted((FIRMWARE_DIR / "test" / "golden").glob("*.script")):
    trace = script.with_suffix(".trace")
    got = run_script(script)
    if update:
        trace.write_text(got)
        print(f"gravado  {trace.name} ({len(got.splitlines())} linhas)")
    elif not trace.exists() or trace.read_text() != got:
        print(f"DIFERE   {trace.name}")
        status = 1
    else:
        print(f"ok       {trace.name}")
sys.exit(status)
