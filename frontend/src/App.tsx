import { useCallback, useRef, useState } from "react";

import {
  type AssetSelection,
  AssetControls,
  EMPTY_SELECTION,
} from "./components/AssetControls";
import { EmptyResult } from "./components/EmptyResult";
import { GenerateButton } from "./components/GenerateButton";
import { GenerationError } from "./components/GenerationError";
import { GenerationResult } from "./components/GenerationResult";
import { GenerationStatus } from "./components/GenerationStatus";
import { GeneratorHero } from "./components/GeneratorHero";
import { Header } from "./components/Header";
import { PromptInput } from "./components/PromptInput";
import { PromptInspector } from "./components/PromptInspector";
import { SessionHistory } from "./components/SessionHistory";
import { useGenerationJob } from "./hooks/useGenerationJob";
import { userChoicesOf } from "./specOverrides";
import { type PromptEdit, usePromptPreview } from "./hooks/usePromptPreview";
import { type GenerationMode, type HistoryEntry, MODES } from "./types";

const MAX_HISTORY = 12;

/** O app só gera Pixel Art (Fase A do plano do app). */
const MODE: GenerationMode = "pixel";

/**
 * "Gerar" está desligado na Fase A do plano do app
 * (backend/docs/PLANO_APP_DESENHISTA.md). O único gerador é a desenhista, que
 * precisa de uma receita escrita pelo Claude; a tela não tem como mandá-la.
 * Na Fase B, o botão passa a criar um pedido numa fila que o Claude atende —
 * e é esta constante que volta a ligar o caminho, num lugar só.
 */
const GERAR_LIGADO = false;

const AVISO_GERAR_DESLIGADO =
  "Gerar está desligado nesta versão. Na próxima fase, os pedidos feitos aqui " +
  "passam a ir para uma fila que o Claude atende. Por enquanto, desenhe pela " +
  "conversa com o Claude, pelo servidor MCP do AssetFlow.";

/**
 * Página do gerador (plano da tela §28 e §29).
 *
 * Todo o estado do fluxo vive aqui e no hook `useGenerationJob`. Os
 * componentes abaixo são de apresentação — o que mantém a troca de polling
 * por WebSocket, no futuro, restrita a um arquivo.
 *
 * Desde a Fase A do plano do app a tela não pergunta nada de tecnologia: sem
 * seletor de motor, sem "Automático" e sem modo 2D Normal. Ela monta o pedido
 * e mostra o que o AssetFlow entendeu dele.
 */
export function App() {
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  // Os controles explícitos (tipo, resolução, paleta, fundo). Começam todos
  // em automático: quem só quer um sprite não deve precisar preencher nada.
  const [selection, setSelection] = useState<AssetSelection>(EMPTY_SELECTION);
  // A correção da leitura mora aqui, e não dentro do painel: ela precisa
  // sobreviver ao painel fechado e acompanhar o pedido até a geração.
  const [edit, setEdit] = useState<PromptEdit | null>(null);

  const promptRef = useRef<HTMLTextAreaElement>(null);
  const { state, stage, error, result, isBusy, generate, reset, showResult } =
    useGenerationJob();
  const inspector = usePromptPreview(MODE, prompt, selection, edit, setEdit);

  const canGenerate = GERAR_LIGADO && prompt.trim().length > 0 && !isBusy;

  const runGeneration = useCallback(
    async (targetPrompt: string) => {
      const cleaned = targetPrompt.trim();
      if (!GERAR_LIGADO || !cleaned || isBusy) return;

      await generate({
        mode: MODE,
        prompt: cleaned,
        selection,
        spec: edit?.spec ?? null,
        semantic: edit?.semantic ?? null,
      });
    },
    [edit, generate, isBusy, selection],
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
          <PromptInput
            ref={promptRef}
            value={prompt}
            placeholder={MODES[MODE].placeholder}
            disabled={isBusy}
            onChange={setPrompt}
            onSubmit={() => void runGeneration(prompt)}
          />

          <AssetControls
            selection={selection}
            resolved={inspector.preview?.resolved ?? null}
            pixel
            disabled={isBusy}
            onChange={setSelection}
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
            note={GERAR_LIGADO ? null : AVISO_GERAR_DESLIGADO}
            onClick={() => void runGeneration(prompt)}
          />
        </section>

        <section className="outcome" aria-live="polite">
          {isBusy ? <GenerationStatus state={state} stage={stage} /> : null}

          {!isBusy && state === "failed" && error ? (
            <GenerationError message={error} onRetry={() => void runGeneration(prompt)} />
          ) : null}

          {!isBusy && state === "completed" && result ? (
            <GenerationResult
              outcome={result}
              busy={isBusy}
              onRegenerate={() => void runGeneration(result.prompt)}
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
            // Reabrir uma geração antiga traz de volta as decisões dela —
            // só as decisões. O que veio do profile continua automático, para
            // que trocar de estilo depois volte a ter efeito (plano T→J §16).
            setSelection(EMPTY_SELECTION);
            setEdit(
              entry.preview
                ? {
                    spec: userChoicesOf(entry.preview.resolved),
                    semantic: entry.preview.semantic,
                    basePrompt: entry.prompt,
                  }
                : null,
            );
            showResult(entry);
            lastRecorded.current = entry.jobId;
          }}
        />
      </main>

      <footer className="page__footer">
        <p>
          O AssetFlow tem um gerador só: o <strong>desenhista</strong>, em que o Claude
          desenha o sprite na grade lógica a partir de uma receita. Todo desenho passa
          pelo <strong>Pixel Exact</strong> e pelo <strong>Pixel Optimizer</strong>{" "}
          antes de ser entregue.
        </p>
      </footer>
    </div>
  );
}
