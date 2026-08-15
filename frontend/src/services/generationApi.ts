/**
 * Serviço de API (plano da tela §30).
 *
 * Nenhum componente faz `fetch` direto: tudo passa por aqui. Isso mantém o
 * contrato com o backend em um lugar só e permite trocar polling por
 * WebSocket/SSE mais tarde sem tocar na interface.
 */

import type { CreateJobPayload, Job, JobSubmission } from "../types";

const BASE_URL = "/api/generation";

/** Erro de aplicação: mensagem já apresentável ao usuário. */
export class GenerationApiError extends Error {
  readonly code: string;

  constructor(message: string, code = "unknown_error") {
    super(message);
    this.name = "GenerationApiError";
    this.code = code;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new GenerationApiError(
      "Não foi possível falar com o servidor do AssetFlow.",
      "network_error",
    );
  }

  if (!response.ok) {
    // O backend devolve erro normalizado {code, message}. Mesmo assim, a
    // mensagem técnica nunca é exibida crua ao usuário (plano da tela §40).
    let code = "unknown_error";
    try {
      const body = (await response.json()) as { code?: string };
      if (body?.code) code = body.code;
    } catch {
      /* resposta sem corpo JSON */
    }
    throw new GenerationApiError(messageForCode(code), code);
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
function messageForCode(code: string): string {
  switch (code) {
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
    default:
      return "Não conseguimos concluir esta geração. Tente novamente ou altere sua descrição.";
  }
}
