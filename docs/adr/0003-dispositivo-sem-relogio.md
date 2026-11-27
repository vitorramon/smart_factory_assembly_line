# 0003 — O dispositivo envia idade do evento, não data/hora

- **Estado:** Aceito
- **Data:** 2026-11-26

## Contexto

Um ESP32 não tem relógio confiável sem NTP, e a rede do chão de fábrica cai. Carimbar o evento só na chegada (como
na versão anterior) distorce lead time e paradas quando o evento fica guardado na placa.

## Decisão

Cada evento sai com `age_ms`, calculado no envio com o relógio monotônico da placa. O servidor grava
`recebimento − age_ms`. Duplicatas são eliminadas por `(boot, seq)`.

## Consequências

- Eventos guardados durante uma queda entram no horário certo; nenhuma sincronização de relógio na placa.
- O erro é o atraso de rede da última tentativa (milissegundos).
- A fila da placa tem 24 posições; além disso o mais antigo é descartado e o contador `dropped` aparece no painel.
- Se a placa reiniciar com eventos na fila, eles se perdem (não há gravação em flash).
