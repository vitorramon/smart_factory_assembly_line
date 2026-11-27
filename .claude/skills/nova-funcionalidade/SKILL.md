---
name: nova-funcionalidade
description: Implementa ou altera uma funcionalidade do Smart Factory Assembly Line como fatia vertical — protocolo → núcleo do firmware → camada do ESP32 → planta simulada → motor → indicadores → painel → testes e traço de referência — mantendo firmware e simulador com o mesmo comportamento. Use sempre que for escrever código novo neste projeto, de um botão novo na estação a um indicador novo no painel.
---

# Nova funcionalidade (fatia vertical)

Leia antes: `docs/ARCHITECTURE.md` (tabela "Onde mexer"), `docs/PROTOCOL.md` e as regras em `.claude/rules/`.

## Primeiro, onde ela mora

| A funcionalidade é sobre… | Mora em… |
| --- | --- |
| o que a estação faz sozinha (botão, tempo, luz, fila) | núcleo: `firmware/lib/station_core` |
| um sensor, pino ou rádio | placa: `firmware/src` (+ método novo na `Hal` se o núcleo precisar do valor) |
| o que acontece no mundo (defeito, quebra, operador) | planta: `software/sfal/sim/plant.py` |
| memória e regra da linha (rota, qualidade, retenção) | motor: `software/sfal/engine.py` |
| um número (indicador) | `software/sfal/kpi.py` |
| um parâmetro da fábrica | `config/line.yaml` + `config.py` |
| o que o operador ou o líder vê | `software/sfal/web` |

Se a resposta for "no simulador e na placa", ela mora no núcleo.

## Ordem

1. **Protocolo:** se muda o que trafega, escreva primeiro em `docs/PROTOCOL.md`. Campo opcional entra em `v1`; quebra cria `v2` e ADR.
2. **Núcleo:** implemente com teste em `firmware/test/test_core`. Método novo na `Hal` precisa das duas implementações: `src/main.cpp` e `sim/capi.cpp` (+ `firmware_lib.py`).
3. **Roteiro de referência:** acrescente o caso em `firmware/test/golden/turno.script` e rode `tools/golden.py --update`; leia o diff do traço.
4. **Planta:** faça o mundo simulado provocar a situação (e, se fizer sentido, um tipo de falha em `inject` + `FAULTS`).
5. **Motor e indicadores:** com teste em `software/tests` de resultado conhecido.
6. **Painel:** estado legível em 5 segundos; cor sempre acompanhada de texto ou ícone; indicador contra referência e meta.
7. **Documentação** afetada (README, HARDWARE, ARCHITECTURE).

## Verificação

- `(cd software && uv run pytest)`, `(cd firmware && pio test -e native && pio run -e esp32-asm)`, `tools/golden.py`.
- `docker compose up -d --build` e veja no painel; provoque a falha correspondente na aba "Provocar falhas".
- Se toca rede ou tempo: derrube a estação (falha `link_drop`) e o servidor (`docker compose stop backend`) e veja o modo degradado e a recuperação.
- `(cd software && uv run sfal whatif --hours 2)` continua coerente (nenhuma unidade some: iniciadas = prontas + refugo + em processo).
- Peça revisão ao agente `revisor-contratos` e feche com a skill `concluir-tarefa`.
- Diga o que foi verificado e por qual meio; hardware real não testado é dito como não testado.
