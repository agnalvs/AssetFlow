import { useCallback, useRef, useState } from "react";

import { EmptyResult } from "./components/EmptyResult";
import { GenerateButton } from "./components/GenerateButton";
import { GenerationError } from "./components/GenerationError";
import { GenerationModeSelector } from "./components/GenerationModeSelector";
import { GenerationResult } from "./components/GenerationResult";
import { GenerationStatus } from "./components/GenerationStatus";
import { GeneratorHero } from "./components/GeneratorHero";
import { Header } from "./components/Header";
import { PromptInput } from "./components/PromptInput";
import { PromptInspector } from "./components/PromptInspector";
import { SessionHistory } from "./components/SessionHistory";
import { useGenerationJob } from "./hooks/useGenerationJob";
import { type PromptEdit, usePromptPreview } from "./hooks/usePromptPreview";
import { type GenerationMode, type HistoryEntry, MODES } from "./types";

const MAX_HISTORY = 12;

/**
 * Página do gerador (plano da tela §28 e §29).
 *
 * Todo o estado do fluxo vive aqui e no hook `useGenerationJob`. Os
 * componentes abaixo são de apresentação — o que mantém a troca de polling
 * por WebSocket, no futuro, restrita a um arquivo.
 */
export function App() {
  const [mode, setMode] = useState<GenerationMode>("pixel");
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  // A correção da leitura mora aqui, e não dentro do painel: ela precisa
  // sobreviver ao painel fechado e acompanhar o pedido até a geração.
  const [edit, setEdit] = useState<PromptEdit | null>(null);

  const promptRef = useRef<HTMLTextAreaElement>(null);
  const { state, error, result, isBusy, generate, reset, showResult } = useGenerationJob();
  const inspector = usePromptPreview(mode, prompt, edit, setEdit);

  const canGenerate = prompt.trim().length > 0 && !isBusy;

  const runGeneration = useCallback(
    async (targetMode: GenerationMode, targetPrompt: string) => {
      const cleaned = targetPrompt.trim();
      if (!cleaned || isBusy) return;

      await generate({
        mode: targetMode,
        prompt: cleaned,
        semantic: edit?.semantic ?? null,
      });
    },
    [edit, generate, isBusy],
  );

  // O histórico é alimentado quando uma geração conclui.
  const lastRecorded = useRef<string | null>(null);
  if (result && result.jobId !== lastRecorded.current) {
    lastRecorded.current = result.jobId;
    setHistory((current) => {
      if (current.some((entry) => entry.jobId === result.jobId)) return current;
      const entry: HistoryEntry = {
        jobId: result.jobId,
        mode: result.mode,
        prompt: result.prompt,
        variant: result.variant,
        preview: result.preview,
        createdAt: Date.now(),
      };
      return [entry, ...current].slice(0, MAX_HISTORY);
    });
  }

  const handleNewPrompt = useCallback(() => {
    setPrompt("");
    setEdit(null);
    reset();
    lastRecorded.current = null;
    promptRef.current?.focus();
  }, [reset]);

  return (
    <div className="page">
      <Header />

      <main className="page__main">
        <GeneratorHero />

        <section className="generator" aria-label="Gerador de assets">
          <GenerationModeSelector value={mode} disabled={isBusy} onChange={setMode} />

          <PromptInput
            ref={promptRef}
            value={prompt}
            placeholder={MODES[mode].placeholder}
            disabled={isBusy}
            onChange={setPrompt}
            onSubmit={() => void runGeneration(mode, prompt)}
          />

          <PromptInspector
            preview={inspector.preview}
            loading={inspector.loading}
            error={inspector.error}
            edited={inspector.edited}
            stale={inspector.stale}
            disabled={isBusy}
            onEdit={inspector.setEdit}
          />

          <GenerateButton
            disabled={!canGenerate}
            busy={isBusy}
            onClick={() => void runGeneration(mode, prompt)}
          />
        </section>

        <section className="outcome" aria-live="polite">
          {isBusy ? <GenerationStatus state={state} /> : null}

          {!isBusy && state === "failed" && error ? (
            <GenerationError
              message={error}
              onRetry={() => void runGeneration(mode, prompt)}
            />
          ) : null}

          {!isBusy && state === "completed" && result ? (
            <GenerationResult
              outcome={result}
              busy={isBusy}
              onRegenerate={() => void runGeneration(result.mode, result.prompt)}
              onNewPrompt={handleNewPrompt}
            />
          ) : null}

          {!isBusy && state !== "completed" && state !== "failed" ? <EmptyResult /> : null}
        </section>

        <SessionHistory
          entries={history}
          activeJobId={result?.jobId ?? null}
          onSelect={(entry) => {
            setPrompt(entry.prompt);
            setMode(entry.mode);
            // Reabrir uma geração antiga traz de volta a leitura dela, e não
            // só a frase: é o que permite pegar um acerto e mexer em um campo
            // sem torcer para o builder interpretar igual de novo.
            setEdit(
              entry.preview
                ? { semantic: entry.preview.semantic, basePrompt: entry.prompt }
                : null,
            );
            showResult(entry);
            lastRecorded.current = entry.jobId;
          }}
        />
      </main>

      <footer className="page__footer">
        <p>
          O AssetFlow escolhe automaticamente o motor de geração mais adequado para o
          estilo selecionado.
        </p>
      </footer>
    </div>
  );
}
