// Fronteira entre a lógica da estação e o mundo físico.
//
// O núcleo (StationCore) só enxerga esta interface. Existem duas implementações:
//   - src/hal_esp32.cpp : pinos, Wi-Fi e MQTT de um ESP32 real;
//   - sim/capi.cpp      : estado em memória, preenchido pelo simulador em Python.
// Como o núcleo é o mesmo arquivo-fonte nos dois casos, o simulador se comporta como a placa.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace sfal {

enum class Button : uint8_t { Start = 0, Fail = 1, Call = 2 };
const uint8_t kButtonCount = 3;

class Hal {
 public:
  virtual ~Hal() {}
  // Relógio monotônico em milissegundos (pode dar a volta; o núcleo só usa diferenças).
  virtual uint32_t millis() = 0;
  // Nível bruto do botão, sem debounce: true = pressionado.
  virtual bool buttonPressed(Button b) = 0;
  // Temperatura em °C. Retorna false se não há sensor ou a leitura falhou.
  virtual bool readTemperature(float &celsius) = 0;
  // Código lido pelo leitor (QR/código de barras). true quando há um código completo em buf.
  virtual bool readScan(char *buf, size_t len) = 0;
  // Torre luminosa e buzina.
  virtual void setLight(bool green, bool yellow, bool red) = 0;
  virtual void setBuzzer(bool on) = 0;
  // Enlace MQTT pronto para publicar.
  virtual bool linkUp() = 0;
  // Publica; false = não saiu (o núcleo tenta de novo no caso de eventos).
  virtual bool publish(const char *topic, const char *payload, uint8_t qos, bool retain) = 0;
  // Intensidade do sinal em dBm (0 se não se aplica).
  virtual int rssi() = 0;
};

}  // namespace sfal
