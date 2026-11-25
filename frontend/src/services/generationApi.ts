/**
 * Serviço de API (plano da tela §30).
 *
 * Nenhum componente faz `fetch` direto: tudo passa por aqui. Isso mantém o
 * contrato com o backend em um lugar só e permite trocar polling por
 * WebSocket/SSE mais tarde sem tocar na interface.
 *
 * Desde a Fase B do plano do app a tela não cria jobs: ela cria **pedidos**
 * (`/api/pedidos`), que o Claude desenha pela conversa. A pré-visualização é a
 * dos pedidos, para o spec mostrado ser o mesmo que fica gravado.
 */

import {
  type AssetSelection,
  selectionToOutput,
} from "../components/AssetControls";
import {
  type GenerationMode,
  type Liberdade,
  MODES,
  type Pedido,
  type PedidoCorpo,
  type PedidoDetalhe,
  type PedidoLista,
  type PromptPreview,
  type SemanticPrompt,
  type SpecOverrides,
} from "../types";

const PEDIDOS_URL = "/api/pedidos";

/**
 * O corpo de um pedido, montado em um lugar só.
 *
 * A pré-visualização e a criação mandam **o mesmo objeto**: é isso que faz o
 * painel descrever o pedido que vai ser gravado, e não um parecido. Sem
 * motor e sem projeto: os dois são do app, e o backend os põe.
 */
export function buildPedidoPayload(input: {
  mode: GenerationMode;
  prompt: string;
  selection?: AssetSelection | null;
  spec?: SpecOverrides | null;
  semantic?: SemanticPrompt | null;
  liberdade?: Liberdade;
  direcaoDeArte?: string;
}): PedidoCorpo {
  const config = MODES[input.mode];
  const selection = input.selection ?? null;
  const direcao = input.direcaoDeArte?.trim();
  return {
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
    ...(input.liberdade ? { liberdade: input.liberdade } : {}),
    ...(direcao ? { direcao_de_arte: direcao } : {}),
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
    // O backend devolve erro normalizado {code, message}. A mensagem crua só
    // aparece quando ela é escrita para ser lida (ver `messageForCode`).
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

// ---------------------------------------------------------------------------
// Pedidos (Fase B do plano do app)
// ---------------------------------------------------------------------------

/** O que o AssetFlow entenderia deste pedido — o spec que a criação grava. */
export function previaPedido(payload: PedidoCorpo, signal?: AbortSignal): Promise<PromptPreview> {
  return request<PromptPreview>(`${PEDIDOS_URL}/previa`, {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

/** Cria um pedido na fila. */
export function criarPedido(payload: PedidoCorpo): Promise<PedidoDetalhe> {
  return request<PedidoDetalhe>(PEDIDOS_URL, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Os pedidos do projeto do app, do mais novo para o mais antigo. */
export function listarPedidos(signal?: AbortSignal): Promise<PedidoLista> {
  return request<PedidoLista>(`${PEDIDOS_URL}?limit=40`, { signal });
}

/** O pedido inteiro, com o corpo que a tela mandou. */
export function detalharPedido(id: string): Promise<PedidoDetalhe> {
  return request<PedidoDetalhe>(`${PEDIDOS_URL}/${encodeURIComponent(id)}`);
}

/** Cancela um pedido na fila ou em desenho. */
export function cancelarPedido(id: string): Promise<Pedido> {
  return request<Pedido>(`${PEDIDOS_URL}/${encodeURIComponent(id)}/cancelar`, {
    method: "POST",
  });
}

/** Tira a reserva de um pedido em desenho e o devolve à fila, sem cancelar. */
export function devolverPedido(id: string): Promise<Pedido> {
  return request<Pedido>(`${PEDIDOS_URL}/${encodeURIComponent(id)}/devolver`, {
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
  // Estes códigos trazem frase escrita para ser lida por quem pediu: o
  // resolver recusa em português e explica o motivo (plano T→J §30), e a fila
  // de pedidos diz o que fazer quando o arquivo está ocupado ou danificado.
  // Trocá-las pela frase genérica esconderia justamente a informação útil.
  const legiveis = new Set([
    "invalid_request",
    "fila_indisponivel",
    "fila_corrompida",
    "pedido_nao_encontrado",
    "pedido_em_outra_situacao",
  ]);
  if (legiveis.has(code) && reason) return reason;

  switch (code) {
    case "no_engine_available":
    case "engine_unavailable":
      return "O gerador está indisponível no momento. Tente novamente em instantes.";
    case "invalid_request":
      return "Revise a descrição e tente de novo.";
    case "fila_indisponivel":
    case "fila_corrompida":
      return "A fila de pedidos não respondeu. Tente de novo em instantes.";
    case "profile_not_found":
    case "pipeline_not_found":
      return "Esse tipo de asset não está disponível no momento.";
    case "network_error":
      return "Não foi possível falar com o servidor do AssetFlow.";
    case "aborted":
      return "requisição cancelada";
    default:
      return "Não conseguimos concluir este pedido. Tente novamente ou altere a descrição.";
  }
}
