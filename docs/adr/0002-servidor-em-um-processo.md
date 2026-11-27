# 0002 — Servidor em um processo, motor sem relógio nem rede

- **Estado:** Aceito
- **Data:** 2026-11-26

## Contexto

A versão anterior dividia o caminho do dado em gateway, servidor OPC UA, sincronizador, AAS, núcleo e painel
Streamlit, com orquestrador próprio. Cada parte era pequena, mas subir, depurar e mudar qualquer coisa ficou caro
para o tamanho do problema (uma linha, cinco estações).

## Decisão

Um processo (`sfal server`) contém o cliente MQTT, o motor (`Engine`), o banco SQLite, a API e o painel. O motor é
uma classe que recebe `(tópico, payload, instante)` e publica por uma função injetada.

## Consequências

- Sobe com `docker compose up`; depura-se com um log só.
- O mesmo motor roda no "E se?" com relógio virtual, sem broker.
- Não há OPC UA nem AAS. Se uma integração com outro sistema exigir um desses padrões, entra como adaptador que
  consome o MQTT ou a API, sem mudar o motor.
- Escala vertical apenas; suficiente para uma linha.

## Alternativas consideradas

- Manter os serviços separados: rejeitado pelo custo operacional.
- Streamlit no painel: rejeitado; redesenho por página inteira e sem push em tempo real.
