/**
 * A leitura que o AssetFlow faz da descrição, acompanhando a digitação.
 *
 * Entre a frase que a pessoa escreve e a imagem que sai existe uma
 * interpretação — vista, pose, composição, uma lista de coisas a evitar que
 * ninguém pediu. Ela sempre existiu; o que não existia era poder olhar para
 * ela **antes** de gastar uma geração, e discordar.
 *
 * A decisão que dá forma ao hook: quem responde o que será enviado é sempre o
 * backend, inclusive quando a semântica foi corrigida à mão. O pedido de
 * pré-visualização leva a correção junto, e a resposta volta normalizada e
 * validada pelo mesmo contrato que a geração usaria. Guardar a correção só
 * do lado do cliente seria mais rápido e mentiria em dois casos: um JSON fora
 * do contrato (que só falharia na hora de gerar) e um campo omitido (que o
 * backend preencheria com o padrão, sem o painel mostrar).
 *
 * Uma correção pode envelhecer: se a descrição mudar depois dela, o hook não
 * descarta nem atualiza sozinho — ele avisa (`stale`). As duas decisões são
 * de quem escreveu.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  type FieldError,
  GenerationApiError,
  buildJobPayload,
  previewPrompt,
} from "../services/generationApi";
import type { GenerationMode, PromptPreview, SemanticPrompt } from "../types";

/** Espera depois da última tecla antes de perguntar ao backend. */
const DEBOUNCE_MS = 450;

export interface PromptEdit {
  semantic: SemanticPrompt;
  /** Descrição vigente quando a correção foi feita — base do aviso `stale`. */
  basePrompt: string;
}

export interface PreviewError {
  message: string;
  fields: readonly FieldError[];
}

export interface UsePromptPreview {
  /** O que será enviado ao gerar. `null` enquanto não há leitura. */
  preview: PromptPreview | null;
  loading: boolean;
  error: PreviewError | null;
  /** Há uma correção à mão em vigor. */
  edited: boolean;
  /** A descrição mudou depois da correção — o painel está desatualizado. */
  stale: boolean;
  /** Aplica uma semântica corrigida (ou `null` para voltar ao automático). */
  setEdit: (semantic: SemanticPrompt | null) => void;
}

export function usePromptPreview(
  mode: GenerationMode,
  prompt: string,
  edit: PromptEdit | null,
  onEditChange: (edit: PromptEdit | null) => void,
): UsePromptPreview {
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<PreviewError | null>(null);

  const trimmed = prompt.trim();
  const inFlight = useRef<AbortController | null>(null);
  const semantic = edit?.semantic ?? null;

  useEffect(() => {
    if (!trimmed) {
      setPreview(null);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    const timer = window.setTimeout(() => {
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;

      previewPrompt(
        buildJobPayload({ mode, prompt: trimmed, semantic }),
        controller.signal,
      )
        .then((result) => {
          if (controller.signal.aborted) return;
          setPreview(result);
          setError(null);
        })
        .catch((caught: unknown) => {
          if (controller.signal.aborted) return;
          if (caught instanceof GenerationApiError && caught.code === "aborted") return;
          // Falhar aqui não impede de gerar: o painel é diagnóstico, e uma
          // leitura indisponível não é motivo para travar o botão.
          setPreview(null);
          setError({
            message:
              caught instanceof GenerationApiError
                ? caught.message
                : "Não foi possível carregar a leitura desta descrição.",
            fields: caught instanceof GenerationApiError ? caught.fields : [],
          });
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [mode, trimmed, semantic]);

  // Desmontou no meio de uma busca: não deixa a requisição pendurada.
  useEffect(() => () => inFlight.current?.abort(), []);

  const setEdit = useCallback(
    (next: SemanticPrompt | null) => {
      onEditChange(next ? { semantic: next, basePrompt: trimmed } : null);
    },
    [onEditChange, trimmed],
  );

  return {
    preview,
    loading,
    error,
    edited: edit !== null,
    stale: edit !== null && edit.basePrompt !== trimmed,
    setEdit,
  };
}
