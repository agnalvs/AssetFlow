# Estudo dos melhores sprites — o que dá para reaproveitar

> Lote 13 da sessão (pedido da autora em 2026-11-26; SUGESTOES_DE_MELHORIA §9).
> Os quadros foram olhados como imagem, ampliados; nenhum pixel foi copiado.
> **As análises de cada sprite ficam em `backend/data/referencias/estudo/`**
> (fora do git, porque falam de arquivos de terceiros). Aqui ficam só as
> técnicas gerais.

## 1. Como foi feito

1. Dos pacotes CC0 ativos, o primeiro quadro parado de cada folha (sem pulo,
   ataque nem queda), sem repetidos, com teto por pacote para nenhum dominar:
   104 candidatos, mais 40 personagens de corpo inteiro de 16×16 de um pacote
   que a primeira amostra trouxe só em retrato.
2. Folhas de contato numeradas, ampliadas sem suavizar; escolha de 30
   variando pacote (9 dos 10 ativos), tipo (19 personagens, 11 objetos) e
   porte (de 9×11 a 46×44 nos objetos; de 12×15 a 36×64 nos personagens).
3. Uma folha maior só com os 30, e uma análise curta de cada um: rosto, maior
   contraste, roupa e volume, silhueta, uma técnica.

**Ficaram de fora** os corpos-base sem roupa (o pacote de personagem
customizável tem 400 quadros deles): foi um desses que atrapalhou como exemplo
na Fase B2. Também saiu um quadro em que o personagem vinha recortado junto
com um objeto solto, e um baú que o pacote classifica como personagem — como
exemplo, ele apareceria num pedido de personagem.

## 2. Técnicas gerais

### Rosto

- **Em 16 px, o rosto é dois olhos.** Olhos de 1×1 ou 1×2, escuros, e quase
  nunca boca. A expressão vem de **um** elemento a mais: rubor de 1 px na
  bochecha, uma sobrancelha inclinada, uma faixa na testa.
- **Um olho de 2×2 com um pixel de reflexo** já carrega o personagem num corpo
  de 16 a 20 px de altura.
- **No retrato (busto), o olho pode ganhar cor própria** em vez de preto: é
  ali que mora a personalidade.
- **Quando o rosto some** (elmo, máscara, capuz de ninja), um bloco escuro no
  lugar dos olhos, ou uma fenda de pele com dois pontos, faz o rosto — ou um
  acessório grande (óculos) assume a expressão.
- **Olhos claros dentro de uma faixa de sombra** (sob a aba do chapéu) dão
  mistério com dois pixels.

### Contraste

- **O ponto de maior contraste fica no centro**: a boca escura na máscara
  clara, as órbitas no crânio, os olhos no rosto. O olho de quem vê vai direto
  para ele.
- **Moldura escura em volta do rosto claro** (cabelo, capuz, juba) concentra a
  leitura.
- **Uma marca de cor**: uma faixa saturada, uma pluma quente num elmo frio, uma
  estrela de 1 px de cor complementar num chapéu. Pequena, e só daquele
  personagem.
- **Personagem escuro pede contorno mais claro que ele** — o contorno preto
  some num corpo preto.

### Roupa, volume e material

- **Dois a três tons por material bastam** em 16 px; a sombra fica num lado só
  (cabelo, juba, túnica).
- **Metal = faixa clara estreita ao lado da escura.** Uma lâmina é só isso.
  **Dourado = 3 a 4 amarelos** com um reflexo quase branco em faixa.
- **Madeira de caixa** = moldura mais clara de 2 px e painel mais escuro, com o
  grão em pontos.
- **Fruta** = esfera com o brilho do lado da luz e uma folha de cor
  complementar.
- **Gema** = um valor por face; 4 cores fazem a lapidação.
- **Relevo e entalhe** = par de linhas: clara em cima, escura embaixo.
- **Sem contorno, valor diferente entre vizinhos** (cabelo, pele, camisa,
  calça) — a regra de "partes vizinhas com valores diferentes" vale ainda mais.

### Silhueta

- **Em 16 px, cabeça grande**: cerca de 2/3 da altura, corpo de 4 a 5 px.
- **Um elemento sai do contorno e identifica**: chifres, pluma, presas,
  orelhas, pontas de uma faixa voando, a ponta do chapéu. Em preto, é ele que
  diz quem é.
- **A silhueta do mago é o chapéu**; a do cavaleiro, a pluma; a do inimigo, as
  presas para fora.
- **Em proporção realista (60 px ou mais), a silhueta parada perde força**:
  de perfil, com os braços colados, quase não se lê em preto. A pose (pernas
  em tesoura) e um elemento que balança (rabo de cavalo, capa) resolvem.

### Objetos e ícones

- **Ícone pequeno = um símbolo**: em 9 px, um coração no rótulo diz o que o
  frasco é.
- **Dois objetos de tamanhos diferentes juntos** fazem composição num ícone
  pequeno.
- **Arma longa na diagonal de 45°**, com degraus 1:1 limpos.
- **Pixel solto só como efeito**: faíscas de um pavio, nunca sujeira.

### Contorno

- O preto (ou quase preto) contínuo é o mais comum nos personagens de 16 px.
- **Colorido** (o escuro da própria cor) integra criaturas ao cenário.
- **Seletivo** (claro do lado da luz) deixa frutas e bichos macios.

## 3. O que mudou no app

- **Os 30 viraram "bons exemplos"** (`backend/data/referencias/bons_exemplos.json`):
  com o exemplo de construção religado (`ASSETFLOW_EXEMPLO=1`), ele escolhe só
  entre eles (`ASSETFLOW_EXEMPLO_SO_BONS`, ligado). Para humanoide de 32 px,
  por exemplo, sobra um personagem vestido em vez de 400 corpos-base.
- **Treze regras propostas** em
  `config/pixel_knowledge/propostas/estudo_sprites.yaml`, cada uma com a
  verificação. **Nenhuma está ativa**: a base não lê essa pasta. Para aprovar,
  mova as que quiser para um tema em `temas/`.

## 4. Limites

- **30 de ~6.000 quadros**, escolhidos por mim olhando: é gosto, com o
  cuidado de variar pacote, tipo e porte. Um pacote (o de 16×16 com 85
  personagens) dá um terço dos personagens, porque é o que mais tem personagem
  vestido no porte de 16.
- **Poucos personagens de 32 a 48 px** nos pacotes ativos: a lista tem um de
  32 e dois de 60 px ou mais. Pacotes melhores nesse porte ajudariam.
- As técnicas são observação de quadros parados; animação não foi estudada.
