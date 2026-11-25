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

/** Estados genéricos do fluxo, independentes de backend. */
export type GenerationState =
  | "idle"
  | "queued"
  | "generating"
  | "processing"
  | "completed"
  | "failed";

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

export interface CreateJobPayload {
  project_id: string;
  capability: string;
  profile: string;
  prompt: string;
  /** Tipo escolhido no dropdown; ausente = automático (classificador decide). */
  asset_type?: AssetTypeId;
  output?: OutputSelection;
  /** Correção manual do spec — ganha de tudo, inclusive dos controles acima. */
  spec_overrides?: SpecOverrides;
  /** Semântica corrigida à mão. Presente, ela substitui o PromptBuilder. */
  semantic_prompt?: SemanticPrompt;
  /**
   * O motor escolhido. Em `auto` o campo vai só com o modo: um `engine_id`
   * junto com `auto` seria dizer duas coisas ao mesmo tempo.
   *
   * Não existe um campo irmão para a otimização. Ela não é opção do pedido —
   * é parte do pipeline, e o servidor a impõe (plano Optimizer §33 e §34).
   */
  engine?: { mode: "auto" | "manual"; engine_id?: string };
}

export interface JobSubmission {
  job_id: string;
  status: string;
  capability: string;
  profile: string | null;
  pipeline: string;
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

/**
 * Motor pedido × motor usado (plano de motores §25, regra 3).
 *
 * A regra exige que a tela mostre os dois, mais o modelo carregado. Um
 * fallback silencioso — em que a pessoa escolhe um motor e recebe o resultado
 * de outro sem saber — é exatamente o que ela existe para impedir.
 */
export interface EngineSelectionView {
  mode: "auto" | "manual";
  requested_engine_id: string | null;
  reason: string;
  allow_fallback: boolean;
  resolved_engine_id: string | null;
  resolved_model_id: string | null;
  resolved_engine_version: string | null;
  fallback_used: boolean;
  attempted_engines: string[];
}

export interface Job {
  job_id: string;
  status: string;
  progress: number;
  stage: string;
  asset: Asset | null;
  engine_selection: EngineSelectionView;
  /**
   * O asset não veio do gerador preferido para este modo (plano §44).
   *
   * É um booleano, e é assim que tem de ser: a interface precisa avisar que
   * houve substituição sem descobrir **quem** substituiu quem. O backend
   * também manda a frase pronta em `warnings`, mas ela cita o id do motor —
   * exibi-la aqui furaria a regra de a tela não conhecer motor (§32/§46).
   */
  fallback_used: boolean;
  /** O que o AssetFlow entendeu. Chega preenchido quando o job termina. */
  prompt: PromptPreview | null;
  /**
   * Avisos do backend, já escritos para serem lidos.
   *
   * Eles não chegavam à tela, e a ausência tinha um custo concreto: um pedido
   * saía como uma forma genérica, o backend avisava por quê, e a pessoa via só
   * o resultado estranho — sem nenhuma pista de que o sistema **sabia** o que
   * tinha acontecido.
   */
  warnings: string[];
  error: { code: string; message: string } | null;
}

/** Uma geração concluída, guardada na sessão (plano da tela §25). */
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

/**
 * Traduz o status técnico do job para o estado da interface.
 *
 * Os nomes internos do backend (`postprocessing`, `cancel_requested`) não
 * vazam para os componentes: eles só conhecem :type:`GenerationState`.
 */
export function toGenerationState(status: string): GenerationState {
  switch (status) {
    case "queued":
      return "queued";
    case "running":
    case "generating":
      return "generating";
    case "postprocessing":
      return "processing";
    case "completed":
      return "completed";
    case "failed":
    case "cancelled":
    case "cancel_requested":
      return "failed";
    default:
      return "idle";
  }
}
