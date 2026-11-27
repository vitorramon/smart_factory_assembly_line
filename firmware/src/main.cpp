// Firmware da estação para ESP32 (framework Arduino).
//
// Este arquivo só liga o núcleo (lib/station_core) ao hardware: pinos, Wi-Fi e MQTT.
// Toda regra de funcionamento está no núcleo, que é o mesmo código executado pelo simulador.
//
// A rede roda numa tarefa própria: conexão lenta ou broker fora do ar não travam os botões.
#include <Arduino.h>
#include <MQTT.h>
#include <WiFi.h>

#include "pins.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#warning "include/secrets.h não existe: compilando com credenciais vazias (copie secrets.h.example)"
#include "secrets.h.example"
#endif
#include "station_core.h"

#if defined(SFAL_TEMP_DHT22)
#include <DHT.h>
static DHT dht(PIN_DHT, DHT22);
#endif

#ifndef SFAL_STATION_ID
#error "Defina SFAL_STATION_ID (veja platformio.ini)"
#endif
#ifndef SFAL_FW_VERSION
#define SFAL_FW_VERSION "dev"
#endif

static WiFiClient net;
static MQTTClient mqtt(512);
static SemaphoreHandle_t mqtt_mutex;
static volatile bool link_up = false;

class Esp32Hal : public sfal::Hal {
 public:
  uint32_t millis() override { return ::millis(); }

  bool buttonPressed(sfal::Button b) override {
    if (virtual_until_[(uint8_t)b] && (int32_t)(virtual_until_[(uint8_t)b] - ::millis()) > 0) return true;
    virtual_until_[(uint8_t)b] = 0;
    switch (b) {
      case sfal::Button::Start: return digitalRead(PIN_BTN_START) == LOW;
      case sfal::Button::Fail: return digitalRead(PIN_BTN_FAIL) == LOW;
      case sfal::Button::Call: return digitalRead(PIN_BTN_CALL) == LOW;
    }
    return false;
  }

  bool readTemperature(float &celsius) override {
#if defined(SFAL_TEMP_DHT22)
    const float t = dht.readTemperature();
    if (isnan(t)) return false;
    celsius = t;
    return true;
#elif defined(SFAL_TEMP_MAX6675)
    // Leitura de 16 bits por software: D14..D3 = temperatura em passos de 0,25 °C; D2 = termopar aberto.
    uint16_t v = 0;
    digitalWrite(PIN_TC_CS, LOW);
    delayMicroseconds(10);
    for (int i = 0; i < 16; i++) {
      digitalWrite(PIN_TC_SCK, HIGH);
      delayMicroseconds(10);
      v = (uint16_t)((v << 1) | (digitalRead(PIN_TC_SO) ? 1 : 0));
      digitalWrite(PIN_TC_SCK, LOW);
      delayMicroseconds(10);
    }
    digitalWrite(PIN_TC_CS, HIGH);
    if (v & 0x4) return false;
    celsius = (float)(v >> 3) * 0.25f;
    return true;
#else
    (void)celsius;
    return false;
#endif
  }

  // Códigos chegam do leitor na UART2 ou digitados no monitor serial (USB), terminados por nova linha.
  // No monitor serial, "!start", "!fail" e "!call" simulam um toque no botão (teste de bancada sem botões).
  bool readScan(char *buf, size_t len) override {
    if (readLine(Serial2, scan_buf_, scan_len_, buf, len)) return true;
    if (readLine(Serial, usb_buf_, usb_len_, buf, len)) {
      if (buf[0] != '!') return true;
      if (strcmp(buf, "!start") == 0) tap(sfal::Button::Start);
      else if (strcmp(buf, "!fail") == 0) tap(sfal::Button::Fail);
      else if (strcmp(buf, "!call") == 0) tap(sfal::Button::Call);
    }
    return false;
  }

  void setLight(bool g, bool y, bool r) override {
    digitalWrite(PIN_LED_GREEN, g);
    digitalWrite(PIN_LED_YELLOW, y);
    digitalWrite(PIN_LED_RED, r);
  }
  void setBuzzer(bool on) override { digitalWrite(PIN_BUZZER, on); }

  bool linkUp() override { return link_up; }

  bool publish(const char *topic, const char *payload, uint8_t qos, bool retain) override {
    if (!link_up) return false;
    if (xSemaphoreTake(mqtt_mutex, pdMS_TO_TICKS(20)) != pdTRUE) return false;
    const bool ok = mqtt.publish(topic, payload, retain, qos);
    xSemaphoreGive(mqtt_mutex);
    return ok;
  }

  int rssi() override { return WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0; }

 private:
  void tap(sfal::Button b) { virtual_until_[(uint8_t)b] = (::millis() + 120) | 1; }

  static bool readLine(Stream &s, char *acc, size_t &acc_len, char *out, size_t out_len) {
    while (s.available()) {
      const char c = (char)s.read();
      if (c == '\n' || c == '\r') {
        if (acc_len == 0) continue;
        acc[acc_len] = '\0';
        strncpy(out, acc, out_len - 1);
        out[out_len - 1] = '\0';
        acc_len = 0;
        return true;
      }
      if (acc_len + 1 < 64) acc[acc_len++] = c;
    }
    return false;
  }

  char scan_buf_[64];
  size_t scan_len_ = 0;
  char usb_buf_[64];
  size_t usb_len_ = 0;
  uint32_t virtual_until_[sfal::kButtonCount] = {0, 0, 0};
};

static Esp32Hal hal;
static sfal::StationCore core(hal, SFAL_STATION_ID, SFAL_FW_VERSION, "esp32");

// Comandos chegam na tarefa de rede; o núcleo roda na tarefa principal. Uma caixa de entrada de uma
// posição por comando basta: release, light e config são idempotentes e o último vence.
struct Inbox {
  char topic[sfal::kTopicLen];
  char payload[sfal::kPayloadLen];
};
static QueueHandle_t inbox;

static void onMqttMessage(String &topic, String &payload) {
  Inbox m;
  strlcpy(m.topic, topic.c_str(), sizeof(m.topic));
  strlcpy(m.payload, payload.c_str(), sizeof(m.payload));
  xQueueSend(inbox, &m, 0);
}

static void networkTask(void *) {
  uint32_t backoff_ms = 1000;
  for (;;) {
    if (WiFi.status() != WL_CONNECTED) {
      link_up = false;
      WiFi.begin(WIFI_SSID, WIFI_PASS);
      for (int i = 0; i < 100 && WiFi.status() != WL_CONNECTED; i++) vTaskDelay(pdMS_TO_TICKS(100));
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[rede] Wi-Fi sem conexão; nova tentativa");
        WiFi.disconnect();
        vTaskDelay(pdMS_TO_TICKS(2000));
        continue;
      }
      Serial.printf("[rede] Wi-Fi ok, IP %s\n", WiFi.localIP().toString().c_str());
    }

    xSemaphoreTake(mqtt_mutex, portMAX_DELAY);
    bool connected = mqtt.connected();
    if (!connected) {
      link_up = false;
      const char *user = strlen(MQTT_USER) ? MQTT_USER : nullptr;
      const char *pass = strlen(MQTT_PASS) ? MQTT_PASS : nullptr;
      char client_id[40];
      snprintf(client_id, sizeof(client_id), "sfal-%s", SFAL_STATION_ID);
      mqtt.setWill(core.willTopic(), core.willPayload(), true, 1);
      connected = mqtt.connect(client_id, user, pass);
      if (connected) {
        mqtt.subscribe(core.commandFilter(), 1);
        Serial.printf("[rede] MQTT ok em %s:%d\n", MQTT_HOST, MQTT_PORT);
        backoff_ms = 1000;
      }
    } else {
      mqtt.loop();
    }
    xSemaphoreGive(mqtt_mutex);

    link_up = connected;
    if (!connected) {
      Serial.printf("[rede] broker %s:%d inacessível; nova tentativa em %lu ms\n", MQTT_HOST, MQTT_PORT,
                    (unsigned long)backoff_ms);
      vTaskDelay(pdMS_TO_TICKS(backoff_ms));
      if (backoff_ms < 15000) backoff_ms *= 2;
    } else {
      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(SCAN_BAUD, SERIAL_8N1, PIN_SCAN_RX, PIN_SCAN_TX);

  pinMode(PIN_BTN_START, INPUT_PULLUP);
  pinMode(PIN_BTN_FAIL, INPUT_PULLUP);
  pinMode(PIN_BTN_CALL, INPUT_PULLUP);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
#if defined(SFAL_TEMP_DHT22)
  dht.begin();
#elif defined(SFAL_TEMP_MAX6675)
  pinMode(PIN_TC_SCK, OUTPUT);
  pinMode(PIN_TC_CS, OUTPUT);
  pinMode(PIN_TC_SO, INPUT);
  digitalWrite(PIN_TC_CS, HIGH);
  digitalWrite(PIN_TC_SCK, LOW);
#endif

  mqtt_mutex = xSemaphoreCreateMutex();
  inbox = xQueueCreate(8, sizeof(Inbox));

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  mqtt.begin(MQTT_HOST, MQTT_PORT, net);
  mqtt.setOptions(10, true, 2000);  // keep-alive de 10 s, sessão limpa, tempo limite de 2 s
  mqtt.onMessage(onMqttMessage);

  core.begin(esp_random());
  Serial.printf("\n[sfal] estação %s, firmware %s\n", SFAL_STATION_ID, SFAL_FW_VERSION);

  xTaskCreatePinnedToCore(networkTask, "rede", 8192, nullptr, 1, nullptr, 0);
}

void loop() {
  Inbox m;
  while (xQueueReceive(inbox, &m, 0) == pdTRUE) core.onMessage(m.topic, m.payload);

  static sfal::State last = sfal::State::Idle;
  core.loop();
  if (core.state() != last) {
    last = core.state();
    Serial.printf("[sfal] %s unidade=%s %s\n", core.stateName(), core.unit(), core.blockReason());
  }
  delay(2);
}
