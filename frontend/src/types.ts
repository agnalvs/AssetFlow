/**
 * Tipos da interface.
 *
 * Regra arquitetural (plano da tela §32 e §46, atualizada pelo plano de
 * motores §4 e §24): esta camada conhece **Pixel Art** e **2D Normal**,
 * traduzidos para *capacidades*.
 *
 * Sobre motores e métodos, a regra mudou de forma e não de espírito. A tela
 * **oferece** as escolhas — método de criação, e depois motor ou agente — mas
 * continua sem **conhecer** nenhum dos dois: as listas vêm inteiras de
 * `GET /api/generation/strategies`, com id, nome, resumo, selos e
 * disponibilidade. Nenhum id de motor está escrito neste código.
 *
 * A ordem das perguntas é a arquitetura (plano de correção §4 e §52):
 *
 *     1. Como criar?   Automático | Modelo de imagem | Agente Pixel
 *     2. Com o quê?    (só em Modelo) o motor / (só em Agente) o agente
 *
 * Antes disso havia um seletor só, chamado "Motor", com FLUX, SDXL e o agente
 * lado a lado — e a tela dizia à pessoa que as três coisas eram a mesma
 * categoria, quando não são.
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
// Métodos de criação (plano de correção §4 e §32)
// ---------------------------------------------------------------------------

/** Como o asset será criado. `auto` é a ausência de escolha, não um método. */
export type GenerationStrategyId = "auto" | "model" | "pixel_agent";

/** Quanto esforço o agente pode gastar (plano de correção §25). */
export type AgentQualityMode = "auto" | "fast" | "balanced" | "detailed";

/**
 * Um método de criação como o backend o apresenta.
 *
 * `selects_engine` e `selects_agent` são a decisão do §5 tomada no backend: é
 * ele que diz qual controle a tela deve mostrar depois desta escolha. A
 * alternativa — um `if id === "pixel_agent"` no React — poria no frontend uma
 * regra de arquitetura que não é dele.
 */
export interface StrategyDescriptor {
  id: GenerationStrategyId;
  display_name: string;
  summary: string;
  description: string;
  available: boolean;
  unavailable_reason: string | null;
  selects_engine: boolean;
  selects_agent: boolean;
  highlights: string[];
}

/** Um agente de desenho oferecido na tela. */
export interface AgentSummary {
  id: string;
  display_name: string;
  version: string;
  summary: string;
}

/** A resposta de `GET /api/generation/strategies` — tudo que o seletor usa. */
export interface StrategyCatalog {
  items: StrategyDescriptor[];
  engines: EngineCatalogEntry[];
  agents: AgentSummary[];
  quality_modes: AgentQualityMode[];
  capability: string | null;
}

/**
 * O que a tela escolheu sobre **como** criar.
 *
 * `engineId` só vale com `strategy === "model"`, e `agentId`/`quality` só com
 * `"pixel_agent"`. Mandar motor junto de agente é recusado pelo backend
 * (plano de correção §38) — e é assim que se descobre um bug de tela em vez
 * de gerar o asset errado em silêncio.
 */
export interface CreationSelection {
  strategy: GenerationStrategyId;
  engineId: string | null;
  agentId: string | null;
  quality: AgentQualityMode;
}

export const AUTO_CREATION: CreationSelection = {
  strategy: "auto",
  engineId: null,
  agentId: null,
  quality: "auto",
};

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
 * Como este asset será criado (plano de correção §7 e §41).
 *
 * `requested` guarda o que a pessoa escolheu — inclusive `auto` — e `mode`
 * guarda o que isso virou. Os dois, porque sem o pedido original não há como
 * saber, olhando um job antigo, se o método foi decidido por alguém ou pelo
 * sistema.
 */
export interface ResolvedStrategy {
  requested: GenerationStrategyId;
  mode: "model" | "pixel_agent";
  reason: string;
}

/** A configuração do agente resolvida para este job. */
export interface ResolvedPixelAgent {
  agent_id: string;
  quality_mode: AgentQualityMode;
  max_iterations: number | null;
  auto_review: boolean;
}

/** Referência visual opcional do agente (plano de correção §39). */
export interface ResolvedConceptReference {
  enabled: boolean;
  engine_id: string | null;
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
  strategy: ResolvedStrategy;
  engine: ResolvedEngine;
  pixel_agent: ResolvedPixelAgent;
  concept_reference: ResolvedConceptReference;
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
  strategy?: GenerationStrategyId | null;
  agent_id?: string | null;
  agent_quality?: AgentQualityMode | null;
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
  /** Como criar. Ausente = `auto`, que o backend resolve com a política. */
  generation_strategy?: { mode: GenerationStrategyId };
  /** Configuração do agente. Só enviada quando o método é o dele. */
  pixel_agent?: { quality_mode: AgentQualityMode; agent_id?: string };
  /**
   * O motor escolhido. Em `auto` o campo vai só com o modo: um `engine_id`
   * junto com `auto` seria dizer duas coisas ao mesmo tempo.
   *
   * **Nunca** enviado junto com `pixel_agent`: o backend recusa o pedido
   * contraditório (plano de correção §38), e é assim que um bug de tela
   * aparece como erro em vez de virar o asset errado.
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
  /** Ampliação inteira só para visualizar — nunca é o asset (plano Pixel §73). */
  preview_url: string | null;
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
  /** O método pedido e o resolvido (plano de correção §41 e §42). */
  requested_strategy: GenerationStrategyId;
  resolved_strategy: "model" | "pixel_agent";
  strategy_reason: string;
  /** O agente, quando foi ele quem desenhou. `null` na geração por modelo. */
  agent: { id: string; version: string } | null;

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
   * de "house" saía como uma forma genérica, o backend avisava que o agente
   * não conhecia o objeto, e a pessoa via só o resultado estranho — sem
   * nenhuma pista de que o sistema **sabia** o que tinha acontecido.
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
