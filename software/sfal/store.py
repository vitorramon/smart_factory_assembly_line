"""Banco SQLite da linha: unidades, passos por estação, paradas, alertas e diário."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS units (
    id TEXT PRIMARY KEY,
    created_ts REAL NOT NULL,
    status TEXT NOT NULL,            -- wip | rework | done | scrap | removed
    next_station TEXT,               -- estação em que a unidade é esperada
    busy INTEGER NOT NULL DEFAULT 0, -- 1 = em processo numa estação
    ready_ts REAL NOT NULL,          -- desde quando espera pela próxima estação
    finished_ts REAL,
    fails INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS units_next ON units(next_station, busy, status);
CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY,
    unit TEXT NOT NULL,
    station TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    start_ts REAL NOT NULL,
    end_ts REAL,
    dur_ms INTEGER,
    ok INTEGER,
    degraded INTEGER NOT NULL DEFAULT 0,
    temp REAL
);
CREATE INDEX IF NOT EXISTS steps_unit ON steps(unit);
CREATE INDEX IF NOT EXISTS steps_station ON steps(station, end_ts);
CREATE TABLE IF NOT EXISTS downtime (
    id INTEGER PRIMARY KEY,
    station TEXT NOT NULL,
    reason TEXT NOT NULL,            -- call | offline | hold
    start_ts REAL NOT NULL,
    end_ts REAL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    station TEXT,
    kind TEXT NOT NULL,              -- spc | offline | call
    level TEXT NOT NULL,             -- yellow | red
    message TEXT NOT NULL,
    closed_ts REAL
);
CREATE TABLE IF NOT EXISTS inspections (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    station TEXT NOT NULL,
    unit TEXT NOT NULL,
    ok INTEGER,                      -- 1 aprovada, 0 reprovada, NULL sem veredito
    defect TEXT,                     -- tipo apontado pelo modelo
    place TEXT,
    x REAL, y REAL,                  -- posição do defeito na foto (0 a 1)
    score REAL,
    model TEXT,
    latency_ms INTEGER,
    error TEXT,
    truth INTEGER,                   -- gabarito, quando quem enviou a foto sabe (simulador): 1 = tinha defeito
    truth_kind TEXT,
    image TEXT                       -- arquivo da foto em DATA_DIR/inspections
);
CREATE INDEX IF NOT EXISTS inspections_unit ON inspections(unit);
CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    level TEXT NOT NULL,             -- info | warn | error
    station TEXT,
    unit TEXT,
    kind TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


def open_db(path: str | Path = ":memory:") -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    db.row_factory = sqlite3.Row
    if path != ":memory:":
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    return db
