# Como ampliar a base de conhecimento do AssetFlow

Nov 25, 2026 · @Luiza

## 1. Resumo

A base de conhecimento já é maior do que aquilo que o Claude recebe. Antes de pesquisar mais, o maior ganho está em levar o que já existe até a hora do desenho, e só depois ampliar.

**Três números do estado atual** (commit `9362e26`):

| O quê | Tamanho |
| --- | --- |
| Documento de pesquisa (`PIXEL_KNOWLEDGE.md`) | cerca de 60.800 caracteres, em 19 seções |
| Arquivos que o app realmente lê (`config/pixel_knowledge/`) | cerca de 18.200 caracteres, contando comentários |
| O que chega ao Claude em um pedido de personagem | cerca de 2.300 caracteres |

**O que eu recomendo, em ordem:**

1. **Montar uma banca de teste.** Sem ela, não há como saber se uma mudança na base melhorou ou piorou os desenhos.
2. **Converter o que já foi pesquisado** em regras que o app consegue selecionar por pedido, junto com um catálogo de erros.
3. **Criar fichas por assunto**: quadrúpedes, criaturas, armas, materiais. É aqui que a base cresce de verdade, e exige pesquisa nova.
4. **Extrair conhecimento dos pacotes** que você já baixou: rampas reais, formas típicas, detalhes pequenos como olhos e mãos.
5. **Guardar receitas comentadas**, que mostram a ordem de construção de um sprite bom.

A Fase B2, que você já enviou, cobre uma sexta forma: lições e exemplos que se acumulam com o uso.

**O limite a respeitar:** base maior não pode significar mais texto em todo pedido. O que cresce é o acervo. O que chega ao Claude continua sendo um recorte pequeno, escolhido para aquele pedido.

## 2. O que a base tem hoje e o que chega ao Claude

A maior parte da pesquisa de pixel art está guardada no projeto, mas fora do caminho do desenho. A tabela compara as seções do documento com os arquivos que o app lê.

| Seção do `PIXEL_KNOWLEDGE.md` | Está nos arquivos que o app lê? | Chega ao Claude? |
| --- | --- | --- |
| 2. Grade, resolução e escala | Em parte, pelo spec do pedido | Sim |
| 3. Silhueta, forma e legibilidade | Em parte: cinco regras do humanóide | Sim, para humanóide |
| 4. Linhas e contorno | Não | Não |
| 5. Cor e paleta | Sim: paletas e rampas por material | Sim |
| 6. Luz e sombreamento | Duas regras | Sim |
| 7. Anti-aliasing manual e dithering | Não | Não |
| 8. Clusters e limpeza | Não, só no validador | Só como aviso depois do desenho |
| 9. Personagens | Só o humanóide de 32 | Sim, para humanóide |
| 10. Props, itens e ícones | Um molde de 32 | Pouco |
| 11 a 16. Tiles, cenários, animação, efeitos, spritesheets | Não | Não (são fases futuras) |
| 17. Erros comuns e checklist | Não | Vai entrar pela Fase B2 |
| `PIXEL_STYLES.md` inteiro | Não | Não (é a fase de estilos) |

### O que isso mostra

- **Quatro temas de desenho ficaram de fora**: contorno, anti-aliasing, dithering e clusters. São exatamente os que separam um sprite limpo de um sprite com cara de amador.
- **Só um tipo de corpo tem medidas.** Um lobo, um dragão ou um pássaro recebem quase nada de orientação. Isso já estava registrado como pendência.
- **Objetos recebem pouco.** Uma espada e um baú recebem o mesmo texto genérico.
- **A base não conhece materiais além da cor.** Ela diz quais tons usar em metal, mas não como o metal brilha.

Medi isso lendo os arquivos do repositório. A coluna "Chega ao Claude" vem do recorte que o Claude Code mostrou nesta conversa, não de um teste meu com todos os tipos de pedido. O inventário exato é o primeiro passo do pedido na seção 8.

## 3. Seis formas de ampliar a base

As seis se completam. As três primeiras aumentam o que a base sabe, e as três últimas fazem a base aprender com sprites reais e com o uso.

| Forma | O que entra na base | Ganho esperado | Custo |
| --- | --- | --- | --- |
| 1. Converter o que já existe | Regras curtas tiradas do documento, com etiquetas de tema, tipo e tamanho | Alto, e rápido | Baixo: não exige pesquisa |
| 2. Fichas por assunto | Uma ficha para cada família: quadrúpede, ave, criatura sem pernas, arma, frasco, planta, material | Alto para tudo que não é humanóide | Médio: pesquisa por tema |
| 3. Catálogo de erros | Cada erro clássico com descrição, como o app detecta e como corrigir | Alto na limpeza do desenho | Médio: parte é programação |
| 4. Extração dos pacotes | Rampas reais, formas típicas e detalhes pequenos medidos nos sprites CC0 | Médio a alto | Médio: programação e curadoria sua |
| 5. Receitas comentadas | Sprites bons em formato de receita, com a ordem de construção explicada | Médio a alto | Baixo, depois que a conversão existir |
| 6. Lições e exemplos do uso | O que o Claude errou, o que você gostou e não gostou | Cresce com o tempo | Já está na Fase B2 |

### O que a pesquisa diz sobre exemplos e lições

- **Exemplo precisa ser parecido com o pedido.** Um estudo sobre exemplos em geração de código concluiu que os modelos aproveitam bem a informação direta de um exemplo, mas têm dificuldade de tirar lições gerais de soluções apenas parecidas ([Li e outros, 2025](https://arxiv.org/abs/2508.06414)). Para a base, isso quer dizer: mostrar um arqueiro de 48 para um pedido de arqueira de 48 ajuda mais do que mostrar um sprite qualquer.
- **A escolha e a ordem dos exemplos mudam o resultado.** Outro estudo mediu que o desempenho depende muito de quais exemplos entram e de como são selecionados ([Gao e outros, 2023](https://arxiv.org/abs/2304.07575)).
- **Lições acumuladas funcionam sem treinar o modelo.** O método ExpeL guarda lições em texto e as mantém com quatro operações: adicionar, reforçar, enfraquecer e editar ([Zhao e outros, 2024](https://arxiv.org/abs/2308.10144)). É o mesmo desenho do contador de lições da Fase B2.
- **Lições demais atrapalham.** Um trabalho posterior aponta que colar todas as lições em todo pedido, sem olhar a relevância, deixa de funcionar bem conforme a lista cresce ([Experiential Reflective Learning, 2026](https://arxiv.org/abs/2603.24639)). Por isso o limite de cinco lições por pedido.

Esses estudos tratam de código e de agentes em geral, não de pixel art, e eu os li pelos resumos da busca. Servem como direção, e a banca de teste da seção 7 é o que confirma no seu caso.

## 4. Temas que faltam e onde pesquisar

São dois grupos: temas que já estão no documento de pesquisa mas não viraram regra, e temas que ainda não foram pesquisados.

### Já pesquisados, falta converter

| Tema | O que vira regra |
| --- | --- |
| Contorno | Contorno inteiro, seletivo ou colorido; quando quebrar o contorno; espessura por tamanho |
| Anti-aliasing manual | Onde suavizar e onde não suavizar; quantos tons intermediários por tamanho |
| Dithering | Quando usar e quando evitar em sprites pequenos |
| Clusters | Tamanho mínimo de uma mancha de cor; pixel solto só como brilho intencional |
| Erros comuns | A lista da seção 17, que vira o catálogo de erros |

### Ainda não pesquisados

| Tema | Por que falta | Prioridade |
| --- | --- | --- |
| Quadrúpedes e criaturas | A base só tem medidas de humanóide | Alta |
| Rostos e expressão por tamanho | Com 16, 32 e 48 pixels o rosto se resolve de formas diferentes | Alta |
| Materiais | Como metal, vidro, pelo, tecido, pedra e líquido reagem à luz | Alta |
| Itens por família | Armas, frascos, baús, chaves, comida: cada família tem a sua silhueta típica | Média |
| Pose e linha de ação | Como fugir da figura parada de frente sem perder a leitura | Média |
| Variação de matiz nas rampas | Quanto o tom muda de cor ao escurecer e ao clarear, com números | Média |
| Vegetação e objetos de cenário | Árvores, arbustos, pedras, móveis | Baixa, até a fase de tiles |

### Fontes para essa pesquisa

| Fonte | O que cobre | Acesso |
| --- | --- | --- |
| [Tutorial do Pixel Joint](https://pixeljoint.com/forum/forum_posts.asp?TID=11299) | Termos e erros clássicos: anti-aliasing ruim, serrilhado, dithering ruim, faixas, sombreamento "de almofada", ruído, contorno seletivo, rampas e variação de matiz | Gratuito |
| [Catálogo do Pixelblog, de Raymond Schlitter](https://www.slynyrd.com/pixelblog-catalogue) | Anatomia humana, ciclos de caminhada, personagens de vista superior, cavaleiros e monstros, cenários | Maior parte gratuita; o autor informa que parte dos tutoriais novos é paga |
| [Tutoriais de Pedro Medeiros](https://blog.studiominiboss.com/pixelart) | Dezenas de tutoriais curtos em GIF, de fundamentos a animação e efeitos | Gratuitos no blog do autor |
| [Acervo de tutoriais do Lospec](https://lospec.com/pixel-art-tutorials) | Busca por tema, autor e formato | Gratuito |
| [Tutorial de Arne Niklas Jansson](https://www.androidarts.com/pixtut/pixelart.htm) | Sombreamento "de almofada", faixas de cor e como evitá-las | Gratuito |
| [Anti-aliasing no Pixel Parmesan](https://pixelparmesan.com/anti-aliasing-fundamentals-for-pixel-artists) | Anti-aliasing manual e a relação com faixas | Gratuito |

### Como usar essas fontes

- **A base guarda a técnica com as nossas palavras**, com o link da fonte ao lado de cada regra. Texto e imagens dos tutoriais não são copiados para o projeto.
- **Tutorial ensina a regra; os pacotes CC0 dão os números.** "Varie o matiz ao escurecer" vem do tutorial. Quanto variar vem de medir os sprites que você já tem.
- **Uma ficha por vez.** Cada tema vira um documento de pesquisa curto, como os dois anteriores, e depois um arquivo da base.

Não sou advogado. A regra de não copiar texto nem imagem é a postura cautelosa, e combina com a que você já adotou para os pacotes.

## 5. O que o app pode extrair sozinho dos pacotes

Você já tem 7.043 quadros de dez pacotes CC0 medidos. Hoje o app tira deles poucas estatísticas. Dá para tirar bem mais, sem gastar nenhum token.

| O que extrair | Como | Para que serve |
| --- | --- | --- |
| Rampas reais | Agrupar as cores de cada sprite por matiz e ordenar do escuro ao claro | Trocar a regra vaga de variação de matiz por números medidos |
| Hábitos de contorno | Medir a cor do contorno em relação à cor de dentro, e onde ele some | Regras de contorno seletivo com base em sprites reais |
| Tamanho das manchas de cor | Contar manchas por tamanho e a taxa de pixels soltos | Calibrar os avisos de pixel solto, pendência da antiga fase 5 |
| Forma típica por tipo e tamanho | Sobrepor as silhuetas de sprites do mesmo tipo | Mostrar onde o corpo costuma ocupar o quadro, sem impor medidas |
| Proporções por tipo de corpo | Repetir para quadrúpedes e criaturas o que já foi feito para humanóides | Fechar a pendência dos corpos sem medidas |
| Detalhes pequenos | Recortar a região da cabeça e achar os padrões de pixels mais repetidos | Uma biblioteca de olhos, bocas, mãos e pés por tamanho |
| Sprites inteiros como receita | Converter o sprite para o formato de receita | Os exemplos da Fase B2 |

### O que depende de você

- **Curadoria.** O app acha os padrões mais repetidos, mas não sabe se um deles é um olho ou uma fivela. Uma tela simples mostra os candidatos e você marca o que cada um é e quais prestam.
- **Mais pacotes.** Para medir quadrúpedes e criaturas é preciso ter sprites deles. Isso pede uma nova rodada de downloads CC0 pelo `maos`, focada em animais, monstros e itens.

### O limite dessa extração

- **Detalhes pequenos são a parte mais incerta.** Achar um olho automaticamente num sprite de 16 pixels pode não funcionar bem. Vale começar pelas quatro primeiras linhas da tabela, que são contas simples.
- **Medida não é regra.** Tudo o que sai dos pacotes entra marcado como "a calibrar", como as proporções de hoje.
- **A biblioteca de detalhes é a que mais muda a regra dos sprites de terceiros.** Um olho recortado de um pacote e reaproveitado é mais próximo de cópia do que um exemplo mostrado. A licença CC0 permite, mas a decisão é sua.

## 6. Como garantir que a base seja consultada

A base é consultada de verdade quando o app escolhe o trecho certo e o entrega em três momentos, e quando você consegue ver o que foi entregue.

### Três momentos de consulta

| Momento | O que a base entrega | Situação |
| --- | --- | --- |
| Antes de desenhar | O recorte: medidas, luz, cores, a ficha do assunto, um exemplo e as lições | Existe em parte; cresce com as fichas |
| Na hora de olhar | Perguntas de verificação tiradas da base | Entra na Fase B2 |
| Depois de desenhar | As medições do app comparadas com as regras e com as referências | Entra na Fase B2 |

### Como o app escolhe o que mandar

- **Cada regra ganha etiquetas**: tema, tipo de asset, tipo de corpo, faixa de tamanho, material e nível de liberdade.
- **O pedido aciona as etiquetas.** "Espada de ferro 32x32" puxa a ficha de armas, a regra de metal e as regras de 32 pixels. Não puxa nada de pele nem de capa.
- **Um teto por pedido.** Hoje o teto é de 4.000 caracteres. Com exemplo e lições, a proposta é medir quanto cada parte ocupa e fixar um teto novo, em vez de deixar crescer.
- **Prioridade quando não cabe tudo**: limites duros, depois a ficha do assunto, depois o exemplo, depois as lições, e por último as regras gerais.

### Consulta sob demanda

Uma ferramenta nova, `consultar_base(tema)`, deixa o Claude pedir o detalhe de um tema quando tiver dúvida, por exemplo "como desenhar pelo em 32 pixels". Ela só custa tokens quando é usada, e permite que a base seja grande sem que o recorte seja.

### Como você confere

- **Na tela**, "O que o AssetFlow entendeu" mostra o recorte exato que o Claude vai receber, com o nome de cada regra.
- **Em cada asset**, fica gravado quais regras, qual exemplo e quais lições foram enviados.
- **Com o tempo**, o app cruza isso com os seus "gostei" e "não gostei". Uma regra que aparece muito em desenhos de que você não gosta é candidata a revisão.

### O que evitar

- **Mandar a base inteira.** Gasta tokens em todo pedido e dilui o que importa.
- **Regra sem fonte.** Cada regra aponta para a seção do documento ou para a medição de onde saiu.
- **Regra que ninguém testa.** Uma regra nova entra depois de passar pela banca da seção 7.

## 7. Como saber se melhorou

Uma banca de teste fixa: os mesmos pedidos, desenhados antes e depois de cada mudança na base, com a sua nota. Sem isso, cada mudança é um palpite.

### A banca

Seis pedidos que cobrem os casos principais:

| Pedido | O que testa |
| --- | --- |
| Maga do gelo 48x48, 12 cores | Personagem com roupa larga e acessório |
| Guerreiro anão 32x32, 8 cores | Proporção fora do padrão, tamanho pequeno |
| Lobo cinzento 32x32, 8 cores | Quadrúpede |
| Slime verde 16x16, 4 cores | Criatura sem membros, tamanho mínimo |
| Machado de batalha 32x32, 8 cores | Arma, metal e madeira |
| Baú de tesouro aberto 32x32, 10 cores | Objeto com volume e brilho |

### Como rodar

1. **Antes da mudança**, desenhar os seis e guardar como rodada de referência.
2. **Depois da mudança**, desenhar os seis de novo, em conversa nova, do zero.
3. **Na tela**, uma página "Comparar" mostra cada par lado a lado, sem dizer qual é o novo. Você escolhe o melhor e dá uma nota de 1 a 5.
4. **A mudança fica** se a maioria dos pares melhorar e nenhum piorar muito. Senão, é desfeita ou ajustada.

### O que o app registra junto

- As medições do olho do app em cada desenho.
- Quantos remendos cada desenho precisou.
- Quantos tokens a rodada gastou.

### Limites honestos

- **É pouco desenho para tirar conclusão forte.** Seis pares mostram tendência, não prova. Uma diferença pequena pode ser acaso.
- **A nota é sua opinião**, e é isso mesmo que se quer medir, porque o app é para você.
- **Cada rodada custa** seis desenhos da sua assinatura, mais os remendos. Por isso a banca é de seis, e não de vinte.
- **Mudar uma coisa por vez.** Se a rodada misturar três mudanças, não dá para saber qual delas ajudou.

## 8. Ordem sugerida e pedido para o Claude Code

A base cresce em quatro etapas, depois da Fase B2. Cada etapa passa pela banca antes de ser mantida.

| Etapa | O que faz | Quem faz |
| --- | --- | --- |
| K1. Inventário e banca | Mede o que a base tem e o que chega ao Claude; cria a banca e a tela "Comparar"; roda a rodada de referência | Claude Code |
| K2. Converter e catalogar | Leva contorno, anti-aliasing, dithering, clusters e erros comuns para a base, com etiquetas; cria `consultar_base` | Claude Code |
| K3. Fichas por assunto | Pesquisa de cada tema e ficha correspondente, começando por quadrúpedes, rostos e materiais | Eu pesquiso; Claude Code implementa |
| K4. Extração dos pacotes | Rampas reais, contorno, manchas de cor e formas típicas; depois, detalhes pequenos com a sua curadoria | Claude Code; você na curadoria; `maos` para pacotes novos |

As receitas comentadas entram junto com a K4, porque dependem da conversão de sprites que a Fase B2 cria.

### Pedido para a etapa K1

Exporte este documento em Markdown, salve como `backend/docs/PLANO_BASE_CONHECIMENTO.md` e envie o texto abaixo **depois** que a Fase B2 estiver concluída e testada.

```text
Adicionei backend/docs/PLANO_BASE_CONHECIMENTO.md. Leia esse arquivo
inteiro antes de qualquer alteração. Mesmas regras de sempre: branch
desenhista-mcp, sem PR, sem tocar no main, sem enviar backend/data/,
.mcp.json nem .env.

Execute SOMENTE a etapa K1 (inventário e banca). Antes de programar,
me mostre e ESPERE meu "sim":

1. O inventário real: para cada seção do PIXEL_KNOWLEDGE.md e do
   PIXEL_STYLES.md, quais regras existem nos arquivos de
   config/pixel_knowledge/, e quais chegam ao recorte em cada um destes
   pedidos: personagem 48, personagem 32, quadrúpede 32, criatura 16,
   arma 32 e objeto 32. Corrija a tabela da seção 2 do plano onde ela
   estiver errada.
2. O tamanho do recorte em cada um desses seis pedidos, em caracteres,
   separado por parte (medidas, luz, cores, silhueta, exemplo, lições,
   referências).
3. A banca de teste: como os seis pedidos da seção 7 ficam guardados,
   como uma rodada é criada e ligada a uma versão da base, e como a
   fila os entrega para desenho.
4. A tela "Comparar": pares lado a lado sem dizer qual é o novo, a
   minha escolha e a nota de 1 a 5, e o resumo da rodada.
5. O que o app registra em cada asset sobre o recorte recebido (regras,
   exemplo, lições), para cruzar depois com as minhas notas.
6. Onde o plano não bate com o código.

Depois do "sim", programe, rode a rodada de referência comigo e pare.
Não comece a K2 sem eu pedir.
```
