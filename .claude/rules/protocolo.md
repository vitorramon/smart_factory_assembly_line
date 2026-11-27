---
paths:
  - "firmware/lib/**"
  - "firmware/sim/**"
  - "firmware/test/**"
  - "software/sfal/engine.py"
  - "software/sfal/sim/**"
  - "docs/PROTOCOL.md"
---

# Protocolo `sfal/v1` (docs/PROTOCOL.md, ADR-0003)

- **Fonte da verdade:** `station_core.cpp` (dispositivo) e `engine.py` (servidor), documentados em `docs/PROTOCOL.md`.
  Exemplo executável: `firmware/test/golden/turno.script` → `turno.trace`.
- **Tópicos:** `sfal/v1/{id}/status` (retido, Last Will), `/tel` (QoS 0), `/evt/{scan,cycle,call}` (QoS 1),
  `/cmd/{release,result,config,light}` (QoS 1; `config` e `light` retidos). `result` é o veredito da inspeção automática e só vale para a unidade em ciclo.
- **Sem data/hora vinda do dispositivo.** Evento leva `age_ms`; o servidor grava `recebimento − age_ms`.
- **`boot` + `seq` em todo evento:** o servidor descarta duplicata e conta lacuna.
- **`release` responde a um `scan` específico** (`req` = `seq` do scan); resposta velha é ignorada pela placa.
- **Mensagem inválida não derruba nem entra no banco:** conta em `rejected` e, se a estação é conhecida, vai ao diário.
- **Campo novo opcional** pode entrar em `v1`. **Mudança incompatível** cria `sfal/v2` convivendo com `v1`, com ADR.
- **Ao mexer no protocolo, tudo junto:** núcleo, motor, `docs/PROTOCOL.md`, testes nativos, `tests/test_engine.py` e
  `tools/golden.py --update` (confira o diff do traço: ele mostra exatamente o que mudou no fio).
- Payloads do núcleo cabem em `kPayloadLen` (256) e tópicos em `kTopicLen` (96); identificadores passam por
  `sanitizeToken` em vez de escape de JSON.
