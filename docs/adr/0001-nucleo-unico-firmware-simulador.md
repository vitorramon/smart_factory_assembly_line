# 0001 — O simulador executa o núcleo do firmware em vez de imitá-lo

- **Estado:** Aceito
- **Data:** 2026-11-26

## Contexto

O projeto anterior (Módulo 3 da disciplina) tinha um emulador em Python e um firmware em C++ que implementavam o
mesmo contrato separadamente. Manter os dois iguais dependia de disciplina e de mensagens de referência. O pedido
agora é um firmware embarcável e um simulador "com o mesmo comportamento".

## Decisão

A lógica da estação fica em `firmware/lib/station_core`, C++ sem dependência de placa nem de biblioteca externa,
atrás da interface `Hal`. O ESP32 implementa a `Hal` com pinos e rede; `firmware/sim/capi.cpp` a implementa com
variáveis em memória e exporta uma API C. O simulador carrega essa biblioteca com `ctypes` e simula apenas o mundo
físico.

## Consequências

- Comportamento igual por construção; um roteiro de referência é conferido dos dois lados (`tools/golden.py`,
  `pio test -e native`).
- O relógio é uma entrada da `Hal`, então o simulador roda em tempo acelerado (base do "E se?").
- O núcleo não pode usar `String`, `millis()` nem bibliotecas Arduino; JSON é escrito com `snprintf` e lido por um
  leitor próprio de um nível (`json_mini`).
- O que **não** fica coberto pela paridade: a camada `firmware/src` (Wi-Fi, MQTT, tarefas, sensores). Só hardware
  real valida essa parte.
- O contêiner do simulador precisa de `g++` para compilar a biblioteca.

## Alternativas consideradas

- Emulador reescrito em Python: mais simples de empacotar, mas volta ao problema de duas implementações.
- Firmware inteiro no QEMU do ESP32: cobre também a camada de placa, porém não acelera o tempo e é pesado para
  cinco estações.
