import type { GenerationOutcome } from "../hooks/useGenerationJob";
import { MODES } from "../types";
import { AssetPreview } from "./AssetPreview";
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
      {outcome.fallbackUsed ? <FallbackNotice /> : null}
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
 * Aviso de que o asset não veio do gerador preferido (plano §44).
 *
 * Sem ele, uma substituição é invisível: o asset chega completo, com selo
 * técnico e tudo, e nada distingue a arte que você pediu de um placeholder de
 * emergência. Foi exatamente assim que um "red dragon" virou um boneco
 * geométrico sem ninguém perceber — a informação existia no job desde sempre,
 * só não chegava à tela.
 *
 * O texto é deliberadamente neutro. O backend manda junto uma frase que cita
 * o id do motor; usá-la aqui seria mais informativo e furaria a regra de a
 * interface não conhecer motor nenhum (§32 e §46). O que o usuário precisa
 * saber é que **houve** substituição, não quem substituiu quem.
 */
function FallbackNotice() {
  return (
    <p className="result__fallback" role="status">
      <span aria-hidden="true">⚠</span> O gerador principal deste modo não estava
      disponível, e este asset saiu de um gerador alternativo — o resultado tende a
      ser bem mais simples que o pedido. Vale gerar de novo.
    </p>
  );
}
