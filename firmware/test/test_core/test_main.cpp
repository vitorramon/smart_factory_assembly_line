// Testes do núcleo da estação no PC (pio test -e native).
#include <unity.h>

#include <stdio.h>
#include <string.h>

#include <deque>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "json_mini.h"
#include "station_core.h"

using namespace sfal;

namespace {

struct Msg {
  std::string topic, payload;
  int qos;
  bool retain;
};

class TestHal : public Hal {
 public:
  uint32_t now = 0;
  bool btn[kButtonCount] = {false, false, false};
  bool temp_valid = false;
  float temp = 0;
  std::deque<std::string> scans;
  bool link = true;
  bool accept = true;  // false = publish devolve erro
  bool g = false, y = false, r = false, buzz = false;
  std::vector<Msg> sent;

  uint32_t millis() override { return now; }
  bool buttonPressed(Button b) override { return btn[(uint8_t)b]; }
  bool readTemperature(float &c) override {
    c = temp;
    return temp_valid;
  }
  bool readScan(char *buf, size_t len) override {
    if (scans.empty()) return false;
    strncpy(buf, scans.front().c_str(), len - 1);
    buf[len - 1] = '\0';
    scans.pop_front();
    return true;
  }
  void setLight(bool G, bool Y, bool R) override {
    g = G;
    y = Y;
    r = R;
  }
  void setBuzzer(bool on) override { buzz = on; }
  bool linkUp() override { return link; }
  bool publish(const char *t, const char *p, uint8_t qos, bool retain) override {
    if (!link || !accept) return false;
    sent.push_back({t, p, qos, retain});
    return true;
  }
  int rssi() override { return 0; }

  int outputs() const { return (g ? 1 : 0) | (y ? 2 : 0) | (r ? 4 : 0) | (buzz ? 8 : 0); }
  // Conta as mensagens cujo tópico termina com o sufixo.
  std::vector<Msg> on(const char *suffix) const {
    std::vector<Msg> out;
    const std::string s(suffix);
    for (const Msg &m : sent)
      if (m.topic.size() >= s.size() && m.topic.compare(m.topic.size() - s.size(), s.size(), s) == 0)
        out.push_back(m);
    return out;
  }
};

struct Bench {
  TestHal hal;
  StationCore core;
  Bench() : core(hal, "asm", "1.0.0", "sim") { core.begin(7); }
  void run(uint32_t ms) {
    for (uint32_t i = 0; i < ms; i += 10) {
      hal.now += 10;
      core.loop();
    }
  }
  void tap(Button b) {
    hal.btn[(uint8_t)b] = true;
    run(100);
    hal.btn[(uint8_t)b] = false;
    run(100);
  }
  void rx(const char *cmd, const char *json) {
    const std::string t = std::string("sfal/v1/asm/cmd/") + cmd;
    core.onMessage(t.c_str(), json);
  }
};

bool has(const std::string &s, const char *needle) { return s.find(needle) != std::string::npos; }

}  // namespace

void setUp() {}
void tearDown() {}

void test_json_le_tipos_e_ignora_aninhado() {
  const char *j = "{ \"a\": {\"req\": 9, \"s\": \"}\"}, \"req\": 12, \"ok\": true, \"unit\": \"U-1\\\"x\", \"f\": -3.7 }";
  long n = 0;
  bool b = false;
  char s[16];
  TEST_ASSERT_TRUE(jsonGetInt(j, "req", n));
  TEST_ASSERT_EQUAL(12, n);
  TEST_ASSERT_TRUE(jsonGetBool(j, "ok", b));
  TEST_ASSERT_TRUE(b);
  TEST_ASSERT_TRUE(jsonGetString(j, "unit", s, sizeof(s)));
  TEST_ASSERT_EQUAL_STRING("U-1\"x", s);
  TEST_ASSERT_TRUE(jsonGetInt(j, "f", n));
  TEST_ASSERT_EQUAL(-3, n);
  TEST_ASSERT_FALSE(jsonGetInt(j, "s", n));
  TEST_ASSERT_FALSE(jsonGetInt(j, "ok", n));
  TEST_ASSERT_FALSE(jsonGetBool("nao e json", "ok", b));
  TEST_ASSERT_FALSE(jsonGetString("{\"unit\":\"sem fim", "unit", s, sizeof(s)));
}

void test_status_retido_ao_conectar() {
  Bench b;
  b.run(50);
  auto st = b.hal.on("/status");
  TEST_ASSERT_EQUAL(1, st.size());
  TEST_ASSERT_TRUE(st[0].retain);
  TEST_ASSERT_TRUE(has(st[0].payload, "\"online\":true"));
  TEST_ASSERT_TRUE(has(st[0].payload, "\"boot\":7"));
  TEST_ASSERT_EQUAL_STRING("sfal/v1/asm/status", b.core.willTopic());
  TEST_ASSERT_EQUAL_STRING("sfal/v1/asm/cmd/#", b.core.commandFilter());
}

void test_ciclo_liberado_mede_desde_o_pedido() {
  Bench b;
  b.run(50);
  b.hal.scans.push_back("U-1");
  b.run(20);
  TEST_ASSERT_EQUAL((int)State::WaitRelease, (int)b.core.state());
  b.rx("release", "{\"req\":1,\"ok\":true}");
  b.run(2000);
  TEST_ASSERT_EQUAL((int)State::Running, (int)b.core.state());
  TEST_ASSERT_EQUAL(1, b.hal.outputs());  // verde
  b.tap(Button::Start);
  TEST_ASSERT_EQUAL((int)State::Idle, (int)b.core.state());
  auto cy = b.hal.on("/evt/cycle");
  TEST_ASSERT_EQUAL(1, cy.size());
  TEST_ASSERT_EQUAL(1, cy[0].qos);
  TEST_ASSERT_TRUE(has(cy[0].payload, "\"unit\":\"U-1\""));
  TEST_ASSERT_TRUE(has(cy[0].payload, "\"ok\":true"));
  TEST_ASSERT_TRUE(has(cy[0].payload, "\"degraded\":false"));
  long dur = 0;
  TEST_ASSERT_TRUE(jsonGetInt(cy[0].payload.c_str(), "dur_ms", dur));
  TEST_ASSERT_INT_WITHIN(40, 2060, dur);
}

void test_repique_do_botao_nao_gera_evento() {
  Bench b;
  b.run(50);
  for (int i = 0; i < 6; i++) {  // ruído de 10 ms: nunca fica estável por 25 ms
    b.hal.btn[0] = !b.hal.btn[0];
    b.run(10);
  }
  b.hal.btn[0] = false;
  b.run(100);
  TEST_ASSERT_EQUAL(0, b.hal.on("/evt/scan").size());
}

void test_resposta_velha_e_ignorada_e_negada_bloqueia() {
  Bench b;
  b.run(50);
  b.hal.scans.push_back("U-9");
  b.run(20);
  b.rx("release", "{\"req\":99,\"ok\":true}");
  b.run(20);
  TEST_ASSERT_EQUAL((int)State::WaitRelease, (int)b.core.state());
  b.rx("release", "{\"req\":1,\"ok\":false,\"reason\":\"upstream_fail\"}");
  b.run(20);
  TEST_ASSERT_EQUAL((int)State::Blocked, (int)b.core.state());
  TEST_ASSERT_EQUAL_STRING("upstream_fail", b.core.blockReason());
  TEST_ASSERT_TRUE(b.hal.outputs() & 4);  // vermelho
  b.run(5000);                            // desfaz sozinho
  TEST_ASSERT_EQUAL((int)State::Idle, (int)b.core.state());
  TEST_ASSERT_EQUAL(0, b.hal.on("/evt/cycle").size());
}

void test_sem_resposta_segue_degradado_ou_bloqueia() {
  Bench b;
  b.run(50);
  b.hal.scans.push_back("U-2");
  b.run(1600);
  TEST_ASSERT_EQUAL((int)State::Running, (int)b.core.state());
  b.tap(Button::Fail);
  auto cy = b.hal.on("/evt/cycle");
  TEST_ASSERT_TRUE(has(cy[0].payload, "\"ok\":false"));
  TEST_ASSERT_TRUE(has(cy[0].payload, "\"degraded\":true"));

  b.rx("config", "{\"fail_open\":false,\"release_timeout_ms\":500}");
  b.hal.scans.push_back("U-3");
  b.run(600);
  TEST_ASSERT_EQUAL((int)State::Blocked, (int)b.core.state());
  TEST_ASSERT_EQUAL_STRING("no_server", b.core.blockReason());
}

void test_rede_fora_guarda_eventos_e_envia_com_idade() {
  Bench b;
  b.run(50);
  b.hal.link = false;
  b.hal.scans.push_back("U-5");
  b.run(1000);
  b.tap(Button::Start);
  TEST_ASSERT_EQUAL(2, b.core.queued());
  TEST_ASSERT_EQUAL(0, b.hal.on("/evt/cycle").size());
  b.run(3000);
  b.hal.link = true;
  b.run(50);
  TEST_ASSERT_EQUAL(0, b.core.queued());
  TEST_ASSERT_EQUAL(2, b.hal.on("/status").size());
  auto cy = b.hal.on("/evt/cycle");
  TEST_ASSERT_EQUAL(1, cy.size());
  long age = 0;
  TEST_ASSERT_TRUE(jsonGetInt(cy[0].payload.c_str(), "age_ms", age));
  TEST_ASSERT_INT_WITHIN(150, 3100, age);
}

void test_publicacao_recusada_e_repetida_sem_perder_ordem() {
  Bench b;
  b.run(50);
  b.hal.accept = false;
  b.tap(Button::Call);
  b.tap(Button::Call);
  TEST_ASSERT_EQUAL(2, b.core.queued());
  b.hal.accept = true;
  b.run(600);
  auto ev = b.hal.on("/evt/call");
  TEST_ASSERT_EQUAL(2, ev.size());
  TEST_ASSERT_TRUE(has(ev[0].payload, "\"seq\":1") && has(ev[0].payload, "\"on\":true"));
  TEST_ASSERT_TRUE(has(ev[1].payload, "\"seq\":2") && has(ev[1].payload, "\"on\":false"));
}

void test_fila_cheia_descarta_o_mais_antigo() {
  Bench b;
  b.run(50);
  b.hal.link = false;
  for (size_t i = 0; i < kQueueLen + 3; i++) b.tap(Button::Call);
  TEST_ASSERT_EQUAL(kQueueLen, b.core.queued());
  b.hal.link = true;
  b.run(200);
  auto ev = b.hal.on("/evt/call");
  TEST_ASSERT_EQUAL(kQueueLen, ev.size());
  TEST_ASSERT_TRUE(has(ev[0].payload, "\"seq\":4,"));
  TEST_ASSERT_TRUE(has(b.hal.on("/tel").back().payload, "\"dropped\":3"));
}

void test_chamado_impede_inicio_e_pisca_vermelho() {
  Bench b;
  b.run(50);
  b.tap(Button::Call);
  TEST_ASSERT_TRUE(b.core.callActive());
  b.hal.scans.push_back("U-7");
  b.run(100);
  TEST_ASSERT_EQUAL((int)State::Idle, (int)b.core.state());
  bool viu_vermelho = false, viu_apagado = false;
  for (int i = 0; i < 100; i++) {
    b.run(10);
    if (b.hal.outputs() & 4) viu_vermelho = true;
    else viu_apagado = true;
  }
  TEST_ASSERT_TRUE(viu_vermelho && viu_apagado);
}

void test_takt_estourado_acende_amarelo_e_identificador_e_saneado() {
  Bench b;
  b.run(50);
  b.rx("config", "{\"takt_ms\":1000,\"interlock\":false}");
  b.hal.scans.push_back(" U\"7\\ x ");
  b.run(500);
  TEST_ASSERT_EQUAL_STRING("U7x", b.core.unit());
  TEST_ASSERT_EQUAL(1, b.hal.outputs());
  b.run(700);
  TEST_ASSERT_EQUAL(2, b.hal.outputs());
}

void test_resultado_da_inspecao_automatica_encerra_o_ciclo() {
  Bench b;
  b.run(50);
  b.hal.scans.push_back("U-8");
  b.run(20);
  b.rx("release", "{\"req\":1,\"ok\":true}");
  b.run(1000);
  b.rx("result", "{\"unit\":\"U-9\",\"ok\":false}");  // outra unidade: ignora
  b.rx("result", "{\"ok\":false}");                      // sem unidade: ignora
  b.run(20);
  TEST_ASSERT_EQUAL((int)State::Running, (int)b.core.state());
  b.rx("result", "{\"unit\":\"U-8\",\"ok\":false}");
  b.run(20);
  TEST_ASSERT_EQUAL((int)State::Idle, (int)b.core.state());
  auto cy = b.hal.on("/evt/cycle");
  TEST_ASSERT_EQUAL(1, cy.size());
  TEST_ASSERT_TRUE(has(cy[0].payload, "\"unit\":\"U-8\"") && has(cy[0].payload, "\"ok\":false"));
  b.rx("result", "{\"unit\":\"U-8\",\"ok\":true}");   // fora de ciclo: ignora
  b.run(20);
  TEST_ASSERT_EQUAL(1, b.hal.on("/evt/cycle").size());
}

// Mesmo roteiro e mesmo formato de traço de software/sfal/sim/golden.py.
void test_roteiro_de_referencia() {
  std::ifstream script("test/golden/turno.script");
  TEST_ASSERT_TRUE_MESSAGE(script.good(), "rode a partir da pasta firmware/");
  Bench b;
  b.hal.link = false;
  std::ostringstream trace;
  size_t sent_seen = 0;
  int last_out = 0;
  auto advance = [&](uint32_t until) {
    while (b.hal.now < until) {
      b.hal.now += 10;
      b.core.loop();
      for (; sent_seen < b.hal.sent.size(); sent_seen++) {
        const Msg &m = b.hal.sent[sent_seen];
        trace << b.hal.now << " pub " << m.topic << " q" << m.qos << (m.retain ? " r " : " - ") << m.payload << "\n";
      }
      const int out = b.hal.outputs() & 7;  // buzina fora: pisca rápido demais para o traço
      if (out != last_out) {
        last_out = out;
        trace << b.hal.now << " out " << out << "\n";
      }
    }
  };
  std::string line;
  while (std::getline(script, line)) {
    if (line.empty() || line[0] == '#') continue;
    std::istringstream in(line);
    uint32_t t;
    std::string cmd, a, rest;
    in >> t >> cmd;
    advance(t);
    if (cmd == "end") break;
    in >> a;
    std::getline(in, rest);
    if (!rest.empty() && rest[0] == ' ') rest.erase(0, 1);
    if (cmd == "link") b.hal.link = a == "1";
    else if (cmd == "temp") {
      b.hal.temp_valid = a != "nan";
      if (b.hal.temp_valid) b.hal.temp = std::stof(a);
    } else if (cmd == "scan") b.hal.scans.push_back(a);
    else if (cmd == "btn") {
      const int i = a == "start" ? 0 : a == "fail" ? 1 : 2;
      b.hal.btn[i] = rest == "1";
    } else if (cmd == "rx") b.rx(a.c_str(), rest.c_str());
  }
  std::ofstream("test/golden/turno.native.out") << trace.str();
  std::ifstream golden("test/golden/turno.trace");
  std::stringstream want;
  want << golden.rdbuf();
  TEST_ASSERT_TRUE_MESSAGE(golden.good() || !want.str().empty(), "falta test/golden/turno.trace (tools/golden.py --update)");
  TEST_ASSERT_TRUE_MESSAGE(want.str() == trace.str(), "traço difere: compare turno.native.out com turno.trace");
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_json_le_tipos_e_ignora_aninhado);
  RUN_TEST(test_status_retido_ao_conectar);
  RUN_TEST(test_ciclo_liberado_mede_desde_o_pedido);
  RUN_TEST(test_repique_do_botao_nao_gera_evento);
  RUN_TEST(test_resposta_velha_e_ignorada_e_negada_bloqueia);
  RUN_TEST(test_sem_resposta_segue_degradado_ou_bloqueia);
  RUN_TEST(test_rede_fora_guarda_eventos_e_envia_com_idade);
  RUN_TEST(test_publicacao_recusada_e_repetida_sem_perder_ordem);
  RUN_TEST(test_fila_cheia_descarta_o_mais_antigo);
  RUN_TEST(test_chamado_impede_inicio_e_pisca_vermelho);
  RUN_TEST(test_takt_estourado_acende_amarelo_e_identificador_e_saneado);
  RUN_TEST(test_resultado_da_inspecao_automatica_encerra_o_ciclo);
  RUN_TEST(test_roteiro_de_referencia);
  return UNITY_END();
}
