# Plano do app — o desenhista como AssetFlow inteiro

Nov 25, 2026 · @Luiza

## 1. Objetivo

O AssetFlow passa a ter um único gerador, o desenhista, e a tela vira o lugar onde você monta o pedido, vê o que foi criado, pede ajustes e exporta. O uso é pessoal, na sua máquina, com a sua assinatura do Claude.

**O que o app passa a ter**

- Um formulário de pedido com os controles que já existem: tipo, resolução, cores, vista, tipo corporal, detalhe e contorno.
- Um botão "Gerar" que funciona de verdade, por dois caminhos: uma fila que a conversa do Claude atende, e depois o Claude acionado pelo próprio app.
- Uma galeria permanente de tudo o que foi desenhado, com laudo, receita e versões.
- Ajustes por texto sobre um asset existente, que viram remendos.
- Exportação de PNG, de versões ampliadas e de conjuntos.

**O que o app deixa de ter**

- O seletor de motor e o modo "Automático".
- O modo 2D Normal (Studio).
- A ideia de que um mock pode gerar no lugar do desenhista.

**O que não muda**

- O desenho continua vindo de uma receita, validada pelo Pixel Exact e pelo Optimizer.
- O `FinalResolvedSpec`, a base de conhecimento e as referências seguem como estão.
- O servidor MCP e as quatro ferramentas atuais continuam, e ganham mais duas para a fila.
- As fases 4 a 7 do plano anterior (acabamento, validações de estilo, animação, tiles) e a fase de estilos continuam valendo. Elas passam a aparecer na tela nova.

## 2. O que os termos de uso permitem

Pelo que a documentação diz hoje, o seu app acionar o Claude Code na sua máquina, com o seu login, é um uso previsto e conta dentro dos limites da assinatura. O que não é permitido é oferecer isso a outras pessoas. Não sou advogado; os links estão abaixo para você conferir.

| O que conferi | O que a fonte diz | Fonte |
| --- | --- | --- |
| Rodar o Claude Code sem interação | Existe um modo oficial para scripts, com `claude -p`, que aceita saída estruturada e lista de ferramentas autorizadas | [Run Claude Code programmatically](https://code.claude.com/docs/en/headless) |
| De onde sai o consumo | Com o login do plano, o `claude -p` e o Agent SDK continuam descontando dos limites da assinatura. A página registra que uma mudança anunciada foi pausada em junho de 2026 | [Use the Claude Agent SDK with your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan) |
| Oferecer a terceiros | A Anthropic não permite que desenvolvedores ofereçam login do claude.ai em seus aplicativos nem encaminhem pedidos pelas credenciais de plano em nome dos usuários | [Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance) |
| Chave de API no ambiente | Se a variável `ANTHROPIC_API_KEY` existir, o modo `-p` usa a chave em vez da assinatura | [Environment variables](https://code.claude.com/docs/en/env-vars) |

### O que isso significa para o plano

- **Uso pessoal: viável.** O backend pode chamar `claude -p` na sua máquina.
- **Distribuir o app: não, neste formato.** Se um dia você quiser que outras pessoas usem, cada uma precisaria do próprio Claude Code e do próprio login, ou o app passaria a usar a API paga.
- **A regra pode mudar.** A página de suporte mostra que isso já esteve para mudar uma vez. Por isso a fila de pedidos entra primeiro e continua existindo: ela depende só da conversa normal do Claude.
- **Cuidado com chave de API.** O app deve garantir que `ANTHROPIC_API_KEY` não esteja definida ao chamar o Claude, para não gerar cobrança por fora da assinatura.
- **Limites de uso.** Cada desenho consome da mesma cota que as suas conversas. O app precisa mostrar quando o limite for atingido, em vez de falhar sem explicação.

As páginas foram consultadas pelos trechos devolvidos na busca em 25 de novembro de 2026, não lidas por inteiro. Antes da fase do Claude embutido, vale abrir as quatro e reler.

## 3. A tela nova

A tela terá quatro áreas: pedido, galeria, detalhe do asset e conversa. Três delas reaproveitam componentes que já existem no frontend.

### Pedido

- **Descrição em texto**, como hoje (`PromptInput`).
- **Controles** de tipo, resolução, cores, vista, tipo corporal, detalhe e contorno, como hoje (`AssetControls`). Um controle em "Automático" continua não enviando nada, e o app deduz.
- **Novos**: perfil de quadro (32, 48, 64), estilo (quando a fase de estilos existir) e quantidade de variações.
- **"O que o AssetFlow entendeu"**, como hoje (`PromptInspector`): o spec com a origem de cada valor, e agora também o recorte de conhecimento e a linha de referências que o Claude vai receber.
- **Botão "Gerar"**: cria um pedido na fila.

### Galeria

Hoje o histórico da tela vive só na memória e some ao recarregar a página. O backend, porém, já guarda tudo e já tem a rota `/api/assets/history`. A galeria passa a ler de lá.

- Todos os assets, incluindo os feitos pela conversa (projeto `mcp`).
- Miniaturas ampliadas por vizinho mais próximo.
- Filtros por tipo, tamanho, estilo e situação (aprovado ou não).
- Agrupamento por família: um asset e os remendos derivados dele ficam juntos.
- Marcar favorito e descartar.

### Detalhe do asset

- Imagem ampliada, com fundo xadrez para ver a transparência.
- Laudo: situação, nota, problemas com posição, o que o Optimizer fez.
- Receita em camadas, com o nome de cada uma. Ligar e desligar uma camada na visualização é um extra barato e útil.
- Paleta usada.
- Histórico de versões.
- Ações: pedir ajuste, criar variante, promover a molde, exportar.

### Conversa

- Campo de texto ligado ao asset aberto: "deixa a capa mais longa".
- Na primeira etapa, o texto vira um pedido de ajuste na fila.
- Na última etapa, o texto vai direto ao Claude acionado pelo app, e a resposta aparece ali.

### Exportação

| Nível | O que sai | Quando |
| --- | --- | --- |
| Arquivo | PNG no tamanho real | Primeira etapa da galeria |
| Ampliado | PNG em 2×, 4× ou 8×, por vizinho mais próximo | Primeira etapa da galeria |
| Seleção | ZIP com os assets marcados, a receita e o laudo de cada um | Etapa de exportação |
| Paleta | Arquivo de paleta para editores de pixel art | Etapa de exportação |
| Animação | Spritesheet com metadados e GIF de prévia | Com a fase de animação |

### O que sai da tela

- `EngineSelector` e `EngineCredit`: não há mais motor para escolher nem para creditar.
- `GenerationModeSelector` e `ModeCard`: não há mais modo Studio.
- `SessionHistory`: dá lugar à galeria permanente.

## 4. O que sai e o que fica no código

A recomendação é simplificar sem demolir: tirar da frente o que não serve mais, e deixar quieto o núcleo que está testado e não atrapalha. Revisei o branch no commit `7e02362`.

### Sai

| O quê | Onde | Por quê |
| --- | --- | --- |
| Seletor de motor e crédito de motor na tela | `frontend/src/components/EngineSelector.tsx`, `EngineCredit.tsx`, `hooks/useEngineCatalog.ts` | Só há um gerador |
| Modo Studio na tela | `GenerationModeSelector.tsx`, `ModeCard.tsx` | O app é só de pixel art |
| Modo "Automático" de motor | `kernel/auto_policy.py`, `config/engine_policy.yaml` | Não há o que escolher |
| Fallback para mock | Configuração de rotas em `config/capabilities.yaml` | Um mock nunca deve gerar no lugar do desenhista |
| Pipeline e pós-processamento Studio | `pipelines/studio/`, `postprocessing/studio/`, profiles Studio | Dormente desde a fase 0 |
| Montagem de prompt para difusão | `generation/prompting/` | Servia aos motores de imagem; conferir antes se o pipeline Pixel ainda depende dele |

### Fica

| O quê | Por quê |
| --- | --- |
| Contrato de gavetas, registro e descoberta do kernel | O desenhista é uma gaveta e é chamado por ali. Arrancar isso mexeria em centenas de testes sem ganho para você |
| Gavetas de referência (`mock_image`, `mock_pixel_alt`) | A suíte de testes roda sobre elas. Ficam só nos testes, fora do app em uso |
| Jobs, fila e worker | A fila de pedidos nova se apoia neles |
| Spec, taxonomia, Pixel Exact, Optimizer, validador | São o que garante a qualidade |
| Base de conhecimento e referências | Idem |
| Servidor MCP e serviço do desenhista | É o caminho do desenho |
| Storage e histórico | A galeria lê de lá |

### Muda de papel

- **`GenerationService.submit`**: deixa de aceitar seleção de motor vinda da tela. O pedido da tela vira um item da fila, e só o desenho com receita cria o job de geração.
- **Rotas de motores da API**: ficam só para diagnóstico.
- **Ambiente**: com um gerador só, a diferença entre desenvolvimento e produção para os mocks deixa de afetar o uso. Os mocks são registrados apenas nos testes.

### Uma pendência do relatório que entra aqui

A busca de asset por id varre o histórico inteiro a cada chamada. Com a galeria, o histórico vai crescer. Vale trocar o arquivo de linhas por um índice, ou por um banco SQLite local, antes de a galeria ficar pesada.

## 5. Fases de construção

São seis fases, e a partir da segunda o app já é usável do jeito novo. Cada uma termina com testes passando, commit próprio e parada para a sua conferência.

### Fase A: simplificação

- Executar a seção 4: tirar seletor de motor, modo Studio, modo automático e fallback para mock.
- A tela fica com pedido, "O que o AssetFlow entendeu" e o resultado.
- O botão "Gerar" fica desligado, com a explicação de que os pedidos passam a ir para a fila na fase seguinte.
- Nenhuma funcionalidade nova. É só limpeza, como a fase 0 do plano anterior.

### Fase B: fila de pedidos

- **Pedido como registro próprio**: texto, controles, spec resolvido, situação (pendente, em desenho, concluído, falhou, cancelado) e o asset resultante.
- **API**: criar, listar, cancelar e consultar pedidos.
- **Tela**: "Gerar" cria o pedido; uma lista mostra os pendentes e o andamento.
- **MCP, duas ferramentas novas**:
  - `pedidos_pendentes`: devolve os pedidos na fila, cada um já com o que `consultar_pedido` devolveria, para o Claude não gastar uma chamada extra por pedido.
  - `desenhar` ganha o parâmetro `pedido_id`, que liga o asset ao pedido e o marca como concluído.
- **Uso**: você monta os pedidos na tela e diz na conversa "desenhe os pedidos pendentes do AssetFlow".
- Pedidos de ajuste entram na mesma fila, com o id do asset de origem.

**Marco**: montar três pedidos na tela, pedir na conversa, e ver os três resultados aparecerem na tela.

### Fase B2: ver, corrigir e aprender

Acrescentada depois da B, a pedido da autora: o desenho era feito às cegas, e o
laudo dava 96 a 100 para qualquer coisa. Detalhes em [OLHAR.md](OLHAR.md).

- **Ver e corrigir**: o `desenhar` devolve a imagem do olhar (ampliada,
  silhueta, tamanho real) e o laudo pede um olhar com a lista de verificação da
  base; aprovado no validador não é pronto — o pedido conclui com
  `concluir_pedido`, com até 2 remendos do olhar.
- **O olho do app**: o desenho medido contra as referências do mesmo porte;
  só desvios, que só informam.
- **Exemplos reais**: um sprite CC0 convertido para receita no recorte (nunca
  base nem remendo), em rotação entre os pacotes.
- **Aprendizado**: `registrar_licao`, lições no recorte, "gostei" e "não
  gostei" na tela, lista de lições editável.

### Fase C: galeria e detalhe

- Galeria lendo o histórico do backend, com todos os projetos.
- Filtros, favoritos, descarte e agrupamento por família de remendos. Os
  favoritos reaproveitam o "gostei" da Fase B2 (`data/aprendizado/`): um
  sistema só.
- Tela de detalhe com laudo, receita em camadas, paleta e versões.
- Campo "pedir ajuste", que cria um pedido de remendo na fila.
- Download do PNG e das versões ampliadas.
- Troca do histórico em arquivo por um índice ou SQLite.

### Fase D: exportação e moldes

- ZIP de uma seleção, com receita e laudo.
- Exportação da paleta.
- "Promover a molde": salvar um asset aprovado como molde-base de um tipo e tamanho, que é a melhoria da base de conhecimento pelo uso.

### Fase E: o Claude dentro do app

- **Antes de programar**: reler as quatro páginas da seção 2 e confirmar que a regra não mudou.
- **Como**: o backend chama o Claude Code em modo não interativo, com saída em fluxo, conectado ao servidor MCP do AssetFlow.
- **Restrições de segurança**:
  - só as ferramentas do AssetFlow autorizadas; nada de terminal nem de edição de arquivos;
  - pasta de trabalho vazia e própria;
  - teto de voltas por pedido;
  - `ANTHROPIC_API_KEY` removida do ambiente da chamada.
- **Configuração**: o caminho do executável `claude` vem de variável de ambiente, porque é da sua máquina.
- **Tela**: "Gerar" dispara direto; o painel de conversa mostra o andamento, permite cancelar e avisa quando o limite de uso for atingido.
- **Reserva**: se o Claude não puder ser acionado, o pedido fica na fila da fase B.

Os nomes exatos das opções de linha de comando devem ser conferidos na referência da CLI na hora, não escritos de memória.

### Fase F: o que já estava planejado, agora na tela

- **Estilos**: seletor de estilo no pedido, a partir do `PIXEL_STYLES.md`.
- **Acabamento e variantes** (fase 4 do plano anterior): botões de variante no detalhe do asset.
- **Validações de estilo** (fase 5): avisos novos no laudo, e calibração de órfãos e de redundância.
- **Animação** (fase 6): linha do tempo de frames, prévia animada e exportação de spritesheet.
- **Tiles** (fase 7): prévia ladrilhada 3×3.

### Por que nesta ordem

- A e B primeiro, porque entregam o app novo sem depender de nada externo.
- C e D antes de E, porque a galeria e a exportação são úteis com qualquer forma de disparo.
- E por último entre as estruturais, porque é a única que depende de regra de terceiros e é a de mais código.

## 6. Riscos e decisões

### Riscos

| Risco | Como aparece | O que fazer |
| --- | --- | --- |
| A regra de uso da assinatura muda | O Claude embutido para de funcionar ou passa a cobrar | A fila da fase B continua funcionando; a fase E é isolada num módulo próprio |
| Limite de uso da assinatura | Um lote grande de pedidos esgota a cota | Mostrar o aviso na tela; processar a fila aos poucos; variantes sem Claude |
| Simplificação quebra testes distantes | Falhas em testes de motor, catálogo e modo automático | Fase A em commit só dela, com a suíte rodada antes e depois, como na fase 0 |
| Histórico grande | Galeria e remendos ficam lentos | Índice ou SQLite na fase C |
| O Claude acionado pelo app com ferramentas demais | Ele poderia mexer em arquivos do computador | Lista fechada de ferramentas e pasta de trabalho vazia, com teste |
| Tela nova maior que o planejado | A fase C se estende | Entregar a galeria simples primeiro; filtros e famílias depois |

### Decisões que são suas

1. **Apagar ou só esconder o modo Studio.** Apagar deixa o código menor; esconder é mais rápido e sem risco. O plano propõe apagar na fase A, porque ele está parado desde a fase 0.
2. **Apagar ou manter o modo automático de motor.** Mesma lógica. O plano propõe apagar.
3. **Um projeto só ou vários.** Hoje os assets da conversa ficam no projeto `mcp`. Você pode querer separar por jogo (por exemplo, um projeto por jogo, cada um com seu estilo e sua paleta). O plano assume um projeto padrão agora e deixa vários projetos para depois da fase C.
4. **Fazer a fase E.** Só depois de reler os termos. Se preferir não depender disso, o app fica completo com a fila.
5. **Ordem entre a fase F e as demais.** Se os estilos forem mais urgentes para você que a galeria, dá para fazer estilos logo depois da fase B.

### O que eu ainda preciso de você

- O caminho do executável `claude` na sua máquina e em qual terminal ele funciona. Só é necessário para a fase E.
- Qualquer coisa que a tela precise ter e que não esteja na seção 3.

## 7. Instrução pronta para o Claude Code

Exporte este plano em Markdown e salve como `backend/docs/PLANO_APP_DESENHISTA.md`. Depois cole o texto abaixo no Claude Code. Ele cobre só a fase A.

```text
Adicionei backend/docs/PLANO_APP_DESENHISTA.md. Leia esse arquivo, o
CLAUDE.md e o RELATORIO_ESTADO.md antes de qualquer alteração.

O objetivo geral é o desenhista virar o gerador único do app. Vamos uma
fase por vez, com as mesmas regras de sempre: código e commits em
português, um commit por fase no branch desenhista-mcp, pytest e ruff sem
regressão, testes de fronteira sem afrouxar, documentação atualizada, e
parada ao final de cada fase.

Execute SOMENTE a Fase A (simplificação):

1. Rode pytest -q, ruff check . e o typecheck do frontend, e anote.
2. Me mostre a lista exata do que vai apagar e do que vai editar, no
   backend e no frontend, conforme a seção 4 do plano. Para cada item da
   tabela "Sai", diga se confirma que nada do caminho do desenhista
   depende dele. Em especial, confira generation/prompting/ antes de
   propor apagar. ESPERE meu "sim".
3. Diga também onde o plano não bate com o código, como nas outras fases.
4. Depois do "sim": apague e edite só o que estiver na lista. Não toque
   no servidor MCP, na gaveta desenhista, na base de conhecimento, nas
   referências, no Pixel Exact, no Optimizer nem em backend/data/.
5. As gavetas mock continuam existindo para os testes, mas não podem mais
   gerar no app em uso: sem fallback e sem rota de capacidade para elas
   fora dos testes. Mostre como garantiu isso.
6. Na tela, o botão "Gerar" fica desligado, com uma frase explicando que
   os pedidos passam a ir para a fila na próxima fase. O desenho pela
   conversa (MCP) tem de continuar funcionando exatamente como hoje.
7. Rode tudo de novo, atualize a documentação e o RELATORIO_ESTADO.md,
   faça um único commit e o push.
8. Resumo final: o que saiu, testes apagados, reescritos e mantidos, e a
   confirmação de que um desenho pelo MCP continua aprovado.

Não comece a Fase B sem eu pedir.
```

Para as fases seguintes, o pedido é curto: "Execute a Fase B do PLANO\_APP\_DESENHISTA.md. Antes de programar, me mostre o formato do registro de pedido, as rotas novas, a descrição exata das ferramentas MCP novas e o desenho da tela, e espere meu sim."
