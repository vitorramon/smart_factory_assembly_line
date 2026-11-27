# Asset Administration Shell (AAS)

Dois servidores AAS, com papéis diferentes, alimentados pelo que o servidor da linha já sabe (ADR-0004):

| | Produtos | Estações (provedores) |
|---|---|---|
| Servidor | Eclipse BaSyx (AAS Environment) | FA³ST Service 1.3.0 |
| Acesso | HTTP (API do AAS, Parte 2) | OPC UA (e HTTP, só leitura) |
| Endereço | `http://localhost:8081` · catálogo em `http://localhost:3000` | `opc.tcp://localhost:4840` · `http://localhost:8443/api/v3.0` |
| O que tem | O produto (tipo) e um shell por unidade, **desde o planejamento** | Um shell por estação e um da linha |
| Para quê | Catálogo e acompanhamento da fabricação de cada unidade | Máquina de estados, indicadores e capacidade dos equipamentos |
| Quem escreve | O servidor da linha, por HTTP (`software/sfal/aas/sync.py`) | O próprio FA³ST, assinando o gêmeo publicado em MQTT |

É a proposta do M1: o produto é o **requisitante** (ordena as etapas e pede uma capacidade em cada uma) e as estações
são os **provedores** dessas capacidades.

Sobe junto com a linha (`./start.sh simulation` ou `prod`); `--sem-aas` deixa de fora. Verificado em 2026-11-26 com
tudo simulado; nenhum cliente além dos testes abaixo foi usado (UaExpert, por exemplo, não).

## Produtos no BaSyx

**Produto (tipo)** `urn:sfal:aas:product:SFAL-X1`, definido em `product` no `config/line.yaml`:

- `Identificacao`: código, nome, descrição, fabricante, takt.
- `ProcessoDeFabricacao`: lista `Etapas` na ordem da rota; cada etapa tem `Capacidade`, `Estacao`, `Provedor` (o id do
  AAS da estação no FA³ST), `CicloIdealS` e `AoReprovar`.

**Unidade (instância)** `urn:sfal:aas:unit:U-000042`, derivada do produto, com o submodelo `Fabricacao`:

| Elemento | Conteúdo |
|---|---|
| `Status` | `planejada`, `em_producao`, `retrabalho`, `pronta`, `refugada` ou `retirada` |
| `Pedido`, `NumeroDeSerie`, `Produto` | de onde veio |
| `EstacaoAtual`, `ProximaEstacao` | onde está em processo, ou qual estação aguarda |
| `PlanejadaEm`, `IniciadaEm`, `ConcluidaEm`, `LeadTimeS`, `Reprovacoes` | tempos e qualidade |
| `Passos` | uma entrada por passagem em estação: capacidade, tentativa, início, fim, duração, resultado, temperatura |
| `Inspecoes` | cada inspeção óptica por IA: veredito, defeito, modelo, posição e o endereço da foto |

**Pedidos.** Uma unidade passa a existir quando é planejada, antes de ser fabricada: o pedido reserva os números de
série e os shells aparecem no BaSyx com `Status = planejada`. A primeira estação inicia sempre a planejada mais
antiga. Com `orders.auto: true` (padrão), o servidor planeja um lote novo quando as planejadas estão acabando; com
`false`, os pedidos são criados na aba "Linha conectada" ou por `POST /api/orders {"quantity": 20}`, e sem pedido a
unidade nasce na primeira estação, como antes.

```bash
curl -s localhost:8081/shells                                   # todos os shells
ID=$(printf 'urn:sfal:sm:unit:U-000042:fabricacao' | base64 -w0 | tr '+/' '-_' | tr -d '=')
curl -s "localhost:8081/submodels/$ID/\$value"                   # situação de fabricação da unidade, só os valores
```

O BaSyx roda com armazenamento em memória. Quando ele reinicia, o servidor da linha reenvia o produto, as unidades
abertas e as 150 últimas encerradas; unidades mais antigas ficam só no banco da linha.

## Estações no FA³ST (OPC UA)

Um shell por estação (`urn:sfal:aas:station:<id>`, nome `Estacao_<id>`) com três submodelos:

| Submodelo | Propriedades |
|---|---|
| `Estado_<id>` | `Estado` (IDLE, WAIT, RUNNING, BLOCKED, OFFLINE), `Online`, `Unidade`, `CicloMs`, `Chamado`, `Retida`, `MotivoBloqueio`, `TorreLuminosa`, `Fila`, `Temperatura` |
| `Indicadores_<id>` | `OEE`, `FPY`, `Disponibilidade`, `Desempenho`, `Qualidade`, `Ciclos`, `Reprovacoes`, `CicloMedioS`, `ParadaS` |
| `Capacidade_<id>` | `Capacidade`, `Nome`, `PosicaoNaRota`, `CicloIdealS`, `TemLeitor`, `PostoManual`, `AoReprovar`, `InspecaoPorIA` |

E o shell `Linha`, com `Indicadores_linha` (FPY, RTY, OEE, COPQ, planejadas, em processo, prontas, refugo, lead time,
vazão, gargalo).

**No cliente OPC UA**, navegue por nome, não por NodeId (os NodeIds do FA³ST são numéricos e mudam a cada partida):

```
Objects → AASEnvironment → Estado_asm → Estado → Value
```

Assinaturas (monitored items) funcionam: a mudança chega sem consulta periódica.

```python
# uv run --no-project --with asyncua python exemplo.py
import asyncio
from asyncua import Client

async def main():
    async with Client("opc.tcp://localhost:4840") as c:
        async def filho(no, nome):
            for k in await no.get_children():
                if (await k.read_browse_name()).Name == nome:
                    return k
        env = await filho(c.nodes.objects, "AASEnvironment")
        valor = await filho(await filho(await filho(env, "Estado_asm"), "Estado"), "Value")
        print(await valor.read_value())          # RUNNING

asyncio.run(main())
```

**Como os valores chegam.** O servidor da linha publica o gêmeo de cada estação em MQTT, separado por ritmo de
mudança, e o FA³ST assina esses tópicos (`software/sfal/aas/twin.py` é a fonte única dos campos):

| Tópico | Conteúdo | Ritmo |
|---|---|---|
| `sfal/twin/v1/station/<id>/estado` | máquina de estados, unidade, chamado, retenção, fila | quando muda |
| `sfal/twin/v1/station/<id>/processo` | tempo de ciclo decorrido, temperatura | no máximo a cada 5 s |
| `sfal/twin/v1/station/<id>/indicadores` | OEE, FPY, ciclos… | no máximo a cada 10 s |
| `sfal/twin/v1/line/indicadores` | indicadores da linha | no máximo a cada 10 s |

Medido em 2026-11-26: estado e unidade lidos pelo OPC UA iguais aos do servidor em 183 de 200 leituras feitas 1,2 s
depois (as demais caíram em cima de uma transição).

O modelo AAS e a configuração do FA³ST são gerados de `config/line.yaml` a cada subida (`sfal aas-config`): estação
nova no arquivo aparece no OPC UA sem outra mudança.

### O jar do FA³ST

`tools/starter-1.3.0.jar` não é versionado (82 MB). Baixe da página de versões do projeto
(https://github.com/FraunhoferIOSB/FAAAST-Service/releases) e coloque nesse caminho. Sem o jar, o `start.sh` sobe o
resto e avisa que não há OPC UA.

## Três armadilhas do FA³ST encontradas no caminho

Ficam registradas porque custaram tempo e não estão na documentação dele:

1. **Não chamar o contêiner de `localhost`.** Com esse nome de host o servidor OPC UA não sobe ("OPC UA server could
   not be started"). O contêiner se chama `sfal-opcua` (`SFAL_OPCUA_HOST`).
2. **Não publicar o gêmeo com retenção, nem com `clientId` fixo.** Mensagens retidas chegando todas juntas na
   assinatura derrubavam a conexão MQTT do FA³ST e algumas assinaturas não eram refeitas. O gêmeo é publicado sem
   retenção e repetido a cada 15 s.
3. **Não mandar tudo a cada segundo.** O FA³ST reprocessa todas as propriedades de um tópico a cada mensagem; com um
   tópico por estação atualizado a cada segundo (mais de 100 atualizações por segundo) ele ficava minutos atrás da
   linha. Daí os três grupos acima.

## Limitações

- **OPC UA sem segurança.** Política `NONE` e acesso anônimo → qualquer um na rede lê o estado das estações → use só
  em rede isolada, ou configure usuários e certificados em `software/sfal/aas/faaast.py` (opções
  `supportedSecurityPolicies`, `supportedAuthentications`, `userMap`).
- **Nome anunciado pelo servidor OPC UA.** O endpoint se anuncia como `opc.tcp://sfal-opcua:4840` → clientes que
  usam o endereço anunciado (o UaExpert pergunta se deve trocar) não resolvem esse nome → aceite a troca pelo
  endereço digitado, ou ponha `sfal-opcua` no arquivo de hosts do cliente.
- **Só leitura.** Nada escrito no OPC UA ou no BaSyx volta para a linha → não dá para comandar uma estação por AAS →
  se for preciso, o caminho é um provedor de operação no FA³ST chamando a API do servidor.
- **Submodelos próprios.** Não usam os modelos padronizados da IDTA nem `semanticId` → outro sistema não os
  interpreta sozinho → mapear para os templates (Digital Nameplate, Technical Data, capacidades) quando houver com
  quem interoperar.
- **`CicloMs` e `Temperatura` têm resolução de 5 s** no OPC UA; para o tempo exato do ciclo use o evento da estação
  ou a rastreabilidade.
