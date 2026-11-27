"""Linha de comando: sfal server | sim | whatif | golden."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import threading


def _pct(v) -> str:
    return "   —  " if v is None else f"{v:6.1%}"


def cmd_server(args) -> None:
    import uvicorn

    uvicorn.run("sfal.api:create_app", factory=True, host=args.host, port=args.port, log_level="info", access_log=False)


def cmd_sim(args) -> None:
    from .config import load
    from .sim import live

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    real = tuple(s for s in (args.real or "").split(",") if s)
    try:
        live.run(load(), real=real, stop=stop)
    except KeyboardInterrupt:
        stop.set()


def cmd_whatif(args) -> None:
    from .config import load
    from .sim import whatif

    cfg = load()
    names = args.scenarios.split(",") if args.scenarios else list(cfg.scenarios)
    results = whatif.compare(cfg, names, args.hours, args.seed)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    t = cfg.targets
    print(f"E se? — {cfg.name}, turno de {args.hours:g} h (simulação; firmware real em cada estação)\n")
    print(f"{'cenário':<10} {'FPY':>6} {'RTY':>6} {'OEE':>6} {'prontas':>8} {'refugo':>7} {'WIP':>5} {'lead time':>10} {'gargalo':>8}")
    for r in results:
        k = r["line"]
        lead = "—" if k["lead_time_avg_s"] is None else f"{k['lead_time_avg_s'] / 60:.1f} min"
        print(
            f"{r['scenario']:<10} {_pct(k['fpy'])} {_pct(k['rty'])} {_pct(k['oee'])} {k['done']:>8} {k['scrap']:>7} "
            f"{k['wip']:>5} {lead:>10} {k['bottleneck'] or '—':>8}"
        )
    if t:
        print("\nmeta       " + " ".join(_pct(t.get(k, {}).get("goal")) for k in ("fpy", "rty", "oee")))
        print("referência " + " ".join(_pct(t.get(k, {}).get("baseline")) for k in ("fpy", "rty", "oee")))
    for r in results:
        print(f"\n{r['scenario']}: {r['label']}")


def main() -> None:
    logging.basicConfig(level=os.environ.get("SFAL_LOG", "INFO"), format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)   # uma linha por foto enviada é ruído
    p = argparse.ArgumentParser(prog="sfal", description="Smart Factory Assembly Line")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("server", help="servidor da linha (painel em http://localhost:8000)")
    s.add_argument("--host", default=os.environ.get("SFAL_HTTP_HOST", "0.0.0.0"))
    s.add_argument("--port", type=int, default=int(os.environ.get("SFAL_HTTP_PORT", "8000")))
    s.set_defaults(fn=cmd_server)

    s = sub.add_parser("sim", help="simulador ao vivo (firmware real, mundo simulado)")
    s.add_argument("--real", default=os.environ.get("SFAL_REAL", ""), help="estações com placa real, separadas por vírgula")
    s.set_defaults(fn=cmd_sim)

    s = sub.add_parser("whatif", help="compara cenários em tempo acelerado")
    s.add_argument("--scenarios", help="lista separada por vírgula (padrão: todos)")
    s.add_argument("--hours", type=float, default=8)
    s.add_argument("--seed", type=int)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_whatif)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
