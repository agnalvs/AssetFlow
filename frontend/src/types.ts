/**
 * Tipos da interface.
 *
 * Regra arquitetural (plano da tela §32 e §46, atualizada pelo plano de
 * motores §4 e §24): esta camada conhece **Pixel Art** e **2D Normal**,
 * traduzidos para *capacidades*.
 *
 Sobre motores, a tela **oferece** a escolha mas continua sem **conhecer**
 * nenhum: a lista vem inteira de `GET /api/generation/engines/catalog`, com
 * id, nome, resumo, selos e disponibilidade. Nenhum id de motor está escrito
 * neste código.
 *
 * Existe **uma** pergunta de tecnologia, e é essa (plano Optimizer §25 e §26):
 *
 *     Com qual motor?   Automático | FLUX | SD-πXL | Pixel Forge | ...
 *
 * Não há um seletor de "método de criação", e a ausência é deliberada. Ele já
 * existiu, oferecendo "Modelo de imagem" e "Agente Pixel" como se fossem
 * alternativas — e não são: o motor produz a imagem, e o AssetFlow Pixel
 * Optimizer corrige a imagem produzida, sempre, em toda geração (§46 e §79).
 * Perguntar qual dos dois usar era pedir à pessoa que escolhesse entre duas
 * metades do mesmo pipeline.
 *
 * O Optimizer, por isso, **não** aparece em lista nenhuma da interface (§76).
 * Ele aparece no resultado, contando o que fez.
 *
 * A diferença importa. Se amanhã entrar uma gaveta nova, ela aparece no
 * seletor sozinha; se `flux-pixel-v1` estivesse escrito aqui, cada motor novo
 * exigiria uma alteração no frontend — o "hardcode de nomes de modelos em
 * múltiplos lugares" que o §24 lista entre as coisas a não fazer.
 */

/** Os dois modos de criação oferecidos ao usuário. */
export type GenerationMode = "pixel" | "studio";

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
  studio: {
    id: "studio",
    label: "2D Normal",
    description: "Assets ilustrados em estilos 2D convencionais.",
    capability: "text_to_image.general",
    profile: "studio_character",
    placeholder:
      "Ex.: Um guerreiro de fantasia usando armadura azul, corpo inteiro, vista lateral, estilo cartoon 2D.",
    pixelated: false,
  },
};

export const MODE_LIST: readonly ModeConfig[] = [MODES.pixel, MODES.studio];

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
// A escolha de tecnologia (plano Optimizer §25 e §26)
// ---------------------------------------------------------------------------

/**
 * O que a tela escolheu sobre **com o quê** criar.
 *
 * Um campo só, e é esse o ponto. Este objeto já teve quatro — método, motor,
 * agente e modo de qualidade —, e três deles descreviam uma bifurcação que
 * não existe mais (plano Optimizer §27).
 *
 * `engineId` a `null` significa "Automático": o backend escolhe e explica o
 * motivo antes de gerar.
 */
export interface CreationSelection {
  engineId: string | null;
}

export const AUTO_CREATION: CreationSelection = { engineId: null };

// ---------------------------------------------------------------------------
// Catálogo de motores (plano de motores §6) — o que o seletor de motor desenha
// ---------------------------------------------------------------------------

/** A tecnologia por trás da gaveta. A tela usa só para agrupar e rotular. */
export type EngineFamily =
  | "diffusion"
  | "native_sprite"
  | "optimization"
  | "agentic"
  | "procedural";

export type EngineQualityTier = "draft" | "standard" | "high" | "reference";

export type EngineSpeedTier = "instant" | "fast" | "moderate" | "slow" | "very_slow";

/**
 * Um motor como o backend o apresenta.
 *
 * Espelha `EngineCatalogEntry`. Todo texto exibido no seletor sai daqui —
 * inclusive o resumo e os selos —, e é por isso que a tela pode oferecer um
 * motor que ela não conhece.
 */
export interface EngineCatalogEntry {
  engine_id: string;
  display_name: string;
  engine_family: EngineFamily;
  version: string;
  description: string;
  summary: string;
  highlights: string[];
  badges: string[];

  supports_pixel_art: boolean;
  supports_image_editing: boolean;
  supports_reference_image: boolean;
  supports_palette_control: boolean;
  supports_exact_resolution: boolean;
  supports_background_transparency: boolean;
  supports_seed: boolean;
  supported_logical_sizes: number[];

  quality_tier: EngineQualityTier;
  speed_tier: EngineSpeedTier;
  license_type: string;

  /** `active` | `disabled` | `unavailable` | `incompatible`. */
  status: string;
  /** Dá para escolher este motor agora? */
  available: boolean;
  /** Por que não dá, em português. `null` quando dá. */
  unavailable_reason: string | null;

  capabilities: string[];
  model_id: string | null;
  provider: string;
  gpu_required: boolean;
  recommended_vram_mb: number;
  recommended_timeout_s: number;
}

/** A resposta de `GET /api/generation/engines/catalog`. */
export interface EngineCatalogResponse {
  items: EngineCatalogEntry[];
  capability: string | null;
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
  /** Reabrir uma geração antiga precisa reabrir o aviso junto com ela. */
  fallbackUsed: boolean;
  /** Quem gerou esta entrada — é o que torna o histórico comparável. */
  engine: EngineSelectionView | null;
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
