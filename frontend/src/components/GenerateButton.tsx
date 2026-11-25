interface GenerateButtonProps {
  disabled: boolean;
  busy: boolean;
  /**
   * Por que o botão está desligado, quando é por decisão do app e não por um
   * campo vazio. Aparece junto do botão, para ninguém achar que ele quebrou.
   */
  note?: string | null;
  onClick: () => void;
}

/**
 * CTA principal (plano da tela §10 e §11).
 *
 * Fica desabilitado com prompt vazio e durante a geração — o que também
 * impede o clique duplo criando dois jobs (§41). Na Fase A do plano do app ele
 * fica desligado de todo, com `note` dizendo por quê.
 */
export function GenerateButton({ disabled, busy, note, onClick }: GenerateButtonProps) {
  return (
    <div className="generate">
      <button
        type="button"
        className="generate-button"
        disabled={disabled || busy}
        aria-busy={busy}
        aria-describedby={note ? "generate-note" : undefined}
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
      {note ? (
        <p id="generate-note" className="generate__note">
          {note}
        </p>
      ) : null}
    </div>
  );
}
