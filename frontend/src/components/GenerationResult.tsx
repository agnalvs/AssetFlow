import type { UseCreationCatalog } from "../hooks/useCreationCatalog";
import type { GenerationOutcome } from "../hooks/useGenerationJob";
import { MODES } from "../types";
import { AssetPreview } from "./AssetPreview";
import { EngineCredit } from "./EngineCredit";
import { GenerationNotices } from "./GenerationNotices";
import { ResultActions } from "./ResultActions";

interface GenerationResultProps {
  outcome: GenerationOutcome;
  busy: boolean;
  /** Os nomes de método, motor e agente, vindos do catálogo do backend. */
  catalog: UseCreationCatalog;
  onRegenerate: () => void;
  onNewPrompt: () => void;
}

/** Área de resultado (plano da tela §19 e §39). */
export function GenerationResult({
  outcome,
  busy,
  catalog,
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
      <GenerationNotices
        warnings={outcome.warnings}
        fallbackUsed={outcome.fallbackUsed}
      />
      <EngineCredit selection={outcome.engine} catalog={catalog} />
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
