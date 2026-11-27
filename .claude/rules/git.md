# Git

- `smart_factory_assembly_line/` é o repositório do projeto (local, sem remoto até o usuário configurar um). Branches: `main` (versões estáveis, com tag) e `dev` (trabalho do dia a dia). Trabalhe em `dev`; `main` só recebe o que foi verificado. Versões por tag semântica sem prefixo (`1.0.0`).
- A pasta-mãe `lean-manufacture/` não é repositório. `../Documentation/Atividade/MOD 3`,
  `../Documentation/Atividade/MOD 2/GemeoDigitalCelulares` e `../Base/Virtual-Factory` são repositórios de outros
  trabalhos: não edite nem faça commit neles.

## Commits

- Mensagens em pt-BR, Conventional Commits (`feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `build`), escopo
  opcional = parte do sistema (`feat(firmware): …`, `fix(engine): …`, `docs(adr): …`).
- **Sem `Co-Authored-By` nem qualquer outra atribuição ao assistente**, em commits e em descrições de pull request.
  Decisão do usuário (2026-11-15).
- Um commit por mudança coerente, só com os arquivos dela. Confira `git status` antes; nada de `git add .` às cegas.
- Nunca versionar: `.env`, `firmware/include/secrets.h`, `.venv/`, `.pio/`, `firmware/sim/build/`, `data/`.

## Remoto

- `push` e `tag` só com pedido explícito.
