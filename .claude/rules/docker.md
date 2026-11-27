---
paths:
  - "Dockerfile"
  - "docker-compose.yml"
  - ".dockerignore"
  - "infra/**"
---

# Docker

- Um `docker-compose.yml`, projeto `sfal`: `broker`, `backend`, `simulator` e, no perfil `ia`, `ollama`.
- Uma imagem para servidor e simulador; o comando escolhe o papel. A imagem compila a biblioteca do firmware
  (`firmware/sim/build.sh`): mexeu no núcleo, reconstrua (`docker compose up -d --build`).
- `config/` é montado só leitura: mudar `line.yaml` pede só `docker compose restart backend simulator`.
- **Ollama roda em contêiner** (decisão do usuário, 2026-11-26), com a porta publicada só em `127.0.0.1`. Não instale
  no host.
- Dados em volume nomeado (`dados`, `ollama`). `docker compose down -v` apaga os dois: pergunte antes.
- Segredos por variável de ambiente ou arquivo montado, nunca por `COPY`.
- Cada serviço nosso tem `healthcheck`; quem depende espera `service_healthy`.
- **WSL2 + Docker Desktop:** não reinicie o Docker Desktop sem perguntar e não toque em contêineres de outros
  projetos (`rebac-*`). Não instale nada no host sem pedir.
