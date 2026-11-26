import { optimizationLabel } from "../labels";
import { type GenerationOutcome, MODES, type PixelOptimization } from "../types";
import { AssetPreview } from "./AssetPreview";
import { GenerationNotices } from "./GenerationNotices";
import { OpiniaoControls } from "./OpiniaoControls";
import { ResultActions } from "./ResultActions";

interface GenerationResultProps {
  outcome: GenerationOutcome;
  busy: boolean;
  onRegenerate: () => void;
  onNewPrompt: () => void;
}

/** Área de resultado (plano da tela §19 e §39). */
export function GenerationResult({
  outcome,
  busy,
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
      <GenerationNotices warnings={outcome.warnings} />
      <OptimizationLine optimization={outcome.variant.optimization} />
      {outcome.olhar ? (
        <p className="result__olhar">
          <span className="result__optimization-key">Olhar do Claude</span> {outcome.olhar}
        </p>
      ) : null}
      {outcome.assetId ? <OpiniaoControls assetId={outcome.assetId} /> : null}
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

/**
 * O que o Pixel Optimizer fez, em uma linha (plano Optimizer §30).
 *
 * Era a segunda linha do crédito de motor, que saiu na Fase A do plano do app
 * junto com a escolha de motor. Esta fica: ela não fala de motor, fala do
 * estágio que corrige toda geração. Aparece **sempre** que houver laudo,
 * inclusive quando nada foi corrigido — "nenhuma correção necessária" é
 * informação, e esconder a linha faria parecer que o estágio às vezes não
 * roda (§46).
 */
function OptimizationLine({ optimization }: { optimization: PixelOptimization | null }) {
  if (!optimization) return null;
  return (
    <div className="result__optimization">
      <p>
        <span className="result__optimization-key">Otimização</span>{" "}
        <strong>{optimizationLabel(optimization)}</strong>
      </p>
    </div>
  );
}
