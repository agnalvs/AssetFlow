/**
 * Tipos da interface.
 *
 * Regra arquitetural (plano da tela §32 e §46): esta camada conhece apenas
 * **Pixel Art** e **2D Normal**, traduzidos para *capacidades*. Em nenhum
 * lugar do frontend existe — nem pode existir — o nome de um motor ou modelo.
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

/** Resposta de `POST /api/generation/prompt/preview`, e o campo `prompt` do job. */
export interface PromptPreview {
  profile: string;
  capability: string;
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

export interface CreateJobPayload {
  project_id: string;
  capability: string;
  profile: string;
  prompt: string;
  output?: { variations?: number };
  /** Semântica corrigida à mão. Presente, ela substitui o PromptBuilder. */
  semantic_prompt?: SemanticPrompt;
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

export interface Job {
  job_id: string;
  status: string;
  progress: number;
  stage: string;
  asset: Asset | null;
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
