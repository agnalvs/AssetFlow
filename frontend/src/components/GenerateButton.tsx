interface GenerateButtonProps {
  disabled: boolean;
  busy: boolean;
  onClick: () => void;
}

/**
 * CTA principal (plano da tela §10 e §11).
 *
 * Fica desabilitado com prompt vazio e durante a geração — o que também
 * impede o clique duplo criando dois jobs (§41).
 */
export function GenerateButton({ disabled, busy, onClick }: GenerateButtonProps) {
  return (
    <button
      type="button"
      className="generate-button"
      disabled={disabled || busy}
      aria-busy={busy}
      onClick={onClick}
    >
      {busy ? (
        <>
          <span className="generate-button__spinner" aria-hidden="true" />
          Gerando...
        </>
      ) : (
        "Gerar Asset"
      )}
    </button>
  );
}
