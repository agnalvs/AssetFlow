/**
 * Tipos da interface.
 *
 * Regra arquitetural (plano da tela §32 e §46): esta camada conhece **Pixel
 * Art**, traduzido para uma *capacidade*, e mais nada.
 *
 * Desde a Fase A do plano do app (backend/docs/PLANO_APP_DESENHISTA.md) o
 * AssetFlow tem um gerador só, a desenhista, e a tela não pergunta mais nada
 * de tecnologia: saíram o seletor de motor, o modo "Automático" e o modo 2D
 * Normal. Nenhum id de motor está escrito neste código — e agora nenhum
 * aparece na tela.
 *
 * O AssetFlow Pixel Optimizer também não aparece em lista nenhuma (§76): ele
 * corrige toda geração, e aparece no resultado contando o que fez.
 */

/** O modo de criação: o app só gera Pixel Art (Fase A do plano do app). */
export type GenerationMode = "pixel";

/** Configuração de cada modo. Note que só há capacidade e profile aqui. */
export interface ModeConfig {
  readonly id: GenerationMode;
  readonly label: string;
  readonly description: string;
  /** Capacidade pedida ao backend, ex.: `text_to_image.pixel`. */
  readonly capability: string;
  /** Profile do AssetFlow — define resolução lógica, paleta e pipeline. */
  readonly profile: string;
  readonly placeholder: string;
  /** Se `true`, o preview usa nearest-neighbor (`image-rendering: pixelated`). */
  readonly pixelated: boolean;
}

export const MODES: Readonly<Record<GenerationMode, ModeConfig>> = {
  pixel: {
    id: "pixel",
    label: "Pixel Art",
    description: "Sprites e assets com estética pixel-perfect.",
    capability: "text_to_image.pixel",
    profile: "pixel_character_64",
    placeholder:
      "Ex.: Um cavaleiro medieval com armadura azul, espada curta, visto de lado, estilo RPG.",
    pixelated: true,
  },
};

// ---------------------------------------------------------------------------
// Contratos da API (espelham o backend, sem qualquer detalhe de motor)
// ---------------------------------------------------------------------------

/**
 * A leitura que o AssetFlow faz da descrição (plano §26 e §28).
 *
 * Espelha o `SemanticPrompt` do backend. É o objeto que o painel mostra e que
 * pode ser corrigido à mão: nenhum campo aqui é específico de motor, e por
 * isso a interface pode exibi-lo inteiro sem descobrir o que gera as imagens.
 */
export interface SemanticComposition {
  single_subject: boolean;
  centered: boolean;
  full_body: boolean | null;
  isolated_background: boolean;
  margin_ratio: number | null;
}

export interface SemanticTechnical {
  clean_silhouette: boolean;
  sharp_edges: boolean | null;
  limited_palette: number | null;
  no_text: boolean;
  no_watermark: boolean;
  transparent_background: boolean;
}

export interface SemanticPrompt {
  subject: string;
  medium: string;
  style: string | null;
  view: string | null;
  pose: string | null;
  appearance: Record<string, string>;
  details: string[];
  avoid: string[];
  composition: SemanticComposition;
  technical: SemanticTechnical;
  extra: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Final Resolved Spec — o contrato que a geração executa (plano T→J §15)
// ---------------------------------------------------------------------------

/**
 * De onde veio cada valor do spec (plano T→J §16).
 *
 * A tela usa isto para não mentir: mostrar "32 × 32" sem dizer se o número
 * foi pedido ou herdado do profile é o que fazia ninguém perceber que o
 * pedido tinha sido ignorado.
 */
export type SpecSource =
  | "manual_override"
  | "explicit_prompt"
  | "ui_selection"
  | "inference"
  | "category_inference"
  | "profile_default"
  | "global_default";

export type AssetTypeId =
  | "character"
  | "prop"
  | "background"
  | "tile"
  | "tileset"
  | "spritesheet"
  | "icon"
  | "effect"
  | "ui"
  | "raw";

export interface ResolvedAsset {
  type: AssetTypeId;
  subject: string;
  category: string | null;
  mode: string;
}

export interface Resolution {
  width: number;
  height: number;
}

export interface ResolvedPalette {
  mode: "max_colors" | "locked";
  max_colors: number | null;
  colors: string[];
}


/**
 * A forma do corpo do sujeito (pesquisa PixelLab).
 *
 * Eixo **diferente** de `asset.type`: um lobo e um cavaleiro são ambos
 * `character`, e só isto distingue quatro patas de duas pernas. `unknown` é
 * silêncio honesto — nada no pedido disse a forma, e o motor decide.
 */
export type BodyTypeId =
  | "unknown"
  | "humanoid"
  | "quadruped"
  | "avian"
  | "aquatic"
  | "serpentine"
  | "amorphous";

export type DetailLevelId = "auto" | "low" | "medium" | "high";
export type OutlineModeId =
  | "auto"
  | "none"
  | "black"
  | "single_color"
  | "selective"
  | "adaptive_dark";
export type ShadingModeId = "auto" | "flat" | "basic" | "medium" | "detailed";

/**
 * A intenção de estilo.
 *
 * Tudo aqui é **orientação**, nunca garantia: o motor tenta, o Pixel Optimizer
 * melhora o que der, e o validador mede sem reprovar. É por isso que o painel
 * mostra estes campos com um selo diferente do de "32×32" — ver `constraints`
 * em `PromptPreview`.
 */
export interface ResolvedStyle {
  detail: DetailLevelId;
  outline: { mode: OutlineModeId; thickness: string; color: string | null };
  shading: { mode: ShadingModeId; light_direction: string | null };
}

/** O que o AssetFlow promete sobre um campo do spec. */
export type ConstraintClassId = "hard" | "semantic" | "style" | "engine_hint";

/**
 * O que acontece depois do motor (plano Optimizer §32).
 *
 * Um campo do spec que **ninguém escolhe**. Ele está aqui para ser mostrado,
 * não decidido: quando o teto de iterações mudar, ou quando o revisor por LLM
 * entrar, um job antigo continuará dizendo por qual pipeline passou.
 */
export interface ResolvedPixelPipeline {
  optimize: boolean;
  optimizer_id: string;
  max_iterations: number;
  reviewer: string;
  /** Sempre `true`: a otimização é imposta pelo servidor (§33 e §34). */
  forced: boolean;
}

/**
 * A decisão de motor deste pedido (plano de motores §5 e §17).
 *
 * Em `auto`, `engine_id` é o motor que a política **prefere** e `reason` diz
 * por quê — é o que a tela mostra em "Motor: X — Motivo: Y" antes de gerar.
 * Em `manual`, é o motor exigido, e `reason` fica vazio porque o motivo é
 * "foi pedido".
 */
export interface ResolvedEngine {
  selection_mode: "auto" | "manual";
  engine_id: string | null;
  allow_fallback: boolean;
  reason: string;
}

/**
 * Espelha o `FinalResolvedSpec` do backend.
 *
 * É o objeto que a aba "Interpretação" lê e o que a aba "JSON final" mostra —
 * e são o mesmo objeto de propósito (plano T→J §32 e §33): o resumo legível
 * não pode ser uma segunda leitura, feita do lado do cliente, que envelhece
 * em silêncio quando o backend mudar.
 */
export interface FinalResolvedSpec {
  spec_id: string;
  spec_hash: string;
  profile_id: string;
  pipeline_id: string;
  capability: string;
  asset: ResolvedAsset;
  logical_resolution: Resolution | null;
  render_resolution: Resolution;
  palette: ResolvedPalette | null;
  background: { mode: "transparent" | "solid" };
  composition: { view: string | null; centered: boolean; margin_ratio: number | null };
  /** Topologia corporal do sujeito — eixo diferente de `asset.type`. */
  character: { body_type: BodyTypeId };
  style: ResolvedStyle;
  generation: { variations: number; seed: number | null; quality: string };
  engine: ResolvedEngine;
  pixel_pipeline: ResolvedPixelPipeline;
  sources: Record<string, SpecSource>;
  notes: string[];
}

/**
 * Correção manual do spec — o nível de precedência mais alto (plano T→J §9).
 *
 * Esparso de propósito: o que não estiver aqui continua sendo resolvido pelo
 * backend. É o que a edição do JSON envia de volta.
 */
export interface SpecOverrides {
  asset_type?: AssetTypeId | null;
  subject?: string | null;
  category?: string | null;
  mode?: string | null;
  logical_width?: number | null;
  logical_height?: number | null;
  render_width?: number | null;
  render_height?: number | null;
  palette_max_colors?: number | null;
  background?: "transparent" | "solid" | null;
  view?: string | null;
  variations?: number | null;
  body_type?: BodyTypeId | null;
  detail?: DetailLevelId | null;
  outline?: OutlineModeId | null;
  outline_color?: string | null;
  shading?: ShadingModeId | null;
  light_direction?: string | null;
  engine_id?: string | null;
  engine_mode?: "auto" | "manual" | null;
  allow_engine_fallback?: boolean | null;
  // Não existe aqui um campo para o Pixel Optimizer, e a ausência é a regra:
  // correção manual é o nível mais alto entre as camadas que decidem o asset,
  // e a otimização não é uma delas — é parte do pipeline (§33 e §46).
}

/** Resposta de `POST /api/generation/prompt/preview`, e o campo `prompt` do job. */
export interface PromptPreview {
  profile: string;
  capability: string;
  /** O contrato final: o que será realmente executado. */
  resolved: FinalResolvedSpec;
  /**
   * O que o AssetFlow **promete** sobre cada campo, por caminho pontuado.
   *
   * Vem do backend, e não de uma tabela aqui, pela mesma razão do catálogo de
   * motores: é regra de arquitetura, e uma cópia no React envelheceria em
   * silêncio. Sem isso a tela exibe "32×32" e "contorno seletivo" com o mesmo
   * peso — e só o primeiro é garantido.
   */
  constraints: Record<string, ConstraintClassId>;
  semantic: SemanticPrompt;
  /**
   * Renderização neutra, para conferência humana. Um motor com dialeto
   * próprio relê a semântica e recebe outro texto — quem manda é `semantic`.
   */
  positive: string;
  negative: string | null;
  /** `builder` = o AssetFlow interpretou; `request` = veio corrigido daqui. */
  source: "builder" | "request";
}

/** O que os controles da tela selecionaram (plano T→J §18, nível 3). */
export interface OutputSelection {
  variations?: number;
  logical_width?: number;
  logical_height?: number;
  palette_size?: number;
  transparent?: boolean;
  view?: string;
  body_type?: BodyTypeId;
  detail?: DetailLevelId;
  outline?: OutlineModeId;
  shading?: ShadingModeId;
  light_direction?: string;
}

/**
 * Quanto o desenho pode se afastar da base (Fase B do plano do app). Muda só
 * a orientação que o Claude recebe; grade, cores, fundo e validação não mudam.
 */
export type Liberdade = "fiel" | "equilibrado" | "ousado";

/**
 * O corpo de um pedido, como a tela manda (`POST /api/pedidos` e a prévia).
 * Sem motor e sem projeto: os dois são do app.
 */
export interface PedidoCorpo {
  capability?: string;
  profile?: string;
  prompt?: string;
  /** Tipo escolhido no dropdown; ausente = automático (classificador decide). */
  asset_type?: AssetTypeId;
  output?: OutputSelection;
  /** Correção manual do spec — ganha de tudo, inclusive dos controles acima. */
  spec_overrides?: SpecOverrides;
  /** Semântica corrigida à mão. Presente, ela substitui o PromptBuilder. */
  semantic_prompt?: SemanticPrompt;
  liberdade?: Liberdade;
  /** Texto livre, entregue ao Claude como está. */
  direcao_de_arte?: string;
  /** Quem escolhe o conceito antes do desenho (lote 1). */
  modo_conceito?: ModoConceito;
  /** Num ajuste: o asset de origem e o que mudar. */
  origem_asset_id?: string;
  texto?: string;
}

/** O que a tela diz sobre um pedido. */
export type PedidoEtapa =
  | "na_fila"
  | "na_vez"
  | "desenhando"
  | "corrigindo"
  | "olhando"
  | "conceituando"
  | "escolha_conceito"
  | "pronto"
  | "nao_aprovado"
  | "cancelado";

/** Um pedido como a lista mostra (espelha `PedidoView`). */
export interface Pedido {
  id: string;
  tipo: "desenho" | "ajuste";
  situacao:
    | "pendente"
    | "em_desenho"
    | "em_revisao"
    | "escolhendo"
    | "concluido"
    | "falhou"
    | "cancelado";
  etapa: PedidoEtapa;
  texto: string;
  projeto: string;
  liberdade: Liberdade;
  direcao_de_arte: string | null;
  origem_asset_id: string | null;
  tentativas: number;
  max_tentativas: number;
  /** Remendos pedidos pelo olhar do Claude (Fase B2) e o teto. */
  remendos: number;
  max_remendos: number;
  /** Os desenhos do pedido aprovados no validador. */
  candidatos: string[];
  /** A linha do olhar do Claude que concluiu o pedido. */
  olhar: string | null;
  /** A etapa de conceito (lote 1). */
  modo_conceito: ModoConceito;
  conceitos: Conceito[];
  conceito: (Conceito & { indice?: number; editado?: boolean }) | null;
  motivo_conceito: string | null;
  recusados: number;
  /** Numa rodada da banca de teste. */
  banca: { rodada: string; item: string; ordem: number; total: number } | null;
  reservado_ate: string | null;
  motivo: string | null;
  criado_em: string;
  atualizado_em: string;
  resumo: {
    tipo_asset: string | null;
    grade: string | null;
    cores: number | null;
    fundo: string | null;
  };
  /** O desenho que concluiu o pedido, o que espera o olhar, ou o último não aprovado. */
  asset: Asset | null;
}

/** Quem escolhe o conceito antes do desenho (lote 1). */
export type ModoConceito = "eu_escolho" | "claude_escolhe" | "sem_conceito";

/** Um conceito: traço marcante, silhueta, objeto, pose e o que simplificar. */
export interface Conceito {
  traco: string;
  silhueta: string;
  objeto: string;
  pose: string;
  simplificar: string;
}

/** Uma rodada da banca de teste (espelha `RodadaView`). */
export interface Rodada {
  id: string;
  rotulo: string;
  modo_conceito: ModoConceito;
  criada_em: string;
  versao_base: string;
  git_commit: string | null;
  interruptores: Record<string, unknown>;
  itens: { item: string; pedido_id: string; ordem: number; etapa: string | null; asset_id: string | null }[];
  pronta: boolean;
  tokens_estimados: number;
}

export interface BancaResumo {
  itens: { id: string; texto: string; testa: string }[];
  rodadas: Rodada[];
}

/** Um lado de um par: a imagem e a etapa, nunca a rodada. */
export interface LadoDoPar {
  asset: Asset | null;
  etapa: string | null;
}

export interface ParDaBanca {
  item: string;
  texto: string;
  testa: string;
  esquerda: LadoDoPar;
  direita: LadoDoPar;
  escolha: "esquerda" | "direita" | "empate" | null;
  nota_esquerda: number | null;
  nota_direita: number | null;
}

export interface Comparacao {
  a: string;
  b: string;
  pares: ParDaBanca[];
  avaliados: number;
  resumo: Record<string, unknown> | null;
}

/** Uma lição do aprendizado (espelha `LicaoView`, Fase B2). */
export interface Licao {
  id: string;
  regra: string;
  errou: string;
  porque: string;
  tema: string;
  natureza: "forma" | "tecnica";
  tipo: string;
  corpo: string;
  porte: string;
  origem: "claude" | "autora";
  texto_da_autora: string | null;
  contador: number;
  ligada: boolean;
  asset_id: string | null;
  assets: string[];
  criada_em: string;
  atualizada_em: string;
}

export interface LicaoLista {
  items: Licao[];
  /** Tema -> natureza ("forma" ou "tecnica"). */
  temas: Record<string, string>;
}

/** A opinião da autora sobre um asset (espelha `OpiniaoView`). */
export interface Opiniao {
  asset_id: string;
  gostei: boolean;
  motivo: string | null;
  situacao: "nota" | "pendente" | "convertida";
  licao: string | null;
  em: string;
}

/** Uma linha da ficha de verificação (lote F5): uma regra da base e quem a conferiu. */
export interface FichaLinha {
  regra: string;
  verificacao: string;
  tipo: "construcao" | "medida" | "olhar" | "autora";
  resultado: "passou" | "nao_passou" | "sem_resposta" | "nao_se_aplica";
  detalhe: string;
  quem: string;
}

/** O Claude respondeu "sim" e a medida do app acusou o problema. */
export interface FichaDivergencia {
  pergunta: string;
  resposta: string | null;
  medida: string;
  detalhe: string;
}

/** A ficha de verificação de um asset (espelha `000_ficha.json`). */
export interface Ficha {
  linhas: FichaLinha[];
  respostas: Record<string, string | null>;
  sem_resposta: string[];
  divergencias: FichaDivergencia[];
}

/** Em que código a API e o servidor MCP estão (lote 11). */
export interface ProcessoDoServidor {
  processo: "api" | "mcp";
  pid: number;
  commit: string | null;
  subiu_em: string;
  desatualizado: boolean;
  motivo: string | null;
}

export interface EstadoDosServidores {
  codigo: { commit: string | null; alterado_em: string | null };
  processos: ProcessoDoServidor[];
  aviso: string | null;
}

/** Uma cópia de segurança de `backend/data/` (lote 9). */
export interface CopiaDeSeguranca {
  arquivo: string;
  nome: string;
  criada_em: string;
  tamanho: number;
  arquivos: number;
  commit: string | null;
}

export interface CopiasDeSeguranca {
  pasta: string;
  items: CopiaDeSeguranca[];
}

/** A grade lógica de um asset pronto, para o editor de pixels (lote 5). */
export interface EditorDados {
  pedido_id: string;
  asset_id: string;
  largura: number;
  altura: number;
  /** Chave da receita -> `#rrggbb`: as únicas cores do editor. */
  paleta: Record<string, string>;
  /** Linha a linha, `#rrggbb` ou `null` (transparente). */
  pixels: (string | null)[][];
}

/** O que a edição salva deu (espelha `EdicaoView`). */
export interface EdicaoResultado {
  aprovado: boolean;
  asset_id: string;
  mudados: number;
  ficaram: number;
  camada: string;
  pedido: Pedido | null;
  motivo: string | null;
  avisos: string[];
}

/** O pedido inteiro (espelha `PedidoDetalhe`). */
export interface PedidoDetalhe extends Pedido {
  corpo: PedidoCorpo;
  leitura: { resolved?: FinalResolvedSpec; semantic?: SemanticPrompt | null };
  eventos: { em: string; situacao: string; nota: string }[];
  ultimo_laudo: string | null;
}

/** A resposta de `GET /api/pedidos`. */
export interface PedidoLista {
  projeto: string;
  items: Pedido[];
}

export interface AssetVariant {
  id: string;
  index: number;
  uri: string;
  url: string | null;
  thumbnail_url: string | null;
  width: number;
  height: number;
  logical_width: number | null;
  logical_height: number | null;
  /**
   * Selo técnico do Pixel Exact (plano Pixel §79). `null` em arte 2D
   * convencional, onde a pergunta não faz sentido.
   *
   * Repare que a interface continua sem saber o que é um motor: ela recebe um
   * veredito já calculado pelo backend e apenas o mostra.
   */
  pixel_exact: boolean | null;
  quality_score: number | null;
  status: string | null;
  color_count: number | null;
  palette: string[];
  /**
   * O que o AssetFlow Pixel Optimizer fez com esta variação (§30).
   *
   * `null` em arte 2D convencional, onde ele não roda — e em geração Pixel
   * ele vem **sempre** preenchido, porque o estágio é obrigatório (§46). Um
   * bloco ausente em Pixel Art é sinal de asset gerado por uma versão
   * anterior, não de otimização pulada.
   */
  optimization: PixelOptimization | null;
  /** Ampliação inteira só para visualizar — nunca é o asset (plano Pixel §73). */
  preview_url: string | null;
}

/**
 * O laudo do Pixel Optimizer (plano Optimizer §30 e §48).
 *
 * `status` é o campo que a tela lê primeiro, e `skipped` é o que mais engana:
 * ele quer dizer "o Optimizer olhou e não havia o que corrigir", nunca "o
 * Optimizer foi pulado" (§46).
 */
export interface PixelOptimization {
  status:
    | "skipped"
    | "optimized"
    | "no_safe_repairs"
    | "exhausted"
    | "disabled";
  reviewer: string;
  iterations: number;
  tool_calls: number;
  pixels_changed: number;
  score_before: number | null;
  score_after: number | null;
  improvement: number | null;
  /** A correção foi descartada por ter piorado o asset (§20)? */
  reverted: boolean;
  duration_ms: number;
}

export interface Asset {
  id: string;
  job_id: string;
  type: string;
  mode: string;
  name: string;
  variants: AssetVariant[];
}

/** Um desenho pronto, como a área de resultado o mostra. */
export interface GenerationOutcome {
  /** O id do pedido que o produziu (serve de chave e de nome do arquivo). */
  jobId: string;
  mode: GenerationMode;
  prompt: string;
  variant: AssetVariant;
  /** A leitura que produziu esta imagem, quando a tela a tem. */
  preview: PromptPreview | null;
  /** Avisos sobre este desenho, prontos para exibir. */
  warnings: string[];
  /** O asset do desenho, para a opinião (só em pedido pronto). */
  assetId?: string | null;
  /** A linha do olhar do Claude que concluiu o pedido. */
  olhar?: string | null;
  /** O pedido do desenho, para a ficha de verificação (só em pedido pronto). */
  pedidoId?: string | null;
}

/** Um desenho pronto na faixa "Prontos" (plano da tela §25). */
export interface HistoryEntry {
  jobId: string;
  mode: GenerationMode;
  prompt: string;
  variant: AssetVariant;
  /** A leitura que produziu esta imagem, para poder reabri-la exatamente. */
  preview: PromptPreview | null;
  warnings: string[];
  createdAt: number;
}
