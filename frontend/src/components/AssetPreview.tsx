import type { AssetVariant, ModeConfig } from "../types";

interface AssetPreviewProps {
  variant: AssetVariant;
  mode: ModeConfig;
  alt: string;
}

/**
 * Preview do asset (plano da tela §19 a §22).
 *
 * A diferença que importa: Pixel Art é ampliada com `image-rendering:
 * pixelated` (nearest-neighbor), senão o navegador borra os pixels e o asset
 * parece defeituoso. Arte 2D usa `object-fit: contain` e suavização normal.
 * A escolha é automática, derivada do modo — não é um toggle do usuário.
 */
export function AssetPreview({ variant, mode, alt }: AssetPreviewProps) {
  const logicalSize =
    variant.logical_width && variant.logical_height
      ? `${variant.logical_width} × ${variant.logical_height}`
      : `${variant.width} × ${variant.height}`;

  return (
    <figure className="preview">
      <div className={`preview__frame${mode.pixelated ? " preview__frame--pixelated" : ""}`}>
        {variant.url ? (
          <img
            className="preview__image"
            src={variant.url}
            alt={alt}
            width={variant.width}
            height={variant.height}
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
      </figcaption>
    </figure>
  );
}
