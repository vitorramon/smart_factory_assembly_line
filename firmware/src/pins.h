// Pinagem padrão da placa de estação (ESP32 DevKit, 30 ou 38 pinos). Ver docs/HARDWARE.md.
#pragma once

#define PIN_BTN_START 5   // INICIAR / FIM OK   (botão para GND, INPUT_PULLUP)
#define PIN_BTN_FAIL 18   // FIM NOK (reprova)  (botão para GND, INPUT_PULLUP)
#define PIN_BTN_CALL 19   // CHAMADO (andon)    (botão para GND, INPUT_PULLUP)

#define PIN_LED_GREEN 25  // torre luminosa, ativo em nível alto (resistor de 220 Ω em série)
#define PIN_LED_YELLOW 26
#define PIN_LED_RED 27
#define PIN_BUZZER 14     // buzina ativa (5 V via transistor) ou módulo de buzina de 3V3

#define PIN_DHT 4         // DHT22: dados (com pull-up de 10 kΩ para 3V3)

#define PIN_TC_SCK 32     // MAX6675 (termopar K do forno): SCK
#define PIN_TC_CS 33      //                                CS
#define PIN_TC_SO 35      //                                SO (entrada)

#define PIN_SCAN_RX 16    // leitor de QR/código de barras por UART (TX do leitor -> GPIO 16)
#define PIN_SCAN_TX 17
#define SCAN_BAUD 9600
