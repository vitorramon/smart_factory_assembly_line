# Hardware da estação

> Estado em 2026-11-26: o firmware **compila** para ESP32 (`pio run`, 58 % da flash) e a lógica passa nos testes no
> PC, mas **nenhuma placa física foi ligada ainda**. Trate o primeiro teste em bancada como validação desta página.

## Materiais (por estação)

| Item | Qtde | Observação |
|---|---|---|
| ESP32 DevKit (ESP-WROOM-32, 30 ou 38 pinos) | 1 | alimentação pela USB |
| Botão de pressão | 3 | INICIAR/FIM, REPROVAR, CHAMADO |
| LED verde, amarelo, vermelho + resistor 220 Ω | 3 + 3 | ou torre luminosa de 3V3/5 V com transistor |
| Buzina ativa 3V3 (ou 5 V com transistor) | 1 | opcional |
| Leitor de QR/código de barras com saída UART (ex.: GM65) | 1 | opcional; sem ele a estação usa só os botões |
| DHT22 + resistor 10 kΩ | 1 | opcional (temperatura do posto) |
| MAX6675 + termopar tipo K | 1 | só na estação do forno (`smt`) |

## Ligações

Definidas em `firmware/src/pins.h`.

| Função | GPIO | Ligação |
|---|---|---|
| Botão INICIAR / FIM OK | 5 | botão entre o pino e GND (pull-up interno) |
| Botão REPROVAR | 18 | botão entre o pino e GND |
| Botão CHAMADO | 19 | botão entre o pino e GND |
| LED verde | 25 | pino → 220 Ω → LED → GND |
| LED amarelo | 26 | idem |
| LED vermelho | 27 | idem |
| Buzina | 14 | nível alto = ligada |
| DHT22 (dados) | 4 | 10 kΩ entre dados e 3V3; VCC em 3V3 |
| MAX6675 SCK / CS / SO | 32 / 33 / 35 | VCC em 3V3 |
| Leitor UART: TX do leitor | 16 | 9600 bps, 8N1; leitor configurado para terminar com nova linha |

## Gravar

```bash
cd firmware
cp include/secrets.h.example include/secrets.h    # preencha Wi-Fi e MQTT_HOST
pio run -e esp32-asm -t upload                     # ambientes: esp32-smt, -aoi, -asm, -tst, -pkg
pio device monitor                                 # 115200 bps
```

- `MQTT_HOST` é o IP do computador que roda o broker **na rede Wi-Fi** (Windows: `ipconfig`). Com Docker Desktop a
  porta 1883 é publicada no Windows; libere-a no firewall para a rede local.
- No WSL2 a USB precisa ser repassada pelo Windows: `usbipd list` e `usbipd attach --wsl --busid <id>`
  (PowerShell como administrador). Alternativa: gravar pelo PlatformIO instalado no Windows.
- Estação nova: um bloco em `config/line.yaml` e um ambiente `[env:esp32-<id>]` em `platformio.ini` com o mesmo id.

## Teste de bancada sem botões nem leitor

Pelo monitor serial (cada linha termina com Enter):

| Digite | Efeito |
|---|---|
| `U-000123` | como se o leitor tivesse lido essa etiqueta |
| `!start` | toque em INICIAR / FIM OK |
| `!fail` | toque em REPROVAR |
| `!call` | toque em CHAMADO |

Roteiro mínimo: `docker compose up -d broker backend`, grave a placa como `smt` (primeira estação, cria a unidade),
digite `!start`, espere alguns segundos, `!start` de novo. O painel deve mostrar a estação como **ESP32**, um ciclo e
a unidade `U-000001`. Desligue o roteador por alguns segundos durante um ciclo: a estação pisca amarelo, o ciclo é
guardado e aparece no painel quando a rede volta.

## Uma placa real com o resto simulado

```bash
SFAL_REAL=asm docker compose up -d
```

O simulador deixa de simular `asm`; as unidades chegam à fila dela e esperam você. Na placa `asm`, aperte INICIAR
(o servidor atribui a unidade mais antiga da fila) ou leia a etiqueta; ao apertar FIM, o simulador segue com a
unidade pelas estações seguintes. A lógica está coberta por teste (`tests/test_firmware_sim.py`), mas com uma placa
de verdade ainda não foi exercitada.

## Câmera na inspeção óptica

A estação `aoi` decide pelo veredito do modelo de visão. Sem o simulador, quem manda a foto é a câmera. Qualquer
programa que tire a foto e faça um POST serve (computador com webcam, Raspberry Pi, ESP32-CAM):

```bash
curl -s localhost:8000/api/vision/inspect -H 'Content-Type: application/json' \
  -d "{\"station\":\"aoi\",\"unit\":\"U-000042\",\"image_b64\":\"$(base64 -w0 placa.jpg)\"}"
```

A unidade precisa estar em ciclo na estação (lida pelo leitor ou INICIAR apertado); o servidor responde com o
veredito e manda `cmd/result` à placa, que encerra o ciclo. Não testado com câmera nem com fotos reais: o
classificador atual só conhece as fotos sintéticas do simulador e precisa ser retreinado com fotos da sua placa
(`tools/train_aoi.py`).

## Broker com senha

```bash
docker compose exec broker mosquitto_passwd -c -b /mosquitto/data/senhas linha <senha>
```

Em `infra/mosquitto.conf`: `allow_anonymous false` e `password_file /mosquitto/data/senhas`. Depois defina
`MQTT_USER`/`MQTT_PASS` no `secrets.h` e `SFAL_MQTT_USER`/`SFAL_MQTT_PASS` no ambiente do `backend` e do `simulator`.
Este caminho ainda não foi testado.
