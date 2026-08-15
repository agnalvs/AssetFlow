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

export interface CreateJobPayload {
  project_id: string;
  capability: string;
  profile: string;
  prompt: string;
  output?: { variations?: number };
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
  error: { code: string; message: string } | null;
}

/** Uma geração concluída, guardada na sessão (plano da tela §25). */
export interface HistoryEntry {
  jobId: string;
  mode: GenerationMode;
  prompt: string;
  variant: AssetVariant;
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
