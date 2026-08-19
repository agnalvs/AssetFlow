import { useEffect, useRef, useState } from "react";

import type { AssetVariant, ModeConfig } from "../types";

interface AssetPreviewProps {
  variant: AssetVariant;
  mode: ModeConfig;
  alt: string;
}

/**
 * Preview do asset (plano da tela §19 a §22, plano Pixel §79 a §81).
 *
 * Duas regras diferentes convivem aqui:
 *
 * - Arte 2D usa `object-fit: contain` e suavização normal do navegador.
 * - Pixel Art é ampliada com `image-rendering: pixelated` (nearest-neighbor) e
 *   **em escala inteira**. Escala fracionária — `scale(7.8125)` — produz
 *   linhas de pixel com larguras diferentes, e o sprite parece defeituoso
 *   (plano Pixel §81). Por isso o componente mede o quadro e escolhe o maior
 *   múltiplo inteiro que cabe, em vez de esticar a imagem para 100%.
 */
export function AssetPreview({ variant, mode, alt }: AssetPreviewProps) {
  const logicalWidth = variant.logical_width ?? variant.width;
  const logicalHeight = variant.logical_height ?? variant.height;
  const logicalSize = `${logicalWidth} × ${logicalHeight}`;

  const frameRef = useRef<HTMLDivElement>(null);
  const scale = useIntegerScale(frameRef, logicalWidth, logicalHeight, mode.pixelated);

  const pixelated = mode.pixelated;
  const style = pixelated
    ? { width: `${logicalWidth * scale}px`, height: `${logicalHeight * scale}px` }
    : undefined;

  return (
    <figure className="preview">
      <div
        className={`preview__frame${pixelated ? " preview__frame--pixelated" : ""}`}
        ref={frameRef}
      >
        {variant.url ? (
          <img
            className="preview__image"
            src={variant.url}
            alt={alt}
            width={variant.width}
            height={variant.height}
            style={style}
            draggable={false}
          />
        ) : (
          <p className="preview__missing">A imagem não pôde ser carregada.</p>
        )}
      </div>
      <figcaption className="preview__caption">
        <span className="preview__mode">{mode.label}</span>
        <span className="preview__separator" aria-hidden="true">
          •
        </span>
        <span className="preview__size">{logicalSize} px</span>
        {variant.color_count !== null && (
          <>
            <span className="preview__separator" aria-hidden="true">
              •
            </span>
            <span className="preview__colors">{variant.color_count} cores</span>
          </>
        )}
        {variant.pixel_exact === true && (
          <span
            className="preview__badge"
            title="Resolução lógica real, paleta dentro do limite e alpha binário — validado pelo AssetFlow."
          >
            PIXEL EXACT ✓
          </span>
        )}
      </figcaption>
    </figure>
  );
}

/**
 * Maior ampliação **inteira** que cabe no quadro (mínimo 1×).
 *
 * O quadro é responsivo (`min(420px, 72vw)`), então o valor precisa ser
 * recalculado quando a janela muda — daí o `ResizeObserver`.
 */
function useIntegerScale(
  frameRef: React.RefObject<HTMLDivElement>,
  width: number,
  height: number,
  enabled: boolean,
): number {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const frame = frameRef.current;
    if (!enabled || !frame || width <= 0 || height <= 0) {
      setScale(1);
      return;
    }

    const measure = () => {
      const style = window.getComputedStyle(frame);
      const padding =
        parseFloat(style.paddingLeft || "0") + parseFloat(style.paddingRight || "0");
      const available = Math.min(
        frame.clientWidth - padding,
        frame.clientHeight - padding,
      );
      const fit = Math.floor(available / Math.max(width, height));
      setScale(Math.max(1, fit));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(frame);
    return () => observer.disconnect();
  }, [frameRef, width, height, enabled]);

  return scale;
}
