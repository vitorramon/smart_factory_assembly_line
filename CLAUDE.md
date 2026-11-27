# Smart Factory Assembly Line — notas para o Claude

Sistema de acompanhamento e controle de uma linha de montagem de celulares: firmware de estação (ESP32), servidor
com painel e simulador que executa o mesmo firmware. Nasceu da ideia do Módulo 3 da disciplina PGENE586, mas **não é
mais uma atividade**: não há rubrica, fases nem formato de entrega a cumprir. O critério é funcionar e ser fácil de
mudar.

## Leia antes de agir

1. [README.md](README.md): o que é, como rodar, limitações
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): desenho e a tabela "Onde mexer"
3. [docs/PROTOCOL.md](docs/PROTOCOL.md): contrato MQTT `sfal/v1`
4. [docs/adr/](docs/adr/README.md): por quê

## Regras do projeto

- **Um núcleo, dois mundos.** `firmware/lib/station_core` é o mesmo código no ESP32 e no simulador. Nunca
  reimplemente lógica de estação em Python; nunca ponha cabeçalho de placa no núcleo (ADR-0001).
- **O simulador simula o mundo, não a estação.** `software/sfal/sim/plant.py` só mexe em entradas da `Hal` (botões,
  leitor, temperatura, enlace) e observa saídas.
- **O servidor não distingue placa de simulação.** `hw` é informação de painel; nenhuma regra depende dele.
- **O dispositivo não envia data/hora** (ADR-0003): só `age_ms`, `boot`, `seq`.
- **O motor não conhece relógio nem rede** (ADR-0002): `Engine.handle(topic, payload, now)`. Nada de `time.time()`
  dentro de `engine.py`, `kpi.py` ou `spc.py`.
- **A fábrica está em `config/line.yaml`.** Estação, takt, regra, meta ou cenário novo entra lá, não no código.
- **Indicador tem uma definição só**, em `software/sfal/kpi.py`, usada pelo painel e pelo "E se?".
- **M1, M2 e M3 não se misturam.** `config/m1.yaml` é a transcrição do diagnóstico (não invente número nem texto
  que não esteja na entrega do M1). `software/sfal/m2` é o modelo SimPy do M2 portado: `tests/test_m2.py` trava os
  resultados publicados; se ele quebrar, o modelo deixou de ser o do M2. O M3 é o motor ao vivo.
- **Na Síntese, todo número leva a origem** (diagnóstico, simulação, simulação ao vivo ou medido) e o aviso de que as
  três etapas representam linhas de tamanhos diferentes.
- **A IA que decide é a da inspeção óptica** (`software/sfal/vision`, classificador `models/aoi.onnx`): aprova ou
  reprova na AOI. O assistente do Ollama só escreve texto. Modelo novo de visão só entra com medição contra gabarito
  (`sfal/vision/evaluate.py` ou a ficha de `tools/train_aoi.py`); modelos genéricos do Ollama foram medidos e reprovados.
- **Fotos sintéticas são ditas como sintéticas.** Desempenho do classificador é "em fotos sintéticas", nunca "na linha".
- **Mudou o comportamento do núcleo?** Testes nativos + `tools/golden.py --update` + `docs/PROTOCOL.md`.

## Honestidade técnica

- Nenhuma placa física foi testada até 2026-11-26. Não escreva que algo "funciona no ESP32" sem ter visto funcionar;
  "compila" e "passa no simulador" são afirmações diferentes.
- Números do "E se?" são simulação com parâmetros hipotéticos; diga isso sempre que os citar.
- Só diga que está pronto depois de rodar os testes e, se mexeu em fluxo, ver no painel.

## Comandos

```bash
./start.sh simulation [--ia]                       # tudo simulado; painel em http://localhost:8000 (--ia: Ollama)
./start.sh prod [--ia]                             # só broker + servidor, esperando placas reais
./stop.sh                                          # derruba e APAGA os dados da linha: só com pedido do usuário
docker compose up -d --build                       # reconstruir depois de mudar código, sem apagar dados
docker compose logs -f backend simulator
(cd software && uv run pytest)                     # 41 testes
(cd software && uv run sfal whatif --hours 8)      # cenários em tempo acelerado
(cd firmware && pio test -e native)                # 13 testes do núcleo
(cd firmware && pio run -e esp32-asm)              # compila para a placa
# retreinar a inspeção óptica (PyTorch só aqui; leva dezenas de minutos na CPU): ver o cabeçalho de tools/train_aoi.py
uv run --project software python tools/golden.py   # paridade firmware × simulador (--update regrava)
```

## Ambiente

- Linux em WSL2 com Docker Desktop (runtime `nvidia` disponível). `uv`, Python 3.12 (via uv; o do sistema é 3.14) e
  PlatformIO em `~/.local/bin`. Ollama só em contêiner, por decisão do usuário (2026-11-26).
- Repositório Git local, sem remoto. Branches `main` (estável, com tag) e `dev` (trabalho). Commit, push e tag só a pedido, sem linha de coautoria.
- Projeto anterior, só para consulta: `../Documentation/Atividade/MOD 3` (repositório próprio; não editar). Os
  arquivos do Claude daquele projeto estão guardados em `../claude-mod3-original.tar.gz`.
- Contêineres de outros projetos na máquina (por exemplo `rebac-*`): não mexa.
