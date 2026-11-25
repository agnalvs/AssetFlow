# Estilos de pixel art — dos consoles antigos aos jogos atuais

Nov 25, 2026 · @Luiza

## 1. Como ler as fichas

Cada estilo deste documento é descrito pelos mesmos campos, para virar um arquivo de configuração do AssetFlow sem reinterpretação. São três grupos de estilos: os definidos pelo hardware, os de limite escolhido e os de direção de arte.

### Os campos da ficha

| Campo | O que registra |
| --- | --- |
| Resolução e tamanhos | Tela, tamanho típico de sprite e de tile |
| Cor | Total de cores, cores na tela, cores por sprite, paleta fixa ou livre |
| Contorno | Preto, colorido, seletivo ou nenhum |
| Luz e sombra | Número de tons, uso de dithering |
| Proporção | Como os personagens costumam ser construídos |
| Assinatura | O que faz o olho reconhecer o estilo |
| O que quebra o estilo | Erros que fazem o desenho parecer de outra época |

### Limite e costume

Em cada ficha, as afirmações se dividem em dois tipos, e a diferença importa para o app:

- **Limite**: o que a máquina permitia. É fato verificável, e vem de documentação técnica. No app vira regra `hard`: um sprite "estilo NES" com cinco cores por bloco está errado.
- **Costume**: como os artistas costumavam trabalhar dentro do limite. Tem exceções e não tem fonte única. No app vira regra `style`, marcada `a_calibrar`, para ser conferida com a medição de referências.

Neste documento, os limites trazem link para a fonte. Os costumes são conhecimento geral de arte de jogos e estão identificados como tal.

### Três avisos

- **Número de cores "na tela" não é número de cores "no sprite".** O Super Nintendo mostrava 256 cores na tela, mas cada sprite usava 15. É o limite por sprite que define a cara do personagem.
- **Muitos jogos burlavam os limites** com truques de programação: trocar a paleta no meio da tela, sobrepor dois sprites para ganhar cores. As fichas registram o limite normal e citam o truque quando ele marcou o estilo.
- **Estilo descreve uma época ou uma escola, não um jogo.** As fichas não reproduzem personagens nem sprites de jogos existentes, e o app não deve fazê-lo.

## 2. Quadro comparativo do hardware

O número que mais define a cara de um estilo é a quantidade de cores por sprite, e ela variou de 1 a 15 entre as máquinas clássicas. A tabela reúne os limites normais de cada uma, sem truques de programação.

| Máquina | Tela típica | Cores totais | Cores na tela | Cores por sprite | Tamanho de sprite | Sprites na tela / por linha |
| --- | --- | --- | --- | --- | --- | --- |
| ZX Spectrum | 256×192 | 15 | 15 | 2 por bloco 8×8 | sem sprites de hardware | não se aplica |
| MSX (TMS9918) | 256×192 | 16 fixas | 16 | 1 | 8×8 ou 16×16 | 32 / 4 |
| Commodore 64 | 320×200 ou 160×200 | 16 fixas | 16 | 1, ou 3 no modo multicor | 24×21 (12×21 multicor) | 8 / 8 |
| NES | 256×240 (224 visíveis) | 64 | 25 | 3 | 8×8 ou 8×16 | 64 / 8 |
| Master System | 256×192 | 64 | 32 | 15 | 8×8 ou 8×16 | 64 / 8 |
| Game Boy | 160×144 | 4 tons | 4 | 3 | 8×8 ou 8×16 | 40 / 10 |
| Game Boy Color | 160×144 | 32.768 | 56 | 3 | 8×8 ou 8×16 | 40 / 10 |
| PC Engine | 256×224 a 256×239 | 512 | 482 | 15 | 16×16 a 32×64 | 64 / 16 |
| Mega Drive | 320×224 | 512 | 61 | 15 | até 32×32 | 80 / 20 |
| Super Nintendo | 256×224 | 32.768 | 256 | 15 | 8×8 a 64×64 | 128 / 32 |
| Amiga (OCS) | 320×200 ou 320×256 | 4.096 | 32 (64 em EHB) | paleta da tela | livre (bitmap) | não se aplica |
| Neo Geo | 320×224 | 65.536 | 3.840 | 15 por tile | 16 de largura, até 512 de altura | 380 / 96 |
| Game Boy Advance | 240×160 | 32.768 | 512 em paletas | 15 ou 255 | 8×8 a 64×64 | 128 |
| PICO-8 (fantasia) | 128×128 | 16 fixas | 16 | 16 | 8×8 | livre |

As fontes de cada linha estão nas fichas das seções 3 a 7. "Cores por sprite" não conta a transparência.

### O que a tabela mostra

- **O salto de 3 para 15 cores por sprite** separa a geração de 8 bits da de 16. É a diferença entre um personagem com pele, roupa e contorno e um personagem com rampas de sombra em cada material.
- **O Master System é a exceção dos 8 bits**: já tinha 15 cores por sprite, mas só 64 cores no total para escolher.
- **Mega Drive e Super Nintendo empatam em cores por sprite** e diferem em quantas cores existem na tela: 61 contra 256. Isso explica o visual mais contrastado de um e mais suave do outro.
- **Sprites pequenos eram regra.** Personagens maiores que 8×16 ou 16×16 eram montados com vários sprites lado a lado, e cada peça podia usar uma paleta diferente.

## 3. Consoles de 8 bits

O estilo de 8 bits nasce de poucas cores por sprite e de sprites minúsculos. Um personagem tem três cores, e toda a leitura depende de silhueta e contraste.

### NES

**Limites**, segundo o [guia de limitações do NES de Noel Berry](https://noelberry.ca/posts/nes/index.html):

- Tela visível de 256×224, com tiles de 8×8.
- 64 cores no console, com 8 paletas ativas: 4 para o fundo e 4 para sprites, cada uma com 3 cores. No máximo 25 cores na tela.
- Cada sprite usa uma paleta: 3 cores mais a transparência.
- No fundo, cada bloco de 2×2 tiles (16×16 pixels) usa uma única paleta.
- Sprites de 8×8 ou 8×16, um modo por jogo. Até 64 na tela e 8 por linha horizontal; pixels transparentes contam.
- Sprites podem ser espelhados, mas não girados nem redimensionados.
- Sobrepor dois sprites dá mais cores a um personagem. O artigo cita Mega Man como exemplo.

O manual do [Pro Motion para NES](https://www.cosmigo.com/promotion/docs/onlinehelp/gfxHardware-NES.htm) observa que a paleta útil fica em torno de 54 cores, porque várias das 64 entradas se repetem.

**Costumes** (conhecimento geral, a calibrar):

- Personagens de 16×16 a 16×32, montados com 4 a 8 sprites.
- As três cores viram: contorno escuro, cor principal e cor de pele ou de destaque.
- Contorno preto ou quase preto, muitas vezes aproveitando o fundo preto.
- Sem rampa de sombra: cada material tem um tom só.
- Cores saturadas, tiradas direto da paleta do console.

**Assinatura**: três cores por personagem, blocos de cor chapada, cabeça grande.

**O que quebra o estilo**: mais de 3 cores num sprite, sombra em degradê, anti-aliasing, cor fora da paleta do console, fundo com mais de 3 cores num bloco de 16×16.

### Master System

**Limites**, pelas [especificações no Sega Retro](https://segaretro.org/Sega_Master_System/Technical_specifications):

- Paleta de 64 cores (6 bits), com até 32 na tela: 16 para o fundo e 16 para sprites.
- 16 cores por tile e por sprite.
- 64 sprites na tela, 8 por linha sem piscar, em 8×8 ou 16×16.

A [comparação de hardware do mesmo site](https://segaretro.org/Sega_Master_System/Hardware_comparison) resume a diferença para o NES: 15 cores mais transparência por sprite, contra 3.

**Costumes**: sprites com mais tons que os do NES, mas todos tirados de só 64 cores, o que dá um colorido forte e pouco sutil. Como todos os sprites dividem uma única paleta de 16, os personagens de uma mesma tela compartilham cores.

**Assinatura**: cores vivas e "de doce", mais tons por personagem que no NES, sem os meios-tons dos 16 bits.

**O que quebra o estilo**: tons intermediários que a paleta de 64 não tem; mais de 15 cores somando todos os sprites da cena.

### Game Boy

**Limites**, pelos [Pan Docs](https://bgb.bircd.org/pandocs.htm):

- Tela de 160×144, ou 20×18 tiles.
- 4 tons de cinza, esverdeados na tela original.
- Paletas: uma de 4 tons para o fundo e duas de 3 para sprites.
- Sprites de 8×8 ou 8×16, até 40 na tela e 10 por linha.

**Costumes**: como são só 4 tons, tudo se resolve por contraste de valor. O tom mais escuro faz o contorno, o mais claro o fundo ou o brilho, e os dois do meio fazem o corpo. Dithering em xadrez é comum em fundos, para sugerir tons que não existem.

**Assinatura**: monocromia em 4 tons, contorno escuro forte, personagem claro sobre fundo médio.

**O que quebra o estilo**: um quinto tom; matizes diferentes; sprite e fundo com o mesmo valor, que faz o personagem sumir.

### Game Boy Color

**Limites**, pelos mesmos Pan Docs e pela [lista de paletas de consoles](https://en.wikipedia.org/wiki/List_of_video_game_console_palettes):

- Mesma tela e mesmos sprites do Game Boy.
- 32.768 cores possíveis, até 56 na tela: 8 paletas de 4 cores para o fundo e 8 paletas de 3 cores mais transparência para sprites.

**Costumes**: continua o desenho de 3 cores por sprite do NES, mas com liberdade total para escolher as três. Paletas suaves e pastéis, que o NES não tinha. Contorno escuro colorido em vez de preto puro.

**Assinatura**: estrutura de 8 bits com cores de 16 bits.

**O que quebra o estilo**: mais de 3 cores por sprite de 8×16; rampas longas de sombra.

## 4. Consoles de 16 bits

Com 15 cores por sprite, a geração de 16 bits passou a sombrear cada material com uma rampa. É o estilo que a maioria das pessoas chama de "pixel art clássica".

### Super Nintendo

**Limites**, pelas [especificações no Wikibooks](https://en.wikibooks.org/wiki/Super_NES_Programming/SNES_Specs) e pelo [guia de sprites da Mega Cat Studios](https://megacatstudios.com/blogs/retro-development/snes-sprite-engine-design-guidelines):

- Resolução usual de 256×224.
- 32.768 cores possíveis (15 bits), com 256 na tela.
- Sprites de 8×8 até 64×64, cada um com uma de oito paletas de 16 cores (15 mais transparência).
- 128 sprites na tela e 32 por linha, com teto de 34 tiles de 8×8 por linha.

**Costumes** (conhecimento geral, a calibrar):

- Rampas de 3 a 4 tons por material, com desvio de matiz.
- Contorno colorido: a linha é um tom escuro da cor da área, não preto.
- Transições suaves, favorecidas pela paleta grande. Pouco dithering nos sprites.
- Personagens de RPG em torno de 16×24; personagens de ação de 32 a 48 de altura.
- Transparência e mistura de camadas em água, névoa e luz, que o console fazia por hardware.

**Assinatura**: cores suaves e variadas, sombra em rampa, contorno colorido, cenários com camadas translúcidas.

**O que quebra o estilo**: contorno preto duro em tudo; mais de 15 cores num sprite; cores chapadas sem rampa.

### Mega Drive

**Limites**, pelas [especificações no Sega Retro](https://segaretro.org/Sega_Mega_Drive/Technical_specifications) e pela página de [uso do VDP](https://segaretro.org/Sega_Mega_Drive/VDP_general_usage):

- Resolução usual de 320×224.
- 512 cores possíveis (9 bits), em 4 paletas de 16. Na prática, 61 cores utilizáveis na tela.
- 16 cores por sprite, contando a transparente.
- 80 sprites na tela e 20 por linha no modo de 320 pixels.
- Um modo de sombra e realce amplia a paleta para 1.536 cores.

Um [resumo técnico da paleta](https://martink-rsa.github.io/bitmapped/presets/genesis) registra um costume importante: muitos jogos usavam dithering que se misturava na saída de vídeo composto das TVs da época, criando cores fora da paleta.

**Costumes**:

- Paleta mais curta e mais escura que a do Super Nintendo, com contraste alto.
- Dithering em xadrez e em colunas, em sprites e fundos, para simular meios-tons e transparência.
- Com só 4 paletas para a tela inteira, personagens e cenário dividem cores.
- Tela mais larga (320 pixels) e sprites grandes em jogos de ação.

**Assinatura**: contraste forte, tons mais sombrios, textura de dithering.

**O que quebra o estilo**: degradês longos e suaves; mais de 61 cores na cena; transparência real em vez de dithering.

**Atenção para o app**: o dithering do Mega Drive foi feito para borrar numa TV antiga. Numa tela atual ele aparece como xadrez nítido. Vale decidir, por projeto, se o estilo usa esse dithering ou só a paleta.

### PC Engine

**Limites**, pelas páginas do [TurboGrafx-16](https://en.wikipedia.org/wiki/TurboGrafx-16) e do [SuperGrafx](https://en.wikipedia.org/wiki/PC_Engine_SuperGrafx) na Wikipedia e pela ficha do [8bitworkshop](https://8bitworkshop.com/docs/platforms/pce/index.html):

- 512 cores possíveis (9 bits), com até 482 na tela.
- 32 paletas: 16 para o fundo e 16 para sprites, cada uma de sprite com 15 cores mais transparência.
- Sprites de 16×16 até 32×64, 64 na tela e 16 por linha.

**Costumes**: como cada sprite pode usar uma de 16 paletas, as telas são mais coloridas que as do Mega Drive, com a mesma profundidade de cor. Sprites grandes e bem definidos, próximos dos arcades.

**Assinatura**: colorido rico com cores "duras" de 9 bits, sprites grandes.

**O que quebra o estilo**: meios-tons finos que 9 bits não representam.

## 5. Portáteis de 32 bits e arcade

Neste grupo o limite deixa de ser a cor e passa a ser o tamanho da tela ou o custo de produção. São os estilos de pixel art mais detalhados da era clássica.

### Game Boy Advance

**Limites**, pela documentação do [gbadev sobre gráficos](https://gbadev-org.github.io/gbadoc/graphics.html) e [sobre sprites](https://gbadev-org.github.io/gbadoc/sprites.html):

- Tela de 240×160.
- Cores de 15 bits (32.768), com uma paleta de 256 entradas para fundos e outra de 256 para sprites.
- Sprites de 8×8 até 64×64, em 16 paletas de 16 cores ou numa paleta única de 256.
- 128 sprites nos modos de fundo em tiles.
- Rotação e escala de sprites por hardware, e sprites semitransparentes.

**Costumes** (conhecimento geral, a calibrar):

- Cores mais claras e saturadas que as do Super Nintendo. A tela original não tinha luz própria, e os artistas compensavam clareando a paleta.
- Estrutura de 16 bits (15 cores por sprite, rampas, contorno colorido) numa tela menor.
- Personagens proporcionalmente grandes na tela, por causa da resolução baixa.

**Assinatura**: 16 bits com cores lavadas e vivas, enquadramento fechado.

**O que quebra o estilo**: paleta escura e de baixo contraste; cenas pensadas para tela larga.

### Neo Geo

**Limites**, pelas [especificações no wiki do NeoGeo Dev](https://wiki.neogeodev.org/index.php/General_specifications):

- Resolução de 320×224.
- 65.536 cores possíveis, com até 3.840 na tela: 256 paletas de 15 cores.
- Até 380 sprites, 96 por linha.
- Os sprites têm 16 pixels de largura e até 512 de altura, montados com tiles de 16×16. Até os cenários são feitos de sprites.

**Costumes**:

- Personagens enormes para a época, de 100 pixels de altura ou mais em jogos de luta.
- Como cada tile escolhe uma entre 256 paletas, um personagem grande junta várias paletas e passa de 15 cores.
- Animação com muitos frames e muito detalhe de tecido e músculo.
- Rampas longas, de 5 tons ou mais.

**Assinatura**: sprites grandes, animação fluida, cor abundante.

**O que quebra o estilo**: sprites pequenos e simplificados; poucas cores; animação de 2 ou 3 frames.

### Placas de arcade

As placas dos anos 1990 seguem a mesma lógica do Neo Geo. Um [estudo de Fabien Sanglard](https://fabiensanglard.net/snes_ppus_why) compara os sistemas: a placa CPS-1 da Capcom desenha 256 sprites sem limite por linha, enquanto o Super Nintendo fica em 128 com 32 por linha e o Mega Drive em 80 com 20.

Sem o limite por linha, o arcade podia encher a tela de personagens grandes. Para o AssetFlow, "estilo arcade" significa na prática: corpo de 64 pixels ou mais, 15 cores por parte do corpo e animação com muitos frames.

**Aviso de escopo**: este é o estilo mais caro de produzir, também para o app. Um desenhista por receita chega bem a 48 ou 64 de corpo; personagens de luta de 100 pixels ficam fora do alcance prático.

## 6. Computadores

Os computadores domésticos tinham regras de cor mais estranhas que as dos consoles, e cada um gerou um visual inconfundível. São estilos de nicho, úteis para jogos que querem parecer "de micro".

### ZX Spectrum

**Limites**, pelo artigo sobre [attribute clash](https://en.wikipedia.org/wiki/Attribute_clash) e pela página de [modos gráficos do ZX Spectrum](https://www.wikipedia.org/wiki/ZX_Spectrum_graphic_modes):

- Tela de 256×192.
- 15 cores fixas e muito saturadas: 8 cores básicas em dois níveis de brilho, com o preto igual nos dois.
- Cada bloco de 8×8 pixels só pode ter 2 cores, e as duas precisam ser do mesmo nível de brilho.
- Não há sprites de hardware.

Quando duas figuras de cores diferentes ocupam o mesmo bloco, uma "vaza" na outra. É o efeito chamado *attribute clash*. Uma saída comum era desenhar o jogo em duas cores só, como registra o mesmo artigo.

**Costumes** (conhecimento geral): personagens em uma cor sobre fundo preto; cenários alinhados à grade de 8×8 para a cor não vazar; muito detalhe de linha, já que a resolução de pixels é alta e a de cor é baixa.

**Assinatura**: cores primárias berrantes, blocos de cor quadrados, sprites monocromáticos.

**O que quebra o estilo**: três cores num bloco de 8×8; tons pastéis; mistura de cor clara e escura no mesmo bloco.

### Commodore 64

**Limites**, pela página do [chip VIC-II](https://en.wikipedia.org/wiki/MOS_Technology_VIC-II):

- 320×200 em alta resolução, ou 160×200 no modo multicor, em que cada pixel tem largura dupla.
- 16 cores fixas.
- 8 sprites por linha, de 24×21 em uma cor ou 12×21 em multicor.
- No modo multicor, 3 cores por bloco mais a cor de fundo.

**Costumes**: a maioria dos jogos usa o modo multicor, então o pixel é um retângulo deitado. A paleta de 16 cores é terrosa e pouco saturada, com vários marrons e cinzas, o que dá um ar sombrio.

**Assinatura**: pixels largos, paleta fosca de marrons, cinzas e azuis.

**O que quebra o estilo**: pixels quadrados com mais de 2 cores por bloco; cores vivas que a paleta não tem.

**Atenção para o app**: pixel de largura dupla exige uma grade lógica não quadrada, que o AssetFlow hoje não tem. Dá para aproximar desenhando em 160×200 e ampliando 2× só na horizontal na exibição.

### MSX

**Limites**, por um [resumo do chip TMS9918](https://info.sonicretro.org/VDP):

- Tela de 256×192.
- Paleta fixa de 16 cores, sendo 15 mais a transparente.
- 32 sprites de uma cor só, de 8×8 ou 16×16, com no máximo 4 por linha.
- No fundo, 2 cores a cada faixa de 8×1 pixels.

**Costumes**: personagens de uma cor, ou de duas e três cores feitos com sprites sobrepostos. Fundos mais detalhados que os do Spectrum, porque a cor muda a cada linha do bloco.

**Assinatura**: sprites chapados de uma cor sobre fundos coloridos em faixas horizontais.

### Amiga

**Limites**, pelo [arquivo de modos de tela do Amiga](https://amiga.lychesis.net/articles/ScreenModes.crt.html) e pela [lista de paletas de computadores de 16 bits](https://en.wikipedia.org/wiki/List_of_16-bit_computer_color_palettes):

- Baixa resolução de 320×200 (NTSC) ou 320×256 (PAL).
- 4.096 cores possíveis (12 bits), com até 32 na tela no modo normal.
- Modo EHB com 64 cores, em que as 32 extras são versões mais escuras das primeiras.
- Modo HAM, que mostra as 4.096 com restrições entre pixels vizinhos.
- Um coprocessador troca cores da paleta no meio da tela, o que permite mais cores do que o limite sugere.

**Costumes**: como a paleta de 16 ou 32 cores vale para a tela inteira, e não por sprite, os artistas montavam uma paleta única muito bem planejada para cada cena. Céus em degradê feitos com a troca de cor por linha. Uso generoso de dithering e de anti-aliasing manual, numa estética mais "pintada".

**Assinatura**: degradês de céu, paleta única e harmônica por tela, acabamento polido com dithering.

**O que quebra o estilo**: cores chapadas sem transição; uma paleta diferente para cada personagem.

## 7. Estilos de limite escolhido

Aqui não há máquina impondo nada: o artista adota um limite de propósito, e o limite vira o estilo. São os estilos mais fáceis de o AssetFlow reproduzir com fidelidade, porque as regras são poucas e explícitas.

### PICO-8

O PICO-8 é um "console de fantasia": um programa que imita as limitações de uma máquina de 8 bits que nunca existiu. As [especificações oficiais](https://www.lexaloffle.com/pico-8.php) são:

- Tela de 128×128 com 16 cores.
- 256 sprites de 8×8.
- Mapa de 128×32 tiles.

A paleta de 16 cores é fixa, e todas podem ser usadas em qualquer sprite. Os valores exatos estão no `paletas.yaml` do AssetFlow, conferidos no Lospec.

**Costumes** (conhecimento geral): personagens de 8×8 ou 16×16; contorno preto opcional, muitas vezes ausente; cores chapadas, com no máximo uma sombra; tela inteira muito legível por causa da resolução minúscula.

**Assinatura**: a paleta, reconhecível de imediato, e a escala minúscula.

**O que quebra o estilo**: uma décima sétima cor; sprites grandes e detalhados; degradês.

### 1 bit

Duas cores: uma de fundo e uma de figura. O limite é autoimposto, e vêm dele as regras:

- Toda forma se define por silhueta e por contorno, sem tons.
- Volume e textura saem de padrões de dithering. O [guia de dithering do Pixel Parmesan](https://pixelparmesan.com/dithering-for-pixel-artists) trata o trabalho de 1 bit como o caso em que o dithering de preenchimento mais se justifica, e observa que ele pede mais resolução para os padrões funcionarem.
- Separar figura e fundo exige uma linha de contorno na cor oposta ou uma margem vazia em volta.

**Costumes**: as duas cores raramente são preto e branco puros; é comum um par escuro e claro com matiz, como azul-marinho e creme. Trocar o par de cores muda o clima sem redesenhar nada.

**Assinatura**: duas cores, padrões de pontos, silhuetas fortes.

**O que quebra o estilo**: um terceiro tom, mesmo que seja só anti-aliasing.

### Paletas fechadas da comunidade

São paletas publicadas com nome, de 4 a 64 cores, usadas por muitos artistas. O jogo inteiro usa só aquelas cores. O AssetFlow já tem quatro cadastradas: Endesga 32, Sweetie 16, PICO-8 e DawnBringer 16.

| Tamanho | Como se usa | Efeito |
| --- | --- | --- |
| 4 cores | Um tom para cada papel: fundo, sombra, base, luz | Próximo do Game Boy, com matiz |
| 8 cores | Duas ou três rampas curtas que dividem as pontas | Muito coeso, exige economia |
| 16 cores | Rampas de 3 tons que compartilham cores | O equilíbrio mais popular |
| 32 cores | Rampas de 4 a 5 tons por material | Próximo dos 16 bits |
| 64 cores | Rampas completas com neutros | Liberdade quase total |

A tabela descreve o uso típico; não vem de uma fonte única.

O que dá unidade a esses estilos é a paleta compartilhada, mais do que o tamanho do sprite ou o tipo de contorno. É por isso que a paleta-mestra é o primeiro campo de um estilo no app.

**O que quebra o estilo**: qualquer cor fora da paleta, inclusive as que aparecem em anti-aliasing ou em sprites semitransparentes.

## 8. Estilos de direção de arte

Nos jogos atuais não há limite técnico, e o estilo é uma escolha. Esta seção descreve tendências, não regras: as fontes são entrevistas e análises, e quase tudo aqui é costume.

### Hi-bit

O termo foi proposto em 2016 pelo estúdio do jogo Owlboy. Um [artigo sobre a popularidade da pixel art](https://rocketbrush.com/blog/pixel-art-games-popular) resume a definição: jogos que não replicam as limitações antigas, e sim ampliam o visual de pixels com resoluções maiores e tela larga de 16:9, ganhando complexidade sem perder o sabor retrô. Uma [monografia sobre gráficos hi-bit](https://www.theseus.fi/bitstream/handle/10024/501981/?sequence=2) lista técnicas que separam o hi-bit da pixel art clássica: ajuste de pixel perfeito, mapas de normais e animação por esqueleto.

Uma [discussão no fórum do Pixel Joint](https://pixeljoint.com/forum/printer_friendly_posts.asp?TID=22229) compara o estilo moderno com o retrô em três pontos: menos detalhe e mais cores por sprite, ausência do contorno preto, e cores bem menos saturadas.

**Traços comuns** (a calibrar com referências):

- Sem limite de cores por sprite; rampas longas com desvio de matiz forte.
- Contorno ausente ou seletivo; as formas se separam por valor e por cor.
- Paleta atmosférica: uma cor dominante por cena, com acentos saturados.
- Luz, brilho, partículas e transparência feitos pelo motor do jogo, por cima dos sprites.
- Animação com muitos frames.

**Para o app**: o sprite em si continua sendo pixel art comum. O que faz o "hi-bit" são a paleta sem teto, a falta de contorno preto e os efeitos de motor, que estão fora do AssetFlow.

### Minimalista

Sprites muito pequenos, de 8 a 16 pixels de corpo, com poucas cores e nenhum detalhe interno. O personagem é quase um símbolo.

- 2 a 4 cores por sprite, chapadas.
- Sem contorno, ou com contorno de 1 pixel na cor mais escura.
- A expressão vem da animação e da pose, não do desenho.
- Fundos de cor sólida ou com textura mínima.

**Para o app**: é o estilo mais barato de gerar e o que mais depende de animação para ter graça.

### HD-2D

Nome dado pela Square Enix ao estilo criado para Octopath Traveler, de 2018. A [página sobre HD-2D na Wikipedia](https://en.wikipedia.org/wiki/HD-2D) o define como a combinação de sprites tradicionais em 2D com ambientes tridimensionais. Segundo a mesma página, a designer de pixels Shizuka Morimoto incorporou elementos 3D para dar profundidade, enquanto o produtor insistiu na luz e na sombra para mostrar como a iluminação interage com cenários de pixels.

Em [entrevista à Unreal Engine](https://www.unrealengine.com/developer-interviews/octopath-traveler-ii-builds-a-bigger-bolder-world-in-its-stunning-hd-2d-style), a equipe diz que a meta era uma versão moderna das lembranças de jogar RPGs de pixel art da era do Super Nintendo.

**Traços comuns**: personagens no estilo 16 bits, pequenos e de contorno colorido; cenários em 3D com texturas de pixel; desfoque de profundidade, luz volumétrica e reflexos.

**Para o app**: o AssetFlow só faz a parte 2D. Para HD-2D, os personagens seguem a ficha do Super Nintendo; o resto é trabalho do motor do jogo.

### Isométrico clássico

O isométrico é uma projeção, mas jogos de estratégia e simulação dos anos 1990 fizeram dele um estilo:

- Linhas de chão na razão 2:1 e tiles em losango, como descrito na base de conhecimento.
- Três faces com valores fixos: topo claro, uma lateral média, a outra escura.
- Objetos construídos como blocos, com muito detalhe de textura.
- Paleta de 256 cores para a tela inteira, comum nos PCs da época.

**Para o app**: depende do campo de projeção no projeto e de moldes próprios. É a ficha menos pronta para virar configuração.

### O que estes quatro têm em comum

Nenhum deles se define por um número de cores. O que os define são decisões de contorno, de saturação, de escala e de quanto o motor do jogo acrescenta depois. Por isso, no app, eles dependem mais da biblioteca de referências do que de regras escritas.

## 9. Do estilo ao YAML

Cada ficha vira um arquivo em `backend/config/pixel_knowledge/estilos/`, e o projeto escolhe um estilo ativo. O estilo troca em conjunto o que hoje sai de `BaseDeConhecimento.estilo()`: paleta-mestra, luz, contorno e proporções.

### Formato proposto

```yaml
# config/pixel_knowledge/estilos/nes.yaml
id: nes
nome: 8 bits (NES)
grupo: hardware            # hardware | limite_escolhido | direcao_de_arte

limites:                   # viram regra hard; cada um com a fonte
  cores_por_sprite: {valor: 3, fonte: "noelberry.ca/posts/nes"}
  bloco_de_sprite: {valor: [8, 16], fonte: "noelberry.ca/posts/nes"}
  paleta: nes              # nome em paletas.yaml; cor fora dela reprova
  alpha: binario

costumes:                  # viram regra style, todas a calibrar
  contorno: {valor: preto, a_calibrar: true}
  tons_por_material: {valor: 1, a_calibrar: true}
  dithering: {valor: nenhum, a_calibrar: true}
  corpo_tipico: {valor: "16x24", a_calibrar: true}
  saturacao: {valor: alta, a_calibrar: true}

assinatura: "três cores por personagem, blocos de cor chapada, cabeça grande"
quebra_o_estilo:
  - mais de 3 cores num bloco de sprite
  - sombra em degradê
  - anti-aliasing
```

O exemplo é uma proposta de formato. Os valores de `costumes` são os da ficha da seção 3 e precisam de calibração.

### Regras de construção

- **Limite e costume em blocos separados.** Só `limites` reprova. `costumes` orienta e gera aviso.
- **Todo limite tem fonte.** Sem fonte, o campo vai para `costumes`.
- **O estilo não recalcula o spec.** Ele entra como mais uma camada de precedência, abaixo do que o pedido e a interface disserem. Se o pedido diz "8 cores" e o estilo diz 3, o conflito vira erro em português, sem correção silenciosa.
- **Cores por bloco, não por sprite inteiro.** Em vários consoles o limite vale para cada peça de 8×8 ou 16×16. Um personagem de 16×32 no NES pode ter mais de 3 cores no total, desde que cada bloco respeite o limite. O validador precisa de uma verificação por bloco.
- **Paletas de console entram em `paletas.yaml`**, baixadas da fonte como as atuais, nunca digitadas de memória.

### O que cada grupo exige do app

| Grupo | O que já existe | O que falta |
| --- | --- | --- |
| Hardware de 8 bits | Limite de cores, alpha binário | Verificação de cores por bloco; paletas de NES, Master System e Game Boy |
| Hardware de 16 bits | Limite de cores, rampas, contorno colorido | Teto de 15 cores por sprite; paletas de 9 e 15 bits como regra de arredondamento |
| Computadores | Quase nada | Atributo por bloco de 8×8; pixel de largura dupla |
| Limite escolhido | Paletas nomeadas e travadas | Estilo de 1 bit com padrões de dithering |
| Direção de arte | Paleta sem teto, tipos de contorno | Biblioteca de referências; o resto é do motor do jogo |

### Cores de 9 e 15 bits

Mega Drive e PC Engine só representam 8 níveis por canal; Super Nintendo e Game Boy Advance, 32. Um estilo fiel arredonda cada cor para o nível mais próximo. É uma operação simples de código e dá o aspecto de cor "dura" desses consoles sem precisar de uma lista de paleta.

### Ordem sugerida

1. **Game Boy e PICO-8**: paleta fixa e pequena, regra única. Servem para testar o formato do arquivo.
2. **NES**: obriga a criar a verificação por bloco.
3. **Super Nintendo**: o estilo mais pedido, e o mais próximo do que o app já desenha.
4. **Mega Drive**: reaproveita o anterior, com paleta de 9 bits e decisão sobre dithering.
5. **Paletas fechadas e 1 bit.**
6. **Direção de arte**, depois da biblioteca de referências.
7. **Computadores**, só se houver um jogo que peça.

### Como validar cada estilo

Para cada ficha, importar na biblioteca de referências um pacote de licença livre feito naquele estilo, rodar o medidor e comparar com os `costumes`. Onde a medição discordar da ficha, vale a medição.

## 10. Fontes e limites da pesquisa

Pesquisa feita em 25 de novembro de 2026. Os limites de hardware vêm das páginas abaixo.

| Máquina ou estilo | Fonte |
| --- | --- |
| NES | [NES Limitations, de Noel Berry](https://noelberry.ca/posts/nes/index.html); [manual do Pro Motion](https://www.cosmigo.com/promotion/docs/onlinehelp/gfxHardware-NES.htm) |
| Master System | [Sega Retro, especificações](https://segaretro.org/Sega_Master_System/Technical_specifications) e [comparação de hardware](https://segaretro.org/Sega_Master_System/Hardware_comparison) |
| Game Boy e Game Boy Color | [Pan Docs](https://bgb.bircd.org/pandocs.htm); [lista de paletas de consoles](https://en.wikipedia.org/wiki/List_of_video_game_console_palettes) |
| Super Nintendo | [Wikibooks, SNES Specs](https://en.wikibooks.org/wiki/Super_NES_Programming/SNES_Specs); [Mega Cat Studios, guia de sprites](https://megacatstudios.com/blogs/retro-development/snes-sprite-engine-design-guidelines) |
| Mega Drive | [Sega Retro, especificações](https://segaretro.org/Sega_Mega_Drive/Technical_specifications) e [uso do VDP](https://segaretro.org/Sega_Mega_Drive/VDP_general_usage); [resumo da paleta](https://martink-rsa.github.io/bitmapped/presets/genesis) |
| PC Engine | Wikipedia, [TurboGrafx-16](https://en.wikipedia.org/wiki/TurboGrafx-16) e [SuperGrafx](https://en.wikipedia.org/wiki/PC_Engine_SuperGrafx); [8bitworkshop](https://8bitworkshop.com/docs/platforms/pce/index.html) |
| Game Boy Advance | gbadev, [gráficos](https://gbadev-org.github.io/gbadoc/graphics.html) e [sprites](https://gbadev-org.github.io/gbadoc/sprites.html) |
| Neo Geo | [NeoGeo Dev Wiki](https://wiki.neogeodev.org/index.php/General_specifications) |
| Arcade | [Fabien Sanglard, comparação de sistemas de sprites](https://fabiensanglard.net/snes_ppus_why) |
| ZX Spectrum | Wikipedia, [attribute clash](https://en.wikipedia.org/wiki/Attribute_clash) e [modos gráficos](https://www.wikipedia.org/wiki/ZX_Spectrum_graphic_modes) |
| Commodore 64 | [Wikipedia, VIC-II](https://en.wikipedia.org/wiki/MOS_Technology_VIC-II) |
| MSX | [Sonic Retro, VDP](https://info.sonicretro.org/VDP) |
| Amiga | [Amiga Graphics Archive](https://amiga.lychesis.net/articles/ScreenModes.crt.html); [lista de paletas de 16 bits](https://en.wikipedia.org/wiki/List_of_16-bit_computer_color_palettes) |
| PICO-8 | [Lexaloffle, página oficial](https://www.lexaloffle.com/pico-8.php) |
| Hi-bit | [Rocketbrush](https://rocketbrush.com/blog/pixel-art-games-popular); [monografia de Olli Heikkinen](https://www.theseus.fi/bitstream/handle/10024/501981/?sequence=2); [fórum do Pixel Joint](https://pixeljoint.com/forum/printer_friendly_posts.asp?TID=22229) |
| HD-2D | [Wikipedia, HD-2D](https://en.wikipedia.org/wiki/HD-2D); [entrevista na Unreal Engine](https://www.unrealengine.com/developer-interviews/octopath-traveler-ii-builds-a-bigger-bolder-world-in-its-stunning-hd-2d-style) |

### Como as fontes foram lidas

Só a página de Noel Berry sobre o NES foi aberta e lida por inteiro. As demais foram consultadas pelos trechos devolvidos na busca, que traziam os números citados. Antes de qualquer limite virar regra `hard` no app, vale abrir a página e conferir o número.

### Limites desta pesquisa

- **Os costumes não têm fonte.** Tudo o que aparece em "Costumes", "Assinatura" e "O que quebra o estilo" é conhecimento geral de arte de jogos. É a parte mais sujeita a erro, e por isso está marcada para calibração.
- **Fontes de qualidade desigual.** Documentação técnica de comunidade (Pan Docs, gbadev, NeoGeo Dev, Sega Retro) é confiável. Wikipedia e sites de divulgação servem para números gerais. Para o hi-bit, as fontes são um blog de estúdio, um trabalho de graduação e um fórum.
- **Números com variação entre fontes.** O Neo Geo aparece com 4.096 ou 3.840 cores na tela (a segunda desconta a cor transparente de cada paleta) e com 380 ou 384 sprites. O Mega Drive aparece com 61 ou 64 cores. A tabela usa o valor da documentação técnica.
- **Tamanhos típicos de personagem** por console não foram verificados em fonte; dependem de medir jogos, o que este documento evita por serem obras protegidas.
- **Ficaram de fora**: Atari 2600, Game Gear, Amstrad CPC, PC-98, Nintendo DS, e as placas de arcade além de uma menção à CPS-1. Também não há fichas de animação por estilo.
- **Paletas em hexadecimal** não foram incluídas. Devem ser baixadas da fonte na hora de montar o `paletas.yaml`.
- **Truques de programação** que ampliavam os limites foram só citados. Um estilo "fiel ao console" pode querer alguns deles, como o sprite duplo do NES.
