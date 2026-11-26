# Lote F2 — cor e luz na receita

> Segundo lote da sessão de 2026-11-25 ([FUNDAMENTOS_E_FERRAMENTAS.md](FUNDAMENTOS_E_FERRAMENTAS.md)
> §3, §5 e §8). Proposta escrita e seguida sem consulta, como a autora pediu;
> decisões e dúvidas também no [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md).
> Código: `assetflow/generation/engines/desenhista/cor_e_luz.py`.

## 1. O que entrou

Seis comandos opcionais. A receita de antes continua igual, e os dois jeitos se
misturam na mesma receita.

| Comando | Onde | O que faz |
|---|---|---|
| `rampas` | raiz | `[{"chaves": "abc", "base": "#rrggbb", "desvio": 12, "base_em"?: 1}]` gera de 2 a 5 tons do escuro ao claro em volta da base: ao escurecer o matiz vai para o azul, ao clarear para o amarelo, `desvio` graus por passo (até 20); a saturação cai nas pontas. As chaves entram na paleta |
| `luz` | raiz | `cima-esquerda` (padrão), `cima-direita`, `cima`, `esquerda`, `direita` |
| `material` | camada | `metal`, `vidro`, `tecido`, `pele`, `madeira`, `pelo`, `pedra`: contraste do `sombrear` (metal 1,5×, foscos 0,7–0,8×) e tamanho do `brilho` (metal e vidro 2 px, vidro com reflexo do lado oposto; foscos 1 px) |
| `{"sombrear": volume, "rampa": "abc"}` | op | redistribui os tons da rampa nos pixels **desta camada** que usam uma das chaves dela, pela luz e pelo volume: `esfera`, `cilindro` (vertical), `caixa` (topo claro, frente média, lado oposto à luz escuro), `plano` (gradiente) |
| `{"brilho": "c", "sobre": "ab"}` | op | o ponto de brilho do lado da luz, sobre as chaves de `sobre` |
| `{"oclusao": "<camada>", "cor": "a", "sobre"?}` | op | sombra de contato: os pixels desta camada que encostam na camada citada (desenhada antes) |
| `{"sombra_projetada": "<camada de trás>", "cor": "a", "distancia"?: 1, "sobre"?}` | op | esta camada escurece a de trás, do lado oposto à luz, sem tomar os pixels dela |

**Regras de recusa** (mensagem em português, como as outras): volume, luz ou
material que não existem; rampa com chave fora da paleta; chave de rampa que já
está na paleta; desvio acima de 20; camada citada que não vem antes; efeito em
camada com `espelho` (a cópia levaria a luz para o lado errado).

## 2. Interruptor

`engines.yaml`, `desenhista-v1.options.comandos_cor_e_luz` (padrão `true`;
`ASSETFLOW_ENGINE_DESENHISTA_V1_OPTIONS='{"comandos_cor_e_luz": false}'`).
Desligado: a receita que usar qualquer um dos seis é recusada dizendo isso, e o
formato que o MCP mostra deixa de citá-los. O formato ligado cresce três linhas
(~470 caracteres, ~160 tokens por consulta).

## 3. Decisões tomadas sem consulta

1. **Chaves de rampa de um caractere**, como o resto da paleta: `"chaves":
   "abc"` em vez de nomes, para caberem nas linhas de `px`.
2. **A direção da luz é da receita**, não do spec: a gaveta não lê a base de
   conhecimento (fronteira). O recorte já diz a luz do pedido, e o Claude a
   repete na receita; o padrão é o mesmo da base (`cima-esquerda`).
3. **Os efeitos agem sobre o que a camada já pintou**, na ordem das operações,
   antes do espelho — por isso a recusa em camada espelhada.
4. **O tom mais escuro** sai só onde a intensidade é mínima
   (arredondamento para o tom mais próximo), o que deixa a faixa escura
   estreita, como pede a regra de luz da base.
5. **Ligado por padrão**: a banca mede depois, ligando e desligando.

## 4. Dúvidas

1. Os números de intensidade (raio da esfera, faixas da caixa, contraste por
   material) são convenção minha, `a calibrar` na banca.
2. O desvio de matiz caminha para 240° e 60° fixos; o Pixelblog fala em
   "azul" e "amarelo" sem número exato.
