# Decisões de arquitetura

Uma decisão por arquivo, `NNNN-titulo.md`. Decisão aceita não é reescrita: cria-se outra que a substitui.

| Nº | Decisão | Estado |
|---|---|---|
| [0001](0001-nucleo-unico-firmware-simulador.md) | O simulador executa o núcleo do firmware em vez de imitá-lo | Aceito |
| [0002](0002-servidor-em-um-processo.md) | Servidor em um processo, motor sem relógio nem rede | Aceito |
| [0003](0003-dispositivo-sem-relogio.md) | O dispositivo envia idade do evento, não data/hora | Aceito |
| [0004](0004-aas-como-adaptadores.md) | AAS como adaptadores: produtos no BaSyx (HTTP), estações no FA³ST (OPC UA) | Aceito |

Modelo:

```markdown
# NNNN — Título

- **Estado:** Proposto | Aceito | Substituído por NNNN
- **Data:** AAAA-MM-DD

## Contexto
## Decisão
## Consequências
## Alternativas consideradas
```
