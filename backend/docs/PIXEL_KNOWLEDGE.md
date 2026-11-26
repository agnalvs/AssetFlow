# Base de conhecimento de pixel art e animação — AssetFlow

Nov 25, 2026 · @Luiza

## 1. Como usar este documento

Este documento reúne as práticas de pixel art e de animação que o AssetFlow precisa conhecer para desenhar bem na grade. Cada seção termina com um quadro **"Regra para o app"**, que diz como a prática vira configuração, validação ou acabamento automático.

As regras se dividem em três destinos dentro do app:

| Destino | O que entra | Onde mora |
| --- | --- | --- |
| Conhecimento para o desenhista | Proporções, paletas, número de frames, poses-chave | `config/pixel_knowledge/*.yaml`, entregue em trechos curtos pela ferramenta MCP |
| Acabamento automático | Contorno, sombra, espelho, limpeza | Código do desenhista e do Pixel Optimizer |
| Validação | O que reprova ou gera aviso | `PixelValidator` e `PixelAcceptancePolicy` |

Três avisos sobre o conteúdo:

- **Regra medida e regra de gosto são coisas diferentes.** "Alpha binário" e "paleta dentro do limite" são verificáveis. "Evite dithering" é convenção de estilo, e artistas experientes discordam entre si. O texto indica qual é qual.
- **Os números são pontos de partida.** Contagens de frames e tempos vêm de tutoriais reconhecidos, mas cada jogo ajusta ao próprio ritmo.
- **Onde uma fonte não dá número, o documento diz isso.** Valores marcados como "convenção comum" não têm fonte única e devem ser testados no app.

## 2. Fundamentos: grade, resolução e escala

Pixel art se define pelo controle deliberado de cada pixel, não pelo formato do arquivo. O [tutorial do Pixel Joint](https://gwern.net/doc/www/pixeljoint.com/ddfba8b00ecdc232df4936b61575ca99d5aba345.html) trata muitas cores como sinal de alerta, porque costumam vir de ferramentas de mistura automática, e manda salvar em PNG ou GIF, nunca JPG.

### Resolução lógica

- **Um pixel lógico = um pixel do arquivo.** O sprite é desenhado no tamanho real (32×32 são 1.024 pixels) e só é ampliado na exibição.
- **Ampliação sempre inteira e por vizinho mais próximo** (2×, 3×, 4×). Escala fracionária cria pixels de larguras diferentes; filtro bilinear cria borrão.
- **Sem rotação ou redimensionamento livre depois de pronto.** Girar 30° ou reduzir 70% destrói a grade. Rotações seguras: 90°, 180°, 270° e espelhamentos.
- **Mesma densidade em todo o jogo.** Um personagem 32×32 ao lado de um tile 16×16 ampliado 2× tem "pixels de tamanhos diferentes" na tela. É o erro de consistência mais visível.

### Tamanhos de canvas

| Tamanho | O que cabe | Uso típico |
| --- | --- | --- |
| 8×8 | Olhos e direção do corpo | Ícones mínimos |
| 16×16 | Olhos, cabelo, tipo de corpo | Estilo NES, tiles clássicos |
| 24×24 | Roupa, expressão, acessórios | Meio-termo |
| 32×32 | Equipamento, poses, expressões variadas | Estilo SNES, o mais versátil |
| 48×48 ou mais | Proporção realista, detalhe fino | Retratos, luta |

Fonte da tabela: [Pixnote, personagens](https://pixnote.net/en/learn/character). Para tiles, 16×16 é o tamanho mais comum, e acima de 32×32 já é exagero para pixel art, segundo o [Pixelblog 20](https://www.slynyrd.com/blog/2019/8/27/pixelblog-20-top-down-tiles).

### Canvas maior que o sprite

O canvas de um personagem animado precisa de folga para o salto, a arma estendida e o efeito de golpe. Um personagem "32×32" costuma viver num quadro de 48×48 ou 64×64. Todos os frames de uma animação usam o mesmo canvas, com os pés na mesma linha.

### Regra para o app

- Validação `hard`: dimensão exata do spec, alpha binário, PNG.
- Preview: escala inteira, vizinho mais próximo, nunca o asset.
- Conhecimento: tabela `canvas_por_tipo` com tamanho do corpo e folga de animação por tipo de asset.
- Aviso `semantic`: sprite que ocupa menos de \~50% ou encosta na borda do canvas (valor a calibrar).

## 3. Silhueta, forma e legibilidade

Um sprite bom se reconhece só pelo contorno preenchido de preto. O [guia de personagens do Pixnote](https://pixnote.net/en/learn/character) propõe três testes: ele se lê em preto sólido, se distingue dos outros personagens, e a arma ou item-chave faz parte do contorno.

### Ordem de construção

1. **Silhueta** em uma cor só.
2. **Cores-base**: pele, cabelo, roupa, com 3 a 5 cores.
3. **Luz e sombra** a partir de uma fonte de luz definida.
4. **Polimento**: contorno, olhos, acessórios.

Essa ordem é a mesma do Pixnote e vale para qualquer asset. Ela também é a ordem natural das camadas que o desenhista do app recebe.

### Práticas de forma

- **Formas grandes primeiro.** Em 32×32 cabem três ou quatro massas legíveis (cabeça, tronco, pernas, arma). Detalhe só entra depois que as massas funcionam.
- **Exagere o que identifica.** Chapéu do mago, escudo do guerreiro e arco do arqueiro devem alterar a silhueta, não só a cor interna.
- **Classe pela forma e pela cor.** O Pixnote sugere guerreiro largo em tons de metal, mago em trapézio (o manto esconde o corpo), arqueiro esguio em verde, curandeiro em branco e pastéis.
- **Assimetria dá personalidade.** Cabelo ou equipamento desigual evita o aspecto de carimbo.
- **Espaço negativo conta.** O vão entre braço e tronco, ou entre as pernas, separa os membros. Em 16×16, braço de 1 pixel de largura; com 2 ele se funde ao tronco.
- **Contraste de valor antes de matiz.** Converta mentalmente para tons de cinza: se as partes se confundem, a cor não vai salvar.

### Regra para o app

- Validação `semantic`: gerar a máscara da silhueta e medir ocupação, número de componentes soltos e contraste de valor entre regiões vizinhas.
- Conhecimento: `silhuetas_base` por tipo de corpo e tamanho, que o desenhista personaliza em vez de começar do zero.
- Acabamento: preview da silhueta em preto junto do laudo, para revisão rápida.

## 4. Linhas e contorno

Uma linha limpa tem degraus de comprimento regular; degrau fora do padrão é o defeito chamado *jaggy*. O [tutorial do Pixel Joint](https://gwern.net/doc/www/pixeljoint.com/ddfba8b00ecdc232df4936b61575ca99d5aba345.html) aponta três causas: pixel fora do lugar, segmentos de comprimento desigual e falta de anti-aliasing.

### Linhas retas

- **Ângulos perfeitos**: horizontal, vertical e 45° (1:1) não geram jaggies.
- **Ângulos regulares**: 2:1 (\~26,6°), 3:1, 1:2, 1:3. Cada degrau tem o mesmo comprimento.
- **Ângulos irregulares** misturam comprimentos (2,3,2,3). Funcionam se o padrão for periódico; ficam ruins se for aleatório.

### Curvas

Numa curva limpa, o comprimento dos segmentos muda de forma monótona: 4, 3, 2, 1, 1, 2, 3, 4. Uma sequência como 3, 1, 3, 2 cria um bico. Esta é a verificação mais útil que o app pode automatizar em contornos.

### Linha de 1 pixel

- Espessura constante de 1 pixel no contorno.
- **Sem "dobras" (doubles):** numa diagonal, dois pixels que se tocam pela lateral e pelo canto ao mesmo tempo engrossam a linha. Remover o pixel do canto interno deixa a linha "pixel-perfect".
- Linhas mais escuras parecem mais finas; a luminosidade muda a espessura aparente, segundo o Pixel Joint.

### Tipos de contorno

| Tipo | Como é | Lado bom | Lado ruim |
| --- | --- | --- | --- |
| Preto ou quase preto | Uma cor escura em toda a volta | Legível em qualquer fundo | Pesa em sprites pequenos |
| Colorido | Versão mais escura da cor de cada área | Mais suave e integrado | Some em fundo de cor parecida |
| Seletivo (*sel-out*) | Contorno clareia do lado da luz e escurece na sombra | Volume e leveza | Mal aplicado, quebra a linha e cria jaggies |
| Sem contorno | Só contraste de cor | Limpo, moderno | Falha em fundo claro ou parecido |

Os três primeiros tipos e o último estão no [Pixnote](https://pixnote.net/en/learn/character), que recomenda evitar preto puro e usar um cinza muito escuro com leve matiz (o exemplo dele é `#2d3436`). O Pixel Joint alerta que o sel-out só é apropriado quando o fundo é conhecido de antemão, e que sombrear o contorno conforme a luz é outra coisa e causa menos jaggies.

### Contorno interno

Linhas internas separam braço de tronco ou cabeça de cabelo. Use uma cor mais clara que o contorno externo, ou troque a linha por mudança de valor entre as duas áreas. Contorno interno preto em sprite pequeno come pixels preciosos.

### Regra para o app

- Acabamento: contorno automático de 1 pixel a partir da máscara, com tipo escolhido no spec (`preto`, `colorido`, `seletivo`, `nenhum`).
- Limpeza automática de doubles em diagonais.
- Validação `style`: detector de jaggies que percorre o contorno e sinaliza quebra de monotonia nos comprimentos dos segmentos.
- Para sel-out, exigir a direção de luz do spec.

## 5. Cor e paleta

Paleta pequena dá coesão: as mesmas cores repetidas amarram a peça e facilitam ajustes, segundo o [Pixel Joint](https://gwern.net/doc/www/pixeljoint.com/ddfba8b00ecdc232df4936b61575ca99d5aba345.html). O Pixnote sugere 2 a 3 cores por parte (base, sombra, luz) e 6 a 12 cores por personagem.

### Os três eixos

- **Matiz**: a identidade da cor.
- **Saturação**: a intensidade. Saturação muito alta cansa a vista em tela.
- **Valor (luminosidade)**: claro ou escuro. A paleta precisa de faixa larga de valor para ter contraste.

### Rampas

Rampa é um grupo de cores ordenado do escuro ao claro. Rampas podem compartilhar a cor mais escura e a mais clara, e um meio-tom pode servir a duas rampas, o que economiza cores. Uma cor que não encaixa na rampa "fura" a imagem, quase sempre por saturação excessiva ou matiz que briga com os vizinhos.

### Hue shifting

Numa rampa boa o matiz também muda, não só o brilho. A convenção é empurrar as luzes para um matiz quente (amarelo) e as sombras para um frio (azul ou roxo). Rampa "reta", que só varia luminosidade, fica chapada.

Receita do [Pixelblog 1, de Raymond Schlitter](https://www.slynyrd.com/blog/2018/1/10/pixelblog-1-color-palettes):

1. **9 amostras por rampa.**
2. **Matiz**: +20° entre amostras vizinhas, 160° no total. Desvio positivo aquece a cor conforme clareia.
3. **Amostra do meio**: a cor mais vibrante que você aceita usar.
4. **Brilho**: sobe de forma constante, começando acima de 0%, com passos menores perto de 100%.
5. **Saturação**: pico no meio, nunca 0% nem 100%; passos maiores nas pontas.
6. **Guarda**: evite saturação alta junto de brilho alto. Cores escuras carregam mais saturação.
7. **Paleta completa**: 8 rampas, cada uma deslocada 45°, fecham o círculo (72 cores).
8. **Neutros**: duplicar a parte central da paleta, dessaturar e usar como cinzas naturais.

O autor não publica os valores exatos de saturação e brilho em texto; eles aparecem só nas imagens. O desvio de 20° é forte e pensado para uma paleta geral. Para a rampa de um único material, 5° a 15° por passo é a faixa de convenção comum.

### Contagem de cores

| Alvo | Cores | Observação |
| --- | --- | --- |
| Sprite 16×16 | 3 a 6 | Uma rampa de 3 por material |
| Personagem 32×32 | 6 a 12 | Faixa do Pixnote |
| Tileset | até 16 | O [Pixelblog 28](https://slynyrd.com/blog/2020/5/21/pixelblog-28-side-view-tiles) usa 16 e considera suficiente |
| Jogo inteiro | 16 a 64 | Convenção comum; uma paleta-mestra compartilhada |

### Paletas de referência

Paletas públicas conhecidas para cadastrar por nome: Game Boy (4 tons de verde), PICO-8 (16), DawnBringer 16 e 32, Endesga 32, AAP-64, Sweetie 16, Resurrect 64. Os valores hexadecimais devem ser copiados do banco de paletas do Lospec na hora de montar o arquivo, e não digitados de memória.

### Erros de cor

- **Sombra = base + preto.** Fica suja. Sombra desloca o matiz e costuma ganhar saturação.
- **Luz = base + branco.** Fica lavada. Luz desloca para o quente e perde saturação.
- **Passos de valor iguais demais.** Cores vizinhas na rampa precisam se distinguir a olho; se não, uma delas sobra.
- **Cores quase idênticas** deixadas por ferramenta automática. Fundir.

### Regra para o app

- Conhecimento: `paletas.yaml` com paletas nomeadas e rampas já marcadas por material (pele, metal, madeira, folha, pedra, tecido).
- Acabamento: gerador de rampa com hue shift a partir de uma cor-base, com os parâmetros acima.
- Validação `hard`: total de cores dentro do limite do spec. Validação `style`: rampa reta (matiz constante), pares de cores com distância perceptual mínima, saturação e brilho altos ao mesmo tempo.

## 6. Luz e sombreamento

Sombra descreve volume a partir de uma fonte de luz; sombra que só acompanha o contorno é o erro chamado *pillow shading*. O [Pixel Joint](https://gwern.net/doc/www/pixeljoint.com/ddfba8b00ecdc232df4936b61575ca99d5aba345.html) o define como faixas escuras concêntricas que seguem a borda e ignoram a luz, descrevendo forma plana em vez de tridimensional.

### Fonte de luz

- **Uma direção para o jogo inteiro.** A convenção comum é luz de cima e da esquerda, ou de cima e da direita. Todos os assets seguem a mesma.
- **Luz de cima** é a escolha segura para tiles que serão espelhados: o [Pixelblog 28](https://slynyrd.com/blog/2020/5/21/pixelblog-28-side-view-tiles) lembra que só dá para espelhar esquerda e direita se a luz for simétrica.
- Luz frontal pode funcionar, desde que a forma seja respeitada.

### Volumes básicos

Todo objeto se reduz a esfera, cilindro, cubo e cone. Para cada um:

- **Esfera**: luz num ponto deslocado para a fonte, meio-tom em crescente, sombra no lado oposto, luz rebatida fina na borda da sombra.
- **Cilindro**: faixas paralelas ao eixo, com a mais clara deslocada para a luz.
- **Cubo**: um valor por face. Topo mais claro, face voltada à luz média, face oposta escura.
- **Cone**: como o cilindro, com as faixas convergindo.

### Quantos tons

- 16×16: 2 tons por material (base e sombra), luz só em material brilhante.
- 32×32: 3 tons (sombra, base, luz).
- 48×48 ou mais: 4 a 5 tons, com luz rebatida.

Estes números são convenção comum, coerentes com as "2 a 3 cores por parte" do Pixnote.

### Banding

Banding acontece quando pixels vizinhos terminam na mesma coordenada, e a grade fica aparente. O Pixel Joint lista quatro formas:

- **Hugging**: uma faixa corre paralela à forma que envolve, com as pontas alinhadas.
- **Fat pixels**: quadrados ou linhas grossas que saltam à vista.
- **Skip-one**: fileiras separadas por um vão ainda se leem como faixa.
- **45°**: degraus diagonais de 1 pixel alinhados entre si.

Uma [pesquisa da TU Delft](https://repository.tudelft.nl/file/File_65d43acd-9779-4eab-999b-9bcd4f0a96a9) usa uma definição mensurável: dois segmentos de cores diferentes, adjacentes, com os extremos alinhados no mesmo eixo. Essa definição serve direto como métrica para o validador.

### Materiais

- **Metal**: contraste alto, luz quase branca ao lado de sombra escura, reflexo em faixa.
- **Tecido**: transição suave, pouco contraste, sombra nas dobras.
- **Madeira**: veios como linhas curtas quebradas, não riscos contínuos.
- **Pedra**: planos facetados com valores distintos.
- **Pele**: sombra puxada para o vermelho ou roxo, luz para o amarelo.

### Sombra projetada

Sombra no chão ancora o objeto. Em visão de cima 3/4, é uma elipse escura sob os pés. Costuma ser um sprite separado, para o jogo controlá-la.

### Regra para o app

- Spec: campo `luz.direcao` no nível do projeto, herdado por todo asset.
- Acabamento: sombreamento automático por volume, usando a forma declarada de cada camada (esfera, cilindro, caixa).
- Validação `style`: contador de pares de segmentos em banding; detector de pillow shading (faixas que repetem o contorno em todos os lados).

## 7. Anti-aliasing manual e dithering

As duas técnicas são opcionais, e em sprites pequenos de jogo o padrão mais seguro é não usar nenhuma. O guia de [anti-aliasing do Pixel Parmesan](https://pixelparmesan.com/anti-aliasing-fundamentals-for-pixel-artists) diz que em sprites pequenos o AA tende a virar ruído e que iniciantes podem dispensá-lo.

### Anti-aliasing (AA) manual

AA é colocar à mão pixels de cor intermediária para suavizar um degrau.

- **Cor intermediária pelo valor.** Um quadrado 50% coberto pede um valor no meio entre linha e fundo; 25% coberto, um quarto do caminho.
- **Não tire a média das duas cores.** Pode ficar barrento, sobretudo com cores complementares. Use um matiz vizinho já existente no sprite.
- **Segmento longo pede AA longo.** Para degraus compridos, empilhe dois ou mais tons em trechos de comprimentos diferentes.
- **Dentro da silhueta, não na borda externa.** AA na borda de um sprite de jogo fica errado sobre fundo desconhecido. Se for preciso, use pixels semitransparentes, o que o autor reserva para efeitos.
- **Cuidado com banding.** Trechos de AA do mesmo comprimento, paralelos à borda, reforçam a grade.

O Pixel Joint nomeia os três erros: AA demais (borda borrada), AA de menos (um único pixel que não suaviza) e AA em banding.

Como o AssetFlow exige alpha binário, AA externo com transparência está fora. AA interno é permitido, desde que use cores da paleta.

### Dithering

Dithering alterna duas cores em padrão para sugerir uma terceira.

| Padrão | Como é | Uso |
| --- | --- | --- |
| 50% (xadrez) | Alterna pixel a pixel | O mais comum |
| 25% e outros | Pontos mais espaçados | Transição mais fina, porém mais visível |
| Estilizado | Padrão com pequenas formas | Textura decorativa |
| Entrelaçado | Duas regiões se trançam na fronteira | Degradês |
| Aleatório | Pixels soltos espalhados | Em geral, evitar |

A lista é do [Pixel Joint](https://gwern.net/doc/www/pixeljoint.com/ddfba8b00ecdc232df4936b61575ca99d5aba345.html), que dá duas regras: dither bom afina a borda de uma área sólida, e se o dither cobre metade do sprite é melhor acrescentar uma cor. Quanto menor o contraste entre as duas cores, menos áspero o resultado.

O guia de [dithering do Pixel Parmesan](https://pixelparmesan.com/dithering-for-pixel-artists) acrescenta:

- **Evite em sprites muito pequenos e em personagens animados**: não há pixels para sustentar o padrão.
- **Dither amolece a borda** e pode borrar formas já definidas.
- **Fica mais óbvio quando ampliado.** O tamanho final de exibição entra na decisão.
- **Serve bem** a trabalho de 1 bit ou pouquíssimas cores, a céus e fundos grandes, e a efeitos intencionais como sujeira.

O autor diz que quase nunca usa dithering no próprio trabalho. É uma posição de estilo, não uma regra técnica: muita pixel art clássica usa dither com ótimo resultado.

Em animação, dither que muda de posição entre frames cintila. Se houver dither num sprite animado, o padrão deve ficar ancorado à grade.

### Regra para o app

- Padrão do spec: `aa: nenhum`, `dithering: nenhum` para personagens e props até 32×32.
- Liberar `dithering: xadrez` para fundos, céus e tiles grandes, com teto de área (por exemplo 15%, a calibrar).
- Validação `hard`: nenhuma cor fora da paleta, alpha só 0 ou 255.
- Validação `style`: proporção de área em padrão xadrez; pixels isolados fora de padrão.

## 8. Clusters e limpeza

Um pixel isolado é ruído; pixels devem se agrupar em blocos da mesma cor que formam áreas sólidas. Essa é a definição de *cluster* do [Pixel Joint](https://gwern.net/doc/www/pixeljoint.com/ddfba8b00ecdc232df4936b61575ca99d5aba345.html), que nota que a borda de um cluster define a forma do vizinho: mexer em um altera os dois.

### Quando o pixel solto é legítimo

- Brilho especular forte.
- Detalhe essencial em sprite minúsculo: olho, botão, estrela.
- Pixel de transição encostado num cluster, que se lê como parte dele.

Isso confirma a regra que o Pixel Optimizer já segue: um pixel isolado cuja cor aparece em quantidade no sprite pode ser vocabulário do desenho e fica preservado.

### O que limpar

| Defeito | Como reconhecer | Correção |
| --- | --- | --- |
| Pixel órfão | Nenhum vizinho da mesma cor nos 8 lados | Fundir à cor vizinha dominante, salvo exceção acima |
| Double | Canto engrossado numa diagonal de 1 pixel | Remover o pixel interno |
| Cluster fino demais | Tira de 1 pixel de cor entre duas áreas | Engrossar ou absorver |
| Cores quase iguais | Dois tons indistinguíveis | Fundir num só |
| Buraco | Pixel transparente dentro da silhueta | Preencher |
| Sujeira externa | Pixel opaco solto fora da silhueta | Apagar |
| Contorno quebrado | Falha de 1 pixel na linha | Fechar |

### Formato dos clusters

- Prefira formas orgânicas com borda de comprimentos variados a retângulos perfeitos.
- Evite "escadinhas" regulares na fronteira entre dois tons, que viram banding.
- Em animação, cada frame tem de passar no teste: o [Pixelblog 8](https://www.slynyrd.com/blog/2018/8/19/pixelblog-8-intro-to-animation) alerta que o loop expõe qualquer pixel fora do lugar e que movimento fluido não esconde cluster fraco.

### Regra para o app

- O Optimizer já cobre órfão, contorno e paleta. Acrescentar: doubles, buracos internos, sujeira externa e fusão de cores quase iguais.
- Manter a regra "otimizar não pode piorar": toda limpeza passa pela comparação de nota antes e depois.
- Registrar cada pixel preservado e o motivo, como hoje em `RepairPlan.declined`.

## 9. Personagens

Quanto menor o canvas, maior a cabeça em relação ao corpo. Sprites pequenos usam proporção "chibi" porque o rosto precisa de pixels para ter olhos legíveis.

### Proporção por tamanho

| Canvas | Altura em cabeças | Olho | Largura do braço |
| --- | --- | --- | --- |
| 8×8 | 1 a 1,5 | 1×1 | sem braço separado |
| 16×16 | 2 a 3 | 1×1, 1×2 ou 2×1 | 1 px |
| 24×24 | 2,5 a 3,5 | 1×2 ou 2×2 | 1 a 2 px |
| 32×32 | 3 a 4 | 2×2 com brilho de 1 px | 2 px |
| 48×48 ou mais | 4 a 6 | 3×3 ou mais, com íris e pálpebra | 3 px ou mais |

Proporções e olhos vêm do [Pixnote](https://pixnote.net/en/learn/character), que também fixa o braço de 1 pixel em 16×16. As demais larguras de braço são extrapolação e devem ser testadas.

### Rosto e expressão

As expressões partem de um rosto-base e mudam só olhos, sobrancelhas e boca:

- **Neutro**: olhos 2×2, boca de 1 a 2 pixels.
- **Feliz**: olhos fechados em linha, boca para cima.
- **Triste**: sobrancelha interna erguida, boca para baixo.
- **Bravo**: sobrancelhas em V, olhos menores.
- **Surpreso**: olhos maiores, boca redonda.

Deslocar um olho 1 pixel muda a expressão inteira; por isso o rosto é a última coisa que o acabamento automático deve tocar.

### Tipo de corpo

O terceiro eixo do spec (`character.body_type`) muda a silhueta-base:

- **Humanóide**: vertical, cabeça no topo, dois braços, duas pernas.
- **Quadrúpede**: horizontal, cabeça na frente, quatro apoios, canvas mais largo que alto.
- **Voador**: asas dominam a silhueta; corpo pequeno.
- **Serpentino ou sem membros**: uma curva em S.
- **Amorfo** (slime): massa com base larga.

### Vistas

- **Frontal**: a mais simples e simétrica; pose de espera clássica de RPG.
- **3/4**: leve ângulo, mais natural.
- **Lateral**: padrão de jogos de ação e de ciclos de caminhada.

### Direções em visão de cima

- **4 direções**: baixo, esquerda, direita, cima. Esquerda e direita podem ser espelho uma da outra se o personagem for simétrico.
- **8 direções**: acrescenta as diagonais. O [Pixelblog 56](https://www.slynyrd.com/blog/2025/5/23/pixelblog-56-top-down-character-attack-animation) trabalha com um molde de 8 direções com espera e corrida.
- Espelhar economiza trabalho, mas inverte detalhes assimétricos (espada na mão direita, tapa-olho). O spec deve dizer se o espelhamento é permitido.

### Consistência entre personagens

- Mesma altura de olhos e mesma linha de chão em todo o elenco.
- Mesmo tipo de contorno e mesma direção de luz.
- Mesma paleta-mestra.
- Detalhes cosméticos mínimos, em especial dobras de roupa: o [Pixelblog 50](https://www.slynyrd.com/blog/2024/5/24/pixelblog-50-human-walk-cycle) avisa que são caros de animar com consistência.

### Regra para o app

- Conhecimento: `proporcoes.yaml` com a tabela acima por `body_type` e tamanho, mais as silhuetas-base.
- Conhecimento: `expressoes.yaml` com as diferenças de pixels por expressão sobre o rosto-base.
- Acabamento: geração das direções espelhadas quando `espelhamento: permitido`.
- Validação `semantic`: canvas mais largo que alto para quadrúpede; linha de chão na mesma coordenada.

## 10. Props, itens e ícones

Um prop precisa ser reconhecido em um relance e ocupar bem o canvas. Diferente do personagem, ele raramente é animado, então pode gastar mais pixels em material e textura.

### Práticas gerais

- **Um objeto, uma ideia.** Espada, poção, baú. Nada de cena dentro do ícone.
- **Diagonal aproveita o canvas.** Armas longas (espada, lança, cajado) desenhadas a 45° cabem maiores num quadrado e usam um ângulo de linha perfeito.
- **Margem de 1 pixel** entre o objeto e a borda, para o contorno não ser cortado e o item não colar no vizinho numa grade de inventário.
- **Mesma projeção do jogo.** O [Pixelblog 21](https://www.slynyrd.com/blog/2019/9/18/pixelblog-21-top-down-objects) pede que todos os objetos sigam as mesmas regras de projeção; nele, quase todos cabem num tile de 16×16.
- **Escala coerente com o personagem.** Um baú bate na cintura, uma porta é mais alta que o herói.

### Por categoria

| Categoria | O que define a leitura | Cuidado |
| --- | --- | --- |
| Armas | Silhueta da lâmina ou da ponta; guarda e punho em cor contrastante | Lâmina com 2 a 3 tons de metal e um fio de luz |
| Poções e frascos | Forma do vidro e cor do líquido | Brilho de 1 a 2 pixels no vidro; líquido não enche até a rolha |
| Baús e caixas | Tampa, faixa de metal, fechadura | Versões fechado e aberto com a mesma base |
| Comida | Cor saturada e forma icônica | Evitar marrom sobre marrom |
| Moedas e gemas | Brilho e faceta | Alto contraste; ótimas candidatas a animação de giro |
| Móveis e decoração | Topo visível na projeção 3/4 | Sombra projetada para ancorar |
| Vegetação | Massa da copa em clusters, tronco curto | Copa não é círculo perfeito |

A tabela reúne convenções comuns de arte de jogos; não vem de uma fonte única.

### Ícones de interface

- Tamanhos usuais: 8×8, 16×16, 24×24, 32×32.
- Contorno mais forte que o de um prop de cenário, porque o ícone fica sobre painéis de cor variável.
- Consistência de família: mesmo ângulo, mesma espessura de linha, mesma luz em todo o conjunto.
- Estados (normal, selecionado, desabilitado) como variações de paleta do mesmo desenho.

### Raridade e variação

Jogos costumam diferenciar versões de um item por troca de paleta: espada de ferro, de ouro, de cristal. O desenho fica igual e a rampa do material muda. É a variação mais barata que existe.

### Regra para o app

- Conhecimento: `props.yaml` com a tabela por categoria e a orientação padrão (45° para armas longas).
- Acabamento: troca de rampa por material para gerar variantes sem novo desenho.
- Validação `semantic`: margem de 1 pixel respeitada; ocupação mínima do canvas.

## 11. Tiles e tilesets

Um tile precisa se repetir sem que a emenda ou o padrão apareçam. O tamanho padrão é 16×16; o [Pixelblog 28](https://slynyrd.com/blog/2020/5/21/pixelblog-28-side-view-tiles) recomenda tile quadrado, de dimensão par, de preferência potência de 2.

### Repetição sem emenda

As práticas abaixo vêm do [Pixelblog 20](https://www.slynyrd.com/blog/2019/8/27/pixelblog-20-top-down-tiles):

- **Desenhar em modo ladrilhado**, vendo as cópias vizinhas em tempo real.
- **Clusters atravessam a borda** e continuam do lado oposto, para nenhuma borda parecer corte.
- **Peso visual distribuído.** Nenhuma região do tile domina; um elemento chamativo vira um "ponto" repetido no mapa.
- **Poucos clusters-chave repetidos**, sem que dois se toquem lado a lado. Encostar pelo canto pode.
- **Poucas cores.** Cores demais borram a textura, e contraste forte dentro do padrão vira ruído.
- **Nunca duas texturas agitadas lado a lado.** Espaço negativo descansa o olho.

Para o app, o teste de emenda é mecânico: montar uma grade 3×3 do tile e verificar se a fronteira tem a mesma estatística de cor e de contraste que o interior.

### Variantes

Um conjunto bem feito precisa de poucas variantes, mas todo tile muito repetido merece ao menos uma. Espelhar tiles cria orientações novas, desde que a luz seja simétrica.

### Autotile

Autotile é o sistema em que o jogo escolhe a peça certa olhando os vizinhos. Os esquemas abaixo estão descritos em um [artigo do Red Blob Games](https://www.redblobgames.com/articles/autotile/claude/):

| Técnica | Tiles | Cantos internos | Indicado para |
| --- | --- | --- | --- |
| Máscara de 4 bits | 16 | Não | Protótipo, estilos simples |
| Blob de 8 bits | 47 | Sim | Jogos 2D polidos |
| Grade dupla | 16 | Sim | Transições suaves de terreno |
| Mini-tiles 2×2 | 5 formas | Sim | Estilo RPG Maker |

**4 bits**: Norte = 1, Leste = 2, Sul = 4, Oeste = 8. Soma-se o valor de cada vizinho igual e o resultado (0 a 15) indexa o tile.

**8 bits (blob)**: N = 1, NE = 2, L = 4, SE = 8, S = 16, SO = 32, O = 64, NO = 128. Uma diagonal só conta se os dois vizinhos cardeais ao lado dela também forem iguais. Essa regra reduz as 256 combinações a 47 formas distintas.

**Grade dupla**: o dado do terreno fica nos cantos das células, e a grade de exibição é deslocada meio tile. Com dois terrenos são 2⁴ = 16 configurações, já com cantos internos.

Para um gerador, a grade dupla pede 16 desenhos em vez de 47 e dá resultado equivalente. É o melhor custo-benefício para o AssetFlow começar.

### Tiles de plataforma (visão lateral)

- **Topo inclinado**: o tile de chão mostra uma faixa do topo, como em 3/4, para a superfície ter profundidade.
- **Cantos** com inclinação nos dois lados externos.
- **Tiles de acabamento** (grama, plantas) para o topo não ser uma linha reta, com a colisão limpa por baixo.
- **Suportes de plataforma** no plano de fundo imediato, para a plataforma parecer ancorada.
- **Fundo em várias camadas simples**, não uma ou duas muito detalhadas.
- **O fundo nunca compromete a frente.** Detalhe de fundo não pode competir com sprites e objetos interativos.

### Peças mínimas de um terreno

Convenção comum para um conjunto manual de 9 peças: quatro cantos, quatro bordas e o centro, mais quatro cantos internos (13 no total). O blob de 47 e a grade dupla de 16 são as versões completas.

### Regra para o app

- Conhecimento: `tiles.yaml` com as máscaras de bits e os 16 moldes da grade dupla.
- Acabamento: gerar o conjunto de transição a partir de dois tiles-base (interior de A e de B) e de um perfil de borda.
- Validação `hard` para tiles: teste de emenda 3×3.
- Validação `style`: detecção de ponto dominante por análise de repetição.

## 12. Cenários e perspectiva

Todo asset de um jogo segue uma única projeção; misturar projeções é o erro de cenário mais comum. O spec do AssetFlow deve carregar a projeção como campo do projeto.

### Projeções

| Projeção | Como é | Onde se usa |
| --- | --- | --- |
| Lateral | Câmera de lado, sem profundidade | Plataforma, luta, metroidvania |
| De cima (pura) | Câmera a 90°, só se vê o topo | Naves, quebra-cabeças |
| De cima 3/4 | Topo e frente visíveis, sem rotação | RPG clássico, aventura |
| Isométrica | Objeto girado 45°, topo e duas faces visíveis | Estratégia, simulação, construção |

O [Pixelblog 4](https://slynyrd.com/blog/2018/4/12/pixelblog-4-graphical-projection-part-2) descreve a 3/4 de cima como parecida com a isométrica, porém sem a rotação de 45°, e observa que a isométrica é mais difícil em jogos de controle direto e preciso.

### Isométrica em pixel art

- **Linha 2:1.** A cada 2 pixels na horizontal, 1 na vertical. A isometria verdadeira usa 30°, que na grade vira degrau irregular; a linha 2:1 dá cerca de 26,6° e degraus regulares.
- **Tile em losango com largura = 2 × altura**: 16×8, 32×16, 64×32.
- **Verticais continuam verticais.** Só as linhas do plano do chão seguem a 2:1.
- **Um cubo-guia** em arame ajuda a manter personagens e objetos alinhados à grade.
- Espelhar um objeto isométrico troca a face iluminada, então o espelho exige recolorir.

### De cima 3/4

- Objetos mostram o topo e a face da frente. A face lateral não aparece.
- Personagens são desenhados quase de frente, com leve visão de cima; a cabeça cobre parte dos ombros.
- O que está mais abaixo na tela fica na frente (ordenação por Y).
- Paredes têm altura visível; o topo da parede é outro tile.

### Profundidade e parallax (visão lateral)

- **Camadas**: frente de jogo, fundo próximo, fundo médio, fundo distante, céu. O Pixelblog 28 considera que poucas camadas com sobreposição e contornos sutis bastam.
- **Perspectiva atmosférica**: quanto mais longe, menos contraste, menos saturação e matiz puxado para a cor do céu.
- **Menos detalhe ao fundo.** Formas maiores e mais simples.
- **Velocidade de parallax** proporcional à distância; a camada mais distante quase não se move.
- **Camadas repetíveis** na horizontal passam pelo mesmo teste de emenda dos tiles.

### Composição de um fundo

- Faixa de valor reservada: o fundo usa os valores médios e deixa os extremos (mais claro e mais escuro) para personagens e objetos interativos.
- Dithering é aceitável em céus e degradês grandes (ver seção 7).
- Linha do horizonte fora do centro exato.

### Regra para o app

- Spec: `projecao` como campo do projeto (`lateral`, `cima`, `cima_3_4`, `isometrica`), herdado por todo asset.
- Conhecimento: `projecoes.yaml` com razões de linha, formato do tile e faces visíveis por projeção.
- Acabamento: geração das camadas de parallax com redução automática de contraste e saturação por distância.
- Validação `semantic`: em isométrica, checar que as arestas do chão seguem 2:1 e que o tile tem largura dupla da altura.

## 13. Animação: princípios

Em pixel art, a energia do movimento vale mais que a suavidade, e frames demais deixam a ação mole. Essa é a tese do [Pixelblog 8](https://www.slynyrd.com/blog/2018/8/19/pixelblog-8-intro-to-animation), que lembra que jogos de 8 bits usavam só os quadros-chave.

### Quadros-chave e intermediários

- **Quadros-chave** são as poses mais dramáticas, que resumem o movimento. A animação deve se ler só com eles.
- **Intermediários** preenchem os vãos. Entram depois, e só os necessários.
- **Ordem de trabalho**: poses-chave, teste de tempo, intermediários, limpeza de clusters em cada frame.

### Taxa de quadros

| Faixa | Sensação | Uso |
| --- | --- | --- |
| 4 a 6 fps | Lento, relaxado | Espera, efeitos de ambiente |
| 8 a 12 fps | Padrão de pixel art | Caminhada, ações gerais |
| 15 a 24 fps | Fluido, rápido | Efeitos de golpe, cenas rápidas |

Faixas do [Pixnote](https://pixnote.net/en/learn/animation), que sugere por ação: espera a 6 fps, caminhada a 8, ataque a 10 a 12. A mesma fonte registra que sprites de NES e SNES atualizavam a 4 a 8 fps.

Mais importante que a taxa global é a **duração por frame**: cada frame tem seu tempo em milissegundos. Um golpe usa frames de 40 a 60 ms no impacto e de 120 a 200 ms na preparação (valores de convenção comum). O Pixelblog 8 dá um par verificado: ciclo de corrida de 8 frames a 80 ms por pose, e o de 4 frames a 160 ms, para a energia ficar igual quando se cortam frames.

### Os princípios clássicos na grade

- **Antecipação**: agachar antes do pulo, recuar o braço antes do golpe. Avisa o jogador do que vem.
- **Esticar e achatar**: 1 pixel já funciona. O volume se conserva: se alarga, perde altura.
- **Aceleração e desaceleração**: devagar nas pontas, rápido no meio. Em pixel art se faz com a duração dos frames e com o deslocamento em pixels entre eles.
- **Continuidade e sobreposição**: cabelo, capa e cauda seguem 1 frame atrasados e passam do ponto antes de assentar.
- **Arcos**: mãos, pés e armas percorrem curvas, não retas.
- **Ação secundária**: piscar, mexer a orelha, balançar o cinto.
- **Exagero**: o Pixelblog 9 sugere alongar o braço ou a arma no ponto de extensão máxima.
- **Pose clara**: cada quadro-chave passa no teste da silhueta.

### Movimento sub-pixel

Quando a forma não pode andar 1 pixel inteiro (uma respiração num sprite de 16 pixels), move-se a **cor** em vez do contorno: a faixa de luz desce 1 pixel dentro da forma, o tom do meio avança, e o olho lê um deslocamento menor que a grade. O [Pixel Parmesan](https://pixelparmesan.com/anti-aliasing-fundamentals-for-pixel-artists) define a técnica como aplicar anti-aliasing ao longo dos frames, e a considera mais útil em sprites pequenos ou em detalhes pequenos.

### Frames de borrão (smear)

Num movimento muito rápido, um único frame estica o objeto ao longo da trajetória e liga a pose inicial à final. O [Pixelblog 9](https://slynyrd.com/blog/2018/9/8/pixelblog-9-melee-attacks) resume: borrões devem ser poucos e rápidos, e em geral um só basta. O rastro de uma espada é um arco na cor mais clara da lâmina, que some no frame seguinte.

### Loops

- O último frame leva ao primeiro sem salto. Não se duplica o primeiro frame no fim.
- Ciclos simétricos (caminhada) reaproveitam a primeira metade espelhando braços e pernas.
- Modos de reprodução: em frente, reverso e vai-e-volta. O vai-e-volta dobra a duração aparente sem frames novos e serve bem à respiração.

### Consistência entre frames

- **Volume constante.** O personagem não engorda nem encolhe de um frame para outro, salvo em esticar e achatar.
- **Paleta idêntica** em todos os frames.
- **Pés na mesma linha** e canvas fixo.
- **Luz fixa.** A sombra não muda de lado quando o braço se move.
- **Sem pixels que pisquem**: detalhe que aparece num frame e some no outro vira cintilação.

### Regra para o app

- Modelo de dados: animação como lista de frames com `duracao_ms` individual e um `modo_loop`.
- Desenho: o Claude descreve o frame-base e, para os demais, só as diferenças. É a forma mais barata em tokens.
- Validação `hard`: mesmo canvas e mesma paleta em todos os frames.
- Validação `semantic`: variação da área da silhueta entre frames dentro de um limite; linha de chão constante; contagem de pixels que mudam entre frames vizinhos (muito baixa = frame redundante, muito alta = salto).

## 14. Ciclos padrão de personagem

Um personagem jogável básico precisa de espera, caminhada ou corrida, pulo, ataque, dano e morte. A tabela dá o ponto de partida de cada um.

| Animação | Frames (mínimo a confortável) | Tempo por frame | Loop | Fonte do número |
| --- | --- | --- | --- | --- |
| Espera | 2 a 4 | 150 a 250 ms | Sim, vai-e-volta | Frames: Pixnote; tempo: \~6 fps |
| Caminhada | 4 a 8 | 100 a 150 ms | Sim | Pixnote e Pixelblog 50 |
| Corrida | 4 a 8 | 80 ms (8 frames) a 160 ms (4 frames) | Sim | Pixelblog 8 |
| Pulo | 3 a 5 poses | Controlado pela física | Não | Convenção comum |
| Ataque | 4 a 8 | Variável por fase | Não | Pixnote |
| Dano | 1 a 3 | 80 a 120 ms | Não | Convenção comum |
| Morte | 4 a 8 | 100 a 150 ms, último frame fixo | Não | Convenção comum |

### Espera (idle)

O único requisito é haver movimento. A forma mais comum é uma respiração que balança o corpo, e jogos de 8 bits às vezes reutilizam a caminhada de 2 frames, segundo o [Pixelblog 8](https://www.slynyrd.com/blog/2018/8/19/pixelblog-8-intro-to-animation).

- Mudar só 1 a 2 pixels entre frames: o tronco desce 1 pixel, os ombros acompanham, os pés ficam fixos.
- Um piscar de 2 frames a cada poucos ciclos dá vida com custo mínimo.
- A complexidade segue o tamanho do projeto: espera de 8 frames para todo personagem pode ser inviável.

### Caminhada

As quatro poses da primeira metade, pelo [Pixelblog 50](https://www.slynyrd.com/blog/2024/5/24/pixelblog-50-human-walk-cycle):

1. **Contato**: o calcanhar toca o chão, os membros estão no extremo do balanço, o corpo está no ponto mais baixo.
2. **Descida**: o pé assenta e o corpo volta ao centro enquanto o outro pé sai do chão.
3. **Passagem**: as pernas se cruzam no centro, o corpo está no ponto mais alto.
4. **Balanço**: a perna da frente avança ao máximo, ainda no ar.

Os quatro frames seguintes repetem as poses com os lados trocados. O autor considera 8 frames o equilíbrio entre economia e fluidez, mostra versões de 6 e de 4, e trata mais de 8 como escolha estética. A altura da cabeça deve seguir uma onda triangular, não uma senoide perfeita.

Versão mínima do [Pixnote](https://pixnote.net/en/learn/character): 3 desenhos (passagem, pé direito à frente, pé esquerdo à frente) tocados como passagem, direito, passagem, esquerdo, com o corpo subindo ou descendo 1 pixel por passo, pés sempre na mesma linha, a 100 a 150 ms por frame.

Braços balançam em oposição às pernas.

### Corrida

- Poses de passada fortes, com membros estendidos e tronco inclinado para a frente.
- O punho sobe quase como um soco, para dar energia.
- No frame de passagem, os membros ficam junto ao corpo, em posição neutra.
- Há movimento vertical, que cria o quique.
- Para reduzir de 8 para 6 frames, tira-se o frame de recuo. Para 4, tira-se também o ponto alto. Contato e passagem nunca saem.

A versão de 3 frames no estilo Mega Man usa 4 posições no loop, com a passagem repetida.

### Pulo

Poses separadas, escolhidas pelo jogo conforme a velocidade vertical: preparação (agachado), subida (corpo esticado), ápice (encolhido), queda (braços para cima) e aterrissagem (achatado). A preparação costuma ser pulada em jogos de plataforma para o controle responder na hora.

### Ataque

Fases, pelo [Pixelblog 9](https://slynyrd.com/blog/2018/9/8/pixelblog-9-melee-attacks):

1. **Antecipação**: a partir da postura. Armas pesadas têm antecipação e recuperação mais lentas.
2. **Golpe**: em geral um único frame de borrão.
3. **Continuação**: segurada um instante a mais que os outros frames, para dar peso.
4. **Recuperação**: volta à postura, com leve passagem do ponto (o exemplo desloca a postura 1 pixel por 1 frame).

O artigo não dá contagem de frames por fase nem milissegundos. O [Pixnote](https://pixnote.net/en/learn/animation) dá 4 a 8 frames no total, com o golpe em apenas 1 a 2.

O equilíbrio é de jogabilidade: antecipação demais parece atraso de comando, e recuperação demais deixa o personagem preso e vulnerável. Em golpes fortes, congelar o frame de impacto por alguns frames reforça a batida, com moderação.

### Dano e morte

- **Dano**: recuo de 1 a 2 pixels na direção oposta ao golpe, pose encolhida, e um frame todo em branco ou vermelho. O flash costuma ser feito pelo jogo, não desenhado.
- **Morte**: desequilíbrio, queda, assentamento. O último frame fica fixo ou o sprite se desfaz em efeito.

### Quadrúpedes e outras criaturas

Caminhada de quatro apoios tem as patas da frente e de trás defasadas em meio ciclo. Voadores usam ciclo de asa de 3 a 4 frames (cima, meio, baixo, meio). Slimes usam só esticar e achatar em 4 frames. São convenções comuns, a validar com exemplos.

### Regra para o app

- Conhecimento: `animacoes.yaml` com a tabela acima e, por animação e `body_type`, a lista de poses-chave em texto curto.
- A ferramenta MCP entrega só a receita da animação pedida.
- Acabamento: gerar a segunda metade da caminhada por troca de lados; gerar o vai-e-volta da espera.
- Validação `semantic`: frames de contato com os pés na linha de chão; deslocamento vertical dentro de 1 a 2 pixels na espera.

## 15. Efeitos visuais animados

Um efeito começa pequeno, expande de uma vez e se dissipa devagar. O [Pixnote](https://pixnote.net/en/learn/animation) indica 3 a 6 frames para explosões, fumaça e brilhos, com o primeiro frame pequeno e o seguinte já bem maior, para dar impacto.

Pacotes publicados mostram a faixa prática: um [conjunto de explosões no itch.io](https://pimen.itch.io/explosion-effect) usa de 7 a 14 frames em canvas de 32×32 a 64×32, e um [pacote de efeitos](https://rs-pixel-store.itch.io/pixel-explosion-vfx-pack) entrega em 64×64 a 12 fps. Esses dois links são exemplos de mercado vistos apenas nos resultados de busca, não tutoriais.

### Anatomia de um efeito

1. **Antecipação** (opcional): um ponto ou brilho de 1 frame.
2. **Estouro**: a forma atinge o tamanho máximo em 1 a 2 frames, na cor mais clara.
3. **Corpo**: a cor escurece do centro para a borda, a forma se parte.
4. **Dissipação**: pedaços encolhem e somem. É a fase mais longa.

### Por tipo

| Efeito | Forma | Cor ao longo do tempo | Loop |
| --- | --- | --- | --- |
| Explosão | Bola que cresce e se rasga em fumaça | Branco, amarelo, laranja, vermelho, cinza | Não |
| Fogo | Línguas que sobem e se soltam | Amarelo na base, laranja, vermelho na ponta | Sim, 4 a 8 frames |
| Fumaça | Bolhas que sobem, crescem e se desfazem | Cinza que clareia ou escurece até sumir | Sim ou não |
| Faísca e impacto | Traços radiais curtos | Branco para a cor do golpe | Não, 2 a 4 frames |
| Corte de espada | Arco fino na trajetória | Branco que afina e some | Não, 2 a 3 frames |
| Magia | Partículas em órbita ou espiral | Rampa de uma cor saturada | Sim |
| Água e respingo | Gotas em arco, coroa no impacto | Azul claro com brilho branco | Não |
| Poeira de passo | Dois ou três tufos baixos | Tom do chão, mais claro | Não, 3 a 4 frames |

Formas e cores são convenção comum de arte de efeitos; as contagens de frames seguem a faixa do Pixnote, com loops um pouco mais longos.

### Práticas

- **Efeito usa cores mais claras e saturadas** que personagens e cenário, para se destacar.
- **Sem contorno**, em geral. O efeito é luz, não objeto.
- **Formas irregulares.** Círculo perfeito parece balão, não explosão.
- **Dissipar por buracos**: a fumaça some abrindo furos por dentro, não só encolhendo.
- **Semitransparentes só aqui.** O Pixel Parmesan cita efeitos como o caso em que pixels semitransparentes ajudam. Se o AssetFlow quiser isso, será uma exceção explícita ao alpha binário, restrita ao tipo `effect`.
- **Efeito é sprite separado** do personagem, para o jogo posicionar, girar em 90° e reutilizar.
- **Loop de fogo**: os frames deslocam as línguas para cima; o último emenda no primeiro.

### Regra para o app

- Conhecimento: `efeitos.yaml` com a anatomia em 4 fases e a tabela por tipo, incluindo a rampa de cor temporal.
- Acabamento: geradores procedurais para os efeitos mais regulares (faísca radial, poeira, anéis de impacto), sem custo de tokens.
- Spec: `effect` é o único tipo que pode declarar `alpha: parcial`.
- Validação `semantic`: área do efeito cresce rápido e decresce devagar; último frame de efeito sem loop termina vazio ou quase.

## 16. Spritesheets e exportação

Uma spritesheet é uma grade de frames do mesmo tamanho, acompanhada de um arquivo de metadados que diz onde cada frame está e quanto dura. As regras de layout abaixo vêm do Pixnote ([personagens](https://pixnote.net/en/learn/character) e [animação](https://pixnote.net/en/learn/animation)).

### Layout

- **Todo frame no tamanho cheio do canvas**, incluindo o espaço vazio.
- **Uma linha por ação ou direção**, frames em ordem de reprodução nas colunas. Ordem usual das direções: baixo, esquerda, direita, cima.
- **O pixel mais baixo do pé na mesma linha** em todos os frames.
- **PNG com fundo transparente.**
- Tamanho do frame e taxa são configurados no motor do jogo, ou lidos dos metadados.

### Espaçamento e vazamento

Quando o motor do jogo filtra ou reduz a textura, a cor de um frame pode vazar para o vizinho. As defesas usuais:

- **Espaçamento** de 1 a 2 pixels transparentes entre frames.
- **Extrusão**: repetir a cor da borda de cada frame no espaçamento, a opção mais segura para tiles.
- **Filtro "nearest" e sem mipmaps** no motor, que resolve a maior parte dos casos em pixel art.

Este trecho é convenção comum de ferramentas como Aseprite e TexturePacker. A página de documentação que eu abriria para confirmar os nomes exatos das opções não carregou, então os valores devem ser conferidos na ferramenta antes de virar padrão do app.

O Pixnote recomenda empacotar sem vãos. As duas orientações servem a casos diferentes: sem vão é mais simples de fatiar por grade; com espaçamento é mais seguro contra vazamento. O app deve oferecer as duas e gravar a escolha nos metadados.

### Metadados

Um JSON por spritesheet, com o mínimo:

```json
{
  "imagem": "heroi.png",
  "frame": {"largura": 32, "altura": 32},
  "espacamento": 0,
  "pivo": {"x": 16, "y": 31},
  "animacoes": {
    "espera":    {"linha": 0, "frames": 4, "duracoes_ms": [200, 200, 200, 200], "loop": "vai_e_volta"},
    "caminhada": {"linha": 1, "frames": 8, "duracoes_ms": [100, 100, 100, 100, 100, 100, 100, 100], "loop": "sim"},
    "ataque":    {"linha": 2, "frames": 5, "duracoes_ms": [140, 50, 50, 110, 120], "loop": "nao"}
  }
}
```

O exemplo é uma proposta de formato para o AssetFlow, não um padrão externo. Os tempos do ataque ilustram frames de duração desigual.

- **Pivô**: o ponto do sprite que o jogo usa como posição. Para personagens, o centro da base dos pés.
- **Caixas de colisão e de golpe** por frame são um acréscimo útil mais adiante.
- Um exportador no formato JSON do Aseprite (frames, duração e marcadores de animação) abre a porta para Godot, Unity e Phaser, que já têm importadores para ele.

### Formatos de saída

| Saída | Para quê |
| --- | --- |
| PNG do asset | O arquivo real, 1 pixel lógico = 1 pixel |
| PNG de preview ampliado | Visualização; nunca vai para o jogo |
| Spritesheet PNG + JSON | Animações |
| GIF | Prévia animada para revisão. O Pixnote cita 20 ms como atraso mínimo de frame em GIF |
| Paleta (.hex ou .gpl) | Reuso em editores |
| ZIP do conjunto | Kit completo com metadados |

### Nomes de arquivo

Padrão sugerido: `tipo_nome_variante_tamanho.png`, tudo em minúsculas e sem acento, como `character_cavaleiro_ouro_32x32.png`.

### Regra para o app

- O `AssetStorageService` grava asset, preview e metadados como artefatos separados.
- Exportador com `espacamento` e `extrusao` configuráveis.
- Validação `hard`: todos os frames com a mesma dimensão; dimensão da folha = frames × tamanho + espaçamentos.

## 17. Erros comuns e checklist de validação

A tabela reúne os defeitos das seções anteriores na forma em que o validador pode tratá-los. A coluna "Classe" usa as classes do `SPEC_CONSTRAINTS` do AssetFlow.

| Defeito | Como detectar | Classe | Correção automática? |
| --- | --- | --- | --- |
| Dimensão diferente do spec | Comparar tamanho do arquivo | hard | Não; reprova |
| Alpha parcial | Valores de alpha fora de 0 e 255 | hard | Sim, por limiar |
| Cores acima do limite | Contar cores únicas | hard | Sim, quantizar para a paleta |
| Cor fora da paleta travada | Comparar com a paleta do spec | hard | Sim, cor mais próxima |
| Emenda visível em tile | Grade 3×3, estatística da fronteira | hard (tiles) | Não |
| Frames de tamanhos diferentes | Comparar dimensões | hard | Não |
| Paleta muda entre frames | Comparar conjuntos de cores | hard | Sim, remapear |
| Canvas vazio ou quase | Ocupação abaixo do mínimo | semantic | Não |
| Sprite encosta na borda | Pixels opacos na linha ou coluna extrema | semantic | Sim, recentrar se houver folga |
| Silhueta em pedaços | Contar componentes conectados | semantic | Parcial, `connect_cluster` |
| Linha de chão varia entre frames | Pixel opaco mais baixo por frame | semantic | Sim, deslocar frame |
| Volume oscila entre frames | Área da silhueta por frame | semantic | Não |
| Pixel órfão | Sem vizinho da mesma cor | style | Sim, com preservação registrada |
| Double em diagonal | Padrão em L no contorno | style | Sim |
| Jaggy | Quebra de monotonia nos segmentos | style | Parcial |
| Banding | Pares de segmentos com extremos alinhados | style | Parcial |
| Pillow shading | Faixas que repetem o contorno em todos os lados | style | Não; avisar |
| Rampa reta | Matiz constante ao longo da rampa | style | Sim, se a paleta não for travada |
| Cores quase iguais | Distância perceptual abaixo do limiar | style | Sim, fundir |
| Dither em excesso | Área em xadrez acima do teto | style | Não; avisar |
| Contorno quebrado | Falha na linha externa | style | Sim, `repair_outline` |
| Buraco interno | Transparente cercado de opaco | style | Sim |

### Erros de processo

- **Detalhar antes de fechar a silhueta.**
- **Começar com cores demais.** O Pixel Joint recomenda começar com canvas e paleta pequenos.
- **Usar ferramenta de borrão, suavização ou degradê automático.**
- **Redimensionar ou girar livremente** depois de pronto.
- **Salvar em JPG.**
- **Misturar densidades de pixel** no mesmo jogo.
- **Animar com frames demais**, perdendo energia.
- **Mudar luz, proporção ou paleta** entre assets do mesmo projeto.

### Checklist de aprovação, em ordem

1. Arquivo: dimensão, PNG, alpha binário.
2. Paleta: contagem e aderência.
3. Silhueta: ocupação, borda, componentes.
4. Limpeza: órfãos, doubles, buracos, contorno.
5. Estilo: jaggies, banding, pillow shading, rampa.
6. Animação: canvas, paleta, chão e volume entre frames.
7. Conjunto: mesma luz, projeção, contorno e paleta-mestra do projeto.

Os quatro primeiros passos o AssetFlow já cobre em boa parte. Os passos 5 a 7 são o que este documento acrescenta.

### O que nenhum validador mede

Se o desenho é bonito, se o personagem tem carisma, se a espada parece espada. Para isso existem duas saídas: o revisor por modelo (já previsto em `optimizer.yaml`) e a sua escolha entre variações.

## 18. Do texto ao código

A base de conhecimento vira uma pasta `backend/config/pixel_knowledge/`, no mesmo molde de `asset_taxonomy/`: só YAML, lida no boot, sem código dentro.

### Arquivos propostos

| Arquivo | Conteúdo | Seções de origem |
| --- | --- | --- |
| `paletas.yaml` | Paletas nomeadas, rampas por material, parâmetros do gerador de rampa | 5 |
| `proporcoes.yaml` | Cabeças, olho e braço por `body_type` e tamanho; folga de canvas | 2, 9 |
| `silhuetas/*.yaml` | Moldes-base em camadas de formas, por tipo de corpo e tamanho | 3, 9 |
| `contorno.yaml` | Tipos de contorno e cor de linha por estilo | 4 |
| `luz.yaml` | Direções de luz, tons por tamanho, regras por material | 6 |
| `props.yaml` | Orientação, margem e pontos de leitura por categoria | 10 |
| `tiles.yaml` | Máscaras de autotile, moldes de grade dupla, peças por terreno | 11 |
| `projecoes.yaml` | Razões de linha, formato de tile e faces visíveis | 12 |
| `animacoes.yaml` | Frames, durações, loop e poses-chave por animação e corpo | 13, 14 |
| `efeitos.yaml` | Fases, formas e rampa temporal por efeito | 15 |
| `validacao.yaml` | Limiares de cada verificação da seção 17 | 17 |
| `olhar.yaml` | A lista de verificação do olhar, por forma, cada pergunta com a seção e a regra de origem (Fase B2 do plano do app, [OLHAR.md](OLHAR.md)) | 3, 4, 6, 8, 9, 10, 17 |

### Como o conhecimento chega ao desenhista

1. O pedido é resolvido no `FinalResolvedSpec`, como hoje.
2. Um seletor monta o **recorte** que vale para aquele spec: a linha de proporção, a paleta, o molde-base, a receita da animação.
3. A ferramenta MCP devolve o spec com esse recorte, em poucas linhas.
4. O Claude desenha em camadas sobre o molde e envia.
5. O app aplica acabamento, Optimizer e validação, e devolve o laudo em texto.

O recorte é o que mantém o custo baixo: o documento inteiro nunca entra na conversa, só as dez ou vinte linhas daquele pedido.

### Exemplo de entrada

```yaml
# proporcoes.yaml
humanoide:
  "16x16": {cabecas: 2.5, olho: [1, 2], braco_px: 1, tons_por_material: 2}
  "32x32": {cabecas: 3.5, olho: [2, 2], braco_px: 2, tons_por_material: 3}
quadrupede:
  "32x32": {canvas: [40, 32], cabeca_frente: true, tons_por_material: 3}
```

```yaml
# animacoes.yaml
caminhada:
  humanoide:
    frames: 8
    duracao_ms: 100
    loop: sim
    poses: [contato, descida, passagem, balanco]
    espelhar_segunda_metade: true
    deslocamento_vertical_px: 1
```

Os valores dos exemplos são ilustrativos e saem das tabelas das seções 9 e 14. A linha do quadrúpede é uma suposição a testar.

### Regras de arquitetura a respeitar

- **Nada disso entra numa gaveta.** O conhecimento mora na estante, ao lado de `assetflow/pixel/`.
- **O conhecimento não recalcula o spec.** Ele lê `context.resolved` e acrescenta orientação; tamanho, paleta e tipo continuam vindo só do `FinalResolvedSpec`.
- **Cada regra declara a classe** (`hard`, `semantic`, `style`), para a tela não dar o mesmo peso a tudo.
- **Limiares em `validacao.yaml`**, nunca no código, para calibrar sem mexer em `.py`.

### Ordem de construção sugerida

1. `paletas.yaml` e `proporcoes.yaml`, com um molde humanóide 32×32 e um prop 32×32.
2. Acabamento automático: contorno, espelho, sombra por volume.
3. Verificações de estilo: doubles, jaggies, banding.
4. `animacoes.yaml` com espera e caminhada, e o modelo de frames com duração.
5. Tiles com grade dupla e teste de emenda.
6. Efeitos procedurais.

### O que precisa de calibração com exemplos reais

- Todos os limiares numéricos da seção 17.
- Larguras de braço e tons acima de 16×16.
- Tempos por frame marcados como convenção comum.
- Regras de quadrúpedes, voadores e criaturas sem membros.

Uma boa forma de calibrar é rodar o validador sobre 20 a 30 sprites de pacotes livres de boa qualidade e ajustar os limiares até que eles passem e os sprites ruins do SDXL-Turbo reprovem.

## 19. Fontes consultadas

Páginas abertas e lidas nesta pesquisa, em 25 de novembro de 2026:

| Fonte | Usada para |
| --- | --- |
| [The Pixel Art Tutorial, de cure (Pixel Joint, cópia arquivada)](https://gwern.net/doc/www/pixeljoint.com/ddfba8b00ecdc232df4936b61575ca99d5aba345.html) | Clusters, AA, jaggies, dithering, banding, pillow shading, sel-out, rampas |
| [Pixelblog 1: Color Palettes, de Raymond Schlitter](https://www.slynyrd.com/blog/2018/1/10/pixelblog-1-color-palettes) | Receita de rampa e paleta |
| [Pixelblog 4: Graphical Projection Part 2](https://slynyrd.com/blog/2018/4/12/pixelblog-4-graphical-projection-part-2) | Projeções, linha 2:1 |
| [Pixelblog 8: Intro to Animation](https://www.slynyrd.com/blog/2018/8/19/pixelblog-8-intro-to-animation) | Quadros-chave, espera, corrida, tempos |
| [Pixelblog 9: Melee Attacks](https://slynyrd.com/blog/2018/9/8/pixelblog-9-melee-attacks) | Fases do ataque, borrão |
| [Pixelblog 20: Top Down Tiles](https://www.slynyrd.com/blog/2019/8/27/pixelblog-20-top-down-tiles) | Tiles sem emenda |
| [Pixelblog 28: Side View Tiles](https://slynyrd.com/blog/2020/5/21/pixelblog-28-side-view-tiles) | Tiles de plataforma, camadas de fundo |
| [Pixelblog 50: Human Walk Cycle](https://www.slynyrd.com/blog/2024/5/24/pixelblog-50-human-walk-cycle) | Poses da caminhada |
| [Anti-Aliasing Fundamentals, Pixel Parmesan](https://pixelparmesan.com/anti-aliasing-fundamentals-for-pixel-artists) | AA manual, sub-pixel |
| [Dithering for Pixel Artists, Pixel Parmesan](https://pixelparmesan.com/dithering-for-pixel-artists) | Dithering |
| [Autotiling, Red Blob Games](https://www.redblobgames.com/articles/autotile/claude/) | Máscaras de autotile |
| [How to Draw Pixel Art Characters, Pixnote](https://pixnote.net/en/learn/character) | Proporções, olhos, contorno, spritesheet |
| [Pixel Art Animation Basics, Pixnote](https://pixnote.net/en/learn/animation) | Taxas de quadros e contagens de frames |

Vistas apenas nos resultados de busca, sem leitura completa: a [pesquisa da TU Delft sobre banding e pillow shading](https://repository.tudelft.nl/file/File_65d43acd-9779-4eab-999b-9bcd4f0a96a9), o [Pixelblog 21](https://www.slynyrd.com/blog/2019/9/18/pixelblog-21-top-down-objects), o [Pixelblog 56](https://www.slynyrd.com/blog/2025/5/23/pixelblog-56-top-down-character-attack-animation) e os dois pacotes de efeitos do itch.io.

### Limites desta pesquisa

- A documentação de exportação do Aseprite não carregou; o trecho sobre espaçamento e extrusão não está confirmado em fonte aberta.
- Tutoriais em vídeo e livros pagos (como *Pixel Logic*, de Michael Azzi, e *Pixel Art for Game Developers*, de Daniel Silber) não foram consultados. São as referências mais completas do assunto e valem a compra para aprofundar.
- Pixnote é um site de ferramenta, não de um artista reconhecido; os números dele batem com as demais fontes, mas têm menos autoridade.
- Quadrúpedes, voadores, isométrico detalhado e efeitos têm cobertura mais fraca e dependem de convenção comum.
- Valores hexadecimais de paletas não foram incluídos, para não serem citados de memória.
