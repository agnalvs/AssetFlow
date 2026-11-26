# Lote 5 — editor de pixels na tela

> Quinto lote da sessão de 2026-11-25 ([FUNDAMENTOS_E_FERRAMENTAS.md](FUNDAMENTOS_E_FERRAMENTAS.md)
> §6, "as três que mais economizam", e §8: "o editor de pixels na tela vale ser
> adiantado"). Proposta seguida sem consulta; decisões e dúvidas também no
> [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md). Código: `assetflow/editor/`,
> `frontend/src/components/EditorDePixels.tsx`.

## 1. O que entrou

**Na tela.** O resultado de um pedido pronto ganha "Editar pixels". O editor
abre no lugar, com a grade lógica ampliada (fundo xadrez no transparente):

- **lápis** (clicar ou arrastar), **apagar** e **conta-gotas**;
- a **paleta do asset** — as chaves da receita, com as cores; nenhuma cor nova
  entra pelo editor;
- desfazer e refazer (também Ctrl+Z / Ctrl+Y), a contagem de pixels mudados, a
  prévia em tamanho real e em 2×;
- um campo opcional, **"o que estava errado"**;
- "Salvar como remendo" e "Cancelar".

**O que salva.** Uma camada nova no fim da receita da base, `retoque_N` (N
cresce a cada edição, então dá para editar uma edição), com um `px` sobre o
retângulo do que mudou: `.` mantém, `-` apaga, a chave pinta. É o mesmo remendo
do MCP ([MCP.md](MCP.md) §3) com uma camada só: sai um **asset novo**, e a base
fica como era.

**Por onde passa.** O caminho de todo desenho: a receita inteira vai para a
`desenhista-v1` pelo nome, sem fallback, com o spec da base; depois
pós-processamento, Optimizer e validador. O Optimizer não é pulado (é regra da
arquitetura) e pode desfazer um pixel isolado; a resposta diz quantos dos
pixels mudados ficaram no PNG final.

**Onde fica.** Aprovado, o resultado vira um **pedido de ajuste já concluído**
na fila (`tipo: ajuste`, origem no asset editado, olhar "corrigido pela autora
no editor"), e aparece em "Prontos" ao lado do original. Não aprovado, nenhum
pedido é criado: a tela mostra o motivo, e o asset fica avulso.

**A lição.** Com "o que estava errado" preenchido, a edição grava um "não
gostei" com esse motivo no asset **original**. Ele fica pendente, e na próxima
conversa o Claude o converte em lição da autora — o caminho da Fase B2, sem
nada novo.

**API.** `GET /api/pedidos/{id}/editor` (a grade lógica em hexadecimal e a
paleta) e `POST /api/pedidos/{id}/editor` (`{"pixels": [{"x", "y", "cor"}],
"motivo"?}`; `cor` é uma chave da paleta ou `null` para apagar).

## 2. Interruptor

`ASSETFLOW_EDITOR` (`settings.pedidos.editor`, padrão ligado). Desligado, as
duas rotas recusam com a frase "o editor de pixels está desligado nesta
instalação", e a tela a mostra no lugar do editor.

Custo: **zero tokens**. Uma correção pequena feita aqui substitui um remendo do
olhar (~1.000 tokens) ou um pedido de ajuste inteiro (~3.000 a 5.000).

## 3. Decisões tomadas sem consulta

1. **Só pedido pronto** (`concluido`) abre o editor: em revisão, o Claude
   ainda pode remendar o mesmo desenho, e as duas edições disputariam a vez.
2. **Uma camada nova, nunca a troca de uma existente**: a edição fica visível
   na receita (`retoque_1`, `retoque_2`), e remover a camada desfaz a edição.
3. **Um `px` sobre o retângulo do que mudou**, e não um por pixel: a receita
   cresce no máximo a área do retângulo.
4. **Pedido de ajuste já concluído**, gravado numa instrução só
   (`registrar_edicao`, um `INSERT`): é uma criação, não uma transição, e
   nenhum estado intermediário fica visível ao Claude.
5. **A paleta vem da gaveta**: a `desenhista-v1` passa a gravar a paleta
   efetiva (com as chaves de `rampas`) em `engine_metadata.paleta`. Asset de
   antes do lote cai na `paleta` da receita.
6. **"Ficou" compara com tolerância de 8 por canal**, porque o
   pós-processamento pode ajustar a cor em uma unidade.
7. **O motivo vai para o asset original**, trocando uma opinião que houvesse:
   foi nele que algo estava errado.
8. **O editor não importa API, MCP, gaveta nem jobs** (teste de fronteiras); a
   requisição de ajuste é montada pelo `ServicoDePedidos`, no mesmo lugar que a
   do pedido de ajuste da fila.

## 4. Dúvidas para a autora

1. **O Optimizer pode desfazer a sua correção** — um olho de 1 px numa cor rara
   pode ser lido como pixel órfão. A tela avisa quantos ficaram; se acontecer
   muito, a saída seria uma marca "da autora" que o Optimizer respeita, o que
   mexe numa regra da arquitetura e fica para você decidir.
2. **Editar um pedido que falhou** (o último desenho não aprovado) ficou de
   fora: faz sentido para corrigir à mão o que o Claude não acertou em três
   tentativas, mas o pedido não tem "pronto" para mostrar ao lado.
3. **A ficha de verificação** do asset editado sai vazia: as respostas do
   Claude eram do desenho anterior.
