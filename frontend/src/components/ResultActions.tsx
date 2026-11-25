import type { AssetVariant } from "../types";

interface ResultActionsProps {
  variant: AssetVariant;
  fileName: string;
  busy: boolean;
  onRegenerate: () => void;
  onNewPrompt: () => void;
}

/** Ações sobre um desenho pronto (plano da tela §23). "Pedir de novo" cria outro pedido igual. */
export function ResultActions({
  variant,
  fileName,
  busy,
  onRegenerate,
  onNewPrompt,
}: ResultActionsProps) {
  return (
    <div className="result-actions">
      <button
        type="button"
        className="button button--primary"
        onClick={onRegenerate}
        disabled={busy}
      >
        Pedir de novo
      </button>
      <button type="button" className="button button--ghost" onClick={onNewPrompt}>
        Novo pedido
      </button>
      {variant.url ? (
        <a
          className="button button--ghost"
          href={variant.url}
          download={fileName}
          // O arquivo vem da mesma origem (proxy /api), então `download`
          // funciona sem abrir o PNG em outra aba.
        >
          Baixar PNG
        </a>
      ) : null}
    </div>
  );
}
