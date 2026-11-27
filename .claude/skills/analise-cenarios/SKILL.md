---
name: analise-cenarios
description: Produz análises de dados do Smart Factory Assembly Line — comparação de cenários no "E se?" com várias sementes (média ± desvio), calibração dos parâmetros de simulação com dados medidos na linha, comparação medido × simulado, análise de gargalo, de esperas e de unidades lentas pela rastreabilidade, e leitura das cartas de controle. Use quando pedirem "compara os cenários", "vale a pena tal mudança?", "calibra o simulador", "por que essa unidade demorou?", "onde está a perda?".
---

# Análise de cenários e de dados da linha

Indicadores têm uma definição só: `software/sfal/kpi.py` (leia o cabeçalho antes de interpretar um número).

## Regras de origem

- **Medido:** veio de estações com `hw: esp32` na linha real. **Simulado ao vivo:** `hw: sim`. **"E se?":** simulação acelerada. Toda tabela diz de qual dos três veio cada número, a janela de tempo e o tamanho da amostra.
- Parâmetros dos cenários (`sim:` e `scenarios` em `config/line.yaml`) são hipóteses até serem calibrados. Diga isso.
- Uma semente só não é resultado: use várias e mostre a variação.

## 1. Comparar cenários

```bash
cd software
for s in 1 2 3 4 5 6 7 8 9 10; do uv run sfal whatif --hours 8 --seed $s --json; done
```

Agregue por cenário: média ± desvio de FPY, RTY, OEE, prontas, refugo, WIP final, lead time. Diferença menor que a variação entre sementes não é diferença. Cenário novo = bloco em `scenarios` com `label` e `patch`; mude **uma coisa por cenário** quando quiser atribuir o efeito.

## 2. Calibrar o simulador com a linha real

Com placas reais rodando, o banco tem os ciclos (`steps`): por estação, média e coeficiente de variação de `dur_ms`, fração de reprovação na primeira tentativa, duração e frequência das paradas (`downtime`). Leve para `sim:` (`mean_s`, `cv`, `defect_p`/`detect_p`, `mtbf_s`, `mttr_s`). Depois rode o "E se?" no cenário calibrado e compare com o medido: se FPY, OEE e lead time não baterem dentro da variação, o modelo está faltando algo (diga o quê) — não ajuste até bater.

Acesso aos dados: API (`/api/snapshot`, `/api/units`, `/api/units/<id>`) ou o SQLite do volume em modo só leitura.

## 3. Onde está a perda

- **Gargalo:** estação de ciclo médio mais longo; confirme pela fila antes dela.
- **Esperas:** na ficha da unidade, "espera antes" de cada estação = início − fim da anterior. Unidade lenta: onde esperou, e por quê (fila, retrabalho, parada)?
- **Qualidade:** FPY por estação e onde o defeito é detectado × onde nasce. Defeito detectado longe da origem é a perda cara.
- **Disponibilidade:** paradas por motivo (chamado, offline, retenção).
- **Processo:** carta de controle — ponto além de 3σ, sequência de 8 do mesmo lado, tendência de 6; relacione com reprovações no mesmo intervalo antes de afirmar causa.

## Saída

Tabela com origem e amostra de cada número, o que os dados sustentam, o que é hipótese e qual experimento a testaria. Gráfico: use a skill de visualização disponível.
