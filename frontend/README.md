# AssetFlow — Web

Primeira interface web do AssetFlow: descrever o asset, ver o que o AssetFlow
entendeu do pedido e, quando o caminho estiver ligado, gerar, acompanhar e
baixar.

> **Plano do app** ([../backend/docs/PLANO_APP_DESENHISTA.md](../backend/docs/PLANO_APP_DESENHISTA.md)).
> O app tem um gerador só, a desenhista, que desenha a partir de uma receita
> escrita pelo Claude. Desde a Fase B, "Gerar" **cria um pedido** numa fila
> (`/api/pedidos`); o Claude o desenha pela conversa e a tela mostra o
> resultado sozinha (`usePedidos` consulta a lista a cada 2 s enquanto houver
> pedido ativo). A fila de pedidos e os prontos vêm da API: recarregar a
> página não os perde. Detalhes: [../backend/docs/PEDIDOS.md](../backend/docs/PEDIDOS.md).

## A regra que governa esta camada

> A interface conhece **Pixel Art**. Nada mais.

O rótulo vira uma *capacidade* (`text_to_image.pixel`) em um único arquivo —
[`src/types.ts`](src/types.ts). Daí para baixo, nenhum componente sabe o que é
um motor.

Você **não** vai encontrar aqui:

```ts
if (mode === "pixel") useSDXL();   // ERRADO
```

E sim:

```ts
capability: MODES[mode].capability   // "text_to_image.pixel"
```

Qual gaveta atende o pedido é decisão exclusiva do backend — hoje, a desenhista,
sem fallback.

## Rodar

Precisa do backend no ar:

```powershell
# terminal 1
cd ..\backend
.\.venv\Scripts\python.exe -m uvicorn assetflow.main:app --reload

# terminal 2
cd frontend
npm install
npm run dev
```

Abra <http://localhost:5173>.

O Vite encaminha `/api` para `http://127.0.0.1:8000` — o frontend só fala com
a própria origem, então não há CORS nem host de backend no código. Para
apontar para outro backend: `ASSETFLOW_API_URL=http://outro:8000 npm run dev`.

## Estrutura

```text
src/
├── types.ts                    # modos, estados e a tradução modo → capacidade
├── services/generationApi.ts   # ÚNICO lugar que fala HTTP
├── hooks/useGenerationJob.ts   # criar job + polling + estados
├── components/
│   ├── Header.tsx
│   ├── GeneratorHero.tsx
│   ├── GenerationModeSelector.tsx
│   │   └── ModeCard.tsx
│   ├── PromptInput.tsx
│   ├── GenerateButton.tsx
│   ├── GenerationStatus.tsx
│   ├── GenerationResult.tsx
│   │   ├── AssetPreview.tsx
│   │   └── ResultActions.tsx
│   ├── GenerationError.tsx
│   ├── EmptyResult.tsx
│   └── SessionHistory.tsx
├── App.tsx
└── styles.css
```

## Detalhes que valem saber

**Pixel-perfect.** Um asset de 64×64 é exibido a ~420px com
`image-rendering: pixelated`. Sem isso o navegador interpola e a Pixel Art
parece borrada/defeituosa. Arte 2D usa suavização normal. A escolha é
automática, derivada do modo — não é opção do usuário.

**Loader indeterminado.** O backend ainda não publica progresso confiável por
etapa, então a tela não inventa percentual. Quando publicar, muda só
`GenerationStatus`.

**Polling a cada 1,2s.** Isolado em `useGenerationJob`. Trocar por
WebSocket/SSE depois é mexer nesse arquivo e em mais nenhum.

**Erros.** `CUDA OOM` e `EngineResolverException` nunca chegam à tela. O
serviço de API traduz o código normalizado do backend para uma frase útil; o
detalhe técnico fica no log do servidor.

**Profile junto da capacidade.** O pedido envia `capability` *e* `profile`
(`pixel_character_64`). O profile é quem carrega a
resolução lógica de 64×64 e a paleta de 16 cores — e, como profiles nunca
citam motor, a independência continua intacta.

## O que não existe ainda

Editor, camadas, paleta editável, crop, animação e spritesheet ficaram
deliberadamente de fora desta etapa. O espaço visual para eles está previsto,
mas construir agora atrapalharia o objetivo: provar o caminho
`web → capacidade → job → motor modular → imagem`.
