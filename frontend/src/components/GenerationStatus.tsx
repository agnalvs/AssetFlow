import type { GenerationState } from "../types";

interface GenerationStatusProps {
  state: GenerationState;
  /** O estágio reportado pelo backend, quando houver (plano Optimizer §29). */
  stage?: string;
}

/**
 * Estado de processamento (plano da tela §14 a §17; plano Optimizer §29).
 *
 * O loader é **indeterminado** de propósito: o backend ainda não publica
 * progresso confiável por etapa, e inventar um percentual seria mentir para
 * o usuário. O que ele publica é o **estágio**, e esse dá para mostrar.
 *
 * O estágio ganha do estado quando existe, e a diferença importa desde que o
 * Pixel Optimizer entrou: um sprite de 32×32 passa mais tempo sendo revisado
 * do que sendo gerado, e "Finalizando a imagem..." durante essa espera faz
 * parecer que a geração travou no fim.
 */
export function GenerationStatus({ state, stage }: GenerationStatusProps) {
  const message = STAGES[stage ?? ""] ?? STATES[state];
  if (!message) return null;

  return (
    <div className="status" role="status" aria-live="polite">
      <span className="status__spinner" aria-hidden="true" />
      <p className="status__message">{message}</p>
      <span className="status__dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
    </div>
  );
}

/** Os estágios que o backend nomeia. Um estágio novo cai no genérico. */
const STAGES: Record<string, string> = {
  building_prompt: "Interpretando sua descrição...",
  postprocessing: "Revisando o sprite pixel a pixel...",
};

const STATES: Partial<Record<GenerationState, string>> = {
  queued: "Preparando sua geração...",
  generating: "Criando seu asset...",
  processing: "Finalizando a imagem...",
};
