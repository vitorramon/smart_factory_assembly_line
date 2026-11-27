---
name: verificar-ambiente
description: Diagnostica o ambiente do Smart Factory Assembly Line — Docker e Compose, GPU para a IA local, uv e Python 3.12, PlatformIO e toolchain do ESP32, g++, portas 1883/8000/11434, estado da pilha e dos contêineres, modelo do Ollama, acesso USB à placa pelo WSL2. Use num computador novo, antes de gravar uma placa, antes do agente testador-terceiro ou quando algo não subir.
---

# Verificar ambiente

Rode os comandos e devolva uma tabela **item · resultado · ok? · ação sugerida**. **Não instale nada** sem o usuário pedir; diga o que falta e como instalar.

| Item | Comando | Esperado |
| --- | --- | --- |
| Docker | `docker info --format '{{.ServerVersion}}'; docker compose version` | servidor respondendo, Compose v2 |
| GPU no Docker | `docker info \| grep -i runtimes` | contém `nvidia` (só para o perfil `ia`; sem GPU a IA roda devagar) |
| Outros contêineres | `docker ps --format '{{.Names}}\t{{.Ports}}'` | anote o que não é `sfal-*` (não tocar) e o que usa nossas portas |
| Pilha | `docker compose ps` | `broker`, `backend`, `simulator` saudáveis (e `ollama`, se o perfil `ia` estiver ligado) |
| Portas | `for p in 1883 8000 11434; do (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null && echo "$p ocupada" \|\| echo "$p livre"; done` | ocupadas pela nossa pilha, ou livres antes de subir |
| Painel | `curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/health` | `200` |
| Modelo da IA | `docker compose exec -T ollama ollama list` | o modelo de `config/line.yaml` (`assistant.model`) |
| uv e Python | `uv --version; uv python list 2>/dev/null \| grep 3.12` | uv instalado, 3.12 disponível |
| Testes do software | `(cd software && uv run pytest -q)` | todos passam |
| g++ | `g++ --version \| head -1` | necessário para a biblioteca do simulador fora do contêiner |
| PlatformIO | `pio --version; ls ~/.platformio/platforms` | instalado, plataforma `espressif32` |
| Testes do firmware | `(cd firmware && pio test -e native 2>&1 \| tail -3)` | todos passam |
| Paridade | `uv run --project software python tools/golden.py` | `ok` em cada traço |
| Credenciais da placa | `test -f firmware/include/secrets.h && echo existe` | existe antes de gravar (não leia o conteúdo) |
| Porta serial | `ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null` | aparece com a placa conectada |
| Disco | `df -h .` | folga para a imagem do Ollama e o modelo (~10 GB) |

## Interpretação

- **USB no WSL2:** a placa só aparece depois de `usbipd attach --wsl --busid <id>` no PowerShell do Windows. Sem isso, grave pelo PlatformIO do Windows.
- **Placa não alcança o broker:** `MQTT_HOST` tem de ser o IP do Windows na rede Wi-Fi, e a porta 1883 precisa estar liberada no firewall.
- **Não** reinicie o Docker Desktop sem perguntar: derruba contêineres de outros projetos.
- Código em `/mnt/c` é lento; o projeto fica em `/home`.
- Primeira pergunta ao assistente depois de subir o Ollama demora (carga do modelo na GPU); as seguintes levam segundos.
