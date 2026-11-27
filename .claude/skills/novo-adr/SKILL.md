---
name: novo-adr
description: Registra uma decisão de arquitetura do Smart Factory Assembly Line em docs/adr/ (próximo número com 4 dígitos, modelo do projeto, índice atualizado, ADR substituído marcado, decisão propagada para a documentação e as regras). Use quando uma decisão técnica for tomada ou revista — biblioteca, protocolo, formato de dados, porta, hardware, modelo de IA, estrutura do servidor — mesmo que o usuário não diga "ADR". Também para confirmar (Proposto → Aceito) ou recusar um ADR existente.
---

# Novo ADR

Pasta: `docs/adr/`.

1. **Número:** liste a pasta e use o próximo livre com 4 dígitos (`0004-titulo-em-kebab-case.md`). Números nunca são reaproveitados.

2. **Arquivo** em pt-BR, seguindo o modelo de `docs/adr/README.md`:
   - **Estado:** `Aceito` se o usuário decidiu; `Proposto` se é sugestão do assistente ou está em discussão.
   - **Data:** hoje (AAAA-MM-DD).
   - **Contexto, Decisão, Consequências (boas e ruins), Alternativas consideradas** — curtos e concretos. Se veio de medição ou teste, cite o número e como foi obtido.
   - Diga o que a decisão **não** cobre (por exemplo, o que continua sem teste em hardware).

3. **Substituição:** não reescreva o ADR antigo. Troque só o estado dele para `Substituído por NNNN` e cite o antigo no novo.
   **Confirmação:** para promover `Proposto → Aceito`, edite só a linha de estado.

4. **Índice:** acrescente ou atualize a linha na tabela de `docs/adr/README.md`.

5. **Propague:**
   - `docs/PROTOCOL.md` se mudar mensagem;
   - `docs/ARCHITECTURE.md` se mudar estrutura, fluxo, porta ou dados;
   - `docs/HARDWARE.md` se mudar placa, pino ou sensor;
   - `.claude/rules/` e `CLAUDE.md` se a decisão virar regra de código (cite o ADR na regra);
   - `README.md` se mudar como rodar ou uma limitação.
