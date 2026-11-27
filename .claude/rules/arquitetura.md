---
paths:
  - "firmware/**"
  - "software/**"
  - "config/**"
---

# Arquitetura (docs/ARCHITECTURE.md, ADR-0001 e ADR-0002)

| Parte | Pasta | Pode depender de | Não pode |
| --- | --- | --- | --- |
| Núcleo da estação | `firmware/lib/station_core` | C/C++ padrão, `hal.h` | Arduino, FreeRTOS, `millis()`, `String`, bibliotecas externas, alocação dinâmica |
| Placa | `firmware/src` | Arduino, núcleo | conter regra de funcionamento (estado, tempo de ciclo, torre) |
| Ponte do simulador | `firmware/sim` | núcleo | lógica própria: só repassa entradas e saídas |
| Planta simulada | `software/sfal/sim` | `firmware_lib`, config | decidir pelo firmware; ler o banco do servidor |
| Motor | `software/sfal/engine.py`, `kpi.py`, `spc.py`, `store.py` | config, SQLite | relógio de parede, MQTT, HTTP, saber se a origem é `sim` ou `esp32` |
| Simulação do M2 | `software/sfal/m2` | SimPy | depender do motor, do firmware ou de MQTT; mudar hipóteses sem atualizar `tests/test_m2.py` |
| Inspeção óptica | `software/sfal/vision`, `models/` | Pillow, onnxruntime; Ollama só como alternativa | aprovar sem veredito; PyTorch em produção; trocar de modelo sem medir contra gabarito |
| AAS | `software/sfal/aas`, `infra/basyx` | motor (leitura), httpx, MQTT | ser importado pelo motor; escrever na linha; publicar gêmeo retido ou a cada segundo (docs/AAS.md) |
| Síntese | `software/sfal/sintese.py`, `config/m1.yaml` | `kpi`, `m2`, motor (leitura) | escrever no banco; apresentar número sem origem |
| Borda | `software/sfal/api.py`, `mqtt.py`, `assistant.py`, `web/` | motor | SQL direto; recalcular indicador |

- **Um núcleo, dois mundos.** Se o simulador precisa de um comportamento que a placa não teria, o lugar é a planta
  (`plant.py`), não o núcleo nem um `if` de simulação.
- **O relógio é sempre entrada**: `Hal::millis()` no firmware, `now` no motor. É isso que permite o "E se?" acelerado.
- **Configuração antes de código**: o que descreve a fábrica vai para `config/line.yaml`.
- O painel é HTML e módulos ES sem etapa de build: uma aba por arquivo em `web/js/` (`m1`, `m2`, `m3`, `sintese`), gráficos compartilhados em `charts.js`. O servidor calcula, o navegador desenha. Não introduza framework nem empacotador sem ADR.
- Nada de pastas `utils`, `common` ou `misc`: o nome diz o que o módulo guarda.
