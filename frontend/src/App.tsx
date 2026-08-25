import { useCallback, useRef, useState } from "react";

import {
  type AssetSelection,
  AssetControls,
  EMPTY_SELECTION,
} from "./components/AssetControls";
import { EmptyResult } from "./components/EmptyResult";
import { CreationMethodSelector } from "./components/CreationMethodSelector";
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
import { useCreationCatalog } from "./hooks/useCreationCatalog";
import { useGenerationJob } from "./hooks/useGenerationJob";
import { userChoicesOf } from "./specOverrides";
import { type PromptEdit, usePromptPreview } from "./hooks/usePromptPreview";
import {
  AUTO_CREATION,
  type CreationSelection,
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
  // Como criar. Começa em Automático — quem só quer um sprite não deve
  // precisar saber que existem métodos, motores e agentes (plano §5).
  const [creation, setCreation] = useState<CreationSelection>(AUTO_CREATION);

  const promptRef = useRef<HTMLTextAreaElement>(null);
  const { state, error, result, isBusy, generate, reset, showResult } = useGenerationJob();
  const catalog = useCreationCatalog(MODES[mode].capability);
  const inspector = usePromptPreview(mode, prompt, selection, edit, setEdit, creation);

  const canGenerate = prompt.trim().length > 0 && !isBusy;

  // Pixel Art e 2D convencional não oferecem os mesmos métodos nem os mesmos
  // motores. Ao trocar de modo, uma escolha que deixou de existir no catálogo
  // faria a tela oferecer algo que a geração recusaria; o catálogo devolve a
  // versão corrigida dela.
  const reconciled = catalog.reconcile(creation);
  if (reconciled !== creation) {
    setCreation(reconciled);
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
        creation,
      });
    },
    [creation, edit, generate, isBusy, selection],
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
        warnings: result.warnings,
        createdAt: Date.now(),
      };
      return [entry, ...current].slice(0, MAX_HISTORY);
    });
  }

  const handleNewPrompt = useCallback(() => {
    setPrompt("");
    setSelection(EMPTY_SELECTION);
    setEdit(null);
    setCreation(AUTO_CREATION);
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

          <CreationMethodSelector
            selection={creation}
            catalog={catalog}
            resolvedStrategy={inspector.preview?.resolved.strategy ?? null}
            resolvedEngine={inspector.preview?.resolved.engine ?? null}
            disabled={isBusy}
            onChange={setCreation}
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
              catalog={catalog}
              onRegenerate={() => void runGeneration(result.mode, result.prompt)}
              onNewPrompt={handleNewPrompt}
            />
          ) : null}

          {!isBusy && state !== "completed" && state !== "failed" ? <EmptyResult /> : null}
        </section>

        <SessionHistory
          entries={history}
          activeJobId={result?.jobId ?? null}
          catalog={catalog}
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
            // O método volta só quando foi **escolhido**: uma geração feita
            // em Automático reabre em Automático, para que a política continue
            // podendo responder se o cenário tiver mudado.
            setCreation(creationOf(entry));
            showResult(entry);
            lastRecorded.current = entry.jobId;
          }}
        />
      </main>

      <footer className="page__footer">
        <p>
          Em <strong>Automático</strong>, o AssetFlow escolhe o método de criação mais
          adequado ao tipo de asset e mostra o motivo antes de gerar. Você também pode
          escolher o método à mão — e nesse caso ele é respeitado.
        </p>
      </footer>
    </div>
  );
}

/**
 * A escolha de criação de uma geração antiga, para reabri-la (§42).
 *
 * Só o que foi **escolhido** volta. Um job feito em Automático reabre em
 * Automático: se ele voltasse já resolvido, trocar de tamanho depois não
 * mudaria mais o método, e a política deixaria de ter efeito sem que nada na
 * tela explicasse por quê.
 */
function creationOf(entry: HistoryEntry): CreationSelection {
  const resolved = entry.preview?.resolved;
  if (!resolved || resolved.strategy.requested === "auto") return AUTO_CREATION;

  if (resolved.strategy.mode === "pixel_agent") {
    return {
      strategy: "pixel_agent",
      engineId: null,
      agentId: resolved.pixel_agent.agent_id,
      quality: resolved.pixel_agent.quality_mode,
    };
  }
  return {
    strategy: "model",
    engineId:
      resolved.engine.selection_mode === "manual" ? resolved.engine.engine_id : null,
    agentId: null,
    quality: "auto",
  };
}
