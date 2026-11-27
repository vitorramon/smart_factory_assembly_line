// Leitor mínimo de JSON para os comandos recebidos (objetos de um nível).
// Sem alocação dinâmica; chaves aninhadas são ignoradas.
#pragma once

#include <stddef.h>

namespace sfal {

// Cada função devolve true se a chave existe no primeiro nível e tem o tipo pedido.
bool jsonGetString(const char *json, const char *key, char *out, size_t out_len);
bool jsonGetInt(const char *json, const char *key, long &out);
bool jsonGetBool(const char *json, const char *key, bool &out);

}  // namespace sfal
