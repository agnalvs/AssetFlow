# Lote F3 — construção na receita

> Terceiro lote da sessão de 2026-11-25 ([FUNDAMENTOS_E_FERRAMENTAS.md](FUNDAMENTOS_E_FERRAMENTAS.md)
> §2, §5 e §8). Proposta seguida sem consulta; decisões e dúvidas também no
> [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md). Código:
> `assetflow/generation/engines/desenhista/construcao.py`.

## 1. O que entrou

| Comando | Onde | O que faz |
|---|---|---|
| `{"capsula": [x0, y0, x1, y1, (x2, y2)], "espessura": 1–8, "cor": "b", "contorno"?: "k", "vao"?: "<camada>"}` | op | um membro entre dois ou três pontos (cotovelo, joelho), pontas redondas; `contorno` pinta a borda; `vao` deixa 1 px transparente até uma camada anterior, menos junto ao primeiro ponto (onde o membro se prende) |
| `{"copiar": "<camada>", "desloca": [dx, dy], "espelho"?: "x"\|"y"}` | op | duplica o que uma camada anterior pintou, deslocado e espelhado em torno do centro dela |
| `"boneco"` | raiz | as massas de um humanoide em seis camadas `boneco_*` (braço de trás, pernas, tronco, cabeça, braço da frente), antes das camadas da receita |

**Parâmetros do boneco:**

| Campo | Valores | Efeito |
|---|---|---|
| `altura`, `chao`, `centro` | px | o tamanho e onde ele pisa |
| `cabecas` | 1,5 a 8 (padrão 3) | a proporção: altura ÷ cabeça; 2 é mascote, 5 a 8 realista |
| `forma` | `circulo`, `quadrado`, `triangulo` | o tronco (e a cabeça no quadrado): amigável, sólido, ombros largos |
| `acao` + `lado` | `reta`, `curva`, `inclinada`; `direita`, `esquerda` | a linha de ação: a coluna desloca em curva (seno) ou inclinada, até 8% da altura |
| `pose` | `parado`, `andando`, `ataque`, `conjurando` | pés e mãos: passo, base larga com braço estendido, braços erguidos |
| `cores` | `{"pele", "roupa", "contorno"}` | chaves da paleta |

As camadas da receita pintam por cima do boneco: ele é o manequim, e o Claude o
veste. Nomes iguais (`boneco_tronco` na receita) são recusados.

## 2. Interruptor

`comandos_construcao` nas opções da gaveta (padrão `true`). O formato do MCP
cresce duas linhas (~520 caracteres, ~170 tokens) quando ligado.

## 3. Decisões tomadas sem consulta

1. **O boneco vira camadas antes do parse**: as camadas geradas usam os
   comandos de sempre (`capsula`, `elipse`, `ret`, `poligono`), e por isso o
   mesmo leitor confere tudo.
2. **Proporções do boneco** (convenção minha, `a calibrar`): cabeça = altura ÷
   cabeças; tronco = 45% do resto; pernas, o que sobra; perna = 35% da largura
   do tronco; braço, um a menos.
3. **Só humanoide.** Quadrúpede e criatura ficam para as fichas da K3.
4. **`vao` poupa o primeiro ponto**, a raiz do membro, num raio de
   `espessura + 1`.

## 4. Dúvidas

1. O boneco é a ferramenta que mais pode igualar os personagens (plano §9):
   vale medir na banca com e sem ele.
2. As poses são quatro, fixas; mais poses (correndo, agachado, de costas)
   entram se a banca mostrar uso.
