---
name: nova-estacao
description: Acrescenta, remove ou altera uma estação da linha do Smart Factory Assembly Line de ponta a ponta — bloco em config/line.yaml (rota, ciclo ideal, leitor, retrabalho ou refugo, carta de controle, parâmetros de simulação), ambiente do PlatformIO para a placa, sensor e pinos, cenários do "E se?" e documentação de hardware — sem tocar no código do servidor. Use quando pedirem uma estação, posto, sensor de processo ou mudança de rota.
---

# Nova estação

**Critério de sucesso:** a estação aparece no painel, entra na rota, nos indicadores e no "E se?" **sem alteração de código** em `software/sfal`. Se precisar alterar, falta um campo de configuração: acrescente-o em `config.py` e documente no `line.yaml`.

1. **Para que serve:** que perda ela ataca (defeito que escapa, espera, falta de padrão)? Onde entra na rota? A ordem dos blocos em `stations` é a rota.
2. **`config/line.yaml`:** bloco com `name`, `ideal_cycle_s`, `reader` (tem leitor de etiqueta?), `on_fail` (`rework` ou `scrap`). Sinal de processo a vigiar: `spc: {label, unit, target, sigma}` (alvo e sigma vêm de dados do processo sob controle, não de chute; se for chute, diga no comentário).
3. **Simulação (`sim:`):** `mean_s`, `cv`, e conforme o papel: `defect`/`defect_p` (introduz defeito), `detects`/`detect_p`/`false_fail_p` (inspeciona), `rework_s`/`fix_p`, `mtbf_s`/`mttr_s`, `temp`/`temp_noise`. São hipóteses: comente a origem de cada número.
4. **Cenários:** revise `scenarios` — a estação nova muda o que "atual" e "futuro" significam?
5. **Placa:** ambiente `[env:esp32-<id>]` em `firmware/platformio.ini` com `-DSFAL_STATION_ID=\"<id>\"` e, se houver sensor, `-DSFAL_TEMP_DHT22` ou `-DSFAL_TEMP_MAX6675`. Sensor de outro tipo: implemente em `Esp32Hal::readTemperature` (`firmware/src/main.cpp`) e os pinos em `pins.h`.
6. **Verifique:**
   - `(cd software && uv run pytest)` (testes que citam estações pelo id podem precisar de ajuste);
   - `(cd software && uv run sfal whatif --hours 2)`: a estação tem ciclos e as contas fecham;
   - `docker compose restart backend simulator` e veja o cartão no painel; `pio run -e esp32-<id>` compila.
7. **Docs:** `docs/HARDWARE.md` (materiais, pinos, ambiente) e, se a rota mudou, o README.

Remover uma estação com unidades em processo deixa essas unidades presas: comece um turno limpo (`docker compose down -v`, com a concordância do usuário) ou termine as unidades antes.
