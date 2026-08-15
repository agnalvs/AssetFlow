import { forwardRef } from "react";

const MAX_LENGTH = 600;

interface PromptInputProps {
  value: string;
  placeholder: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

/**
 * Campo de descrição (plano da tela §8 e §9).
 *
 * `Ctrl/Cmd + Enter` envia — atalho esperado em ferramenta de criação, sem
 * roubar o Enter de quem está escrevendo várias linhas.
 */
export const PromptInput = forwardRef<HTMLTextAreaElement, PromptInputProps>(
  function PromptInput({ value, placeholder, disabled = false, onChange, onSubmit }, ref) {
    const remaining = MAX_LENGTH - value.length;

    return (
      <div className="prompt">
        <label className="prompt__label" htmlFor="prompt-input">
          Descreva o asset que você quer criar
        </label>
        <textarea
          id="prompt-input"
          ref={ref}
          className="prompt__field"
          value={value}
          placeholder={placeholder}
          maxLength={MAX_LENGTH}
          rows={5}
          disabled={disabled}
          spellCheck
          aria-describedby="prompt-counter"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              onSubmit();
            }
          }}
        />
        <div className="prompt__footer">
          <span className="prompt__hint">
            <kbd>Ctrl</kbd> + <kbd>Enter</kbd> para gerar
          </span>
          <span
            id="prompt-counter"
            className={`prompt__counter${remaining < 60 ? " prompt__counter--low" : ""}`}
          >
            {value.length}/{MAX_LENGTH}
          </span>
        </div>
      </div>
    );
  },
);
