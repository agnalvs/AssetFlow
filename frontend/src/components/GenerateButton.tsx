interface GenerateButtonProps {
  disabled: boolean;
  busy: boolean;
  /** O que acontece com o pedido, ou o que fazer em seguida. */
  note?: string | null;
  /** Um pedido recusado, com a razão do backend. */
  error?: string | null;
  onClick: () => void;
}

/**
 * CTA principal (plano da tela §10 e §11).
 *
 * Desde a Fase B do plano do app ele **cria um pedido** na fila; quem desenha
 * é o Claude, pela conversa. Fica desabilitado com a descrição vazia e
 * enquanto o pedido é enviado — o que também impede o clique duplo (§41).
 */
export function GenerateButton({ disabled, busy, note, error, onClick }: GenerateButtonProps) {
  return (
    <div className="generate">
      <button
        type="button"
        className="generate-button"
        disabled={disabled || busy}
        aria-busy={busy}
        aria-describedby={note || error ? "generate-note" : undefined}
        onClick={onClick}
      >
        {busy ? (
          <>
            <span className="generate-button__spinner" aria-hidden="true" />
            Enviando...
          </>
        ) : (
          "Gerar Asset"
        )}
      </button>
      {error ? (
        <p id="generate-note" className="generate__note generate__note--erro" role="alert">
          {error}
        </p>
      ) : note ? (
        <p id="generate-note" className="generate__note">
          {note}
        </p>
      ) : null}
    </div>
  );
}
