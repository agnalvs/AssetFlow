import { useState } from "react";

import type { PreviewError } from "../hooks/usePromptPreview";
import type { PromptPreview, SemanticPrompt } from "../types";

interface PromptInspectorProps {
  preview: PromptPreview | null;
  loading: boolean;
  error: PreviewError | null;
  edited: boolean;
  stale: boolean;
  disabled?: boolean;
  onEdit: (semantic: SemanticPrompt | null) => void;
}

/**
 * O que o AssetFlow entendeu da descrição — e onde discordar.
 *
 * A descrição é uma frase; o que chega ao motor é uma estrutura. Entre as
 * duas há decisões que ninguém pediu explicitamente: a vista lateral, a pose
 * parada, a lista de termos barrados para que o modelo não devolva uma folha
 * de sprite. Quando a imagem sai errada, essas decisões são a primeira
 * suspeita — e até agora eram invisíveis.
 *
 * O painel nasce fechado. Ele é uma ferramenta de quando algo deu errado, não
 * um formulário: quem só quer um sprite escreve a frase e clica em gerar, e a
 * complexidade fica dobrada até ser pedida.
 *
 * Sobre editar: o que está no quadro é literalmente o que será enviado. O
 * AssetFlow não reaplica os padrões dele por cima de uma correção — tirar
 * "sprite sheet" da lista de `avoid` tira mesmo, com a consequência junto.
 */
export function PromptInspector({
  preview,
  loading,
  error,
  edited,
  stale,
  disabled = false,
  onEdit,
}: PromptInspectorProps) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  const editing = draft !== null;

  if (!preview && !loading && !error) return null;

  const startEditing = () => {
    if (!preview) return;
    setDraft(JSON.stringify(preview.semantic, null, 2));
    setParseError(null);
  };

  const cancelEditing = () => {
    setDraft(null);
    setParseError(null);
  };

  const apply = () => {
    if (draft === null) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(draft);
    } catch (caught) {
      setParseError(
        caught instanceof Error ? `JSON inválido: ${caught.message}` : "JSON inválido.",
      );
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setParseError("O conteúdo precisa ser um objeto JSON.");
      return;
    }
    // O contrato de campos quem confere é o backend, na pré-visualização:
    // duplicar a validação aqui só criaria duas versões da mesma regra.
    onEdit(parsed as SemanticPrompt);
    setDraft(null);
    setParseError(null);
  };

  return (
    <section className={`inspector${open ? " inspector--open" : ""}`}>
      <button
        type="button"
        className="inspector__toggle"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="inspector__chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="inspector__title">O que o AssetFlow entendeu</span>
        {edited ? <span className="inspector__badge">editado</span> : null}
        {stale ? (
          <span className="inspector__badge inspector__badge--warn">desatualizado</span>
        ) : null}
        {loading ? <span className="inspector__loading">lendo…</span> : null}
      </button>

      {open ? (
        <div className="inspector__body">
          {stale ? (
            <p className="inspector__notice">
              A descrição mudou depois da sua correção. O que está abaixo é o que será
              enviado — a frase nova só entra se você voltar ao automático.
            </p>
          ) : null}

          {error ? (
            <div className="inspector__error" role="alert">
              <p>{error.message}</p>
              {error.fields.length > 0 ? (
                <ul className="inspector__fields">
                  {error.fields.map((field) => (
                    <li key={`${field.campo}:${field.erro}`}>
                      <code>{field.campo}</code> — {field.erro}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {editing ? (
            <>
              <textarea
                className="inspector__editor"
                value={draft}
                spellCheck={false}
                rows={20}
                aria-label="Semântica do pedido, em JSON"
                onChange={(event) => setDraft(event.target.value)}
              />
              {parseError ? (
                <p className="inspector__error" role="alert">
                  {parseError}
                </p>
              ) : null}
            </>
          ) : preview ? (
            <pre className="inspector__json">
              {JSON.stringify(preview.semantic, null, 2)}
            </pre>
          ) : null}

          <div className="inspector__actions">
            {editing ? (
              <>
                <button type="button" className="inspector__action" onClick={apply}>
                  Aplicar
                </button>
                <button
                  type="button"
                  className="inspector__action inspector__action--ghost"
                  onClick={cancelEditing}
                >
                  Cancelar
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="inspector__action"
                  disabled={disabled || !preview}
                  onClick={startEditing}
                >
                  Editar
                </button>
                {edited ? (
                  <button
                    type="button"
                    className="inspector__action inspector__action--ghost"
                    disabled={disabled}
                    onClick={() => onEdit(null)}
                  >
                    Voltar ao automático
                  </button>
                ) : null}
              </>
            )}
          </div>

          {preview && !editing ? <NeutralReading preview={preview} /> : null}
        </div>
      ) : null}
    </section>
  );
}

/**
 * A renderização textual neutra, em segundo plano e rotulada como tal.
 *
 * Ela ajuda a conferir a leitura com olho humano, mas **não** é a string que
 * chega ao modelo: um motor com dialeto próprio relê a semântica e monta o
 * texto dele. Apresentá-la como "o prompt enviado" faria alguém concluir que
 * o modelo ignorou uma palavra que ele nunca recebeu.
 */
function NeutralReading({ preview }: { preview: PromptPreview }) {
  return (
    <dl className="inspector__neutral">
      <dt>Leitura neutra</dt>
      <dd>{preview.positive}</dd>
      {preview.negative ? (
        <>
          <dt>Evitar</dt>
          <dd>{preview.negative}</dd>
        </>
      ) : null}
      <dd className="inspector__neutral-note">
        Texto de conferência. Um motor com dialeto próprio relê a estrutura acima e
        monta o prompt dele.
      </dd>
    </dl>
  );
}
