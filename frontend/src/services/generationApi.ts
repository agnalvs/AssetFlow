/**
 * Serviço de API (plano da tela §30).
 *
 * Nenhum componente faz `fetch` direto: tudo passa por aqui. Isso mantém o
 * contrato com o backend em um lugar só e permite trocar polling por
 * WebSocket/SSE mais tarde sem tocar na interface.
 */

import {
  type AssetSelection,
  selectionToOutput,
} from "../components/AssetControls";
import {
  type CreateJobPayload,
  type EngineCatalogEntry,
  type EngineSelection,
  type GenerationMode,
  type Job,
  type JobSubmission,
  MODES,
  type PromptPreview,
  type SemanticPrompt,
  type SpecOverrides,
} from "../types";

const BASE_URL = "/api/generation";

/** Identidade de projeto do playground, estável entre recarregamentos. */
export function getProjectId(): string {
  const key = "assetflow.project_id";
  try {
    const stored = window.localStorage.getItem(key);
    if (stored) return stored;
    const created = `web_${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem(key, created);
    return created;
  } catch {
    return "web_playground";
  }
}

/**
 * O corpo enviado ao backend, montado em um lugar só.
 *
 * A pré-visualização e a geração precisam mandar **o mesmo objeto**: é isso
 * que faz o painel descrever a geração que vai acontecer, e não uma parecida.
 * Duas montagens separadas divergiriam no primeiro campo novo.
 */
export function buildJobPayload(input: {
  mode: GenerationMode;
  prompt: string;
  selection?: AssetSelection | null;
  spec?: SpecOverrides | null;
  semantic?: SemanticPrompt | null;
  engine?: EngineSelection | null;
}): CreateJobPayload {
  const config = MODES[input.mode];
  const selection = input.selection ?? null;
  return {
    project_id: getProjectId(),
    // O frontend pede uma CAPACIDADE, nunca um motor.
    capability: config.capability,
    profile: config.profile,
    prompt: input.prompt.trim(),
    // Controles em "Automático" não entram no corpo: ausência é o que o
    // backend lê como "não opino", e é assim que o classificador e o profile
    // continuam podendo responder (plano T→J §23).
    ...(selection?.assetType ? { asset_type: selection.assetType } : {}),
    output: selection ? selectionToOutput(selection) : { variations: 1 },
    ...(input.spec ? { spec_overrides: input.spec } : {}),
    ...(input.semantic ? { semantic_prompt: input.semantic } : {}),
    // Auto vai só com o modo. Mandar um `engine_id` junto de `auto` seria
    // dizer "escolha por mim, mas use este" — e o backend, corretamente,
    // trataria isso como escolha manual.
    engine: input.engine?.engineId
      ? { mode: "manual", engine_id: input.engine.engineId }
      : { mode: "auto" },
  };
}

/** Um campo recusado pelo backend, no formato normalizado do erro 422. */
export interface FieldError {
  campo: string;
  erro: string;
}

/** Erro de aplicação: mensagem já apresentável ao usuário. */
export class GenerationApiError extends Error {
  readonly code: string;
  /**
   * Campos recusados, quando o backend soube dizer quais.
   *
   * Só o editor de JSON usa isto. Para o resto da tela, o contrato continua
   * sendo o de sempre: uma frase pronta, sem detalhe técnico (plano §40).
   */
  readonly fields: readonly FieldError[];

  constructor(message: string, code = "unknown_error", fields: readonly FieldError[] = []) {
    super(message);
    this.name = "GenerationApiError";
    this.code = code;
    this.fields = fields;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (caught) {
    // Cancelar uma requisição em voo é operação normal aqui: a
    // pré-visualização acompanha a digitação e aborta a anterior a cada
    // tecla. Traduzir isso para "o servidor não respondeu" encheria a tela
    // de erro justamente quando tudo está funcionando.
    if (caught instanceof DOMException && caught.name === "AbortError") {
      throw new GenerationApiError("requisição cancelada", "aborted");
    }
    throw new GenerationApiError(
      "Não foi possível falar com o servidor do AssetFlow.",
      "network_error",
    );
  }

  if (!response.ok) {
    // O backend devolve erro normalizado {code, message}. Mesmo assim, a
    // mensagem técnica nunca é exibida crua ao usuário (plano da tela §40).
    let code = "unknown_error";
    let fields: FieldError[] = [];
    let reason: string | undefined;
    try {
      const body = (await response.json()) as {
        code?: string;
        message?: string;
        detail?: { errors?: FieldError[] };
      };
      if (body?.code) code = body.code;
      if (body?.message) reason = body.message;
      if (body?.detail?.errors) fields = body.detail.errors;
    } catch {
      /* resposta sem corpo JSON */
    }
    throw new GenerationApiError(messageForCode(code, reason), code, fields);
  }

  return (await response.json()) as T;
}

/** Cria um job de geração. Retorna imediatamente, com status `queued`. */
export function createGenerationJob(payload: CreateJobPayload): Promise<JobSubmission> {
  return request<JobSubmission>(`${BASE_URL}/jobs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Mostra o que o AssetFlow entenderia deste pedido, sem gerar nada.
 *
 * Recebe **o mesmo payload** do `createGenerationJob` de propósito: a
 * pergunta é "o que aconteceria se eu mandasse isto?", e ela só tem valor se
 * for feita com o objeto que seria mandado. O backend garante o outro lado —
 * as duas rotas resolvem a semântica pela mesma função.
 */
export function previewPrompt(
  payload: CreateJobPayload,
  signal?: AbortSignal,
): Promise<PromptPreview> {
  return request<PromptPreview>(`${BASE_URL}/prompt/preview`, {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

/**
 * O catálogo de motores oferecíveis (plano de motores §6).
 *
 * A tela desenha o seletor inteiro a partir desta resposta — nomes, resumos,
 * selos e disponibilidade —, e é isso que permite acrescentar uma gaveta no
 * backend sem tocar em nenhum componente.
 *
 * O filtro por capacidade importa: em Pixel Art e em 2D convencional os
 * motores disponíveis não são os mesmos, e oferecer um motor que o backend
 * vai recusar é pior do que não oferecer.
 */
export function listEngineCatalog(
  capability?: string,
  signal?: AbortSignal,
): Promise<{ items: EngineCatalogEntry[]; capability: string | null }> {
  const query = capability ? `?capability=${encodeURIComponent(capability)}` : "";
  return request<{ items: EngineCatalogEntry[]; capability: string | null }>(
    `${BASE_URL}/engines/catalog${query}`,
    { signal },
  );
}

/** Consulta o estado atual de um job. */
export function getGenerationJob(jobId: string): Promise<Job> {
  return request<Job>(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}`);
}

/** Pede o cancelamento de um job em andamento. */
export function cancelGenerationJob(jobId: string): Promise<Job> {
  return request<Job>(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
  });
}

/**
 * Traduz o código de erro do backend para uma frase útil.
 *
 * O usuário nunca vê "CUDA OOM" nem "EngineResolverException": o detalhe
 * técnico fica no log do backend.
 */
function messageForCode(code: string, reason?: string): string {
  // `invalid_request` é o único código cuja mensagem do backend é escrita
  // para ser lida por quem pediu: o resolver recusa em português e explica o
  // motivo — "resolução 4×4 fora do suportado" (plano T→J §30). Trocá-la pela
  // frase genérica esconderia justamente a informação que o §30 existe para
  // dar. Todos os outros continuam traduzidos aqui, porque a mensagem crua
  // deles é técnica ("CUDA OOM") e não serve a ninguém na tela.
  if (code === "invalid_request" && reason) return reason;

  switch (code) {
    // Quando a pessoa escolheu o motor, a mensagem genérica esconde a única
    // coisa acionável: o motor escolhido é que não está de pé, e trocar de
    // motor resolve. O backend não troca sozinho de propósito (§25, regra 1).
    case "engine_not_found":
    case "engine_disabled":
      return reason
        ? `${reason}. Escolha outro motor ou volte para Automático.`
        : "O motor escolhido não está disponível. Escolha outro ou volte para Automático.";
    case "no_engine_available":
    case "engine_unavailable":
      return "O gerador está indisponível no momento. Tente novamente em instantes.";
    case "engine_timeout":
      return "A geração demorou mais do que o esperado. Tente novamente.";
    case "engine_out_of_memory":
      return "Não há recursos suficientes agora. Tente novamente em instantes.";
    case "invalid_request":
      return "Revise a descrição e tente de novo.";
    case "profile_not_found":
    case "pipeline_not_found":
      return "Esse tipo de asset não está disponível no momento.";
    case "network_error":
      return "Não foi possível falar com o servidor do AssetFlow.";
    case "aborted":
      return "requisição cancelada";
    default:
      return "Não conseguimos concluir esta geração. Tente novamente ou altere sua descrição.";
  }
}
