#include "json_mini.h"

#include <stdlib.h>
#include <string.h>

namespace sfal {
namespace {

const char *skipWs(const char *p) {
  while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
  return p;
}

// p aponta para a aspa de abertura; devolve o caractere após a aspa de fechamento (ou nullptr).
const char *skipString(const char *p) {
  p++;
  while (*p && *p != '"') {
    if (*p == '\\' && p[1]) p++;
    p++;
  }
  return *p == '"' ? p + 1 : nullptr;
}

// Pula um valor qualquer (string, número, literal, objeto ou vetor).
const char *skipValue(const char *p) {
  p = skipWs(p);
  if (*p == '"') return skipString(p);
  if (*p == '{' || *p == '[') {
    int depth = 0;
    while (*p) {
      if (*p == '"') {
        p = skipString(p);
        if (!p) return nullptr;
        continue;
      }
      if (*p == '{' || *p == '[') depth++;
      if (*p == '}' || *p == ']') {
        depth--;
        if (depth == 0) return p + 1;
      }
      p++;
    }
    return nullptr;
  }
  while (*p && *p != ',' && *p != '}' && *p != ']') p++;
  return p;
}

// Devolve o início do valor da chave no primeiro nível, ou nullptr.
const char *findValue(const char *json, const char *key) {
  if (!json || !key) return nullptr;
  const char *p = skipWs(json);
  if (*p != '{') return nullptr;
  p++;
  const size_t key_len = strlen(key);
  for (;;) {
    p = skipWs(p);
    if (*p != '"') return nullptr;  // '}' ou JSON malformado
    const char *k = p + 1;
    const char *end = skipString(p);
    if (!end) return nullptr;
    const size_t len = (size_t)(end - 1 - k);
    p = skipWs(end);
    if (*p != ':') return nullptr;
    p = skipWs(p + 1);
    if (len == key_len && strncmp(k, key, key_len) == 0) return p;
    p = skipValue(p);
    if (!p) return nullptr;
    p = skipWs(p);
    if (*p != ',') return nullptr;
    p++;
  }
}

}  // namespace

bool jsonGetString(const char *json, const char *key, char *out, size_t out_len) {
  const char *p = findValue(json, key);
  if (!p || *p != '"' || out_len == 0) return false;
  p++;
  size_t n = 0;
  while (*p && *p != '"') {
    char c = *p;
    if (c == '\\') {
      p++;
      switch (*p) {
        case 'n': c = '\n'; break;
        case 't': c = '\t'; break;
        case 'r': c = '\r'; break;
        case 'u':  // \uXXXX: não há texto não-ASCII nos comandos; vira '?'
          c = '?';
          for (int i = 0; i < 4 && p[1]; i++) p++;
          break;
        case '\0': return false;
        default: c = *p; break;
      }
    }
    if (n + 1 < out_len) out[n++] = c;
    p++;
  }
  if (*p != '"') return false;
  out[n] = '\0';
  return true;
}

bool jsonGetInt(const char *json, const char *key, long &out) {
  const char *p = findValue(json, key);
  if (!p) return false;
  if (!(*p == '-' || (*p >= '0' && *p <= '9'))) return false;
  char *end = nullptr;
  const double v = strtod(p, &end);
  if (end == p) return false;
  out = (long)v;
  return true;
}

bool jsonGetBool(const char *json, const char *key, bool &out) {
  const char *p = findValue(json, key);
  if (!p) return false;
  if (strncmp(p, "true", 4) == 0) {
    out = true;
    return true;
  }
  if (strncmp(p, "false", 5) == 0) {
    out = false;
    return true;
  }
  return false;
}

}  // namespace sfal
