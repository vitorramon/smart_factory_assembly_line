---
name: concluir-tarefa
description: Fecha uma mudança no Smart Factory Assembly Line com verificação de verdade — testes do software e do firmware, paridade firmware × simulador, compilação para a placa, pilha no ar quando o fluxo mudou — e atualiza só a documentação afetada (README, protocolo, hardware, arquitetura, ADR). Use ao terminar qualquer alteração de código ou configuração, ou quando o usuário disser "terminei", "fecha isso", "pode commitar".
---

# Concluir tarefa

1. **Verifique o que mudou** (rode de fato; não presuma):

   | Mexeu em… | Rode |
   | --- | --- |
   | `software/` | `(cd software && uv run pytest && uv run ruff check sfal --select F,E9)` |
   | `firmware/lib` ou `firmware/sim` | `(cd firmware && pio test -e native)`, `uv run --project software python tools/golden.py`, `(cd software && uv run pytest)` |
   | `firmware/src` ou `platformio.ini` | `(cd firmware && pio run -e esp32-asm)` (e o ambiente alterado) |
   | `config/line.yaml` | `(cd software && uv run pytest && uv run sfal whatif --hours 2)` |
   | `Dockerfile`, compose, fluxo de ponta a ponta | `docker compose up -d --build`, depois `curl -s localhost:8000/api/health` e uma olhada no painel |

   Traço de referência diferente: se a mudança é intencional, `tools/golden.py --update` e leia o diff; se não é, há uma regressão.

2. **Se algo não pôde ser verificado, diga.** Hardware real sem teste é "não testado na placa", não "pronto".

3. **Documentação afetada, e só ela:** README (como rodar, o que faz, limitações, contagem de testes), `docs/PROTOCOL.md` (mensagens), `docs/HARDWARE.md` (pinos, gravação), `docs/ARCHITECTURE.md` (estrutura, portas, dados), comentários do `line.yaml`, `CLAUDE.md`/`.claude/rules` se uma regra mudou. Limitação resolvida sai da lista; limitação nova entra.

4. **Decisão nova?** Escolha técnica não registrada (biblioteca, contrato, formato, porta): skill `novo-adr`.

5. **Relate** em poucas linhas: o que mudou, o que foi verificado e como, o que ficou em aberto.

6. **Commit** só se o usuário pedir, sem linha de coautoria (`.claude/rules/git.md`).

Nunca: dizer que funciona sem ter rodado; apresentar simulação como medição; criar documento de progresso ou relatório que ninguém pediu.
