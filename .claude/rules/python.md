---
paths:
  - "software/**"
  - "tools/**"
---

# Python

- Python **3.12** via `uv`, um projeto só (`software/pyproject.toml`). Dependência nova com `uv add`, lockfile
  versionado. Nada de `pip install` solto.
- Dependências atuais: `fastapi`, `uvicorn`, `paho-mqtt`, `pyyaml`, `httpx`. Pense duas vezes antes de somar outra.
- **Motor determinístico:** `engine.py`, `kpi.py` e `spc.py` recebem `now`; nenhum `time.time()` neles. Aleatoriedade
  só na planta simulada, por `random.Random(seed)`.
- **Threads:** o cliente MQTT chama o motor de outra thread; todo acesso passa por `Engine.lock`. Não segure o lock
  durante I/O de rede.
- Nada de `except: pass`. A única captura ampla permitida é a da thread de rede em `mqtt.py`, e ela registra.
- Testes com `pytest` em `software/tests`. Indicador testado com caso pequeno de resultado conhecido; regra de
  liberação nova ganha um caso em `test_intertravamento_recusa`.
- Antes de dizer que terminou: `uv run pytest` e `uv run ruff check sfal --select F,E9`.
- Arquivos com um propósito; passou de ~400 linhas, divida.
