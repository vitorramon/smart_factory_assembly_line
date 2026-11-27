---
paths:
  - "firmware/**"
---

# Firmware (ADR-0001)

- **Núcleo sem placa.** `lib/station_core` compila com `g++` puro (`sim/build.sh`) e não inclui nada do Arduino.
  Regra nova de funcionamento entra aqui, com teste em `test/test_core`.
- **`src/` é só ligação**: pinos (`pins.h`), Wi-Fi, MQTT, sensores. A rede roda em tarefa própria; o laço principal
  nunca bloqueia (nada de `delay()` longo, nada de conexão no `loop()`).
- **Sem alocação dinâmica nem `String` no núcleo.** Buffers de tamanho fixo e `snprintf`.
- **Tempo por diferença** de `uint32_t` (`now - t0`), que sobrevive à volta do contador.
- **Credenciais só em `include/secrets.h`** (fora do Git); o modelo é `secrets.h.example`.
- **Versões fixadas** em `platformio.ini`. Biblioteca nova só na camada `src/`, com versão exata.
- **Estação nova** = ambiente `[env:esp32-<id>]` com `SFAL_STATION_ID` igual ao id em `config/line.yaml`.
- **Toda mudança:** `pio test -e native`, `pio run -e esp32-asm` e `tools/golden.py`. Mudança intencional de
  comportamento: `tools/golden.py --update` e revise o diff do traço.
- Compilar e passar no simulador não é "funciona na placa". Diga o que foi de fato verificado.
