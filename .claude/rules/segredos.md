# Segredos

- Fora do Git: `.env`, `firmware/include/secrets.h` (Wi-Fi e broker), tokens.
- Versione o modelo: `.env.example` e `secrets.h.example`, com um comentário por variável. Variável nova entra no
  modelo e na documentação.
- Não leia `.env` nem `secrets.h`. Para saber o que existe, consulte o `.example`.
- Logs e diário registram IDs, contagens e tempos; nunca credenciais.
- Nenhum dado pessoal de operador: identificação por código (`OP1`), não por nome.
- O assistente de IA é local. Não envie dados da linha a serviço externo sem pedido explícito.
- Testes automáticos não dependem de rede externa, de broker nem do Ollama.
