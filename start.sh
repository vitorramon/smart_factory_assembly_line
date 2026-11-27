#!/usr/bin/env bash
# Sobe a linha.
#
#   ./start.sh simulation        tudo simulado: broker + servidor + simulador (firmware real, mundo simulado)
#   ./start.sh prod              espera hardware real: broker + servidor, sem simulador
#   ./start.sh <modo> --ia       também sobe a IA local do Assistente (Ollama; baixa o modelo na primeira vez)
#
# Para trocar de modo, rode ./stop.sh antes: os dados de uma simulação não devem se misturar com os da linha real.
set -euo pipefail
cd "$(dirname "$0")"

usage() { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-1}"; }

MODE="${1:-}"; shift || true
IA=0
for arg in "$@"; do
  case "$arg" in
    --ia) IA=1 ;;
    *) echo "Opção desconhecida: $arg" >&2; usage ;;
  esac
done
case "$MODE" in
  simulation|prod) ;;
  -h|--help|help) usage 0 ;;
  *) echo "Informe o modo: simulation ou prod." >&2; usage ;;
esac

# ---- pré-requisitos
command -v docker >/dev/null || { echo "Docker não encontrado. Instale o Docker (com Compose) e tente de novo." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 não encontrado (comando 'docker compose')." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "O Docker não está respondendo. Abra o Docker Desktop e tente de novo." >&2; exit 1; }

# ---- não misturar simulação com linha real
MARK=.sfal-mode
if [[ -f $MARK && "$(cat $MARK)" != "$MODE" ]]; then
  echo "A linha foi iniciada antes no modo '$(cat $MARK)' e ainda tem dados desse modo." >&2
  echo "Rode ./stop.sh (apaga os dados da linha) e depois ./start.sh $MODE." >&2
  exit 1
fi

HTTP_PORT="${SFAL_HTTP_PORT:-8000}"
MQTT_PORT="${SFAL_MQTT_PORT:-1883}"
[[ -f .env ]] && { HTTP_PORT="$(grep -E '^SFAL_HTTP_PORT=' .env | cut -d= -f2 || true)"; HTTP_PORT="${HTTP_PORT:-8000}"; }
[[ -f .env ]] && { M="$(grep -E '^SFAL_MQTT_PORT=' .env | cut -d= -f2 || true)"; MQTT_PORT="${M:-$MQTT_PORT}"; }

PROFILE=()
SERVICES=(broker backend)
[[ $MODE == simulation ]] && SERVICES+=(simulator)
if [[ $IA == 1 ]]; then PROFILE=(--profile ia); SERVICES+=(ollama); fi

echo "==> Subindo em modo $MODE: ${SERVICES[*]}"
echo "$MODE" > $MARK
docker compose "${PROFILE[@]}" up -d --build "${SERVICES[@]}"
if [[ $MODE == prod ]]; then          # garante que não ficou simulador de uma execução anterior
  docker compose rm -sf simulator >/dev/null 2>&1 || true
fi

echo "==> Esperando o servidor responder"
for i in $(seq 1 60); do
  if curl -fs "http://localhost:$HTTP_PORT/api/health" >/dev/null 2>&1; then OK=1; break; fi
  sleep 2
done
if [[ "${OK:-0}" != 1 ]]; then
  echo "O servidor não respondeu em 2 minutos. Veja: docker compose logs --tail 50 backend broker" >&2
  exit 1
fi

if [[ $IA == 1 ]]; then
  MODEL="${SFAL_OLLAMA_MODEL:-qwen2.5:7b}"
  if ! docker compose exec -T ollama ollama list 2>/dev/null | grep -q "^$MODEL"; then
    echo "==> Baixando o modelo do Assistente ($MODEL, alguns GB; só na primeira vez)"
    docker compose exec -T ollama ollama pull "$MODEL"
  fi
fi

echo
echo "Painel: http://localhost:$HTTP_PORT"
if [[ $MODE == simulation ]]; then
  echo "Modo simulação: as cinco estações são simuladas (firmware real, mundo simulado)."
  echo "A linha leva cerca de um minuto para a primeira unidade sair. Falhas: aba 3, 'Provocar falhas'."
else
  echo "Modo produção: o servidor está esperando as placas. Nenhuma estação aparece até uma placa conectar."
  echo
  echo "Nas placas (firmware/include/secrets.h), MQTT_PORT = $MQTT_PORT e MQTT_HOST = o IP deste computador na rede"
  echo "Wi-Fi das placas. Endereços encontrados:"
  if command -v ipconfig.exe >/dev/null 2>&1; then      # WSL2: o que as placas enxergam é o IP do Windows
    ipconfig.exe 2>/dev/null | tr -d '\r' | grep -iE 'IPv4' | sed 's/^ */  Windows: /' || true
    echo "  (no WSL2 use um endereço do Windows, não o do Linux, e libere a porta $MQTT_PORT no firewall)"
  else
    hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.' | sed 's/^/  /' || true
  fi
  echo
  echo "Gravar uma estação:  cd firmware && pio run -e esp32-asm -t upload    (ambientes: esp32-smt, -aoi, -asm, -tst, -pkg)"
  echo "Detalhes, ligações e teste de bancada: docs/HARDWARE.md"
  echo "A inspeção óptica da AOI espera a foto de uma câmera (docs/HARDWARE.md, 'Câmera na inspeção óptica');"
  echo "sem câmera, o ciclo da AOI é encerrado pelos botões da estação."
fi
[[ $IA == 0 ]] && echo "Assistente de IA desligado (use --ia para ligar). A inspeção óptica não depende dele."
echo "Parar e apagar os dados: ./stop.sh"
