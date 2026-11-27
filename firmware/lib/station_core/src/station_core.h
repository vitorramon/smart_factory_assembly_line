// Lógica de uma estação da linha, independente de placa.
//
// Uma estação: recebe uma unidade (leitura de código ou botão INICIAR), pede liberação ao servidor
// (intertravamento de rota: unidade reprovada antes não avança), cronometra o ciclo, registra o
// resultado (OK / NOK), aciona a torre luminosa e a buzina, e guarda os eventos quando a rede cai.
//
// Protocolo MQTT em docs/PROTOCOL.md. O dispositivo nunca envia data/hora: envia `age_ms`
// (há quanto tempo o evento ocorreu) e o servidor carimba o instante.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "hal.h"

namespace sfal {

enum class State : uint8_t { Idle = 0, WaitRelease = 1, Running = 2, Blocked = 3 };
enum class LightLevel : uint8_t { Auto = 0, Off = 1, Green = 2, Yellow = 3, Red = 4 };

const size_t kUnitLen = 32;     // identificador de unidade, com o terminador
const size_t kReasonLen = 24;
const size_t kQueueLen = 24;    // eventos guardados enquanto a rede está fora
const size_t kTopicLen = 96;
const size_t kPayloadLen = 256;

// Parâmetros que o servidor ajusta em tempo de execução (tópico cmd/config, retido).
struct Settings {
  uint32_t takt_ms = 0;               // 0 = sem aviso de ciclo estourado
  uint32_t tel_ms = 2000;             // período da telemetria
  uint32_t release_timeout_ms = 1500; // espera pela liberação do servidor
  bool interlock = true;              // false = inicia o ciclo sem perguntar
  bool fail_open = true;              // sem resposta: true segue em modo degradado, false bloqueia
};

class StationCore {
 public:
  StationCore(Hal &hal, const char *station_id, const char *fw_version, const char *hw_kind);

  void begin(uint32_t boot_id);
  void loop();
  void onMessage(const char *topic, const char *payload);

  // Para a camada de transporte configurar o Last Will e a assinatura.
  const char *willTopic() const { return status_topic_; }
  const char *willPayload() const { return "{\"online\":false}"; }
  const char *commandFilter() const { return cmd_filter_; }

  State state() const { return state_; }
  const char *stateName() const;
  const char *unit() const { return unit_; }
  const char *blockReason() const { return reason_; }
  bool callActive() const { return call_; }
  size_t queued() const { return q_count_; }
  const Settings &settings() const { return cfg_; }

 private:
  enum class EvKind : uint8_t { Scan, Cycle, Call };
  struct Event {
    EvKind kind;
    uint32_t seq;
    uint32_t t_ms;
    uint32_t dur_ms;
    bool flag;      // Cycle: ok; Call: on
    bool degraded;
    char unit[kUnitLen];
  };
  struct Debounce {
    bool stable = false;
    bool last_raw = false;
    uint32_t t_change = 0;
  };

  bool pressed(Button b, uint32_t now);
  void requestStart(const char *code, uint32_t now);
  void startCycle(bool degraded);
  void finishCycle(bool ok, uint32_t now);
  void block(const char *reason, uint32_t now);
  void setState(State s);
  uint32_t enqueue(EvKind kind, const char *unit, uint32_t dur_ms, bool flag, bool degraded, uint32_t now);
  void flushQueue(uint32_t now);
  void publishStatus();
  void publishTelemetry(uint32_t now);
  void updateOutputs(uint32_t now);
  void topic(char *out, const char *suffix) const;

  Hal &hal_;
  char id_[24];
  char fw_[16];
  char hw_[12];
  char status_topic_[kTopicLen];
  char cmd_filter_[kTopicLen];
  char cmd_prefix_[kTopicLen];

  Settings cfg_;
  uint32_t boot_ = 0;
  uint32_t seq_ = 0;
  uint32_t t_begin_ = 0;

  State state_ = State::Idle;
  char unit_[kUnitLen];
  char reason_[kReasonLen];
  uint32_t t_request_ = 0;   // instante do pedido de início (é o início do ciclo)
  uint32_t t_block_ = 0;
  uint32_t req_seq_ = 0;     // seq do evento scan que aguarda liberação
  bool degraded_ = false;
  bool call_ = false;
  LightLevel override_ = LightLevel::Auto;

  Debounce btn_[kButtonCount];

  Event queue_[kQueueLen];
  size_t q_head_ = 0;
  size_t q_count_ = 0;
  uint32_t dropped_ = 0;
  uint32_t t_last_try_ = 0;
  bool retry_wait_ = false;

  bool link_was_up_ = false;
  bool status_pending_ = false;
  bool tel_dirty_ = false;
  uint32_t t_last_tel_ = 0;
};

// Copia um identificador mantendo só ASCII imprimível seguro para JSON (sem aspas nem barra invertida).
void sanitizeToken(char *dst, size_t dst_len, const char *src);

}  // namespace sfal
