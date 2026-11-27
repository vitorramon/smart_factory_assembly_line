#!/usr/bin/env bash
# Derruba a linha e apaga os dados, para a próxima subida começar do zero.
#
#   ./stop.sh           para e remove os contêineres e apaga os dados da linha (banco, fotos da inspeção, shells no BaSyx)
#   ./stop.sh --tudo    apaga também os modelos baixados do Ollama (~11 GB) e a imagem construída
#   ./stop.sh --sim     não pergunta nada (para uso em scripts)
#
# Os modelos do Ollama ficam por padrão porque baixar de novo leva vários minutos e eles não guardam estado da linha.
# Código, configuração e o modelo da inspeção óptica (models/aoi.onnx) nunca são tocados.
set -euo pipefail
cd "$(dirname "$0")"

ALL=0; YES=0
for arg in "$@"; do
  case "$arg" in
    --tudo) ALL=1 ;;
    --sim|-y) YES=1 ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opção desconhecida: $arg (use --tudo, --sim ou --help)" >&2; exit 1 ;;
  esac
done

command -v docker >/dev/null || { echo "Docker não encontrado." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "O Docker não está respondendo. Abra o Docker Desktop e tente de novo." >&2; exit 1; }

echo "Isto vai parar a linha e APAGAR os dados dela: unidades, ciclos, alertas, diário e fotos da inspeção."
[[ $ALL == 1 ]] && echo "Com --tudo: também os modelos do Ollama (terão de ser baixados de novo) e a imagem construída."
if [[ $YES == 0 ]]; then
  read -r -p "Continuar? [s/N] " ans
  [[ "$ans" =~ ^[sS]$ ]] || { echo "Nada foi alterado."; exit 0; }
fi

if [[ $ALL == 1 ]]; then
  docker compose --profile ia --profile aas down --volumes --remove-orphans --rmi local
else
  docker compose --profile ia --profile aas down --remove-orphans
  docker volume rm sfal_dados >/dev/null 2>&1 && echo "Dados da linha apagados." || echo "Não havia dados da linha para apagar."
  docker volume rm sfal_faaast >/dev/null 2>&1 || true      # configuração gerada do FA³ST (refeita na próxima subida)
fi
rm -f .sfal-mode
echo "Pronto. Para subir de novo: ./start.sh simulation   ou   ./start.sh prod"
