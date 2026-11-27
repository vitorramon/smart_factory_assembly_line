#include "station_core.h"

#include <stdio.h>
#include <string.h>

#include "json_mini.h"

namespace sfal {
namespace {

const uint32_t kDebounceMs = 25;
const uint32_t kMinCycleMs = 300;      // FIM antes disso é toque duplo
const uint32_t kBlockedHoldMs = 4000;  // bloqueio se desfaz sozinho depois disso
const uint32_t kBlockedBuzzMs = 600;
const uint32_t kRetryMs = 500;         // espera após uma publicação recusada
const uint8_t kFlushPerLoop = 4;

bool blink(uint32_t now, uint32_t period_ms) { return ((now / (period_ms / 2)) & 1u) == 0; }

}  // namespace

void sanitizeToken(char *dst, size_t dst_len, const char *src) {
  size_t n = 0;
  if (dst_len == 0) return;
  for (const char *p = src ? src : ""; *p && n + 1 < dst_len; p++) {
    const char c = *p;
    if (c > 0x20 && c < 0x7f && c != '"' && c != '\\') dst[n++] = c;
  }
  dst[n] = '\0';
}

StationCore::StationCore(Hal &hal, const char *station_id, const char *fw_version, const char *hw_kind)
    : hal_(hal) {
  sanitizeToken(id_, sizeof(id_), station_id);
  sanitizeToken(fw_, sizeof(fw_), fw_version);
  sanitizeToken(hw_, sizeof(hw_), hw_kind);
  unit_[0] = '\0';
  reason_[0] = '\0';
  topic(status_topic_, "status");
  topic(cmd_filter_, "cmd/#");
  topic(cmd_prefix_, "cmd/");
}

void StationCore::topic(char *out, const char *suffix) const {
  snprintf(out, kTopicLen, "sfal/v1/%s/%s", id_, suffix);
}

const char *StationCore::stateName() const {
  switch (state_) {
    case State::Idle: return "IDLE";
    case State::WaitRelease: return "WAIT";
    case State::Running: return "RUNNING";
    case State::Blocked: return "BLOCKED";
  }
  return "?";
}

void StationCore::begin(uint32_t boot_id) {
  boot_ = boot_id;
  seq_ = 0;
  t_begin_ = hal_.millis();
  t_last_tel_ = t_begin_;
  state_ = State::Idle;
  link_was_up_ = false;
  hal_.setLight(false, false, false);
  hal_.setBuzzer(false);
}

void StationCore::setState(State s) {
  if (s != state_) {
    state_ = s;
    tel_dirty_ = true;
  }
}

// Debounce por tempo: o nível precisa ficar estável por kDebounceMs. Devolve true na borda de aperto.
bool StationCore::pressed(Button b, uint32_t now) {
  Debounce &d = btn_[(uint8_t)b];
  const bool raw = hal_.buttonPressed(b);
  if (raw != d.last_raw) {
    d.last_raw = raw;
    d.t_change = now;
  }
  if (raw != d.stable && (uint32_t)(now - d.t_change) >= kDebounceMs) {
    d.stable = raw;
    return raw;
  }
  return false;
}

uint32_t StationCore::enqueue(EvKind kind, const char *unit, uint32_t dur_ms, bool flag, bool degraded,
                              uint32_t now) {
  if (q_count_ == kQueueLen) {  // cheio: descarta o mais antigo e conta
    q_head_ = (q_head_ + 1) % kQueueLen;
    q_count_--;
    dropped_++;
  }
  Event &e = queue_[(q_head_ + q_count_) % kQueueLen];
  e.kind = kind;
  e.seq = ++seq_;
  e.t_ms = now;
  e.dur_ms = dur_ms;
  e.flag = flag;
  e.degraded = degraded;
  sanitizeToken(e.unit, sizeof(e.unit), unit);
  q_count_++;
  return e.seq;
}

void StationCore::requestStart(const char *code, uint32_t now) {
  if (call_) return;  // estação parada por chamado: não inicia ciclo
  sanitizeToken(unit_, sizeof(unit_), code);
  reason_[0] = '\0';
  t_request_ = now;
  req_seq_ = enqueue(EvKind::Scan, unit_, 0, false, false, now);
  if (!cfg_.interlock) {
    startCycle(false);
  } else if (hal_.linkUp()) {
    setState(State::WaitRelease);
  } else if (cfg_.fail_open) {
    startCycle(true);
  } else {
    block("no_link", now);
  }
}

void StationCore::startCycle(bool degraded) {
  degraded_ = degraded;
  setState(State::Running);
}

void StationCore::finishCycle(bool ok, uint32_t now) {
  enqueue(EvKind::Cycle, unit_, (uint32_t)(now - t_request_), ok, degraded_, now);
  unit_[0] = '\0';
  setState(State::Idle);
}

void StationCore::block(const char *reason, uint32_t now) {
  sanitizeToken(reason_, sizeof(reason_), reason);
  t_block_ = now;
  setState(State::Blocked);
}

void StationCore::onMessage(const char *topic, const char *payload) {
  const size_t prefix_len = strlen(cmd_prefix_);
  if (!topic || !payload || strncmp(topic, cmd_prefix_, prefix_len) != 0) return;
  const char *cmd = topic + prefix_len;
  const uint32_t now = hal_.millis();

  if (strcmp(cmd, "release") == 0) {
    long req = 0;
    bool ok = false;
    if (state_ != State::WaitRelease) return;
    if (!jsonGetInt(payload, "req", req) || (uint32_t)req != req_seq_) return;  // resposta velha
    if (!jsonGetBool(payload, "ok", ok)) return;
    if (ok) {
      char unit[kUnitLen];
      // O servidor pode atribuir a unidade (estação sem leitor: fila FIFO).
      if (jsonGetString(payload, "unit", unit, sizeof(unit)) && unit[0]) {
        sanitizeToken(unit_, sizeof(unit_), unit);
      }
      startCycle(false);
    } else {
      char reason[kReasonLen] = "denied";
      jsonGetString(payload, "reason", reason, sizeof(reason));
      block(reason, now);
    }
  } else if (strcmp(cmd, "result") == 0) {
    // Resultado de uma inspeção automática (câmera + IA no servidor): encerra o ciclo como o botão faria.
    // Vale só para a unidade em processo; resultado de outra unidade ou fora de ciclo é ignorado.
    bool ok = false;
    char unit[kUnitLen];
    if (state_ != State::Running || !jsonGetBool(payload, "ok", ok)) return;
    if (!jsonGetString(payload, "unit", unit, sizeof(unit)) || strcmp(unit, unit_) != 0) return;
    finishCycle(ok, now);
  } else if (strcmp(cmd, "light") == 0) {
    char level[12];
    if (!jsonGetString(payload, "level", level, sizeof(level))) return;
    if (strcmp(level, "auto") == 0) override_ = LightLevel::Auto;
    else if (strcmp(level, "off") == 0) override_ = LightLevel::Off;
    else if (strcmp(level, "green") == 0) override_ = LightLevel::Green;
    else if (strcmp(level, "yellow") == 0) override_ = LightLevel::Yellow;
    else if (strcmp(level, "red") == 0) override_ = LightLevel::Red;
  } else if (strcmp(cmd, "config") == 0) {
    long v = 0;
    bool b = false;
    if (jsonGetInt(payload, "takt_ms", v) && v >= 0) cfg_.takt_ms = (uint32_t)v;
    if (jsonGetInt(payload, "tel_ms", v) && v >= 200) cfg_.tel_ms = (uint32_t)v;
    if (jsonGetInt(payload, "release_timeout_ms", v) && v >= 100) cfg_.release_timeout_ms = (uint32_t)v;
    if (jsonGetBool(payload, "interlock", b)) cfg_.interlock = b;
    if (jsonGetBool(payload, "fail_open", b)) cfg_.fail_open = b;
  }
}

void StationCore::loop() {
  const uint32_t now = hal_.millis();

  // Enlace: ao (re)conectar, anuncia o status retido.
  const bool link = hal_.linkUp();
  if (link && !link_was_up_) {
    status_pending_ = true;
    retry_wait_ = false;
    tel_dirty_ = true;
  }
  link_was_up_ = link;
  if (link && status_pending_) publishStatus();

  // Entradas.
  const bool start = pressed(Button::Start, now);
  const bool fail = pressed(Button::Fail, now);
  const bool call = pressed(Button::Call, now);
  char code[kUnitLen];
  const bool scanned = hal_.readScan(code, sizeof(code));

  if (call) {
    call_ = !call_;
    enqueue(EvKind::Call, "", 0, call_, false, now);
    tel_dirty_ = true;
  }

  switch (state_) {
    case State::Idle:
      if (scanned) requestStart(code, now);
      else if (start) requestStart("", now);
      break;

    case State::WaitRelease:
      if ((uint32_t)(now - t_request_) >= cfg_.release_timeout_ms) {
        if (cfg_.fail_open) startCycle(true);
        else block("no_server", now);
      }
      break;

    case State::Running:
      if ((uint32_t)(now - t_request_) >= kMinCycleMs) {
        if (fail) finishCycle(false, now);
        else if (start) finishCycle(true, now);
      }
      break;

    case State::Blocked:
      if (scanned) {
        setState(State::Idle);
        requestStart(code, now);
      } else if (start || (uint32_t)(now - t_block_) >= kBlockedHoldMs) {
        unit_[0] = '\0';
        setState(State::Idle);  // operador reconheceu (ou o tempo passou)
      }
      break;
  }

  if (link) {
    flushQueue(now);
    if (tel_dirty_ || (uint32_t)(now - t_last_tel_) >= cfg_.tel_ms) publishTelemetry(now);
  }
  updateOutputs(now);
}

void StationCore::flushQueue(uint32_t now) {
  if (retry_wait_ && (uint32_t)(now - t_last_try_) < kRetryMs) return;
  retry_wait_ = false;
  char t[kTopicLen];
  char p[kPayloadLen];
  for (uint8_t i = 0; i < kFlushPerLoop && q_count_ > 0; i++) {
    const Event &e = queue_[q_head_];
    const unsigned long age = (uint32_t)(now - e.t_ms);
    switch (e.kind) {
      case EvKind::Scan:
        topic(t, "evt/scan");
        snprintf(p, sizeof(p), "{\"seq\":%lu,\"boot\":%lu,\"age_ms\":%lu,\"unit\":\"%s\"}",
                 (unsigned long)e.seq, (unsigned long)boot_, age, e.unit);
        break;
      case EvKind::Cycle:
        topic(t, "evt/cycle");
        snprintf(p, sizeof(p),
                 "{\"seq\":%lu,\"boot\":%lu,\"age_ms\":%lu,\"unit\":\"%s\",\"dur_ms\":%lu,\"ok\":%s,\"degraded\":%s}",
                 (unsigned long)e.seq, (unsigned long)boot_, age, e.unit, (unsigned long)e.dur_ms,
                 e.flag ? "true" : "false", e.degraded ? "true" : "false");
        break;
      case EvKind::Call:
        topic(t, "evt/call");
        snprintf(p, sizeof(p), "{\"seq\":%lu,\"boot\":%lu,\"age_ms\":%lu,\"on\":%s}", (unsigned long)e.seq,
                 (unsigned long)boot_, age, e.flag ? "true" : "false");
        break;
    }
    if (!hal_.publish(t, p, 1, false)) {
      t_last_try_ = now;
      retry_wait_ = true;
      return;
    }
    q_head_ = (q_head_ + 1) % kQueueLen;
    q_count_--;
  }
}

void StationCore::publishStatus() {
  char p[kPayloadLen];
  snprintf(p, sizeof(p), "{\"online\":true,\"fw\":\"%s\",\"hw\":\"%s\",\"boot\":%lu}", fw_, hw_,
           (unsigned long)boot_);
  if (hal_.publish(status_topic_, p, 1, true)) status_pending_ = false;
}

void StationCore::publishTelemetry(uint32_t now) {
  char t[kTopicLen];
  char p[kPayloadLen];
  char temp[16] = "null";
  float celsius = 0;
  if (hal_.readTemperature(celsius)) snprintf(temp, sizeof(temp), "%.2f", (double)celsius);
  const unsigned long cycle_ms =
      (state_ == State::Running || state_ == State::WaitRelease) ? (uint32_t)(now - t_request_) : 0;
  topic(t, "tel");
  snprintf(p, sizeof(p),
           "{\"boot\":%lu,\"up_ms\":%lu,\"state\":\"%s\",\"unit\":\"%s\",\"cycle_ms\":%lu,\"call\":%s,"
           "\"temp\":%s,\"rssi\":%d,\"queued\":%u,\"dropped\":%lu,\"reason\":\"%s\"}",
           (unsigned long)boot_, (unsigned long)(uint32_t)(now - t_begin_), stateName(), unit_, cycle_ms,
           call_ ? "true" : "false", temp, hal_.rssi(), (unsigned)q_count_, (unsigned long)dropped_,
           state_ == State::Blocked ? reason_ : "");
  hal_.publish(t, p, 0, false);
  t_last_tel_ = now;
  tel_dirty_ = false;
}

// Torre luminosa. Prioridade: chamado > bloqueio > comando do servidor > rede fora > estado do ciclo.
void StationCore::updateOutputs(uint32_t now) {
  bool g = false, y = false, r = false, buzz = false;
  if (call_) {
    r = blink(now, 500);
    buzz = (now % 2000u) < 100u;
  } else if (state_ == State::Blocked) {
    r = true;
    buzz = (uint32_t)(now - t_block_) < kBlockedBuzzMs;
  } else if (override_ != LightLevel::Auto) {
    g = override_ == LightLevel::Green;
    y = override_ == LightLevel::Yellow;
    r = override_ == LightLevel::Red;
  } else {
    if (state_ == State::Running) {
      const bool late = cfg_.takt_ms > 0 && (uint32_t)(now - t_request_) > cfg_.takt_ms;
      g = !late;
      y = late;
    } else if (state_ == State::WaitRelease) {
      g = blink(now, 200);
    }
    if (!hal_.linkUp()) y = blink(now, 1000);  // modo degradado: amarelo piscando
  }
  hal_.setLight(g, y, r);
  hal_.setBuzzer(buzz);
}

}  // namespace sfal
