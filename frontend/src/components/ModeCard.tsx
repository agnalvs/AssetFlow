import type { ModeConfig } from "../types";

interface ModeCardProps {
  mode: ModeConfig;
  selected: boolean;
  disabled?: boolean;
  onSelect: (id: ModeConfig["id"]) => void;
}

/**
 * Card de seleção de modo.
 *
 * Implementado como `role="radio"` — a escolha é excludente e precisa
 * funcionar por teclado (plano da tela §42).
 */
export function ModeCard({ mode, selected, disabled = false, onSelect }: ModeCardProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      className={`mode-card${selected ? " mode-card--selected" : ""}`}
      onClick={() => onSelect(mode.id)}
    >
      <span className="mode-card__icon" aria-hidden="true">
        {mode.pixelated ? <PixelIcon /> : <BrushIcon />}
      </span>
      <span className="mode-card__body">
        <span className="mode-card__label">{mode.label}</span>
        <span className="mode-card__description">{mode.description}</span>
      </span>
      <span className="mode-card__check" aria-hidden="true">
        {selected ? <CheckIcon /> : null}
      </span>
    </button>
  );
}

function PixelIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18M15 3v18M3 9h18M3 15h18" opacity="0.5" />
    </svg>
  );
}

function BrushIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M15.5 4.5a2.1 2.1 0 0 1 3 3L11 15l-4 1 1-4z" />
      <path d="M5 19c1.5 0 2.5-.6 3-2-1.4.5-2 1.5-3 2z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.4">
      <path d="M5 12.5l4.5 4.5L19 7" />
    </svg>
  );
}
