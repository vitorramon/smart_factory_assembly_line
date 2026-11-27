"""Caminhos do projeto. Cada um pode ser trocado por variável de ambiente (contêiner, testes)."""

import os
from pathlib import Path

ROOT = Path(os.environ.get("SFAL_ROOT", Path(__file__).resolve().parents[2]))
FIRMWARE_DIR = Path(os.environ.get("SFAL_FIRMWARE_DIR", ROOT / "firmware"))
CONFIG_PATH = Path(os.environ.get("SFAL_CONFIG", ROOT / "config" / "line.yaml"))
DATA_DIR = Path(os.environ.get("SFAL_DATA_DIR", ROOT / "data"))
WEB_DIR = Path(__file__).resolve().parent / "web"
