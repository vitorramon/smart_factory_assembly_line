# Idioma

- Documentação, ADRs, commits, comentários, logs e textos do painel em **português (pt-BR)**, com acentuação correta.
- **Identificadores de código em inglês** (`StationCore`, `release`, `lead_time_avg_s`), como já está no projeto.
- No fio (MQTT e API) tudo em inglês: tópicos, chaves e valores (`RUNNING`, `upstream_fail`). A tradução para o
  operador acontece no painel (`web/app.js`) e no diário (`engine.py`, `REASONS`).
- Termos de padrões e de Lean ficam como são usados no chão de fábrica: MQTT (topic, QoS, Last Will), takt, andon,
  jidoka, FPY, RTY, OEE, WIP.
- Cite decisões pelo ADR (`ADR-0001`).
