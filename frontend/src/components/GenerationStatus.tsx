import type { GenerationState } from "../types";

interface GenerationStatusProps {
  state: GenerationState;
}

/**
 * Estado de processamento (plano da tela §14 a §17).
 *
 * O loader é **indeterminado** de propósito: o backend ainda não publica
 * progresso confiável por etapa, e inventar um percentual seria mentir para
 * o usuário. Quando houver progresso real, esta é a peça que muda.
 */
export function GenerationStatus({ state }: GenerationStatusProps) {
  const messages: Partial<Record<GenerationState, string>> = {
    queued: "Preparando sua geração...",
    generating: "Criando seu asset...",
    processing: "Finalizando a imagem...",
  };
  const message = messages[state];
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
