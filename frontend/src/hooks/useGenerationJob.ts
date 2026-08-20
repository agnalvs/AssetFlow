/**
 * Orquestra o ciclo de uma geração: criar job, acompanhar, entregar o asset.
 *
 * O polling (plano da tela §18) está isolado aqui. Quando o backend publicar
 * progresso por WebSocket/SSE, só este hook muda — nenhum componente sabe
 * como o estado chega.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  GenerationApiError,
  buildJobPayload,
  createGenerationJob,
  getGenerationJob,
} from "../services/generationApi";
import type { AssetSelection } from "../components/AssetControls";
import {
  type AssetVariant,
  type GenerationMode,
  type GenerationState,
  type PromptPreview,
  type SemanticPrompt,
  type SpecOverrides,
  toGenerationState,
} from "../types";

const POLL_INTERVAL_MS = 1200;
/** Corta o polling se o backend parar de responder por muito tempo. */
const MAX_POLL_ATTEMPTS = 600;

export interface GenerationRequestInput {
  mode: GenerationMode;
  prompt: string;
  /** O que os controles da tela selecionaram. */
  selection?: AssetSelection | null;
  /** Correção manual do contrato. Ganha de tudo (plano T→J §9). */
  spec?: SpecOverrides | null;
  /** Semântica corrigida no painel. Ausente, o AssetFlow interpreta a frase. */
  semantic?: SemanticPrompt | null;
}

export interface GenerationOutcome {
  jobId: string;
  mode: GenerationMode;
  prompt: string;
  variant: AssetVariant;
  /**
   * A leitura que produziu esta imagem, como o backend a registrou.
   *
   * Vem do job, e não do que o cliente mandou: é o que permite reabrir uma
   * geração antiga com exatamente a semântica dela, inclusive os campos que
   * o backend preencheu por padrão.
   */
  preview: PromptPreview | null;
  /** O asset saiu de um gerador alternativo, não do preferido do modo. */
  fallbackUsed: boolean;
}

export interface UseGenerationJob {
  state: GenerationState;
  error: string | null;
  result: GenerationOutcome | null;
  isBusy: boolean;
  generate: (input: GenerationRequestInput) => Promise<void>;
  reset: () => void;
  showResult: (outcome: GenerationOutcome) => void;
}

export function useGenerationJob(): UseGenerationJob {
  const [state, setState] = useState<GenerationState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerationOutcome | null>(null);

  const cancelled = useRef(false);

  useEffect(() => {
    // Evita atualizar estado depois que a página foi desmontada.
    cancelled.current = false;
    return () => {
      cancelled.current = true;
    };
  }, []);

  const reset = useCallback(() => {
    setState("idle");
    setError(null);
    setResult(null);
  }, []);

  const showResult = useCallback((outcome: GenerationOutcome) => {
    setResult(outcome);
    setState("completed");
    setError(null);
  }, []);

  const generate = useCallback(
    async ({ mode, prompt, selection, spec, semantic }: GenerationRequestInput) => {
      setError(null);
      setResult(null);
      setState("queued");

      try {
        // O mesmo construtor da pré-visualização: o que o painel mostrou é o
        // que vai. Montar o corpo aqui de novo abriria espaço para diferença.
        const submission = await createGenerationJob(
          buildJobPayload({ mode, prompt, selection, spec, semantic }),
        );

        for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
          if (cancelled.current) return;
          await sleep(POLL_INTERVAL_MS);
          if (cancelled.current) return;

          const job = await getGenerationJob(submission.job_id);
          const next = toGenerationState(job.status);

          if (next === "completed") {
            const variant = job.asset?.variants?.[0];
            if (!variant?.url) {
              setError("A geração terminou, mas a imagem não pôde ser carregada.");
              setState("failed");
              return;
            }
            setResult({
              jobId: job.job_id,
              mode,
              prompt,
              variant,
              preview: job.prompt,
              fallbackUsed: Boolean(job.fallback_used),
            });
            setState("completed");
            return;
          }

          if (next === "failed") {
            // A mensagem técnica do backend fica no log; aqui vai a do usuário.
            setError(
              "Não conseguimos concluir esta geração. Tente novamente ou altere sua descrição.",
            );
            setState("failed");
            return;
          }

          setState(next === "idle" ? "generating" : next);
        }

        setError("A geração está demorando mais do que o esperado. Tente novamente.");
        setState("failed");
      } catch (caught) {
        const message =
          caught instanceof GenerationApiError
            ? caught.message
            : "Não conseguimos concluir esta geração. Tente novamente.";
        setError(message);
        setState("failed");
      }
    },
    [],
  );

  return {
    state,
    error,
    result,
    isBusy: state === "queued" || state === "generating" || state === "processing",
    generate,
    reset,
    showResult,
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
