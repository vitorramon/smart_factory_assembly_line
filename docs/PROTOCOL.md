# Protocolo MQTT `sfal/v1`

Contrato entre uma estação (ESP32 ou simulada) e o servidor. Fonte da verdade no código:
`firmware/lib/station_core/src/station_core.cpp` (dispositivo) e `software/sfal/engine.py` (servidor).
O roteiro `firmware/test/golden/turno.script` e seu traço `turno.trace` são exemplos executáveis de todas as mensagens.

Regras gerais:

- JSON em UTF-8, objetos de um nível.
- **O dispositivo nunca envia data/hora.** Eventos levam `age_ms` (há quanto tempo ocorreram); o servidor carimba
  `instante = recebimento − age_ms`. Assim um evento guardado durante uma queda de rede entra no horário certo.
- Todo evento leva `boot` (número sorteado a cada partida) e `seq` (contador de eventos desde a partida). O servidor
  descarta `seq` repetido e conta lacunas.

## Dispositivo → servidor

| Tópico | QoS | Retido | Conteúdo |
|---|---|---|---|
| `sfal/v1/{id}/status` | 1 | sim | `{"online":true,"fw":"1.0.0","hw":"esp32","boot":123}`; Last Will: `{"online":false}` |
| `sfal/v1/{id}/tel` | 0 | não | Telemetria a cada `tel_ms` e a cada mudança de estado |
| `sfal/v1/{id}/evt/scan` | 1 | não | Pedido de início: `{"seq","boot","age_ms","unit"}`; `unit` vazio = estação sem leitor |
| `sfal/v1/{id}/evt/cycle` | 1 | não | Fim de ciclo: `{"seq","boot","age_ms","unit","dur_ms","ok","degraded"}` |
| `sfal/v1/{id}/evt/call` | 1 | não | Chamado: `{"seq","boot","age_ms","on"}` |

Telemetria: `{"boot","up_ms","state","unit","cycle_ms","call","temp","rssi","queued","dropped","reason"}`.
`state` é `IDLE`, `WAIT`, `RUNNING` ou `BLOCKED`; `temp` é °C ou `null`; `queued`/`dropped` são eventos na fila
da placa e eventos descartados por fila cheia; `reason` é o motivo do bloqueio.

`hw` vale `esp32` ou `sim`. É só informação para o painel: nenhuma regra do servidor depende dele.

## Servidor → dispositivo

| Tópico | QoS | Retido | Conteúdo |
|---|---|---|---|
| `sfal/v1/{id}/cmd/release` | 1 | não | Resposta ao `scan`: `{"req":<seq do scan>,"ok":true,"unit":"U-000042"}` ou `{"req","ok":false,"reason"}` |
| `sfal/v1/{id}/cmd/result` | 1 | não | Resultado de inspeção automática: `{"unit":"U-000042","ok":false}`. Encerra o ciclo em andamento dessa unidade, como o botão faria; outra unidade ou estação fora de ciclo: ignorado |
| `sfal/v1/{id}/cmd/config` | 1 | sim | `{"takt_ms","tel_ms","release_timeout_ms","interlock","fail_open"}` (todos opcionais) |
| `sfal/v1/{id}/cmd/light` | 1 | sim | `{"level":"auto"}`; valores: `auto`, `off`, `green`, `yellow`, `red` |

Motivos de recusa: `upstream_fail`, `skipped_step`, `already_done`, `unknown_unit`, `scrapped`, `in_process`,
`no_unit`, `hold`. O dispositivo gera `no_server` (tempo esgotado com `fail_open:false`) e `no_link`.

## Ciclo de uma unidade

```
operador lê a etiqueta (ou aperta INICIAR)
   estação ──evt/scan {seq:7, unit}──────────────▶ servidor: confere rota, qualidade e retenção
   estação ◀─cmd/release {req:7, ok:true, unit}── servidor
   [RUNNING: verde; amarelo se passar do takt]
operador aperta INICIAR (aprovada) ou REPROVAR
   estação ──evt/cycle {unit, dur_ms, ok}────────▶ servidor: fecha o passo, move a unidade na rota
```

`dur_ms` conta do pedido de início ao botão de fim. Sem resposta em `release_timeout_ms`: com `fail_open` a estação
segue e marca `degraded:true`; sem ele, bloqueia com `no_server`.

## Inspeção óptica por IA

Na estação configurada em `vision.station` (a AOI), quem aprova ou reprova é um modelo de visão:

```
câmera ──POST /api/vision/inspect {station, unit, image_b64}──▶ servidor: classifica a foto, guarda foto e veredito
   estação ◀─cmd/result {unit, ok}────────────────────────────── servidor
   estação ──evt/cycle {unit, dur_ms, ok}──────────────────────▶ servidor: fecha o passo como em qualquer estação
```

A foto vai por HTTP (é grande demais para o MQTT das placas); o resultado volta pelo MQTT. O campo opcional `truth`
(`{"defect": true, "kind": "ponte"}`) é o gabarito, enviado só pelo simulador, e serve para medir o modelo.
Sem veredito (modelo fora do ar), nada é enviado à estação e o ciclo é encerrado pelos botões.

## Torre luminosa (decidida na placa)

Prioridade, da maior para a menor: chamado aberto (vermelho piscando + bipe) · bloqueio (vermelho + buzina 0,6 s) ·
comando `light` do servidor · sem rede (amarelo piscando) · em ciclo (verde; amarelo após o takt) · pedindo
liberação (verde piscando rápido) · aguardando (apagada).

## Simulador

`sfal/v1/sim/status` (retido) anuncia o simulador e as falhas disponíveis; `sfal/v1/sim/cmd` recebe
`{"fault","station","seconds","factor"}`. Placas reais ignoram esses tópicos.

## Mudança de contrato

Mudança incompatível cria `sfal/v2` convivendo com `v1`. Campo novo opcional pode entrar em `v1`. Em qualquer caso:
atualizar este arquivo, o roteiro de referência (`tools/golden.py --update`) e os testes dos dois lados.
