# Lote F1 — linha e contorno

> Sexto lote da sessão de 2026-11-25 ([FUNDAMENTOS_E_FERRAMENTAS.md](FUNDAMENTOS_E_FERRAMENTAS.md)
> §4 e §5). Proposta seguida sem consulta; decisões e dúvidas também no
> [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md). Código:
> `assetflow/generation/engines/desenhista/linha.py` (os comandos) e
> `assetflow/referencias/linha.py` (as medidas do olho).

## 1. O que entrou

**Comandos da receita** (grupo `linha`):

| Comando | Onde | O que faz |
|---|---|---|
| `{"reta": [x0, y0, x1, y1], "cor": "k"}` | op | degraus do mesmo tamanho (1 por 1, 2 por 1, 3 por 1); se os degraus iguais não chegam ao ponto final, o fim é ajustado e o aviso diz onde a reta terminou |
| `{"curva": [x0, y0, x1, y1, x2, y2, …], "cor": "k"}` | op | 3 a 8 pontos, por onde a curva passa (Catmull-Rom), 8-conectada e sem canto em L; degraus fora de progressão viram aviso com a posição |
| `{"limpar_linha": "k"}` ou `true` | op | sobre o que a camada já pintou: tira as dobras (2×2), depois os cantos em L, e relata o que tirou e o que sobrou, com posições. O pixel tirado volta a ser o que estava embaixo |
| `"contorno": {"tipo": "inteiro"\|"seletivo"\|"colorido", "cor": "k", "cor_luz"?: "c"}` | raiz | contorna a silhueta de todas as camadas, por último (camada `contorno_auto`): inteiro numa cor; seletivo com `cor_luz` na borda virada para a luz da receita; colorido com o tom mais escuro da rampa de cada pixel (`cor` fora de rampa) |

A `linha` de sempre continua: a reta de degraus perfeitos nem sempre emenda
com a seguinte (§4, "um cuidado com a reta").

**Regras da limpeza.** Canto em L é o pixel do meio de um degrau que encosta
nos dois lados (um vizinho na horizontal, um na vertical, sem o diagonal entre
eles) e cuja saída não separa os vizinhos. Fica o **canto proposital** — os dois
braços retos por 2 pixels ou mais, como o canto de uma caixa. Dobra é um bloco
2×2 da mesma cor; uma cor com miolo (algum pixel com os quatro vizinhos dela)
não perde dobras, porque ali o 2×2 é a mancha. A ordem — dobras, depois
cantos, depois medir de novo — é a do §4 ("um cuidado com a limpeza
automática").

**Medidas do olho do app** (`referencias/linha.py`), sobre a máscara da cor do
contorno quando ele é "escuro único": cantos em L, dobras e degraus fora de
progressão (o trecho menor ou maior que os dois vizinhos numa escada de um
sentido só: 5, 2, 1, 2 tem um; 5, 2, 2, 1, 1 não), por 100 px de contorno.
Acima do limite do tipo, o olho dá os desvios `CANTOS`, `DOBRAS` e `DEGRAUS`,
com posições. Como todo o olho, **só informa**.

**Calibração pelas referências** (`scripts/calibrar_linha.py`, só imprime):
p90 dos quadros com contorno "escuro único" dos pacotes ativos, peso igual por
pacote, em 2026-11-26:

| Tipo | Quadros / pacotes | Cantos p50 / p90 | Dobras p50 / p90 | Degraus p50 / p90 |
|---|---|---|---|---|
| character | 3.320 / 7 | 2,2 / 6,3 | 0 / 3,5 | 2,4 / 5,6 |
| prop | 248 / 5 | 0 / 5,9 | 0 / 0,4 | 0 / 5,3 |
| tile | 411 / 5 | 0 / 2,4 | 0 / 1,4 | 0 / 4,8 |

Os limites em `referencias.yaml` (`olho.linha`) são os p90, `a_calibrar`.

**Na ficha (F5).** `CANTOS`, `DOBRAS` e `DEGRAUS` entram em
`MEDIDAS_CONHECIDAS`, e a pergunta `limpeza` passa a cruzar com elas e com
`ORFAOS`: "sim" com qualquer uma delas acusada é divergência.

## 2. Interruptor

`comandos_linha` nas opções da gaveta (padrão `true`). Desligado, a receita
com `reta`, `curva`, `limpar_linha` ou `contorno` é recusada dizendo isso, e o
formato do MCP não cita o grupo (~330 caracteres, ~110 tokens, a menos). As
medidas do olho não têm interruptor próprio: sem `olho.linha` no YAML, não há
comparação.

## 3. Decisões tomadas sem consulta

1. **A reta ajusta o fim, não o degrau**: degraus iguais é a regra do
   comando; quem precisa do ponto exato usa `linha`.
2. **A curva passa pelos pontos** (Catmull-Rom), em vez de usá-los como
   controle: é o que o Claude descreve ao olhar ("passa por aqui").
3. **O ápice de uma curva não é calombo**: a progressão vale num trecho de
   inclinação de um sinal só, e a sequência recomeça onde ele troca.
4. **O contorno é a borda de dentro** (o pixel pintado com um vizinho
   transparente), e não um pixel a mais por fora: não cresce o sprite nem sai
   da grade. Ele repinta também traços finos que estejam na borda.
5. **Limites por tipo**, porque props quase não têm dobra (p90 0,4) e
   personagens têm (3,5).
6. **A limpeza da gaveta e a medida do olho são dois códigos** com a mesma
   regra: o teste de fronteiras não deixa um importar o outro, e
   `tests/test_linha.py` confere que, depois da limpeza, o olho mede zero.

**Correção do lote F5, achada aqui.** As três perguntas `limpeza` do
`olhar.yaml` eram feitas no negativo ("há pixel solto…?"), e a ficha lê "sim"
como passou: o "sim" de um desenho sujo contaria como limpo. Elas foram
reescritas no positivo ("o contorno está limpo — sem pixel solto…?"), e o
cabeçalho do `olhar.yaml` diz a regra: "sim" é sempre o desenho certo.

## 4. Dúvidas para a autora

1. **Os pacotes profissionais têm canto em L**: mediana de 2,2 por 100 px nos
   personagens. A regra "sem canto em L" do §4 não é absoluta; o olho só acusa
   acima do p90. A poção de exemplo da gaveta (`exemplos/pocao_16x16.json`)
   tem 4 no ombro do frasco e passa a receber o desvio.
2. **Contorno seletivo e colorido** não foram medidos contra as referências
   (o medidor classifica o tipo, mas não diz de que lado fica a cor clara).
3. **O degrau 2, 1, 2, 1** (inclinação 2:3) conta como irregular, como o §4
   pede; ele é comum em sprites e pode acusar demais. Está dentro do p90.
