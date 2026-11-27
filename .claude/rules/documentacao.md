# Documentação

Cada documento tem um papel; não crie outros sem pedido.

| Arquivo | Para quê | Quando atualizar |
| --- | --- | --- |
| `README.md` | O que é, como rodar, limitações | Ao mudar como rodar, o que o sistema faz ou uma limitação |
| `docs/ARCHITECTURE.md` | Desenho, serviços, dados, "onde mexer" | Ao mudar estrutura, fluxo ou porta |
| `docs/PROTOCOL.md` | Contrato MQTT | Ao mudar qualquer mensagem |
| `docs/HARDWARE.md` | Materiais, ligações, gravação, bancada | Ao mudar pino, sensor ou procedimento |
| `docs/adr/` | Decisões | A cada decisão (skill `novo-adr`) |
| `config/line.yaml` | A fábrica; os comentários são a documentação dos campos | Ao criar campo novo |

- **Verificado antes de afirmado.** Diga o que rodou e o que viu. "Compila", "passa no simulador" e "testado na placa"
  são três coisas diferentes; use a que é verdade.
- **Simulação é declarada como simulação.** Todo número do "E se?" vem acompanhado de "simulado" e da semente.
- **Limitações** no formato limitação → efeito → o que fazer, específicas.
- Não documente comando que não foi executado com sucesso. Saída colada no README leva a data.
- Nunca reescreva um ADR aceito: crie outro que o substitua.
- Sem documentos de plano, progresso ou relatório por conta própria: o estado do projeto é o código, os testes e o Git.
- O `CLAUDE.md` continua curto. Regra nova vai para `.claude/rules/`.
