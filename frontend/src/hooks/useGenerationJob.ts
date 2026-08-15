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
  createGenerationJob,
  getGenerationJob,
} from "../services/generationApi";
import {
  type AssetVariant,
  type GenerationMode,
  type GenerationState,
  MODES,
  toGenerationState,
} from "../types";

const POLL_INTERVAL_MS = 1200;
/** Corta o polling se o backend parar de responder por muito tempo. */
const MAX_POLL_ATTEMPTS = 600;

export interface GenerationRequestInput {
  mode: GenerationMode;
  prompt: string;
}

export interface GenerationOutcome {
  jobId: string;
  mode: GenerationMode;
  prompt: string;
  variant: AssetVariant;
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

/** Identidade de projeto do playground, estável entre recarregamentos. */
function resolveProjectId(): string {
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

export function useGenerationJob(): UseGenerationJob {
  const [state, setState] = useState<GenerationState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerationOutcome | null>(null);

  const cancelled = useRef(false);
  const projectId = useRef<string>(resolveProjectId());

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

  const generate = useCallback(async ({ mode, prompt }: GenerationRequestInput) => {
    const config = MODES[mode];
    setError(null);
    setResult(null);
    setState("queued");

    try {
      const submission = await createGenerationJob({
        project_id: projectId.current,
        // O frontend pede uma CAPACIDADE, nunca um motor.
        capability: config.capability,
        profile: config.profile,
        prompt: prompt.trim(),
        output: { variations: 1 },
        engine: { mode: "auto" },
      });

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
          setResult({ jobId: job.job_id, mode, prompt, variant });
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
  }, []);

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
