import type { GenerationOutcome } from "../hooks/useGenerationJob";
import { MODES } from "../types";
import { AssetPreview } from "./AssetPreview";
import { EngineCredit } from "./EngineCredit";
import { ResultActions } from "./ResultActions";

interface GenerationResultProps {
  outcome: GenerationOutcome;
  busy: boolean;
  /** Nome de exibição de um motor, vindo do catálogo do backend. */
  nameOf: (engineId: string | null | undefined) => string;
  onRegenerate: () => void;
  onNewPrompt: () => void;
}

/** Área de resultado (plano da tela §19 e §39). */
export function GenerationResult({
  outcome,
  busy,
  nameOf,
  onRegenerate,
  onNewPrompt,
}: GenerationResultProps) {
  const mode = MODES[outcome.mode];

  return (
    <section className="result" aria-label="Resultado da geração">
      <AssetPreview
        variant={outcome.variant}
        mode={mode}
        alt={`Asset gerado em ${mode.label}: ${outcome.prompt}`}
      />
      <p className="result__prompt" title={outcome.prompt}>
        {outcome.prompt}
      </p>
      <EngineCredit selection={outcome.engine} nameOf={nameOf} />
      <ResultActions
        variant={outcome.variant}
        fileName={`assetflow-${outcome.jobId}.png`}
        busy={busy}
        onRegenerate={onRegenerate}
        onNewPrompt={onNewPrompt}
      />
    </section>
  );
}
