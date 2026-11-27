# 0004 — AAS de volta, como adaptadores: produtos no BaSyx, estações no FA³ST (OPC UA)

- **Estado:** Aceito
- **Data:** 2026-11-26

## Contexto

O ADR-0002 tirou OPC UA e AAS do caminho do dado e previu que voltariam, se preciso, como adaptadores. O usuário
pediu a volta com papéis definidos: os produtos num catálogo acessível por HTTP no BaSyx, existindo antes de serem
fabricados e mostrando a situação de fabricação; os equipamentos (provedores) acessíveis por OPC UA pelo FA³ST
Service, mostrando a máquina de estados. É a arquitetura requisitante/provedor proposta no M1.

## Decisão

- **Estações no FA³ST 1.3.0**, um shell por estação. O servidor da linha publica o gêmeo em MQTT
  (`sfal/twin/v1/...`) e o FA³ST o espelha por conexões de ativo MQTT; clientes leem e assinam por OPC UA.
  Modelo e configuração são gerados de `config/line.yaml`.
- **Produtos no BaSyx (AAS Environment em Java, memória)**: um shell do produto e um por unidade, gravados por um
  sincronizador do servidor. O motor só anota quais unidades mudaram.
- **Pedidos**: a unidade nasce planejada, com número de série, antes de ser fabricada; a primeira estação inicia a
  planejada mais antiga.
- O motor não conhece AAS. Com os dois servidores desligados a linha funciona igual.

## Consequências

- Atende à proposta do M1 sem pôr AAS no caminho crítico: a liberação de unidades continua em milissegundos pelo
  MQTT das estações.
- Três serviços a mais (dois em Java) e cerca de 1 GB de memória; por isso ficam num perfil que pode ser desligado.
- O jar do FA³ST (82 MB) fica fora do repositório.
- O gêmeo em MQTT precisou ser separado por ritmo de mudança, sem retenção, para o FA³ST acompanhar (docs/AAS.md).
- Só leitura, sem segurança no OPC UA e com submodelos próprios, não os da IDTA: limitações declaradas em docs/AAS.md.
- Mudou o significado de `created_ts` em unidade planejada (passa a ser o início da produção só quando ela começa) e
  o indicador "iniciadas" deixou de contar planejadas.

## Alternativas consideradas

- FA³ST também para os produtos: um servidor só, mas o usuário pediu BaSyx para o catálogo, e a interface web do
  BaSyx já serve de catálogo.
- Servidor OPC UA próprio (asyncua) em vez do FA³ST: menos peças, mas sem AAS nos equipamentos.
- O FA³ST lendo a API do servidor por HTTP em vez de MQTT: consulta periódica de 106 propriedades; o MQTT entrega só
  o que muda.
- BaSyx em Go com PostgreSQL (como no Virtual-Factory): persistente, porém quatro serviços a mais.
