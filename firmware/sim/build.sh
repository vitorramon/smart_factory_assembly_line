#!/usr/bin/env bash
# Compila o núcleo do firmware como biblioteca para o simulador: sim/build/libstation_core.so
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p sim/build
"${CXX:-g++}" -std=c++17 -O2 -Wall -Wextra -fPIC -shared \
  -Ilib/station_core/src \
  lib/station_core/src/station_core.cpp lib/station_core/src/json_mini.cpp sim/capi.cpp \
  -o sim/build/libstation_core.so
echo "ok: firmware/sim/build/libstation_core.so"
