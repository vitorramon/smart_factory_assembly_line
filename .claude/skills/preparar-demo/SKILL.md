---
name: preparar-demo
description: Prepara uma demonstração do Smart Factory Assembly Line — roteiro de 5 a 10 minutos com a pilha no ar, falhas provocadas na ordem certa (reprovação e intertravamento, deriva do forno e jidoka, queda de rede e modo degradado, chamado), rastreabilidade de uma unidade, pergunta ao assistente de IA e comparação no "E se?", com ou sem placa real, mais a checagem prévia do ambiente. Use quando pedirem demo, apresentação, vídeo, "como eu mostro isso?" ou ensaio.
---

# Preparar demonstração

## Antes (15 min antes)

1. Skill `verificar-ambiente`.
2. Turno limpo, se o usuário concordar: `docker compose down -v && docker compose up -d --build` (apaga os dados). Senão, botão "Novo turno" no painel.
3. Com IA: `docker compose --profile ia up -d` e faça uma pergunta de aquecimento (a primeira carga do modelo demora).
4. Deixe a linha rodar ~3 min para os indicadores terem base.
5. Com placa real: grave e teste a estação antes (`docs/HARDWARE.md`); suba com `SFAL_REAL=<id>`.

## Roteiro (o sistema na tela, não slides)

| Min | Mostrar | Como |
| --- | --- | --- |
| 0–1 | A linha andando: fluxo, torre luminosa, indicadores contra referência e meta | painel |
| 1–3 | **Qualidade na fonte:** unidade reprovada volta para a mesma estação e não avança | aba "Provocar falhas" → surto de defeitos; clique numa unidade com ▲ e mostre as tentativas |
| 3–5 | **Jidoka:** o forno deriva, a carta de controle acusa, a estação é retida e a fila some depois dela | "Deriva de temperatura do forno" (40 s) |
| 5–6 | **Rede cai, a linha não:** estação segue em modo degradado e os ciclos chegam depois com o horário certo | "Queda de rede da estação" em `tst` (25 s) |
| 6–7 | **Rastreabilidade:** história completa de uma unidade | aba "Rastreabilidade" |
| 7–8 | **Assistente:** "onde está o gargalo e o que fazer?" e o relatório do turno | aba "Assistente" |
| 8–10 | **E se?:** atual × futuro em um turno de 8 h | aba "E se?" |

Com placa real, troque o bloco 5–6 por desligar a placa ou o Wi-Fi de verdade, e faça um ciclo com as mãos.

## O que dizer com precisão

- O simulador roda **o mesmo firmware** da placa; simulado é o mundo em volta.
- Os números do "E se?" são simulação com hipóteses do `line.yaml`, não medição.
- O que ainda não foi testado em hardware (veja "Limitações conhecidas" no README) é dito, não escondido.
- O assistente pode errar um número; o painel é a referência.

## Plano B

- Sem IA: o assistente responde com o diagnóstico por regras; siga.
- Painel parado: `docker compose logs --tail 50 backend simulator`; agente `investigador-pipeline`.
- Vídeo de reserva: grave o roteiro acima uma vez com tudo funcionando.
