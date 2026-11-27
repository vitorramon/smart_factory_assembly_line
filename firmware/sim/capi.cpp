// Ponte C do núcleo da estação para o simulador (software/sfal/sim/firmware_lib.py, via ctypes).
//
// Aqui a camada de hardware é um conjunto de variáveis em memória: o simulador escreve botões,
// temperatura, leituras e o relógio; o núcleo — o mesmo de src/main.cpp — decide o resto.
// Compile com sim/build.sh (g++ puro, sem dependências).
#include <stdint.h>
#include <string.h>

#include <deque>
#include <string>

#include "station_core.h"

extern "C" {
typedef int (*sc_publish_fn)(void *user, const char *topic, const char *payload, int qos, int retain);
}

namespace {

class SimHal : public sfal::Hal {
 public:
  uint32_t now = 0;
  bool buttons[sfal::kButtonCount] = {false, false, false};
  bool temp_valid = false;
  float temp = 0;
  std::deque<std::string> scans;
  bool link = false;
  bool green = false, yellow = false, red = false, buzzer = false;
  sc_publish_fn publish_fn = nullptr;
  void *user = nullptr;

  uint32_t millis() override { return now; }
  bool buttonPressed(sfal::Button b) override { return buttons[(uint8_t)b]; }
  bool readTemperature(float &c) override {
    c = temp;
    return temp_valid;
  }
  bool readScan(char *buf, size_t len) override {
    if (scans.empty() || len == 0) return false;
    strncpy(buf, scans.front().c_str(), len - 1);
    buf[len - 1] = '\0';
    scans.pop_front();
    return true;
  }
  void setLight(bool g, bool y, bool r) override {
    green = g;
    yellow = y;
    red = r;
  }
  void setBuzzer(bool on) override { buzzer = on; }
  bool linkUp() override { return link; }
  bool publish(const char *topic, const char *payload, uint8_t qos, bool retain) override {
    if (!link || !publish_fn) return false;
    return publish_fn(user, topic, payload, qos, retain ? 1 : 0) != 0;
  }
  int rssi() override { return 0; }
};

struct Station {
  SimHal hal;
  sfal::StationCore core;
  Station(const char *id, const char *fw) : core(hal, id, fw, "sim") {}
};

Station *S(void *h) { return static_cast<Station *>(h); }

}  // namespace

extern "C" {

void *sc_create(const char *station_id, const char *fw_version, uint32_t boot_id, sc_publish_fn fn, void *user) {
  Station *s = new Station(station_id, fw_version);
  s->hal.publish_fn = fn;
  s->hal.user = user;
  s->core.begin(boot_id);
  return s;
}
void sc_destroy(void *h) { delete S(h); }

void sc_set_time(void *h, uint32_t ms) { S(h)->hal.now = ms; }
void sc_set_button(void *h, int button, int pressed) {
  if (button >= 0 && button < (int)sfal::kButtonCount) S(h)->hal.buttons[button] = pressed != 0;
}
void sc_set_temp(void *h, int valid, float celsius) {
  S(h)->hal.temp_valid = valid != 0;
  S(h)->hal.temp = celsius;
}
void sc_push_scan(void *h, const char *code) { S(h)->hal.scans.push_back(code ? code : ""); }
void sc_set_link(void *h, int up) { S(h)->hal.link = up != 0; }
void sc_on_message(void *h, const char *topic, const char *payload) { S(h)->core.onMessage(topic, payload); }
void sc_loop(void *h) { S(h)->core.loop(); }

// Saídas: bit0 verde, bit1 amarelo, bit2 vermelho, bit3 buzina.
int sc_outputs(void *h) {
  const SimHal &x = S(h)->hal;
  return (x.green ? 1 : 0) | (x.yellow ? 2 : 0) | (x.red ? 4 : 0) | (x.buzzer ? 8 : 0);
}
int sc_state(void *h) { return (int)S(h)->core.state(); }
const char *sc_state_name(void *h) { return S(h)->core.stateName(); }
const char *sc_unit(void *h) { return S(h)->core.unit(); }
const char *sc_block_reason(void *h) { return S(h)->core.blockReason(); }
int sc_call_active(void *h) { return S(h)->core.callActive() ? 1 : 0; }
int sc_queued(void *h) { return (int)S(h)->core.queued(); }
const char *sc_will_topic(void *h) { return S(h)->core.willTopic(); }
const char *sc_will_payload(void *h) { return S(h)->core.willPayload(); }
const char *sc_command_filter(void *h) { return S(h)->core.commandFilter(); }

}  // extern "C"
