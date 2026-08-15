import { type GenerationMode, MODE_LIST } from "../types";
import { ModeCard } from "./ModeCard";

interface GenerationModeSelectorProps {
  value: GenerationMode;
  disabled?: boolean;
  onChange: (mode: GenerationMode) => void;
}

/**
 * Seleção Pixel Art × 2D Normal (plano da tela §6 e §7).
 *
 * É aqui que o vocabulário do produto vira vocabulário de capacidade — e o
 * assunto termina. Nenhum componente abaixo sabe o que é `text_to_image.pixel`.
 */
export function GenerationModeSelector({
  value,
  disabled = false,
  onChange,
}: GenerationModeSelectorProps) {
  return (
    <div
      className="mode-selector"
      role="radiogroup"
      aria-label="Estilo do asset"
    >
      {MODE_LIST.map((mode) => (
        <ModeCard
          key={mode.id}
          mode={mode}
          selected={mode.id === value}
          disabled={disabled}
          onSelect={onChange}
        />
      ))}
    </div>
  );
}
