# Fundamentos de desenho e ferramentas inteligentes para o AssetFlow

Nov 25, 2026 · @Luiza

## 1. Resumo

A ideia central: cada fundamento de desenho entra no AssetFlow de três formas ao mesmo tempo. Como regra escrita na base, como ferramenta que aplica a regra, e como verificação que confere se ela foi cumprida. Uma regra que só existe como texto depende de a IA lembrar dela.

**O que este documento traz:**

- **Fundamentos de desenho** adaptados ao pixel art, em três grupos: forma, luz e cor, e técnica própria do pixel (seções 2 a 4).
- **19 comandos novos para a receita**, que deixam o Claude pedir o resultado em vez de pintar pixel por pixel (seção 5).
- **12 ferramentas de produtividade** do app, que não gastam tokens (seção 6).
- **Um sistema de verificação** em que nenhuma regra entra na base sem dizer como será conferida (seção 7).
- **A ordem de construção** e o primeiro pedido para o Claude Code (seção 8).

**Como ler as tabelas das seções 2 a 4.** Cada linha é um fundamento, com quatro colunas: a regra que vai para a base, a ferramenta que a aplica, e como ela é verificada. As verificações são de quatro tipos:

| Tipo | Quem confere | Custo |
| --- | --- | --- |
| Por construção | A própria ferramenta: o erro deixa de ser possível | Nenhum |
| Medida | O app, com uma conta sobre a imagem | Nenhum |
| Olhar | O Claude, vendo a imagem e respondendo a uma pergunta | Tokens |
| Autora | Você, com "gostei", "não gostei" e a banca de teste | Seu tempo |

**O que é pesquisa e o que é proposta.** Os fundamentos vêm de fontes citadas na seção 9. As ferramentas são propostas minhas, desenhadas a partir deles. Nenhuma foi construída nem testada. Cada uma só fica no app se melhorar os desenhos na banca de teste.

**Relação com os planos anteriores.** Este documento substitui a ordem das etapas K2 a K4 do plano da base de conhecimento. A banca de teste (K1) e a Fase B2 continuam vindo primeiro.

## 2. Fundamentos de forma

A forma decide se o desenho se lê antes de qualquer cor entrar. Os cursos de desenho de figura separam duas ideias: a construção, que são as partes da figura, e o gesto, que é a relação e o movimento entre elas.

| Fundamento | Regra para a base | Ferramenta que aplica | Como se verifica |
| --- | --- | --- | --- |
| Gesto e linha de ação | Toda figura nasce de uma linha curva única que atravessa o corpo; figura reta e parada é a exceção | `boneco` com parâmetro de linha de ação | Medida: inclinação do eixo do corpo; olhar |
| Construção por volumes simples | O corpo é montado com esferas, cilindros e caixas antes do detalhe | `capsula` para membros, `boneco` para o conjunto | Por construção |
| Proporção | A altura se mede em cabeças; a escolha da proporção define o estilo (2 a 3 cabeças para mascote, 5 a 8 para realista) | `boneco` com parâmetro de cabeças | Medida: altura da cabeça sobre altura total |
| Sobreposição | Uma parte na frente da outra cria profundidade; partes que só se tocam pela borda achatam o desenho | Ordem das camadas com vão ou cobertura | Medida: partes vizinhas que se tocam sem se cobrir |
| Silhueta | Preenchida de preto, a figura ainda precisa ser reconhecível; o item que identifica o personagem tem de mudar o contorno | Prévia em silhueta, que a Fase B2 já cria | Olhar; medida de irregularidade do contorno |
| Linguagem de formas | Círculo sugere amigável, quadrado sugere sólido, triângulo sugere perigo ou agilidade; a forma dominante combina com o papel do personagem | Parâmetro de forma dominante no `boneco` | Olhar; autora |
| Assimetria e peso | Peso apoiado mais em uma perna, ombros e quadril em ângulos opostos, um lado diferente do outro | Poses prontas no `boneco` | Medida: simetria esquerda e direita abaixo de um limite |
| Espaço negativo | Os vãos entre braço e tronco e entre as pernas fazem parte do desenho | `capsula` mantém vão mínimo de 1 pixel | Medida: vãos presentes quando o membro está à mostra |

### O que muda em tamanhos pequenos

- **Com 16 pixels**, quase tudo acima vira uma decisão só: a silhueta. Não há espaço para gesto sutil.
- **Com 32 pixels**, cabe uma inclinação de corpo e uma assimetria clara.
- **Com 48 e 64 pixels**, cabem linha de ação, peso em uma perna e sobreposição de membros.

Por isso cada regra de forma entra na base com a faixa de tamanho em que vale.

### O que falta medir

Os números de proporção por estilo são convenções de ensino de desenho, não medições dos seus pacotes. Entram marcados como "a calibrar" até o app medir os sprites CC0 que você tem.

## 3. Fundamentos de luz, valor, cor e materiais

Este é o grupo em que as ferramentas mais ajudam, porque a luz segue regras que um programa consegue aplicar sempre do mesmo jeito.

### Luz e sombra

O ensino de desenho divide a luz sobre um volume em partes com nome. Do lado iluminado: o brilho e os meios-tons. A borda onde a luz vira sombra. Do lado da sombra: a sombra própria, a faixa mais escura junto à borda, a luz refletida, a sombra projetada sobre outra superfície e a sombra de contato, que é a mais escura de todas.

| Fundamento | Regra para a base | Ferramenta que aplica | Como se verifica |
| --- | --- | --- | --- |
| Uma fonte de luz | A luz vem de uma direção só, a mesma em todas as partes e em todos os assets do projeto | `sombrear` lê a direção do pedido | Por construção |
| Separar luz de sombra | Primeiro dividir cada volume em lado claro e lado escuro; os tons intermediários vêm depois | `sombrear` com tipo de volume: esfera, cilindro, caixa ou plano | Por construção |
| Sombra que não acompanha o contorno | Sombrear igualmente em volta da forma, sem direção, é o erro chamado sombreamento "de almofada" | `sombrear` | Medida: tom escuro distribuído por igual em toda a borda |
| Sombra projetada | Uma parte que fica na frente de outra escurece a de trás, do lado oposto à luz | `sombra_projetada` | Medida: partes sobrepostas sem sombra entre elas |
| Sombra de contato | Onde duas partes se encostam fica o ponto mais escuro | `oclusao` | Por construção |
| Quantidade de tons | Em sprite pequeno, três tons por material bastam; cinco é o teto do modelo clássico (três claros, dois escuros) | `rampa` com número de tons por tamanho | Medida: tons por material |

### Valor

| Fundamento | Regra para a base | Ferramenta que aplica | Como se verifica |
| --- | --- | --- | --- |
| Valor antes de matiz | O desenho precisa funcionar em tons de cinza; cor diferente com o mesmo valor não separa as partes | Prévia em cinza no painel do olhar | Medida: diferença de valor entre partes vizinhas, que a Fase B2 já cria |
| Hierarquia | O ponto de maior contraste fica onde o olho deve ir primeiro, em geral o rosto | Parâmetro de foco no `sombrear` | Medida: região de maior contraste; olhar |
| Separação do fundo | O sprite tem de se ler sobre fundo claro e sobre fundo escuro | Prévia sobre dois fundos | Medida: contraste do contorno contra cada fundo |

### Cor

| Fundamento | Regra para a base | Ferramenta que aplica | Como se verifica |
| --- | --- | --- | --- |
| Rampa por brilho | Uma rampa é um grupo de cores que funcionam juntas, ordenadas pelo brilho | `rampa` | Por construção |
| Variação de matiz | Ao escurecer, a cor caminha para o azul; ao clarear, para o amarelo; rampa que só muda o brilho fica sem vida | `rampa` com parâmetro de desvio de matiz | Medida: desvio de matiz entre tons vizinhos |
| Saturação controlada | A saturação cai nos tons muito claros e muito escuros e tem o pico no meio da rampa | `rampa` | Medida: saturação alta junto com brilho alto |
| Uma direção só | Matiz, saturação e brilho mudam cada um em um sentido único ao longo da rampa | `rampa` | Medida: mudança de sentido dentro da rampa |
| Economia | Poucas cores, reaproveitadas entre materiais | `rampa` compartilha tons extremos | Medida: número de cores contra o limite |

Um número útil para calibrar: Raymond Schlitter, autor do Pixelblog, escreve que gosta de bastante desvio de matiz, mas que 20 graus por passo é o máximo a que chega.

### Materiais

| Material | Regra para a base | Como se verifica |
| --- | --- | --- |
| Metal | Contraste alto: brilhos mais claros, sombras mais escuras, e às vezes luz refletida | Medida: faixa de valor do material |
| Fosco (tecido, pele, madeira) | Contraste baixo, transições suaves, sem brilho forte | Medida: faixa de valor do material |
| Vidro e água | Um brilho grande e claro do lado da luz e um segundo brilho do lado oposto | Olhar |
| Pelo e cabelo | Tufos que seguem uma direção, não fios soltos | Medida: pixels soltos; olhar |
| Pedra | Planos com valores diferentes, rachaduras e arestas | Olhar |

A ferramenta `material` junta as três coisas: ao declarar que uma camada é de metal, o app escolhe a rampa, o contraste e o tipo de brilho.

## 4. Fundamentos próprios do pixel

São as regras que não existem no desenho comum, porque nascem da grade. Quase todas são mecânicas, então são as melhores candidatas a virar ferramenta e medida automática.

| Fundamento | Regra para a base | Ferramenta que aplica | Como se verifica |
| --- | --- | --- | --- |
| Reta com degraus iguais | Uma reta inclinada é feita de segmentos do mesmo tamanho: 1 por 1, 2 por 1, 3 por 1; segmento diferente dos outros salta aos olhos | `reta` | Por construção; medida nos traços livres |
| Curva com degraus em progressão | Os tamanhos dos segmentos mudam aos poucos e em um sentido: 5, 2, 2, 1, 1 está certo; 5, 2, 1, 2, 1 cria um calombo | `curva` | Por construção; medida nos traços livres |
| Sem canto em L | Numa linha de 1 pixel, o pixel do meio de um canto em L é removido | `limpar_linha` | Medida: cantos em L restantes |
| Sem dobra | Trechos em que a linha fica com 2 pixels de espessura sem querer engrossam o traço | `limpar_linha` | Medida: dobras |
| Contorno coerente | Contorno inteiro escuro, ou seletivo (mais claro do lado da luz), ou colorido pelo tom escuro de cada material; a escolha vale para o projeto inteiro | `contorno` | Por construção; medida do tipo de contorno |
| Manchas, e não pixels soltos | A cor se organiza em manchas; pixel sozinho só como brilho intencional | Otimizador, que já existe | Medida: pixels soltos, que o laudo já conta |
| Sem faixas | Tons que acompanham o contorno em fileiras paralelas criam faixas e achatam o volume | `sombrear` | Medida: fileiras paralelas de tons vizinhos |
| Suavização manual, com critério | Um tom intermediário suaviza curvas; não se usa em retas horizontais e verticais nem em sprites muito pequenos | `suavizar` | Medida: suavização em reta ou em sprite pequeno |
| Pontilhado, com critério | Mistura dois tons em padrão regular; em sprite pequeno vira ruído | `pontilhar` | Medida: área pontilhada por tamanho |
| Leitura no tamanho real | O desenho é julgado em 1 vez, não ampliado | Painel do olhar com o tamanho real | Olhar |

### Um cuidado com a `reta`

Os editores de pixel art convivem com um conflito conhecido: a reta de degraus perfeitos fica bonita sozinha, mas nem sempre emenda com a reta seguinte. Por isso o comando `linha` de hoje continua existindo, e a `reta` é uma opção a mais.

### Um cuidado com a limpeza automática

Um tutorial de Pedro Medeiros observa que o algoritmo de remoção de cantos é útil mas nem sempre acerta, e que corrigir cantos pode criar serrilhados novos. A ordem recomendada é desenhar, corrigir cantos e depois corrigir serrilhados. No app, isso significa rodar as duas medidas depois da limpeza, e não confiar que ela resolveu.

### O que já está no documento de pesquisa anterior

Contorno, suavização, pontilhado e manchas já têm seções próprias no `PIXEL_KNOWLEDGE.md` (4, 7 e 8). A novidade aqui é ligar cada um a uma ferramenta e a uma medida.

## 5. Catálogo de ferramentas da receita

São 19 comandos novos, em seis grupos. Todos são opcionais: os comandos de hoje (`ret`, `elipse`, `linha`, `poligono`, `balde`, `px`) continuam valendo, e o Claude pode misturar os dois jeitos na mesma receita.

### Construção

| Comando | O que o Claude pede | O que o app faz |
| --- | --- | --- |
| `capsula` | Um membro entre dois ou três pontos, com espessura | Desenha braço ou perna com articulação e mantém o vão de 1 pixel até o tronco |
| `boneco` | Altura em cabeças, forma dominante, pose e linha de ação | Gera as massas do corpo em camadas nomeadas, prontas para vestir |
| `copiar` | Uma camada, com deslocamento e espelhamento | Duplica um braço, uma perna ou um enfeite sem reescrever os pixels |

### Linha

| Comando | O que o Claude pede | O que o app faz |
| --- | --- | --- |
| `reta` | Dois pontos | Traça com degraus de tamanho igual |
| `curva` | Três ou mais pontos | Traça com degraus em progressão suave |
| `limpar_linha` | Uma camada | Remove cantos em L e dobras, e relata o que mudou |

### Cor

| Comando | O que o Claude pede | O que o app faz |
| --- | --- | --- |
| `rampa` | Uma cor base, o número de tons e o desvio de matiz | Gera os tons e cria as chaves da paleta |
| `material` | O material de uma camada: metal, tecido, pele, madeira, vidro, pedra, pelo | Escolhe a rampa, o contraste e o tipo de brilho |

### Luz

| Comando | O que o Claude pede | O que o app faz |
| --- | --- | --- |
| `sombrear` | Uma camada e o tipo de volume: esfera, cilindro, caixa ou plano | Distribui claro, base e escuro conforme a direção da luz do pedido |
| `brilho` | Uma camada | Põe o ponto de brilho do lado da luz, do tamanho que o material pede |
| `sombra_projetada` | A camada que está na frente e a que está atrás | Escurece a de trás do lado oposto à luz |
| `oclusao` | Duas camadas que se encostam | Põe o tom mais escuro na linha de contato |
| `luz_de_borda` | Uma camada | Traça uma linha clara na borda oposta à luz, para destacar de fundo escuro |

### Acabamento

| Comando | O que o Claude pede | O que o app faz |
| --- | --- | --- |
| `contorno` | O tipo: inteiro, seletivo ou colorido | Gera o contorno de todas as camadas no estilo do projeto |
| `suavizar` | Uma borda curva | Põe tons intermediários, e recusa em retas e em sprites pequenos |
| `pontilhar` | Uma região e dois tons | Preenche com padrão regular, e recusa abaixo de um tamanho mínimo |
| `textura` | Uma camada e um padrão: veio de madeira, rachadura, tufos, escamas | Aplica o padrão com os tons da rampa do material |

### Detalhes

| Comando | O que o Claude pede | O que o app faz |
| --- | --- | --- |
| `rosto` | A expressão e a direção do olhar | Desenha olhos e boca no formato certo para o tamanho da cabeça |
| `extremidade` | Mão ou pé, aberto ou fechado | Desenha no formato certo para o tamanho do membro |

### Como isso muda uma receita

Um cavaleiro de 48 pixels hoje exige que o Claude escreva cada mancha de cor, cada sombra e cada pixel de contorno. Com as ferramentas, a receita vira uma lista de decisões: boneco de 3 cabeças com o peso na perna esquerda; camadas de armadura em metal; capa em tecido vermelho; sombrear tudo; sombra da capa sobre as costas; contorno seletivo; rosto sério. A receita fica mais curta, e os erros de luz e de linha deixam de depender de atenção.

### Três regras para não engessar

1. **Tudo é opcional.** Em "ousado", o Claude pode ignorar o `boneco` e construir a forma à mão, usando só as ferramentas de luz e de linha.
2. **Toda ferramenta aceita ajuste manual depois.** Um `px` por cima corrige o que o automático errou.
3. **O laudo diz o que cada ferramenta fez**, com posição, para o Claude conferir na imagem.

## 6. Ferramentas de produtividade do app

São 12 ferramentas que rodam só no app, sem chamar o Claude. Como os desenhos são receitas em camadas, muita coisa que seria um desenho novo vira uma operação sobre um desenho existente.

### Multiplicar um asset

| Ferramenta | O que faz | Exemplo |
| --- | --- | --- |
| Variantes de paleta | Troca as rampas de um asset aprovado | O mesmo soldado em azul, vermelho e verde |
| Troca de camadas | Substitui uma camada por outra da biblioteca | O mesmo guerreiro com espada, machado ou lança |
| Espelhar direção | Vira o sprite, mantendo a luz do lado certo | Personagem olhando para a esquerda e para a direita |
| Família de personagens | Reaproveita o corpo de um asset em vários pedidos | Quatro classes com a mesma proporção e o mesmo traço |

### Guardar o que deu certo

| Ferramenta | O que faz | Exemplo |
| --- | --- | --- |
| Biblioteca de peças próprias | Guarda camadas aprovadas para reuso | A capa que ficou boa serve em outros personagens |
| Promover a molde | Salva um asset como ponto de partida de um tipo e tamanho | O seu melhor mago vira o molde de magos |

As peças dessa biblioteca são desenhos feitos no seu app, então não há questão de licença de terceiros.

### Conferir sem gastar

| Ferramenta | O que faz | Exemplo |
| --- | --- | --- |
| Prévia em contexto | Mostra o sprite em tamanho real, sobre fundo claro e escuro, ao lado dos outros do projeto | Ver se a arqueira combina com o cavaleiro |
| Checagem de conjunto | Compara luz, contorno, paleta e proporção entre os assets do projeto | Avisa que um baú tem a luz do lado contrário |
| Comparar pedidos | Põe lado a lado o mesmo pedido com liberdades diferentes | É a tela da banca de teste |

### Ajustar e entregar

| Ferramenta | O que faz | Exemplo |
| --- | --- | --- |
| Editor de pixels na tela | Deixa você trocar alguns pixels com o mouse e salvar como remendo | Corrigir um olho torto sem pedir ao Claude |
| Conversão de paleta | Refaz as cores para uma paleta limitada | Ver o sprite na paleta de um console antigo |
| Folha de exportação | Junta vários assets em uma imagem só, com o arquivo de posições | Entregar os itens de um jogo em um arquivo |

### As três que mais economizam

1. **Editor de pixels na tela.** Hoje qualquer correção pequena custa uma rodada inteira com o Claude. Com o editor, você mesma resolve em segundos, e a sua correção pode virar lição.
2. **Variantes de paleta e troca de camadas.** Um asset bom rende vários, sem nenhum desenho novo.
3. **Biblioteca de peças próprias.** Quanto mais você usa o app, menos o Claude precisa desenhar do zero.

Várias destas já estavam previstas nas fases C e D do plano do app. Aqui elas aparecem juntas para mostrar o conjunto.

## 7. Como garantir que cada regra seja verificada

A garantia vem de uma regra de engenharia, e não de pedir atenção à IA: nenhuma regra entra na base sem declarar como será verificada, e o app registra o resultado de cada verificação em cada asset.

### A regra de entrada

Cada regra da base ganha um campo obrigatório, `verificacao`, com um dos quatro tipos da seção 1. Um teste automático do projeto falha se existir regra sem esse campo, ou se o campo apontar para uma medida ou pergunta que não existe.

### Distribuição dos fundamentos deste documento

| Tipo de verificação | Quantos fundamentos | Exemplos |
| --- | --- | --- |
| Por construção | 8 | Luz única, rampa por brilho, reta com degraus iguais |
| Medida pelo app | 24 | Valor entre partes vizinhas, desvio de matiz, cantos em L, simetria |
| Só pelo olhar | 4 | Silhueta reconhecível, leitura no tamanho real, vidro e pedra |
| Só pela autora | 1 | Se a forma dominante combina com o personagem |

A contagem considera o tipo principal de cada linha das tabelas das seções 2 a 4. O ponto que importa: a maior parte pode ser conferida sem depender do julgamento da IA.

### A ficha de verificação de cada asset

Cada asset pronto guarda uma ficha com uma linha por regra aplicável:

| Campo | Conteúdo |
| --- | --- |
| Regra | O identificador da regra na base |
| Tipo | Construção, medida, olhar ou autora |
| Resultado | Passou, não passou, não se aplica |
| Detalhe | O número medido, ou a resposta do Claude, com a posição |
| Quem | App, Claude ou você |

A ficha aparece na tela de detalhe do asset. É nela que você vê se a base foi mesmo consultada naquele desenho.

### Como evitar um olhar de faz de conta

A Fase B2 já registrou este limite: o servidor não tem como provar que o Claude olhou a imagem. Três medidas reduzem o risco.

1. **Resposta por pergunta, e não uma linha livre.** Ao concluir, o Claude responde a cada pergunta da lista com sim ou não, e com a posição quando for não. Uma resposta genérica fica evidente.
2. **Cruzamento com as medidas.** Se o Claude responde que os valores estão bons e o app mediu partes vizinhas com o mesmo valor, a ficha marca divergência. Divergências aparecem em destaque na tela.
3. **Revisão independente na banca.** Nas rodadas de teste, uma conversa nova, que não participou do desenho, avalia a imagem com a mesma lista. Custa tokens, então fica só para a banca.

### O que continua dependendo de você

- **Beleza.** Nenhuma medida diz se um desenho é bonito. Os seus "gostei" e "não gostei" continuam sendo a verificação final.
- **Os limites das medidas.** Cada medida nova entra marcada como "a calibrar" e é ajustada contra os pacotes de referência, como foi feito com o validador.
- **Medida que acusa demais.** Uma medida que marca erro em sprites profissionais está errada, e sai ou é ajustada.

### Verificação da própria base

- Cada regra aponta a fonte de onde saiu: uma seção de documento ou uma medição.
- Números tirados de tutorial entram como "a calibrar" até serem conferidos nos pacotes.
- Uma regra que piora os desenhos na banca é desligada, com o motivo anotado.

## 8. Ordem de construção e pedido para o Claude Code

As ferramentas entram em cinco lotes pequenos, do mais mecânico para o mais criativo. Cada lote passa pela banca de teste antes do seguinte.

| Lote | Ferramentas | Por que nesta posição |
| --- | --- | --- |
| F1. Linha e contorno | `reta`, `curva`, `limpar_linha`, `contorno`, e as medidas de cantos, dobras e degraus | São regras exatas, com pouco risco de engessar |
| F2. Cor e luz | `rampa`, `material`, `sombrear`, `brilho`, `oclusao`, `sombra_projetada` | É onde estão os erros mais visíveis de hoje |
| F3. Construção | `capsula`, `copiar`, `boneco` | Maior ganho de produtividade e maior risco de engessar |
| F4. Detalhes e acabamento | `rosto`, `extremidade`, `suavizar`, `textura`, `luz_de_borda`, `pontilhar` | Dependem dos lotes anteriores |
| F5. Ficha de verificação | O campo obrigatório nas regras, a ficha por asset, as respostas por pergunta e o cruzamento | Pode começar junto com o F1 e crescer a cada lote |

As ferramentas de produtividade da seção 6 entram nas fases C e D do plano do app. O editor de pixels na tela vale ser adiantado, porque economiza desde o primeiro dia.

### Sequência completa, juntando os planos

1. Fase B2: ver, corrigir e aprender. Já enviada.
2. K1: inventário e banca de teste. O pedido está no plano da base de conhecimento.
3. F1 e F5, deste documento.
4. F2, F3 e F4, um por vez.
5. Fichas por assunto (quadrúpedes, rostos, materiais), com pesquisa minha para cada uma.
6. Fases C e D do app, com as ferramentas de produtividade.

### Pedido para os lotes F1 e F5

Exporte este documento em Markdown, salve como `backend/docs/FUNDAMENTOS_E_FERRAMENTAS.md` e envie o texto abaixo **depois** que a banca de teste (K1) existir.

```text
Adicionei backend/docs/FUNDAMENTOS_E_FERRAMENTAS.md. Leia inteiro antes
de qualquer alteração. Mesmas regras de sempre: branch desenhista-mcp,
sem PR, sem tocar no main, sem enviar backend/data/, .mcp.json nem
.env.

Execute SOMENTE os lotes F1 (linha e contorno) e F5 (ficha de
verificação). Antes de programar, me mostre e ESPERE meu "sim":

1. O formato exato de cada comando novo da receita (reta, curva,
   limpar_linha, contorno), com um exemplo real de cada e a mensagem de
   erro em português quando o pedido não fizer sentido.
2. A mesma figura simples desenhada do jeito de hoje e com os comandos
   novos: as duas imagens, o tamanho de cada receita em caracteres e
   em tokens.
3. As medidas novas (cantos em L, dobras, degraus irregulares em reta e
   em curva): como cada uma é calculada e o que ela dá nos pacotes de
   referência. Uma medida que acusa erro na maioria dos sprites
   profissionais está errada: diga quais ficaram assim.
4. O campo verificacao nas regras da base, o teste que impede regra
   sem verificação, e a lista das regras atuais com o tipo que cada
   uma recebe.
5. A ficha de verificação por asset e como ela aparece na tela.
6. A resposta por pergunta no concluir_pedido e o cruzamento com as
   medidas, com o custo em tokens.
7. Como o contorno automático convive com o contorno desenhado à mão,
   e o que acontece em "ousado".
8. Onde o documento não bate com o código.

Todo comando novo é opcional: os comandos atuais continuam funcionando
e podem ser misturados na mesma receita.

Depois do "sim", programe, rode a banca de teste comparando com a
rodada de referência e pare. Só mantemos o que melhorar na banca.
```

## 9. Fontes e limites

### Fontes consultadas

| Tema | Fonte |
| --- | --- |
| Construção e gesto no desenho de figura | [JW Learning, Gesture and Construction](https://www.skillshare.com/en/classes/beginner-figure-drawing-fundamentals-gesture-and-construction/1007981938) |
| Linha de ação e linguagem de formas | [BINUS, Line, Shape, and Motion: Visual Language in Animation](https://binus.ac.id/bandung/dkv/2025/11/04/line-shape-and-motion-visual-language-in-animation/) |
| Partes da luz e da sombra, e a estrutura de cinco valores | [Proko, Elements of Light and Shadow](https://www.proko.com/course-lesson/elements-of-light-and-shadow/notes) e [Shading Light and Form](https://www.proko.com/lesson/shading-light-and-form-basics) |
| Sombra de contato e luz refletida | [Sessions College, The Anatomy of a Shadow](https://www.sessions.edu/notes-on-design/looking-at-light-the-anatomy-of-a-shadow/) |
| Rampas, saturação e desvio de matiz | [Raymond Schlitter, Pixelblog 1: Color Palettes](https://www.slynyrd.com/blog/2018/1/10/pixelblog-1-color-palettes) |
| Rampa com mudança em um sentido só; cor mais azul ao escurecer | [OpenGameArt, Chapter 5: Color Palettes](https://opengameart.org/content/chapter-5-color-palettes) |
| Retas por coeficiente e curvas por tamanho de segmento | [OpenGameArt, Chapter 2: Lines and Curves](https://opengameart.org/content/chapter-2-lines-and-curves) |
| Ordem dos segmentos em curvas | [Lospec, Pixel Art Outlines Tutorial](https://lospec.com/articles/pixel-art-outlines) |
| Remoção de cantos em L e seus limites | [Pedro Medeiros, How to start making pixel art #7](https://medium.com/pixel-grimoire/how-to-start-making-pixel-art-7-e504bfa4ddf2) |
| Reta perfeita contra reta contínua | [Fórum do Aseprite, Line tool makes irregular lines](https://community.aseprite.org/t/line-tool-makes-irregular-lines/6306) |
| Faixas e sombreamento "de almofada" | [Pixel Parmesan, Anti-Aliasing Fundamentals](https://pixelparmesan.com/anti-aliasing-fundamentals-for-pixel-artists) |
| Contraste de metal e de materiais foscos | [Highrise, guia de materiais](https://create.highrise.game/learn/designer-resources/artguides/material) |
| Vidro, água e texturas em pixel art | [OpenGameArt, Chapter 7: Textures and Dithering](https://opengameart.org/node/5495) |
| Teste em tons de cinza | [Studio Matrx, Colour Contrast and Legibility](https://www.studiomatrx.org/students/colour-theory-and-application/colour-contrast-and-legibility) |

Um sinal de que a geração de rampas pode ser automatizada: já existe um gerador de paletas de código aberto, o [PalettePainter](https://github.com/chickensoft-games/PalettePainter), construído sobre os princípios do Pixelblog, com parâmetros de desvio de matiz e de redução de saturação.

### Limites desta pesquisa

- **Li as fontes pelos trechos devolvidos na busca**, em 25 de novembro de 2026, e não as páginas inteiras. Antes de uma regra entrar na base com número, vale abrir a fonte e conferir.
- **Os fundamentos de forma vêm do desenho tradicional.** A adaptação para 16, 32 e 48 pixels é leitura minha, e precisa da banca para ser confirmada.
- **As ferramentas são propostas.** Não há garantia de que cada uma melhore o resultado. Algumas podem piorar ou engessar, e por isso entram em lotes pequenos.
- **O `boneco` é a aposta mais arriscada.** É a ferramenta que mais economiza e a que mais pode deixar todos os personagens parecidos. Deve nascer com muitos parâmetros e ser sempre opcional.
- **Nenhuma medida julga beleza.** O conjunto reduz erros técnicos visíveis. O gosto continua sendo seu.
- **Texto e imagens dos tutoriais não entram no projeto.** A base guarda a técnica com palavras próprias e o link da fonte.
