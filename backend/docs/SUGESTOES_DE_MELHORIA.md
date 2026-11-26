# Sugestões de melhoria do AssetFlow

Lista de ideias para depois que os planos atuais estiverem implementados
(`PLANO_APP_DESENHISTA.md`, `PLANO_BASE_CONHECIMENTO.md` e
`FUNDAMENTOS_E_FERRAMENTAS.md`). Nenhuma foi construída nem testada.

Escrito em 26 de novembro de 2026.

## Como usar esta lista

- São 17 sugestões em três grupos: qualidade do desenho, produtividade e
  uso do app.
- Cada uma traz o que é, como funcionaria, por que ajuda, e o custo ou risco.
- A seção final propõe uma ordem.
- Cinco delas (9, 12, 14, 15 e 16) foram oferecidas como itens extras para a
  fila do Claude Code na noite de 25 de novembro. Se você enviou esses itens,
  confira no `RELATORIO_ESTADO.md` o que ficou pronto e risque aqui.
- Uma ideia ficou de fora por decisão sua: importar um rabisco feito por você.
  O app deve fazer o trabalho, e não depender de você desenhar.

---

## Grupo A: para o desenho ficar mais bonito

### 1. Silhueta antes do detalhe

**O que é.** Depois do conceito, o Claude desenha só a mancha preta do
personagem, em três versões. Você escolhe uma, e ele detalha a escolhida.

**Como funcionaria.**
- Uma etapa nova entre "conceito" e "desenho", com modo "eu escolho",
  "o Claude escolhe" e "pular".
- A silhueta é uma receita de uma camada e uma cor, então é curta.
- A silhueta escolhida vira a base do desenho: as camadas de cor entram por
  cima dela.

**Por que ajuda.** A forma é o que mais pesa na leitura de um sprite, e é
onde os desenhos atuais saem genéricos. Uma silhueta custa muito pouco, então
dá para descartar formas sem graça antes de pagar pelo desenho inteiro.

**Custo e risco.** Mais uma ida à conversa por pedido no modo "eu escolho".
Em 16 pixels a etapa quase não faz diferença, e pode ser pulada.

### 2. Guia de estilo por projeto

**O que é.** Cada jogo tem a sua paleta, tipo de contorno, direção de luz,
proporção e nível de detalhe, definidos uma vez.

**Como funcionaria.**
- Vários projetos no app, em vez de um só (`principal`).
- Uma tela "Estilo do projeto" com as escolhas, e uma prévia.
- Todo pedido do projeto herda o guia, sem você repetir instruções.
- A checagem de conjunto avisa quando um asset foge do guia.

**Por que ajuda.** Hoje cada pedido decide tudo do zero, e dois assets do
mesmo jogo podem não combinar. Com o guia, o conjunto fica coerente.

**Custo e risco.** Exige a parte de vários projetos, que foi adiada no plano
do app. Combina com a fase de estilos (`PIXEL_STYLES.md`).

### 3. Ficha de personagem

**O que é.** Um personagem aprovado vira uma ficha permanente, com as suas
camadas, cores, medidas e conceito.

**Como funcionaria.**
- Botão "criar ficha" no detalhe de um asset aprovado.
- Pedidos novos podem citar a ficha: "a maga friorenta, de costas", "a maga
  friorenta, atacando".
- O Claude recebe a receita da ficha como ponto de partida e muda só o que o
  pedido exige.

**Por que ajuda.** Poses, direções e animações do mesmo personagem saem
consistentes, e custam menos do que desenhar do zero.

**Custo e risco.** Depende das ferramentas de construção (`boneco`,
`capsula`) para mudar a pose sem redesenhar tudo.

### 4. Perfil do seu gosto

**O que é.** Um texto curto que descreve o que você acha bonito em pixel art,
tirado de exemplos que você escolhe.

**Como funcionaria.**
- Você separa de 15 a 20 pixel arts de que gosta, de jogos ou de artistas.
- O Claude olha todas e escreve o que têm em comum: proporção, quantidade de
  detalhe, tipo de contorno, clima das cores, expressão.
- Você revisa e corrige o texto.
- O perfil entra em todo pedido, e pode ter versões por projeto.

**Por que ajuda.** O app conhece regras de pixel art, mas não conhece o seu
gosto. Beleza é subjetiva, e hoje esse critério só aparece depois, no
"gostei" e "não gostei".

**Custo e risco.** As imagens servem só para descrever o gosto. Nada é
copiado nem guardado no repositório. O perfil precisa ser curto, para não
engessar.

### 5. Desenhar em passes

**O que é.** O desenho é feito em etapas, com um olhar no meio, em vez de
tudo de uma vez.

**Como funcionaria.**
- Passe 1: formas e cores chapadas, sem sombra. O Claude olha e corrige forma,
  proporção e pose.
- Passe 2: sombra, brilho, detalhes e contorno. O Claude olha de novo.
- O número de passes é configurável, para controlar o custo.

**Por que ajuda.** Hoje ele só olha no fim, quando um erro de forma já está
coberto pela sombra e pelo detalhe. Corrigir a forma antes custa menos e dá
resultado melhor. As pesquisas sobre desenho por código apontam o mesmo:
ver o resultado no meio do caminho melhora a qualidade.

**Custo e risco.** Uma imagem a mais por pedido (cerca de 300 tokens) e
possivelmente um remendo a mais. Combina bem com as ferramentas de luz, que
tornam o passe 2 barato.

### 6. Comentário apontando o lugar

**O que é.** Você clica numa região da imagem e escreve o que quer mudar ali.

**Como funcionaria.**
- Na tela de detalhe, um clique ou um retângulo sobre o sprite ampliado.
- O comentário vai para o Claude com a posição exata e as camadas que ficam
  naquela área.
- Ele remenda só aquele pedaço.

**Por que ajuda.** "O cajado ficou grande" obriga o Claude a adivinhar o que
mudar. Com a posição, a correção fica precisa, e o remendo, menor.

**Custo e risco.** Baixo. Depende do mapa de camadas que a Fase B2 já grava.

### 7. Passe de polimento

**O que é.** Um pedido separado, "polir", que só faz acabamento em um asset
já aprovado na forma e nas cores.

**Como funcionaria.**
- Uma lista de verificação própria: pixels soltos, curvas, brilhos, contorno,
  suavização.
- Uma regra dura: o polimento não muda a silhueta nem a paleta.
- O app compara antes e depois e mostra o que mudou.

**Por que ajuda.** Separa a decisão criativa do capricho técnico. Evita que
um pedido de "melhorar" mexa no que já estava bom.

**Custo e risco.** Depende das medidas de linha e de limpeza do lote F1.

### 8. Especializar antes de generalizar

**O que é.** Uma escolha de estratégia: ficar muito boa em uma faixa antes de
abrir para todas.

**Como funcionaria.**
- Escolher um alvo, por exemplo personagens de 48 pixels em um estilo.
- Concentrar ali as fichas da base, as lições, os moldes, as peças próprias e
  a banca de teste.
- Só expandir para outro tipo ou tamanho quando esse estiver no nível que
  você quer.

**Por que ajuda.** Hoje o app tenta personagem, bicho, arma e objeto, em
quatro tamanhos, e a base fica rasa em tudo. Acumular no mesmo lugar faz a
qualidade subir mais rápido.

**Custo e risco.** Nenhum custo de programação. O custo é adiar os outros
tipos de asset.

### 9. Estudo dos melhores sprites

**O que é.** O Claude olha, como imagem, os melhores sprites dos pacotes CC0
e escreve por que cada um funciona.

**Como funcionaria.**
- Escolher os 30 melhores, variando pacote, tipo e tamanho.
- Para cada um, uma análise curta: como o rosto foi resolvido naquele
  tamanho, onde está o contraste, como a roupa sugere volume, o que a
  silhueta tem de marcante.
- As técnicas gerais viram regras propostas para a base, que você aprova.
- Os 30 ficam marcados como "bons exemplos", para o interruptor de exemplo
  usar só eles.

**Por que ajuda.** A base passa a ter conteúdo tirado de exemplos reais, e
não só de regra genérica. Resolve também o problema do exemplo ruim, que
apareceu no teste da maga.

**Custo e risco.** Gasta bastante tokens uma vez só. As análises ficam em
`backend/data/`, porque tratam de arquivos de terceiros; só as técnicas
gerais vão para a documentação.

---

## Grupo B: para render mais com menos tokens

### 10. Animação por camadas

**O que é.** O app anima um sprite movendo e trocando as suas camadas, sem
chamar o Claude.

**Como funcionaria.**
- Animações prontas: respirar, piscar, flutuar, balançar a capa, tremer.
- Cada uma é uma lista de deslocamentos por camada e por quadro.
- Prévia animada na tela e exportação em spritesheet e GIF.

**Por que ajuda.** As animações simples, que são a maioria num jogo pequeno,
saem de graça a partir de um asset aprovado.

**Custo e risco.** Só funciona bem se as camadas tiverem nomes padronizados
(cabeça, tronco, braço), o que o `boneco` ajuda a garantir. Caminhada e
ataque continuam precisando de desenho.

### 11. Pedidos em lista

**O que é.** Você cola uma lista e o app cria todos os pedidos de uma vez.

**Como funcionaria.**
- Um campo de texto, um item por linha: "espada, escudo, elmo, bota".
- Tamanho, cores, liberdade e estilo valem para a lista toda.
- Opção de tratar como família, com a mesma paleta e a mesma luz.

**Por que ajuda.** Um conjunto inteiro de itens em um passo, e coerente.

**Custo e risco.** Baixo. O gasto de tokens é o mesmo de pedir um por um.

### 12. Painel de custo

**O que é.** A tela mostra quanto cada pedido gastou e o total do dia.

**Como funcionaria.**
- Tokens estimados por pedido, por etapa (conceito, desenho, olhar, remendo).
- Total do dia e da semana.
- Um limite diário que você define, com aviso ao ser atingido.

**Por que ajuda.** Com o plano menor, você precisa saber o que cabe antes de
começar um lote.

**Custo e risco.** O app só consegue estimar. O raciocínio do Claude não
entra na conta, então o número real é maior que o mostrado.

### 13. Modelo mais leve para tarefas simples

**O que é.** Usar um modelo mais barato para as tarefas fáceis e o mais forte
para o desenho de personagens.

**Como funcionaria.**
- Conceitos, lições e itens pequenos com o modelo leve.
- Personagens e remendos difíceis com o modelo forte.

**Por que ajuda.** Estica o plano.

**Custo e risco.** Precisa conferir o que o Claude Code permite escolher e
como isso conta nos limites do plano. O modelo leve pode desenhar pior, e a
banca de teste é o que mostra se compensa.

---

## Grupo C: para o app dar menos trabalho

### 14. Um clique para abrir

**O que é.** Um atalho que sobe a API e a tela e abre o navegador.

**Como funcionaria.**
- Um arquivo `iniciar.bat` na raiz do projeto.
- Ele espera as duas partes responderem e abre o endereço certo, mesmo quando
  a porta 5173 está ocupada por outro app.

**Por que ajuda.** Acaba com os dois terminais e com a confusão de endereços
que aconteceu no primeiro teste.

**Custo e risco.** Muito baixo.

### 15. Aviso de servidor desatualizado

**O que é.** A tela avisa quando o servidor MCP está rodando código antigo.

**Como funcionaria.**
- A API e o servidor MCP registram o commit em que subiram.
- Se o MCP estiver em um commit mais antigo que o código, a tela mostra
  "reconecte pelo /mcp".

**Por que ajuda.** Esse problema aconteceu várias vezes, e fez desenhos
saírem pelo código antigo sem ninguém perceber.

**Custo e risco.** Muito baixo.

### 16. Cópia de segurança

**O que é.** Um botão que salva em um arquivo tudo o que fica em
`backend/data/`.

**Como funcionaria.**
- Um zip datado com assets, fila, lições, opiniões e banca.
- Um comando para restaurar.
- O zip fica fora do repositório.

**Por que ajuda.** Essa pasta não vai para o GitHub. Se ela se perder, todos
os desenhos e todo o aprendizado acumulado se perdem junto.

**Custo e risco.** Muito baixo. Os bancos têm três arquivos cada, e a cópia
precisa levar os três de forma consistente.

### 17. Exportar para motor de jogo

**O que é.** Saída pronta para Godot, Unity ou Aseprite.

**Como funcionaria.**
- Spritesheet com o arquivo de posições no formato de cada motor.
- Arquivo com camadas para abrir no Aseprite e continuar editando.
- Paleta no formato dos editores.

**Por que ajuda.** Encurta o caminho entre o asset pronto e o jogo.

**Custo e risco.** Médio. Cada formato precisa ser conferido na documentação
oficial na hora de implementar. Vale escolher um motor só para começar.

---

## Ordem sugerida

Depois que os planos atuais estiverem implementados e testados:

| Ordem | Sugestão | Motivo |
|---|---|---|
| 1 | 16. Cópia de segurança | Protege tudo o que já foi construído |
| 2 | 14. Um clique para abrir | Pequena, e melhora o uso de todo dia |
| 3 | 15. Aviso de servidor desatualizado | Pequena, e evita erro silencioso |
| 4 | 12. Painel de custo | Necessário com o plano menor |
| 5 | 9. Estudo dos melhores sprites | Alimenta a base com exemplos reais |
| 6 | 4. Perfil do seu gosto | Ensina ao app o que é bonito para você |
| 7 | 1. Silhueta antes do detalhe | Completa a etapa de conceito |
| 8 | 5. Desenhar em passes | Corrige a forma antes do detalhe |
| 9 | 6. Comentário apontando o lugar | Deixa as suas correções precisas |
| 10 | 2. Guia de estilo por projeto | Dá coerência ao conjunto de um jogo |
| 11 | 3. Ficha de personagem | Abre caminho para poses e animação |
| 12 | 10. Animação por camadas | Animações simples sem gastar tokens |
| 13 | 7. Passe de polimento | Acabamento separado da criação |
| 14 | 11. Pedidos em lista | Produção em volume |
| 15 | 17. Exportar para motor de jogo | Quando houver um jogo para receber |
| 16 | 13. Modelo mais leve | Depende de conferir o que o plano permite |

A sugestão 8 (especializar antes de generalizar) não entra na fila, porque é
uma decisão sua e não uma implementação. Vale tomá-la antes da número 5, já
que ela define em que tipo de sprite o estudo deve se concentrar.

## Regra para todas

Como nos planos anteriores: uma por vez, com interruptor quando fizer
sentido, e passando pela banca de teste antes de ser mantida. O que não
melhorar os desenhos ou o uso sai.
