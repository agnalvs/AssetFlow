import type { AssetVariant } from "../types";

interface ResultActionsProps {
  variant: AssetVariant;
  fileName: string;
  busy: boolean;
  onRegenerate: () => void;
  onNewPrompt: () => void;
}

/** Ações pós-geração (plano da tela §23). */
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
        Gerar novamente
      </button>
      <button type="button" className="button button--ghost" onClick={onNewPrompt}>
        Novo prompt
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
