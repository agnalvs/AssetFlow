import { useCallback, useRef, useState } from "react";

import {
  type AssetSelection,
  AssetControls,
  EMPTY_SELECTION,
} from "./components/AssetControls";
import { EmptyResult } from "./components/EmptyResult";
import { EngineSelector } from "./components/EngineSelector";
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
import { useEngineCatalog } from "./hooks/useEngineCatalog";
import { useGenerationJob } from "./hooks/useGenerationJob";
import { userChoicesOf } from "./specOverrides";
import { type PromptEdit, usePromptPreview } from "./hooks/usePromptPreview";
import {
  AUTO_ENGINE,
  type EngineSelection,
  type GenerationMode,
  type HistoryEntry,
  MODES,
} from "./types";

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
  // Os controles explícitos (tipo, resolução, paleta, fundo). Começam todos
  // em automático: quem só quer um sprite não deve precisar preencher nada.
  const [selection, setSelection] = useState<AssetSelection>(EMPTY_SELECTION);
  // A correção da leitura mora aqui, e não dentro do painel: ela precisa
  // sobreviver ao painel fechado e acompanhar o pedido até a geração.
  const [edit, setEdit] = useState<PromptEdit | null>(null);
  // O motor escolhido. Começa em Automático — quem só quer um sprite não deve
  // precisar saber que existem motores (plano de motores §4.1).
  const [engine, setEngine] = useState<EngineSelection>(AUTO_ENGINE);

  const promptRef = useRef<HTMLTextAreaElement>(null);
  const { state, error, result, isBusy, generate, reset, showResult } = useGenerationJob();
  const catalog = useEngineCatalog(MODES[mode].capability);
  const inspector = usePromptPreview(mode, prompt, selection, edit, setEdit, engine);

  const canGenerate = prompt.trim().length > 0 && !isBusy;

  // Pixel Art e 2D convencional não são atendidos pelos mesmos motores.
  // Ao trocar de modo, um motor que não atende o novo modo deixa de existir
  // no catálogo — e manter a escolha apontando para ele faria a tela oferecer
  // algo que a geração recusaria. Voltar para Automático é o comportamento
  // honesto: a pessoa escolhe de novo, agora entre os que servem.
  if (
    engine.engineId !== null &&
    !catalog.loading &&
    catalog.engines.length > 0 &&
    !catalog.engines.some((item) => item.engine_id === engine.engineId)
  ) {
    setEngine(AUTO_ENGINE);
  }

  const runGeneration = useCallback(
    async (targetMode: GenerationMode, targetPrompt: string) => {
      const cleaned = targetPrompt.trim();
      if (!cleaned || isBusy) return;

      await generate({
        mode: targetMode,
        prompt: cleaned,
        selection,
        spec: edit?.spec ?? null,
        semantic: edit?.semantic ?? null,
        engine,
      });
    },
    [edit, engine, generate, isBusy, selection],
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
        fallbackUsed: result.fallbackUsed,
        engine: result.engine,
        createdAt: Date.now(),
      };
      return [entry, ...current].slice(0, MAX_HISTORY);
    });
  }

  const handleNewPrompt = useCallback(() => {
    setPrompt("");
    setSelection(EMPTY_SELECTION);
    setEdit(null);
    setEngine(AUTO_ENGINE);
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

          <AssetControls
            selection={selection}
            resolved={inspector.preview?.resolved ?? null}
            pixel={mode === "pixel"}
            disabled={isBusy}
            onChange={setSelection}
          />

          <EngineSelector
            selection={engine}
            engines={catalog.engines}
            loading={catalog.loading}
            empty={catalog.empty}
            error={catalog.error}
            resolved={inspector.preview?.resolved.engine ?? null}
            nameOf={catalog.nameOf}
            disabled={isBusy}
            onChange={setEngine}
          />

          <PromptInspector
            preview={inspector.preview}
            loading={inspector.loading}
            error={inspector.error}
            specEdited={inspector.specEdited}
            semanticEdited={inspector.semanticEdited}
            stale={inspector.stale}
            disabled={isBusy}
            onEditSpec={inspector.setSpecEdit}
            onEditSemantic={inspector.setSemanticEdit}
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
              nameOf={catalog.nameOf}
              onRegenerate={() => void runGeneration(result.mode, result.prompt)}
              onNewPrompt={handleNewPrompt}
            />
          ) : null}

          {!isBusy && state !== "completed" && state !== "failed" ? <EmptyResult /> : null}
        </section>

        <SessionHistory
          entries={history}
          activeJobId={result?.jobId ?? null}
          nameOf={catalog.nameOf}
          onSelect={(entry) => {
            setPrompt(entry.prompt);
            setMode(entry.mode);
            // Reabrir uma geração antiga traz de volta a leitura dela, e não
            // só a frase: é o que permite pegar um acerto e mexer em um campo
            // sem torcer para o builder interpretar igual de novo.
            setSelection(EMPTY_SELECTION);
            // Reabrir uma geração antiga traz de volta as decisões dela —
            // só as decisões. O que veio do profile continua automático, para
            // que trocar de estilo depois volte a ter efeito (plano T→J §16).
            setEdit(
              entry.preview
                ? {
                    spec: userChoicesOf(entry.preview.resolved),
                    semantic: entry.preview.semantic,
                    basePrompt: entry.prompt,
                  }
                : null,
            );
            // O motor volta só quando foi **escolhido**: uma geração feita em
            // Automático reabre em Automático, para que a política continue
            // podendo responder se o cenário tiver mudado.
            setEngine(
              entry.preview?.resolved.engine.selection_mode === "manual"
                ? { engineId: entry.preview.resolved.engine.engine_id }
                : AUTO_ENGINE,
            );
            showResult(entry);
            lastRecorded.current = entry.jobId;
          }}
        />
      </main>

      <footer className="page__footer">
        <p>
          Em <strong>Automático</strong>, o AssetFlow escolhe o motor mais adequado ao
          tipo de asset e mostra o motivo antes de gerar. Você também pode escolher o
          motor à mão — e nesse caso ele é respeitado.
        </p>
      </footer>
    </div>
  );
}
