# Arquitetura

```
        ESP32 (firmware/src)                 Simulador (software/sfal/sim)
   pinos · Wi-Fi · MQTT · sensores      unidades · operador · forno · defeitos · falhas
              │  Hal                                   │  Hal (firmware/sim/capi.cpp)
              ▼                                        ▼
        ┌──────────────────────────────────────────────────────┐
        │   StationCore  (firmware/lib/station_core, C++ puro)  │   ← o mesmo código-fonte
        │   estados · debounce · fila offline · torre luminosa  │
        └──────────────────────────────────────────────────────┘
              │ MQTT sfal/v1 (docs/PROTOCOL.md)        │ MQTT (ao vivo) ou chamada direta (E se?)
              ▼                                        ▼
        ┌──────────────────────────────────────────────────────┐
        │  Engine (software/sfal/engine.py)                     │
        │  liberação · genealogia · paradas · CEP · jidoka      │──▶ SQLite (store.py)
        └──────────────────────────────────────────────────────┘
              │ kpi.py (FPY, RTY, OEE, lead time)  │ assistant.py ──▶ Ollama (opcional)
              ▼
        api.py: REST + WebSocket ──▶ painel (software/sfal/web, HTML/JS sem etapa de build)
```

## Ideias que sustentam o desenho

1. **Um núcleo, três invólucros.** `StationCore` só fala com a interface `Hal`. No ESP32 a `Hal` são pinos e rede;
   no simulador são variáveis que a planta simulada escreve. O simulador não reimplementa a lógica da estação: ele a
   carrega (`ctypes`). Um teste nativo em C++ e um teste em Python rodam o mesmo roteiro e exigem o mesmo traço.
2. **O motor não conhece relógio nem rede.** `Engine.handle(topic, payload, now)` recebe o instante e devolve
   comandos por uma função `publish`. Ao vivo, quem chama é o cliente MQTT com a hora do sistema; no "E se?", a
   planta chama direto com relógio virtual, e um turno de 8 h roda em poucos segundos.
3. **Tudo o que descreve a fábrica está em `config/line.yaml`.** Estações, rota, takt, regras, metas, parâmetros da
   simulação e cenários. Servidor, painel e simulador leem o mesmo arquivo.
4. **A placa decide o que é urgente; o servidor decide o que precisa de memória.** Debounce, cronometragem, torre
   luminosa e modo degradado ficam na placa e funcionam sem rede. Rota, qualidade, indicadores e CEP ficam no servidor.

## Inspeção óptica por IA

`software/sfal/vision`: `board.py` gera a foto sintética da placa (faz o papel da câmera), `cnn.py` roda o
classificador (`models/aoi.onnx`, onnxruntime, CPU, poucos milissegundos por foto), `inspector.py` é a alternativa
com modelo de visão do Ollama e `service.py` escolhe entre os dois conforme `vision.engine`. O servidor recebe a foto
em `POST /api/vision/inspect`, classifica, guarda foto e veredito (`inspections`, `data/inspections/`) e publica
`cmd/result` para a estação, que encerra o ciclo. O treino (`tools/train_aoi.py`) precisa de PyTorch; a execução não.

O "E se?" não chama o modelo (rodaria milhares de inferências por cenário): usa `detect_p` e `false_fail_p`.

## As quatro abas do painel

O painel (`software/sfal/web`) é HTML e módulos JavaScript sem etapa de build. `js/main.js` troca de aba pelo
endereço (`#m1`, `#m2`, `#m3`, `#sintese`) e carrega cada módulo na primeira visita.

| Aba | Módulo JS | De onde vêm os dados |
|---|---|---|
| 1 · Problema e metas | `js/m1.js` | `GET /api/m1` → `config/m1.yaml` |
| 2 · Simulação | `js/m2.js`, `js/m2-draw.js` (desenho da linha em canvas) | `GET /api/m2/run` → `sfal/m2/model.py` (SimPy) + `sfal/m2/metrics.py` |
| 3 · Linha conectada | `js/m3.js` | WebSocket `/ws` (`js/live.js`) → `Engine` |
| 4 · Síntese | `js/sintese.js` | `GET /api/sintese` → `sfal/sintese.py` (junta M1, M2 e o estado ao vivo) |

`js/charts.js` tem os gráficos compartilhados (Pareto, teia, Ishikawa, evolução, séries no tempo) e `js/util.js`,
formatação e a dica flutuante. O servidor calcula; o navegador só desenha. A exceção é a reprodução do M2: o
servidor manda os eventos da simulação e o navegador reconstrói o estado das estações no instante escolhido.

O M2 é independente do M3: é a linha completa de 22 estações em SimPy, sem firmware nem MQTT. O "E se?" da aba 3 é
outra coisa: roda o recorte de 5 estações do M3 com o firmware real em tempo acelerado.

## Processos e portas

| Serviço (compose) | Porta | Papel |
|---|---|---|
| `broker` | 1883 | Mosquitto |
| `backend` | 8000 | `sfal server`: motor + API + painel; único escritor do banco (`/data/sfal.db`) |
| `simulator` | — | `sfal sim`: uma conexão MQTT por estação simulada |
| `ollama` (perfil `ia`) | 11434 (só localhost) | IA local |

## Dados

SQLite, tabelas em `software/sfal/store.py`: `units` (situação e próxima estação de cada unidade), `steps` (um
registro por passagem em estação: tentativa, início, fim, duração, resultado, temperatura), `downtime` (paradas por
chamado, offline e retenção), `alerts`, `log` (diário) e `meta`. O estado ao vivo das estações fica em memória e é
refeito pelas mensagens retidas e pela telemetria quando o servidor reinicia.

## Onde mexer

| Quero… | Mexo em… |
|---|---|
| mudar o comportamento da estação | `firmware/lib/station_core` + testes nativos + `tools/golden.py --update` |
| trocar pino, sensor ou rádio | `firmware/src` (nada mais muda) |
| mudar regra de liberação, retrabalho ou jidoka | `software/sfal/engine.py` + `tests/test_engine.py` |
| mudar a definição de um indicador | `software/sfal/kpi.py` (painel e "E se?" seguem juntos) |
| acrescentar estação, mudar takt, metas ou cenário | `config/line.yaml` |
| mudar o texto do diagnóstico ou a situação de uma causa-raiz | `config/m1.yaml` |
| mudar o modelo ou um cenário do M2 | `software/sfal/m2/model.py` (o teste `test_m2.py` trava os números publicados) |
| retreinar a inspeção óptica (outro defeito, fotos reais) | `tools/train_aoi.py` e `software/sfal/vision/board.py`; a ficha do modelo fica em `models/aoi.json` |
| acrescentar um gráfico | `software/sfal/web/js/charts.js` |
| acrescentar um tipo de falha simulada | `software/sfal/sim/plant.py` (`inject`) e `live.py` (`FAULTS`) |
