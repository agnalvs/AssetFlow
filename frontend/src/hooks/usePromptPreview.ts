/**
 * A leitura que o AssetFlow faz da descrição, acompanhando a digitação.
 *
 * Entre a frase que a pessoa escreve e a imagem que sai existe uma
 * interpretação — hoje um contrato inteiro, o `FinalResolvedSpec` — e ela
 * sempre existiu. O que não existia era poder olhar para ela **antes** de
 * gastar uma geração, e discordar.
 *
 * A decisão que dá forma ao hook: quem responde o que será enviado é sempre o
 * backend, inclusive quando algo foi corrigido à mão. O pedido de
 * pré-visualização leva a correção junto, e a resposta volta normalizada e
 * validada pelo mesmo contrato que a geração usaria. Guardar a correção só do
 * lado do cliente seria mais rápido e mentiria em dois casos: um JSON fora do
 * contrato (que só falharia na hora de gerar) e um campo omitido (que o
 * backend preencheria com o padrão, sem o painel mostrar).
 *
 * São dois níveis de correção, e eles não se confundem (plano T→J §9):
 *
 *     spec       o contrato — resolução, paleta, tipo de asset
 *     semantic   o prompt — vista, pose, o que evitar
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
import type { AssetSelection } from "../components/AssetControls";
import type {
  EngineSelection,
  GenerationMode,
  PromptPreview,
  SemanticPrompt,
  SpecOverrides,
} from "../types";

/** Espera depois da última tecla antes de perguntar ao backend. */
const DEBOUNCE_MS = 450;

export interface PromptEdit {
  /** Correção manual do contrato (plano T→J §9, nível 1). */
  spec: SpecOverrides | null;
  /** Semântica corrigida à mão; substitui o PromptBuilder inteiro. */
  semantic: SemanticPrompt | null;
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
  specEdited: boolean;
  semanticEdited: boolean;
  /** A descrição mudou depois da correção — o painel está desatualizado. */
  stale: boolean;
  setSpecEdit: (overrides: SpecOverrides | null) => void;
  setSemanticEdit: (semantic: SemanticPrompt | null) => void;
}

export function usePromptPreview(
  mode: GenerationMode,
  prompt: string,
  selection: AssetSelection,
  edit: PromptEdit | null,
  onEditChange: (edit: PromptEdit | null) => void,
  // O motor entra na pré-visualização pelo mesmo motivo que os outros
  // controles: a resposta precisa descrever a geração que **vai** acontecer.
  // Em "Automático", é ela que traz o motor resolvido e o motivo (§17).
  engine: EngineSelection | null = null,
): UsePromptPreview {
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<PreviewError | null>(null);

  const trimmed = prompt.trim();
  const inFlight = useRef<AbortController | null>(null);
  const spec = edit?.spec ?? null;
  const semantic = edit?.semantic ?? null;

  // Os controles são objeto novo a cada render do App; comparar por valor
  // evita refazer a pré-visualização a cada tecla digitada em outro campo.
  const selectionKey = JSON.stringify(selection);
  const specKey = JSON.stringify(spec);
  const engineKey = engine?.engineId ?? "";

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
        buildJobPayload({ mode, prompt: trimmed, selection, spec, semantic, engine }),
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
          // leitura indisponível não é motivo para travar o botão. A exceção
          // é o pedido recusado pelo backend (uma resolução impossível, por
          // exemplo) — aí o erro é o próprio conteúdo da resposta.
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, trimmed, selectionKey, specKey, semantic, engineKey]);

  // Desmontou no meio de uma busca: não deixa a requisição pendurada.
  useEffect(() => () => inFlight.current?.abort(), []);

  const setSpecEdit = useCallback(
    (next: SpecOverrides | null) => {
      if (next === null && semantic === null) {
        onEditChange(null);
        return;
      }
      onEditChange({ spec: next, semantic, basePrompt: trimmed });
    },
    [onEditChange, semantic, trimmed],
  );

  const setSemanticEdit = useCallback(
    (next: SemanticPrompt | null) => {
      if (next === null && spec === null) {
        onEditChange(null);
        return;
      }
      onEditChange({ spec, semantic: next, basePrompt: trimmed });
    },
    [onEditChange, spec, trimmed],
  );

  return {
    preview,
    loading,
    error,
    specEdited: spec !== null,
    semanticEdited: semantic !== null,
    stale: edit !== null && edit.basePrompt !== trimmed,
    setSpecEdit,
    setSemanticEdit,
  };
}
