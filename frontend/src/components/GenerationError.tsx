interface GenerationErrorProps {
  message: string;
  onRetry: () => void;
}

/**
 * Erro apresentável (plano da tela §40).
 *
 * A mensagem que chega aqui já foi traduzida no serviço de API. `CUDA OOM` e
 * afins ficam no log do backend, onde servem para alguma coisa.
 */
export function GenerationError({ message, onRetry }: GenerationErrorProps) {
  return (
    <div className="error-panel" role="alert">
      <span className="error-panel__icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7.5v5.5M12 16.2v.6" />
        </svg>
      </span>
      <div className="error-panel__body">
        <p className="error-panel__title">Não conseguimos concluir esta geração.</p>
        <p className="error-panel__message">{message}</p>
      </div>
      <button type="button" className="button button--ghost" onClick={onRetry}>
        Tentar novamente
      </button>
    </div>
  );
}
